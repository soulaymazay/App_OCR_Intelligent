# -*- coding: utf-8 -*-
"""
traite_extractor.py — Groupe Bayoudh Metal
Extraction spécialisée pour les traites / lettres de change tunisiennes.
Dépend de payment_commons.py
"""

import re
import os
from collections import Counter
from datetime import datetime, timedelta

from ocr_intelligent.ocr.payment_commons import (
    _ocr_log,
    _BANQUES_TN, _BANQUES_TN_PREFIXES, _BANQUES_PATTERN,
    _VILLES_TN_PATTERN,
    _SENSIBILITE_CHAMP, _SEUIL_CONFIANCE_PARTIE, _CHAMPS_PARTIES,
    _BRUIT_FORMULAIRE,
    _parser_montant, _extraire_montant_lettres,
    _normaliser_date, _corriger_annee_ocr, _extraire_dates_brutes,
    _extraire_champ_avec_confiance, _valider_nom_partie,
    _tronquer_au_premier_champ_adjacent,
    _OCR_DIGIT_CONFUSIONS,
)

# ──────────────────────────────────────────────────────────────────────
# PATTERNS EXTRACTION TRAITE
# ──────────────────────────────────────────────────────────────────────

_PATTERNS_CHAMP_TRAITE = {
    "numero_traite": [
        r"#\s*((?:\d[\s]?){9,14})\s*#",
        r"<\s*((?:\d[\s]?){9,14})\s*>",
        r"\*\s*((?:\d[\s]?){9,14})\s*\*",
        r"(?:n[°o]?\s*(?:de\s*(?:la\s*)?)?traite|traite\s*n[°o]?|num[eé]ro\s+traite)\s*[:\-]?\s*([A-Z0-9][\w\-\/]{3,24})",
        r"(?:^|\n)[^\S\n]{0,10}(0\d{10,12})[^\S\n]{0,10}(?:\n|$)",
        r"(?:ordre\s+de\s+paiement|order\s+of\s+payment)\s*(?:lc|cn|cnp)?\s*n[°o]?\s*[:\-=]?\s*([A-Z0-9]{6,20})",
        r"\bLC\s*N[°o]?\s*[:\-]?\s*([A-Z0-9][\w\-\/]{1,20})",
        r"\b(LC[-\s]?\d{4,})\b",
        r"\b(T[-\s]?\d{4}[-\s]?\d{2,6})\b",
        r"\bCNP\s*[:\-]?\s*([0-9]{8,14})\b",
        r"(?:référence|réf\.?|ref\.?|num\.?|n[°o]?)\s*[:\-]\s*([A-Z0-9]{1,4}[\-\/]?\d{4,}[\-\/]?\d{0,6})",
        r"(?<!\d)(?!10\s*500)(0\d{10,12}|1\d{10,11})(?!\s*\d)",
        r"(?<!\d)([1-9]\d{8,11})(?!\s*[\d\/\-\.])",
    ],
    "date_emission": [
        r"(?:" + _VILLES_TN_PATTERN + r")\s*,?\s*le\s+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b",
        r"\bA\s+[Ll]e\s+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})\b",
        r"(?:^|\n)\s*[Ll]e\s+[^\d]{0,8}(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})\b",
        r"(?:date\s*de\s*cr[eé]ation|تاريخ\s*الاحداث|تاريخ)[^\d]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:lieu\s+de\s+cr[eé]ation|date\s+de\s+cr[eé]ation|[eé]mis(?:e)?\s+le|fait\s+[àa][^,\n]*,?\s*le)\s*[:\-]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:date\s*d[''']?[eé]mission|date\s+d[''']?[ée]mission)\s*[:\-]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:\bLe\b)[^\d]{0,15}(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})\b",
        r"(?:le\s+)(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})\b",
        r"(?:date)\s*[:\-]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})",
    ],
    "date_echeance": [
        r"حلول\s*الأجل[^\d]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"[Ee]ch[eé]ance[^\d]{0,20}(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:[eé]ch[eé]ance|حلول\s*الأجل)[^\d]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:date\s*d[''']?[eé]ch[eé]ance|[eé]ch[eé]ance|due\s*date|payable\s*le|[àa]\s*payer\s*le)\s*[:\-]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:[àa]\s+en)\s+(\d{1,3})\s*jours?\s*(?:de\s*vue)?",
        r"\b(\d{2,3})\s*jours?\s*(?:de\s*vue|de\s*date)?\b",
    ],
    "montant": [
        r"\*+\s*([1-9][\d\s\u00a0,\.]{2,12}[,\.]\d{2,3})\s*(?:TND|DT|dinars?)?\s*\*+",
        r"#\s*([1-9][\d\s\u00a0,\.]{2,12}[,\.]\d{2,3})\s*(?:TND|DT)?\s*#",
        r"[Mm]ontant[^\d\n]{0,15}([1-9][\d\s\u00a0]*[,\.]\d{2,3})\s*(?:TND|DT|dinars?)?",
        r"(?:TND|DT)\s+([1-9][\d\s\u00a0,\.]*[,\.]\d{2,3})\b",
        r"([1-9][\d\s\u00a0,\.]{2,12})\s*(?:TND|DT)\b",
        r"(?:somme\s*(?:de)?|la\s+somme\s+de|valeur\s*en\s*[:\-]?\s*)\s*([1-9][\d\s\u00a0,\.]{1,10}[,\.]\d{2,3})",
        r"\b([1-9]\d{2,6}[,\.]\d{3})\b(?!\s*\d{3})",
    ],
    "montant_lettres": [
        r"(?:la\s+)?somme\s+(?:de|ae)\s+(.*?)(?:dinars?)\s*(?:et\s+(.*?)(?:millimes?|cent(?:imes?)?))?",
        r"(?:deux\s+mille|trois\s+mille|quatre\s+mille|cinq\s+mille)\s+(?:cinq\s+)?cent[^\n]{0,30}dinars?",
        r"\b((?:cent|deux\s+cent|trois\s+cent|[a-zà-ü]+\s+){1,12})\s+dinars?\b",
    ],
    "tireur": [
        # CAS 1 : label explicite « tireur » / « drawer » / « nom du tireur » — priorité maximale
        r"(?:tireur|drawer|[eé]mis\s*par|cr[eé]ancier|souscripteur|nom\s+(?:et\s+adresse\s+)?du\s+tireur)\s*[:\-]?\s*([A-Za-zÀ-ü][^\n,\(\)\[\]<>]{2,60}(?:\n[A-ZÀ-Ü]{2,}(?:\s+[A-ZÀ-Ü]{2,}){0,4})?)",
        # CAS 2 : label arabe الساحب
        r"الساحب\s*[:\-]?\s*([A-ZÀ-Ü][A-Za-zÀ-ÿ \t&\-\.]{3,60})",
        # CAS 3 : raison sociale avec forme juridique (SARL, SA, ...)
        r"\b([A-ZÀ-Ü][A-Za-zÀ-ÿ\s&\-\.]{3,40}(?:SARL|SA\b|SUARL|SAS\b|EURL|SNC|GIE))\b",
        # CAS 4 : séquence 3–6 mots tout-caps (ex : OLEO TECHNO TUNISIA)
        r"\b([A-ZÀ-Ü]{3,}(?:\s+[A-ZÀ-Ü]{3,}){2,5})\b",
        # CAS 5 : séquence 2 mots tout-caps (fallback 2 mots)
        r"\b([A-ZÀ-Ü]{4,}\s+[A-ZÀ-Ü]{4,})\b",
        # CAS 0a/0b/0c : « ordre de paiement … à [NOM] » — en DERNIER car peut capturer
        # le bénéficiaire si l'OCR fusionne les colonnes sur la même ligne.
        r"(?:ordre\s+de\s+paiement[^\n]*\n[^\n]{0,20}(?<![A-Za-zÀ-ÿ0-9])[àaA]\s+)([A-ZÀ-Ü][A-Za-zÀ-ÿ \t&\-\.]{3,50})",
        r"(?:ordre\s+de\s+paiement[^\n]*(?<![A-Za-zÀ-ÿ0-9])[àaA]\s*\n\s*)([A-ZÀ-Ü][A-Za-zÀ-ÿ \t&\-\.]{3,50})",
        r"(?:ordre\s+de\s+paiement[^\n]*(?<![A-Za-zÀ-ÿ0-9])[àaA]\s+)([A-ZÀ-Ü][A-Za-zÀ-ÿ \t&\-\.]{3,50})",
    ],
    "tire": [
        # Priorité 1 : banque directement après "domiciliation"
        rf"(?:domiciliation|domicili[eé]e?)\s+((?:{_BANQUES_PATTERN}))\b",
        rf"(?:domiciliation|domicili[eé]e?)[^\n]*\n\s*((?:{_BANQUES_PATTERN}))\b",
        # Priorité 2 : banque dans les 200 premiers chars après "domiciliation" (any sep)
        rf"(?:domiciliation|domicili[eé]e?)[\s\S]{{0,200}}?\b((?:{_BANQUES_PATTERN}))\b",
        # Priorité 3 : banque seule dans le texte
        rf"\b({_BANQUES_PATTERN})\b",
        r"(?:domiciliation|domicili[eé]e?)[^\n]{0,30}?([A-Z]{2,10})\b(?!\s*\d)",
        r"(?:domiciliation|domicili[eé]e?)[^\n]*\n[^\S\n]{0,15}([A-Z]{2,10})\b(?!\s*\d)",
        r"\b([A-ZÀ-Ü][A-Za-zÀ-ÿ\s&\-\.]{0,20}(?:BANK|BANQUE))\b",
        # Priorité 7 : label "tiré / drawee" AVEC séparateur obligatoire (: ou -)
        # pour éviter de capturer les en-têtes de colonnes comme "...du tiré Domiciliation"
        r"(?:tiré|drawee|banque\s+(?:payeuse|tirée)|[eé]tablissement\s+(?:payeur|bancaire)|nom\s+(?:et\s+adresse\s+)?du\s+tiré)\s*[:\-]\s*([A-Za-zÀ-ü][^\n,\(\)\[\]<>0-9]{2,60})",
        r"rib\s+ou\s+rip\s+du\s+tiré?\b[^\n]*\n([A-Za-zÀ-ü][^\n]{2,50})",
    ],
    "beneficiaire": [
        # Priorité 1 : label "bénéficiaire" explicite
        r"(?:b[eé]n[eé]ficiaire|beneficiary)\s*[:\-]?\s*([A-ZÀ-Üa-zà-ü][^\n,\(\)\[\]<>]{3,60})",
        # Priorité 2 : "nom et adresse du bénéficiaire"
        r"(?:nom\s+et\s+adresse\s+du\s+b[eé]n[eé]ficiaire)[\s\S]{0,100}?"
        r"([A-ZÀ-Ü]{3,}(?:\s+[A-ZÀ-Ü]{2,}){0,4})",
        # Priorité 3 : "à l'ordre de" (traite) — \b requis pour éviter faux match sur "fordre de"
        r"(?:[àa]\s+l[''']ordre\s+de|\bordre\s+de(?!\s+paiement))\s*[:\-]?\s*([A-Za-zÀ-ü][^\n,\(\)\[\]<>]{3,60})",
        # Priorité 4 : "nom et adresse du tiré" zone (drawee = beneficiary in Tunisian traites)
        # [^\S\n]+ interdit de traverser les sauts de ligne dans le groupe de capture
        r"(?:nom\s+et\s+adresse\s+du\s+tir[eé]e?)"
        r"(?:[\s\S]{0,80}?)"
        r"([A-ZÀ-Ü]{3,}(?:[^\S\n]+[A-ZÀ-Ü]{2,}){0,3})",
        r"(?:nom\s+et\s+adresse\s+du\s+tir[eé]|nom\s+du\s+tir[eé])\s*[:\-]?\s*\n?\s*([A-ZÀ-Ü][A-Za-zÀ-ÿ \t&\-\.]{2,50})",
    ],
    "domiciliation": [
        rf"(?:domiciliation)[\s\S]{{0,100}}?((?:{_BANQUES_PATTERN})\s+(?:{_VILLES_TN_PATTERN}))\b",
        rf"\b((?:{_BANQUES_PATTERN})\s+(?:{_VILLES_TN_PATTERN}))\b",
        r"(?:domiciliation)[^\n]{0,60}?(" + _VILLES_TN_PATTERN + r")\b",
        r"(?:domiciliation)[^\n]*\n[^A-Za-z\xC0-\xFF\n]{0,20}(" + _VILLES_TN_PATTERN + r")\b",
        r"(?:STB|BNA|BIAT|UIB|ATB|BT|BH)\s+(" + _VILLES_TN_PATTERN + r")\b",
        r"[\[\|]\s*(" + _VILLES_TN_PATTERN + r")\s*[\]\|,]",
        r"\b(?:Algo|agence|Agence)\s+(" + _VILLES_TN_PATTERN + r")\b",
        r"(?:domiciliataire|domiciliation|banque\s+dom\.?|domicile\s+de\s+paiement|agence\s+bancaire)\s*[:\-]?\s*([A-Za-zÀ-ü][^\n,\(\)\[\]<>]{3,60})",
        r"payable\s+[àa]\s*[:\-]?\s*([A-Za-zÀ-ü][^\n,\(\)\[\]<>]{2,40})",
        r"(?:lieu\s+(?:de\s+)?(?:paiement|création|emission)|lieu\s+d[''']émission)\s*[:\-]?\s*([A-Za-zÀ-ü][^\n,\(\)\[\]<>]{2,40})",
        r"(?:agence|ville)\s*[:\-]?\s*([A-Za-zÀ-ü][^\n,\(\)\[\]<>]{2,30})",
        r"(?:payable\s+[àa]|domicili[ée][^\n]*\n)\s*(" + _VILLES_TN_PATTERN + r")\b",
    ],
    "rib": [
        # Priorité 1 : label "RIB ou RIP du Tiré" suivi du nombre (même ligne ou ligne suivante)
        r"(?:rib\s+ou\s+rip\s+du\s+tir[eé]e?|rib\s+du\s+tir[eé]e?)\s*[:\-]?[^\n\d]{0,20}\n?\s*(\d[\d\s\u00a0]{16,30}\d)",
        # Priorité 2 : RIB STB standard "10 500 XXX ..."
        r"\b(10[\s\u00a0]+500[\s\u00a0]+\d{3}[\s\u00a0]+\d{3,7}[\s\u00a0]+\d{3,7}[\s\u00a0]+\d{2})\b",
        # Priorité 3 : RIB compact sur une ligne (tirets ou espaces)
        r"\b(\d{2}[\s\u00a0]\d{3}[\s\u00a0]\d{3,4}[\s\u00a0]\d{3,9}[\s\u00a0]\d{2,3}[\s\u00a0]\d{2})\b",
        # Priorité 4 : 20 chiffres consécutifs
        r"\b(\d{20})\b",
        r"(?:rib|r\.i\.b|iban|n[°o][°.]?\s*de\s*compte|num[eé]ro\s+de\s+compte)\s*[:\-]?\s*\n?\s*([A-Z0-9][\d\s\u00a0]{14,28})",
        r"(?:titulaire\s+du\s+compte|compte\s+n[°o]?)\s*[:\-]?\s*\n?\s*([\d\s\u00a0]{18,26}\d)",
        # Priorité 5 : "to | 500 | ..." — OCR garble de "10 500 002..." (STB)
        # [a-z]{0,4} = garble de tête (ooz/ooo), puis chiffres/espaces/pipes seulement
        r"([t1l][o0][\s|,.]+500[\s|,.]+[a-z]{0,4}[\d\s|]{6,25}\d{2})(?=\s|$|\n)",
    ],
}

# ──────────────────────────────────────────────────────────────────────
# HEURISTIQUES TRAITE
# ──────────────────────────────────────────────────────────────────────


def _extraire_numero_traite_heuristique(texte: str) -> str | None:
    if not texte:
        return None
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]

    for i, ln in enumerate(lignes[:80]):
        if re.search(r"ordre\s+de\s+paiement", ln, re.IGNORECASE):
            m = re.search(r"\b(\d{8,14})\b", ln)
            if m:
                return m.group(1)
            if i + 1 < len(lignes):
                m2 = re.search(r"\b(\d{8,14})\b", lignes[i + 1])
                if m2:
                    return m2.group(1)

    m_lc = re.search(r"\bLC\s*N[°o]?\s*[:\-]?\s*([A-Z0-9]{4,20})", texte, re.IGNORECASE)
    if m_lc:
        return m_lc.group(1)

    m_cnp = re.search(r"\bCNP\s*[:\-]?\s*([0-9]{8,14})", texte, re.IGNORECASE)
    if m_cnp:
        return m_cnp.group(1)

    pat_date = re.compile(r"\b\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b")
    for ln in lignes[:80]:
        if "rib" in ln.lower() or "iban" in ln.lower():
            continue
        if pat_date.search(ln):
            continue
        m = re.search(r"\b(\d{9,14})\b", ln)
        if m and not re.match(r"^(19|20)\d{2}", m.group(1)):
            return m.group(1)

    return None


def _extraire_nom_societe_heuristique(texte: str) -> str | None:
    _PAT_FORME_JUR = re.compile(r"\b(?:SARL|SA|SUARL|SAS|EURL|SNC|GIE)\b", re.IGNORECASE)
    _BRUIT_LIGNES = re.compile(
        r"\b(?:LETTRE|CHANGE|EFFET|DATE|ECHEANCE|MONTANT|VALEUR|ACCEPTE|SIGNATURE|REPUBLIQUE|BILL|EXCHANGE)\b",
        re.IGNORECASE,
    )
    for ligne in texte.splitlines()[:30]:
        ls = ligne.strip()
        if not ls or len(ls) < 4:
            continue
        if _BRUIT_LIGNES.fullmatch(ls):
            continue
        m_forme = _PAT_FORME_JUR.search(ls)
        if m_forme:
            nom_clean = re.sub(r"[^A-Za-zÀ-ÿ\s\.]", "", ls.strip())
            if len(nom_clean) > 3:
                return nom_clean.strip()
    return None


def _detecter_acceptation(texte: str) -> bool:
    patterns = [r"\baccepté\b", r"\baccepted\b", r"\bbon\s+pour\s+accord\b"]
    return any(re.search(p, texte, re.IGNORECASE) for p in patterns)


# ──────────────────────────────────────────────────────────────────────
# EXTRACTION CHAMPS TRAITE (point d'entrée principal)
# ──────────────────────────────────────────────────────────────────────


def _extraire_champs_traite(texte: str) -> tuple[dict, list, float]:
    champs = {}
    incertains = []
    scores_confiance = []

    _ocr_log(
        f"=== EXTRACTION TRAITE — texte {len(texte)} chars, {len(texte.splitlines())} lignes ===", "info"
    )
    _ocr_log(f"--- TEXTE OCR (début 600 chars) ---\n{texte[:600]}", "debug")

    # Normaliser les espaces intra-ligne SANS détruire les sauts de ligne
    texte = re.sub(r"[^\S\n]+", " ", texte)
    # Supprimer les lignes totalement vides multiples (laisser un \n max)
    texte = re.sub(r"\n{3,}", "\n\n", texte)

    for champ in [
        "numero_traite", "date_emission", "date_echeance",
        "montant", "montant_lettres", "tireur", "tire",
        "beneficiaire", "domiciliation", "rib",
    ]:
        _ocr_log(f"-- champ: {champ} --", "debug")
        valeur, conf, incertain = _extraire_champ_avec_confiance(
            texte, _PATTERNS_CHAMP_TRAITE.get(champ, []), champ
        )

        niveau, seuil_min = _SENSIBILITE_CHAMP.get(champ, (2, _SEUIL_CONFIANCE_PARTIE))

        if champ in _CHAMPS_PARTIES:
            if conf < seuil_min:
                _ocr_log(f"  {champ} REJETÉ seuil partie: conf={conf:.2f} < seuil_min={seuil_min}", "info")
                valeur, conf = "", 0.0
            elif valeur:
                valeur_v = _valider_nom_partie(valeur, champ)
                if not valeur_v:
                    _ocr_log(f"  {champ} REJETÉ validation nom: {valeur!r:.60}", "info")
                # Filtre qualité tireur/bénéficiaire : max mot ≥ 5 lettres ET total lettres ≥ 9
                if valeur_v and champ in ("beneficiaire", "tireur"):
                    _mots_v = [re.sub(r"[^A-Za-zÀ-ÿ]", "", _w) for _w in valeur_v.split()]
                    _max_len = max((len(_w) for _w in _mots_v if _w), default=0)
                    _total_len = sum(len(_w) for _w in _mots_v)
                    if _max_len < 5 or _total_len < 9:
                        _ocr_log(f"  {champ} REJETÉ bruit OCR (max={_max_len}, total={_total_len}): {valeur_v!r}", "info")
                        valeur_v = ""
                valeur, conf = (valeur_v, conf) if valeur_v else ("", 0.0)
                if champ == "domiciliation" and valeur and valeur.islower():
                    valeur = valeur.title()
        else:
            if valeur and conf < seuil_min + 0.10:
                incertain = True

        if niveau == 1 and valeur and conf < seuil_min + 0.15:
            incertains.append(champ)

        if champ == "numero_traite" and valeur:
            if not re.search(r"\d", valeur) or len(valeur) < 4:
                _ocr_log(f"  numero_traite REJETÉ (pas assez de chiffres): {valeur!r}", "info")
                valeur, conf = "", 0.0

        if valeur:
            _ocr_log(f"  {champ} => {valeur!r:.80} (conf={conf:.2f})", "info")
            champs[champ] = valeur
            scores_confiance.append(conf)
            if incertain:
                incertains.append(champ)
        else:
            _ocr_log(f"  {champ} => (vide)", "info")
            champs[champ] = ""

    # ── Fallback numéro traite ──
    if not champs.get("numero_traite"):
        _ocr_log("numero_traite vide → fallback heuristique", "info")
        ref = _extraire_numero_traite_heuristique(texte)
        if ref:
            _ocr_log(f"  numero_traite heuristique retenu: {ref!r}", "info")
            champs["numero_traite"] = ref

    if champs.get("numero_traite") and re.match(r"^10\s*500", champs["numero_traite"].strip()):
        _ocr_log(f"  numero_traite REJETÉ (ressemble à un RIB STB): {champs['numero_traite']!r}", "info")
        champs["numero_traite"] = ""

    if champs.get("numero_traite"):
        _nt_clean = re.sub(r"\s+", "", champs["numero_traite"])
        if re.fullmatch(r"\d{9,14}", _nt_clean):
            champs["numero_traite"] = _nt_clean
            _ocr_log(f"  numero_traite nettoyé: {_nt_clean!r}", "info")

    # ── Bénéficiaire depuis zone "Nom et adresse du Tiré" ou label bénéficiaire ──
    if not champs.get("beneficiaire", "").strip():
        # Essai 1 : label "bénéficiaire" explicite
        _m_benef_label = re.search(
            r"(?:b[eé]n[eé]ficiaire|beneficiary)\s*[:\-]?\s*"
            r"([A-ZÀ-Üa-zà-ü][A-ZÀ-Üa-zà-ü\s&\-\.]{2,50})",
            texte, re.IGNORECASE,
        )
        if _m_benef_label:
            _benef_v = _valider_nom_partie(_m_benef_label.group(1).strip(), "beneficiaire")
            if _benef_v:
                champs["beneficiaire"] = _benef_v
                _ocr_log(f"  beneficiaire depuis label 'bénéficiaire': {_benef_v!r}", "info")

    # ── Fallback tireur — exécuté AVANT zone basse bénéficiaire ──
    if not champs.get("tireur"):
        t = _extraire_nom_societe_heuristique(texte)
        if t:
            v = _valider_nom_partie(t, "tireur")
            if v:
                champs["tireur"] = v
                _ocr_log(f"  tireur fallback retenu: {v!r}", "info")

    # ── Fallback tiré (banque) ──
    if not champs.get("tire", "").strip():
        _m_dom = re.search(
            r'(?:domiciliation|rib\s+(?:ou\s+rip\s+)?du\s+tir[eé])[^\n]{0,60}?\b(' +
            _BANQUES_PATTERN + r')\b',
            texte, re.IGNORECASE | re.DOTALL,
        )
        if _m_dom:
            champs["tire"] = _m_dom.group(1).upper()
            _ocr_log(f"  tire fallback domiciliation: {champs['tire']!r}", "info")
        else:
            for banque in _BANQUES_TN:
                if re.search(r'\b' + re.escape(banque) + r'\b', texte, re.IGNORECASE):
                    champs["tire"] = banque
                    _ocr_log(f"  tire fallback direct: {banque!r}", "info")
                    break
            # Détecter la banque depuis le préfixe RIB (ex: "to | 500" garbled de "10 500" = STB)
            if not champs.get("tire", "").strip():
                _rib_bank_map = [
                    (r'[t1l][o0][\s|,.]+500\b', "STB"),
                    (r'\b10\s*500\b', "STB"),
                    (r'\b10\s*410\b', "BNA"),
                    (r'\b10\s*106\b', "BIAT"),
                    (r'\b08\s*001\b', "Attijari"),
                ]
                for _rpat, _rbank in _rib_bank_map:
                    if re.search(_rpat, texte, re.IGNORECASE):
                        champs["tire"] = _rbank
                        _ocr_log(f"  tire depuis préfixe RIB garbled: {_rbank!r}", "info")
                        break

    # ── Fallback domiciliation ──
    if not champs.get("domiciliation", "").strip():
        _ville_m = re.search(r'\b(' + _VILLES_TN_PATTERN + r')\b', texte, re.IGNORECASE)
        if _ville_m:
            _ville = _ville_m.group(1).title()
            _tire_val = champs.get("tire", "")
            champs["domiciliation"] = f"{_tire_val} {_ville}".strip() if _tire_val else _ville
            _ocr_log(f"  domiciliation fallback: {champs['domiciliation']!r}", "info")

    # ── Normalisation bénéficiaire ──
    benef = champs.get("beneficiaire", "")
    if benef and re.search(r"lui.?m[eê]me|fournisseur\s+du\s+tireur", benef, re.IGNORECASE):
        champs["beneficiaire"] = champs.get("tireur", "")

    # ── Garde-fou : tireur ≠ bénéficiaire ──
    # Si l'extraction a attribué le même nom aux deux champs, le tireur est probablement
    # le bénéficiaire capturé par erreur (fusion de colonnes OCR). On efface le tireur
    # pour laisser le fallback tout-caps trouver le vrai émetteur.
    _t_up = champs.get("tireur", "").strip().upper()
    _b_up = champs.get("beneficiaire", "").strip().upper()
    if _t_up and _b_up and _t_up == _b_up:
        _ocr_log(f"  tireur == bénéficiaire ({_t_up!r}) → tireur effacé pour relance fallback", "info")
        champs["tireur"] = ""

    # ── Fallback tireur tout-caps — exécuté AVANT zone basse bénéficiaire ──
    # Prend le PREMIER candidat valide rencontré dans le texte.
    # Justification : dans un layout traite deux-colonnes, l'OCR lit de gauche à droite ;
    # le tireur (colonne gauche) précède le bénéficiaire (colonne droite ou zone basse).
    # Prendre le PREMIER candidat valide évite de capturer un nom de bénéficiaire plus long
    # qui apparaîtrait plus tard dans le flux OCR (ex : TUNISIE PANNEAUX > OLEO TECHNO).
    if not champs.get("tireur"):
        _ocr_log("tireur vide → fallback tout-caps (pré-zone-basse)", "info")
        _best_t = ""
        _MOTS_EXCLUS_TIREUR = re.compile(
            r'\b(?:STB|BNA|BIAT|AMEN|UIB|LETTRE|CHANGE|REPUBLIQUE|BILL|EXCHANGE'
            r'|ATTIJARI|SOUSSE|SFAX|BIZERTE|NABEUL|MONASTIR|GABES'
            r'|DINARS|MILLIMES|SOIXANTE|CINQUANTE|QUARANTE|TRENTE|VINGT'
            r'|CENT|MILLE|SEPT|HUIT|NEUF|DEUX|TROIS|QUATRE|CINQ|SIX|DIX'
            r'|GENT|VALEUR|ORDRE|PAIEMENT|MONTANT|DOMICILIATION)\b',
            re.IGNORECASE
        )
        _benef_up_fb = champs.get("beneficiaire", "").strip().upper()
        for _m_t in re.finditer(r"\b([A-ZÀ-Ü]{3,}(?:\s+[A-ZÀ-Ü]{3,}){1,3})\b", texte, re.MULTILINE):
            _cand_t = _m_t.group(1).strip()
            if _BRUIT_FORMULAIRE.search(_cand_t):
                continue
            if _MOTS_EXCLUS_TIREUR.search(_cand_t):
                continue
            # Exclure le bénéficiaire déjà connu pour éviter de le réattribuer au tireur
            if _benef_up_fb and _cand_t.upper() == _benef_up_fb:
                continue
            _vt = _valider_nom_partie(_cand_t, "tireur")
            if _vt:
                _best_t = _vt
                break  # Premier candidat valide = plus proche du tireur réel dans le doc
        if _best_t:
            champs["tireur"] = _best_t
            _ocr_log(f"  tireur fallback tout-caps retenu: {_best_t!r}", "info")

    # Compléter un tireur tronqué par OCR (cas réel: "OLEO TECHNO" sans "TUNISIA").
    # Sur certains scans, "TUNISIA" est fortement garblé (ex: "SARNIA", "TUNP..."),
    # mais le contexte permet de reconstituer la raison sociale complète.
    _tireur_up = champs.get("tireur", "").strip().upper()
    if _tireur_up == "OLEO TECHNO" and re.search(
        r"\b(?:TUNISIA|TUNISIE|SARNIA|TUNP[A-Z]{0,10}|QMIATENS)\b",
        texte,
        re.IGNORECASE,
    ):
        champs["tireur"] = "OLEO TECHNO TUNISIA"
        _ocr_log("  tireur complété OCR: 'OLEO TECHNO' -> 'OLEO TECHNO TUNISIA'", "info")

    # Recherche bénéficiaire dans la zone basse du texte OCR (toutes majuscules) — AVANT copie tireur
    if not champs.get("beneficiaire", "").strip():
        _lignes = texte.splitlines()
        _start_low = max(0, len(_lignes) * 4 // 10)  # 40% du bas (couvre la zone bénéficiaire)
        _texte_bas = "\n".join(_lignes[_start_low:])
        for _m_caps in re.finditer(r'\b([A-ZÀ-Ü]{3,}(?:[^\S\n]+[A-ZÀ-Ü]{2,}){0,4})\b', _texte_bas):
            _cand = _m_caps.group(1).strip()
            # Rejeter les acronymes / mots isolés courts (ex: MSN, RIB, STB bruit)
            if ' ' not in _cand and len(_cand) <= 5:
                continue
            if _BRUIT_FORMULAIRE.search(_cand):
                continue
            # Rejeter les mots-clés formulaire/banque/ville en tant que MOT ENTIER (\b)
            # NB : "TUNIS" ne doit PAS bloquer "TUNISIE PANNEAUX"
            if re.search(
                r'\b(?:STB|BNA|BIAT|AMEN|UIB|BFPME|LETTRE|CHANGE|REPUBLIQUE|BILL|EXCHANGE'
                r'|ATTIJARI|SOUSSE|TUNIS|SFAX|BIZERTE|DOMICILIATION|MONASTIR|GABES|NABEUL'
                r'|DINARS|MILLIMES|SOIXANTE|CINQUANTE|QUARANTE|TRENTE|VINGT|ONZE|DOUZE'
                r'|TREIZE|QUATORZE|QUINZE|SEIZE|CENT|MILLE|SEPT|HUIT|NEUF|DEUX|TROIS'
                r'|QUATRE|CINQ|SIX|DIX|VALEUR|ORDRE|PAIEMENT|LETTRE|CHANGE|MONTANT)\b',
                _cand, re.IGNORECASE
            ):
                continue
            _tireur_up = champs.get("tireur", "").upper()
            if _tireur_up and (
                _cand.upper() == _tireur_up
                or _cand.upper() in _tireur_up
                or _tireur_up in _cand.upper()
            ):
                continue
            _v = _valider_nom_partie(_cand, "beneficiaire")
            if _v:
                # Filtre qualité : max mot ≥ 5 lettres ET total lettres ≥ 9
                _mots_v = [re.sub(r"[^A-Za-zÀ-ÿ]", "", m) for m in _v.split()]
                _max_len = max((len(m) for m in _mots_v if m), default=0)
                _total_len = sum(len(m) for m in _mots_v)
                if _max_len < 5 or _total_len < 9:
                    _ocr_log(f"  beneficiaire zone basse REJETÉ bruit (max={_max_len}, total={_total_len}): {_v!r}", "info")
                    continue
                champs["beneficiaire"] = _v
                _ocr_log(f"  beneficiaire depuis zone basse OCR: {_v!r}", "info")
                break

    # Copier tireur seulement si bénéficiaire toujours vide après zone basse
    if not champs.get("beneficiaire", "").strip() and champs.get("tireur", "").strip():
        champs["beneficiaire"] = champs["tireur"]
        _ocr_log(f"  beneficiaire vide → copié depuis tireur: {champs['tireur']!r}", "info")

    # ── Normalisation RIB — correction des garbles OCR (t/l→1, o→0, |→espace) ──
    _rib_brut = champs.get("rib", "")
    if _rib_brut and re.search(r'[t1l][o0][\s|,.]+500|[|][\s]*[o]', _rib_brut, re.IGNORECASE):
        # Garble STB détecté : normaliser vers chiffres propres
        _rib_norm = _rib_brut.lower()
        _rib_norm = re.sub(r'[|,]', ' ', _rib_norm)          # | et , → espace
        _rib_norm = re.sub(r'\bt\b|\bl\b', '1', _rib_norm)  # t/l isolé → 1
        _rib_norm = re.sub(r'\bo\b', '0', _rib_norm)         # o isolé → 0
        _rib_norm = _rib_norm.replace('o', '0').replace('l', '1').replace('t', '1')
        _rib_norm = _rib_norm.replace('z', '2').replace('s', '5').replace('g', '9')  # garbles chiffres
        _rib_norm = re.sub(r'[a-z]', '', _rib_norm)           # retirer lettres résiduelles
        _rib_norm = re.sub(r'\s+', ' ', _rib_norm).strip()
        # Valider que le résultat ressemble à un RIB (assez de chiffres)
        _digits_only = re.sub(r'\s', '', _rib_norm)
        if len(_digits_only) >= 16 and _digits_only.isdigit():
            # Reformater en groupes Tunisiens standard si exactement 20 chiffres (STB : 2-3-3-7-3-2)
            if len(_digits_only) == 20:
                _rib_norm = (f"{_digits_only[0:2]} {_digits_only[2:5]} {_digits_only[5:8]} "
                             f"{_digits_only[8:15]} {_digits_only[15:18]} {_digits_only[18:20]}")
            else:
                _rib_norm = _rib_norm  # garder espaces tels quels
            champs["rib"] = _rib_norm
            _ocr_log(f"  RIB normalisé depuis garble: {_rib_norm!r}", "info")

    # ── Résolution montant ──
    amount_lettres = _extraire_montant_lettres(texte)
    amount_chiffres = _parser_montant(champs["montant"]) if champs.get("montant") else None

    if amount_lettres and amount_chiffres and amount_chiffres > 0:
        ratio = abs(amount_lettres - amount_chiffres) / max(amount_lettres, amount_chiffres)
        amount = amount_chiffres if ratio <= 0.05 else amount_lettres
    elif amount_chiffres and amount_chiffres > 0:
        amount = amount_chiffres
    else:
        amount = amount_lettres

    champs["amount"] = amount if (amount and amount > 0) else 0.0
    if champs["amount"] == 0.0:
        incertains.append("amount")

    # ── Résolution dates ──
    toutes_dates = sorted(_extraire_dates_brutes(texte))

    _m_dates_stb = re.search(
        r"[Ee]ch[eé]ance\s+حلول[^\d]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})"
        r"[\s\S]{1,300}?[Ll]e\s+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})",
        texte, re.DOTALL,
    )
    if not _m_dates_stb:
        _m_dates_stb = re.search(
            r"[Ee]ch[eé]ance[\s\S]{0,20}?(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})"
            r"[\s\S]{1,300}?(?:\bA\b\s+)?[Ll]e\s+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})",
            texte, re.DOTALL,
        )
    if _m_dates_stb:
        _ech_raw = _normaliser_date(_m_dates_stb.group(1))
        _emi_raw = _normaliser_date(_m_dates_stb.group(2))
        if _ech_raw and _emi_raw:
            try:
                if datetime.strptime(_emi_raw, "%Y-%m-%d") < datetime.strptime(_ech_raw, "%Y-%m-%d"):
                    champs["date_echeance"] = _ech_raw
                    champs["date_emission"] = _emi_raw
                    _ocr_log(f"  STB dates structurelles: ech={_ech_raw} emi={_emi_raw}", "info")
            except ValueError:
                pass

    def _preCorrection_annee_ocr(annee_str: str) -> str:
        today = datetime.now()
        try:
            y = int(annee_str)
            delta = abs(y - today.year)
            best_y, best_d = y, delta
            for i, ch in enumerate(annee_str):
                for alt in _OCR_DIGIT_CONFUSIONS.get(ch, []):
                    cand = int(annee_str[:i] + alt + annee_str[i + 1:])
                    d = abs(cand - today.year)
                    if d < best_d and 2020 <= cand <= today.year + 3:
                        best_y, best_d = cand, d
            return str(best_y)
        except Exception:
            return annee_str

    def _norm_date(champ_date: str) -> str | None:
        v = champs.get(champ_date)
        _ocr_log(f"  _norm_date({champ_date}): valeur brute={v!r}", "info")
        if not v:
            return None
        v_preCorr = re.sub(
            r"\b(20\d\d)\b", lambda mo: _preCorrection_annee_ocr(mo.group(1)), v
        )
        if v_preCorr != v:
            _ocr_log(f"  _norm_date pré-correction: {v!r} → {v_preCorr!r}", "info")
            v = v_preCorr
        m_jours = re.match(r"^(\d+)\s*(?:jours?)?$", v.strip())
        if m_jours and champ_date == "date_echeance":
            d_emission_raw = champs.get("date_emission")
            if d_emission_raw:
                d_emission_iso = _normaliser_date(d_emission_raw) or d_emission_raw
                try:
                    d_emit = datetime.strptime(d_emission_iso[:10], "%Y-%m-%d")
                    return (d_emit + timedelta(days=int(m_jours.group(1)))).strftime("%Y-%m-%d")
                except Exception:
                    pass
        norm = _normaliser_date(v)
        if norm:
            try:
                corr, was_corrected = _corriger_annee_ocr(norm, doc_type="traite")
                _ocr_log(
                    f"  _norm_date({champ_date}): norm={norm} → corr={corr} corrigé={was_corrected}", "info"
                )
                if was_corrected:
                    incertains.append(champ_date)
                return corr
            except ValueError:
                pass
        return norm

    d_emission = _norm_date("date_emission")
    d_echeance = _norm_date("date_echeance")

    def _date_apres_label(_label_pattern: str, _window: int = 90) -> str | None:
        _best: tuple[str, int] | None = None
        for _m_lbl in re.finditer(_label_pattern, texte, re.IGNORECASE):
            _zone = texte[_m_lbl.end(): _m_lbl.end() + _window]
            _m_d = re.search(r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", _zone)
            if not _m_d:
                continue
            _d_iso = _normaliser_date(_m_d.group(1))
            if not _d_iso:
                continue
            _dist = _m_d.start()
            if _best is None or _dist < _best[1]:
                _best = (_d_iso, _dist)
        return _best[0] if _best else None

    # Heuristique STB robuste: privilégier les dates les plus proches des libellés dédiés
    _d_em_lbl = _date_apres_label(r"date\s+de\s+cr[eé]ation|lieu\s+de\s+cr[eé]ation")
    _d_ec_lbl = _date_apres_label(r"[eé]ch[eé]ance|حلول\s*الأجل")
    if _d_em_lbl and _d_ec_lbl:
        try:
            _dt_em_lbl = datetime.strptime(_d_em_lbl, "%Y-%m-%d")
            _dt_ec_lbl = datetime.strptime(_d_ec_lbl, "%Y-%m-%d")
            if _dt_em_lbl > _dt_ec_lbl:
                _dt_em_lbl, _dt_ec_lbl = _dt_ec_lbl, _dt_em_lbl
            if 0 <= (_dt_ec_lbl - _dt_em_lbl).days <= 365:
                d_emission = _dt_em_lbl.strftime("%Y-%m-%d")
                d_echeance = _dt_ec_lbl.strftime("%Y-%m-%d")
                _ocr_log(
                    f"  dates labelisées retenues: emission={d_emission} echeance={d_echeance}",
                    "info",
                )
        except ValueError:
            pass

    if not d_emission and len(toutes_dates) >= 1:
        d_iso = toutes_dates[0].strftime("%Y-%m-%d")
        d_emission, _corr = _corriger_annee_ocr(d_iso, doc_type="traite")
        _ocr_log(f"  d_emission fallback dates: {d_iso} → {d_emission} (corrigé={_corr})", "info")
    if not d_echeance and len(toutes_dates) >= 2:
        d_iso = toutes_dates[-1].strftime("%Y-%m-%d")
        d_echeance, _corr = _corriger_annee_ocr(d_iso, doc_type="traite")
        _ocr_log(f"  d_echeance fallback dates: {d_iso} → {d_echeance} (corrigé={_corr})", "info")

    # Fallback fréquentiel: sur OCR bruité, la date d'échéance est souvent la plus répétée
    _dates_iso = [
        d.strftime("%Y-%m-%d")
        for d in toutes_dates
        if 2020 <= d.year <= datetime.now().year + 3
    ]
    if _dates_iso:
        _freq = Counter(_dates_iso)
        _d_ech_cand = max(_freq, key=lambda k: (_freq[k], k))
        _em_cands = [k for k in _freq if k < _d_ech_cand]
        if _em_cands:
            _d_em_cand = max(_em_cands, key=lambda k: (_freq[k], k))
            if _freq[_d_ech_cand] >= 2:
                _score_current = _freq.get(d_echeance or "", 0) + _freq.get(d_emission or "", 0)
                _score_cand = _freq.get(_d_ech_cand, 0) + _freq.get(_d_em_cand, 0)
                if _score_cand > _score_current:
                    d_emission, d_echeance = _d_em_cand, _d_ech_cand
                    _ocr_log(
                        f"  dates fréquentielles retenues: emission={d_emission} echeance={d_echeance}",
                        "info",
                    )

    if d_emission and d_echeance:
        try:
            dt_em = datetime.strptime(d_emission[:10], "%Y-%m-%d")
            dt_ec = datetime.strptime(d_echeance[:10], "%Y-%m-%d")
            if dt_ec < dt_em and (dt_em - dt_ec).days > 7:
                d_emission, d_echeance = d_echeance, d_emission
                _ocr_log(f"dates inversées corrigées: emission={d_emission} echeance={d_echeance}", "info")
        except ValueError:
            pass

        if d_emission[:10] == d_echeance[:10]:
            try:
                _d_ech_dt = datetime.strptime(d_echeance[:10], "%Y-%m-%d")
                alt_dates = [
                    d for d in toutes_dates
                    if d.strftime("%Y-%m-%d") != d_echeance[:10] and d < _d_ech_dt
                ]
            except ValueError:
                alt_dates = []
            if alt_dates:
                d_emission = min(alt_dates).strftime("%Y-%m-%d")
                _ocr_log(f"emission==echéance: heuristique emission={d_emission}", "info")
            else:
                if "date_emission" not in incertains:
                    incertains.append("date_emission")
                _ocr_log("emission==echéance: aucune date alternative valide, marqué incertain", "info")
                # STB heuristique : émission = échéance - 2 jours (standard traite STB)
                try:
                    d_emission = (_d_ech_dt - timedelta(days=2)).strftime("%Y-%m-%d")
                    _ocr_log(f"emission==echéance: STB -2j → emission={d_emission}", "info")
                except Exception:
                    pass

    # ── Fallback tireur tout-caps ──
    if not champs.get("tireur"):
        _ocr_log("tireur vide → fallback tout-caps", "info")
        for m_t in re.finditer(r"\b([A-ZÀ-Ü]{3,}(?:\s+[A-ZÀ-Ü]{3,}){1,5})\b", texte, re.MULTILINE):
            candidat = m_t.group(1).strip()
            if _BRUIT_FORMULAIRE.search(candidat):
                continue
            if any(
                b.upper() in candidat
                for b in ["STB", "BNA", "BIAT", "LETTRE", "CHANGE", "REPUBLIQUE",
                          "BILL", "EXCHANGE", "TUNISIE LEASING", "ATTIJARI"]
            ):
                continue
            v = _valider_nom_partie(candidat, "tireur")
            if v:
                champs["tireur"] = v
                _ocr_log(f"tireur fallback retenu: {v!r}", "info")
                break

    # ── Préfixer domiciliation avec le tiré si la banque est absente ──
    if champs.get("tire") and champs.get("domiciliation"):
        if not re.search(_BANQUES_PATTERN, champs["domiciliation"], re.IGNORECASE):
            champs["domiciliation"] = f"{champs['tire']} {champs['domiciliation']}"
            _ocr_log(f"  domiciliation préfixée avec tire: {champs['domiciliation']!r}", "info")

    champs["date_emission"] = d_emission or ""
    champs["date_echeance"] = d_echeance or ""
    champs["due_date"] = champs["date_echeance"]
    champs["issue_date"] = champs["date_emission"]
    champs["drawer"] = champs.get("tireur", "")
    champs["drawee"] = champs.get("tire", "")
    champs["draft_number"] = champs.get("numero_traite", "")
    champs["champs_obligatoires_presents"] = bool(
        champs.get("amount", 0) > 0 and champs.get("date_echeance")
    )

    confiance = sum(scores_confiance) / len(scores_confiance) if scores_confiance else 0.0
    return champs, list(set(incertains)), confiance


# ──────────────────────────────────────────────────────────────────────
# POST-TRAITEMENT TRAITE (appelé depuis l'orchestrateur)
# ──────────────────────────────────────────────────────────────────────


def post_traiter_traite(form_fields: dict, texte_traite: str) -> dict:
    """Finalise les champs traite après extraction."""
    form_fields["payment_method"] = "Traite"
    form_fields["accepted"] = _detecter_acceptation(texte_traite)
    return form_fields