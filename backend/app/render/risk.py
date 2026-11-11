"""Rapport de risques d'un short (cahier des charges §13).

INFORMATIF UNIQUEMENT : il ne bloque jamais l'export et n'affirme jamais qu'un clip est
juridiquement autorisé ou monétisable. Il rassemble ce qui est connu, ce qui ne l'est pas, et
des recommandations. L'utilisateur garde la décision finale.
"""

from __future__ import annotations

from typing import Any

RIGHTS_LABELS = {
    "unknown": "Inconnu / non vérifié",
    "owned": "Déclaré : vous êtes le créateur de la vidéo",
    "authorized": "Déclaré : autorisation obtenue du créateur",
    "licensed": "Déclaré : licence permettant la réutilisation",
}

DISCLAIMER = (
    "Ce rapport est une aide à la décision produite automatiquement. Il ne constitue ni un avis "
    "juridique ni une garantie de conformité aux règles des plateformes ou d'éligibilité à la "
    "monétisation. La décision d'exporter et de publier vous appartient."
)


def build_risk_report(
    *,
    source: dict[str, Any],
    profile: dict[str, Any],
    plan: dict[str, Any] | None,
    plan_engine: str | None,
    subtitles_translated: bool,
    subtitles_enabled: bool,
    candidate: dict[str, Any] | None,
    qc: dict[str, Any] | None,
) -> dict[str, Any]:
    rights = source.get("rights_status") or "unknown"
    own = rights == "owned"

    # Transformation éditoriale : éléments ajoutés à la séquence d'origine.
    added: list[str] = ["recadrage vertical 9:16"]
    if subtitles_enabled:
        added.append("sous-titres traduits" if subtitles_translated else "sous-titres animés")
    if plan and plan.get("hook_text"):
        added.append("accroche")
    if plan and plan.get("cta_text"):
        added.append("appel à l'action")
    if plan and plan.get("zooms"):
        added.append(f"{len(plan['zooms'])} zoom(s)")
    level = "modérée" if len(added) >= 4 else "faible"
    transformation = {
        "level": level,
        "added": added,
        "missing": ["narration originale", "musique ou habillage sonore"],
        "detail": (
            "Le short reprend la séquence et l'audio d'origine avec un habillage. Sans narration "
            "ni commentaire original, la valeur ajoutée reste limitée."
        ),
    }

    if own:
        reused = {"level": "faible", "detail": "Vous déclarez être le créateur de la source."}
    elif rights in {"authorized", "licensed"}:
        reused = {
            "level": "modéré",
            "detail": "Réutilisation déclarée autorisée ; conservez la preuve de l'autorisation "
            "ou de la licence et créditez la source.",
        }
    else:
        reused = {
            "level": "élevé",
            "detail": "Droits non vérifiés sur un contenu de tiers peu transformé : risque de "
            "réclamation de droits d'auteur et de refus de monétisation pour « contenu "
            "réutilisé ».",
        }

    audio = {
        "status": "non_analysé",
        "detail": "La détection de musique n'est pas encore disponible (Phase 5) : l'audio "
        "d'origine est conservé tel quel. Une musique commerciale éventuelle n'a pas été "
        "recherchée ni atténuée.",
    }
    facecam = {
        "status": "non_vérifié",
        "detail": "La détection du facecam n'est pas encore disponible (Phase 5) : un visage "
        "présent dans la source peut apparaître dans le short.",
    }

    ai_warnings = list((candidate or {}).get("warnings", [])) + list(
        (plan or {}).get("warnings", [])
    )
    if plan_engine == "fallback":
        ai_warnings.append("Plan éditorial construit sans IA.")
    if plan and plan.get("hook_kind") == "original":
        ai_warnings.append(
            f"Accroche originale (non prononcée dans la vidéo) : « {plan.get('hook_text')} ». "
            "Vérifiez qu'elle ne promet rien d'absent."
        )
    qc_warnings = [
        f"{c['label']} : {c['detail']}" for c in (qc or {}).get("checks", []) if not c["ok"]
    ]

    recommendations: list[str] = []
    if not own:
        recommendations.append(
            f"Créditez la source : « {source.get('title') or 'vidéo d’origine'} » de "
            f"{source.get('uploader') or 'créateur inconnu'} ({source.get('url')})."
        )
    if rights == "unknown":
        recommendations.append(
            "Vérifiez et documentez vos droits avant publication (fiche du projet > Droits)."
        )
    recommendations.append("Regardez le short en entier avant de le publier.")
    if level == "faible":
        recommendations.append(
            "Ajoutez une valeur éditoriale (commentaire, narration) pour réduire le risque de "
            "« contenu réutilisé »."
        )

    return {
        "source": {
            "title": source.get("title"),
            "creator": source.get("uploader"),
            "url": source.get("url"),
            "platform_license": source.get("platform_license") or "non indiquée",
        },
        "rights": {
            "status": rights,
            "label": RIGHTS_LABELS.get(rights, rights),
            "note": source.get("rights_note"),
            "verified_by_app": False,
        },
        "audio_music": audio,
        "transformation": transformation,
        "reused_content": reused,
        "facecam": facecam,
        "ai_warnings": ai_warnings,
        "qc_warnings": qc_warnings,
        "recommendations": recommendations,
        "blocking": False,
        "disclaimer": DISCLAIMER,
        "profile": profile.get("name"),
    }


def export_warnings(report: dict[str, Any], qc: dict[str, Any] | None) -> list[str]:
    """Avertissements à présenter avant la confirmation d'export."""
    warnings: list[str] = []
    if report["rights"]["status"] == "unknown":
        warnings.append("Droits sur la source non vérifiés.")
    if report["reused_content"]["level"] == "élevé":
        warnings.append("Risque élevé de « contenu réutilisé » (réclamation, monétisation).")
    warnings.append("Musique d'origine non analysée (Phase 5).")
    warnings.append("Présence éventuelle d'un facecam non vérifiée (Phase 5).")
    warnings += report.get("qc_warnings", [])
    warnings += [w for w in report.get("ai_warnings", []) if w.startswith("Accroche originale")]
    return warnings
