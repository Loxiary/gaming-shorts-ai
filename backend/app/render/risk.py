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
    audio: dict[str, Any] | None = None,
    facecam: dict[str, Any] | None = None,
    credits: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    rights = source.get("rights_status") or "unknown"
    audio = audio or {}
    narration = audio.get("narration", {})
    added_music = audio.get("music", {})
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
    has_narration = narration.get("status") == "added"
    has_music = added_music.get("status") == "added"
    if has_narration:
        added.append(f"narration de synthèse ({len(narration.get('lines', []))} ligne(s))")
    if has_music:
        added.append("musique de fond sous licence")
    effects = (plan or {}).get("effects") or []
    if effects:
        added.append(f"{len(effects)} effet(s) ponctuel(s)")
    if (
        profile.get("transition_in", "none") != "none"
        or profile.get("transition_out", "none") != "none"
    ):
        added.append("transitions")
    missing = []
    if not has_narration:
        missing.append("narration ou commentaire original")
    if not has_music:
        missing.append("musique ou habillage sonore")
    level = "faible"
    if len(added) >= 4:
        level = "modérée"
    if has_narration and len(added) >= 5:
        level = "élevée"
    transformation = {
        "level": level,
        "added": added,
        "missing": missing,
        "detail": (
            "Narration ajoutée : elle apporte du contexte, mais une voix de synthèse factuelle "
            "ne remplace pas un vrai commentaire personnel."
            if has_narration
            else "Le short reprend la séquence et l'audio d'origine avec un habillage. Sans "
            "narration ni commentaire original, la valeur ajoutée reste limitée."
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

    audio_music = _audio_section(audio.get("source_music") or {}, added_music)
    facecam_section = _facecam_section(facecam or {})

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
    if audio_music["status"] in {"détectée", "résiduelle"}:
        recommendations.append(
            "Écoutez l'aperçu audio : une musique d'origine reste présente. Une musique "
            "commerciale peut déclencher une réclamation automatique (Content ID) ; augmentez "
            "l'atténuation dans le profil si besoin."
        )
    if facecam_section["status"] in {"incertain", "non_exclu"}:
        recommendations.append("Vérifiez qu'aucun visage de la webcam du créateur n'apparaît.")
    for c in credits or []:
        recommendations.append(f"Ajoutez ce crédit à la description : {c['text']}")
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
        "audio_music": audio_music,
        "transformation": transformation,
        "reused_content": reused,
        "facecam": facecam_section,
        "credits": credits or [],
        "audio_notes": list(audio.get("notes", [])),
        "ai_warnings": ai_warnings,
        "qc_warnings": qc_warnings,
        "recommendations": recommendations,
        "blocking": False,
        "disclaimer": DISCLAIMER,
        "profile": profile.get("name"),
    }


def _audio_section(src: dict[str, Any], added: dict[str, Any]) -> dict[str, Any]:
    status = src.get("status")
    extra = (
        f" Musique ajoutée : « {added.get('title')} » ({added.get('license')})."
        if added.get("status") == "added"
        else ""
    )
    if status in (None, "unavailable"):
        return {
            "status": "non_analysée",
            "detail": "La musique d'origine n'a pas été analysée (modèle absent ou analyse "
            "désactivée) : une musique commerciale éventuelle n'a été ni recherchée ni "
            "atténuée." + extra,
        }
    if status == "disabled":
        return {
            "status": "non_analysée",
            "detail": "Analyse de la musique d'origine désactivée dans le profil." + extra,
        }
    ratio = float(src.get("ratio", 0))
    if status == "none":
        return {
            "status": "absente",
            "detail": f"Pas de musique détectée dans l'audio d'origine ({ratio:.0%} des "
            "secondes au-dessus du seuil). Détection automatique : elle peut manquer une "
            "musique très discrète." + extra,
        }
    if src.get("attenuated"):
        residual = float(src.get("residual_ratio", 0))
        state = "résiduelle" if residual >= 0.1 else "atténuée"
        return {
            "status": state,
            "detail": f"Musique détectée sur {ratio:.0%} de l'extrait, atténuée de "
            f"{src.get('reduction_db', 0):.0f} dB par séparation de sources (voix "
            f"conservées). Après traitement, une musique reste détectable (à niveau réduit) "
            f"sur {residual:.0%} des secondes : le détecteur repère aussi une musique très "
            "atténuée. Une atténuation réduit le risque de réclamation sans le supprimer." + extra,
        }
    return {
        "status": "détectée",
        "detail": f"Musique détectée sur {ratio:.0%} de l'extrait et CONSERVÉE (profil en mode "
        "« détection seule »)." + extra,
    }


def _facecam_section(fc: dict[str, Any]) -> dict[str, Any]:
    status = fc.get("status")
    if status == "detected" and fc.get("crop"):
        return {
            "status": "exclu",
            "detail": f"Facecam détecté (bord {fc.get('crop_side')}) et exclu par recadrage "
            f"({fc.get('loss', 0):.0%} de l'image retirée)."
            + (f" {fc['warning']}" if fc.get("warning") else ""),
        }
    if status in ("detected", "detected_not_cropped"):
        return {"status": "non_exclu", "detail": fc.get("warning") or "Facecam non exclu."}
    if status == "uncertain":
        return {"status": "incertain", "detail": fc.get("warning") or "Détection incertaine."}
    if status == "none":
        return {
            "status": "absent",
            "detail": f"Aucun visage persistant sur {fc.get('frames_analyzed', 0)} images "
            "échantillonnées.",
        }
    if status == "disabled":
        return {"status": "non_vérifié", "detail": "Détection du facecam désactivée (profil)."}
    return {
        "status": "non_vérifié",
        "detail": fc.get("warning") or "Présence d'un facecam non vérifiée.",
    }


def export_warnings(report: dict[str, Any], qc: dict[str, Any] | None) -> list[str]:
    """Avertissements à présenter avant la confirmation d'export."""
    warnings: list[str] = []
    if report["rights"]["status"] == "unknown":
        warnings.append("Droits sur la source non vérifiés.")
    if report["reused_content"]["level"] == "élevé":
        warnings.append("Risque élevé de « contenu réutilisé » (réclamation, monétisation).")
    music = report.get("audio_music", {})
    if music.get("status") == "non_analysée":
        warnings.append("Musique d'origine non analysée.")
    elif music.get("status") == "détectée":
        warnings.append("Musique d'origine conservée (risque de réclamation).")
    elif music.get("status") == "résiduelle":
        warnings.append(
            "Musique d'origine atténuée mais encore détectable (risque de réclamation réduit, "
            "non nul)."
        )
    fc = report.get("facecam", {})
    if fc.get("status") in {"non_vérifié", "incertain", "non_exclu"}:
        warnings.append(f"Facecam : {fc.get('detail')}")
    if report.get("credits"):
        warnings.append("Crédits à ajouter à la description (voix ou musique sous licence).")
    warnings += report.get("qc_warnings", [])
    warnings += [w for w in report.get("ai_warnings", []) if w.startswith("Accroche originale")]
    return warnings
