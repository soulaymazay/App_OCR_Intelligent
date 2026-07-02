# -*- coding: utf-8 -*-
"""
segmenter.py — Groupe Bayoudh Metal
Segmentation du texte OCR en trois zones : entete / corps / pied.
+ Extraction intégrée des données de chaque zone.

Deux stratégies (utilisées en cascade) :
  1. bbox PaddleOCR  : segmentation par position Y sur la page (prioritaire)
  2. Ancres textuelles : segmentation par mots-clés regex (fallback)

Aucune dépendance supplémentaire requise.
"""

import re


# ─────────────────────────────────────────────────────────────────────
# ANCRES TEXTUELLES
# ─────────────────────────────────────────────────────────────────────

_ANCRES_CORPS = [
    r"d[eé]signation\s*[\|;]?\s*qt[eé]",
    r"r[eé]f[eé]rence\s*[\|;]?\s*article",
    r"code\s*article\s*[\|;]?\s*lib[eé]ll[eé]",
    r"n[°o]\s*[\|;]?\s*d[eé]signation\s*[\|;]?\s*quantit[eé]",
    r"article\s*[\|;]?\s*quantit[eé]\s*[\|;]?\s*prix",
]

_ANCRES_PIED = [
    r"total\s*h\.?t\.?",
    r"montant\s*h\.?t\.?",
    r"sous[-\s]?total",
    r"net\s*[àa]\s*payer",
    r"montant\s*t\.?t\.?c\.?",
    r"total\s*t\.?t\.?c\.?",
]


# ─────────────────────────────────────────────────────────────────────
# PATTERNS EXTRACTION CORPS
# ─────────────────────────────────────────────────────────────────────

_LIGNE_SEPARATEUR = re.compile(
    r'[\|;]\s*|\s{2,}|\t'
)

_PATTERN_REFERENCE = re.compile(
    r'\b([A-Z]{2,5}\d{3,8})\b'
)

_PATTERN_NOMBRE = re.compile(
    r'\b(\d{1,6}(?:[.,]\d{1,3})?)\b'
)

_PATTERN_UNITE = re.compile(
    r'\b(UN|U|KG|M|M2|M3|L|PCE|PCS|BOX)\b',
    re.IGNORECASE
)

_ENTETES_COLONNES = re.compile(
    r'^\s*(?:ref|référence|code|désignation|designation|'
    r'libellé|libelle|qté|quantité|qty|pu|prix|unitaire|'
    r'remise|total|montant|n°|no)\s*$',
    re.IGNORECASE
)


# ─────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────────────────────────────────

def _trouver_ancre(texte: str, ancres: list) -> int:
    """
    Retourne la position de la première ancre trouvée.
    Retourne -1 si aucune ancre trouvée.
    """
    positions = []
    for pattern in ancres:
        m = re.search(pattern, texte, re.IGNORECASE | re.MULTILINE)
        if m:
            positions.append(m.start())
    return min(positions) if positions else -1


def _nettoyer_nombre(val: str) -> float:
    try:
        return float(val.replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def _est_ligne_entete_tableau(ligne: str) -> bool:
    cols = _LIGNE_SEPARATEUR.split(ligne.strip())
    nb_entetes = sum(
        1 for c in cols
        if _ENTETES_COLONNES.match(c.strip())
    )
    return nb_entetes >= 2


def _est_ligne_vide(ligne: str) -> bool:
    return not ligne.strip()


# ─────────────────────────────────────────────────────────────────────
# STRATÉGIE 1 — BBOX PADDLEOCR
# ─────────────────────────────────────────────────────────────────────

def segmenter_par_bbox(ocr_result: list, hauteur_page: int) -> dict:
    """
    Segmente le résultat PaddleOCR en trois zones selon la position Y.

    Args:
        ocr_result   : résultat brut PaddleOCR
                       [[ [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], ("texte", score) ], ...]
        hauteur_page : hauteur totale de l'image en pixels

    Returns:
        {"entete": str, "corps": str, "pied": str}
    """
    entete_lignes = []
    corps_lignes  = []
    pied_lignes   = []

    seuil_corps = hauteur_page * 0.30   # 0%  → 30%  = entête
    seuil_pied  = hauteur_page * 0.75   # 30% → 75%  = corps
                                        # 75% → 100% = pied

    for ligne in ocr_result:
        if not ligne:
            continue
        bbox, (texte, score) = ligne[0], ligne[1]

        # Centre Y de la bbox
        y_centre = (bbox[0][1] + bbox[2][1]) / 2

        if y_centre < seuil_corps:
            entete_lignes.append(texte)
        elif y_centre < seuil_pied:
            corps_lignes.append(texte)
        else:
            pied_lignes.append(texte)

    return {
        "entete": "\n".join(entete_lignes),
        "corps":  "\n".join(corps_lignes),
        "pied":   "\n".join(pied_lignes),
    }


# ─────────────────────────────────────────────────────────────────────
# STRATÉGIE 2 — ANCRES TEXTUELLES (fallback)
# ─────────────────────────────────────────────────────────────────────

def segmenter_par_ancres(texte: str) -> dict:
    """
    Segmente le texte OCR brut en trois zones via des ancres regex.
    Utilisé quand les bbox ne sont pas disponibles
    (Tesseract, Claude Vision).

    Args:
        texte : texte brut complet sorti de l'OCR

    Returns:
        {"entete": str, "corps": str, "pied": str}
    """
    pos_corps = _trouver_ancre(texte, _ANCRES_CORPS)
    pos_pied  = _trouver_ancre(texte, _ANCRES_PIED)

    # Cas : aucune ancre trouvée → tout dans entête
    if pos_corps == -1 and pos_pied == -1:
        return {"entete": texte, "corps": "", "pied": ""}

    # Cas : corps trouvé mais pas pied
    if pos_corps != -1 and pos_pied == -1:
        return {
            "entete": texte[:pos_corps],
            "corps":  texte[pos_corps:],
            "pied":   "",
        }

    # Cas : pied trouvé mais pas corps
    if pos_corps == -1 and pos_pied != -1:
        return {
            "entete": texte[:pos_pied],
            "corps":  "",
            "pied":   texte[pos_pied:],
        }

    # Sécurité : si pied détecté avant corps → inverser
    if pos_pied < pos_corps:
        pos_corps, pos_pied = pos_pied, pos_corps

    return {
        "entete": texte[:pos_corps],
        "corps":  texte[pos_corps:pos_pied],
        "pied":   texte[pos_pied:],
    }


# ─────────────────────────────────────────────────────────────────────
# EXTRACTION ENTÊTE
# ─────────────────────────────────────────────────────────────────────

def extraire_entete(texte_entete: str) -> dict:
    """
    Retourne le texte entête brut — l'extraction détaillée
    est faite par header_extractor.py.
    """
    return {
        "texte":      texte_entete,
        "nb_lignes":  len([l for l in texte_entete.split("\n") if l.strip()]),
    }


# ─────────────────────────────────────────────────────────────────────
# EXTRACTION CORPS
# ─────────────────────────────────────────────────────────────────────

def _parser_ligne_article(ligne: str) -> dict | None:
    """
    Tente de parser une ligne du corps comme ligne article.
    Retourne un dict ou None si la ligne n'est pas un article.
    """
    ligne = ligne.strip()
    if not ligne or len(ligne) < 5:
        return None

    if _est_ligne_entete_tableau(ligne):
        return None

    cols = [c.strip() for c in _LIGNE_SEPARATEUR.split(ligne) if c.strip()]

    if len(cols) < 2:
        return None

    result = {
        "reference":     "",
        "designation":   "",
        "quantite":      0.0,
        "prix_unitaire": 0.0,
        "total_ligne":   0.0,
        "unite":         "",
    }

    nombres = []
    textes  = []

    for col in cols:
        m_ref = _PATTERN_REFERENCE.match(col)
        if m_ref and not result["reference"]:
            result["reference"] = m_ref.group(1)
            continue

        m_unite = _PATTERN_UNITE.fullmatch(col)
        if m_unite:
            result["unite"] = col.upper()
            continue

        m_nb = _PATTERN_NOMBRE.fullmatch(col)
        if m_nb:
            nombres.append(_nettoyer_nombre(col))
            continue

        if len(col) >= 3 and not col.isdigit():
            textes.append(col)

    if textes:
        result["designation"] = textes[0]

    # Heuristique : total > PU > qté
    if len(nombres) >= 3:
        nombres_tries = sorted(nombres, reverse=True)
        result["total_ligne"]   = nombres_tries[0]
        result["prix_unitaire"] = nombres_tries[1]
        result["quantite"]      = nombres_tries[2]
    elif len(nombres) == 2:
        result["prix_unitaire"] = nombres[0]
        result["quantite"]      = nombres[1]
    elif len(nombres) == 1:
        result["quantite"] = nombres[0]

    if (result["designation"] or result["reference"]) and nombres:
        return result

    return None


def extraire_corps(texte_corps: str) -> dict:
    """
    Extrait toutes les lignes articles depuis le segment corps.

    Args:
        texte_corps : texte du segment corps

    Returns:
        {"lignes": [...], "nb_lignes": int}
    """
    if not texte_corps or not texte_corps.strip():
        return {"lignes": [], "nb_lignes": 0}

    lignes_doc      = texte_corps.split("\n")
    lignes_articles = []

    for ligne in lignes_doc:
        if _est_ligne_vide(ligne):
            continue
        article = _parser_ligne_article(ligne)
        if article:
            lignes_articles.append(article)

    return {
        "lignes":    lignes_articles,
        "nb_lignes": len(lignes_articles),
    }


# ─────────────────────────────────────────────────────────────────────
# EXTRACTION PIED
# ─────────────────────────────────────────────────────────────────────

def extraire_pied(texte_pied: str) -> dict:
    """
    Extrait les totaux depuis le segment pied.

    Returns:
        {"montant_ht": float, "tva": float,
         "montant_ttc": float, "texte": str}
    """
    pied = {
        "montant_ht":  0.0,
        "tva":         0.0,
        "montant_ttc": 0.0,
        "texte":       texte_pied,
    }

    if not texte_pied:
        return pied

    patterns = {
        "montant_ht": [
            r"(?:montant\s*h\.?t\.?|total\s*h\.?t\.?|hors\s*taxe)"
            r"\s*[:\-]?\s*([\d\s.,]+)",
        ],
        "tva": [
            r"(?:tva|t\.v\.a\.?)\s*(?:\(?\d+%\)?)?\s*[:\-]?\s*([\d\s.,]+)",
        ],
        "montant_ttc": [
            r"(?:montant\s*t\.?t\.?c\.?|total\s*t\.?t\.?c\.?|net\s*[àa]\s*payer)"
            r"\s*[:\-]?\s*([\d\s.,]+)",
        ],
    }

    for champ, liste_patterns in patterns.items():
        for pattern in liste_patterns:
            m = re.search(pattern, texte_pied, re.IGNORECASE)
            if m:
                pied[champ] = _nettoyer_nombre(m.group(1))
                break

    return pied


# ─────────────────────────────────────────────────────────────────────
# FONCTION PRINCIPALE — CASCADE
# ─────────────────────────────────────────────────────────────────────

def segmenter(texte: str,
              ocr_result: list = None,
              hauteur_page: int = None) -> dict:
    """
    Point d'entrée unique.
    Segmente le texte ET extrait les données de chaque zone.

    Args:
        texte        : texte brut OCR complet
        ocr_result   : résultat PaddleOCR brut (optionnel)
        hauteur_page : hauteur image en pixels (optionnel)

    Returns:
        {
            "entete":  {"texte": str, "nb_lignes": int},
            "corps":   {"lignes": [...], "nb_lignes": int},
            "pied":    {"montant_ht": float, "tva": float,
                        "montant_ttc": float, "texte": str},
            "texte_utile": str   ← entête + pied pour header_extractor
        }
    """
    # ── Segmentation ──────────────────────────────────────────────────
    if ocr_result and hauteur_page:
        zones = segmenter_par_bbox(ocr_result, hauteur_page)
    else:
        zones = segmenter_par_ancres(texte)

    # ── Extraction par zone ───────────────────────────────────────────
    entete = extraire_entete(zones["entete"])
    corps  = extraire_corps(zones["corps"])
    pied   = extraire_pied(zones["pied"])

    return {
        "entete":      entete,
        "corps":       corps,
        "pied":        pied,
        "texte_utile": zones["entete"] + "\n" + zones["pied"],
    }