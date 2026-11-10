"""Worker de la file d'attente (processus séparé de l'API).

Lancement : ``python -m app.workers.runner``. Traite un job à la fois (séquentiel par défaut).
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.time import utcnow
from app.db.session import create_db_engine, create_session_factory, ensure_database_ready
from app.models import Job, JobStatus, JobStep, StepStatus, WorkerHeartbeat
from app.services.queue import claim_next_job, recover_stale_jobs, release_job
from app.workers.handlers import HANDLERS, StepContext

logger = logging.getLogger("app.worker")


class Worker:
    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.started_at = utcnow()
        self.stop_event = threading.Event()
        self.stale_after = timedelta(seconds=settings.worker_stale_seconds)
        self._log = {"worker_id": self.worker_id}

    # ----------------------------------------------------------------- présence

    def beat(self) -> None:
        now = utcnow()
        with self.session_factory() as s:
            hb = s.get(WorkerHeartbeat, self.worker_id)
            if hb is None:
                s.add(
                    WorkerHeartbeat(
                        worker_id=self.worker_id,
                        hostname=socket.gethostname(),
                        pid=os.getpid(),
                        started_at=self.started_at,
                        last_seen_at=now,
                    )
                )
            else:
                hb.last_seen_at = now
            # Nettoie les entrées de workers disparus depuis longtemps.
            s.execute(
                delete(WorkerHeartbeat).where(
                    WorkerHeartbeat.worker_id != self.worker_id,
                    WorkerHeartbeat.last_seen_at < now - 10 * self.stale_after,
                )
            )
            s.commit()

    def _job_heartbeat(self, job_id: str) -> None:
        now = utcnow()
        with self.session_factory() as s:
            s.execute(
                update(Job)
                .where(Job.id == job_id, Job.locked_by == self.worker_id)
                .values(heartbeat_at=now)
            )
            s.commit()
        self.beat()

    # ----------------------------------------------------------------- boucle

    def run_once(self) -> bool:
        """Reprend les jobs abandonnés puis traite au plus un job (True si un job a tourné)."""
        self.beat()
        with self.session_factory() as s:
            recover_stale_jobs(s, self.stale_after)
            job_id = claim_next_job(s, self.worker_id)
        if job_id is None:
            return False
        self.process_job(job_id)
        return True

    def run_forever(self) -> None:
        logger.info("Worker démarré", extra=self._log)
        try:
            while not self.stop_event.is_set():
                if not self.run_once():
                    self.stop_event.wait(self.settings.worker_poll_seconds)
        finally:
            with self.session_factory() as s:
                s.execute(
                    delete(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == self.worker_id)
                )
                s.commit()
            logger.info("Worker arrêté", extra=self._log)

    # ----------------------------------------------------------------- exécution

    def process_job(self, job_id: str) -> None:
        log = {**self._log, "job_id": job_id}
        try:
            self._execute_steps(job_id, log)
        except KeyboardInterrupt:
            # Arrêt manuel (Ctrl+C) : on rend le job à la file, les étapes terminées sont gardées.
            with self.session_factory() as s:
                release_job(s, job_id, self.worker_id)
            logger.warning("Arrêt du worker : job remis en file", extra=log)
            raise

    def _execute_steps(self, job_id: str, log: dict[str, object]) -> None:
        with self.session_factory() as s:
            job = s.get(Job, job_id)
            assert job is not None
            kind, attempt = job.kind, job.attempts
            steps = list(
                s.scalars(
                    select(JobStep).where(JobStep.job_id == job_id).order_by(JobStep.position)
                )
            )
            step_ids = [(st.id, st.name, st.status) for st in steps]
        handler = HANDLERS.get(kind)
        total = len(step_ids)
        logger.info("Traitement du job (tentative %s)", attempt, extra={**log, "kind": kind})

        if handler is None:
            self._finish(job_id, JobStatus.FAILED, f"Aucun handler pour le type de job « {kind} ».")
            return

        done = sum(1 for _, _, status in step_ids if status == StepStatus.COMPLETED)
        for step_id, step_name, step_status in step_ids:
            if step_status == StepStatus.COMPLETED:
                continue  # reprise : ne jamais rejouer une étape réussie
            if self._cancel_requested(job_id):
                self._cancel(job_id)
                logger.info("Job annulé entre deux étapes", extra=log)
                return
            self._start_step(job_id, step_id, step_name)
            ctx = StepContext(
                job_id=job_id,
                kind=kind,
                step_name=step_name,
                attempt=attempt,
                step_seconds=self.settings.demo_step_seconds,
                heartbeat=lambda: self._job_heartbeat(job_id),
            )
            try:
                handler(ctx)
            except Exception as exc:  # noqa: BLE001 — l'erreur est persistée et journalisée
                message = str(exc) or exc.__class__.__name__
                self._fail_step(job_id, step_id, message)
                logger.exception("Échec de l'étape", extra={**log, "step": step_name})
                return
            done += 1
            self._complete_step(job_id, step_id, done / total)
            logger.info("Étape terminée", extra={**log, "step": step_name})

        self._finish(job_id, JobStatus.COMPLETED, None)
        logger.info("Job terminé", extra={**log, "status": "completed"})

    # ----------------------------------------------------------------- persistance

    def _cancel_requested(self, job_id: str) -> bool:
        with self.session_factory() as s:
            return bool(s.scalar(select(Job.cancel_requested).where(Job.id == job_id)))

    def _start_step(self, job_id: str, step_id: str, step_name: str) -> None:
        now = utcnow()
        with self.session_factory() as s:
            s.execute(
                update(JobStep)
                .where(JobStep.id == step_id)
                .values(
                    status=StepStatus.RUNNING, started_at=now, finished_at=None, error_message=None
                )
            )
            s.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(current_step=step_name, heartbeat_at=now, updated_at=now)
            )
            s.commit()

    def _complete_step(self, job_id: str, step_id: str, progress: float) -> None:
        now = utcnow()
        with self.session_factory() as s:
            s.execute(
                update(JobStep)
                .where(JobStep.id == step_id)
                .values(status=StepStatus.COMPLETED, finished_at=now)
            )
            s.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(progress=min(progress, 1.0), heartbeat_at=now, updated_at=now)
            )
            s.commit()

    def _fail_step(self, job_id: str, step_id: str, message: str) -> None:
        now = utcnow()
        with self.session_factory() as s:
            s.execute(
                update(JobStep)
                .where(JobStep.id == step_id)
                .values(status=StepStatus.FAILED, finished_at=now, error_message=message)
            )
            s.commit()
        self._finish(job_id, JobStatus.FAILED, message)

    def _cancel(self, job_id: str) -> None:
        with self.session_factory() as s:
            s.execute(
                update(JobStep)
                .where(JobStep.job_id == job_id, JobStep.status == StepStatus.PENDING)
                .values(status=StepStatus.CANCELLED)
            )
            s.commit()
        self._finish(job_id, JobStatus.CANCELLED, None)

    def _finish(self, job_id: str, status: JobStatus, error: str | None) -> None:
        now = utcnow()
        with self.session_factory() as s:
            s.execute(
                update(Job)
                # Garde : ne pas écraser un job repris entre-temps par un autre worker.
                .where(Job.id == job_id, Job.locked_by == self.worker_id)
                .values(
                    status=status,
                    error_message=error,
                    finished_at=now,
                    updated_at=now,
                    current_step=None,
                    locked_by=None,
                    cancel_requested=False,
                )
            )
            s.commit()


def main() -> None:
    settings = get_settings()
    configure_logging(settings, "worker")
    engine = create_db_engine(settings)
    ensure_database_ready(engine, settings)
    worker = Worker(settings, create_session_factory(engine))
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
