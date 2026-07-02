# -*- coding: utf-8 -*-
"""
payment_doc_extractor.py — Groupe Bayoudh Metal
Orchestrateur principal pour l'analyse des documents de paiement
(chèques et traites / lettres de change tunisiennes).

Utilisé par ocr_pipeline.py via :
    from ocr_intelligent.ocr.payment_doc_extractor import analyser_document_paiement
    from ocr_intelligent.ocr.payment_doc_extractor import _normaliser_payment_method
"""

import os
import re
import time
from datetime import datetime

from ocr_intelligent.ocr.payment_commons import (
    _ocr_log,
    _OCR_CACHE,
    _identifier_type_document,
    _detecter_type_alternatif,
    _evaluer_qualite,
    _normaliser_payment_method,
    _pretraiter_texte_ocr,
    _ameliorer_image_floue,
    _md5_image,
    _mapper_frappe,
    _MAPPING_FRAPPE_CHEQUE,
    _MAPPING_FRAPPE_TRAITE,
    _LABELS_TYPE,
    PEREMPTION_CHEQUE_MOIS,
)

from ocr_intelligent.ocr.cheque_extractor import (
    _corriger_annee_ocr,
    _extraire_champs_cheque,
    _extraire_dates_image_cheque,
    post_traiter_cheque,
)

from ocr_intelligent.ocr.traite_extractor import (
    _extraire_champs_traite,
    post_traiter_traite,
)


# ──────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ──────────────────────────────────────────────────────────────────────


def _libelle_type_document(doc_type: str) -> str:
    """Retourne le libellé lisible d'un type de document (clé depuis _LABELS_TYPE)."""
    return _LABELS_TYPE.get(doc_type, (doc_type or "inconnu")).strip()


def _construire_message_type_invalide(type_attendu: str, type_detecte: str) -> str:
    """
    Construit le message d'erreur utilisateur quand le type de document soumis
    ne correspond pas au mode de paiement sélectionné.
    """
    label_attendu = _libelle_type_document(type_attendu)
    label_detecte = _libelle_type_document(type_detecte)
    return (
        f"Document refusé : le mode de paiement sélectionné est « {label_attendu} », "
        f"mais le document soumis a été détecté comme « {label_detecte} ». "
        f"Veuillez soumettre uniquement un document de type « {label_attendu} »."
    )


# Mots-clés présents sur les traites mais jamais sur les chèques
# AMÉLIORATION : patterns plus tolérants aux erreurs OCR (espaces, accents, casse)
_MOTS_EXCLUSIFS_TRAITE = re.compile(
    r"(?:"
    # Lettre de change
    r"lettre\s*de\s*change"
    # Échéance (avec variations OCR courantes : é/e, espaces, etc.)
    r"|[eéèê]\s*ch?\s*[eéèê]\s*ance"
    r"|ech\s*ance"
    r"|[eé]ch[eéèê]\s*ance"
    # Tireur / Tiré
    r"|tireur|tir[eéèê]\b|ti\s*reur|ti\s*r[eéèê]"
    # Domiciliation
    r"|domiciliat(?:aire|ion)"
    r"|domicili\s*ation"
    # Aval
    r"|aval\b|bon\s+pour\s+aval"
    # Veuillez payer / Ordre de paiement
    r"|veuillez\s+payer|ordre\s+de\s+paiement"
    # Anglais
    r"|bill\s+of\s+exchange|effet\s+de\s+commerce"
    # Indicateurs spécifiques traites tunisiennes
    r"|valeur\s+en\s+compte|valeur\s+re[çc]ue"
    # Labels tunisiens courants sur traites (souvent au milieu du document)
    r"|حلول\s*الأجل"  # "échéance" en arabe
    r"|تاريخ\s*الاحداث"  # "date de création" en arabe
    r")",
    re.IGNORECASE,
)

# Mots-clés présents sur les chèques mais jamais sur les traites
# NB : "endossable" survit même au bruit OCR (ex : "won endossable" → match)
_MOTS_EXCLUSIFS_CHEQUE = re.compile(
    r"\b(?:endossable|non\s+endossable|payez\s+contre\s+ce\s+ch[eèé]que"
    r"|payez\s+(?:\w+\s+){0,3}ch[eèé]que|chequi[eé]r|carnet\s+de\s+ch[eèé]ques)\b",
    re.IGNORECASE,
)


def _cheque_est_perime(*dates_candidates: str) -> bool:
    """
    Détermine si un chèque est périmé en vérifiant si l'une des dates
    candidates dépasse le seuil configuré (PEREMPTION_CHEQUE_MOIS × 30.44 jours).
    Retourne True si au moins une date est périmée.
    """
    seuil_jours = int(PEREMPTION_CHEQUE_MOIS * 30.44)
    for date_value in dates_candidates:
        if not date_value:
            continue
        try:
            delta_jours = (datetime.now() - datetime.strptime(date_value[:10], "%Y-%m-%d")).days
        except ValueError:
            continue
        if delta_jours > seuil_jours:
            return True
    return False


def analyser_document_paiement(
    chemin_img: str,
    texte_ocr: str = "",
    payment_method: str = "",
    score_ocr: float = 0,
) -> dict:
    """
    Analyse un document de paiement (chèque ou traite).

    Retourne un dict avec :
        valid                   bool
        document_type_detected  str   ("cheque" | "traite" | "inconnu")
        form_fields             dict  champs OCR bruts
        champs_remplis          dict  champs mappés Frappe
        uncertain_fields        list
        image_enhanced          bool
        date_cheque_retenue     str | None  (ISO YYYY-MM-DD)
        errors                  list
        confiance               float
    """
    t_debut = time.monotonic()
    errors = []
    image_enhanced = False

    # ── 0. Cache MD5 ──────────────────────────────────────────────────
    md5 = _md5_image(chemin_img) if chemin_img and os.path.exists(chemin_img) else None
    cache_key = f"{md5}:{payment_method}" if md5 else None
    if cache_key and cache_key in _OCR_CACHE:
        _ocr_log(f"analyser_document_paiement: cache hit {cache_key[:16]}…", "info")
        return _OCR_CACHE[cache_key]

    # ── 1. Prétraitement texte ────────────────────────────────────────
    texte = _pretraiter_texte_ocr(texte_ocr or "")

    # ── 2. Amélioration image si qualité insuffisante ─────────────────
    qualite_insuffisante = _evaluer_qualite(texte, score_ocr)
    if qualite_insuffisante and chemin_img and os.path.exists(chemin_img):
        _ocr_log("qualité insuffisante → amélioration image", "info")
        texte_enh, score_enh = _ameliorer_image_floue(chemin_img)
        if texte_enh and len(texte_enh.split()) > len(texte.split()):
            texte = _pretraiter_texte_ocr(texte_enh)
            score_ocr = max(score_ocr, score_enh)
            image_enhanced = True
            _ocr_log(f"image améliorée — score={score_enh}", "info")

    if not texte.strip():
        return _resultat_echec(
            "Aucun texte détecté dans le document. "
            "Vérifiez la qualité de l'image (min. 300 DPI).",
            errors,
        )

    # ── 3. Détection du type ──────────────────────────────────────────
    type_force = _normaliser_payment_method(payment_method)
    type_detecte, confiance_type = _identifier_type_document(texte)

    _contient_traite_exclusif = bool(_MOTS_EXCLUSIFS_TRAITE.search(texte))
    _contient_cheque_exclusif = bool(_MOTS_EXCLUSIFS_CHEQUE.search(texte))

    # ── 3.1. VÉRIFICATION DOUBLON PRÉCOCE (avant validation stricte) ──
    # Pour éviter de rejeter un document comme "inconnu" alors que c'est un doublon
    if type_force in ("cheque", "traite"):
        import frappe
        _ocr_log(f"Vérification doublon pour type_force={type_force}", "info")
        try:
            numero_ref = None
            
            if type_force == "cheque":
                from ocr_intelligent.ocr.cheque_extractor import _extraire_champs_cheque
                champs_temp = _extraire_champs_cheque(texte, chemin_img or "")
                numero_ref = champs_temp.get("numero_cheque", "").strip()
                _ocr_log(f"Chèque: numero_cheque extrait = {numero_ref!r}", "info")
            else:  # traite
                # Essayer d'extraire le numéro de traite avec patterns directs
                from ocr_intelligent.ocr.traite_extractor import _PATTERNS_CHAMP_TRAITE
                _ocr_log(f"Traite: extraction avec {len(_PATTERNS_CHAMP_TRAITE.get('numero_traite', []))} patterns", "info")
                
                # Essayer chaque pattern pour le numéro de traite
                for pattern in _PATTERNS_CHAMP_TRAITE.get("numero_traite", []):
                    match = re.search(pattern, texte, re.IGNORECASE | re.MULTILINE)
                    if match:
                        numero_candidat = match.group(1).strip()
                        # Nettoyer les espaces internes
                        numero_candidat = re.sub(r'\s+', '', numero_candidat)
                        if len(numero_candidat) >= 4:  # Minimum 4 caractères pour un numéro valide
                            numero_ref = numero_candidat
                            _ocr_log(f"Traite: numéro trouvé avec pattern '{pattern[:50]}...' → {numero_ref!r}", "info")
                            break
                
                if not numero_ref:
                    _ocr_log("Traite: aucun numéro trouvé avec les patterns directs", "warning")
            
            if numero_ref:
                _ocr_log(f"Recherche doublon avec reference_no={numero_ref}", "info")
                doublon = frappe.db.get_value(
                    "Payment Entry",
                    {"reference_no": numero_ref, "docstatus": ["!=", 2]},
                    ["name", "reference_date", "posting_date"],
                    as_dict=True,
                )
                _ocr_log(f"Résultat recherche doublon: {doublon}", "info")
                
                if doublon:
                    date_paiement = doublon.get("reference_date") or doublon.get("posting_date") or ""
                    if date_paiement:
                        try:
                            from datetime import datetime as _dt
                            date_paiement = _dt.strptime(str(date_paiement), "%Y-%m-%d").strftime("%d/%m/%Y")
                        except Exception:
                            date_paiement = str(date_paiement)
                    
                    doc_type_label = "chèque" if type_force == "cheque" else "traite"
                    _ocr_log(f"✓ DOUBLON CONFIRMÉ : {doc_type_label} N° {numero_ref} (date={date_paiement})", "warning")
                    
                    return {
                        "valid": False,
                        "doublon": True,
                        "doublon_name": doublon["name"],
                        "doublon_date": date_paiement,
                        "reference_no": numero_ref,
                        "document_type_detected": type_force,
                        "errors": [f"Ce {doc_type_label} existe déjà : N° {numero_ref} (enregistré le {date_paiement})."],
                        "form_fields": {},
                        "champs_remplis": {},
                        "uncertain_fields": [],
                        "image_enhanced": image_enhanced,
                        "confiance": 0.0,
                    }
                else:
                    _ocr_log(f"Aucun doublon trouvé pour reference_no={numero_ref}", "info")
            else:
                _ocr_log(f"Aucun numéro extrait pour {type_force}", "warning")
        except Exception as e:
            _ocr_log(f"ERREUR vérification doublon : {type(e).__name__}: {str(e)}", "error")
            import traceback
            _ocr_log(f"Traceback: {traceback.format_exc()}", "error")
            pass  # Continuer avec la validation normale

    # ── Cas 0 : Rejet immédiat des documents alternatifs (facture, BL, etc.) pour modes strict
    if type_force in ("cheque", "traite"):
        doc_alt = _detecter_type_alternatif(texte)
        if doc_alt and doc_alt not in ("cheque", "traite"):
            return _resultat_echec(
                f"Document refusé : le document soumis a été identifié comme « {_LABELS_TYPE.get(doc_alt, doc_alt)} ». "
                f"Le mode de paiement « {_LABELS_TYPE.get(type_force, type_force)} » accepte uniquement les documents de type {_LABELS_TYPE.get(type_force, type_force)}.",
                errors,
                doc_type="inconnu",
            )

    # ── Cas 1a : paiement = "chèque" mais document contient mots exclusifs traite
    if type_force == "cheque" and _contient_traite_exclusif:
        return _resultat_echec(
            _construire_message_type_invalide(type_force, "traite"),
            errors,
            doc_type="traite",
        )

    # ── Cas 1b : paiement = "traite" mais document contient mots exclusifs chèque
    if type_force == "traite" and _contient_cheque_exclusif:
        return _resultat_echec(
            _construire_message_type_invalide(type_force, "cheque"),
            errors,
            doc_type="cheque",
        )

    # ── Cas 2 : paiement forcé ("chèque" ou "traite") mais type détecté est clairement différent
    #            NB : si type_detecte == "inconnu" (OCR bruité), on fait confiance à type_force
    if type_force in ("cheque", "traite"):
        if type_detecte in ("cheque", "traite") and type_detecte != type_force:
            # Type clairement identifié mais c'est l'opposé → refus
            return _resultat_echec(
                _construire_message_type_invalide(type_force, type_detecte),
                errors,
                doc_type=type_detecte,
            )
        if type_detecte == "inconnu":
            # OCR bruité : vérifier d'abord s'il y a un type alternatif (facture, BL…)
            # Si oui → refus ; si non → faire confiance à type_force et continuer
            alt = _detecter_type_alternatif(texte)
            if alt:
                return _resultat_echec(
                    _construire_message_type_invalide(type_force, alt),
                    errors,
                    doc_type=alt,
                )
            # Si payment_method=chèque mais aucun indicateur chèque détecté →
            # impossible de confirmer : le document est peut-être une traite à OCR bruité
            if type_force == "cheque" and not _contient_cheque_exclusif:
                return _resultat_echec(
                    "Document refusé : le mode de paiement sélectionné est « chèque », "
                    "mais le document soumis ne contient aucun indicateur d'un chèque "
                    "(la mention « non endossable » est absente ou illisible). "
                    "Vérifiez que le document est bien un chèque ou améliorez la qualité de l'image.",
                    errors,
                    doc_type="inconnu",
                )
            # Si payment_method=traite mais aucun indicateur traite détecté →
            # Essayer quand même d'extraire les champs avant de rejeter (OCR peut être bruité)
            if type_force == "traite" and not _contient_traite_exclusif:
                _ocr_log("Traite sans indicateurs : tentative d'extraction des champs en mode relaxé", "warning")
                # Essayer d'extraire les champs de traite malgré tout
                try:
                    from ocr_intelligent.ocr.traite_extractor import _extraire_champs_traite
                    champs_test, _, _ = _extraire_champs_traite(texte)
                    
                    # Si on a extrait au moins 3 champs significatifs, accepter le document
                    champs_valides = 0
                    if champs_test.get("numero_traite"):
                        champs_valides += 1
                    if champs_test.get("amount", 0) > 0:
                        champs_valides += 2  # Le montant compte double
                    if champs_test.get("date_echeance"):
                        champs_valides += 1
                    if champs_test.get("tireur"):
                        champs_valides += 1
                    if champs_test.get("tire") or champs_test.get("domiciliation"):
                        champs_valides += 1
                    
                    if champs_valides >= 3:
                        _ocr_log(f"Traite acceptée malgré absence d'indicateurs : {champs_valides} champs extraits", "info")
                        # Continuer avec le traitement normal
                        pass
                    else:
                        _ocr_log(f"Traite rejetée : seulement {champs_valides} champs extraits (minimum 3 requis)", "warning")
                        return _resultat_echec(
                            "Document refusé : le mode de paiement sélectionné est « traite », "
                            "mais le document soumis ne contient aucun indicateur d'une traite "
                            "(les mentions « lettre de change », « échéance », « tireur » sont absentes ou illisibles) "
                            "et l'extraction automatique n'a pas pu récupérer suffisamment de champs. "
                            "Vérifiez que le document est bien une traite ou améliorez la qualité de l'image.",
                            errors,
                            doc_type="inconnu",
                        )
                except Exception as e:
                    _ocr_log(f"Erreur lors de la tentative d'extraction relaxée : {e}", "error")
                    return _resultat_echec(
                        "Document refusé : le mode de paiement sélectionné est « traite », "
                        "mais le document soumis ne contient aucun indicateur d'une traite "
                        "(les mentions « lettre de change », « échéance », « tireur » sont absentes ou illisibles). "
                        "Vérifiez que le document est bien une traite ou améliorez la qualité de l'image.",
                        errors,
                        doc_type="inconnu",
                    )

    # ── Cas 3 : détermination du type final
    if type_force:
        doc_type = type_force
        _ocr_log(f"type forcé par payment_method: {doc_type}", "info")
    elif type_detecte in ("cheque", "traite"):
        doc_type = type_detecte
        _ocr_log(f"type détecté: {doc_type} (conf={confiance_type:.2f})", "info")
    else:
        alt = _detecter_type_alternatif(texte)
        if alt:
            return _resultat_echec(
                f"Document identifié comme « {_LABELS_TYPE.get(alt, alt)} ». "
                "Ce module accepte uniquement les chèques et les traites.",
                errors,
                doc_type=alt,
            )
        return _resultat_echec(
            "Le moyen de paiement n'a pas été détecté . "
            "Veuillez sélectionner manuellement le moyen de paiement (Chèque ou Traite) "
            "avant de téléverser le document.",
            errors,
            doc_type="inconnu",
        )

    # ── 4. Extraction ─────────────────────────────────────────────────
    if doc_type == "cheque":
        result = _traiter_cheque(
            chemin_img=chemin_img,
            texte=texte,
            score_ocr=score_ocr,
            image_enhanced=image_enhanced,
            errors=errors,
            t_debut=t_debut,
        )
    else:
        # Pour les traites : passes OCR supplémentaires PSM11 + PSM4
        # Conditionnelles (texte faible) + cache MD5 + max 2× upscale + oem1
        _mots_base = len(texte.split())
        if chemin_img and os.path.exists(chemin_img) and _mots_base < 40:
            _cache_key_extra = f"traite_extra:{md5}" if md5 else None
            _cached_extra = _OCR_CACHE.get(_cache_key_extra) if _cache_key_extra else None
            if _cached_extra:
                texte = texte + "\n" + _cached_extra
                _ocr_log("traite: passes extra récupérées depuis cache", "info")
            else:
                try:
                    import pytesseract as _tess
                    from PIL import Image as _PILImg
                    _pil_orig = _PILImg.open(chemin_img).convert("RGB")
                    _w, _h = _pil_orig.size
                    _sf = min(2, max(1, int(2400 / _w)))  # max 2× upscale
                    _pil_big = _pil_orig.resize((_w * _sf, _h * _sf), _PILImg.LANCZOS)
                    _textes_extra = []
                    for _psm in (11, 4):
                        try:
                            _t = _tess.image_to_string(
                                _pil_big, lang="fra+eng", config=f"--oem 1 --psm {_psm}"
                            )
                            if _t.strip():
                                _textes_extra.append(_pretraiter_texte_ocr(_t))
                        except Exception:
                            pass
                    if _textes_extra:
                        _extra_combined = "\n".join(_textes_extra)
                        texte = texte + "\n" + _extra_combined
                        _ocr_log(f"traite: {len(_textes_extra)} passes OCR supplémentaires ajoutées", "info")
                        if _cache_key_extra:
                            _OCR_CACHE[_cache_key_extra] = _extra_combined
                except Exception:
                    pass
        else:
            _ocr_log(f"traite: passes extra ignorées (texte riche: {_mots_base} mots)", "info")
        result = _traiter_traite(
            texte=texte,
            errors=errors,
            t_debut=t_debut,
        )

    # ── 5. Cache ──────────────────────────────────────────────────────
    if cache_key and result.get("valid"):
        _OCR_CACHE[cache_key] = result

    _ocr_log(
        f"analyser_document_paiement TOTAL: {time.monotonic() - t_debut:.2f}s "
        f"type={doc_type} valid={result.get('valid')}",
        "info",
    )
    return result


# ──────────────────────────────────────────────────────────────────────
# TRAITEMENT CHÈQUE
# ──────────────────────────────────────────────────────────────────────


def _traiter_cheque(
    chemin_img: str,
    texte: str,
    score_ocr: float,
    image_enhanced: bool,
    errors: list,
    t_debut: float,
) -> dict:
    """
    Sous-orchestrateur du pipeline chèque :
      1. Extraction des champs (numéro, date, montant, bénéficiaire, RIB)
      2. Dates supplémentaires depuis l'image (si date non fiable en OCR)
      3. Post-traitement (bénéficiaire manuscrit, Vision API, nettoyages)
      4. Blocage dur si date périmée ou signature absente
    Retourne le dict résultat standard (valid, form_fields, champs_remplis…).
    """
    from datetime import datetime

    _ocr_log("=== _traiter_cheque ===", "info")
    t1 = time.monotonic()

    form_fields, incertains, confiance = _extraire_champs_cheque(texte)
    _ocr_log(f"TIMING _extraire_champs_cheque: {time.monotonic() - t1:.2f}s", "info")

    # Dates depuis l'image — skipé si la date est déjà extraite avec certitude du texte
    date_cheque_retenue = None

    _date_deja_fiable = (
        form_fields.get("date_cheque")
        and "date_cheque" not in incertains
    )
    if chemin_img and os.path.exists(chemin_img) and not _date_deja_fiable:
        t2 = time.monotonic()
        dates_img = _extraire_dates_image_cheque(chemin_img)
        _ocr_log(f"TIMING _extraire_dates_image_cheque: {time.monotonic() - t2:.2f}s", "info")

        # Appliquer la correction d'année OCR (ex: 2020→2026) AVANT le filtrage de validité.
        # Sans correction préalable, une date OCR de 2020 serait rejetée comme périmée alors qu'elle
        # représente en réalité 2026 (OCR confond '2' et '6' sur les 2 derniers chiffres).
        now = datetime.now()
        dates_img_corr = []
        for _d_raw in dates_img:
            try:
                _d_corr_str, _ = _corriger_annee_ocr(_d_raw.strftime("%Y-%m-%d"))
                _d_corr = datetime.strptime(_d_corr_str, "%Y-%m-%d")
                dates_img_corr.append(_d_corr)
            except Exception:
                dates_img_corr.append(_d_raw)

        # Filtrer par plage réaliste (passé ≤ PEREMPTION ou futur ≤ 18 mois)
        if dates_img_corr:
            dates_valides = []
            for d in dates_img_corr:
                delta_mois = (now - d).days / 30.44
                if 0 <= delta_mois <= PEREMPTION_CHEQUE_MOIS:
                    dates_valides.append(d)
                elif -18 <= delta_mois < 0:  # futur proche (jusqu'à 18 mois)
                    dates_valides.append(d)
            if dates_valides:
                date_retenue = min(dates_valides, key=lambda d: abs((now - d).days))
                date_cheque_retenue = date_retenue.strftime("%Y-%m-%d")
                _ocr_log(f"date chèque retenue depuis image: {date_cheque_retenue}", "info")
            else:
                # Scan effectué mais aucune date valide → sentinel "" pour éviter re-scan dans post_traiter_cheque
                date_cheque_retenue = ""
        else:
            # Scan effectué mais aucune date trouvée → sentinel "" pour éviter re-scan dans post_traiter_cheque
            date_cheque_retenue = ""

    # Post-traitement
    t3 = time.monotonic()
    form_fields, incertains, confiance = post_traiter_cheque(
        chemin_img=chemin_img,
        texte_traite=texte,
        form_fields=form_fields,
        incertains=incertains,
        confiance=confiance,
        date_cheque_retenue=date_cheque_retenue,
    )
    _ocr_log(f"TIMING post_traiter_cheque: {time.monotonic() - t3:.2f}s", "info")

    # Validation champs obligatoires (avertissements uniquement — ne bloquent pas)
    if not form_fields.get("champs_obligatoires_presents", False):
        manquants = []
        if not form_fields.get("numero_cheque"):
            manquants.append("numéro de chèque")
        if not form_fields.get("amount", 0) > 0:
            manquants.append("montant")
        if not form_fields.get("cheque_date"):
            manquants.append("date")
        if manquants:
            errors.append("Champs obligatoires manquants : {}.".format(", ".join(manquants)))

    # Blocage dur : date périmée
    hard_block = False
    date_brute_normalisee = ""
    if form_fields.get("date_cheque"):
        try:
            from ocr_intelligent.ocr.payment_commons import _normaliser_date
            date_brute_normalisee = _normaliser_date(form_fields.get("date_cheque")) or ""
        except Exception:
            date_brute_normalisee = ""

    if _cheque_est_perime(date_brute_normalisee, form_fields.get("cheque_date", "")):
        date_aff = date_brute_normalisee or form_fields.get("cheque_date", "")
        errors.append(
            "Document détecté : « Chèque ». "
            f"La date du chèque ({date_aff}) est expiré ; "
            "le document est refusé."
        )
        hard_block = True

    champs_remplis = _mapper_frappe(form_fields, _MAPPING_FRAPPE_CHEQUE)

    # Blocage dur : signature absente
    if not form_fields.get("signature_present", True):
        hard_block = True
        # L'erreur est déjà ajoutée dans post_traiter_cheque via form_fields["errors"]
        _sig_err = "Chèque rejeté : aucune signature détectée."
        if _sig_err not in errors:
            errors.append(_sig_err)

    valid = not hard_block

    return {
        "valid":                  valid,
        "document_type_detected": "cheque",
        "form_fields":            form_fields,
        "champs_remplis":         champs_remplis,
        "uncertain_fields":       list(set(incertains)),
        "image_enhanced":         image_enhanced,
        "date_cheque_retenue":    date_cheque_retenue,
        "confiance":              round(confiance, 3),
        "errors":                 errors,
    }


# ──────────────────────────────────────────────────────────────────────
# TRAITEMENT TRAITE
# ──────────────────────────────────────────────────────────────────────


def _traiter_traite(
    texte: str,
    errors: list,
    t_debut: float,
) -> dict:
    """
    Sous-orchestrateur du pipeline traite/lettre de change :
      1. Extraction des champs (numéro, dates, montant, tireur, tiré, domiciliation)
      2. Post-traitement (normalisation, fallbacks RIB/tireur)
    Retourne le dict résultat standard (valid toujours True pour les traites).
    """
    _ocr_log("=== _traiter_traite ===", "info")
    t1 = time.monotonic()

    form_fields, incertains, confiance = _extraire_champs_traite(texte)
    _ocr_log(f"TIMING _extraire_champs_traite: {time.monotonic() - t1:.2f}s", "info")

    form_fields = post_traiter_traite(form_fields=form_fields, texte_traite=texte)

    # Validation champs obligatoires (avertissements uniquement — ne bloquent pas)
    if not form_fields.get("champs_obligatoires_presents", False):
        manquants = []
        if not form_fields.get("amount", 0) > 0:
            manquants.append("montant")
        if not form_fields.get("date_echeance"):
            manquants.append("date d'échéance")
        if manquants:
            errors.append("Champs obligatoires manquants : {}.".format(", ".join(manquants)))

    champs_remplis = _mapper_frappe(form_fields, _MAPPING_FRAPPE_TRAITE)
    valid = True  # la traite n'est jamais bloquée par des champs manquants

    return {
        "valid":                  valid,
        "document_type_detected": "traite",
        "form_fields":            form_fields,
        "champs_remplis":         champs_remplis,
        "uncertain_fields":       list(set(incertains)),
        "image_enhanced":         False,
        "date_cheque_retenue":    None,
        "confiance":              round(confiance, 3),
        "errors":                 errors,
    }


# ──────────────────────────────────────────────────────────────────────
# HELPER — RÉSULTAT D'ÉCHEC
# ──────────────────────────────────────────────────────────────────────


def _resultat_echec(message: str, errors: list, doc_type: str = "inconnu") -> dict:
    """
    Construit un dict résultat d'échec standardisé avec valid=False.
    Ajoute le message à la liste errors et remet à zéro tous les champs.
    """
    errors.append(message)
    return {
        "valid":                  False,
        "document_type_detected": doc_type,
        "form_fields":            {},
        "champs_remplis":         {},
        "uncertain_fields":       [],
        "image_enhanced":         False,
        "date_cheque_retenue":    None,
        "confiance":              0.0,
        "errors":                 errors,
    }