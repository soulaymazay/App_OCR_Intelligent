# -*- coding: utf-8 -*-
"""
bom_extractor.py - Groupe Bayoudh Metal
Extraction des champs Nomenclature (BOM) depuis un document imprimé.

Champs header extraits :
  item, item_name, company, quantity, uom, currency,
  rm_cost_as_per, routing, transfer_material_against,
  conversion_rate, is_active, is_default,
  scrap_percentage

Champs composants extraits (liste de dicts) :
  item_code, item_name, description, qty, uom,
  qty_per_unit, stock_uom, conversion_factor, rate
"""

import re

# ──────────────────────────────────────────────────────────────────────
# MAPPINGS
# ──────────────────────────────────────────────────────────────────────

# Mapping texte FR/EN → valeur ERPNext pour rm_cost_as_per
_RM_COST_MAP = {
    "valuation rate":           "Valuation Rate",
    "prix de revient standard": "Valuation Rate",
    "taux d'évaluation":        "Valuation Rate",
    "taux devaluation":         "Valuation Rate",
    "last purchase rate":       "Last Purchase Rate",
    "dernier prix d'achat":     "Last Purchase Rate",
    "dernier prix dachat":      "Last Purchase Rate",
    "price list":               "Price List",
    "liste de prix":            "Price List",
}

# Mapping texte FR/EN → valeur ERPNext pour transfer_material_against
_TRANSFER_MAP = {
    "work order":               "Work Order",
    "ordre de fabrication":     "Work Order",
    "contre ordre de fabrication": "Work Order",
    "job card":                 "Job Card",
    "fiche de travail":         "Job Card",
}

# UDM : normalisation texte → nom ERPNext
_UOM_NORMALIZE = {
    "kilogramme": "Kg", "kg": "Kg", "kilo": "Kg",
    "gramme": "g", "gr": "g",
    "mètre": "m", "metre": "m", "ml": "m",
    "m²": "m²", "m2": "m²", "mètre carré": "m²",
    "m³": "m³", "m3": "m³",
    "litre": "L", "liter": "L", "lt": "L",
    "unité": "Unité", "unite": "Unité", "nos": "Unité",
    "pièce": "Unité", "piece": "Unité", "pcs": "Unité", "pce": "Unité",
    "l": "L",
}


# ──────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ──────────────────────────────────────────────────────────────────────

def extraire_champs_bom(texte: str) -> dict:
    """
    Analyse le texte OCR d'un document Nomenclature (BOM) et retourne
    un dict avec :
      champs      → dict header fieldname → valeur
      composants  → liste de dicts ligne composant
      confiances  → dict fieldname → float [0,1]
      type_document → "nomenclature" | "inconnu"
    """
    if not texte or not texte.strip():
        return _resultat_vide()

    t = _normaliser(texte)
    lignes = t.splitlines()

    champs = {}
    confiances = {}

    # ── Header ───────────────────────────────────────────────────────
    _extraire_numero_bom(t, lignes, champs, confiances)
    _extraire_article(t, lignes, champs, confiances)
    _extraire_societe(t, lignes, champs, confiances)
    _extraire_quantite(t, lignes, champs, confiances)
    _extraire_uom(t, lignes, champs, confiances)
    _extraire_devise(t, lignes, champs, confiances)
    _extraire_rm_cost_as_per(t, lignes, champs, confiances)
    _extraire_routing(t, lignes, champs, confiances)
    _extraire_transfer_material(t, lignes, champs, confiances)
    _extraire_conversion_rate(t, lignes, champs, confiances)
    _extraire_scrap(t, lignes, champs, confiances)
    _extraire_flags(t, lignes, champs, confiances)

    # ── Composants ───────────────────────────────────────────────────
    composants = _extraire_composants(t, lignes)

    # ── Coûts résumés ─────────────────────────────────────────────────
    _extraire_couts(t, lignes, champs, confiances)

    # ── Détection type ────────────────────────────────────────────────
    signaux = [
        "nomenclature", "bom", "composants", "composant",
        "bill of materials", "bill of material",
        "matière première", "matiere premiere",
        "quantité produite", "quantite produite",
    ]
    type_doc = "nomenclature" if any(s in t.lower() for s in signaux) else "inconnu"
    if len([v for v in champs.values() if v]) >= 3:
        type_doc = "nomenclature"

    return {
        "champs":        champs,
        "composants":    composants,
        "confiances":    confiances,
        "type_document": type_doc,
    }


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS HEADER
# ──────────────────────────────────────────────────────────────────────

def _extraire_numero_bom(t, lignes, champs, confiances):
    """Extrait le numéro BOM, ex: BOM-0002-001"""
    m = re.search(r'\bBOM-\d{4}-\d{3,}\b', t, re.IGNORECASE)
    if m:
        champs["name"] = m.group(0).upper()
        confiances["name"] = 0.95
        return
    # Fallback : Nomenclature suivi d'un identifiant
    m = re.search(r'nomenclature\s+([A-Z0-9\-]{5,20})', t, re.IGNORECASE)
    if m:
        champs["name"] = m.group(1).upper()
        confiances["name"] = 0.70


def _extraire_article(t, lignes, champs, confiances):
    """Extrait le code et le nom de l'article fini"""
    # Pattern: "Article  0004 — Châssis Soudé"
    patterns = [
        r'article\s+([A-Z0-9]+)\s*[—\-–]+\s*(.+)',
        r'article\s*[:\-]\s*([A-Z0-9]+)\s*[—\-–]+\s*(.+)',
        r'item\s+([A-Z0-9]+)\s*[—\-–]+\s*(.+)',
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            champs["item"] = m.group(1).strip()
            champs["item_name"] = m.group(2).strip()[:80]
            confiances["item"] = 0.85
            confiances["item_name"] = 0.80
            return

    # Fallback: "Article: 0001" en début de ligne uniquement
    # re.MULTILINE + ^ évite de matcher "de l'Article" dans les en-têtes du tableau
    m = re.search(r'^article\s*[:\-]\s*([A-Z0-9]{2,12})', t, re.IGNORECASE | re.MULTILINE)
    if m:
        champs["item"] = m.group(1).strip()
        confiances["item"] = 0.60

    # Extraction du nom article — cherche la dernière occurrence
    # pour éviter de capturer "Nom de l'article" qui est aussi un en-tête de colonne du tableau
    if "item_name" not in champs:
        t_oneline = re.sub(r'\n+', ' ', t)
        for pat_nom in [
            r'nom\s+de\s+l.article\s*[:\|]?\s*(\S[^|]{1,79})',
            r'nom\s+article\s*[:\|]?\s*(\S[^|]{1,79})',
        ]:
            matches = list(re.finditer(pat_nom, t_oneline, re.IGNORECASE))
            if matches:
                val = matches[-1].group(1).strip()
                val = re.split(
                    r'\s{2,}|devise|taux|soci|description|nomenclature|is\s+stock|page\s+\d',
                    val, flags=re.IGNORECASE
                )[0].strip()
                if len(val) > 1 and not re.match(
                    r'^(is\s+stock|description|code\s+de|sr\b|nom\s+de)',
                    val, re.IGNORECASE
                ):
                    champs["item_name"] = val[:80]
                    confiances["item_name"] = 0.80
                    break


def _extraire_societe(t, lignes, champs, confiances):
    patterns = [
        r'soci[eé]t[eé]\s*[:\-]?\s*(Groupe\s+[A-Za-zÀ-ÿ0-9\s\-]+)',  # ← EN PREMIER
        r'soci[eé]t[eé]\s*[/\|]\s*groupe\s+(.+)',
        r'groupe\s*[:\-]?\s*(.+)',
        r'company\s*[:\-]?\s*(.+)',
        r'soci[eé]t[eé]\s*[:\-]?\s*(.+)',
    ]
    _STOP = re.compile(
        r'est\s+(actif|d[eé]faut)|udm|unit[eé]|quantit[eé]|devise|taux|routing|gamme|transfert|statut|nomenclature|bom',
        re.IGNORECASE
    )
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            val = m.group(1).strip().split('\n')[0].strip()
            stop_m = _STOP.search(val)
            if stop_m:
                val = val[:stop_m.start()].strip()
            val = re.sub(r'\s{2,}', ' ', val)[:80]
            if len(val) > 2:
                champs["company"] = val
                confiances["company"] = 0.80
                return

def _extraire_quantite(t, lignes, champs, confiances):
    """Extrait la quantité produite"""
    patterns = [
        r'quantit[eé]\s+produite\s+([\d\s,\.]+)',
        r'quantit[eé]\s*[:\-]\s*([\d\s,\.]+)',
        r'qty?\s+produit[e]?\s+([\d\s,\.]+)',
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            val = _parse_float(m.group(1))
            if val is not None and val > 0:
                champs["quantity"] = val
                confiances["quantity"] = 0.85
                return


def _extraire_uom(t, lignes, champs, confiances):
    """Extrait l'unité de mesure"""
    patterns = [
        r'udm\s+de\s+l.article\s*[:\-]?\s*(\S+)',   # ← AJOUTER EN PREMIER
        r'unit[eé]\s+de\s+mesure\s+(.+)',
        r'uom\s*[:\-]?\s*(.+)',
        r'udm\s*[:\-]?\s*(.+)',
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            val = m.group(1).strip().split('\n')[0].split()[0].strip()
            normalized = _normaliser_uom(val)
            champs["uom"] = normalized
            confiances["uom"] = 0.80
            return


def _extraire_devise(t, lignes, champs, confiances):
    m = re.search(r'devise\s*[:\-]?\s*([A-Z]{2,4})\b', t, re.IGNORECASE)
    if m:
        val = m.group(1).upper()
        # Blacklist des faux positifs
        if val not in ("NOM", "UDM", "QTE", "BOM", "OCR"):
            champs["currency"] = val
            confiances["currency"] = 0.90
            return
    for devise in ["TND", "EUR", "USD", "MAD", "GBP"]:
        if re.search(r'\b' + devise + r'\b', t.upper()):
            champs.setdefault("currency", devise)
            confiances.setdefault("currency", 0.65)
            break

def _extraire_rm_cost_as_per(t, lignes, champs, confiances):
    """Extrait la base de calcul du coût"""
    patterns = [
        r'prix\s+bas[eé]\s+sur\s+(.+)',
        r'rm\s+cost\s+as\s+per\s+(.+)',
        r'cost\s+as\s+per\s+(.+)',
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            val_raw = m.group(1).strip().split('\n')[0].strip().lower()
            val_raw = re.sub(r'\s+', ' ', val_raw)
            mapped = None
            for k, v in _RM_COST_MAP.items():
                if k in val_raw:
                    mapped = v
                    break
            if mapped:
                champs["rm_cost_as_per"] = mapped
                confiances["rm_cost_as_per"] = 0.85
            return


def _extraire_routing(t, lignes, champs, confiances):
    """Extrait la route de fabrication"""
    patterns = [
        r'gamme\s*\(routing\)\s+([\w\d\-_]+)',   # "Gamme (Routing) RT-CHASSIS-001"
        r'routing\s*[:\-]?\s*([\w\d\-_]+)',
        r'route\s*[:\-]?\s*([\w\d\-_]+)',
        r'gamme\s*[:\-]?\s*([\w\d\-_]+)',
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if len(val) > 2:
                champs["routing"] = val
                confiances["routing"] = 0.75
                return


def _extraire_transfer_material(t, lignes, champs, confiances):
    """Extrait le mode de transfert matériel"""
    patterns = [
        r'transfert\s+mat[eé]riel\s+(.+)',
        r'transfer\s+material\s*[:\-]?\s*(.+)',
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            val_raw = m.group(1).strip().split('\n')[0].strip().lower()
            val_raw = re.sub(r'\s+', ' ', val_raw)
            mapped = None
            for k, v in _TRANSFER_MAP.items():
                if k in val_raw:
                    mapped = v
                    break
            if mapped:
                champs["transfer_material_against"] = mapped
                confiances["transfer_material_against"] = 0.80
            return


def _extraire_conversion_rate(t, lignes, champs, confiances):
    """Extrait le taux de change"""
    patterns = [
        r'taux\s+de\s+change\s+([\d\s,\.]+)',
        r'conversion\s+rate\s*[:\-]?\s*([\d\s,\.]+)',
        r'taux\s+conversion\s*[:\-]?\s*([\d\s,\.]+)',
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            val = _parse_float(m.group(1))
            if val is not None and val > 0:
                champs["conversion_rate"] = val
                confiances["conversion_rate"] = 0.80
                return


def _extraire_scrap(t, lignes, champs, confiances):
    """Extrait le taux de perte/rebut"""
    patterns = [
        r'taux\s+de\s+perte\s+processus[^\d]*([\d\s,\.]+)\s*%',
        r'scrap\s*%\s*\)[^\d]*([\d\s,\.]+)\s*%',
        r'scrap\s*%?\s*[:\-]?\s*([\d\s,\.]+)\s*%',
        r'rebut\s*[:\-]?\s*([\d\s,\.]+)\s*%',
        r'perte\s*[:\-]?\s*([\d\s,\.]+)\s*%',
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            val = _parse_float(m.group(1))
            if val is not None and 0 <= val <= 100:
                champs["scrap_percentage"] = val
                confiances["scrap_percentage"] = 0.80
                return


def _extraire_flags(t, lignes, champs, confiances):
    """Extrait les booléens est_actif / est_défaut"""
    # Est Actif
    m = re.search(r'est\s+actif\s+(oui|non|yes|no)', t, re.IGNORECASE)
    if m:
        champs["is_active"] = 1 if m.group(1).lower() in ("oui", "yes") else 0
        confiances["is_active"] = 0.90
    elif re.search(r'\bactif\b', t, re.IGNORECASE):
        champs.setdefault("is_active", 1)
        confiances.setdefault("is_active", 0.60)

    # Est Défaut
    m = re.search(r'est\s+d[eé]faut\s+(oui|non|yes|no)', t, re.IGNORECASE)
    if m:
        champs["is_default"] = 1 if m.group(1).lower() in ("oui", "yes") else 0
        confiances["is_default"] = 0.90

    # Statut
    m = re.search(r'statut\s*[:\|]\s*actif', t, re.IGNORECASE)
    if m:
        champs.setdefault("is_active", 1)
        confiances.setdefault("is_active", 0.85)

    m = re.search(r'par\s+d[eé]faut', t, re.IGNORECASE)
    if m:
        champs.setdefault("is_default", 1)
        confiances.setdefault("is_default", 0.75)


def _extraire_couts(t, lignes, champs, confiances):
    """Extrait les coûts du résumé"""
    cost_map = [
        # Patterns avec nom de champ entre parenthèses (format PDF généré)
        (r'\(raw_material_cost\)[^\d]*([\d\s,\.]+)',  "raw_material_cost"),
        (r'\(operating_cost\)[^\d]*([\d\s,\.]+)',      "operating_cost"),
        (r'\(scrap_material_cost\)[^\d]*([\d\s,\.]+)', "scrap_material_cost"),
        (r'\(total_cost\)[^\d]*([\d\s,\.]+)',           "total_cost"),
        # Patterns texte FR/EN classiques (OCR varié : coût/cout/coat)
        (r'co[uûa][ût]?\s+mati[eè]re\s+premi[eè]re\s+([\d\s,\.]+)', "raw_material_cost"),
        (r"co[uûa][ût]?\s+d.exploitation\s+([\d\s,\.]+)",             "operating_cost"),
        (r'co[uûa][ût]?\s+mise\s+au\s+rebut\s+([\d\s,\.]+)',          "scrap_material_cost"),
        (r'co[uûa][ût]?\s+total\s+([\d\s,\.]+)',                       "total_cost"),
    ]
    for pat, field in cost_map:
        if field in champs:
            continue  # déjà trouvé par un pattern prioritaire
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            val = _parse_float(m.group(1))
            if val is not None:
                champs[field] = val
                confiances[field] = 0.75


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEUR COMPOSANTS (tableau)
# ──────────────────────────────────────────────────────────────────────

def _clean_item_code(raw: str) -> str:
    """
    Normalise un code article extrait par OCR :
      1. Supprime les préfixes minuscules parasites (ex: vVIS012 → VIS012)
      2. Met en majuscules
      3. Corrige la confusion O↔0 si des chiffres sont présents
    """
    code = re.sub(r'^[a-z]+', '', raw).upper()
    if re.search(r'\d', code):
        code = re.sub(r'O(?=O*\d)', '0', code)
        code = re.sub(r'(?<=\d)O', '0', code)
    return code


def _extraire_composants(t, lignes):
    composants = []

    debut_idx = None
    for i, ligne in enumerate(lignes):
        if re.search(r'composants?|bom\s+items?|bill\s+of\s+mat', ligne, re.IGNORECASE):
            debut_idx = i
            break
        if re.search(r'^#\s+code\s+nom', ligne, re.IGNORECASE):
            debut_idx = i
            break

    if debut_idx is None:
        section_lignes = lignes
    else:
        fin_idx = len(lignes)
        section_keywords = [
            "param[eè]tres de fabrication",
            "r[eé]sum[eé] des co[uû]ts",
            "manufacturing parameters",
            "cost summary",
            "op[eé]rations",
            "gamme de fabrication",
        ]
        for i in range(debut_idx + 1, len(lignes)):
            if any(re.search(p, lignes[i], re.IGNORECASE) for p in section_keywords):
                fin_idx = i
                break
        section_lignes = lignes[debut_idx:fin_idx]

    # ── Approche 1 : scan sur texte reconstitué (PDF ERPNext fragmente les lignes) ──
    texte_section = ' '.join(l.strip() for l in section_lignes if l.strip())

    pat_scan = re.compile(
        r'(\d+)\s+'
        r'([A-Za-z0-9\-]{2,15})\s+'
        r'([A-Za-zÀ-ÿ0-9\-/,\.]+(?:\s+[A-Za-zÀ-ÿ0-9\-/,\.]+)*?)\s+'
        r'(?:[A-Za-z0-9]{1,3}\s+)?'
        r'(?:[A-Za-zÀ-ÿ0-9\s\-/,\.]+?\s+)?'
        r'(\d+(?:[,\.]\d+)?)\s+'
        r'(Unité|Unit[eé]|Kg|m²|m³|m\b|L\b|g\b|[A-Z]{1,6})\s+'
        r'(\d+(?:[,\.]\d+)?)\s+'
        r'(Unité|Unit[eé]|Kg|m²|m³|m\b|L\b|g\b|[A-Z]{1,6})\s+'
        r'(\d+(?:[,\.]\d+)?)',
        re.UNICODE | re.IGNORECASE
    )

    for m in pat_scan.finditer(texte_section):
        composants.append({
            "idx":               int(m.group(1)),
            "item_code":         _clean_item_code(m.group(2)),
            "item_name":         m.group(3).strip(),
            "description":       m.group(3).strip(),
            "qty":               _parse_float(m.group(4)) or 1,
            "uom":               _normaliser_uom(m.group(5)),
            "qty_per_unit":      _parse_float(m.group(6)) or 1,
            "stock_uom":         _normaliser_uom(m.group(7)),
            "conversion_factor": _parse_float(m.group(8)) or 1,
            "rate":              0,
        })

    if composants:
        return composants

    # ── Approche 2 : fallback ligne par ligne ────────────────────────────────────
    pat_ligne = re.compile(
        r'^(\d+)\s+'
        r'([A-Za-z0-9\-]{3,15})\s+'
        r'([A-Za-zÀ-ÿ0-9\s\-/,\.]+?)\s+'
        r'([\d]+(?:[,\.]\d+)?)\s+'
        r'([A-Za-z0-9²³°/%]{1,8})\s+'
        r'([\d]+(?:[,\.]\d+)?)\s+'
        r'([A-Za-z0-9²³°/%]{1,8})\s+'
        r'([\d]+(?:[,\.]\d+)?)\s+'
        r'([\d\s,\.]+)$',
        re.UNICODE
    )

    pat_7col = re.compile(
        r'^(\d+)\s+'
        r'([A-Za-z0-9\-]{3,15})\s+'
        r'([A-Za-zÀ-ÿ0-9\s\-/,\.]+?)\s+'
        r'([\d]+(?:[,\.]\d+)?)\s+'
        r'([A-Za-z0-9²³°/%]{1,8})\s+'
        r'([\d]+(?:[,\.]\d+)?)\s+'
        r'([\d\s,\.]+)$',
        re.UNICODE
    )

    pat_simple = re.compile(
        r'^(\d+)\s+'
        r'([A-Za-z0-9\-]{3,15})\s+'
        r'(.+?)\s+'
        r'([\d]+(?:[,\.]\d+)?)\s+'
        r'([A-Za-z0-9²³°/%]{1,8})\s+'
        r'([\d\s,\.]+)$',
        re.UNICODE
    )

    for ligne in section_lignes:
        ligne = ligne.strip()
        if not ligne or len(ligne) < 10:
            continue

        m = pat_ligne.match(ligne)
        if m:
            composants.append({
                "idx":               int(m.group(1)),
                "item_code":         _clean_item_code(m.group(2).strip()),
                "item_name":         m.group(3).strip(),
                "description":       m.group(3).strip(),
                "qty":               _parse_float(m.group(4)) or 1,
                "uom":               _normaliser_uom(m.group(5).strip()),
                "qty_per_unit":      _parse_float(m.group(6)) or 1,
                "stock_uom":         _normaliser_uom(m.group(7).strip()),
                "conversion_factor": _parse_float(m.group(8)) or 1,
                "rate":              _parse_float(m.group(9)) or 0,
            })
            continue

        m = pat_7col.match(ligne)
        if m:
            composants.append({
                "idx":               int(m.group(1)),
                "item_code":         _clean_item_code(m.group(2).strip()),
                "item_name":         m.group(3).strip(),
                "description":       m.group(3).strip(),
                "qty":               _parse_float(m.group(4)) or 1,
                "uom":               _normaliser_uom(m.group(5).strip()),
                "qty_per_unit":      _parse_float(m.group(6)) or 1,
                "stock_uom":         _normaliser_uom(m.group(5).strip()),
                "conversion_factor": 1,
                "rate":              _parse_float(m.group(7)) or 0,
            })
            continue

        m = pat_simple.match(ligne)
        if m:
            composants.append({
                "idx":               int(m.group(1)),
                "item_code":         _clean_item_code(m.group(2).strip()),
                "item_name":         m.group(3).strip(),
                "description":       m.group(3).strip(),
                "qty":               _parse_float(m.group(4)) or 1,
                "uom":               _normaliser_uom(m.group(5).strip()),
                "qty_per_unit":      _parse_float(m.group(4)) or 1,
                "stock_uom":         _normaliser_uom(m.group(5).strip()),
                "conversion_factor": 1,
                "rate":              _parse_float(m.group(6)) or 0,
            })

    return composants

# ──────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ──────────────────────────────────────────────────────────────────────

def _normaliser(texte: str) -> str:
    texte = re.sub(r'\r\n', '\n', texte)
    texte = re.sub(r'\r',   '\n', texte)
    # Normaliser les tirets insécables et tirets em
    texte = texte.replace('\u2014', '—').replace('\u2013', '–')
    # Supprimer les caractères de contrôle sauf \n et \t
    texte = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', texte)
    # Corriger la confusion O→0 dans les codes article (ex: "ACIOO1" → "ACI001")
    # Remplace O par 0 dans les codes qui contiennent déjà au moins un chiffre
    def _fix_code_zeros(m):
        code = m.group(0)
        if re.search(r'\d', code):
            code = re.sub(r'O(?=O*\d)', '0', code)   # O suivi (d'autres O puis) d'un chiffre
            code = re.sub(r'(?<=\d)O', '0', code)    # O précédé d'un chiffre
        return code
    texte = re.sub(r'\b[A-Z][A-Z0-9\-]{2,14}\b', _fix_code_zeros, texte)
    return texte


def _parse_float(s) -> float:
    """Convertit une chaîne en float (format tunisien: virgule=décimale, point=milliers)"""
    if s is None:
        return None
    s = str(s).strip()
    s = re.sub(r'[^\d,\.]', '', s)
    if not s:
        return None
    # Si virgule présente : virgule = séparateur décimal
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def _normaliser_uom(uom: str) -> str:
    """Normalise une unité de mesure vers le nom ERPNext"""
    if not uom:
        return uom
    uom_l = uom.lower().strip()
    for k, v in _UOM_NORMALIZE.items():
        if uom_l == k or re.fullmatch(re.escape(k), uom_l):
            return v
    # Retourner tel quel si pas de correspondance (souvent ML, M², etc.)
    return uom.upper() if len(uom) <= 3 else uom


def _resultat_vide() -> dict:
    return {
        "champs":        {},
        "composants":    [],
        "confiances":    {},
        "type_document": "inconnu",
    }
