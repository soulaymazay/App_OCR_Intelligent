# -*- coding: utf-8 -*-
"""
excel_facture_parser.py — Groupe Bayoudh Metal  v2.0
Correctifs :
  - Extraction cellule par cellule (lecture structurée du tableau)
  - Chaque cellule est analysée avec son contexte propre (colonne voisine gauche)
  - Évite la pollution entre valeurs sur la même ligne
  - Filtre renforcé pour les numéros fiscaux (MF, TVA:, RC:, etc.)
"""

import re


# ──────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ──────────────────────────────────────────────────────────────────────

def parser_facture_excel(chemin_xlsx: str) -> dict:
    """
    Parse un fichier Excel de facture et retourne les champs structurés.

    Stratégie double :
      1. Extraction structurée cellule par cellule (_extraire_champs_excel_direct)
         → analyse le label dans la cellule à gauche pour associer valeur/champ
      2. Fallback textuel aplati (_extraire_champs_facture) via regex
    Les résultats structurés sont prioritaires sur le fallback.

    Retourne :
      { success, type_document, champs_remplis, score_confiance, methode_ocr,
        texte_extrait, message } ou { success: False, erreur: str }
    """
    try:
        import pandas as pd
    except ImportError:
        return {"success": False, "erreur": "pandas non disponible — pip install pandas openpyxl"}

    try:
        xls = pd.ExcelFile(chemin_xlsx, engine="openpyxl")
        textes_feuilles = []
        champs_directs = {}  # Extraction structurée cellule-par-cellule

        for nom_feuille in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=nom_feuille, header=None, dtype=str)
                # Extraction structurée (nouvelle méthode)
                champs_feuille = _extraire_champs_excel_direct(df)
                for k, v in champs_feuille.items():
                    if k not in champs_directs:
                        champs_directs[k] = v
                # Texte aplati pour fallback
                texte_feuille = _dataframe_vers_texte(df)
                if texte_feuille.strip():
                    textes_feuilles.append(texte_feuille)
            except Exception:
                continue

        if not textes_feuilles and not champs_directs:
            return {"success": False, "erreur": "Aucune donnée lisible dans le fichier Excel."}

        texte_complet = "\n".join(textes_feuilles)

        # Fusionner extraction directe + fallback textuel
        champs_texte = _extraire_champs_facture(texte_complet)
        champs_fusionnes = {**champs_texte, **champs_directs}  # directs prioritaires

        champs_remplis = _mapper_champs_frappe(champs_fusionnes)

        if not champs_remplis:
            return {
                "success": False,
                "erreur": "Fichier Excel lu mais aucun champ de facture extrait.",
                "texte_extrait": texte_complet[:500],
            }

        return {
            "success":        True,
            "type_document":  "facture",
            "champs_remplis": champs_remplis,
            "score_confiance": 97,
            "methode_ocr":    "excel_direct",
            "texte_extrait":  texte_complet[:500],
            "message": "{} champ(s) extrait(s) depuis Excel".format(len(champs_remplis)),
        }

    except Exception as e:
        return {"success": False, "erreur": "Erreur lecture Excel : {}".format(str(e))}


# ──────────────────────────────────────────────────────────────────────
# EXTRACTION STRUCTURÉE CELLULE PAR CELLULE (v2.0 — nouveau)
# ──────────────────────────────────────────────────────────────────────

# Mots-clés de ligne/colonne à EXCLURE (numéros non-montants)
_CONTEXTES_EXCLUS_CELLULE = [
    "mf", "matricule", "rib", "iban", "bic", "swift",
    "téléphone", "telephone", "tél", "tel", "fax",
    "registre", "siret", "siren", "ice",
    "tva :", "tva:", "n° tva", "n°tva", "n°fiscal", "fiscal",
    "rc :", "rc:", "code postal", "bp ", "b.p",
]

def _est_contexte_exclu(label: str) -> bool:
    """Retourne True si le label correspond à un contexte à exclure (MF, RIB, TVA:, etc.)."""
    l = label.lower().strip()
    return any(exc in l for exc in _CONTEXTES_EXCLUS_CELLULE)

def _extraire_champs_excel_direct(df) -> dict:
    """
    Parcourt le DataFrame ligne par ligne, colonne par colonne.
    Pour chaque cellule numérique, cherche un label dans la cellule à gauche
    (même ligne) ou dans une ligne de header proche au-dessus.
    """
    champs = {}
    nrows, ncols = df.shape

    for i in range(nrows):
        for j in range(ncols):
            val_str = str(df.iloc[i, j]).strip()
            if not val_str or val_str.lower() in ("nan", "none", ""):
                continue

            montant = _parse_montant_cellule(val_str)
            if montant is None:
                continue

            # Label = cellule à gauche
            label = ""
            if j > 0:
                label_raw = str(df.iloc[i, j - 1]).strip()
                if label_raw.lower() not in ("nan", "none", ""):
                    label = label_raw

            # Si pas de label à gauche, chercher sur la même ligne (première cellule non vide)
            if not label:
                for jj in range(j - 1, -1, -1):
                    c = str(df.iloc[i, jj]).strip()
                    if c and c.lower() not in ("nan", "none", ""):
                        label = c
                        break

            if _est_contexte_exclu(label):
                continue

            role = _role_montant_label(label)
            if role and role not in champs:
                champs[role] = montant

        # Extraction dates et références sur la ligne
        ligne_vals = [str(df.iloc[i, j]).strip() for j in range(ncols)
                      if str(df.iloc[i, j]).strip().lower() not in ("nan", "none", "")]
        for idx, cell in enumerate(ligne_vals):
            # Dates
            date_match = re.match(r'^(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})$', cell)
            if date_match:
                label = ligne_vals[idx - 1].lower() if idx > 0 else ""
                role = _role_date_label(label)
                if role not in champs:
                    champs[role] = cell

            # Références facture/BL
            ref_match = re.match(r'^([A-Z]{1,4}[-/]\d{4}[-/]\d+)$', cell)
            if ref_match:
                label = ligne_vals[idx - 1].lower() if idx > 0 else ""
                role = _role_ref_label(label)
                if role not in champs:
                    champs[role] = cell

    return champs


def _parse_montant_cellule(val: str):
    """Retourne float si val est un montant valide, None sinon."""
    val = val.strip()
    # Rejeter les valeurs qui ressemblent à des numéros (trop longs, pas de décimales)
    # ou qui contiennent des lettres
    if re.search(r'[A-Za-z%°]', val):
        return None
    # Formats acceptés : "1729.486", "1 729,486", "1729,486", "1,729.486"
    patterns = [
        (r'^\d{1,3}(?:[ \u00a0]\d{3})*[,]\d{2,3}$', 'espace_virgule'),
        (r'^\d{1,3}(?:[.]\d{3})+[,]\d{2,3}$', 'point_virgule_eu'),
        (r'^\d{1,3}(?:[,]\d{3})+[.]\d{2,3}$', 'virgule_point_en'),
        (r'^\d{1,6}[.]\d{2,3}$', 'point_decimal'),
        (r'^\d{1,6}[,]\d{2,3}$', 'virgule_decimal'),
    ]
    for pat, fmt in patterns:
        if re.match(pat, val):
            try:
                return _nettoyer_montant(val)
            except Exception:
                return None
    return None


def _role_montant_label(label: str) -> str:
    """
    Déduit le rôle d'un montant (ht, tva, ttc, remise, fodec, timbre)
    depuis le label de la cellule voisine.
    Retourne "" si le label ne correspond à aucun rôle connu.
    """
    l = label.lower().strip().rstrip(':').strip()
    if any(k in l for k in ["total ttc", "net à payer", "net a payer", "montant ttc"]):
        return "montant_ttc"
    if any(k in l for k in ["total taxe", "total taxes"]):
        return "montant_tva"
    if re.search(r'total\s+ht$', l) or l == "total ht":
        return "montant_ht"
    if any(k in l for k in ["ht brut", "total ht brut"]):
        return "montant_ht_brut"
    if re.search(r'\bremise\b', l):
        return "remise"
    if re.search(r'\btva\b', l) and "base" not in l:
        return "montant_tva_ligne"
    if any(k in l for k in ["fodec", "timbre", "base tva"]):
        return "montant_taxe_detail"
    if any(k in l for k in ["ht", "hors taxe", "hors-taxe"]):
        return "montant_ht"
    return None  # Pas de rôle clair → ignorer


def _role_date_label(label: str) -> str:
    if "livraison" in label:
        return "date_livraison"
    if "échéance" in label or "echeance" in label or "paiement" in label:
        return "date_echeance"
    if "commande" in label:
        return "date_commande"
    return "date"


def _role_ref_label(label: str) -> str:
    if any(k in label for k in ["facture", "fact", "invoice"]):
        return "numero_facture"
    if any(k in label for k in ["bl", "livraison"]):
        return "numero_bl"
    if any(k in label for k in ["commande", "bc"]):
        return "numero_commande"
    return "reference"


# ──────────────────────────────────────────────────────────────────────
# CONVERSION DATAFRAME → TEXTE (inchangé, pour fallback)
# ──────────────────────────────────────────────────────────────────────

def _dataframe_vers_texte(df) -> str:
    """
    Convertit un DataFrame pandas en texte aplati (fallback textuel).
    Formate chaque cellule via _formater_valeur_cellule et joint par espace.
    Les lignes vides (moins de 2 tokens) sont ignorées.
    """
    lignes = []
    for _, row in df.iterrows():
        parties = []
        for val in row:
            if val is None:
                continue
            s = str(val).strip()
            if not s or s.lower() in ("nan", "none", ""):
                continue
            s = _formater_valeur_cellule(s)
            parties.append(s)
        if parties:
            lignes.append("  ".join(parties))
    return "\n".join(lignes)


def _formater_valeur_cellule(val_str: str) -> str:
    try:
        if "e+" in val_str.lower() or "e-" in val_str.lower():
            f = float(val_str)
            if f == int(f):
                return str(int(f))
            return "{:.6g}".format(f)
        if "." in val_str and re.match(r'^-?\d+\.\d+0+$', val_str):
            f = float(val_str)
            if f == int(f):
                return str(int(f))
            return val_str.rstrip("0").rstrip(".")
        return val_str
    except (ValueError, TypeError):
        return val_str


# ──────────────────────────────────────────────────────────────────────
# EXTRACTION FALLBACK TEXTUEL (inchangé de v1.0)
# ──────────────────────────────────────────────────────────────────────

def _extraire_champs_facture(texte: str) -> dict:
    """
    Fallback textuel : extrait les champs de facture depuis un texte aplati
    en utilisant des patterns regex (numéro, date, montants, fournisseur).
    Moins précis que _extraire_champs_excel_direct mais couvre les cas mal structurés.
    """
    champs = {}
    champs.update(_extraire_dates(texte))
    champs.update(_extraire_montants(texte))
    champs.update(_extraire_references(texte))
    champs.update(_extraire_noms(texte))
    return champs


def _extraire_dates(texte: str) -> dict:
    """
    Extrait toutes les dates du texte et les classe par rôle (date, date_echeance).
    Déduplique par rôle : une seule date par rôle, la première rencontrée.
    """
    patterns = [
        r'\b(\d{2}[/\-.]\d{2}[/\-.]\d{4})\b',
        r'\b(\d{4}[/\-.]\d{2}[/\-.]\d{2})\b',
        r'\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b',
    ]
    vus = set()
    vus_roles = {}
    for p in patterns:
        for m in re.finditer(p, texte):
            val = m.group(1)
            if val in vus:
                continue
            vus.add(val)
            ctx = _contexte_fenetre(texte, m.start())
            role = _role_date_label(ctx)
            if role not in vus_roles:
                vus_roles[role] = val
    return vus_roles


def _extraire_montants(texte: str) -> dict:
    """
    Extrait tous les montants du texte Excel aplati et les classe par rôle
    (montant_ht, montant_tva, montant_ttc, remise, fodec, timbre).
    Exclut les numéros matricule, RIB, TVA:, téléphone.
    """
    PATTERNS_DECIMAL = [
        r'(\d{1,3}(?:[ \u00a0]\d{3})*[,]\d{2,3})',
        r'(\d{1,3}(?:[.]\d{3})+[,]\d{2,3})',
        r'(\d{1,3}(?:[,]\d{3})+[.]\d{2,3})',
        r'(?<!\d)(\d{1,6}[.]\d{2,3})(?!\d)',
    ]
    CONTEXTES_EXCLUS = [
        "mf ", "mf/", "matricule", "rib", "iban", "bic", "swift",
        "tél :", "tel :", "téléphone", "telephone", "fax",
        "registre", "code postal", "bp ", "b.p", "cp ",
        "siret", "siren", "ice",
        "n° tva", "n°tva", "tva :", "tva:", "n°fiscal",
        "rc :", "rc:",
    ]
    PRIORITE_ROLE = {
        "montant_ttc": 0, "montant_ht": 1, "montant_tva": 2,
        "remise": 3, "montant_ht_brut": 4, "montant_tva_ligne": 5,
        "montant_taxe_detail": 6, "montant": 7,
    }
    montants = []
    positions_couvertes = []
    for p in PATTERNS_DECIMAL:
        for m in re.finditer(p, texte, re.IGNORECASE):
            if any(ds <= m.start() < de for ds, de in positions_couvertes):
                continue
            val_brute = m.group(1)
            val = _nettoyer_montant(val_brute)
            if val <= 0 or val > 999_999:
                continue
            ligne = _contexte_ligne(texte, m.start())
            if any(exc in ligne for exc in CONTEXTES_EXCLUS):
                continue
            positions_couvertes.append((m.start(), m.end()))
            role = _role_montant_ligne_pos(texte, m.start(), ligne)
            montants.append({"valeur": val, "role": role})

    montants.sort(key=lambda x: PRIORITE_ROLE.get(x["role"], 99))
    vus_roles = {}
    for mt in montants:
        if mt["role"] not in vus_roles:
            vus_roles[mt["role"]] = mt["valeur"]

    if "montant_tva" not in vus_roles and "montant_tva_ligne" in vus_roles:
        vus_roles["montant_tva"] = vus_roles.pop("montant_tva_ligne")
    else:
        vus_roles.pop("montant_tva_ligne", None)

    if "montant_ttc" not in vus_roles and montants:
        vus_roles["montant_ttc"] = max(m["valeur"] for m in montants)

    if ("montant_ht" not in vus_roles
            and "montant_ttc" in vus_roles
            and "montant_tva" not in vus_roles):
        ttc = vus_roles["montant_ttc"]
        vus_roles["montant_ht"] = round(ttc / 1.19, 3)
        vus_roles["montant_tva"] = round(ttc - ttc / 1.19, 3)

    return vus_roles


def _role_montant_ligne_pos(texte: str, pos: int, ligne: str) -> str:
    """
    Détermine le rôle d'un montant en regardant UNIQUEMENT le texte
    qui précède sa position dans la ligne (contexte gauche).
    """
    debut = texte.rfind('\n', 0, pos)
    debut = debut + 1 if debut >= 0 else 0
    ctx_gauche = texte[debut:pos].lower().strip()

    if any(k in ctx_gauche for k in ["total ttc", "net à payer", "net a payer", "montant ttc"]):
        return "montant_ttc"
    if re.search(r'\bremise\b', ctx_gauche):
        return "remise"
    if re.search(r'total\s+ht\s*$', ctx_gauche) and "brut" not in ctx_gauche:
        return "montant_ht"
    if "ht brut" in ctx_gauche or ("total ht" in ctx_gauche and "brut" in ctx_gauche):
        return "montant_ht_brut"
    if "total taxe" in ctx_gauche or "total taxes" in ctx_gauche:
        return "montant_tva"
    if re.search(r'\btva\b', ctx_gauche) and "base" not in ctx_gauche:
        return "montant_tva_ligne"
    if any(k in ctx_gauche for k in ["base tva", "fodec", "timbre"]):
        return "montant_taxe_detail"
    if any(k in ctx_gauche for k in [" ht", "hors taxe", "hors-taxe"]):
        return "montant_ht"
    if "total" in ctx_gauche:
        return "montant_ttc"
    return "montant"


def _extraire_references(texte: str) -> dict:
    """
    Extrait les références (numéro facture, bon de livraison, bon de commande)
    et les classe par rôle depuis le contexte gauche.
    """
    patterns = [
        r'\b([A-Z]{1,4}[-/]\d{4}[-/]\d+)\b',
        r'\b(\d{4}[-/]\d{3,6})\b',
        r'(?:num[eé]ro|n[°o]\.?|num\.?|r[eé]f\.?|#)\s*'
        r'(?:facture|fact\.?|bl|commande)?\s*[:\s]*([A-Z0-9/\-]{3,20})',
    ]
    vus = set()
    vus_roles = {}
    for p in patterns:
        for m in re.finditer(p, texte, re.IGNORECASE):
            val = m.group(1).strip()
            if not val or len(val) < 3 or val in vus:
                continue
            vus.add(val)
            ctx = _contexte_fenetre(texte, m.start())
            role = _role_ref_label(ctx)
            if role not in vus_roles:
                vus_roles[role] = val
    return vus_roles


def _extraire_noms(texte: str) -> dict:
    """
    Extrait les noms de sociétés (fournisseur, client) depuis le texte aplati.
    Cherche les formes juridiques (SARL, SA, EURL…) et les labels explicites.
    """
    patterns = [
        r'(?:fournisseur|supplier|vendeur)\s*[:\s]+'
        r'([A-ZÀ-Ÿ][A-Za-zÀ-ÿ0-9\s&]{2,38}?)(?=\s*(?:\n|$|MF|RIB|Tél|Tel|Date|N°))',
        r'([A-Z][A-Za-zÀ-ÿ0-9\s&,.\-]{2,44}'
        r'(?:SARL|SA\b|EURL|GROUP|GROUPE|SNC|LLC|SAS|GIE))',
    ]
    vus = set()
    vus_roles = {}
    for p in patterns:
        for m in re.finditer(p, texte, re.IGNORECASE):
            val = _nettoyer_nom(m.group(1).strip())
            if not val or len(val) < 3 or val in vus:
                continue
            vus.add(val)
            ctx = _contexte_fenetre(texte, m.start())
            role = _role_nom(ctx)
            if role not in vus_roles:
                vus_roles[role] = val
    return vus_roles


def _role_nom(ctx: str) -> str:
    """Déduit le rôle d'un nom (fournisseur/client/societe) depuis le contexte."""
    if any(k in ctx for k in ["fournisseur", "vendeur", "supplier"]):
        return "fournisseur"
    if any(k in ctx for k in ["client", "destinataire", "acheteur"]):
        return "client"
    return "societe"


# ──────────────────────────────────────────────────────────────────────
# MAPPING FRAPPE / ERPNEXT
# ──────────────────────────────────────────────────────────────────────

def _mapper_champs_frappe(champs: dict) -> dict:
    """
    Mappe les champs extraits vers les fieldnames ERPNext (Purchase Invoice).
    Ajoute posting_date = bill_date si non renseigné.
    """
    mapping = {
        "date":           "bill_date",
        "date_echeance":  "due_date",
        "numero_facture": "bill_no",
        "numero_bl":      "po_no",
        "fournisseur":    "supplier",
        "societe":        "supplier",
    }
    result = {}
    for cle_ocr, fieldname in mapping.items():
        if cle_ocr in champs and fieldname not in result:
            result[fieldname] = str(champs[cle_ocr])

    if "bill_date" in result and "posting_date" not in result:
        result["posting_date"] = result["bill_date"]

    for cle_montant in ("montant_ht", "montant_tva", "montant_ttc", "remise", "montant_ht_brut"):
        if cle_montant in champs:
            result[cle_montant] = str(round(champs[cle_montant], 3))

    return result


# ──────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ──────────────────────────────────────────────────────────────────────

def _contexte_ligne(texte: str, pos: int) -> str:
    """Retourne le texte de la ligne complète contenant la position pos (en minuscules)."""
    debut = texte.rfind('\n', 0, pos)
    debut = debut + 1 if debut >= 0 else 0
    fin = texte.find('\n', pos)
    fin = fin if fin >= 0 else len(texte)
    return texte[debut:fin].lower()


def _contexte_fenetre(texte: str, pos: int, fenetre: int = 60) -> str:
    """Retourne une fenêtre de texte centrée sur pos (±60 chars, en minuscules)."""
    debut = max(0, pos - fenetre)
    fin = min(len(texte), pos + fenetre)
    return texte[debut:fin].lower()


def _nettoyer_montant(val: str) -> float:
    """
    Convertit une chaîne montant Excel en float.
    Gère les formats FR (1 234,56), EN (1,234.56) et mixtes.
    Retourne 0.0 si la conversion échoue.
    """
    try:
        v = val.strip().replace('\u00a0', ' ')
        if re.search(r'\d,\d{3}\.', v):
            return float(v.replace(',', '').replace(' ', ''))
        if re.search(r'\d\.\d{3},', v):
            return float(v.replace('.', '').replace(' ', '').replace(',', '.'))
        return float(v.replace(' ', '').replace(',', '.'))
    except (ValueError, TypeError):
        return 0.0


def _nettoyer_nom(val: str) -> str:
    """
    Nettoie un nom de société extrait : supprime les labels de fin de ligne
    (Date, Adresse, Tel, MF, RIB, N°…) et trim la chaîne.
    """
    val = val.split("\n")[0].split("\r")[0]
    for p in [r'\s*Date\s*$', r'\s*Adresse\s*$', r'\s*Tel\s*$',
              r'\s*Tél\s*$', r'\s*MF\s*$', r'\s*RIB\s*$',
              r'\s*N°\s*$', r'\s*:\s*$']:
        val = re.sub(p, '', val, flags=re.IGNORECASE)
    return val.strip()


# ──────────────────────────────────────────────────────────────────────
# TEST
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python excel_facture_parser.py <fichier.xlsx>")
        sys.exit(1)
    resultat = parser_facture_excel(sys.argv[1])
    print(json.dumps(resultat, ensure_ascii=False, indent=2))