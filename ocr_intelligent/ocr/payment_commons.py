# -*- coding: utf-8 -*-
"""
payment_commons.py — Groupe Bayoudh Metal
Constantes, utilitaires et fonctions partagées entre cheque_extractor et traite_extractor.
"""

import re
import os
import time
import hashlib
import threading
from datetime import datetime, timedelta

# ──────────────────────────────────────────────────────────────────────
# TIMEOUT GLOBAL OCR
# ──────────────────────────────────────────────────────────────────────

MAX_OCR_SECONDS = 25

_OCR_CACHE: dict = {}

# ──────────────────────────────────────────────────────────────────────
# LOGGER
# ──────────────────────────────────────────────────────────────────────


def _ocr_log(msg: str, level: str = "debug") -> None:
    prefixed = f"[OCR] {msg}"
    try:
        import frappe
        logger = frappe.logger("ocr", allow_site=True, file_count=5)
        getattr(logger, level, logger.debug)(prefixed)
    except Exception:
        print(prefixed)


# ──────────────────────────────────────────────────────────────────────
# CONSTANTES MÉTIER
# ──────────────────────────────────────────────────────────────────────

PEREMPTION_CHEQUE_MOIS = 12

_SEUIL_CONFIANCE_PARTIE = 0.30
_SEUIL_TOKENS_VALIDES = 0.55

_MOTS_INTERDITS_PARTIE = {
    "signature", "cachet", "date", "montant", "banque", "agence",
    "adresse", "telephone", "fax", "sfax", "lieu", "le", "la",
}

# ──────────────────────────────────────────────────────────────────────
# BANQUES TUNISIENNES
# ──────────────────────────────────────────────────────────────────────

_BANQUES_TN = [
    "STB", "BNA", "BIAT", "UIB", "ATB", "BT", "BH", "Zitouna", "QNB",
    "UBCI", "ABC", "CIB", "BFT", "Attijari", "Wafa", "Amen",
    "Tunisie Leasing", "Arab Tunisian Bank", "Banque de Tunisie",
    "Société Tunisienne de Banque", "Banque Nationale Agricole",
    "Banque Internationale Arabe", "Banque B",
]

_BANQUES_TN_LOWER = {b.lower() for b in _BANQUES_TN}
_BANQUES_TN_PREFIXES = [b.lower() for b in _BANQUES_TN]
_BANQUES_PATTERN = "|".join(re.escape(b) for b in _BANQUES_TN)

# ──────────────────────────────────────────────────────────────────────
# VILLES TUNISIENNES
# ──────────────────────────────────────────────────────────────────────

_VILLES_TN = [
    "Tunis", "Sfax", "Sousse", "Bizerte", "Nabeul", "Monastir", "Mahdia",
    "Kasserine", "Kairouan", "Gafsa", "Gabes", "Medenine", "Beja",
    "Jendouba", "Ariana", "Ben Arous", "Zaghouan", "Hammamet", "Kélibia",
    "Zarzis", "Jerba", "Djerba", "Mateur", "Menzel Bourguiba",
]
_VILLES_TN_PATTERN = "|".join(re.escape(v) for v in _VILLES_TN)

# ──────────────────────────────────────────────────────────────────────
# SENSIBILITÉ DES CHAMPS
# ──────────────────────────────────────────────────────────────────────

_SENSIBILITE_CHAMP = {
    "numero_cheque":      (1, 0.55),
    "montant_chiffres":   (1, 0.60),
    "banque":             (1, 0.50),
    "date_cheque":        (2, 0.45),
    "rib":                (2, 0.40),
    "beneficiaire":       (2, 0.45),
    "titulaire_compte":   (3, 0.25),
    "memo":               (3, 0.20),
    "numero_traite":      (1, 0.50),
    "date_echeance":      (1, 0.55),
    "montant":            (1, 0.55),
    "date_emission":      (2, 0.45),
    "tireur":             (2, 0.40),
    "tire":               (2, 0.45),
    "domiciliation":      (3, 0.25),
}

# ──────────────────────────────────────────────────────────────────────
# BRUIT FORMULAIRE
# ──────────────────────────────────────────────────────────────────────

_BRUIT_FORMULAIRE = re.compile(
    r"\b(?:"
    r"lui[\s\-]*m[eê]me|fournisseur\s+du|fournisseur|souscripteur|vendeur"
    r"|acheteur|le\s+soussign|pr[ée]sent|ci[\s\-]?dessus|ci[\s\-]?apr[eè]s"
    r"|pour\s+(?:acquit|solde|valeur)|contre\s+(?:cette|la|remise)"
    r"|accept[ée]e?\s+(?:par|le)|payable(?:\s+[àa])?|[àa]\s+(?:payer|l[''']ordre)"
    r"|bon\s+pour|valeur\s+(?:en|reçue|re[çc]ue)|en\s+(?:votre|notre)"
    r"|i\s+te\s+v|lui\s+meme|lui\-meme|lui\s+même"
    r"|fournisseur\s+d[uo]|du\s+fournisseur|du\s+vendeur|du\s+souscripteur"
    r"|emetteur|[eé]metteur|cr[eé]ancier|d[eé]biteur|porteur|au\s+porteur"
    r"|à\s+l[''']ordre|ordre\s+de|order\s+de|order\s+of"
    r"|order\s+de\s+paiement|ordre\s+de\s+paiement|bill\s+of\s+exchange"
    r"|lettre\s+de\s+change|republique\s+tunisienne|r[ée]publique\s+tunisienne"
    r"|cnp|nom\s+et\s+adresse|adresse\s+du|signature\s+du|cachet\s+du"
    r"|accept[ée]e?|non\s+endossable|bon\s+pour\s+aval|pour\s+aval"
    r"|sous\s+aval|aval(?:is[eé]|ist)|domicili[eé]"
    r"|à\s+l[''']échéance|[àa]\s+vue"
    r"|payer\s+contre|payez\s+contre|somme\s+de|la\s+somme\s+de"
    r"|contre\s+cette|maquette|specimen|modele|formulaire"
    r"|sd\s*,|gee\s+it|blipote|exchanges|ae\s+soh|wee\s+ons|gst\s+oe"
    r"|rae\s+ah|dp\s+pe|cn\s+ase|ase\s+de"
    r"|protestable|non\s+protestable|sans\s+frais|avec\s+frais"
    r"|b[eé]n[eé]fice\s+de|valeur\s+en\s+compte|valeur\s+re[çc]ue"
    r"|cette\s+lettre\s+de\s+change|contre\s+cette\s+lettre"
    r")\b",
    re.IGNORECASE,
)

_MOTS_CHAMP_ADJACENT = re.compile(
    r"(?<![A-Za-zÀ-ÿ])(?:date|adresse|tél|tel|fax|rib|iban|r\.i\.b|agence"
    r"|[eé]ch[eé]ance|[eé]mission|emission|montant|tireur|tiré"
    r"|bénéficiaire|beneficiaire|domiciliation|signature|cachet|ville"
    r"|code\s+postal|banque|bank|numéro|numero|référence|reference|no"
    r"|payable|titulaire|compte|agence)(?![A-Za-zÀ-ÿ])"
    r"|n°",
    re.IGNORECASE,
)

_PREFIXES_LABELS = re.compile(
    r"^(?:soci[eé]t[eé]|sarl|sa|suarl|sas|eurl|snc|gie|m|mr|mme|dr)\s*[:\-]\s*",
    re.IGNORECASE,
)

# ──────────────────────────────────────────────────────────────────────
# PATTERNS DÉTECTION TYPE DOCUMENT
# ──────────────────────────────────────────────────────────────────────

_PATTERNS_CHEQUE = [
    r"\bch[eèé]que\b",
    r"\bpayez\s+(?:contre\s+)?(?:ce\s+)?ch[eèé]que\b",
    r"\bp[ao]ye[rz]\b",
    r"\bsomme\s+de\b",
    r"\bà\s+l[''']ordre\s+de\b",
    r"\bnon\s+endossable\b",
    r"\btunis\s*,?\s*le\b",
    r"\bcmc\s*7\b",
    r"\b\d{2}\s+\d{3}\s+\d{4}\s+\d{3}\s+\d{2}\b",
]

_PATTERNS_TRAITE = [
    r"\blettre\s*de\s*change\b",
    r"\btraite\b",
    r"\beffet\s*de\s*commerce\b",
    r"\btireur\b",
    r"\btiré\b",
    r"\bdomiciliataire\b",
    r"\bvaleur\s+en\s+compte\b",
    r"\baval\b",
    r"\bbon\s*pour\s*aval\b",
    r"\bveuillez\s+payer\b",
    r"\béch[eé]ance\b",
    r"\bT[-\s]?\d{4}[-\s]\d{2,6}\b",
    r"\bLC\s*N[°o]?\b",
    r"\bordre\s+de\s+paiement\b",
    r"\bbill\s+of\s+exchange\b",
]

# ──────────────────────────────────────────────────────────────────────
# MAPPING OCR → FIELDNAMES FRAPPE
# ──────────────────────────────────────────────────────────────────────

_MAPPING_FRAPPE_CHEQUE = {
    "numero_cheque":    "reference_no",
    "date_cheque":      "reference_date",
    "cheque_date":      "reference_date",
    "amount":           "paid_amount",
    "banque":           "bank",
    "beneficiaire":     "party",
    "titulaire_compte": "account_holder_name",
    "rib":              "bank_account",
}

_MAPPING_FRAPPE_TRAITE = {
    "numero_traite":  "reference_no",
    "date_echeance":  "reference_date",
    "amount":         "paid_amount",
    "tire":           "bank",
    "tireur":         "party",
    "beneficiaire":   "custom_beneficiary",
    "domiciliation":  "custom_domiciliation",
    "date_emission":  "custom_issue_date",
    "rib":            "custom_rib_tire",
}

# ──────────────────────────────────────────────────────────────────────
# MONTANT EN LETTRES
# ──────────────────────────────────────────────────────────────────────

_UNITES = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
    "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
    "seize": 16, "dix-sept": 17, "dix sept": 17, "dix-huit": 18,
    "dix huit": 18, "dix-neuf": 19, "dix neuf": 19, "vingt": 20,
    "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
    "soixante-dix": 70, "soixante dix": 70, "quatre-vingt": 80,
    "quatre vingt": 80, "quatre-vingts": 80, "quatre-vingt-dix": 90,
    "quatre vingt dix": 90,
}
_MULTIPLICATEURS = {
    "cent": 100, "cents": 100, "mille": 1000,
    "million": 1_000_000, "millions": 1_000_000_000,
    "milliard": 1_000_000_000, "milliards": 1_000_000_000,
}


def _lettres_vers_chiffre(texte_lettres):
    s = re.sub(r"[-—–]", " ", (texte_lettres or "").lower().strip())
    s = re.sub(r"\s+", " ", s).strip()
    mots = s.split()
    total = courant = 0
    i = 0
    while i < len(mots):
        mot = mots[i]
        bi = mot + " " + mots[i + 1] if i + 1 < len(mots) else ""
        tri = bi + " " + mots[i + 2] if i + 2 < len(mots) else ""
        if tri in _UNITES:
            courant += _UNITES[tri]; i += 3
        elif bi in _UNITES:
            courant += _UNITES[bi]; i += 2
        elif mot in _UNITES:
            courant += _UNITES[mot]; i += 1
        elif mot in ("et",):
            i += 1
        elif mot in _MULTIPLICATEURS:
            mult = _MULTIPLICATEURS[mot]
            if mult == 100:
                courant = (courant if courant > 0 else 1) * 100
                total += courant; courant = 0
            elif mult >= 1000:
                courant = (courant if courant > 0 else 1) * mult
                total += courant; courant = 0
            i += 1
        else:
            i += 1
    total += courant
    return total if total > 0 else None


def _extraire_montant_lettres(texte):
    if not texte:
        return None
    t = re.sub(r"\s+", " ", texte.lower().replace("\n", " "))
    m = re.search(
        r"(?:somme\s+(?:de|ae|d['''])\s*|montant\s+(?:en\s+lettres?\s*)?[:\-]?\s*|la\s+somme\s+de\s+)"
        r"((?:[a-zàâçéèêëîïôùûü\s\-]+?){1,30})"
        r"(?:\s*dinars?)",
        t, re.IGNORECASE,
    )
    if not m:
        _MOTS_LETTRES = (
            r"z[eé]ro|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf"
            r"|dix|onze|douze|treize|quatorze|quinze|seize"
            r"|dix[\s\-]sept|dix[\s\-]huit|dix[\s\-]neuf"
            r"|vingt|trente|quarante|cinquante|soixante"
            r"|quatre[\s\-]vingt|quatre[\s\-]vingts"
            r"|quatre[\s\-]vingt[\s\-]dix"
            r"|cents?|mille|millions?|milliards?"
        )
        m = re.search(
            r"\b((?:(?:" + _MOTS_LETTRES + r")(?:\s+et)?\s+){1,15}"
            r"(?:" + _MOTS_LETTRES + r"))\s+dinars?",
            t, re.IGNORECASE,
        )
    if not m:
        return None
    dinars = _lettres_vers_chiffre(m.group(1).strip())
    if dinars is None or dinars < 10:
        return None
    millimes = 0
    m2 = re.search(r"dinars?\s+et\s+(.*?)(?:millimes?|cent(?:imes?)?)\b", t, re.IGNORECASE)
    if m2:
        v = _lettres_vers_chiffre(m2.group(1).strip())
        if v is not None:
            millimes = v
    return round(dinars + millimes / 1000.0, 3)


# ──────────────────────────────────────────────────────────────────────
# PARSER MONTANT CHIFFRES
# ──────────────────────────────────────────────────────────────────────


def _parser_montant(val) -> float | None:
    if not val:
        return None
    s = re.sub(r"(?i)\s*(TND|DT|dinars?|millimes?|euros?|€)\s*", " ", str(val))
    s = s.strip("* ").strip()
    if not s:
        return None
    s = re.sub(r"[\s\u00A0\u202F]", "", s)
    m_en = re.match(r"^(\d{1,3}(?:,\d{3})+)(?:\.(\d{1,3}))?$", s)
    if m_en:
        entier = m_en.group(1).replace(",", "")
        dec = m_en.group(2) or "0"
        try:
            return float(entier + "." + dec) or None
        except ValueError:
            pass
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2:
            after = parts[1]
            if len(after) == 3 and after.isdigit():
                s = parts[0] + after if len(parts[0]) >= 4 else parts[0] + "." + after
            elif len(after) == 4 and after.isdigit() and len(parts[0]) <= 4:
                s = parts[0] + "." + after[1:]
            else:
                s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit():
            try:
                if int(parts[0]) >= 1000:
                    s = parts[0] + parts[1]
            except ValueError:
                pass
    try:
        v = float(s)
        return v if v > 0 else None
    except ValueError:
        return None


# ──────────────────────────────────────────────────────────────────────
# PRÉTRAITEMENT TEXTE OCR
# ──────────────────────────────────────────────────────────────────────


def _pretraiter_texte_ocr(texte: str) -> str:
    t = texte
    t = re.sub(r"[‐‑‒–—−]", "-", t)
    t = t.replace("／", "/").replace("⁄", "/")
    t = re.sub(r"(?<=[0-9/\-\.])O(?=[0-9/\-\.])", "0", t)
    t = re.sub(r"(?<=[0-9/\-\.])[lI](?=[0-9/\-\.])", "1", t)
    t = re.sub(r"(\d)\s+[Jl\|I](\d{3})\b", r"\1,\2", t)
    t = re.sub(r"\b(\d)\s(\d)(/\d{1,2}/\d{2,4})\b", r"\1\2\3", t)
    # Corrections garbles OCR fréquents sur traites tunisiennes
    t = re.sub(r"PANNEA(?:[\\|/IX'\u2019])?(?!\w)", "PANNEAUX", t)
    t = re.sub(r"TUN[Ii][Gg][Ii][Aa]", "TUNISIA", t, flags=re.IGNORECASE)
    t = re.sub(r"TU+W?N[I1][B8][T7]A[T7]", "TUNISIA", t, flags=re.IGNORECASE)
    t = re.sub(r"OLEO\s*TEC[A-Z]{0,4}(?:ING|N[GDQ0O])(?!\w)", "OLEO TECHNO", t, flags=re.IGNORECASE)
    return t


# ──────────────────────────────────────────────────────────────────────
# AMÉLIORATION IMAGE FLOUE — MULTI-PASSES
# ──────────────────────────────────────────────────────────────────────


def _ameliorer_image_floue(chemin_img: str):
    try:
        import cv2
        import numpy as np
        import pytesseract
        from PIL import Image as PILImage

        ext = os.path.splitext(chemin_img)[1].lower()
        if ext == ".pdf":
            from pdf2image import convert_from_path
            pages = convert_from_path(chemin_img, dpi=300, first_page=1, last_page=1)  # DPI 400→300, première page uniquement
            if not pages:
                return "", 0
            pil_img = pages[0].convert("RGB")
        else:
            pil_img = PILImage.open(chemin_img).convert("RGB")

        w, h = pil_img.size
        scale_factor = 1
        if w < 2000:
            scale_factor = min(2, max(1, int(2400 / w)))  # max 2× upscale; 1× si déjà entre 1200-2000px
            pil_img = pil_img.resize((w * scale_factor, h * scale_factor), PILImage.LANCZOS)

        img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        _gray_init = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        # Pas de fastNlMeansDenoisingColored (très lent) — GaussianBlur suffit
        score_ocr = 0

        hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)
        lower_blue = np.array([95, 40, 40])
        upper_blue = np.array([145, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
        kernel_conn = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask_blue = cv2.dilate(mask_blue, kernel_conn, iterations=1)

        lab = cv2.cvtColor(img_cv, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        img_cv = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

        gaussian = cv2.GaussianBlur(img_cv, (9, 9), 10.0)
        img_cv = cv2.addWeighted(img_cv, 1.8, gaussian, -0.8, 0)
        gaussian2 = cv2.GaussianBlur(img_cv, (0, 0), 2.0)
        img_cv = cv2.addWeighted(img_cv, 1.5, gaussian2, -0.5, 0)

        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        thr_adap = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
        )
        _, thr_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        textes = []
        try:
            _data_first = pytesseract.image_to_data(
                PILImage.fromarray(gray), lang="fra+eng+ara",
                config="--oem 1 --psm 6", output_type=pytesseract.Output.DICT,
            )
            _confs_f = [int(c) for c in _data_first["conf"] if str(c) != "-1" and int(c) > 0]
            _score_f = round(sum(_confs_f) / len(_confs_f), 1) if _confs_f else 0
            _txt_f = " ".join(w for w in _data_first["text"] if isinstance(w, str) and w.strip())
            _mots_f = len([m for m in _txt_f.split() if len(m) > 1])
            _mots_propres_f = len([
                m for m in _txt_f.split()
                if len(m) > 1 and re.match(r"^[A-Za-z0-9\u00C0-\u024F]{2,}$", m)
            ])
            textes.append((_score_f, _mots_f, _txt_f))
            # Early-exit si le premier appel est déjà bon (≥30 mots propres)
            if _mots_propres_f >= 30:
                return _txt_f, _score_f
        except Exception:
            pass

        # Fallback unique : thr_adap PSM 11 (sparse) si le premier était insuffisant
        try:
            _data_fb = pytesseract.image_to_data(
                PILImage.fromarray(thr_adap), lang="fra+eng+ara",
                config="--oem 1 --psm 11", output_type=pytesseract.Output.DICT,
            )
            _confs_fb = [int(c) for c in _data_fb["conf"] if str(c) != "-1" and int(c) > 0]
            _score_fb = round(sum(_confs_fb) / len(_confs_fb), 1) if _confs_fb else 0
            _txt_fb = " ".join(w for w in _data_fb["text"] if isinstance(w, str) and w.strip())
            _mots_fb = len([m for m in _txt_fb.split() if len(m) > 1])
            textes.append((_score_fb, _mots_fb, _txt_fb))
        except Exception:
            pass

        if not textes:
            return "", 0

        def crit(t):
            sc, mots, txt = t
            mots_propres = len([
                m for m in txt.split()
                if len(m) > 1 and re.match(r"^[A-Za-z0-9\u00C0-\u024F]{2,}$", m)
            ])
            return (sc / 100) * 0.45 + (min(mots_propres, 80) / 80) * 0.55

        best = max(textes, key=crit)
        return best[2], best[0]

    except Exception as e:
        _ocr_log(f"amélioration image floue échouée : {e}", "warning")
        return "", 0


def _tenter_amelioration_texte(chemin_img: str) -> str:
    txt, _ = _ameliorer_image_floue(chemin_img)
    return txt


# ──────────────────────────────────────────────────────────────────────
# ÉTAPE 1 — QUALITÉ
# ──────────────────────────────────────────────────────────────────────


def _evaluer_qualite(texte, score_ocr) -> bool:
    mots = [m for m in texte.split() if len(m) > 1]
    if len(mots) < 5:
        _ocr_log(f"qualite KO — mots={len(mots)} (<5)", "info")
        return True
    if score_ocr > 0 and score_ocr < 40:
        _ocr_log(f"qualite KO — score_ocr={score_ocr} (<40)", "info")
        return True
    nb_parasites = len(re.findall(r"[|\\/@#~^<>{}\[\]]{2,}", texte))
    if nb_parasites > 5:
        _ocr_log(f"qualite KO — parasites={nb_parasites} (>5)", "info")
        return True
    mots_propres = [m for m in mots if re.match(r"^[A-Za-z0-9\u00C0-\u024F]{2,}$", m)]
    ratio = len(mots_propres) / len(mots) if mots else 0
    if len(mots) > 5 and ratio < 0.35:
        _ocr_log(f"qualite KO — ratio_propres={ratio:.2f} (<0.35), mots={len(mots)}", "info")
        return True
    _ocr_log(
        f"qualite OK — score_ocr={score_ocr}, mots={len(mots)}, "
        f"propres={len(mots_propres)} ({ratio:.0%}), parasites={nb_parasites}", "debug",
    )
    return False


# ──────────────────────────────────────────────────────────────────────
# ÉTAPE 2 — IDENTIFICATION DU TYPE
# ──────────────────────────────────────────────────────────────────────


def _identifier_type_document(texte) -> tuple[str, float]:
    t = texte.lower()
    sc = sum(1 for p in _PATTERNS_CHEQUE if re.search(p, t, re.IGNORECASE))
    st = sum(1 for p in _PATTERNS_TRAITE if re.search(p, t, re.IGNORECASE))
    if sc == 0 and st == 0:
        return "inconnu", 0.0
    total = sc + st
    if sc >= st:
        return "cheque", round(sc / total, 3)
    return "traite", round(st / total, 3)


_PATTERNS_TYPE_DOC_ALT = {
    "facture": [
        r"\bfacture\b", r"\binvoice\b", r"\bn[°o]\s*facture\b",
        r"\bmontant\s+ttc\b", r"\btva\b.*\bht\b",
    ],
    "bon_livraison": [r"\bbon\s+de\s+livraison\b", r"\bb\.?l\.?\b", r"\blivraison\b"],
    "bon_commande": [
        r"\bbon\s+de\s+commande\b", r"\bcommande\s+n[°o]", r"\bpurchase\s+order\b",
    ],
    "devis": [r"\bdevis\b", r"\bproforma\b", r"\boffre\s+de\s+prix\b"],
    "nomenclature": [
        r"\bnomenclature\b", r"\bbom\b", r"\bcomposants?\b",
        r"\bfiche\s+nomenclature\b", r"\bbill\s+of\s+materials?\b",
    ],
    "fiche_article": [
        r"\bfiche\s+article\b", r"\bfiche\s+produit\b", r"\barticle\s*:\s*[A-Z0-9]",
        r"\btechnical\s+data\s+sheet\b", r"\bdata\s+sheet\b",
    ],
}


def _detecter_type_alternatif(texte: str) -> str | None:
    t = texte.lower()
    meilleur, max_sc = None, 0
    for typ, patterns in _PATTERNS_TYPE_DOC_ALT.items():
        sc = sum(1 for p in patterns if re.search(p, t, re.IGNORECASE))
        if sc > max_sc:
            meilleur, max_sc = typ, sc
    return meilleur if max_sc >= 1 else None


_LABELS_TYPE = {
    "cheque":        "chèque",
    "traite":        "traite",
    "facture":       "facture",
    "bon_livraison": "bon de livraison",
    "bon_commande":  "bon de commande",
    "devis":         "devis / proforma",
    "nomenclature":  "fiche nomenclature",
    "fiche_article": "fiche article",
    "inconnu":       "document non reconnu",
}


def _normaliser_payment_method(pm: str) -> str | None:
    if not pm:
        return None
    p = pm.lower().strip()
    if any(k in p for k in ("chèque", "cheque", "check", "chéque")):
        return "cheque"
    if any(k in p for k in ("traite", "lettre de change", "effet", "draft")):
        return "traite"
    return None


# ──────────────────────────────────────────────────────────────────────
# EXTRACTION DATES
# ──────────────────────────────────────────────────────────────────────

_MOIS_FR = {
    "janvier": "01", "février": "02", "fevrier": "02", "mars": "03",
    "avril": "04", "mai": "05", "juin": "06", "juillet": "07",
    "août": "08", "aout": "08", "septembre": "09", "octobre": "10",
    "novembre": "11", "décembre": "12", "decembre": "12",
}


def _extraire_dates_brutes(texte: str) -> list:
    pat = r"\d{1,2}\s*[\/\-\.]\s*\d{1,2}\s*[\/\-\.]\s*\d{2,4}"
    dates = []
    annee_max = datetime.now().year + 5
    for m in re.finditer(pat, texte):
        raw = re.sub(r"\s*([\/\-\.])\s*", r"\1", m.group(0).strip())
        unified = re.sub(r"[\/\-\.]", "/", raw)
        parts = unified.split("/")
        if len(parts) != 3:
            continue
        try:
            d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            continue
        y = 2000 + y if y < 100 else y
        if not (2000 <= y <= annee_max):
            continue
        try:
            dates.append(datetime.strptime(f"{d:02d}/{mo:02d}/{y:04d}", "%d/%m/%Y"))
        except ValueError:
            continue
    return dates


def _normaliser_date(val: str) -> str | None:
    if not val:
        return None
    val = val.strip()
    val = re.sub(r"\s*([\/\-\.])\s*", r"\1", val)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
        return val
    m_fr = re.match(
        r"(\d{1,2})\s+(" + "|".join(_MOIS_FR.keys()) + r")\s+(\d{4})",
        val, re.IGNORECASE,
    )
    if m_fr:
        dd = m_fr.group(1).zfill(2)
        mm = _MOIS_FR[m_fr.group(2).lower()]
        return f"{m_fr.group(3)}-{mm}-{dd}"
    for fmt in [
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d",
    ]:
        try:
            d = datetime.strptime(val, fmt)
            y = d.year + 2000 if d.year < 100 else d.year
            return f"{y}-{d.month:02d}-{d.day:02d}"
        except ValueError:
            continue
    return None


# ──────────────────────────────────────────────────────────────────────
# CORRECTION CONFUSIONS OCR DANS L'ANNÉE
# ──────────────────────────────────────────────────────────────────────

_OCR_DIGIT_CONFUSIONS: dict[str, list[str]] = {
    "0": ["6"], "6": ["0", "4", "5"], "8": ["6", "0", "3"],
    "1": ["7"], "7": ["1"], "5": ["6", "0", "4"],
    "4": ["9", "6"], "9": ["4", "0"], "3": ["8"], "2": ["7"],
}


def _corriger_annee_ocr(date_iso: str, doc_type: str = "cheque") -> tuple[str, bool]:
    if not date_iso:
        return date_iso, False
    if not isinstance(date_iso, str):
        try:
            date_iso = date_iso.strftime("%Y-%m-%d")
        except Exception:
            return str(date_iso), False
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_iso):
        return date_iso, False
    try:
        d_orig = datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        return date_iso, False

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    delta_mois = (d_orig - today).days / 30.44

    if doc_type == "traite":
        if -6 <= delta_mois <= 36:
            if 12 < delta_mois <= 36:
                _ocr_log(f"  corriger_annee_ocr traite: delta={delta_mois:.1f} → tentative correction {date_iso}", "info")
                year_str_t = str(d_orig.year)
                best_corr_t, best_corr_delta_t = None, abs(delta_mois)
                for i_t, ch_t in enumerate(year_str_t):
                    for alt_t in _OCR_DIGIT_CONFUSIONS.get(ch_t, []):
                        cand_year_str = year_str_t[:i_t] + alt_t + year_str_t[i_t + 1:]
                        try:
                            cand_year = int(cand_year_str)
                            cand_date = d_orig.replace(year=cand_year)
                            c_delta = (cand_date - today).days / 30.44
                            _ocr_log(f"    candidat {cand_year_str}: delta={c_delta:.1f}", "info")
                            if -6 <= c_delta <= 36 and abs(c_delta) < best_corr_delta_t:
                                best_corr_t, best_corr_delta_t = cand_date, abs(c_delta)
                        except (ValueError, OverflowError):
                            continue
                if best_corr_t:
                    return best_corr_t.strftime("%Y-%m-%d"), True
            return date_iso, False

        if 36 < delta_mois <= 60:
            year_str_t = str(d_orig.year)
            for i_t, ch_t in enumerate(year_str_t):
                for alt_t in _OCR_DIGIT_CONFUSIONS.get(ch_t, []):
                    cand_year_str = year_str_t[:i_t] + alt_t + year_str_t[i_t + 1:]
                    try:
                        cand_year = int(cand_year_str)
                        cand_date = d_orig.replace(year=cand_year)
                        c_delta = (cand_date - today).days / 30.44
                        if -6 <= c_delta <= 36:
                            return cand_date.strftime("%Y-%m-%d"), True
                    except (ValueError, OverflowError):
                        continue
    else:
        if -12 <= delta_mois <= 36:
            return date_iso, False

    is_expiry_zone = -36 <= delta_mois < -12
    valid_min = -12 if is_expiry_zone else -18
    valid_max = 12 if is_expiry_zone else 24

    year_str = str(d_orig.year)
    best_date = None
    best_delta = float("inf")

    for i, ch in enumerate(year_str):
        for alt in _OCR_DIGIT_CONFUSIONS.get(ch, []):
            candidate_year_str = year_str[:i] + alt + year_str[i + 1:]
            try:
                candidate_year = int(candidate_year_str)
                candidate_date = d_orig.replace(year=candidate_year)
            except (ValueError, OverflowError):
                continue
            c_delta = (candidate_date - today).days / 30.44
            if valid_min <= c_delta <= valid_max:
                dist = abs(c_delta)
                if dist < best_delta:
                    best_date = candidate_date
                    best_delta = dist

    if best_date:
        return best_date.strftime("%Y-%m-%d"), True
    return date_iso, False


def _anciennete_mois(date_doc) -> float:
    return (datetime.now() - date_doc).days / 30.44


# ──────────────────────────────────────────────────────────────────────
# UTILITAIRES EXTRACTION
# ──────────────────────────────────────────────────────────────────────


def _tronquer_au_premier_champ_adjacent(valeur: str) -> str:
    _SUFFIXES_PROTEGES = re.compile(
        r"\b(?:TUNISIA|TUNISIE|INTERNATIONAL|INDUSTRIES|PANNEAUX|"
        r"ACCESSORIES|EQUIPEMENTS|SERVICES|REPARATION|"
        r"TECHNOLOGY|TECHNO|TRADING|GROUP|HOLDING|LEASING)\b",
        re.IGNORECASE,
    )
    if re.match(r"^[A-Z]{2,5}$", valeur.strip()):
        return valeur.strip()
    # Trouver la position de fin du dernier suffixe protégé
    last_protected_end = 0
    for m in _SUFFIXES_PROTEGES.finditer(valeur):
        last_protected_end = max(last_protected_end, m.end())
    # Tronquer au premier mot-champ qui apparaît APRÈS le dernier suffixe protégé
    starts = []
    for m in _MOTS_CHAMP_ADJACENT.finditer(valeur):
        if m.start() > 0 and m.start() >= last_protected_end:
            starts.append(m.start())
    return valeur[:min(starts)].strip() if starts else valeur.strip()


def _nettoyer_nom_entite(valeur: str) -> str:
    if not valeur:
        return ""
    blacklist = ["tick", "ate", "pea", "giant", "fruit"]
    if any(word in valeur.lower() for word in blacklist):
        return ""
    valeur = re.sub(r"[^A-Za-zÀ-ÿ0-9\s]", " ", valeur).strip().upper()
    return " ".join(valeur.split())


def _extraire_champ_avec_confiance(
    texte: str, patterns: list, nom_champ: str
) -> tuple[str, float, bool]:
    best_valeur, best_conf = "", 0.0
    for i_pat, pattern in enumerate(patterns):
        for match in re.finditer(pattern, texte, re.IGNORECASE | re.MULTILINE):
            try:
                valeur = match.group(1).strip()
            except IndexError:
                valeur = match.group(0).strip()
            valeur = _tronquer_au_premier_champ_adjacent(valeur)
            conf = 0.6
            if nom_champ == "montant":
                if re.search(r"\d", valeur):
                    conf += 0.3
            elif nom_champ in ("date_emission", "date_echeance"):
                if re.match(r"\d{2}[\/\-]\d{2}[\/\-]\d{4}", valeur):
                    conf += 0.35
            elif nom_champ in ("tireur", "beneficiaire", "tire"):
                if len(valeur.split()) >= 2:
                    conf += 0.25
                # Bonus de priorité : les premiers patterns sont les plus spécifiques
                # (label explicite, forme juridique). Les patterns génériques (tout-caps,
                # "ordre de paiement à") sont en fin de liste → bonus décroissant.
                conf += max(0.0, 0.10 - i_pat * 0.02)
            if len(valeur) > 6:
                conf += 0.1
            conf = min(conf, 0.99)
            if conf > best_conf:
                best_valeur, best_conf = valeur, conf
    return best_valeur, best_conf, (best_conf < 0.65)


def _valider_nom_partie(valeur: str, champ: str) -> str | None:
    if not valeur:
        return None
    v = valeur.strip()
    v = _tronquer_au_premier_champ_adjacent(v)
    if not v:
        return None
    if v.lower().strip() in _MOTS_INTERDITS_PARTIE:
        return None
    if _BRUIT_FORMULAIRE.search(v):
        return None
    if len(v) > 80:
        return None
    if re.search(r"[()\[\]|\\<>{}]", v):
        return None
    lettres = re.sub(r"[^A-Za-zÀ-ÿ]", "", v)
    if len(lettres) < 2:
        return None
    if len(re.findall(r"\d", v)) >= 5:
        return None
    nb_bruit = len(re.findall(r"[|\\@#~^<>{}\[\]]{1}", v))
    if nb_bruit > 2:
        return None
    nb_total_no_space = len(re.sub(r"\s", "", v))
    if nb_total_no_space > 0 and len(lettres) / nb_total_no_space < 0.50:
        return None
    mots = v.split()
    if len(mots) >= 2:
        mots_courts = sum(1 for m in mots if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", m)) <= 2)
        ratio_courts = mots_courts / len(mots)
        lettres_maj = len(re.findall(r"[A-ZÀ-Ü]", v))
        if len(lettres) >= 3 and lettres_maj / max(len(lettres), 1) >= 0.70:
            if ratio_courts >= 0.80:
                return None
        elif ratio_courts >= 0.60:
            return None
    if len(mots) <= 1 and v.lower() in {
        "nom", "raison", "sociale", "societe", "société",
        "tireur", "tiré", "beneficiaire", "bénéficiaire",
    }:
        return None
    if champ == "tire":
        v_low = v.lower()
        for banque in _BANQUES_TN_PREFIXES:
            if banque in v_low:
                for b in _BANQUES_TN:
                    if b.lower() in v_low:
                        return b
        # Reject garbled/noise values: too short or all-lowercase (not a bank abbreviation)
        if len(v) < 3 or v == v.lower():
            return None
        return v[:50].strip()
    if champ in ("tireur", "beneficiaire"):
        mots_v2 = v.split()
        nb_mots_mixtes = 0
        for mot_chk in mots_v2:
            alpha_chk = re.sub(r"[^A-Za-zÀ-ÿ]", "", mot_chk)
            if len(alpha_chk) >= 3:
                is_allcaps = alpha_chk == alpha_chk.upper()
                is_titlecase = alpha_chk[0].isupper() and alpha_chk[1:] == alpha_chk[1:].lower()
                if not is_allcaps and not is_titlecase:
                    nb_mots_mixtes += 1
        if len(mots_v2) > 0 and nb_mots_mixtes / len(mots_v2) > 0.40:
            _ocr_log(f"  {champ} REJETÉ casse mixte OCR: {v!r}", "info")
            return None
    if champ in ("beneficiaire", "tireur", "titulaire_compte"):
        v_clean = re.sub(r"(?<![A-Za-zÀ-ÿ])[a-z](?![A-Za-zÀ-ÿ])", "", v).strip()
        v_clean = re.sub(r"\s{2,}", " ", v_clean).strip()
        if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", v_clean)) >= 2:
            v = v_clean
    if champ in ("tireur", "beneficiaire"):
        mots_v = v.split()
        if (
            len(mots_v) >= 3
            and re.match(r"^[A-ZÀ-Ü]{2,3}$", mots_v[0])
            and all(re.match(r"^[A-ZÀ-Ü]{4,}$", w) for w in mots_v[1:3])
        ):
            v_sans_prefix = " ".join(mots_v[1:])
            if len(v_sans_prefix) >= 6:
                v = v_sans_prefix
    if champ == "titulaire_compte":
        all_caps_seqs = re.findall(r"[A-ZÀ-Ü]{2,}(?:\s+[A-ZÀ-Ü]{2,})+", v)
        if all_caps_seqs:
            best = max(all_caps_seqs, key=len)
            if len(best) >= 6 and len(best) < len(v):
                best = re.sub(r"(\s+[A-ZÀ-Ü]{1,3}){1,2}$", "", best).strip()
                if len(best) >= 6:
                    v = best
    # Normaliser les sauts de ligne internes → espace (ex: "OLEO TECHNO\nTUNISIA")
    v = re.sub(r"\n+", " ", v)
    v = re.sub(r" {2,}", " ", v).strip()
    return v[:70].strip()


# ──────────────────────────────────────────────────────────────────────
# FUZZY MATCH FRAPPE PARTIES
# ──────────────────────────────────────────────────────────────────────


def _fuzzy_match_frappe_parties(texte_ocr: str) -> str | None:
    try:
        from rapidfuzz import fuzz
        import frappe

        noms_frappe: list[str] = []
        try:
            noms_frappe += [r[0] for r in frappe.db.sql("SELECT name FROM `tabSupplier` WHERE disabled=0 LIMIT 1000")]
        except Exception:
            pass
        try:
            noms_frappe += [r[0] for r in frappe.db.sql("SELECT name FROM `tabCustomer` WHERE disabled=0 LIMIT 1000")]
        except Exception:
            pass

        if not noms_frappe:
            return None

        texte_norm = re.sub(r"[^A-Za-zÀ-ÿ0-9 ]", " ", texte_ocr).upper().strip()
        tokens_ocr = [t for t in texte_norm.split() if len(t) >= 3]
        if not tokens_ocr:
            return None

        scores: dict[str, tuple[float, float, int]] = {}
        for nom in noms_frappe:
            nom_upper = nom.upper()
            nom_alpha = re.sub(r"[^A-ZÀ-Ü0-9]", "", nom_upper)
            if not nom_alpha:
                continue
            best_tok_sc = 0.0
            for tok in tokens_ocr:
                if tok in nom_upper or tok in nom_alpha:
                    coverage = len(tok) / len(nom_alpha) * 100
                    if coverage > best_tok_sc:
                        best_tok_sc = coverage
            fuzzy_sc = fuzz.token_set_ratio(texte_norm, nom_upper)
            combined = best_tok_sc * 0.7 + fuzzy_sc * 0.3
            if best_tok_sc >= 30 or fuzzy_sc >= 60:
                scores[nom] = (combined, best_tok_sc, fuzzy_sc)

        if not scores:
            return None

        best = max(scores, key=lambda n: scores[n][0])
        combined, tok_sc, fuzzy_sc = scores[best]
        _ocr_log(f"  fuzzy match: best={best!r} tok_sc={tok_sc:.1f} fuzzy_sc={fuzzy_sc:.1f}", "info")

        if tok_sc >= 40 or (fuzzy_sc >= 70 and tok_sc > 0):
            return best
        return None

    except Exception as e:
        _ocr_log(f"_fuzzy_match_frappe_parties échoué: {e}", "warning")
        return None


# ──────────────────────────────────────────────────────────────────────
# MAPPING VERS FRAPPE
# ──────────────────────────────────────────────────────────────────────


def _mapper_frappe(form_fields: dict, mapping: dict) -> dict:
    champs_remplis = {}
    for cle_ocr, fieldname in mapping.items():
        valeur = form_fields.get(cle_ocr)
        if valeur is None or valeur == "":
            continue
        if isinstance(valeur, float) and valeur == 0.0:
            continue
        champs_remplis[fieldname] = valeur
    if form_fields.get("amount") and form_fields["amount"] > 0:
        champs_remplis["paid_amount"] = form_fields["amount"]
    return champs_remplis


# ──────────────────────────────────────────────────────────────────────
# MD5 IMAGE
# ──────────────────────────────────────────────────────────────────────


def _md5_image(chemin_img: str) -> str | None:
    try:
        h = hashlib.md5()
        with open(chemin_img, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────
# CHAMPS PARTIES (ensemble partagé)
# ──────────────────────────────────────────────────────────────────────

_CHAMPS_PARTIES = {
    "tireur", "tire", "beneficiaire", "domiciliation",
    "banque", "titulaire_compte",
}