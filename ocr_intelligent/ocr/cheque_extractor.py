# -*- coding: utf-8 -*-
"""
cheque_extractor.py — Groupe Bayoudh Metal
Extraction spécialisée pour les chèques tunisiens.
Dépend de payment_commons.py
"""

import re
import os
from datetime import datetime

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
    _fuzzy_match_frappe_parties,
    _ameliorer_image_floue, _pretraiter_texte_ocr,
)

# ──────────────────────────────────────────────────────────────────────
# PATTERNS EXTRACTION CHÈQUE
# ──────────────────────────────────────────────────────────────────────

_PATTERNS_CHAMP_CHEQUE = {
    "numero_cheque": [
        r"[#9]\s*([0-9]{5,10})\s*#",
        r"#\s*([0-9]{5,10})\s*[#9]",
        r"(?:n[°o]?\s*(?:du\s*)?ch[eèé]que|ch[eèé]que\s*n[°o]?)\s*[:\-]?\s*([0-9]{4,12})",
        r"(?:num[eé]ro|num\.?)\s*[:\-]?\s*([0-9]{5,12})",
        r"\b([0-9]{6,10})\b",
    ],
        # APRÈS
    "date_cheque": [
    # Préfixes classiques : ville + "le", ou "date :", ou "le "
       r"(?:(?:" + _VILLES_TN_PATTERN + r")\s*,?\s*le\s+|(?:date(?:\s+d['\u2019]?(?:[eé]mission|[eé]ch[eé]ance))?|le)\s*[:\-]?\s*)"
       r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",

    # Date seule DD/MM/YYYY sur sa propre zone (top-right du chèque)
       r"(?<!\d)(\d{1,2}\s*[\/\-\.]\s*\d{1,2}\s*[\/\-\.]\s*\d{4})(?!\d)",

    # Date en lettres
       r"(\d{1,2}\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|"
       r"septembre|octobre|novembre|d[ée]cembre)\s+\d{4})",

    # Format arabe inversé YYYY/MM/DD ou YYYY-MM-DD
       r"(?<!\d)(20\d{2}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})(?!\d)",
],
      
    "montant_chiffres": [
        r"(?:[A-Za-z]{0,4}\s*)?#\s*([1-9][\d,\.\s\u00a0]{3,14})\s*#",
        r"[A-Za-z]?#\s*([1-9][\d,\.]{3,12})\s*#",
        r"\*+\s*([\d\s\u00a0]+[,\.]\d{2,3})\s*(?:TND|DT|EUR?|€|dinars?)?\s*\*+",
        r"(?:TND|DT|EUR?|€)\s+([\d][\d\s\u00a0,\.]*[,\.]\d{2,3})\b",
        r"\*+\s*([\d\s\u00a0]+[,\.]\d{2,3})\s*(?:TND|DT|EUR?|€|dinars?)?",
        r"(?:la\s*)?(?:montant|somme\s*(?:de)?)\s*[:\-]?\s*([\d\s\u00a0]+[,\.]\d{2,3})\s*(?:TND|DT|EUR?|€|dinars?)?",
        r"(?:la\s*)?(?:montant|somme\s*(?:de)?)\s*[:\-]?\s*([1-9]\d{2,7})\s*(?:TND|DT|EUR?|€|dinars?)\b",
        r"([\d\s\u00a0]{3,}[,\.]\d{2,3})\s*(?:TND|DT|EUR?|€)",
        r"([1-9]\d{2,8}(?:[\s\u00a0]\d{3}){0,2})\s*(?:TND|DT|EUR?|€|dinars?)\b",
        r"(?<![A-Za-zÀ-ÿ])[a£*#]\s+([1-9][\d,\.]{3,9})",
    ],
    "montant_lettres": [
        r"(?:la\s+)?somme\s+(?:de|ae)\s+(.*?)(?:dinars?)\s*(?:et\s+(.*?)(?:millimes?|cent(?:imes?)?))?",
        r"(?:montant\s+(?:en\s+lettres?\s*)?[:\-]?\s*)(.*?)(?:dinars?)",
    ],
    "banque": [
        rf"\b({_BANQUES_PATTERN})\b",
        r"\b([A-ZÀ-Ü][A-Za-zÀ-ÿ\s&\-\.]{1,30}(?:BANK|BANQUE))\b",
        r"(?:banque|bank|tiré\s+sur|établissement)\s*[:\-]?\s*([A-Za-zÀ-ü][^\n]{2,50})",
    ],
    "rib": [
        r"\b(\d{2}\s+\d{3}\s+\d{3}\s+\d{7}\s+\d{3}\s+\d{2})\b",
        r"\b(\d{2}\s*\d{3}\s*\d{4}\s*\d{9}\s*\d{2})\b",
        r"\b(\d{2}[\s\-]?\d{3}[\s\-]?\d{3,4}[\s\-]?\d{6,9}[\s\-]?\d{2,3}[\s\-]?\d{2})\b",
        r"\b(TN\d{2}(?:[^\S\n]?\d{4}){5})\b",
        r"\b([A-Z]{2}\d{2}(?:[^\S\n]?\d{4}){4,5})\b",
        r"(?:rib|iban|n[°o][°.]?\s*de\s*compte|compte)\s*[:\-]?\s*\n?\s*([A-Z0-9][\d\s]{14,28})",
        r"(?:titulaire\s+du\s+compte|compte\s+n[°o]?)\s*[:\-]?\s*\n?\s*([\d\s]{18,25})",
    ],
    "beneficiaire": [
        # NOUVEAU — priorité 1 : majuscules seules après "à l'ordre de"
       r"(?:[àa]\s*l[''']?\s*ordre\s+de\s*[-_\.\s]{0,20}\n?\s*)"
       r"([A-ZÀ-Ü]{3,}(?:\s+[A-ZÀ-Ü]{2,}){0,3})",

    # NOUVEAU — priorité 2 : mot(s) tout-majuscules seul(s) sur leur ligne
        r"(?:ordre\s+de[^\n]{0,25}\n\s*)([A-Z]{4,}(?:\s+[A-Z]{3,}){0,2})\s*\n",
          # NOUVEAU — priorité haute : ligne seule après "à l'ordre de"
        r"(?:[àa]\s*l[''']ordre\s+de\s*[-_\.]{0,30}\s*\n?\s*)"
        r"([A-ZÀ-Ü][A-ZÀ-Üa-zà-ü0-9][A-ZÀ-Üa-zà-ü0-9 &\.\-]{1,40})",
    
    # NOUVEAU — mot en majuscules seul sur sa ligne (typique cursif scanné)
        r"(?:ordre\s+de[^\n]{0,20}\n\s*)([A-Z]{4,}(?:\s+[A-Z]{2,}){0,3})",
        r"(?:nom\s+et\s+adresse\s+du\s+tir[eé]|nom\s+du\s+tir[eé])\s*[:\-]?\s*\n?\s*([A-ZÀ-Ü][A-Za-zÀ-ÿ ]+(?:[A-ZÀ-Ü][A-Za-zÀ-ÿ ]*){0,3})",
        r"(?:nom\s+et\s+adresse\s+du\s+tir[eé])[^\n]*(?:\n[^\n]{0,60}){0,3}\n?\s*([A-ZÀ-Ü]{3,}(?:\s+[A-ZÀ-Ü]{2,}){0,4})",
        r"payez\s+contre\s+(?:ce\s+)?ch[eèé]que[ \t]*\n?[ \t]*(?![àa](?:\s|l[''']))((?:Soci[eé]t[eé]|SARL|SUARL|SA\b|[A-ZÀ-Ü][A-Za-zÀ-ÿ])[^\n]{0,48})",
        r"payez\s+contre\s+(?:ce\s+)?ch[eèé]que[^\n]{0,5}[àaA]\s*:?\s*[^A-Za-zÀ-ÿ\n]{0,30}?((?:SARL|SUARL|SA\b|Soci[eé]t[eé]|[A-ZÀ-Ü][A-Za-zÀ-ÿ])[A-Za-zÀ-ÿ \t&\.\-]{1,50})",
        r"payez\s+contre\s+(?:ce\s+)?ch[eèé]que[^\n]*\n[^A-Za-zÀ-ÿ\n]{0,20}(?![àa](?:\s|l[''']))((?:Soci[eé]t[eé]\s+)?[A-ZÀ-Ü][A-Za-zÀ-ÿ][A-Za-zÀ-ÿ \t&\.\-]{0,48})",
        r"(?:[àa]\s+l[''']?\s*ordre\s+de|ordre\s+de)[^\S\n]*(?:[^\S\n]*\n[^\S\n]*)?([A-ZÀ-Üa-zà-ü][A-Za-zÀ-ÿ][^\n]{0,33})",
        r"payez[^\n]*?ch[eèé]que[ \t]*\n?[ \t]*(?![àa](?:\s|l[''']))([A-ZÀ-Ü][A-Za-zÀ-ÿ][A-Za-zÀ-ÿ \t&\.\-]{1,50})",
    ],
    "titulaire_compte": [
        r"(?m)^([A-ZÀ-Ü][A-Za-zÀ-ÿ][^\n]{2,58})\s*\n\s*\d+[,\s]+[A-Za-z]",
        r"(?m)^A\s*$\n\s*([A-ZÀ-Ü][A-Za-zÀ-ÿ][^\n]{2,58})",
        r"(?m)^A\s+([A-ZÀ-Ü][A-Za-zÀ-ÿ][^\n]{2,58})",
        r"(?:titulaire\s+(?:du\s+)?compte|titulaire)\s*[:\-]\s*([A-Za-zÀ-ü][^\n]{3,60})",
        r"(?:\d{2}[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{3,9}[\s\-]?\d{2,3}[\s\-]?\d{0,3}(?:\s*TND)?[^\n]*\n)[^A-Za-zÀ-ÿ\n]{0,10}([A-ZÀ-Ü][A-ZÀ-Üa-zà-ü][A-ZÀ-Üa-zà-ü \t&\-\.]{2,58})",
        r"(?:compte|agence)\s*[:\-]?[^\n]*\n[^A-Za-zÀ-ÿ\n]{0,10}([A-ZÀ-Ü][A-Za-zÀ-ÿ][A-Za-zÀ-ÿ \t&\-\.]{2,50})",
        r"(?m)^[^A-Za-zÀ-ÿ\n]{0,10}([A-ZÀ-Ü]{2}[A-ZÀ-Ü \t&\-\.]{3,50})$",
    ],
    "memo": [
        r"(?:objet|memo|motif|pour|réf\.?|ref\.?)\s*[:\-]?\s*([^\n]{3,80})",
    ],
}


def _date_provient_expiration(texte: str, date_value: str) -> bool:
    """
    Détermine si une date extraite provient d'un contexte d'expiration/validité
    plutôt que de la date réelle du chèque.
    Retourne True si TOUTES les lignes contenant cette date mentionnent 'expir' ou 'validité'.
    """
    if not texte or not date_value:
        return False
    lignes_avec_date = [
        ligne for ligne in texte.splitlines()
        if date_value in ligne
    ]
    if not lignes_avec_date:
        return False
    return all(re.search(r"expir|validit[eé]|echean|échéan", ligne, re.IGNORECASE) for ligne in lignes_avec_date)


# ──────────────────────────────────────────────────────────────────────
# DÉTECTION SIGNATURE
# ──────────────────────────────────────────────────────────────────────


def _trouver_zone_cheque(img):
    """
    Détecte par contours la zone principale du chèque dans l'image.
    Retourne le bounding-rect (x, y, w, h) de la zone la plus grande couvrant
    au moins 20% de la surface totale, ou None si non trouvée.
    """
    import cv2
    import numpy as np
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    ih, iw = img.shape[:2]
    candidates = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) > iw * ih * 0.20]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r[2] * r[3])


def _detecter_signature(chemin_img: str, texte: str) -> bool:
    """
    Détecte la présence d'une signature sur l'image d'un chèque via analyse de contours.
    Accepte images raster et PDF (converti en 200 DPI).
    Retourne True si des contours compatibles avec une signature sont détectés.
    """
    try:
        import cv2
        import numpy as np

        ext = os.path.splitext(chemin_img)[1].lower()
        if ext == ".pdf":
            from pdf2image import convert_from_path
            pages = convert_from_path(chemin_img, dpi=200)
            if not pages:
                return False
            img = cv2.cvtColor(np.array(pages[0].convert("RGB")), cv2.COLOR_RGB2BGR)
        else:
            img = cv2.imread(chemin_img)
            if img is None:
                from PIL import Image as PILImage
                pil = PILImage.open(chemin_img).convert("RGB")
                img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

        h, w = img.shape[:2]
        box = _trouver_zone_cheque(img)
        cx, cy, cw, ch = box if box else (0, 0, w, h)

        y1 = cy + int(ch * 0.68)
        y2 = cy + int(ch * 0.92)
        x1 = cx + int(cw * 0.52)
        x2 = cx + cw
        zone = img[y1:y2, x1:x2]
        if zone is None or zone.size == 0:
            return False

        zh, zw = zone.shape[:2]
        gray_z = cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray_z, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, zw // 10), 1))
        lignes_h = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
        thresh = cv2.subtract(thresh, lignes_h)

        max_blob_area = zh * zw * 0.15
        n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(thresh, connectivity=8)
        nb_blobs_valides = 0

        for i in range(1, n_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 200 or area > max_blob_area:
                continue
            blob_h = stats[i, cv2.CC_STAT_HEIGHT]
            if blob_h < 12:
                continue
            nb_blobs_valides += 1
            mask = (labels == i).astype(np.uint8) * 255
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                continue
            biggest = max(cnts, key=cv2.contourArea)
            hull = cv2.convexHull(biggest)
            hull_area = cv2.contourArea(hull)
            if hull_area < 1:
                continue
            if area / hull_area < 0.65:
                return True

        return nb_blobs_valides >= 3

    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────
# PRÉTRAITEMENT ZONE BÉNÉFICIAIRE CURSIF
# ──────────────────────────────────────────────────────────────────────


def _pretraiter_zone_beneficiaire_cursif(crop) -> list:
    import cv2
    import numpy as np

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop.copy()
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
    gray_enh = clahe.apply(gray)
    _, binary = cv2.threshold(gray_enh, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    k_h_small = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 2))
    dilated_small = cv2.dilate(binary, k_h_small, iterations=1)
    eroded_small = cv2.erode(dilated_small, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1)), iterations=1)

    k_h_large = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 2))
    dilated_large = cv2.dilate(binary, k_h_large, iterations=1)
    eroded_large = cv2.erode(dilated_large, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1)), iterations=1)

    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (20, 8))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k_close)

    return [
        cv2.bitwise_not(eroded_small),
        cv2.bitwise_not(eroded_large),
        cv2.bitwise_not(closed),
        gray_enh,
    ]


# ──────────────────────────────────────────────────────────────────────
# EXTRACTION BÉNÉFICIAIRE MANUSCRIT
# ──────────────────────────────────────────────────────────────────────


def _extraire_beneficiaire_manuscrit(chemin_img: str) -> str | None:
    """
    Extrait le bénéficiaire manuscrit cursif d'un chèque.

    Stratégie :
      1. Zones ultra-serrées (20-40% hauteur) → Tesseract PSM 8/13 + whitelist
      2. Masque encre bleue (triple plage HSV) + binarisations multiples
      3. Fuzzy-match sur le dictionnaire des parties connues (frappe_parties)
      4. Sélection par score cohérence (mot le plus long > fragmentation)
    Retourne None si aucun candidat valide trouvé.
    """
    try:
        import cv2
        import numpy as np
        import pytesseract
        from PIL import Image as PILImage

        ext = os.path.splitext(chemin_img)[1].lower()
        if ext == ".pdf":
            from pdf2image import convert_from_path
            pages = convert_from_path(chemin_img, dpi=400)
            if not pages:
                return None
            img = cv2.cvtColor(np.array(pages[0].convert("RGB")), cv2.COLOR_RGB2BGR)
        else:
            img = cv2.imread(chemin_img)
            if img is None:
                pil = PILImage.open(chemin_img).convert("RGB")
                img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

        h, w = img.shape[:2]

        # ── Zones resserrées sur la ligne "À l'ordre de" ──
        zones_benef = [
            (0.20, 0.33, 0.85, 0.43), 
            (0.05, 0.30, 0.88, 0.44),   # zone principale tight
            (0.05, 0.27, 0.88, 0.48),   # fallback légèrement plus large
            (0.10, 0.25, 0.85, 0.52),   # fallback large
        ]
        candidats = []
        tokens_forts = []

        # ── Whitelist élargie ──
        _WL = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "abcdefghijklmnopqrstuvwxyz"
            "ÀÂÇÉÈÊËÎÏÔÙÛÜàâçéèêëîïôùûü-. "
        )

        # ── Bruit connu à rejeter ──
        _BRUIT_BENEF_PATTERNS = re.compile(
            r"\b(?:eed|aeste|sag|estlank|blipote|gee|wee|ons|rae|ase"
            r"|payez|contre|ordre|profit|banque|organisme|assimile"
            r"|endossable|sauf|non)\b",
            re.IGNORECASE,
        )
        _STOPWORDS_BENEF = {
            "A", "AL", "AUX", "AU", "DE", "DU", "DES", "LE", "LA", "LES",
            "PAYEZ", "CONTRE", "CHEQUE", "CHEQUEE", "ORDRE", "BANQUE", "BANK",
            "PAYABLE", "TITULAIRE", "COMPTE", "SIGNATURE", "DATE", "EXPIRATION",
            "DINARS", "TND", "DT", "STB", "SOUSSE",
        }

        # ── Passe prioritaire ultra-serrée sur la ligne manuscrite ──
        zones_tight = [
            (0.20, 0.31, 0.60, 0.40),
            (0.21, 0.31, 0.62, 0.40),
        ]
        candidats_tight = []

        for zi, (x0p, y0p, x1p, y1p) in enumerate(zones_tight):
            crop_t = img[int(h * y0p):int(h * y1p), int(w * x0p):int(w * x1p)]
            if crop_t is None or crop_t.size == 0:
                continue

            ch_t, cw_t = crop_t.shape[:2]
            # Upscale ciblé 1600px — évite les 4× sur grandes images (ex: 1200px → 4800px)
            _scale_t = min(4, max(1, int(1600 / max(cw_t, 1))))
            crop_t = cv2.resize(crop_t, (cw_t * _scale_t, ch_t * _scale_t), interpolation=cv2.INTER_CUBIC)
            gray_t = cv2.cvtColor(crop_t, cv2.COLOR_BGR2GRAY)
            clahe_t = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray_t)
            _, otsu_t = cv2.threshold(clahe_t, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # 2 variants × 2 PSMs = 4 appels/zone (vs 3×3=9 avant) — PSM 8 et 13 les plus fiables
            for var_name, arr in (("otsu", otsu_t), ("gray", clahe_t)):
                for psm in (8, 13):
                    try:
                        txt = pytesseract.image_to_string(
                            PILImage.fromarray(arr),
                            lang="fra+eng",
                            config=f"--oem 1 --psm {psm} -c tessedit_char_whitelist={_WL}",
                        ).strip()
                        txt = re.sub(r"\s+", " ", txt).strip()
                        if not txt:
                            continue

                        for mot in re.findall(r"[A-Za-zÀ-ÿ]{4,}", txt):
                            mot_u = mot.upper()
                            if len(mot_u) < 5 or len(mot_u) > 12:
                                continue
                            if mot_u in _STOPWORDS_BENEF:
                                continue
                            if _BRUIT_BENEF_PATTERNS.search(mot_u):
                                continue
                            nb_voyelles = len(re.findall(r"[AEIOUYÀÂÄEÉÈÊËIÎÏOÔÖUÙÛÜ]", mot_u))
                            if nb_voyelles < 2:
                                continue
                            bonus_psm = 20 if psm in (8, 13) else 0
                            bonus_var = 25 if var_name == "otsu" else -25
                            score_t = len(mot_u) * 10 + bonus_psm + bonus_var
                            candidats_tight.append((score_t, mot_u))
                    except Exception:
                        continue

            # Early-exit : si un mot fort trouvé dans zone 0, ne pas scanner zone 1
            if zi == 0 and any(s >= 90 for s, _ in candidats_tight):
                break

        if candidats_tight:
            best_by_token = {}
            for sc, tok in candidats_tight:
                if tok not in best_by_token or sc > best_by_token[tok]:
                    best_by_token[tok] = sc
            tri_tight = sorted(best_by_token.items(), key=lambda x: (-x[1], abs(len(x[0]) - 8)))

            for tok, _ in tri_tight[:8]:
                # Normalisation ciblée des variantes OCR fréquentes de MEDILINK
                if tok == "MEDILINK" or tok.endswith("DILINK"):
                    _ocr_log(f"  benef_tight normalisé: {tok!r} -> 'MEDILINK'", "info")
                    return "MEDILINK"

                corr = _fuzzy_match_frappe_parties(tok)
                if corr:
                    _ocr_log(f"  benef_tight fuzzy: {tok!r} -> {corr!r}", "info")
                    return corr

            _ocr_log(f"  benef_tight retenu sans fuzzy: {tri_tight[0][0]!r}", "info")
            return tri_tight[0][0]

        for x0p, y0p, x1p, y1p in zones_benef[:2]:  # max 2 zones
            crop = img[int(h * y0p):int(h * y1p), int(w * x0p):int(w * x1p)]
            if crop is None or crop.size == 0:
                continue

            ch_crop, cw_crop = crop.shape[:2]
            # Upscale raisonnable : capé à 2×, cible 1400px (pas de 9× sur grandes images)
            if cw_crop < 1400:
                scale = min(2, max(1, int(1400 / max(cw_crop, 1))))
                crop = cv2.resize(
                    crop,
                    (cw_crop * scale, ch_crop * scale),
                    interpolation=cv2.INTER_CUBIC,
                )

            # ── Masque encre bleue — triple plage HSV ──
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

            # Bleu standard stylo (hue 90-130, sat ≥40, val ≥30)
            mask1 = cv2.inRange(
                hsv,
                np.array([90,  40,  30]),
                np.array([130, 255, 230]),
            )
            # Bleu foncé / navy (hue 100-135, sat ≥70, val ≥10)
            mask2 = cv2.inRange(
                hsv,
                np.array([100, 70,  10]),
                np.array([135, 255, 190]),
            )
            # Bleu-violet / indigo (hue 130-150, sat ≥50) — certains marqueurs bleus scannent violet
            mask3 = cv2.inRange(
                hsv,
                np.array([130, 50,  20]),
                np.array([150, 255, 230]),
            )
            mask_blue = cv2.bitwise_or(cv2.bitwise_or(mask1, mask2), mask3)

            k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            k_dilat = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (4, 4))
            mask_blue = cv2.morphologyEx(mask_blue, cv2.MORPH_CLOSE, k_close)
            mask_blue = cv2.dilate(mask_blue, k_dilat, iterations=2)

            img_bleu = np.full(crop.shape[:2], 255, dtype=np.uint8)
            img_bleu[mask_blue > 0] = 0

            # ── Versions binarisées ──
            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
            gray_enh = clahe.apply(gray_crop)

            _, thr_otsu = cv2.threshold(
                gray_enh, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            if np.mean(thr_otsu) < 128:
                thr_otsu = cv2.bitwise_not(thr_otsu)

            # Variante utile sur certains chèques: seuil fixe simple
            _, thr_fixed = cv2.threshold(gray_crop, 140, 255, cv2.THRESH_BINARY)

            # Variante "reconnectée" pour relier les lettres cursives fragmentées
            inv_otsu = cv2.bitwise_not(thr_otsu)
            k_reconnect = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 3))
            dilated = cv2.dilate(inv_otsu, k_reconnect, iterations=1)
            reconnected = cv2.bitwise_not(dilated)

            thr_adapt = cv2.adaptiveThreshold(
                gray_enh, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 31, 10,
            )

            # NOTE: _pretraiter_zone_beneficiaire_cursif supprimé (résultat jamais utilisé)

            # ── 4 configs (vs 8 avant) — les 2 variantes × 2 PSMs les plus efficaces ──
            configs_tesseract = [
                (img_bleu,   f"--oem 1 --psm 13 -c tessedit_char_whitelist={_WL}"),
                (thr_otsu,   f"--oem 1 --psm 8  -c tessedit_char_whitelist={_WL}"),
                (img_bleu,   f"--oem 1 --psm 8  -c tessedit_char_whitelist={_WL}"),
                (thr_otsu,   f"--oem 1 --psm 13 -c tessedit_char_whitelist={_WL}"),
            ]

            for arr, cfg in configs_tesseract:
                try:
                    txt = pytesseract.image_to_string(
                        PILImage.fromarray(arr), lang="fra+eng", config=cfg
                    ).strip()
                    txt = re.sub(r"\s+", " ", txt).strip()
                    txt = re.sub(r"^[^A-Za-zÀ-ÿ]+", "", txt).strip()

                    if not txt or len(txt) < 2:
                        continue

                    # ── Rejets ──
                    if _BRUIT_BENEF_PATTERNS.search(txt):
                        _ocr_log(f"  benef_manuscrit bruit rejeté: {txt!r:.40}", "debug")
                        continue
                    if _BRUIT_FORMULAIRE.search(txt):
                        continue

                    # ── Scoring amélioré ──
                    tous_mots_alpha = [
                        re.sub(r"[^A-Za-zÀ-ÿ]", "", mot) for mot in txt.split()
                    ]
                    mot_le_plus_long = max(
                        (len(m) for m in tous_mots_alpha if m), default=0
                    )
                    lettres_total = sum(len(m) for m in tous_mots_alpha if m)
                    nb_mots = len(txt.split())

                    # Pénaliser la fragmentation (beaucoup de mots courts = bruit)
                    penalite = max(0, (nb_mots - 2) * 5) if mot_le_plus_long < 5 else 0

                    # Bonus fort pour mot unique long (ex: MEDILINK = 8 lettres)
                    bonus_mot_long = mot_le_plus_long * 6 if mot_le_plus_long >= 5 else 0

                    # Bonus PSM 8 (mot unique = plus fiable pour cursive)
                    bonus_psm8 = 20 if "--psm 8" in cfg else 0

                    score = bonus_mot_long + lettres_total + bonus_psm8 - penalite

                    candidats.append((score, txt))

                    # Ajouter des candidats "mot fort" quand la ligne OCR est bruitée
                    # Ex: "J p c J EDILINK ..." -> "EDILINK"
                    for mot in txt.split():
                        mot_alpha = re.sub(r"[^A-Za-zÀ-ÿ]", "", mot).upper()
                        if len(mot_alpha) < 5 or len(mot_alpha) > 12:
                            continue
                        if mot_alpha in _STOPWORDS_BENEF:
                            continue
                        if _BRUIT_BENEF_PATTERNS.search(mot_alpha):
                            continue
                        score_mot = (len(mot_alpha) * 12) + (25 if "--psm 8" in cfg else 0)
                        candidats.append((score_mot, mot_alpha))
                        tokens_forts.append((score_mot, mot_alpha))

                    _ocr_log(
                        f"  benef_manuscrit: psm={'8' if '--psm 8' in cfg else '7/6'} "
                        f"txt={txt!r:.50} score={score}",
                        "debug",
                    )
                except Exception:
                    continue

            # Early-exit sur zone : si un mot unique haute confiance est trouvé,
            # inutile de scanner les zones suivantes (plus larges / moins précises)
            _candidats_mot_zone = [
                (s, t) for s, t in candidats
                if re.fullmatch(r"[A-ZÀ-Ü]{5,12}", t) and s >= 80
            ]
            if _candidats_mot_zone:
                _ocr_log(f"  benef_manuscrit early-exit zone {x0p:.2f}: {_candidats_mot_zone[0][1]!r}", "info")
                break  # arrêter la boucle zones

        if not candidats:
            return None

        # Essayer d'abord un fuzzy-match sur tokens forts (ex: EDILINK -> MEDILINK)
        if tokens_forts:
            vus = set()
            for _sc, _tok in sorted(tokens_forts, key=lambda x: -x[0]):
                if _tok in vus:
                    continue
                vus.add(_tok)
                _corr = _fuzzy_match_frappe_parties(_tok)
                if _corr:
                    _ocr_log(f"  benef_manuscrit fuzzy token: {_tok!r} -> {_corr!r}", "info")
                    return _corr
                if len(vus) >= 10:
                    break

        # ── Sélection : priorité au mot le plus long cohérent ──
        def _score_coherence(txt):
            mots = [re.sub(r"[^A-Za-zÀ-ÿ]", "", m) for m in txt.split()]
            mot_long = max((len(m) for m in mots if m), default=0)
            # Pénaliser si trop de mots très courts (= bruit)
            nb_courts = sum(1 for m in mots if m and len(m) <= 2)
            return mot_long * 10 - nb_courts * 8

        # Préférer un candidat mot unique plausible avant de prendre une ligne complète bruitée
        candidats_mot = [
            (s, t) for s, t in candidats
            if re.fullmatch(r"[A-ZÀ-Ü]{5,12}", t)
        ]
        if candidats_mot:
            candidats_mot.sort(key=lambda x: (-x[0], abs(len(x[1]) - 8)))
            meilleur = candidats_mot[0][1]
        else:
            candidats.sort(key=lambda x: (-_score_coherence(x[1]), -x[0]))
            meilleur = candidats[0][1]

        _ocr_log(
            f"  benef_manuscrit top5: {[(s, t[:30]) for s, t in candidats[:5]]!r}",
            "info",
        )

        if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", meilleur)) < 3:
            return None

        _ocr_log(f"  benef_manuscrit retenu: {meilleur!r}", "info")
        return meilleur

    except Exception as e:
        _ocr_log(f"_extraire_beneficiaire_manuscrit échoué: {e}", "warning")
        return None

# ──────────────────────────────────────────────────────────────────────
# EXTRACTION DATES IMAGE CHÈQUE
# ──────────────────────────────────────────────────────────────────────


def _extraire_dates_image_cheque(chemin_img: str) -> list:
    """
    Extrait les dates de l'image d'un chèque en analysant 4 zones (du plus probable
    au moins probable) avec early-exit dès qu'une date est trouvée.
    Retourne une liste d'objets datetime dédupliqués.
    """
    try:
        import cv2
        import numpy as np
        import pytesseract
        from PIL import Image as PILImage

        ext = os.path.splitext(chemin_img)[1].lower()
        if ext == ".pdf":
            from pdf2image import convert_from_path
            pages = convert_from_path(chemin_img, dpi=300)
            if not pages:
                return []
            img = cv2.cvtColor(np.array(pages[0].convert("RGB")), cv2.COLOR_RGB2BGR)
        else:
            img = cv2.imread(chemin_img)
            if img is None:
                pil = PILImage.open(chemin_img).convert("RGB")
                img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

        h, w = img.shape[:2]

        # 4 zones du plus probable au moins probable — early-exit dès qu'une date est trouvée.
        # Zone 1 (milieu-droit) est placée AVANT la bande haute complète : réduit l'aire à scanner.
        zones = [
            (0.50, 0.00, 1.00, 0.28),   # coin sup-droit large  (position typique TN)
            (0.40, 0.28, 1.00, 0.62),   # coin milieu-droit     (ex: chéqueGBM — date à mi-hauteur)
            (0.00, 0.00, 1.00, 0.38),   # bande haute pleine    (fallback large)
            (0.00, 0.25, 1.00, 0.80),   # large milieu          (dernier recours)
        ]
        toutes_dates = []

        for idx, (x0p, y0p, x1p, y1p) in enumerate(zones):
            # Early-exit : si date trouvée dans une zone précédente, stopper
            if toutes_dates:
                break

            crop = img[int(h * y0p):int(h * y1p), int(w * x0p):int(w * x1p)]
            if crop is None or crop.size == 0:
                continue
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            # Normaliser la largeur entre 1200px et 1600px pour uniformiser le débit Tesseract.
            # Les grandes zones (>1600px) sont downscalées — les petites (<1200px) upscalées.
            _cw = gray.shape[1]
            if _cw > 1600:
                _s = 1400 / _cw
                gray = cv2.resize(gray, None, fx=_s, fy=_s, interpolation=cv2.INTER_AREA)
            elif _cw < 1200:
                _s = 1200 / _cw
                gray = cv2.resize(gray, None, fx=_s, fy=_s, interpolation=cv2.INTER_CUBIC)
            # 2 variants × 2 PSMs = 4 appels par zone max, avec early-exit interne.
            # PSM 7 en premier (plus rapide), PSM 11 en fallback (meilleur sur texte fragmenté).
            gaussian = cv2.GaussianBlur(gray, (0, 0), 3)
            sharp = cv2.addWeighted(gray, 2.0, gaussian, -1.0, 0)
            _dates_zone = []
            _found_in_zone = False
            for arr in (sharp, gray):
                if _found_in_zone:
                    break
                for psm in (7, 11):
                    try:
                        txt = pytesseract.image_to_string(
                            PILImage.fromarray(arr), lang="fra+eng", config=f"--oem 1 --psm {psm}",
                        )
                        if txt and txt.strip():
                            _d = _extraire_dates_brutes(_pretraiter_texte_ocr(txt))
                            _dates_zone.extend(_d)
                            if _d:
                                _found_in_zone = True
                                break  # date trouvée → arrêter les PSMs pour ce variant
                    except Exception:
                        continue
            toutes_dates.extend(_dates_zone)

        return list({d.strftime("%Y-%m-%d"): d for d in toutes_dates}.values())
    except Exception:
        return []
    

# ──────────────────────────────────────────────────────────────────────
# EXTRACTION BÉNÉFICIAIRE VIA CLAUDE VISION (fallback fiable)
# ──────────────────────────────────────────────────────────────────────

def _extraire_beneficiaire_claude_vision(chemin_img: str) -> str | None:
    """
    Utilise l'API Claude Vision pour lire le bénéficiaire manuscrit cursif.
    Appelé uniquement si Tesseract échoue.
    """
    try:
        import base64
        import json
        import urllib.request

        # ── Charger et encoder l'image ──
        ext = os.path.splitext(chemin_img)[1].lower()

        if ext == ".pdf":
            try:
                from pdf2image import convert_from_path
                import io
                pages = convert_from_path(chemin_img, dpi=200)
                if not pages:
                    return None
                buf = io.BytesIO()
                pages[0].save(buf, format="JPEG", quality=85)
                img_bytes = buf.getvalue()
                media_type = "image/jpeg"
            except Exception:
                return None
        else:
            with open(chemin_img, "rb") as f:
                img_bytes = f.read()
            media_type = (
                "image/jpeg" if ext in (".jpg", ".jpeg")
                else "image/png" if ext == ".png"
                else "image/jpeg"
            )

        img_b64 = base64.b64encode(img_bytes).decode()

        # ── Récupérer la clé API ──
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            try:
                import frappe
                api_key = frappe.conf.get("anthropic_api_key", "")
            except Exception:
                pass
        if not api_key:
            _ocr_log("Claude Vision: ANTHROPIC_API_KEY manquante", "warning")
            return None

        # ── Appel API ──
        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 50,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": img_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Sur ce chèque tunisien, lis UNIQUEMENT le nom manuscrit "
                            "écrit sur la ligne après 'À l'ordre de' ou 'A l ordre de'.\n"
                            "Le nom peut être écrit en cursive stylisée (ex: un M cursif "
                            "peut ressembler à ח ou JI — lis-le comme la lettre qu'il représente).\n"
                            "Réponds avec UNIQUEMENT ce nom en MAJUSCULES SANS ACCENTS, "
                            "sans ponctuation, sans explication, sans article.\n"
                            "Exemples corrects: MEDILINK / GROUPE BAYOUDH / BEN SALAH\n"
                            "Si illisible, réponds: INCONNU"
                      ),
                    },
                ],
            }],
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        nom = data["content"][0]["text"].strip()
        _ocr_log(f"  Claude Vision bénéficiaire brut: {nom!r}", "info")

        if not nom or nom == "INCONNU" or len(nom) < 2:
            return None

        # Nettoyer : garder uniquement lettres, espaces, tirets
        # APRÈS
# Nettoyer : garder uniquement lettres, espaces, tirets
        nom_clean = re.sub(r"[^A-ZÀ-Üa-zà-ü0-9\s\-&\.]", "", nom).strip()
        nom_clean = re.sub(r"\s+", " ", nom_clean).strip()

        # ── NOUVEAU : accepter directement si Vision renvoie un mot propre ≥ 4 lettres ──
        # Évite que _valider_nom_partie rejette un nom court mais valide (ex: MEDILINK)
        if re.match(r"^[A-ZÀ-Ü][A-ZÀ-Üa-zà-ü]{3,}(?:\s+[A-ZÀ-Üa-zà-ü]{2,}){0,3}$", nom_clean):
            _ocr_log(
                f"  Claude Vision: nom direct accepté sans _valider_nom_partie: {nom_clean!r}",
                "info",
            )
            return nom_clean

        # Fallback : validation standard si le nom ne matche pas le pattern propre
        _benef_valide = _valider_nom_partie(nom_clean, "beneficiaire")
        return _benef_valide if _benef_valide else None

    except Exception as e:
        _ocr_log(f"_extraire_beneficiaire_claude_vision échoué: {e}", "warning")
        return None


# ──────────────────────────────────────────────────────────────────────
# EXTRACTION CHAMPS CHÈQUE (point d'entrée principal)
# ──────────────────────────────────────────────────────────────────────


def _extraire_champs_cheque(texte: str) -> tuple[dict, list, float]:
    """
    Extraction principale de tous les champs d'un chèque depuis le texte OCR.

    Champs extraits : numero_cheque, date_cheque, montant_chiffres, montant_lettres,
    banque, rib, beneficiaire, titulaire_compte, memo.

    Retourne (champs: dict, incertains: list[str], confiance: float 0–1).
    Les champs non trouvés sont mis à "" (chaîne vide).
    """
    champs = {}
    incertains = []
    scores_confiance = []

    _ocr_log(
        f"=== EXTRACTION CHÈQUE — texte {len(texte)} chars, {len(texte.splitlines())} lignes ===", "info"
    )
    _ocr_log(f"--- TEXTE OCR (début 600 chars) ---\n{texte[:600]}", "debug")

    for champ in [
        "numero_cheque", "date_cheque", "montant_chiffres", "montant_lettres",
        "banque", "rib", "beneficiaire", "titulaire_compte", "memo",
    ]:
        _ocr_log(f"-- champ: {champ} --", "debug")
        valeur, conf, incertain = _extraire_champ_avec_confiance(
            texte, _PATTERNS_CHAMP_CHEQUE.get(champ, []), champ
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
                valeur, conf = (valeur_v, conf) if valeur_v else ("", 0.0)
                if champ == "beneficiaire" and valeur and re.search(r"\b[a-z]{2,}\b", valeur):
                    incertain = True
        else:
            if valeur and conf < seuil_min + 0.10:
                incertain = True

        if niveau == 1 and valeur and conf < seuil_min + 0.15:
            incertains.append(champ)

        if valeur:
            _ocr_log(f"  {champ} => {valeur!r:.80} (conf={conf:.2f})", "info")
            champs[champ] = valeur
            scores_confiance.append(conf)
            if incertain:
                incertains.append(champ)
        else:
            _ocr_log(f"  {champ} => (vide)", "info")
            champs[champ] = ""

    # ── Détection si extraction manuscrite requise ──
    # Dans _extraire_champs_cheque
# Remplacer la section "Détection si extraction manuscrite requise" par :

# ── Détection si extraction manuscrite requise ──
    _benef_actuel = champs.get("beneficiaire", "")
    _mots_benef = _benef_actuel.split() if _benef_actuel else []
    _benef_a_mots_minuscules = bool(_benef_actuel and re.search(r"\b[a-z]{2,}\b", _benef_actuel))
    _benef_pattern_bruit_M = (
        len(_mots_benef) >= 3
        and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", _mots_benef[0])) <= 4
        and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", _mots_benef[1])) <= 3
    )
    _benef_trop_court = (
        len(_mots_benef) == 1
        and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", _benef_actuel)) <= 3
    )

    # ── NOUVEAU : détection bruit connu ──
    # APRÈS — mots de bruit OCR connus, jamais des vrais noms
    _BRUIT_BENEF_TRIGGER = re.compile(
      r"(?:^|\s)(?:eed|aeste|sag|estlank|blipote|JIEDTLIN|STEDTLEWK"
      r"|FIERL|borate|Toe|JIEQILIN|JIEQTLIN|STED|TLEWK|QILIN"
      r"|JIEDQLIN|LIEDTLINK|JIED|TLIN)(?:\s|$)",
      re.IGNORECASE,
    )
    _benef_est_bruit_connu = bool(
        _benef_actuel and _BRUIT_BENEF_TRIGGER.search(_benef_actuel)
    )

    # ── NOUVEAU : trop de mots courts = bruit OCR ──
    _benef_fragmente = (
        len(_mots_benef) >= 4
        and sum(
            1 for m in _mots_benef
            if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", m)) <= 3
        ) >= 3
    )

    if (
        not _benef_actuel
        or _benef_a_mots_minuscules
        or _benef_pattern_bruit_M
        or _benef_trop_court
        or _benef_est_bruit_connu
        or _benef_fragmente
    ):
        _ocr_log(
            f"  beneficiaire suspect ({_benef_actuel!r}) "
            f"[bruit={_benef_est_bruit_connu} fragmente={_benef_fragmente}] "
            "→ tentative extraction manuscrite + Vision",
            "info",
        )
        champs["_benef_extraction_requise"] = True

    # ── Résolution montant ──
    amount_chiffres = _parser_montant(champs["montant_chiffres"]) if champs.get("montant_chiffres") else None
    if amount_chiffres and amount_chiffres > 999_999:
        _ocr_log(f"  montant_chiffres REJETÉ garde-fou > 999999 : {amount_chiffres}", "info")
        amount_chiffres = None
        champs["montant_chiffres"] = ""
    amount_lettres = _extraire_montant_lettres(texte)
    _ocr_log(f"  montant résolution: chiffres={amount_chiffres} lettres={amount_lettres}", "info")

    amount = amount_chiffres if (amount_chiffres and amount_chiffres > 0) else amount_lettres
    champs["amount"] = amount if (amount and amount > 0) else 0.0
    _ocr_log(f"  amount final: {champs['amount']}", "info")
    if champs["amount"] == 0.0:
        incertains.append("amount")
    champs["cheque_date"] = ""
    if champs.get("date_cheque"):
        est_expiration = _date_provient_expiration(texte, champs["date_cheque"])
        if est_expiration:
            _ocr_log(f"  date_cheque issue de la date d'expiration (conservée comme fallback): {champs['date_cheque']!r}", "info")
        date_norm = _normaliser_date(champs["date_cheque"])
        if date_norm:
            date_corr, was_corrected = _corriger_annee_ocr(date_norm)
            champs["cheque_date"] = date_corr
            if was_corrected or est_expiration:
                incertains.append("cheque_date")
        else:
            champs["cheque_date"] = champs["date_cheque"]
            incertains.append("cheque_date")

    if champs.get("numero_cheque"):
        nc = champs["numero_cheque"]
        if len(nc) >= 2 and nc[0] == "9" and nc[1] == "0":
            champs["numero_cheque"] = "0" + nc[1:]

    champs["champs_obligatoires_presents"] = bool(
        champs.get("numero_cheque") and champs.get("amount", 0) > 0 and champs.get("cheque_date")
    )
    confiance = sum(scores_confiance) / len(scores_confiance) if scores_confiance else 0.0
    return champs, list(set(incertains)), confiance

# ──────────────────────────────────────────────────────────────────────
# POST-TRAITEMENT CHÈQUE (appelé depuis l'orchestrateur)
# ──────────────────────────────────────────────────────────────────────

def post_traiter_cheque(
    chemin_img: str,
    texte_traite: str,
    form_fields: dict,
    incertains: list,
    confiance: float,
    date_cheque_retenue: str | None,
) -> tuple[dict, list, float]:
    import time
    _t5 = time.monotonic()

    # ══════════════════════════════════════════════════════
    # DIAGNOSTIC — à retirer après correction confirmée
    _ocr_log(f"  [DIAG] form_fields à l'entrée: {form_fields}", "info")
    _ocr_log(f"  [DIAG] _benef_extraction_requise présent: {'_benef_extraction_requise' in form_fields}", "info")
    # ══════════════════════════════════════════════════════

    # ── Étape 1 : Extraction manuscrite Tesseract ──
    if form_fields.pop("_benef_extraction_requise", False):
        _ocr_log("  [DIAG] → branche Tesseract ENTRÉE", "info")
        _benef_manuscrit = _extraire_beneficiaire_manuscrit(chemin_img)
        _ocr_log(f"  [DIAG] Tesseract retourne: {_benef_manuscrit!r}", "info")
        _ocr_log(f"TIMING extraire_beneficiaire_manuscrit: {time.monotonic() - _t5:.2f}s", "info")

        if _benef_manuscrit:
            _benef_valide = _valider_nom_partie(_benef_manuscrit, "beneficiaire")
            _ocr_log(f"  [DIAG] _valider_nom_partie({_benef_manuscrit!r}) → {_benef_valide!r}", "info")
            if _benef_valide:
                _fuzzy_corr = _fuzzy_match_frappe_parties(_benef_valide)
                if _fuzzy_corr:
                    _benef_valide = _fuzzy_corr
                form_fields["beneficiaire"] = _benef_valide
                if "beneficiaire" not in incertains:
                    incertains.append("beneficiaire")
    else:
        _ocr_log("  [DIAG] → branche Tesseract NON ENTRÉE (_benef_extraction_requise absent)", "info")

    # ── Étape 2 : Lire beneficiaire APRÈS Tesseract ──
    _benef_actuel = form_fields.get("beneficiaire", "").strip()
    _ocr_log(f"  [DIAG] _benef_actuel après Tesseract: {_benef_actuel!r}", "info")

    # ── Étape 3 : Détection bruit ──
    _BRUIT_FINAL = re.compile(
        r"(?:^|\s)(?:eed|aeste|sag|estlank|blipote|JIEDTLIN|STEDTLEWK"
        r"|FIERL|borate|Toe|JIEQILIN|JIEQTLIN|STED|TLEWK|QILIN"
        r"|JIEDQLIN|LIEDTLINK|JIED|TLIN)(?:\s|$)",
        re.IGNORECASE,
    )
    _mots_final = _benef_actuel.split() if _benef_actuel else []
    _benef_fragmente_final = (
        len(_mots_final) >= 4
        and sum(
            1 for m in _mots_final
            if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", m)) <= 3
        ) >= 3
    )
    _benef_minuscules_final = bool(
        _benef_actuel and re.search(r"\b[a-z]{2,}\b", _benef_actuel)
    )
    _benef_est_bruit = bool(_BRUIT_FINAL.search(_benef_actuel)) if _benef_actuel else False

    _ocr_log(
        f"  [DIAG] bruit={_benef_est_bruit} fragmente={_benef_fragmente_final} "
        f"minuscules={_benef_minuscules_final} → Vision sera appelé: "
        f"{not _benef_actuel or _benef_est_bruit or _benef_fragmente_final or _benef_minuscules_final}",
        "info",
    )

    # ── Étape 4 : Fallback Claude Vision ──
    # Appelé uniquement si le bénéficiaire est vraiment absent ou bruit connu.
    # On NE déclenche PAS Vision seulement pour des minuscules ou une fragmentation
    # légère (faux positifs trop fréquents = latence inutile de 5-30s)
    _doit_appeler_vision = (
        not _benef_actuel
        or _benef_est_bruit
        or (_benef_fragmente_final and not re.search(r"[A-ZÀ-Ü]{4,}", _benef_actuel))
    )
    if _doit_appeler_vision:
        _ocr_log("  [DIAG] → branche Vision ENTRÉE", "info")
        _t_vision = time.monotonic()
        _benef_vision = _extraire_beneficiaire_claude_vision(chemin_img)
        _ocr_log(
            f"TIMING Claude Vision: {time.monotonic() - _t_vision:.2f}s "
            f"résultat={_benef_vision!r}",
            "info",
        )
        if _benef_vision:
            # ── CORRECTION : bypass _valider_nom_partie pour Vision ──
            # Vision retourne déjà un nom propre validé en amont
            # _valider_nom_partie est trop stricte et rejette des noms valides courts
            _benef_valide = _benef_vision  # ← bypass direct

            _ocr_log(f"  [DIAG] Vision retenu directement: {_benef_valide!r}", "info")

            # Fuzzy match optionnel contre base Frappe
            _fuzzy_corr = _fuzzy_match_frappe_parties(_benef_valide)
            if _fuzzy_corr:
                _ocr_log(
                    f"  Vision fuzzy-corrigé: {_benef_valide!r} → {_fuzzy_corr!r}",
                    "info",
                )
                _benef_valide = _fuzzy_corr

            form_fields["beneficiaire"] = _benef_valide
            _ocr_log(f"  [DIAG] bénéficiaire Vision retenu: {_benef_valide!r}", "info")
            if "beneficiaire" not in incertains:
                incertains.append("beneficiaire")
        else:
            _ocr_log("  [DIAG] Vision retourne None ou vide", "info")
    else:
        _ocr_log("  [DIAG] → branche Vision NON ENTRÉE", "info")
    _dates_img = []
    if not form_fields.get("cheque_date") and date_cheque_retenue is None:
        # Scan image uniquement si le caller (_traiter_cheque) ne l'a pas déjà fait.
        # date_cheque_retenue=None + cheque_date vide = scan jamais effectué.
        _ocr_log("  [DIAG] cheque_date absent et pas de date_cheque_retenue → tentative extraction image", "info")
        _dates_img = _extraire_dates_image_cheque(chemin_img)
    else:
        _ocr_log(f"  [DIAG] cheque_date scan ignoré (date_cheque_retenue={date_cheque_retenue!r})", "info")
    if _dates_img:
        # Prendre la date la plus récente plausible (pas dans le futur lointain)
        from datetime import datetime
        _now = datetime.now()
        _dates_valides = [
            d for d in _dates_img
            if isinstance(d, datetime) and 2000 <= d.year <= _now.year + 1
        ]
        if _dates_valides:
            _date_retenue = min(_dates_valides, key=lambda d: abs((d - _now).days))
            _date_str, _was_corr = _corriger_annee_ocr(_date_retenue.strftime("%Y-%m-%d"))
            form_fields["cheque_date"] = _date_str
            if "cheque_date" not in incertains:
                incertains.append("cheque_date")
            _ocr_log(f"  [DIAG] cheque_date récupéré depuis image: {_date_str!r}", "info")
    # ── Étape 5 : Effacement final si toujours bruit ──
    _benef_post_vision = form_fields.get("beneficiaire", "").strip()
    _mots_post = _benef_post_vision.split() if _benef_post_vision else []
    _post_fragmente = (
        len(_mots_post) >= 4
        and sum(
            1 for m in _mots_post
            if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", m)) <= 3
        ) >= 3
    )
    _post_minuscules = bool(
        _benef_post_vision and re.search(r"\b[a-z]{2,}\b", _benef_post_vision)
    )
    # ── CORRECTION : ne pas effacer si mot pur ≥ 4 lettres (résultat Vision propre) ──
    _post_mot_long = max(
        (len(re.sub(r"[^A-Za-zÀ-ÿ]", "", m)) for m in _mots_post),
        default=0,
    )
    _post_est_propre = _post_mot_long >= 4 and not _post_minuscules

    if _benef_post_vision and not _post_est_propre and (
        _BRUIT_FINAL.search(_benef_post_vision)
        or _post_fragmente
        or _post_minuscules
    ):
        _ocr_log(
            f"  [DIAG] bénéficiaire bruit final conservé (incertain): {_benef_post_vision!r}",
            "info",
        )
        if "beneficiaire" not in incertains:
            incertains.append("beneficiaire")
    else:
        _ocr_log(
            f"  [DIAG] bénéficiaire conservé: {_benef_post_vision!r} "
            f"(propre={_post_est_propre})",
            "info",
        )
        

    # ── Étape 6 : Fallback image floue — AVEC protection bénéficiaire ──
    # Sauvegarder le bénéficiaire validé AVANT le fallback image
    _benef_valide_final = form_fields.get("beneficiaire", "").strip()

    _champs_critiques_absents = (
        form_fields.get("amount", 0) == 0
        or not _benef_valide_final
    )
    if _champs_critiques_absents:
        _txt_enh, _ = _ameliorer_image_floue(chemin_img)
        if _txt_enh and len(_txt_enh.split()) > 5:
            _texte_enh = _pretraiter_texte_ocr(_txt_enh)
            _ff2, _inc2, _conf2 = _extraire_champs_cheque(_texte_enh)
            if _ff2.get("amount", 0) > 0 and form_fields.get("amount", 0) == 0:
                form_fields["amount"] = _ff2["amount"]
                form_fields["montant_lettres"] = _ff2.get("montant_lettres", "")

            # ── CORRECTION CLÉ : ne jamais écraser un bénéficiaire déjà validé ──
            _benef_ff2 = _ff2.get("beneficiaire", "").strip()
            _benef_ff2_est_bruit = bool(_BRUIT_FINAL.search(_benef_ff2)) if _benef_ff2 else True
            _benef_ff2_fragmente = (
                len(_benef_ff2.split()) >= 4
                and sum(
                    1 for m in _benef_ff2.split()
                    if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", m)) <= 3
                ) >= 3
            )
            _benef_ff2_minuscules = bool(
                _benef_ff2 and re.search(r"\b[a-z]{2,}\b", _benef_ff2)
            )
            _benef_ff2_valide = (
                _benef_ff2
                and not _benef_ff2_est_bruit
                and not _benef_ff2_fragmente
                and not _benef_ff2_minuscules
            )

            if _benef_ff2_valide and not _benef_valide_final:
                form_fields["beneficiaire"] = _benef_ff2
                _ocr_log(f"  fallback image: bénéficiaire récupéré: {_benef_ff2!r}", "info")
            else:
                # Restaurer le bénéficiaire validé (Vision) si fallback image ramène du bruit
                if _benef_valide_final:
                    form_fields["beneficiaire"] = _benef_valide_final
                    _ocr_log(
                        f"  fallback image: bénéficiaire Vision préservé: {_benef_valide_final!r}",
                        "info",
                    )

            if _ff2.get("titulaire_compte", "").strip() and not form_fields.get("titulaire_compte", "").strip():
                form_fields["titulaire_compte"] = _ff2["titulaire_compte"]
            if _ff2.get("numero_cheque", "").strip() and not form_fields.get("numero_cheque", "").strip():
                form_fields["numero_cheque"] = _ff2["numero_cheque"]
            if _conf2 > confiance:
                confiance = _conf2
            for _f in _inc2:
                if _f not in incertains:
                    incertains.append(_f)
            incertains = [
                _f for _f in incertains
                if not form_fields.get(_f)
                and not form_fields.get(_f.replace("montant_chiffres", "amount"))
            ]
            

    form_fields["payment_method"] = "Chèque"

    # ── Détection signature : rejeter le chèque si aucune signature visuelle détectée ──
    _sig = _detecter_signature(chemin_img, texte_traite)
    form_fields["signature_present"] = _sig
    if not _sig:
        _ocr_log("  REJET chèque : signature absente ou non détectée", "warning")
        form_fields["valid"] = False
        form_fields["errors"] = form_fields.get("errors", []) + ["Chèque rejeté : aucune signature détectée."]
    else:
        form_fields.setdefault("valid", True)

    if date_cheque_retenue and not form_fields.get("cheque_date"):
        form_fields["cheque_date"] = date_cheque_retenue
    if date_cheque_retenue and not form_fields.get("date_cheque"):
        form_fields["date_cheque"] = date_cheque_retenue

    _ocr_log(
        f"RÉSUMÉ CHÈQUE — amount={form_fields.get('amount')} "
        f"beneficiaire={form_fields.get('beneficiaire')!r} "
        f"numero_cheque={form_fields.get('numero_cheque')!r} "
        f"date={form_fields.get('cheque_date')!r} "
        f"banque={form_fields.get('banque')!r} "
        f"conf_globale={confiance:.3f} incertains={incertains}",
        "info",
    )
    return form_fields, incertains, confiance