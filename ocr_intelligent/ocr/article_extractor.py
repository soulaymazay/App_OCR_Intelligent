# -*- coding: utf-8 -*-
"""
article_extractor.py - Groupe Bayoudh Metal
Extraction des champs Article depuis une fiche technique produit.

Champs extraits :
  - item_code        : Code article
  - item_name        : Nom de l'article
  - item_group       : Groupe d'article
  - stock_uom        : Unité de mesure par défaut
  - standard_rate    : Prix de vente standard
  - last_purchase_rate : Prix d'achat
  - description      : Description / spécifications techniques

v4 — Corrections majeures :
  - _normaliser_udm : plus de fallback "Nos" — retourne "" si non reconnu
  - _extraire_udm   : suppression du fallback "Unité" par défaut
  - _extraire_unites_avancees : filtrage strict des valeurs par défaut (0, 1.0, "Unité")
  - _extraire_groupe : filtre "CONS" et codes courts (< 5 chars)
  - _extraire_champs_physiques / _extraire_familles_statistiques : gardes renforcées
"""

import re


# ──────────────────────────────────────────────────────────────────────
# TABLES DE RÉFÉRENCE
# ──────────────────────────────────────────────────────────────────────

_GROUPES_CONNUS = [
    "Informatique", "Bureautique", "Électronique", "Mobilier",
    "Fournitures de bureau", "Consommables", "Pièces détachées",
    "Outillage", "Matières premières", "Produits finis",
    "Emballage", "Équipement", "Accessoires", "Câblage",
    "Réseau", "Sécurité", "Électricité", "Plomberie",
    "Mécanique", "Chimie", "Hygiène", "Alimentaire",
    "All Item Groups",
]

_MOTS_CLES_GROUPE = {
    "Informatique":       ["ordinateur", "pc ", "laptop", "notebook", "processeur", "cpu",
                           "ram", "disque dur", "ssd", "nvme", "carte mère", "gpu",
                           "carte graphique", "écran", "moniteur", "clavier", "souris",
                           "imprimante", "scanner", "usb", "hdmi", "vga"],
    "Réseau":             ["switch", "routeur", "router", "wifi", "ethernet", "rj45",
                           "fibre", "sfp", "access point", "borne wifi", "modem"],
    "Électronique":       ["arduino", "raspberry", "capteur", "sensor", "module",
                           "transistor", "condensateur", "résistance", "diode", "led",
                           "alimentation", "transformateur", "onduleur", "ups"],
    "Mobilier":           ["bureau", "chaise", "armoire", "étagère", "table", "caisson",
                           "classeur", "meuble"],
    "Fournitures de bureau": ["stylo", "crayon", "ramette", "papier", "agrafeuse",
                              "classeur", "pochette", "reliure", "enveloppe", "toner",
                              "cartouche", "ruban"],
    "Outillage":          ["perceuse", "visseuse", "meuleuse", "scie", "marteau",
                           "tournevis", "clé", "pince", "niveau", "mètre"],
    "Câblage":            ["câble", "cable", "fil", "gaine", "conduit", "prise",
                           "connecteur", "fiche", "cordon"],
    "Sécurité":           ["caméra", "alarme", "détecteur", "badge", "lecteur",
                           "contrôle d'accès", "surveillance", "dvr", "nvr"],
    "Consommables":       ["encre", "toner", "cartouche", "ruban", "étiquette",
                           "papier thermique", "film", "colle", "lubrifiant"],
    "Électricité":        ["disjoncteur", "fusible", "tableau", "câble électrique",
                           "prise électrique", "interrupteur", "contacteur", "relais"],
}

_UDM_MAP = {
    "Unité": ["unité", "unite", "unit", "un", "u", "ea", "each",
              "nos", "pce", "pcs", "pièce", "piece", "qté", "qte"],
    "Kg":   ["kg", "kilogramme", "kilo"],
    "g":    [r"\bg\b", "gramme", "gr"],
    "m":    [r"\bm\b", "mètre", "metre", "ml", "mètre linéaire"],
    "m2":   ["m²", "m2", "mètre carré", "metre carre"],
    "m3":   ["m³", "m3", "mètre cube"],
    "L":    [r"\bl\b", "litre", "liter"],
    "Box":  ["box", "boîte", "boite", "bte", "bt"],
    "Pack": ["pack", "lot", "set"],
    "Pair": ["paire", "pair", "pr"],
    "Roll": ["rouleau", "roll", "rl"],
    "Doz":  ["douzaine", "doz", "dozen"],
}


# ──────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ──────────────────────────────────────────────────────────────────────

def extraire_champs_article(texte: str) -> dict:
    """
    Point d'entrée principal de l'extraction d'un article depuis un texte OCR.

    Orchestre tous les sous-extracteurs (code, nom, groupe, UDM, prix, description
    et les 15+ onglets Sage ERP) puis retourne un dict unifié :
      {
        "champs"        : dict fieldname → valeur extraite,
        "confiances"    : dict fieldname → score 0.0–1.0,
        "type_document" : "fiche_article" ou "inconnu"
      }
    Retourne _resultat_vide() si le texte est vide.
    """
    if not texte or not texte.strip():
        return _resultat_vide()

    texte_norm = _normaliser_texte(texte)
    lignes     = texte_norm.splitlines()

    champs     = {}
    confiances = {}

    _extraire_code_article(texte_norm, lignes, champs, confiances)
    _extraire_nom_article(texte_norm,  lignes, champs, confiances)
    _extraire_groupe(texte_norm,       lignes, champs, confiances)
    _extraire_udm(texte_norm,          lignes, champs, confiances)
    _extraire_prix(texte_norm,         lignes, champs, confiances, texte_brut=texte)
    _extraire_description(texte_norm,  lignes, champs, confiances)
    # Champs Sage ERP — Base
    _extraire_statut(texte_norm,            lignes, champs, confiances)
    _extraire_gestion_stock(texte_norm,     lignes, champs, confiances)
    _extraire_gestion_lot_serie(texte_norm, lignes, champs, confiances)
    _extraire_unites_sage(texte_norm,       lignes, champs, confiances)
    _extraire_poids(texte_norm,             lignes, champs, confiances)
    # Champs Sage ERP — Onglet Identification
    _extraire_champs_identification_sage(texte_norm, lignes, champs, confiances)
    _extraire_familles_statistiques(texte_norm,      lignes, champs, confiances)
    _extraire_champs_physiques(texte_norm,           lignes, champs, confiances)
    # Champs Sage ERP — Onglet Gestion
    _extraire_gestion_avancee(texte_norm,  lignes, champs, confiances)
    # Champs Sage ERP — Onglet Unités
    _extraire_unites_avancees(texte_norm,  lignes, champs, confiances)
    # Champs Sage ERP — Onglet Comptabilité
    _extraire_comptabilite_sage(texte_norm, lignes, champs, confiances)
    # Champs Sage ERP — Onglet Vente
    _extraire_donnees_vente_sage(texte_norm, lignes, champs, confiances)
    # Champs Sage ERP — Appro/Stock site
    _extraire_appro_stock(texte_norm,    lignes, champs, confiances)
    # Champs Sage ERP — Onglet Fournisseurs
    _extraire_fournisseur_article(texte_norm, lignes, champs, confiances)
    # Champs Sage ERP — Onglet Après-vente
    _extraire_apres_vente_sage(texte_norm,   lignes, champs, confiances)
    # Champs Sage ERP — Onglet Clients
    _extraire_clients_sage(texte_norm,       lignes, champs, confiances)

    signaux_fiche = [
        "référence", "reference", "code article", "désignation",
        "désig", "description", "fiche technique", "fiche produit",
        "datasheet", "spécification", "specification", "caractéristique",
        "unité de mesure", "prix unitaire", "prix ht", "prix ttc",
    ]
    # Dériver custom_statut_article depuis disabled si non extrait directement
    if "custom_statut_article" not in champs and "disabled" in champs:
        champs["custom_statut_article"]     = "Inactif" if champs["disabled"] == "1" else "Actif"
        confiances["custom_statut_article"] = confiances.get("disabled", 0.80)

    type_doc = "inconnu"
    if any(s in texte_norm.lower() for s in signaux_fiche):
        type_doc = "fiche_article"
    elif len([v for v in champs.values() if v]) >= 2:
        type_doc = "fiche_article"

    return {
        "champs":         champs,
        "confiances":     confiances,
        "type_document":  type_doc,
    }


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS PAR CHAMP
# ──────────────────────────────────────────────────────────────────────

_DATE_MOIS_ANNEE = re.compile(
    r'^(?:jan(?:v(?:ier)?)?|f[eé]v(?:rier)?|mar(?:s)?|avr(?:il)?|mai|juin'
    r'|juil(?:let)?|ao[uû]t|sept?(?:embre)?|oct(?:obre)?'
    r'|nov(?:embre)?|d[eé]c(?:embre)?'
    r'|january|february|march|april|may|june|july|august'
    r'|september|october|november|december)[\-/]\d{4}$',
    re.IGNORECASE
)


def _extraire_code_article(texte, lignes, champs, confiances):
    """
    CORRIGÉ v5 : Filtre les faux codes courts (≤3 caractères) et les mots communs.
    - Sage ERP layout :  "Article :   ACP0011   EMBOUT GAUCHE PLTSX100"
    - ERPNext PDF layout : label ligne N, valeur ligne N+1
    - Technical datasheets : peut ne pas avoir de code article distinct
    """
    # Mots à exclure (ne sont jamais des codes articles)
    _EXCLUDED_CODES = {"and", "or", "the", "in", "on", "at", "to", "for", "of", "a",
                       "spa", "sa", "srl", "ltd", "inc", "llc", "gmbh", "sarl"}
    
    # ── Pattern Sage ERP "Fiche article" : "Article : CODE  NOM" ────
    pat_sage = r"(?:^|\n)\s*Article\s*:\s*([A-Z0-9]{2,20})\b"
    m = re.search(pat_sage, texte, re.IGNORECASE | re.MULTILINE)
    if m:
        val = _nettoyer_code(m.group(1))
        if val and not _DATE_MOIS_ANNEE.match(val) and val.lower() not in _EXCLUDED_CODES:
            _m_fmt = re.match(r'^([A-Za-z]{2,5})(0{2,})([1-9]\d*)$', val)
            if _m_fmt:
                _letters, _zeros, _sig = _m_fmt.groups()
                if len(_zeros) + len(_sig) > 4:
                    _num = int(_zeros + _sig)
                    if _num <= 9999:
                        val = _letters + str(_num).zfill(4)
            champs["item_code"]     = val
            confiances["item_code"] = 0.97
            return

    # ── Pattern multiligne PRIORITAIRE ─────────────────────────────
    pat_multiline = (
        r"(?:code\s*de\s*l[' ]article|item\s*code)\s*\*?[^\n]*\n"
        r"\s*([A-Z0-9][A-Z0-9\-_./ ]{1,39})"
    )
    m = re.search(pat_multiline, texte, re.IGNORECASE)
    if m:
        val = _nettoyer_code(m.group(1))
        if val:
            champs["item_code"]     = val
            confiances["item_code"] = 0.95
            return

    # ── Patterns inline avec label explicite (haute confiance) ──────
    patterns_labels = [
        r"(?:product\s*code)\s*\*?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_./ ]{1,39})",
        r"(?:code\s*de\s*l[' ]article|code\s*article)\s*\*?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_./ ]{1,39})",
        r"(?:item\s*code|item\s*ref(?:erence)?)\s*\*?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_./ ]{1,39})",
        r"(?:r[eé]f(?:[eé]rence)?\.?|part\s*no\.?|r[eé]f\.\s*art\.?|num[eé]ro\s*article|article\s*n[o°]?\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_./ ]{1,29})",
        r"(?:SKU|EAN|GTIN|ISBN|UPC|CAS)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_.]{1,30})",
    ]
    for pat in patterns_labels:
        m = re.search(pat, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_code(m.group(1))
            if val and len(val) >= 4 and val.lower() not in _EXCLUDED_CODES:
                champs["item_code"]     = val
                confiances["item_code"] = 0.92
                return

    # ── Patterns structurels autonomes (confiance réduite) ──────────
    patterns_struct = [
        r"\b([A-Z]{2,6}[\-/][A-Z0-9]{2,6}[\-/][A-Z0-9]{2,10}(?:[\-/][A-Z0-9]{1,6})?)\b",
        r"\b([A-Z]{2,5}[\-/]\d{3,8}(?:[\-/][A-Z0-9]{1,6})?)\b",
        r"\b([A-Z]{2,4}\d{4,8})\b",
        r"\b(\d{12,13})\b",
    ]
    for pat in patterns_struct:
        m = re.search(pat, texte, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if _DATE_MOIS_ANNEE.match(val) or val.lower() in _EXCLUDED_CODES:
                continue
            if val and 5 <= len(val) <= 40:
                champs["item_code"]     = val
                confiances["item_code"] = 0.65
                return


def _extraire_nom_article(texte, lignes, champs, confiances):
    """
    Stratégie -1 : Technical Datasheet → nom produit après header
    Stratégie 0  : Sage ERP "Article : CODE NOM"
    Stratégie 1  : suite de ligne après item_code
    Stratégie 2  : pattern multiligne
    Stratégie 3  : patterns inline avec label
    Stratégie 4  : heuristique première ligne significative
    """
    has_technical = re.search(r'\bTECHNICAL\b', texte, re.IGNORECASE)
    has_data = re.search(r'\bDATA\b', texte, re.IGNORECASE)
    has_sheet = re.search(r'\bSHEET\b', texte, re.IGNORECASE)
    
    is_technical_datasheet = bool(has_technical and has_data and has_sheet)
    
    if is_technical_datasheet:
        pattern_simple = r'\b([A-Z]{4,}[\s\-]+\d{2,4})\b'
        pattern_compose = r'\b([A-Z]{4,}\s+[A-Z]{4,}\s+[A-Z]+\d{2,})\b'
        
        candidats_composes = re.findall(pattern_compose, texte)
        for candidat in candidats_composes:
            candidat_clean = candidat.strip()
            if re.search(r'\b(REVISION|DATE|VERSION|PAGE|UPDATED|MODIFIED|COLD|SPRAY|COATING)\b', candidat_clean, re.IGNORECASE):
                continue
            if re.search(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}', candidat_clean):
                continue
            champs["item_name"] = candidat_clean
            confiances["item_name"] = 0.98
            return
        
        candidats_simples = re.findall(pattern_simple, texte)
        
        m_desc = re.search(r'\bDESCRIPTION\b', texte, re.IGNORECASE)
        if m_desc:
            texte_description = texte[m_desc.start():]
            candidats_dans_desc = re.findall(pattern_simple, texte_description)
            for candidat in candidats_dans_desc:
                candidat_clean = candidat.strip()
                if re.search(r'\b(REVISION|DATE|VERSION|PAGE|UPDATED|MODIFIED)\b', candidat_clean, re.IGNORECASE):
                    continue
                if re.search(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}', candidat_clean):
                    continue
                if re.search(r'^\d{4}$', candidat_clean):
                    continue
                champs["item_name"] = candidat_clean
                confiances["item_name"] = 0.98
                return
        
        for candidat in candidats_simples:
            candidat_clean = candidat.strip()
            champs["item_name"] = candidat_clean
            confiances["item_name"] = 0.95
            return

    # ── Stratégie 0 : format Sage ERP ───────────────────────────────
    # ── Stratégie 0 : format Sage ERP ───────────────────────────────
    if champs.get("item_code") and confiances.get("item_code", 0) >= 0.90:
      pat_sage_nom = r"(?:^|\n)\s*Article\s*:\s*[A-Z0-9]{2,20}\s+([^\n\r]+)"
      m = re.search(pat_sage_nom, texte, re.IGNORECASE | re.MULTILINE)
      if m:
        val = _nettoyer_chaine(m.group(1))
        # Couper avant les labels de section Sage qui suivent sur la même ligne
        _stop = re.search(
            r'\s{2,}(?:Cat[eé]gorie|Standard|Statut|Sur\s+stock|Gestion)\b',
            val, re.IGNORECASE
        )
        if _stop:
            val = val[:_stop.start()].strip()
        if val and 2 <= len(val) <= 140:
            champs["item_name"]     = val
            confiances["item_name"] = 0.97
            return

    # ── Stratégie 1 : suite de la ligne après item_code ─────────────
    _STOP_INLINE = re.compile(
        r'\s+(?:consommable|produit fini|mati[eè]re|accessoire|outillage|informatique'
        r'|UN\b|Nos\b|Kg\b|Pcs\b|m\b|L\b|Box\b|Pack\b|UDM|UOM|u\.d\.m'
        r'|actif|inactif|d[eé]sactiv[eé]|sauvegard[eé]|enregistr[eé])\b',
        re.IGNORECASE
    )
    if champs.get("item_code") and confiances.get("item_code", 0) >= 0.85:
        code_prefix = re.match(r'^([A-Za-z]{2,5})', champs["item_code"])
        if code_prefix:
            _pat_code_inline = code_prefix.group(1) + r"[A-Z0-9]{2,15}\s+(.+)"
            m = re.search(_pat_code_inline, texte, re.IGNORECASE)
        else:
            code_escaped = re.escape(champs["item_code"])
            m = re.search(code_escaped + r"\s+(.+)", texte, re.IGNORECASE)
        if m:
            reste = m.group(1)
            stop_m = _STOP_INLINE.search(reste)
            if stop_m:
                reste = reste[:stop_m.start()]
            val = _nettoyer_chaine(reste)
            if re.match(r'^(Revision|Date|Version|Page|Updated|Modified)', val, re.IGNORECASE):
                pass
            elif val and 3 <= len(val) <= 120:
                champs["item_name"]     = val
                confiances["item_name"] = 0.92
                return

    # ── Stratégie 2 : pattern multiligne ────────────────────────────
    pat_multiline = (
        r"(?:nom\s*de\s*l[' ]article|item\s*name)\s*\*?[^\n]*\n"
        r"\s*(.+)"
    )
    m = re.search(pat_multiline, texte, re.IGNORECASE)
    if m:
        ligne_val = m.group(1).strip()
        if re.match(r'^(Revision|Date|Version|Page|Product\s+Code|Updated|Modified)', ligne_val, re.IGNORECASE):
            pass
        elif re.search(r'\b(revision|date|version)\b.*\d{1,2}[\s./-]+\d{1,2}[\s./-]+\d{2,4}', ligne_val, re.IGNORECASE):
            pass
        elif re.match(r'^Revision\s+date\b', ligne_val, re.IGNORECASE):
            pass
        else:
            if champs.get("item_code") and ligne_val.startswith(champs["item_code"]):
                ligne_val = ligne_val[len(champs["item_code"]):].strip()
            val = _nettoyer_chaine(ligne_val)
            if val and len(val) >= 3:
                champs["item_name"]     = val[:140]
                confiances["item_name"] = 0.90
                return

    # ── Stratégie 3 : patterns inline avec label ────────────────────
    patterns_labels = [
        r"(?:nom\s*de\s*l[' ]article|nom\s*article)\s*\*?\s*[:\-]?\s*(.+)",
        r"(?:d[eé]signation|d[eé]sig\.?|lib[eé]ll[eé]|product\s*name|item\s*name|description\s*courte)\s*[:\-]?\s*(.+)",
    ]
    for pat in patterns_labels:
        m = re.search(pat, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if re.match(r'^(Revision|Date|Version|Page|Updated|Modified)', val, re.IGNORECASE):
                continue
            if re.match(r'^Revision\s+date\b', val, re.IGNORECASE):
                continue
            if re.search(r'\b(revision|date|version)\b.*\d{1,2}[\s./-]+\d{1,2}[\s./-]+\d{2,4}', val, re.IGNORECASE):
                continue
            if val and len(val) >= 3:
                champs["item_name"]     = val[:140]
                confiances["item_name"] = 0.90
                return

    # ── Stratégie 4 : heuristique première ligne significative ──────
    _SKIP_PATTERNS = re.compile(
        r"(fiche|technique|produit|datasheet|page|date|version|révision|revision"
        r"|tel|fax|mail|@|www\.|\.com|\.tn|sarl|s\.a|s\.a\.r\.l|spa\b"
        r"|document\s*de\s*r[eé]f[eé]rence|document\s*de\s*référence"
        r"|erpnext|erp\s*next|module\s*stock|module\s*article"
        r"|référence\s*produit|reference\s*produit"
        r"|groupes?\s*bayoudh|bayoudh\s*metal"
        r"|identification|tarification|informations?\s*fournisseur"
        r"|\bfiche\s+article\b"
        r"|commerciale|siliconi|technical\s+data|characteristics)",
        re.IGNORECASE
    )
    for ligne in lignes[:20]:
        l = ligne.strip()
        if not l or len(l) < 5:
            continue
        if re.match(r'^[\d\s\-._|/]+$', l):
            continue
        if _SKIP_PATTERNS.search(l):
            continue
        if len(re.findall(r'[A-Za-zÀ-ÿ]', l)) < 3:
            continue
        if re.match(r'^(?:code|nom|groupe|unité|prix|stock|taux|remise|devise|article)\b', l, re.IGNORECASE):
            continue
        champs["item_name"]     = _nettoyer_chaine(l)[:140]
        confiances["item_name"] = 0.60
        return

_SAGE_CAT_MAP = {
    "CONS": "Consommables",
    "ACCP": "Accessoires",
    "AACP": "Accessoires",
    "PIEC": "Pièces détachées",
    "MATO": "Matières premières",
    "EMBA": "Emballage",
    "OUTL": "Outillage",
    "EQUI": "Équipement",
    "PROD": "Produits finis",
    "ELEC": "Électricité",
    "INFO": "Informatique",
    "RESEAU": "Réseau",
}


def _extraire_groupe(texte, lignes, champs, confiances):
    """
    Extrait le groupe d'article (item_group) et la catégorie Sage.

    Priorité :
      1. Pattern Sage ERP  « Catégorie : CODE »  → code mappé via _SAGE_CAT_MAP
      2. Pattern multiligne (label ligne N, valeur ligne N+1)
      3. Pattern inline avec label « groupe d'article / item group »
      4. Nom de groupe connu directement dans le texte (_GROUPES_CONNUS)
      5. Détection par mots-clés (_MOTS_CLES_GROUPE)
    Note : désactivé sur les fiches techniques (évite les faux positifs).
    """
    # ── Pattern Sage ERP PRIORITAIRE : "Catégorie : CODE" ───────────
    m_cat = re.search(r"Cat[eé]gorie\s*:\s*([A-Z0-9]{2,10})\b", texte, re.IGNORECASE)
    if m_cat:
        code_sage = m_cat.group(1).strip().upper()
        champs["custom_categorie_sage"]     = code_sage
        confiances["custom_categorie_sage"] = 0.92
        # Mapper vers groupe ERPNext connu (nom complet)
        if code_sage in _SAGE_CAT_MAP:
            champs["item_group"]     = _SAGE_CAT_MAP[code_sage]
            confiances["item_group"] = 0.88
        else:
            # Code Sage non répertorié → le passer tel quel, la BD
            # utilise peut-être les codes Sage directement comme groupes
            champs["item_group"]     = code_sage
            confiances["item_group"] = 0.80
        return

    # ── Pattern multiligne PRIORITAIRE ──────────────────────────────
    pat_multiline = (
        r"(?:groupe\s*d[' ]article|item\s*group)\s*\*?[^\n]*\n"
        r"\s*(.+)"
    )
    m = re.search(pat_multiline, texte, re.IGNORECASE)
    if m:
        ligne_val = m.group(1).strip()
        val = re.split(r'\s{2,}|\t', ligne_val)[0].strip()
        val = re.split(r'\s*\(', val)[0].strip()
        val = re.split(r'\s+(?:UN|Nos|Kg|Pcs|m\b|L\b|—|\|)', val, flags=re.IGNORECASE)[0].strip()
        val = _nettoyer_chaine(val)
        if val and len(val) >= 5 and val.upper() not in _SAGE_CAT_MAP:
            champs["item_group"]     = val[:80]
            confiances["item_group"] = 0.90
            return

    # ── Pattern inline avec label ────────────────────────────────────
    pat_inline = r"(?:groupe\s*d[' ]article|item\s*group)\s*\*?\s*[:\-]?\s*(.+)"
    m = re.search(pat_inline, texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1).split('\n')[0])
        _stop_inline = re.search(
            r'\s+(?:Standard|Sur\s+stock|Statut|Gestion|Actif|Inactif)\s*[:\s]',
            val, re.IGNORECASE
        )
        if _stop_inline:
            val = val[:_stop_inline.start()].strip()
        val = re.split(r'\s*\(|\s{2,}', val)[0].strip()
        m2 = re.search(r'\s+(?:[A-Z][a-z]{2,}|[A-Z]{3,})\s*:', val)
        if m2:
            val = val[:m2.start()].strip()
        if val and len(val) >= 5 and val.upper() not in _SAGE_CAT_MAP:
            champs["item_group"]     = val[:80]
            confiances["item_group"] = 0.85
            return

    # ── Groupe connu directement dans le texte ───────────────────────
    # GARDE : Les fiches techniques (datasheets) ne contiennent pas de groupe ERPNext.
    # Les heuristiques par mots-clés produisent des faux positifs (ex : "film" dans
    # "Dry film Thickness" → "Consommables"). On les désactive pour ces documents.
    is_technical_datasheet = bool(
        re.search(r'\bTECHNICAL\s+DATA\s+SHEET\b', texte, re.IGNORECASE)
        or re.search(r'\bFICHE\s+TECHNIQUE\b', texte, re.IGNORECASE)
        or (
            re.search(r'\bCHARACTERISTICS\b', texte, re.IGNORECASE)
            and re.search(r'\bPROPERTIES\b', texte, re.IGNORECASE)
        )
    )
    if is_technical_datasheet:
        return  # Pas de groupe inféré depuis le contenu d'une fiche technique

    texte_l = texte.lower()
    for groupe in sorted(_GROUPES_CONNUS, key=len, reverse=True):
        if groupe.lower() in texte_l:
            champs["item_group"]     = groupe
            confiances["item_group"] = 0.75
            return

    # ── Détection par mots-clés ──────────────────────────────────────
    for groupe, mots_cles in _MOTS_CLES_GROUPE.items():
        for mc in mots_cles:
            if re.search(r'\b' + re.escape(mc) + r'\b', texte_l):
                champs["item_group"]     = groupe
                confiances["item_group"] = 0.65
                return


def _extraire_udm(texte, lignes, champs, confiances):
    """
    CORRIGÉ v5 : Suppression du fallback "Unité" par défaut.
    Si aucune UDM n'est trouvée avec certitude, on ne remplit pas le champ.
    """
    # ── Pattern Sage ERP PRIORITAIRE : "Unité stock : UN" ───────────
    for pat_us in [
        r"[Uu]nit[eé]\s*stock\s*[:\-]\s*([A-Za-z]{1,10})",
        r"[Uu]nit[eé]\s*stock\s{2,}([A-Z]{1,5})\b",
    ]:
        m = re.search(pat_us, texte)
        if m:
            udm_norm = _normaliser_udm(m.group(1))
            if udm_norm:
                champs["stock_uom"]     = udm_norm
                confiances["stock_uom"] = 0.92
                return

    # ── Pattern multiligne PRIORITAIRE ──────────────────────────────
    pat_multiline = (
        r"(?:unit[eé]\s*(?:de\s*mesure)?(?:\s*par\s*d[eé]faut)?|u\.?d\.?m\.?|u\.?o\.?m\.?|uom)"
        r"\s*\*?[^\n]*\n\s*([A-Za-z0-9²³/\.]{1,10})"
    )
    m = re.search(pat_multiline, texte, re.IGNORECASE)
    if m:
        udm_brut = m.group(1).strip()
        _udm_tokens_valides = re.compile(
            r'^(?:un|unité|unite|nos|pcs|pce|kg|gr?|m2?|m3?|l|box|pack|paire|pair|roll|doz)$',
            re.IGNORECASE
        )
        if _udm_tokens_valides.match(udm_brut):
            udm_norm = _normaliser_udm(udm_brut)
            if udm_norm:
                champs["stock_uom"]     = udm_norm
                confiances["stock_uom"] = 0.90
                return
        pat_udm_dash = r"(?:unit[eé]\s*(?:de\s*mesure)?(?:\s*par\s*d[eé]faut)?)[^\n]*\n[^\n]*\b(UN|Nos|Pcs|Pce|Kg|m2|m3|L)\b"
        m2 = re.search(pat_udm_dash, texte, re.IGNORECASE)
        if m2:
            udm_norm = _normaliser_udm(m2.group(1))
            if udm_norm:
                champs["stock_uom"]     = udm_norm
                confiances["stock_uom"] = 0.88
                return

    # ── Pattern inline avec label ────────────────────────────────────
    pat_label = r"(?:unit[eé]\s*(?:de\s*mesure)?(?:\s*par\s*d[eé]faut)?|u\.?d\.?m\.?|u\.?o\.?m\.?|uom|mesure|unité\s*stock|unité\s*d[' ]achat|unité\s*de\s*vente)\s*\*?\s*[:\-]?\s*([A-Za-z0-9²³/\.]{1,10})"
    m = re.search(pat_label, texte, re.IGNORECASE)
    if m:
        udm_brut = m.group(1).strip()
        udm_norm = _normaliser_udm(udm_brut)
        if udm_norm:
            champs["stock_uom"]     = udm_norm
            confiances["stock_uom"] = 0.85
            return

    # ── Recherche dans le texte (confiance faible, sans fallback) ────
    # CORRECTION : on cherche uniquement des UDM explicitement mentionnées
    # avec un contexte (ex: "400 ml", "Box 12"), pas de fallback "Unité"
    _UDM_CONTEXTE = [
        (r'\b(\d+)\s*(ml|mL|ML)\b',    "m"),
        (r'\b(\d+)\s*(kg|Kg|KG)\b',    "Kg"),
        (r'\b(\d+)\s*(g|gr)\b',        "g"),
        (r'\b(\d+)\s*(L|litre|liter)\b', "L"),
        (r'\bBox\s+(\d+)',              "Box"),
        (r'\bPack\s+(\d+)',             "Pack"),
    ]
    for pat_ctx, udm_val in _UDM_CONTEXTE:
        if re.search(pat_ctx, texte, re.IGNORECASE):
            # Pour les datasheets, extraire l'UDM du packaging si disponible
            # ex: "Spray Aerosol ml 400" → on ne remplit pas stock_uom
            # car c'est l'unité d'emballage, pas l'UDM stock
            pass  # Ne pas remplir automatiquement depuis le contexte
    
    # CORRECTION : PAS de fallback "Unité" par défaut
    # Si aucune UDM explicite trouvée, laisser le champ vide
    # (l'utilisateur le remplira manuellement dans le dialogue)


def _extraire_prix(texte, lignes, champs, confiances, texte_brut=None):
    """
    CORRIGÉ v3 :
    - Patterns MULTILIGNES prioritaires (label ligne N, valeurs ligne N+1)
    - _parse_prix : gère espace séparateur milliers + 3 décimales tunisiennes
    """
    _MONTANT_MIN = 0.1
    _MONTANT_MAX = 999_999

    def _parse_prix(s):
        s = re.sub(r'\s*(?:DT|TND|€|\$|EUR|HT|TTC)\s*', '', s, flags=re.IGNORECASE).strip()
        s = s.strip().rstrip(".,;:")
        s_no_space = re.sub(r'\s', '', s)
        if "," in s_no_space and "." not in s_no_space:
            s_no_space = s_no_space.replace(",", ".")
        elif "," in s_no_space and "." in s_no_space:
            s_no_space = s_no_space.replace(".", "").replace(",", ".")
        try:
            v = float(s_no_space)
            return v if _MONTANT_MIN < v < _MONTANT_MAX else None
        except Exception:
            return None

    # ── Pattern multi-colonne PRIORITAIRE ───────────────────────────
    texte_cols = texte_brut if texte_brut else texte
    pat_cols = (
        r"(?P<avant>[^\n]*)(?:prix\s*de\s*vente\s*standard)(?P<apres>[^\n]*)\n"
        r"(?P<vals>[^\n]+)"
    )
    m = re.search(pat_cols, texte_cols, re.IGNORECASE)
    if m:
        avant_txt = m.group("avant").strip()
        vals_ligne = m.group("vals").strip()
        nb_avant = len([c for c in re.split(r'\s{2,}|\t', avant_txt) if c.strip()])
        cols_vals = [c.strip() for c in re.split(r'\s{2,}|\t', vals_ligne) if c.strip()]
        if nb_avant < len(cols_vals):
            v = _parse_prix(cols_vals[nb_avant])
            if v:
                champs["standard_rate"]     = str(round(v, 3))
                confiances["standard_rate"] = 0.95
        if nb_avant >= 1 and nb_avant - 1 < len(cols_vals):
            v2 = _parse_prix(cols_vals[nb_avant - 1])
            if v2 and "last_purchase_rate" not in champs:
                champs["last_purchase_rate"]     = str(round(v2, 3))
                confiances["last_purchase_rate"] = 0.88
                if "taux" in avant_txt.lower() and "valorisat" in avant_txt.lower():
                    champs["valuation_rate"]     = str(round(v2, 3))
                    confiances["valuation_rate"] = 0.88
        if "standard_rate" in champs:
            return

    # ── Patterns inline directs ──────────────────────────────────────
    pat_vente_inline = [
        r"(?:prix\s*de\s*vente\s*(?:standard|ht))\s*[:\-]\s*([\d][\d\s,.]{0,15})\s*(?:DT|TND|EUR|€|\$)",
    ]
    for pat in pat_vente_inline:
        m = re.search(pat, texte, re.IGNORECASE)
        if m:
            v = _parse_prix(m.group(1))
            if v:
                champs["standard_rate"]     = str(round(v, 3))
                confiances["standard_rate"] = 0.93
                break

    pat_achat_inline = [
        r"(?:taux\s*de\s*valorisation)\s*[:\-]\s*([\d][\d\s,.]{0,15})(?:\s*(?:DT|TND|EUR|€|\$))?",
        r"(?:prix\s*d['']\s*achat|co[uû]t\s*(?:standard|unitaire)?)\s*[:\-]\s*([\d][\d\s,.]{0,15})\s*(?:DT|TND|EUR|€|\$)",
    ]
    for idx, pat in enumerate(pat_achat_inline):
        m = re.search(pat, texte, re.IGNORECASE)
        if m:
            v = _parse_prix(m.group(1))
            if v:
                champs["last_purchase_rate"]     = str(round(v, 3))
                confiances["last_purchase_rate"] = 0.90
                if idx == 0:
                    champs["valuation_rate"]     = str(round(v, 3))
                    confiances["valuation_rate"] = 0.90
                break

    if "valuation_rate" not in champs:
        m_vr = re.search(
            r"[Tt]aux\s+de\s+valorisation[^\n]{0,30}\n[^\n]*?([\d]+[,.][\d]+)",
            texte, re.IGNORECASE
        )
        if m_vr:
            v = _parse_prix(m_vr.group(1))
            if v is not None:
                champs["valuation_rate"]     = str(round(v, 3))
                confiances["valuation_rate"] = 0.82

    if "standard_rate" in champs or "last_purchase_rate" in champs:
        return

    pat_ligne_prix = (
        r"(?:prix\s*de\s*vente\s*standard)[^\n]*"
        r"(?:prix\s*d['' ]achat\s*standard)[^\n]*\n"
        r"\s*([\d\s,.]+(?:DT|TND|€|\$)?)\s+"
        r"([\d\s,.]+(?:DT|TND|€|\$)?)"
    )
    m = re.search(pat_ligne_prix, texte, re.IGNORECASE)
    if m:
        v_vente = _parse_prix(m.group(1))
        v_achat = _parse_prix(m.group(2))
        if v_vente:
            champs["standard_rate"]     = str(round(v_vente, 3))
            confiances["standard_rate"] = 0.95
        if v_achat:
            champs["last_purchase_rate"]     = str(round(v_achat, 3))
            confiances["last_purchase_rate"] = 0.95
        if v_vente or v_achat:
            return

    if "standard_rate" not in champs:
        pat_vente_ml = (
            r"(?:prix\s*de\s*vente\s*standard|standard\s*rate|prix\s*de\s*vente|prix\s*ht|tarif)"
            r"\s*\*?[^\n]*\n\s*([\d\s,.]+(?:DT|TND|€|\$)?)"
        )
        m = re.search(pat_vente_ml, texte, re.IGNORECASE)
        if m:
            v = _parse_prix(m.group(1))
            if v:
                champs["standard_rate"]     = str(round(v, 3))
                confiances["standard_rate"] = 0.90

    if "last_purchase_rate" not in champs:
        pat_achat_ml = (
            r"(?:prix\s*d['' ]achat\s*standard|prix\s*d['' ]?achat|coût|cout|purchase\s*(?:price|rate))"
            r"\s*\*?[^\n]*\n\s*([\d\s,.]+(?:DT|TND|€|\$)?)"
        )
        m = re.search(pat_achat_ml, texte, re.IGNORECASE)
        if m:
            v = _parse_prix(m.group(1))
            if v:
                champs["last_purchase_rate"]     = str(round(v, 3))
                confiances["last_purchase_rate"] = 0.90

    if "standard_rate" in champs or "last_purchase_rate" in champs:
        return

    pat_vente = [
        r"(?:prix\s*(?:de\s*)?vente\s*standard|prix\s*de\s*vente|prix\s*ht|prix\s*ttc|prix\s*public|pvp|tarif|standard\s*rate|list\s*price|msrp)\s*\*?\s*[:\-]?\s*([\d\s,.]+(?:DT|TND|€|\$)?)",
        r"(?:p\.?v\.?\.?\s*ht|p\.?v\.?\s*ttc)\s*[:\-]?\s*([\d\s,.]+)",
    ]
    for pat in pat_vente:
        m = re.search(pat, texte, re.IGNORECASE)
        if m:
            v = _parse_prix(m.group(1))
            if v:
                champs["standard_rate"]     = str(round(v, 3))
                confiances["standard_rate"] = 0.88
                break

    pat_achat = [
        r"(?:prix\s*d['' ]achat\s*standard|prix\s*(?:d['' ])?achat|coût|cout|cost|purchase\s*(?:price|rate)|p\.?a\.?\.?\s*ht|p\.?a\.?\s*ttc)\s*\*?\s*[:\-]?\s*([\d\s,.]+(?:DT|TND|€|\$)?)",
        r"(?:prix\s*fournisseur|prix\s*net)\s*[:\-]?\s*([\d\s,.]+)",
    ]
    for pat in pat_achat:
        m = re.search(pat, texte, re.IGNORECASE)
        if m:
            v = _parse_prix(m.group(1))
            if v:
                champs["last_purchase_rate"]     = str(round(v, 3))
                confiances["last_purchase_rate"] = 0.88
                break

    if "standard_rate" not in champs and "last_purchase_rate" not in champs:
        pat_generique = r"(?:prix\s*unitaire|prix)\s*[:\-]?\s*([\d\s,.]+(?:DT|TND|€|\$)?)"
        m = re.search(pat_generique, texte, re.IGNORECASE)
        if m:
            v = _parse_prix(m.group(1))
            if v:
                champs["standard_rate"]     = str(round(v, 3))
                confiances["standard_rate"] = 0.70


# Garde-fou pour les extracteurs Sage
_SAGE_LABEL_GUARD = re.compile(
    r'^(?:D[eé]signation|Cl[eé]\s*recherche|Ligne\s*(?:de\s*)?produit|Norme'
    r'|R[eé]f[eé]rence\s+douani[eè]re|Acc[eè]s|Soumis|Code\s+EAN'
    r'|Nature|Forme|Epaisseur|Long\s*barre|Couleur|Film|Type\s+[Tt]ole'
    r'|Mode\s+gestion|Gestion|Unit[eé]|Article\s+remp|Article\s+sub'
    r'|Compteur|Coef|Densit|Prix|Qt[eé]|Stock|Niveau|Code\s+compt'
    r'|Cat[eé]gorie|Standard|Statut)',
    re.IGNORECASE
)


def _couper_avant_label(s: str, maxlen: int = 40) -> str:
    """
    Tronque la chaîne dès qu'un nouveau label (Mot: ou Mot-) est détecté.
    Evite de capturer la valeur du champ suivant dans la même ligne.
    """
    m = re.search(r'\s+[A-ZÀ-Ÿ][^\s]+(?:\s+[^\s:]+)*\s*[:\-]', s)
    if m:
        s = s[:m.start()].strip()
    return s[:maxlen]


_STOP_DESC_SECTIONS = re.compile(
    r'^(?:\d+\.\s*)?(?:inventaire|comptabilit[eé]|achat|vente|taxe|qualit[eé]'
    r'|production|r[eé]sum[eé]\s*stock|code.?barres?|fournisseurs?|clients?'
    r'|re.commande|unit[eé]s?\s*de\s*mesure|n[o°]\s*de\s*s[eé]rie)\b',
    re.IGNORECASE
)


def _extraire_description(texte, lignes, champs, confiances):
    """
    Extrait la description/spécifications techniques de l'article.

    Stratégies :
      1. Bloc DESCRIPTION délimité (datasheets techniques)
      2. Pattern label « description : … » multiligne (≤4 lignes)
      3. Heuristique : lignes contenant des valeurs physiques (mm, kg, V, Hz…)
    Ignoré sur les fiches Sage ERP (Gestion stock / Unité stock détectés).
    """
    if re.search(r"Gestion\s*stock\s*[:\-]|Unit[eé]\s*stock|Fiche\s+article", texte, re.IGNORECASE):
        return

    m_desc = re.search(
        r"(?:^|\n)\s*DESCRIPTION\s*\n+(.+?)(?:\n\s*(?:[A-Z\s]{3,}:|PROPERTIES|INSTRUCTIONS|PACKAGING|$))",
        texte, re.IGNORECASE | re.DOTALL
    )
    if m_desc:
        bloc_desc = m_desc.group(1).strip()
        lignes_desc = [l.strip() for l in bloc_desc.splitlines() if l.strip() and len(l.strip()) > 15][:5]
        if lignes_desc:
            val = " | ".join(lignes_desc)[:700]
            champs["description"]     = val
            confiances["description"] = 0.88
            return

    pat_label = r"(?:description)\s*[:\-]?\n?\s*(.+(?:\n(?!\s*(?:\d+\.\s*)?(?:inventaire|comptabilit[eé]|achat|vente|taxe|qualit[eé]|production)).+){0,4})"
    m = re.search(pat_label, texte, re.IGNORECASE)
    if m:
        bloc = m.group(1)
        lignes_desc = []
        for l in bloc.splitlines():
            l = l.strip()
            if not l:
                continue
            if _STOP_DESC_SECTIONS.match(l):
                break
            lignes_desc.append(l)
            if len(lignes_desc) >= 4:
                break
        val = " | ".join(lignes_desc)[:500]
        if val and len(val) >= 10:
            champs["description"]     = val
            confiances["description"] = 0.80
            return

    _PAT_SPEC = re.compile(
        r'\d+\s*(?:mm|cm|m|kg|g|w|v|a|hz|ghz|mhz|gb|mb|tb|rpm|dpi|ppm|db|°c|°)\b'
        r'|\b(?:compatible|certifi[eé]|homologu[eé]|agr[eé][eé]|norme|standard|classe|ip\d{2})\b'
        r'|\b(?:dimensions?|poids|puissance|tension|fréquence|capacité|vitesse|résolution|couleur)\b',
        re.IGNORECASE
    )
    lignes_spec = []
    for ligne in lignes:
        l = ligne.strip()
        if not l or len(l) < 5:
            continue
        if _PAT_SPEC.search(l):
            lignes_spec.append(l)
        if len(lignes_spec) >= 5:
            break

    if lignes_spec:
        champs["description"]     = " | ".join(lignes_spec)[:500]
        confiances["description"] = 0.60


# ──────────────────────────────────────────────────────────────────────
# NOUVEAUX EXTRACTEURS — CHAMPS SAGE ERP (Fiche article)
# ──────────────────────────────────────────────────────────────────────

def _extraire_statut(texte, lignes, champs, confiances):
    """
    Extrait le statut de l'article (Actif/Inactif) depuis un texte Sage ERP.
    Remplit les champs ERPNext « disabled » (0/1) et « custom_statut_article ».
    """
    # Pattern existant
    m = re.search(r'Statut\s*[:|]?\s*(Actif|Inactif)', texte, re.IGNORECASE)
    if not m:
        m = re.search(r'\bStatut\b[^\n]{0,20}\b(Actif|Inactif)\b', texte, re.IGNORECASE)
    # NOUVEAU : pattern ligne Sage "Catégorie : CONS  Standard : Sur stock  Statut : Actif"
    if not m:
        m = re.search(
            r'Cat[eé]gorie\s*:[^\n]*\bStatut\s*:\s*(Actif|Inactif)\b',
            texte, re.IGNORECASE
        )
    if m:
        valeur = m.group(1).strip().capitalize()
        champs["disabled"]                   = "0" if valeur.lower() == "actif" else "1"
        confiances["disabled"]               = 0.90
        champs["custom_statut_article"]      = valeur
        confiances["custom_statut_article"]  = 0.90


def _extraire_gestion_stock(texte, lignes, champs, confiances):
    """
    Extrait le mode de gestion du stock Sage et l'indicateur ERPNext is_stock_item.
    Valeur « article géré » → is_stock_item = 1, sinon 0.
    """
    m = re.search(r'Gestion\s*stock\s*:?\s*([^\n|,;]{3,60})', texte, re.IGNORECASE)
    if m:
        raw = _nettoyer_chaine(m.group(1))
        val_l = raw.lower()
        est_gere = any(k in val_l for k in ("géré", "gere", "article géré", "article gere"))
        champs["is_stock_item"]           = "1" if est_gere else "0"
        confiances["is_stock_item"]       = 0.88
        if raw:
            champs["custom_gestion_stock"]     = raw[:60]
            confiances["custom_gestion_stock"] = 0.88


def _extraire_gestion_lot_serie(texte, lignes, champs, confiances):
    """
    Extrait la gestion de lot (has_batch_no) et de série (has_serial_no) Sage ERP.
    Détecte les mots-clés « géré », « gere » pour activer les indicateurs ERPNext.
    """
    m_lot = re.search(r'Gestion\s*lot\s*[:\-]?\s*([^\n|,;]{3,60})', texte, re.IGNORECASE)
    if m_lot:
        val_raw = _nettoyer_chaine(m_lot.group(1))
        val = val_raw.lower()
        champs["has_batch_no"]     = "1" if "géré" in val or "gere" in val or "lot" in val and "pas" not in val else "0"
        confiances["has_batch_no"] = 0.85
        champs["custom_gestion_lot_mode"]     = val_raw[:60]
        confiances["custom_gestion_lot_mode"] = 0.85

    m_serie = re.search(r'Gestion\s*s[eé]rie\s*[:\-]?\s*([^\n|,;]{3,60})', texte, re.IGNORECASE)
    if m_serie:
        val_raw = _nettoyer_chaine(m_serie.group(1))
        val = val_raw.lower()
        champs["has_serial_no"]     = "1" if "géré" in val or "gere" in val or ("sortie" in val or "entr" in val) else "0"
        confiances["has_serial_no"] = 0.85
        champs["custom_gestion_serie_mode"]     = val_raw[:60]
        confiances["custom_gestion_serie_mode"] = 0.85


def _extraire_unites_sage(texte, lignes, champs, confiances):
    """
    Extrait les unités de mesure Sage : achat (purchase_uom), vente (sales_uom),
    poids (weight_uom) et conditionnement (custom_uom_conditionnement).
    Le fallback « Unité » est intentionnellement ignoré (trop générique).
    """
    for label, champ in [
        (r"[Uu]nit[eé]\s*achat\s*[:\-]\s*([A-Za-z]{1,5})",  "purchase_uom"),
        (r"[Uu]nit[eé]\s*(?:de\s*)?vente\s*[:\-]\s*([A-Za-z]{1,5})", "sales_uom"),
        (r"[Uu]nit[eé]\s*poids\s*[:\-]\s*([A-Z]{1,5})\b",  "weight_uom"),
    ]:
        m = re.search(label, texte)
        if m:
            udm = _normaliser_udm(m.group(1))
            if champ == "weight_uom" and m.group(1).lower() in ("poids", "pds", "pds."):
                continue
            if udm:
                champs[champ]     = udm
                confiances[champ] = 0.85

    m_uc = re.search(
        r"[Uu]nit[eé]\s*(?:de\s*)?conditionnement\s*[:\-]?\s*([A-Za-z]{1,10})",
        texte
    )
    if m_uc:
        udm_uc = _normaliser_udm(m_uc.group(1))
        # CORRECTION : ne pas stocker "Unité" par défaut (trop générique)
        if udm_uc and udm_uc.lower() not in ("unité", "unite", "unit"):
            champs["custom_uom_conditionnement"]     = udm_uc
            confiances["custom_uom_conditionnement"] = 0.85


def _extraire_poids(texte, lignes, champs, confiances):
    """
    Extrait le poids de l'unité de stock (weight_per_unit) et l'UDM poids.
    Pattern Sage ERP : « Poids de l'US : 1,250 » → weight_per_unit = 1.25
    """
    m = re.search(r"Poids\s*de\s*l[''']?US\s*[:\-]?\s*([\d]+(?:[,.][\d]+)?)", texte, re.IGNORECASE)
    if m:
        try:
            val = float(m.group(1).replace(",", "."))
            if val > 0:
                champs["weight_per_unit"]     = str(round(val, 6))
                confiances["weight_per_unit"] = 0.82
        except ValueError:
            pass


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS SAGE ERP — ONGLET IDENTIFICATION
# ──────────────────────────────────────────────────────────────────────

def _extraire_champs_identification_sage(texte, lignes, champs, confiances):
    """
    Extrait les champs de l'onglet « Identification » Sage ERP :
    barcode/EAN, désignation 2 & 3, clé recherche, ligne produit, norme,
    référence douanière, DEB, accès gestionnaire, informations produit,
    texte production, texte préparation.
    """
    for pat in [
        r"Code\s+EAN\s*[:\-]?\s*([0-9]{8,14})",
        r"EAN\s*[:\-]?\s*([0-9]{8,14})",
        r"\b(\d{13})\b",
    ]:
        m = re.search(pat, texte, re.IGNORECASE)
        if m:
            champs["barcode"]     = m.group(1).strip()
            confiances["barcode"] = 0.90
            break

    for pat_d2 in [
        r"D[eé]signation\s+2\s*:\s*([^\n\t]{2,140})",
        r"D[eé]signation\s+2\s{2,}([^\n\t]{2,140})",
    ]:
        m = re.search(pat_d2, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_designation2"]     = val[:140]
                confiances["custom_designation2"] = 0.85
            break

    for pat_d3 in [
        r"D[eé]signation\s+3\s*:\s*([^\n\t]{2,140})",
        r"D[eé]signation\s+3\s{2,}([^\n\t]{2,140})",
    ]:
        m = re.search(pat_d3, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_designation3"]     = val[:140]
                confiances["custom_designation3"] = 0.85
            break

    for pat_cr in [
        r"Cl[eé]\s*recherche\s*:\s*([^\n\t]{1,80})",
        r"Cl[eé]\s*recherche\s{2,}([^\n\t]{1,80})",
    ]:
        m = re.search(pat_cr, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_cle_recherche"]     = val[:80]
                confiances["custom_cle_recherche"] = 0.85
            break

    for pat_lp in [
        r"Ligne\s*(?:de\s*)?produit\s*:\s*([^\n\t]{1,80})",
        r"Ligne\s*(?:de\s*)?produit\s{2,}([^\n\t]{1,80})",
    ]:
        m = re.search(pat_lp, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_ligne_produit"]     = val[:80]
                confiances["custom_ligne_produit"] = 0.85
            break

    for pat_nr in [
        r"Norme\s*:\s*([^\n\t]{1,80})",
        r"Norme\s{2,}([^\n\t]{1,80})",
    ]:
        m = re.search(pat_nr, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_norme"]     = val[:80]
                confiances["custom_norme"] = 0.85
            break

    for pat_rd in [
        r"R[eé]f[eé]rence\s+douani[eè]re\s*:\s*([^\n\t]{1,80})",
        r"R[eé]f[eé]rence\s+douani[eè]re\s{2,}([^\n\t]{1,80})",
    ]:
        m = re.search(pat_rd, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_ref_douaniere"]     = val[:80]
                confiances["custom_ref_douaniere"] = 0.85
            break

    m = re.search(r"Soumis\s+[àa]\s+la\s+DEB", texte, re.IGNORECASE)
    if m:
        champs["custom_soumis_deb"]     = "1"
        confiances["custom_soumis_deb"] = 0.80

    for pat_ag in [
        r"Acc[eè]s\s+gestionnaire\s*[:\-]\s*([A-Z0-9][^\n\t,|]{0,40})",
        r"Acc[eè]s\s+gestionnaire\s{2,}([A-Z0-9][^\n\t,|]{0,40})",
    ]:
        m = re.search(pat_ag, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_acces_gestionnaire"]     = val[:40]
                confiances["custom_acces_gestionnaire"] = 0.82
            break

    for pat_ip in [
        r"Informations?\s+produits?\s*[:\-]\s*([^\n\t,|]{2,140})",
        r"Informations?\s+produits?\s{2,}([^\n\t,|]{2,140})",
    ]:
        m = re.search(pat_ip, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_infos_produit"]     = val[:140]
                confiances["custom_infos_produit"] = 0.80
            break

    if re.search(r"Texte\s+production", texte, re.IGNORECASE):
        champs["custom_texte_production"]     = "1"
        confiances["custom_texte_production"] = 0.75
    if re.search(r"Texte\s+pr[eé]paration", texte, re.IGNORECASE):
        champs["custom_texte_preparation"]     = "1"
        confiances["custom_texte_preparation"] = 0.75


def _extraire_familles_statistiques(texte, lignes, champs, confiances):
    """
    Extrait les familles statistiques Sage ERP :
    nature, caractéristique technique, forme et autres codes statistiques.
    Exclut les termes anglais chimiques/techniques (faux positifs datasheets).
    """
    if True:
        m = re.search(
            r"Nature\s*[:\-]?\s*([A-Z0-9]{1,20})\s+([A-Za-zÀ-ÿ][^\n\t]{2,79})",
            texte, re.IGNORECASE
        )
        if m:
            code_nat = m.group(1).strip()
            lib_nat  = _nettoyer_chaine(m.group(2))
            if not re.search(r"\b(and|odourless|hydrocarbon|CFC|Free)\b", lib_nat, re.IGNORECASE):
                champs["custom_nature"]     = f"{code_nat} - {lib_nat}" if lib_nat else code_nat
                confiances["custom_nature"] = 0.88
        else:
            m = re.search(r"Nature\s*[:\-]?\s*([^\n\t]{2,80})", texte, re.IGNORECASE)
            if m:
                val = _nettoyer_chaine(m.group(1))
                if val and not re.search(r"\b(and|odourless|hydrocarbon|CFC|Free|Denatured)\b", val, re.IGNORECASE):
                    champs["custom_nature"]     = val[:80]
                    confiances["custom_nature"] = 0.80

    m = re.search(r"Carac(?:t[eé]ristique)?\s+technique\s*[:\-]?\s*([^\n\t]{1,80})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_carac_technique"]     = val[:80]
            confiances["custom_carac_technique"] = 0.85

    for pat_fr in [
        r"\bForme\s*:\s*([A-Z0-9][^\n\t]{0,79})",
        r"\bForme\s{2,}([A-Z0-9][^\n\t]{0,79})",
    ]:
        m = re.search(pat_fr, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_forme"]     = val[:80]
                confiances["custom_forme"] = 0.85
            break

    m = re.search(
        r"Diam\s*(?:ou\s+Long\s*(?:ou\s+Ep\.?)?)?\s*[:\-]\s*([\d][\d\s.,]*(?:\s*(?:mm|cm|m))?)",
        texte, re.IGNORECASE
    )
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_dim_long"]     = val[:40]
            confiances["custom_dim_long"] = 0.82

    m = re.search(
        r"Larg\s*(?:ou\s+Ep\s*inf\.?)?\s*[:\-]\s*([\d][\d\s.,]*(?:\s*(?:mm|cm|m))?)",
        texte, re.IGNORECASE
    )
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_dim_larg"]     = val[:40]
            confiances["custom_dim_larg"] = 0.82


def _extraire_champs_physiques(texte, lignes, champs, confiances):
    """
    Extrait les dimensions physiques Sage ERP :
    épaisseur, longueur barre, et autres mesures structurelles.
    """
    for pat_ep in [
        r"\bEpaisseur\s*[:\-]\s*([\d][\d\s.,]*(?:\s*mm)?)",
        r"\bEpaisseur\s{2,}([\d][\d\s.,]*(?:\s*mm)?)",
    ]:
        m = re.search(pat_ep, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val:
                champs["custom_epaisseur"]     = val[:40]
                confiances["custom_epaisseur"] = 0.85
            break

    m = re.search(r"Long\s*barre(?:/Cor)?\s*[:\-]\s*([\d][\d\s.,]*(?:\s*(?:mm|cm|m))?)", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_long_barre"]     = val[:40]
            confiances["custom_long_barre"] = 0.85

    for pat_cs in [
        r"Couleur\s+[Tt]ole?\s+[Ss]up(?:[eé]rieure)?\s*[:\-]\s*([^\n\t]{1,60})",
        r"Couleur\s+[Tt]ole?\s+[Ss]up(?:[eé]rieure)?\s{2,}([^\n\t]{1,60})",
    ]:
        m = re.search(pat_cs, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_couleur_sup"]     = val[:60]
                confiances["custom_couleur_sup"] = 0.85
            break

    for pat_ci in [
        r"Couleur\s+[Tt]ole?\s+[Ii]nf(?:[eé]rieure)?\s*[:\-]\s*([^\n\t]{1,60})",
        r"Couleur\s+[Tt]ole?\s+[Ii]nf(?:[eé]rieure)?\s{2,}([^\n\t]{1,60})",
    ]:
        m = re.search(pat_ci, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_couleur_inf"]     = val[:60]
                confiances["custom_couleur_inf"] = 0.85
            break

    for pat_fl in [
        r"\bFilm\s*[:\-]\s*([^\n\t]{1,60})",
        r"\bFilm\s{2,}([^\n\t]{1,60})",
    ]:
        m = re.search(pat_fl, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_film"]     = val[:60]
                confiances["custom_film"] = 0.85
            break

    for pat_tt in [
        r"Type\s+[Tt]ole?\s*[:\-]\s*([^\n\t]{1,60})",
        r"Type\s+[Tt]ole?\s{2,}([^\n\t]{1,60})",
    ]:
        m = re.search(pat_tt, texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(m.group(1))
            if val and not _SAGE_LABEL_GUARD.match(val):
                champs["custom_type_tole"]     = val[:60]
                confiances["custom_type_tole"] = 0.85
            break


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS SAGE ERP — ONGLET GESTION
# ──────────────────────────────────────────────────────────────────────

def _extraire_gestion_avancee(texte, lignes, champs, confiances):
    """
    Extrait les champs de l'onglet « Gestion » Sage ERP :
    méthode valorisation (CMUP/FIFO/LIFO), mode gestion, stock négatif,
    traçabilité, titre %, coefficient DLU, article remplacement, gestion
    péremption, compteurs lot/série.
    """
    m_vm = re.search(
        r"M[eé]thode\s+de\s+valorisation\s*[:\-]?\s*([^\n\t,|]{2,40})",
        texte, re.IGNORECASE
    )
    if m_vm:
        raw = _nettoyer_chaine(_couper_avant_label(m_vm.group(1)))
        if raw:
            raw_l = raw.lower()
            if any(k in raw_l for k in ("cmup", "moyen", "average", "pond")):
                champs["valuation_method"]     = "Moving Average"
            elif any(k in raw_l for k in ("fifo", "premier entré")):
                champs["valuation_method"]     = "FIFO"
            elif any(k in raw_l for k in ("lifo", "dernier entré")):
                champs["valuation_method"]     = "LIFO"
            else:
                champs["custom_methode_valorisation"]     = raw[:40]
                confiances["custom_methode_valorisation"] = 0.82
    elif re.search(r"\bStandard\b", texte) and "valuation_method" not in champs:
        if re.search(r"Standard\s*[:\-]\s*Sur\s+stock", texte, re.IGNORECASE):
            champs.setdefault("custom_methode_valorisation", "Standard")
            confiances.setdefault("custom_methode_valorisation", 0.70)

    m = re.search(r"Mode\s+gestion\s*[:\-]\s*([^\n\t]{3,80})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(_couper_avant_label(m.group(1)))
        if val:
            champs["custom_mode_gestion"]     = val
            confiances["custom_mode_gestion"] = 0.88
    elif not champs.get("custom_mode_gestion"):
        m2 = re.search(r"Standard\s*[:\-]\s*([^\n\t,|]{3,40})", texte, re.IGNORECASE)
        if m2:
            val = _nettoyer_chaine(_couper_avant_label(m2.group(1)))
            if val:
                champs["custom_mode_gestion"]     = val
                confiances["custom_mode_gestion"] = 0.82

    m = re.search(
        r"Stock\s*<\s*0\s*autoris[eé]\s*[:\-]?\s*(Oui|Non|yes|no|true|false|\d)",
        texte, re.IGNORECASE
    )
    if m:
        v = m.group(1).strip().lower()
        champs["custom_stock_negatif"]     = "1" if v in ("oui", "yes", "true", "1") else "0"
        confiances["custom_stock_negatif"] = 0.88

    m = re.search(r"Tra[çc]abilit[eé]\s*[:\-]?\s*([^\n\t,|]{3,60})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_tracabilite"]     = val[:60]
            confiances["custom_tracabilite"] = 0.85

    m = re.search(r"Titre\s*\(?en\s*%\)?\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        try:
            v = float(m.group(1).replace(",", ".").strip())
            if v != 0:
                champs["custom_titre_pct"]     = m.group(1).strip()
                confiances["custom_titre_pct"] = 0.85
        except ValueError:
            pass

    m = re.search(r"Coefficient\s+DLU\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        try:
            v_dlu = float(m.group(1).replace(",", ".").strip())
            if v_dlu != 0:
                champs["custom_coef_dlu"]     = m.group(1).strip()
                confiances["custom_coef_dlu"] = 0.85
        except ValueError:
            pass

    m = re.search(r"Article\s+remplacement\s*[:\-][ \t]*([A-Z0-9][^\n\t,|]{0,50})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and len(val) >= 2 and not _SAGE_LABEL_GUARD.match(val):
            champs["custom_article_remplacement"]     = val[:80]
            confiances["custom_article_remplacement"] = 0.85

    m = re.search(r"Gestion\s+(?:de\s+)?p[eé]remption\s*[:\-]?\s*([^\n\t,|]{3,60})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_gestion_peremption"]     = val[:60]
            confiances["custom_gestion_peremption"] = 0.85

    m = re.search(r"Statut\s+(?:p[eé]remption|recontr[oô]le)?\s*[:\-]?\s*([^\n\t,|]{2,60})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and val.lower() not in ("actif", "inactif"):
            champs["custom_statut_peremption"]     = val[:60]
            confiances["custom_statut_peremption"] = 0.80

    m = re.search(
        r"D[eé]lai\s+(?:p[eé]remption\s*)?[:\-]?\s*([\d.,]+)\s*(?:J\.?\s*cal[eé]ndaires?|jours?|J\.)",
        texte, re.IGNORECASE
    )
    if m:
        champs["custom_delai_peremption"]     = m.group(1).strip()
        confiances["custom_delai_peremption"] = 0.82

    m = re.search(r"D[eé]lai\s+recontr[oô]le\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        champs["custom_delai_recontrol"]     = m.group(1).strip()
        confiances["custom_delai_recontrol"] = 0.82

    m = re.search(r"Statut\s+recontr[oô]le\s*[:\-]?\s*([^\n\t,|]{2,60})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_statut_recontrol"]     = val[:60]
            confiances["custom_statut_recontrol"] = 0.80

    m = re.search(
        r"Article\s+remplacement[^\n]{0,60}\n[^\n]*D[eé]signation\s*[:\-]?\s*([^\n\t,|]{2,120})",
        texte, re.IGNORECASE
    )
    if not m:
        m = re.search(
            r"D[eé]signation\s+remplacement\s*[:\-]?\s*([^\n\t,|]{2,120})",
            texte, re.IGNORECASE
        )
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and not _SAGE_LABEL_GUARD.match(val):
            champs["custom_designation_remplacement"]     = val[:120]
            confiances["custom_designation_remplacement"] = 0.80

    m = re.search(
        r"Co[uû]ts?\s+Famille\s*[:\-]?\s*([^\n\t,|]{3,60})"
        r"|Famille\s*[:\-]?\s*(Co[uû]t\s+[^\n\t,|]{2,50})",
        texte, re.IGNORECASE
    )
    if m:
        val = _nettoyer_chaine(m.group(1) or m.group(2))
        if val:
            champs["custom_famille_cout"]     = val[:60]
            confiances["custom_famille_cout"] = 0.82

    m = re.search(r"Compteur\s+lot\s*[:\-]\s*([A-Z0-9][A-Z0-9\-_]{0,19})\b", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and not _SAGE_LABEL_GUARD.match(val):
            champs["custom_compteur_lot"]     = val[:40]
            confiances["custom_compteur_lot"] = 0.82

    m = re.search(r"Compteur\s+s[eé]rie\s*[:\-]\s*([A-Z0-9][A-Z0-9\-_]{0,19})\b", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and not _SAGE_LABEL_GUARD.match(val):
            champs["custom_compteur_serie"]     = val[:40]
            confiances["custom_compteur_serie"] = 0.82


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS SAGE ERP — ONGLET UNITÉS (CORRIGÉ)
# ──────────────────────────────────────────────────────────────────────

def _extraire_unites_avancees(texte, lignes, champs, confiances):
    """
    CORRIGÉ v5 : Filtrage strict des valeurs par défaut non significatives.
    - Densité = 0          → ne pas extraire
    - Volume US = 0        → ne pas extraire
    - Coef UA-US = 1.000   → ne pas extraire (pas de conversion)
    - Coef UV-US = 1.000   → ne pas extraire
    - Coef Ustat-US = 1.000 → ne pas extraire
    - Coef UCEE-US = 0 ou 1 → ne pas extraire
    - Unité statistique = "Unité" → ne pas extraire (trop générique)
    - Unité CEE = "Unité"  → ne pas extraire
    - Unité conditionnement = "Unité" → ne pas extraire (déjà géré dans _extraire_unites_sage)
    """
    def _pf(s):
        try:
            return float(str(s).strip().replace(",", ".").replace(" ", ""))
        except Exception:
            return None

    # Densité
    m = re.search(r"Densit[eé]\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pf(m.group(1))
        # CORRECTION : ne pas extraire si 0 (valeur par défaut)
        if v is not None and v != 0:
            champs["custom_densite"]     = m.group(1).strip()
            confiances["custom_densite"] = 0.85

    # Volume de l'US
    m = re.search(r"Volume\s+de\s+l[''']?US\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pf(m.group(1))
        # CORRECTION : ne pas extraire si 0
        if v is not None and v != 0:
            champs["custom_volume_us"]     = m.group(1).strip()
            confiances["custom_volume_us"] = 0.85

    # Format étiquette US
    m = re.search(r"Format\s+[eé]tiquette\s+US\s*[:\-]?\s*([^\n\t,|]{1,40})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_format_etiquette_us"]     = val[:40]
            confiances["custom_format_etiquette_us"] = 0.80

    # Coef UA-US
    m = re.search(r"Coef(?:ficient)?\s+UA[-\s]?US\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pf(m.group(1))
        # CORRECTION : ne pas extraire si 1.000 (valeur par défaut = pas de conversion)
        if v is not None and v != 1.0 and v != 0:
            champs["custom_coef_ua_us"]     = str(round(v, 6))
            confiances["custom_coef_ua_us"] = 0.88

    # Coef UV-US
    m = re.search(r"Coef(?:ficient)?\s+UV[-\s]?US\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pf(m.group(1))
        # CORRECTION : ne pas extraire si 1.000
        if v is not None and v != 1.0 and v != 0:
            champs["custom_coef_uv_us"]     = str(round(v, 6))
            confiances["custom_coef_uv_us"] = 0.88

    # Unité statistique
    m = re.search(r"Unit[eé]\s+statistique\s*[:\-]?\s*([A-Za-z]{1,10})", texte, re.IGNORECASE)
    if m:
        udm = _normaliser_udm(m.group(1))
        # CORRECTION : ne pas extraire "Unité" (trop générique, valeur par défaut Sage)
        if udm and udm.lower() not in ('unité', 'unite', 'unit', 'u'):
            champs["custom_uom_stat"]     = udm
            confiances["custom_uom_stat"] = 0.85

    # Coef Ustat-US
    m = re.search(r"Coef(?:ficient)?\s+Ustat[-\s]?US\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pf(m.group(1))
        # CORRECTION : ne pas extraire si 1.000
        if v is not None and v != 1.0 and v != 0:
            champs["custom_coef_ustat_us"]     = str(round(v, 6))
            confiances["custom_coef_ustat_us"] = 0.88

    # Unité CEE
    m = re.search(r"Unit[eé]\s+CEE\s*[:\-]?\s*([A-Za-z]{1,10})", texte, re.IGNORECASE)
    if m:
        udm = _normaliser_udm(m.group(1))
        # CORRECTION : ne pas extraire "Unité" (valeur par défaut)
        if udm and udm.lower() not in ('unité', 'unite', 'unit', 'u'):
            champs["custom_uom_cee"]     = udm
            confiances["custom_uom_cee"] = 0.85

    # Coef UCEE-US
    m = re.search(r"Coef(?:ficient)?\s+UCEE[-\s]?US\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pf(m.group(1))
        # CORRECTION : 0 ou 1.000 = non défini dans Sage ERP → ne pas extraire
        if v is not None and v != 0 and v != 1.0:
            champs["custom_coef_ucee_us"]     = str(round(v, 6))
            confiances["custom_coef_ucee_us"] = 0.88

    # Unité Volume
    m = re.search(r"Unit[eé]\s+[Vv]olume\s*[:\-]?\s*([A-Za-z]{1,10})", texte, re.IGNORECASE)
    if m:
        udm = _normaliser_udm(m.group(1))
        # CORRECTION : ne pas extraire "Unité"
        if udm and udm.lower() not in ('unité', 'unite', 'unit', 'u'):
            champs["custom_unite_volume"]     = udm
            confiances["custom_unite_volume"] = 0.85

    # Modifiable (coef UV-US)
    if re.search(r"[Mm]odifiable", texte):
        champs["custom_modifiable_uv"]     = "1"
        confiances["custom_modifiable_uv"] = 0.70


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS SAGE ERP — ONGLET COMPTABILITÉ
# ──────────────────────────────────────────────────────────────────────

def _extraire_comptabilite_sage(texte, lignes, champs, confiances):
    m = re.search(
        r"Code\s+comptable\s*[:\-]?\s*([A-Z0-9]{1,20})(?:\s+([A-Z0-9]{1,20}))?",
        texte, re.IGNORECASE
    )
    if m:
        champs["custom_code_comptable"]     = m.group(1).strip()
        confiances["custom_code_comptable"] = 0.88
        if m.group(2):
            champs["custom_libelle_comptable"]     = m.group(2).strip()
            confiances["custom_libelle_comptable"] = 0.85

    m = re.search(
        r"Niveau\s+taxe\s*[:\-]?\s*([A-Z0-9]{1,10})(?:\s+([A-Za-zÀ-ÿ][^\n\t,|]{2,39}))?",
        texte, re.IGNORECASE
    )
    if m:
        champs["custom_niveau_taxe"]     = m.group(1).strip()
        confiances["custom_niveau_taxe"] = 0.88
        if m.group(2):
            val = _nettoyer_chaine(m.group(2))
            if val:
                champs["custom_libelle_taxe"]     = val[:40]
                confiances["custom_libelle_taxe"] = 0.85

    if re.search(r"[Ii]mmobilisable", texte):
        champs["custom_immobilisable"]     = "1"
        confiances["custom_immobilisable"] = 0.80


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS SAGE ERP — ONGLET VENTE
# ──────────────────────────────────────────────────────────────────────

def _extraire_donnees_vente_sage(texte, lignes, champs, confiances):
    def _pv(s):
        s = re.sub(r'\s*(?:DT|TND|€|\$|EUR|HT|TTC)\s*', '', s or '', flags=re.IGNORECASE).strip()
        try:
            return float(s.replace(",", ".").replace(" ", ""))
        except Exception:
            return None

    m = re.search(r"Prix\s+(?:de\s+)?base\s*[:\-]?\s*([\d\s.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pv(m.group(1))
        if v is not None and v > 0 and "standard_rate" not in champs:
            champs["standard_rate"]     = str(round(v, 4))
            confiances["standard_rate"] = 0.88

    m = re.search(r"Quantit[eé]\s+minimale\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pv(m.group(1))
        if v is not None and v > 0:
            champs["min_order_qty"]     = str(round(v, 3))
            confiances["min_order_qty"] = 0.85

    m = re.search(r"Quantit[eé]\s+maximale\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pv(m.group(1))
        if v is not None and v > 0:
            champs["custom_qte_max_vente"]     = str(round(v, 3))
            confiances["custom_qte_max_vente"] = 0.85

    m = re.search(r"Tol[eé]rance\s+reliquat\s*%?\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        try:
            v = float(m.group(1).replace(",", ".").strip())
            if v != 0:
                champs["custom_tolerance_reliquat"]     = m.group(1).strip()
                confiances["custom_tolerance_reliquat"] = 0.85
        except ValueError:
            pass

    m = re.search(r"Marge\s+minimale\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pv(m.group(1))
        if v is not None and v != 0:
            champs["custom_marge_minimale"]     = str(round(v, 4))
            confiances["custom_marge_minimale"] = 0.85

    m = re.search(r"Prix\s+th[eé]orique\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pv(m.group(1))
        if v is not None and v != 0:
            champs["custom_prix_theorique"]     = str(round(v, 4))
            confiances["custom_prix_theorique"] = 0.85

    m = re.search(r"Prix\s+plancher\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pv(m.group(1))
        if v is not None and v != 0:
            champs["custom_prix_plancher"]     = str(round(v, 4))
            confiances["custom_prix_plancher"] = 0.85

    m = re.search(r"Garantie\s+en\s+mois\s*[:\-]?\s*(\d+)", texte, re.IGNORECASE)
    if m:
        champs["warranty_period"]     = m.group(1).strip()
        confiances["warranty_period"] = 0.90

    m = re.search(r"Article\s+substitution\s*[:\-]?\s*([A-Z0-9][^\n\t,|]{0,50})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and len(val) >= 2:
            champs["custom_article_substitution"]     = val[:80]
            confiances["custom_article_substitution"] = 0.85

    m = re.search(r"Unit[eé]\s+de\s+vente\s*[:\-]?\s*([A-Za-z]{1,10})", texte, re.IGNORECASE)
    if m and "sales_uom" not in champs:
        udm = _normaliser_udm(m.group(1))
        if udm:
            champs["sales_uom"]     = udm
            confiances["sales_uom"] = 0.85

    _TYPES_COMPO = [
        (r"Compos[eé]\s+nomenclature", "Composé nomenclature"),
        (r"Compos[eé]\s+kit",          "Composé kit"),
        (r"Article\s+normal",          "Article normal"),
    ]
    for pat_tc, label_tc in _TYPES_COMPO:
        if re.search(pat_tc, texte, re.IGNORECASE):
            champs["custom_type_composition"]     = label_tc
            confiances["custom_type_composition"] = 0.85
            break

    m = re.search(
        r"Date\s+substitution\s*[:\-]?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}[\-/]\d{2}[\-/]\d{2})",
        texte, re.IGNORECASE
    )
    if m:
        champs["custom_date_substitution"]     = m.group(1).strip()
        confiances["custom_date_substitution"] = 0.85

    if re.search(r"Autorisation\s+pr[eê]t", texte, re.IGNORECASE):
        champs["custom_autorisation_pret"]     = "1"
        confiances["custom_autorisation_pret"] = 0.80

    if re.search(r"Contremarque", texte, re.IGNORECASE):
        champs["custom_contremarque_vente"]     = "1"
        confiances["custom_contremarque_vente"] = 0.75

    m = re.search(r"Qt[eé]\s+directe\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        try:
            v = float(m.group(1).replace(",", ".").replace(" ", ""))
            if v != 0:
                champs["custom_qte_directe"]     = str(round(v, 3))
                confiances["custom_qte_directe"] = 0.85
        except Exception:
            pass

    if re.search(r"Texte\s+vente", texte, re.IGNORECASE):
        champs["custom_texte_vente"]     = "1"
        confiances["custom_texte_vente"] = 0.75


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS SAGE ERP — ONGLET APPRO / STOCK SITE
# ──────────────────────────────────────────────────────────────────────

def _extraire_appro_stock(texte, lignes, champs, confiances):
    def _pi(s):
        try:
            return int(float(str(s).strip().replace(",", ".").replace(" ", "")))
        except Exception:
            return None

    def _derniere_valeur_non_nulle(patron: str):
        vals = [_pi(x) for x in re.findall(patron, texte, re.IGNORECASE)]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        non_nuls = [v for v in vals if v != 0]
        return non_nuls[-1] if non_nuls else vals[-1]

    sites_appro = []
    blocs_site = re.split(r"(?=Stock\s+site\s*[:\-])", texte, flags=re.IGNORECASE)
    for bloc in blocs_site:
        m_site = re.match(
            r"Stock\s+site\s*[:\-]\s*([A-Z0-9]{2,10})[ \t]+([^\n]+)",
            bloc, re.IGNORECASE
        )
        if not m_site:
            continue
        code_site  = m_site.group(1).strip().upper()
        label_site = _nettoyer_chaine(m_site.group(2))

        def _pis(patron):
            m2 = re.search(patron, bloc, re.IGNORECASE)
            return _pi(m2.group(1)) if m2 else None

        sec   = _pis(r"Stock\s+s[eé]curit[eé]\s*[:\-]?\s*([\d.,]+)")
        maxi  = _pis(r"Stock\s+maximum\s*[:\-]?\s*([\d.,]+)")
        seuil = _pis(r"Seuil\s+de\s+r[eé]appro(?:visionnement)?\s*[:\-]?\s*([\d.,]+)")
        qmin  = _pis(r"Qt[eé]\s+mini\s+r[eé]appro(?:visionnement)?\s*[:\-]?\s*([\d.,]+)")
        lot   = _pis(r"Taille\s+du\s+lot\s*[:\-]?\s*([\d.,]+)")

        m_abc = re.search(r"Cat[eé]gorie\s+ABC\s*[:\-]?[ \t]*([^\n\t,|]{2,40})", bloc, re.IGNORECASE)
        abc   = _nettoyer_chaine(_couper_avant_label(m_abc.group(1))) if m_abc else None

        m_inv = re.search(r"Mode\s+inventaire\s*[:\-]?[ \t]*([^\n\t,|]{3,60})", bloc, re.IGNORECASE)
        inv   = _nettoyer_chaine(_couper_avant_label(m_inv.group(1), maxlen=60)) if m_inv else None

        m_ret = re.search(r"Mode\s+retrait(?:\s+de\s+stock)?\s*[:\-]?[ \t]*([^\n\t,|]{3,60})", bloc, re.IGNORECASE)
        ret   = _nettoyer_chaine(_couper_avant_label(m_ret.group(1), maxlen=60)) if m_ret else None

        m_emp = re.search(r"Gestion\s+emplacement\s*[:\-]?[ \t]*([^\n\t,|]{2,20})", bloc, re.IGNORECASE)
        emp   = bool(re.search(r"oui|yes|1|true", m_emp.group(1), re.IGNORECASE)) if m_emp else False

        sites_appro.append({
            "code":                 code_site,
            "label":                label_site,
            "safety_stock":         sec if sec is not None else 0,
            "stock_max":            maxi if maxi is not None else 0,
            "reorder_level":        seuil if seuil is not None else 0,
            "reorder_qty":          qmin if qmin is not None else 0,
            "lot_size":             lot if lot is not None else 0,
            "categorie_abc":        abc or "",
            "mode_inventaire":      inv or "",
            "mode_retrait":         ret or "",
            "gestion_emplacement":  emp,
        })

    if sites_appro:
        import json as _json
        champs["custom_sites_appro"]     = _json.dumps(sites_appro, ensure_ascii=False)
        confiances["custom_sites_appro"] = 0.85

        non_nul_safety = [s["safety_stock"] for s in sites_appro if s["safety_stock"] != 0]
        non_nul_max    = [s["stock_max"]     for s in sites_appro if s["stock_max"]     != 0]
        non_nul_seuil  = [s["reorder_level"] for s in sites_appro if s["reorder_level"] != 0]
        non_nul_qmin   = [s["reorder_qty"]   for s in sites_appro if s["reorder_qty"]   != 0]

        if non_nul_safety:
            champs["safety_stock"]         = str(non_nul_safety[-1])
            confiances["safety_stock"]     = 0.85
        if non_nul_max:
            champs["custom_stock_max"]     = str(non_nul_max[-1])
            confiances["custom_stock_max"] = 0.85
        if non_nul_seuil:
            champs["custom_seuil_reappro"]     = str(non_nul_seuil[-1])
            confiances["custom_seuil_reappro"] = 0.85
        if non_nul_qmin:
            champs["custom_qte_mini_reappro"]     = str(non_nul_qmin[-1])
            confiances["custom_qte_mini_reappro"] = 0.85

        for site in sites_appro:
            if site["categorie_abc"] and "custom_categorie_abc" not in champs:
                champs["custom_categorie_abc"]     = site["categorie_abc"][:40]
                confiances["custom_categorie_abc"] = 0.85
            if site["mode_inventaire"] and "custom_mode_inventaire" not in champs:
                champs["custom_mode_inventaire"]     = site["mode_inventaire"]
                confiances["custom_mode_inventaire"] = 0.85
    else:
        v = _derniere_valeur_non_nulle(r"Stock\s+s[eé]curit[eé]\s*[:\-]?\s*([\d.,]+)")
        if v is not None:
            champs["safety_stock"]     = str(v)
            confiances["safety_stock"] = 0.85

        v = _derniere_valeur_non_nulle(r"Stock\s+maximum\s*[:\-]?\s*([\d.,]+)")
        if v is not None:
            champs["custom_stock_max"]     = str(v)
            confiances["custom_stock_max"] = 0.85

        v = _derniere_valeur_non_nulle(r"Seuil\s+de\s+r[eé]appro(?:visionnement)?\s*[:\-]?\s*([\d.,]+)")
        if v is not None:
            champs["custom_seuil_reappro"]     = str(v)
            confiances["custom_seuil_reappro"] = 0.85

        m = re.search(r"Qt[eé]\s+mini\s+r[eé]appro(?:visionnement)?\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
        if m:
            v = _pi(m.group(1))
            if v is not None and v != 0:
                champs["custom_qte_mini_reappro"]     = str(v)
                confiances["custom_qte_mini_reappro"] = 0.85

    _lots = [_pi(x) for x in re.findall(r"Taille\s+du\s+lot\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)]
    _lots = [v for v in _lots if v is not None]
    if _lots:
        _non_nuls_lot = [v for v in _lots if v != 0]
        v_lot = _non_nuls_lot[-1] if _non_nuls_lot else _lots[-1]
        champs["custom_taille_lot"]     = str(v_lot)
        confiances["custom_taille_lot"] = 0.85

    if "custom_categorie_abc" not in champs:
        m = re.search(r"Cat[eé]gorie\s+ABC\s*[:\-]?[ \t]*([^\n\t,|]{2,40})", texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(_couper_avant_label(m.group(1)))
            if val:
                champs["custom_categorie_abc"]     = val[:40]
                confiances["custom_categorie_abc"] = 0.85

    if "custom_mode_inventaire" not in champs:
        m = re.search(r"Mode\s+inventaire\s*[:\-]?[ \t]*([^\n\t,|]{3,60})", texte, re.IGNORECASE)
        if m:
            val = _nettoyer_chaine(_couper_avant_label(m.group(1), maxlen=60))
            if val:
                champs["custom_mode_inventaire"]     = val
                confiances["custom_mode_inventaire"] = 0.85

    m = re.search(r"Mode\s+retrait\s+de\s+stock\s*[:\-]?[ \t]*([^\n\t,|]{3,40})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(_couper_avant_label(m.group(1)))
        if val:
            champs["custom_mode_retrait"]     = val
            confiances["custom_mode_retrait"] = 0.85

    m = re.search(r"Gestion\s+emplacement\s*[:\-]?\s*(Oui|Non|yes|no|1|0)", texte, re.IGNORECASE)
    if m:
        v = m.group(1).strip().lower()
        champs["custom_gestion_emplacement"]     = "1" if v in ("oui", "yes", "1") else "0"
        confiances["custom_gestion_emplacement"] = 0.85

    m = re.search(r"Acheteur\s*/\s*approv\.?[ \t]*[:\-][ \t]*([^\n\t,|]{2,60})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and not _SAGE_LABEL_GUARD.match(val):
            champs["custom_acheteur_approv"]     = val[:60]
            confiances["custom_acheteur_approv"] = 0.82


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS SAGE ERP — ONGLET FOURNISSEURS
# ──────────────────────────────────────────────────────────────────────

def _extraire_fournisseur_article(texte, lignes, champs, confiances):
    m = re.search(
        r"Fournisseur\s*[:\-]?\s*([A-Z0-9]{2,20})\s+([A-Za-zÀ-ÿ][^\n\t]{2,79})",
        texte, re.IGNORECASE
    )
    if m:
        code_f = m.group(1).strip()
        lib_f  = _nettoyer_chaine(m.group(2))
        champs["custom_fournisseur_principal"]     = f"{code_f} - {lib_f}" if lib_f else code_f
        confiances["custom_fournisseur_principal"] = 0.82

    m = re.search(r"Article\s+fournisseur\s*[:\-]?\s*([A-Za-z0-9][^\n\t,|]{0,50})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and len(val) >= 2:
            champs["custom_ref_fournisseur"]     = val[:60]
            confiances["custom_ref_fournisseur"] = 0.85

    m = re.search(r"Code\s+EAN\s+fournisseur\s*[:\-]?\s*([0-9]{8,14})", texte, re.IGNORECASE)
    if m:
        champs["custom_ean_fournisseur"]     = m.group(1).strip()
        confiances["custom_ean_fournisseur"] = 0.88

    m = re.search(r"Qt[eé]\s+(?:minimum|min(?:imum)?)\s+achat\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        try:
            v = float(m.group(1).replace(",", ".").replace(" ", ""))
            if v > 0:
                champs["min_order_qty"]     = str(round(v, 3))
                confiances["min_order_qty"] = max(confiances.get("min_order_qty", 0), 0.85)
        except Exception:
            pass

    m = re.search(r"Majoration\s+CEE\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        try:
            v = float(m.group(1).replace(",", ".").strip())
            if v != 0:
                champs["custom_majoration_cee"]     = m.group(1).strip()
                confiances["custom_majoration_cee"] = 0.80
        except ValueError:
            pass

    m = re.search(r"D[eé]lai\s+sous[-\s]traitance\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        try:
            v = float(m.group(1).replace(",", ".").strip())
            if v != 0:
                champs["custom_delai_sous_traitance"]     = m.group(1).strip()
                confiances["custom_delai_sous_traitance"] = 0.80
        except ValueError:
            pass

    m = re.search(r"[Bb]locage\s*[:\-]?\s*(Oui|Non|Achat|Vente|Tout|[A-Z][a-z]{1,10})", texte, re.IGNORECASE)
    if m:
        champs["custom_blocage_fournisseur"]     = m.group(1).strip()
        confiances["custom_blocage_fournisseur"] = 0.82

    m = re.search(r"[Cc]oef(?:ficient)?\s+frais\s+approche\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        try:
            v = float(m.group(1).replace(",", ".").replace(" ", ""))
            champs["custom_coef_frais_approche"]     = str(round(v, 6))
            confiances["custom_coef_frais_approche"] = 0.82
        except Exception:
            pass

    m = re.search(r"[Tt]hree[-\s]?way\s+match\s*[:\-]?\s*(Oui|Non|yes|no|\d)?", texte, re.IGNORECASE)
    if m:
        raw = (m.group(1) or "").strip().lower()
        champs["custom_three_way_match"]     = "1" if raw in ("oui", "yes", "1") else ("0" if raw in ("non", "no", "0") else "1")
        confiances["custom_three_way_match"] = 0.80

    m = re.search(r"[Cc]onditionnement\s*[:\-]?\s*([A-Za-z0-9][^\n\t,|]{0,40})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and not _SAGE_LABEL_GUARD.match(val):
            champs["custom_conditionnement_achat"]     = val[:40]
            confiances["custom_conditionnement_achat"] = 0.78

    m = re.search(r"[Cc]oef(?:ficient)?\s+UC[-\s]?UA\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        try:
            v = float(m.group(1).replace(",", ".").replace(" ", ""))
            if v != 1.0 and v != 0:
                champs["custom_coef_uc_ua"]     = str(round(v, 6))
                confiances["custom_coef_uc_ua"] = 0.85
        except Exception:
            pass

    m = re.search(r"[Pp]riorit[eé]\s*[:\-]?\s*([\d]+)", texte, re.IGNORECASE)
    if m:
        champs["custom_priorite_fournisseur"]     = m.group(1).strip()
        confiances["custom_priorite_fournisseur"] = 0.80

    m = re.search(r"[Nn]ote\s+qualit[eé]\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        champs["custom_note_qualite"]     = m.group(1).strip()
        confiances["custom_note_qualite"] = 0.82

    m = re.search(r"[Ss]oumis\s+[àa]\s+contr[oô]le\s*[:\-]?\s*([^\n\t,|]{2,60})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_soumis_controle"]     = val[:60]
            confiances["custom_soumis_controle"] = 0.82

    m = re.search(r"[Ff]r[eé]quence\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        champs["custom_frequence_controle"]     = m.group(1).strip()
        confiances["custom_frequence_controle"] = 0.80

    m = re.search(r"[Nn]um[eé]ro\s+contr[oô]le\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        champs["custom_numero_controle"]     = m.group(1).strip()
        confiances["custom_numero_controle"] = 0.80

    m = re.search(r"[Ff]iche\s+qualit[eé]\s*[:\-]?\s*([^\n\t,|]{1,80})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_fiche_qualite"]     = val[:80]
            confiances["custom_fiche_qualite"] = 0.80

    if re.search(r"[Cc]ontremarque", texte, re.IGNORECASE):
        if "custom_contremarque_vente" not in champs:
            champs["custom_contremarque_fournisseur"]     = "1"
            confiances["custom_contremarque_fournisseur"] = 0.72

    m = re.search(r"[Aa]lt(?:ernative)?\s+sous[-\s]traitance\s*[:\-]?\s*([^\n\t,|]{1,80})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_alt_sous_traitance"]     = val[:80]
            confiances["custom_alt_sous_traitance"] = 0.78


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS SAGE ERP — ONGLET APRÈS-VENTE
# ──────────────────────────────────────────────────────────────────────

def _extraire_apres_vente_sage(texte, lignes, champs, confiances):
    def _pv(s):
        try:
            return float(str(s).strip().replace(",", ".").replace(" ", ""))
        except Exception:
            return None

    if re.search(r"Cr[eé]ation\s+de\s+parc\s+client", texte, re.IGNORECASE):
        champs["custom_creation_parc_client"]     = "1"
        confiances["custom_creation_parc_client"] = 0.82

    m = re.search(r"Cat[eé]gorie\s+de\s+coupon\s*[:\-]?\s*([^\n\t,|]{1,60})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_categorie_coupon"]     = val[:60]
            confiances["custom_categorie_coupon"] = 0.80

    m = re.search(r"Contrat\s+de\s+pr[eê]t\s*[:\-]?\s*([^\n\t,|]{1,80})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_contrat_pret"]     = val[:80]
            confiances["custom_contrat_pret"] = 0.80

    m = re.search(r"Contrat\s+de\s+garantie\s*[:\-]?\s*([^\n\t,|]{1,80})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_contrat_garantie"]     = val[:80]
            confiances["custom_contrat_garantie"] = 0.80

    m = re.search(r"Contrat\s+de\s+service\s*[:\-]?\s*([^\n\t,|]{1,80})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_contrat_service"]     = val[:80]
            confiances["custom_contrat_service"] = 0.80

    m = re.search(r"D[eé]bit\s+de\s+points\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pv(m.group(1))
        if v is not None:
            champs["custom_debit_points"]     = str(round(v, 2))
            confiances["custom_debit_points"] = 0.82

    if re.search(r"[Vv]aleur\s+nulle\s+prise\s+en\s+compte", texte, re.IGNORECASE):
        champs["custom_valeur_nulle_points"]     = "1"
        confiances["custom_valeur_nulle_points"] = 0.78

    m = re.search(r"[Jj]etons?\s+[àa]\s+cr[eé]diter\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pv(m.group(1))
        if v is not None:
            champs["custom_jetons_crediter"]     = str(round(v, 2))
            confiances["custom_jetons_crediter"] = 0.82

    m = re.search(r"toutes\s+les\s+([\d.,]+\s*[^\n\t,|]{0,40})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_frequence_points"]     = val[:60]
            confiances["custom_frequence_points"] = 0.78

    m = re.search(
        r"Alternative\s+nomenclature\s+(?:pour\s+)?apr[eè]s[-\s]?vente\s*[:\-]?\s*([\d.,]+|[^\n\t,|]{1,80})",
        texte, re.IGNORECASE
    )
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_alt_nomenclature_sav"]     = val[:80]
            confiances["custom_alt_nomenclature_sav"] = 0.80

    m = re.search(r"Type\s+d['']\s*article\s*[:\-]?\s*([^\n\t,|]{2,40})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and not _SAGE_LABEL_GUARD.match(val):
            champs["custom_type_article_sav"]     = val[:40]
            confiances["custom_type_article_sav"] = 0.82

    if re.search(r"[Ss]ortie\s+de\s+stock\s+par\s+d[eé]faut", texte, re.IGNORECASE):
        champs["custom_sortie_stock_defaut"]     = "1"
        confiances["custom_sortie_stock_defaut"] = 0.80

    m = re.search(r"Unit[eé]\s+pour\s+les\s+jours\s*[:\-]?\s*([A-Za-z0-9]{1,10})", texte, re.IGNORECASE)
    if m:
        udm = _normaliser_udm(m.group(1))
        if udm:
            champs["custom_unite_jours"]     = udm
            confiances["custom_unite_jours"] = 0.80

    m = re.search(r"Unit[eé]\s+pour\s+les\s+heures\s*[:\-]?\s*([A-Za-z0-9]{1,10})", texte, re.IGNORECASE)
    if m:
        udm = _normaliser_udm(m.group(1))
        if udm:
            champs["custom_unite_heures"]     = udm
            confiances["custom_unite_heures"] = 0.80

    m = re.search(r"Unit[eé]\s+pour\s+les\s+minutes\s*[:\-]?\s*([A-Za-z0-9]{1,10})", texte, re.IGNORECASE)
    if m:
        udm = _normaliser_udm(m.group(1))
        if udm:
            champs["custom_unite_minutes"]     = udm
            confiances["custom_unite_minutes"] = 0.80

    m = re.search(r"[Cc]oef(?:ficient)?\s+[Jj]our\s*[-–]\s*[Hh]eures?\s*[:\-]?\s*([\d.,]+)", texte, re.IGNORECASE)
    if m:
        v = _pv(m.group(1))
        if v is not None:
            champs["custom_coef_jour_heures"]     = str(round(v, 6))
            confiances["custom_coef_jour_heures"] = 0.82


# ──────────────────────────────────────────────────────────────────────
# EXTRACTEURS SAGE ERP — ONGLET CLIENTS
# ──────────────────────────────────────────────────────────────────────

def _extraire_clients_sage(texte, lignes, champs, confiances):
    m = re.search(r"Article[-\s]?[Cc]lient\s*[:\-]?\s*([A-Za-z0-9][^\n\t,|]{0,60})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val and len(val) >= 2:
            champs["custom_article_client"]     = val[:80]
            confiances["custom_article_client"] = 0.82

    m = re.search(r"D[eé]signation\s+client\s*[:\-]?\s*([^\n\t,|]{2,120})", texte, re.IGNORECASE)
    if m:
        val = _nettoyer_chaine(m.group(1))
        if val:
            champs["custom_designation_client"]     = val[:120]
            confiances["custom_designation_client"] = 0.82

    if re.search(r"[Ii]nter[-\s]?sites?", texte, re.IGNORECASE):
        champs["custom_inter_sites_client"]     = "1"
        confiances["custom_inter_sites_client"] = 0.72


# ──────────────────────────────────────────────────────────────────────
# UTILITAIRES INTERNES
# ──────────────────────────────────────────────────────────────────────

def _normaliser_texte(texte: str) -> str:
    """
    Normalise le texte OCR brut : unifie les tirets, apostrophes,
    corrige les confusions O/0 et l/1 fréquentes en OCR, compacte les espaces.
    """
    t = texte
    t = re.sub(r"[‐‑‒–—−]", "-", t)
    t = re.sub(r"['`´]", "'", t)
    t = re.sub(r"[Oo](?=\d)", "0", t)
    t = re.sub(r"(?<=\d)[Oo]", "0", t)
    t = re.sub(r"\bl(?=\d)", "1", t)
    t = re.sub(r"\t", " ", t)
    t = re.sub(r" {2,}", " ", t)
    return t


def _nettoyer_code(val: str) -> str:
    """
    Nettoie une valeur de code article : conserve le premier token,
    supprime la ponctuation finale, vérifie la longueur (2–40 chars).
    Retourne "" si invalide.
    """
    val = val.strip()
    parts = val.split()
    if parts:
        val = parts[0]
    val = val.rstrip(".,;:/-")
    return val if (2 <= len(val) <= 40 and re.search(r'[A-Z0-9]', val, re.IGNORECASE)) else ""


def _nettoyer_chaine(val: str) -> str:
    """
    Nettoie une chaîne de caractères : supprime les espaces multiples,
    la ponctuation initiale/finale (.,;:-|/) et tronque à la 1ère ligne.
    """
    val = val.strip()
    val = re.sub(r'\s+', ' ', val)
    val = val.strip(".,;:-|/")
    if "\n" in val:
        val = val.split("\n")[0].strip()
    return val


def _normaliser_udm(val: str) -> str:
    """
    CORRIGÉ v5 : Retourne "" (chaîne vide) si la valeur n'est pas reconnue,
    au lieu de retourner la valeur brute ou "Nos" par défaut.
    Cela évite d'injecter des UDM invalides dans ERPNext.
    """
    val_l = val.lower().strip()
    for udm_erpnext, variantes in _UDM_MAP.items():
        for v in variantes:
            try:
                if re.fullmatch(v.strip(r'\b'), val_l, re.IGNORECASE):
                    return udm_erpnext
                if val_l == v.strip(r'\b').lower():
                    return udm_erpnext
            except re.error:
                if val_l == v.lower():
                    return udm_erpnext
    # CORRECTION : retourner "" si non reconnu (pas de fallback "Nos")
    return ""


def _mapper_groupe(val: str):
    """
    Mappe une valeur texte vers un groupe ERPNext connu.
    Cherche d'abord dans _GROUPES_CONNUS (correspondance exacte),
    puis dans _MOTS_CLES_GROUPE (mots-clés). Retourne None si aucun match.
    """
    val_l = val.lower()
    for groupe in sorted(_GROUPES_CONNUS, key=len, reverse=True):
        if groupe.lower() in val_l or val_l in groupe.lower():
            return groupe
    for groupe, mots in _MOTS_CLES_GROUPE.items():
        for mc in mots:
            if mc.lower() in val_l:
                return groupe
    return None


def _resultat_vide():
    """
    Retourne le squelette d'un résultat vide avec tous les champs à None.
    Utilisé quand le texte d'entrée est vide ou non exploitable.
    """
    return {
        "champs": {
            "item_code":          None,
            "item_name":          None,
            "item_group":         None,
            "stock_uom":          None,
            "standard_rate":      None,
            "last_purchase_rate": None,
            "description":        None,
            "disabled":           None,
            "is_stock_item":      None,
            "has_batch_no":       None,
            "has_serial_no":      None,
            "weight_uom":         None,
            "weight_per_unit":    None,
            "purchase_uom":       None,
            "sales_uom":          None,
            "min_order_qty":      None,
            "safety_stock":       None,
            "warranty_period":    None,
            "barcode":            None,
            "valuation_method":   None,
            "valuation_rate":     None,
            "custom_designation2":       None,
            "custom_designation3":       None,
            "custom_cle_recherche":      None,
            "custom_ligne_produit":      None,
            "custom_norme":              None,
            "custom_ref_douaniere":      None,
            "custom_soumis_deb":         None,
            "custom_acces_gestionnaire": None,
            "custom_infos_produit":      None,
            "custom_texte_production":   None,
            "custom_texte_preparation":  None,
            "custom_nature":             None,
            "custom_carac_technique":    None,
            "custom_forme":              None,
            "custom_dim_long":           None,
            "custom_dim_larg":           None,
            "custom_epaisseur":          None,
            "custom_long_barre":         None,
            "custom_couleur_sup":        None,
            "custom_couleur_inf":        None,
            "custom_film":               None,
            "custom_type_tole":          None,
            "custom_mode_gestion":            None,
            "custom_stock_negatif":           None,
            "custom_tracabilite":             None,
            "custom_titre_pct":               None,
            "custom_coef_dlu":                None,
            "custom_article_remplacement":    None,
            "custom_designation_remplacement": None,
            "custom_gestion_lot_mode":        None,
            "custom_gestion_serie_mode":      None,
            "custom_gestion_peremption":      None,
            "custom_statut_peremption":       None,
            "custom_delai_peremption":        None,
            "custom_delai_recontrol":         None,
            "custom_statut_recontrol":        None,
            "custom_famille_cout":            None,
            "custom_compteur_lot":            None,
            "custom_compteur_serie":          None,
            "custom_densite":                 None,
            "custom_volume_us":               None,
            "custom_unite_volume":            None,
            "custom_format_etiquette_us":     None,
            "custom_coef_ua_us":              None,
            "custom_coef_uv_us":              None,
            "custom_modifiable_uv":           None,
            "custom_uom_stat":                None,
            "custom_coef_ustat_us":           None,
            "custom_uom_cee":                 None,
            "custom_coef_ucee_us":            None,
            "custom_code_comptable":          None,
            "custom_libelle_comptable":       None,
            "custom_niveau_taxe":             None,
            "custom_libelle_taxe":            None,
            "custom_immobilisable":           None,
            "custom_type_composition":        None,
            "custom_date_substitution":       None,
            "custom_qte_max_vente":           None,
            "custom_tolerance_reliquat":      None,
            "custom_marge_minimale":          None,
            "custom_prix_theorique":          None,
            "custom_prix_plancher":           None,
            "custom_article_substitution":    None,
            "custom_autorisation_pret":       None,
            "custom_contremarque_vente":      None,
            "custom_qte_directe":             None,
            "custom_texte_vente":             None,
            "custom_stock_max":               None,
            "custom_seuil_reappro":           None,
            "custom_qte_mini_reappro":        None,
            "custom_taille_lot":              None,
            "custom_categorie_abc":           None,
            "custom_mode_inventaire":         None,
            "custom_mode_retrait":            None,
            "custom_gestion_emplacement":     None,
            "custom_acheteur_approv":         None,
            "custom_methode_valorisation":    None,
            "custom_sites_appro":             None,
            "custom_fournisseur_principal":       None,
            "custom_ref_fournisseur":             None,
            "custom_ean_fournisseur":             None,
            "custom_majoration_cee":              None,
            "custom_delai_sous_traitance":        None,
            "custom_blocage_fournisseur":         None,
            "custom_coef_frais_approche":         None,
            "custom_three_way_match":             None,
            "custom_conditionnement_achat":       None,
            "custom_coef_uc_ua":                  None,
            "custom_priorite_fournisseur":        None,
            "custom_note_qualite":                None,
            "custom_soumis_controle":             None,
            "custom_frequence_controle":          None,
            "custom_numero_controle":             None,
            "custom_fiche_qualite":               None,
            "custom_contremarque_fournisseur":    None,
            "custom_alt_sous_traitance":          None,
            "custom_creation_parc_client":        None,
            "custom_categorie_coupon":            None,
            "custom_contrat_pret":                None,
            "custom_contrat_garantie":            None,
            "custom_contrat_service":             None,
            "custom_debit_points":                None,
            "custom_valeur_nulle_points":         None,
            "custom_jetons_crediter":             None,
            "custom_frequence_points":            None,
            "custom_alt_nomenclature_sav":        None,
            "custom_type_article_sav":            None,
            "custom_sortie_stock_defaut":         None,
            "custom_unite_jours":                 None,
            "custom_unite_heures":                None,
            "custom_unite_minutes":               None,
            "custom_coef_jour_heures":            None,
            "custom_article_client":              None,
            "custom_designation_client":          None,
            "custom_inter_sites_client":          None,
        },
        "confiances":    {},
        "type_document": "inconnu",
    }