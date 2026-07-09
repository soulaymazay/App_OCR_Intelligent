# -*- coding: utf-8 -*-
"""
ocr_article_pipeline.py - Groupe Bayoudh Metal

Pipeline OCR dédié au formulaire Article (Item) ERPNext.
Suit la même architecture que ocr_pipeline.py (facture d'achat).

Endpoints exposés :
  - pipeline_article(file_url, source_doctype)  → async, retourne job_id
  - get_ocr_article_statut(job_id)              → polling résultat

Job interne :
  - _executer_pipeline_article_job(...)

Champs ERPNext remplis :
  item_code, item_name, item_group, stock_uom,
  standard_rate, last_purchase_rate, description
"""

import frappe
import os
import re
import json
import uuid
import cv2
import numpy as np
import pytesseract
from PIL import Image as PILImage
from werkzeug.utils import secure_filename
import re as _re2


# ──────────────────────────────────────────────────────────────────────
# MAPPING OCR → FIELDNAME ERPNEXT (Item)
# ──────────────────────────────────────────────────────────────────────

MAPPING_ARTICLE = {
    # ── ERPNext standard Item fields ─────────────────────────────────
    "item_code":          "item_code",
    "item_name":          "item_name",
    "item_group":         "item_group",
    "stock_uom":          "stock_uom",
    "standard_rate":      "standard_rate",
    "last_purchase_rate": "last_purchase_rate",
    "description":        "description",
    "disabled":           "disabled",
    "is_stock_item":      "is_stock_item",
    "has_batch_no":       "has_batch_no",
    "has_serial_no":      "has_serial_no",
    "weight_uom":         "weight_uom",
    "weight_per_unit":    "weight_per_unit",
    "purchase_uom":       "purchase_uom",
    "sales_uom":          "sales_uom",
    "min_order_qty":      "min_order_qty",
    "safety_stock":       "safety_stock",
    "warranty_period":    "warranty_period",
    "barcode":            "barcode",
    # ── Sage ERP — Onglet Identification ─────────────────────────────
    "custom_designation2":       "custom_designation2",
    "custom_designation3":       "custom_designation3",
    "custom_cle_recherche":      "custom_cle_recherche",
    "custom_ligne_produit":      "custom_ligne_produit",
    "custom_norme":              "custom_norme",
    "custom_ref_douaniere":      "custom_ref_douaniere",
    "custom_soumis_deb":         "custom_soumis_deb",
    # ── Sage ERP — Familles statistiques ─────────────────────────────
    "custom_nature":             "custom_nature",
    "custom_carac_technique":    "custom_carac_technique",
    "custom_forme":              "custom_forme",
    "custom_dim_long":           "custom_dim_long",
    "custom_dim_larg":           "custom_dim_larg",
    # ── Sage ERP — Champs physiques / tôle ───────────────────────────
    "custom_epaisseur":          "custom_epaisseur",
    "custom_long_barre":         "custom_long_barre",
    "custom_couleur_sup":        "custom_couleur_sup",
    "custom_couleur_inf":        "custom_couleur_inf",
    "custom_film":               "custom_film",
    "custom_type_tole":          "custom_type_tole",
    # ── Sage ERP — Onglet Gestion ────────────────────────────────────
    "custom_mode_gestion":            "custom_mode_gestion",
    "custom_stock_negatif":           "custom_stock_negatif",
    "custom_tracabilite":             "custom_tracabilite",
    "custom_titre_pct":               "custom_titre_pct",
    "custom_coef_dlu":                "custom_coef_dlu",
    "custom_article_remplacement":    "custom_article_remplacement",
    "custom_gestion_peremption":      "custom_gestion_peremption",
    "custom_famille_cout":            "custom_famille_cout",
    "custom_compteur_lot":            "custom_compteur_lot",
    "custom_compteur_serie":          "custom_compteur_serie",
    # ── Sage ERP — Onglet Unités ─────────────────────────────────────
    "custom_densite":                 "custom_densite",
    "custom_volume_us":               "custom_volume_us",
    "custom_format_etiquette_us":     "custom_format_etiquette_us",
    "custom_coef_ua_us":              "custom_coef_ua_us",
    "custom_coef_uv_us":              "custom_coef_uv_us",
    "custom_uom_stat":                "custom_uom_stat",
    "custom_coef_ustat_us":           "custom_coef_ustat_us",
    "custom_uom_cee":                 "custom_uom_cee",
    "custom_coef_ucee_us":            "custom_coef_ucee_us",
    # ── Sage ERP — Onglet Comptabilité ───────────────────────────────
    "custom_code_comptable":          "custom_code_comptable",
    "custom_libelle_comptable":       "custom_libelle_comptable",
    "custom_niveau_taxe":             "custom_niveau_taxe",
    "custom_libelle_taxe":            "custom_libelle_taxe",
    # ── Sage ERP — Onglet Vente ──────────────────────────────────────
    "custom_qte_max_vente":           "custom_qte_max_vente",
    "custom_tolerance_reliquat":      "custom_tolerance_reliquat",
    "custom_marge_minimale":          "custom_marge_minimale",
    "custom_prix_theorique":          "custom_prix_theorique",
    "custom_prix_plancher":           "custom_prix_plancher",
    "custom_article_substitution":    "custom_article_substitution",
    # ── Sage ERP — Appro / Stock site ────────────────────────────────
    "custom_stock_max":               "custom_stock_max",
    "custom_seuil_reappro":           "custom_seuil_reappro",
    "custom_qte_mini_reappro":        "custom_qte_mini_reappro",
    "custom_taille_lot":              "custom_taille_lot",
    "custom_categorie_abc":           "custom_categorie_abc",
    "custom_mode_inventaire":         "custom_mode_inventaire",
    "custom_mode_retrait":            "custom_mode_retrait",
    "custom_gestion_emplacement":     "custom_gestion_emplacement",
    "custom_acheteur_approv":         "custom_acheteur_approv",
    "custom_sites_appro":             "custom_sites_appro",
    "custom_methode_valorisation":    "custom_methode_valorisation",
    # ── ERPNext standard — Valorisation ─────────────────────────────
    "valuation_method":               "valuation_method",
    "valuation_rate":                 "valuation_rate",
    # ── Sage ERP — Onglet Fournisseurs ───────────────────────────────
    "custom_fournisseur_principal":   "custom_fournisseur_principal",
    "custom_ref_fournisseur":         "custom_ref_fournisseur",
    "custom_ean_fournisseur":         "custom_ean_fournisseur",
    "custom_majoration_cee":          "custom_majoration_cee",
    "custom_delai_sous_traitance":    "custom_delai_sous_traitance",
}

# ── Niveau 1 : REJET IMMÉDIAT (patterns regex) ───────────────────────
# Ces signaux identifient SANS AMBIGUÏTÉ un document non-article.
# Le rejet est INCONDITIONNEL — même si "article" ou "produit" apparaît
# dans le document (ex: une facture liste ses articles commandés).
import re as _re
_PATTERNS_REJET_IMMEDIAT = [p for p in [
     # ── Traite / Lettre de change ──────────────────────────────────
    _re.compile(r'\btireur\b',                  _re.IGNORECASE),
    _re.compile(r'\bdomiciliation\b',           _re.IGNORECASE),
    _re.compile(r'\blettre\s+de\s+change\b',    _re.IGNORECASE),
    _re.compile(r'\bbill\s+of\s+exchange\b',    _re.IGNORECASE),   # ← NOUVEAU
    _re.compile(r'\bvaleur\s+en\s+compte\b',    _re.IGNORECASE),
    _re.compile(r'\bvaleur\s+re[çc]ue?\b',      _re.IGNORECASE),
    _re.compile(r'\bvaleur\s+en\b',             _re.IGNORECASE),   # ← NOUVEAU (traite TN)
    _re.compile(r"\bà\s+l['']\s*ordre\s+de\b",  _re.IGNORECASE),
    _re.compile(r"\ba\s+l['']\s*ordre\s+de\b",  _re.IGNORECASE),   # ← NOUVEAU (sans accent)
    _re.compile(r'\bordre\s+de\s+paiement\b',   _re.IGNORECASE),
    _re.compile(r'\bordre\s+de\s+paiement\s+l',  _re.IGNORECASE),  # ← NOUVEAU (L-C tunisien)
    _re.compile(r'\béch[eé]ance\b',             _re.IGNORECASE),   # ← NOUVEAU (seul suffit)
    _re.compile(r'\béch[eé]ance\b.*\btireur\b', _re.IGNORECASE | _re.DOTALL),
    _re.compile(r'\btir[eé]\b',                 _re.IGNORECASE),   # ← NOUVEAU (tiré = accepteur)
    _re.compile(r'\bacceptation\b',             _re.IGNORECASE),   # ← NOUVEAU (case "Acceptation")
    _re.compile(r'\baval\b',                    _re.IGNORECASE),   # ← NOUVEAU (case "Aval")

    # Chèque
    re.compile(r'\bpayez\s+contre\s+ce\s+ch[eè]que\b', _re.IGNORECASE),
    _re.compile(r'\bpayez\s+contre\s+ce\s+ch',          _re.IGNORECASE),  # ← NOUVEAU (troncature OCR)
    _re.compile(r'\bnum[eé]ro\s+(?:de\s+)?ch[eè]que\b', _re.IGNORECASE),
    _re.compile(r'\bno\s*\.?\s*ch[eè]que\b',            _re.IGNORECASE),
    _re.compile(r'\bch[eè]que\s+n[o°]\s*[\.:=]?\s*\d+', _re.IGNORECASE), # ← NOUVEAU "Chèque n° 0001420"
    _re.compile(r'\bch[eè]que\s+n[o°]\b',               _re.IGNORECASE), # ← NOUVEAU (sans numéro)
    _re.compile(r'\bmontant\s+max\b.*\bdt\b',            _re.IGNORECASE | _re.DOTALL), # ← NOUVEAU (chèque TN)
    _re.compile(r'\btitulaire\s+du\s+compte\b',          _re.IGNORECASE), # ← NOUVEAU
    _re.compile(r"\bdate\s+d.expiration\b",              _re.IGNORECASE),
    _re.compile(r'\bnon\s+endossable\b',                 _re.IGNORECASE), # ← NOUVEAU
    # Facture
    _re.compile(r'\bfacture\s+n[o°]?\b',   _re.IGNORECASE),
    _re.compile(r'\bn[o°]\s*\.?\s*facture\b', _re.IGNORECASE),
    _re.compile(r'\binvoice\s+n[o°]?\b',   _re.IGNORECASE),
    _re.compile(r'\bnet\s+[àa]\s+payer\b', _re.IGNORECASE),
    _re.compile(r'\btotal\s+ttc\b',        _re.IGNORECASE),
    _re.compile(r'\bmontant\s+ttc\b',      _re.IGNORECASE),
    _re.compile(r'\bsolde\s+[àa]\s+payer\b', _re.IGNORECASE),
    # Bon de livraison / Bon de commande
    _re.compile(r'\bbon\s+de\s+livraison\b', _re.IGNORECASE),
    _re.compile(r'\bbon\s+de\s+commande\b',  _re.IGNORECASE),
    _re.compile(r'\bdelivery\s+note\b',      _re.IGNORECASE),
    _re.compile(r'\bpurchase\s+order\b',     _re.IGNORECASE),
    _re.compile(r'\bbl\s+n[o°]?\b',         _re.IGNORECASE),
    _re.compile(r'\bbc\s+n[o°]?\b',         _re.IGNORECASE),
    # Devis / Proforma
    _re.compile(r'\bdevis\s+n[o°]?\b',       _re.IGNORECASE),
    _re.compile(r'\bproforma\s+invoice\b',    _re.IGNORECASE),
    _re.compile(r'\bfacture\s+proforma\b',    _re.IGNORECASE),

    # Nomenclature / BOM
    _re.compile(r'\bnomenclature\b',              _re.IGNORECASE),
    _re.compile(r'\bbill\s+of\s+materials\b',      _re.IGNORECASE),
    _re.compile(r'\bBOM\b'),                        # sensible à la casse (évite faux positifs)
    _re.compile(r'\bliste\s+des\s+composants\b',   _re.IGNORECASE),
    _re.compile(r'\bliste\s+de\s+nomenclature\b',  _re.IGNORECASE),
    _re.compile(r'\bcomposants?\s+n[o°]\b',        _re.IGNORECASE),

]
]

# Libellé humain correspondant à chaque pattern (même ordre)
_LABELS_REJET_IMMEDIAT = [
    "tireur (traite)", "domiciliation (traite)", "lettre de change",
    "bill of exchange", "valeur en compte (traite)", "valeur reçue (traite)",
    "valeur en (traite TN)", "à l'ordre de", "a l'ordre de (sans accent)",
    "ordre de paiement", "ordre de paiement L-C (traite TN)",
    "échéance (traite)", "échéance+tireur (traite)",
    "tiré (accepteur traite)", "acceptation (traite)", "aval (traite)",
    "payez contre ce chèque", "payez contre ce ch (troncature)",
    "numéro de chèque", "N° chèque",
    "Chèque n° XXXX", "Chèque n° (sans numéro)",
    "montant max DT (chèque TN)", "titulaire du compte (chèque)",
    "date d'expiration (chèque TN)", "non endossable (chèque)",
    "Facture N°", "N° Facture", "Invoice N°",
    "net à payer", "total TTC", "montant TTC", "solde à payer",
    "bon de livraison", "bon de commande", "delivery note", "purchase order",
    "BL N°", "BC N°",
    "devis N°", "proforma invoice", "facture proforma",
    "nomenclature", "bill of materials", "BOM",
    "liste des composants", "liste de nomenclature", "composant N°",
]

# ── Niveau 2 : Signaux confirmant une VRAIE fiche article/produit ─────
# Ces signaux sont SPÉCIFIQUES aux fiches produit — ils n'apparaissent
# pas dans les factures / traites / chèques.
_SIGNAUX_FICHE_ARTICLE = [
    "fiche article", "fiche technique", "datasheet", "technical data sheet",
    "technical data", "fiche produit",
    "code article", "groupe d'article", "item group",
    "unité de mesure par défaut", "unité stock",
    "catégorie :", "désignation :", "référence article",
    "prix unitaire ht", "prix de vente ht", "prix achat ht",
    "caractéristiques", "specifications", "spécifications",
    "part no", "part number", "sku", "ean",
    "udm", "uom",
]
_LABELS_REJETES_ARTICLE = {
    "traite": "Traite (Lettre de Change)", "cheque": "Chèque",
    "facture": "Facture", "bon_livraison": "Bon de Livraison",
    "bon_commande": "Bon de Commande", "devis": "Devis / Proforma",
    "nomenclature": "Nomenclature (BOM)", "inconnu": "Document inconnu",
}

def _titre_rejet_article(cat):
    return "Document refusé — {}".format(_LABELS_REJETES_ARTICLE.get(cat, "Document refusé"))

def _msg_rejet_article(cat):
    label = _LABELS_REJETES_ARTICLE.get(cat, cat)
    return ("Type de document détecté : {0}\n\nCe module accepte uniquement les fiches "
             "techniques produit.\nVeuillez soumettre la fiche article correspondante."
            ).format(label)

def _categorie_depuis_patterns(patterns_trouves):
    """Déduit la catégorie (traite/cheque/facture/...) à partir des libellés détectés."""
    texte = " ".join(patterns_trouves).lower()
    if any(m in texte for m in ("traite", "tireur", "tiré", "échéance", "aval", "acceptation")):
        return "traite"
    if "chèque" in texte or "cheque" in texte:
        return "cheque"
    if "facture" in texte or "invoice" in texte or "ttc" in texte:
        return "facture"
    if "livraison" in texte or "delivery" in texte or "bl n" in texte:
        return "bon_livraison"
    if "commande" in texte or "purchase order" in texte or "bc n" in texte:
        return "bon_commande"
    if "devis" in texte or "proforma" in texte:
        return "devis"
    if "nomenclature" in texte or "bom" in texte or "composant" in texte:
        return "nomenclature"
    return "inconnu"
# ──────────────────────────────────────────────────────────────────────
# ENDPOINT 1 : Lancement async
# ──────────────────────────────────────────────────────────────────────

@frappe.whitelist()
#api ocr_article_pipeline.pipeline_article(POST) Reçoit fichier → sauvegarde temp → frappe.enqueue job async (OCR + extraction Article)
def pipeline_article(file_url="", source_doctype="Item"):
    """
    Lance le pipeline OCR Article de façon asynchrone.
    Retourne {"success": True, "async": True, "job_id": "<token>"}
    """
    contenu      = None
    nom_original = None
    content_type = ""

    # ── Résolution du fichier ────────────────────────────────────────
    if file_url:
        site_path = frappe.get_site_path()
        if file_url.startswith("/private/"):
            chemin = os.path.join(site_path, "private", "files",
                                  os.path.basename(file_url))
        elif file_url.startswith("/files/"):
            chemin = os.path.join(site_path, "public", "files",
                                  os.path.basename(file_url))
        else:
            chemin = os.path.join(site_path, "public", file_url.lstrip("/"))

        if not os.path.exists(chemin):
            return {"success": False, "erreur": f"Fichier introuvable : {file_url}"}

        nom_original = os.path.basename(chemin)
        with open(chemin, "rb") as f:
            contenu = f.read()
    else:
        files = frappe.request.files
        if not files or "file" not in files:
            return {"success": False,
                    "erreur": "Aucun fichier reçu (form-data, clé: 'file')."}
        file_obj     = files["file"]
        nom_original = file_obj.filename
        content_type = getattr(file_obj, "content_type", "") or ""
        contenu      = file_obj.read()

    nom_original = secure_filename(nom_original)

    # ── Validation taille ────────────────────────────────────────────
    taille_kb = len(contenu) / 1024
    if taille_kb < 2:
        return {
            "success": False,
            "erreur": (
                f"Fichier trop petit ({taille_kb:.1f} KB). "
                "Une fiche technique lisible fait généralement ≥ 50 KB."
            )
        }

    nom_fichier, ext = _corriger_extension(nom_original, content_type, contenu)
    extensions_ok    = [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".xlsx", ".svg"]
    if ext not in extensions_ok:
        return {
            "success": False,
            "erreur": f"Format '{ext}' non supporté. Acceptés : {', '.join(extensions_ok)}"
        }

    # ── Sauvegarde temporaire ────────────────────────────────────────
    dossier_tmp = os.path.join(frappe.get_site_path(), "private", "files")
    os.makedirs(dossier_tmp, exist_ok=True)
    job_token  = str(uuid.uuid4()).replace("-", "")
    chemin_tmp = os.path.join(dossier_tmp,
                              f"ocr_article_tmp_{job_token}_{nom_fichier}")
    with open(chemin_tmp, "wb") as f:
        f.write(contenu)

    frappe.cache().set_value(
        f"ocr_article_status_{job_token}", "en_cours", expires_in_sec=3600
    )

    frappe.enqueue(
        "ocr_intelligent.api.ocr_article_pipeline._executer_pipeline_article_job",
        queue="long",
        timeout=600,
        chemin_tmp=chemin_tmp,
        nom_fichier=nom_fichier,
        ext=ext,
        source_doctype=source_doctype,
        uploaded_by=frappe.session.user,
        job_token=job_token,
    )

    return {"success": True, "async": True, "job_id": job_token}


# ──────────────────────────────────────────────────────────────────────
# ENDPOINT 2 : Polling statut
# ──────────────────────────────────────────────────────────────────────

@frappe.whitelist()
#api ocr_article_pipeline.get_ocr_article_statut(GET) Polling cache Redis (en_cours / termine / erreur)
def get_ocr_article_statut(job_id):
    """
    Retourne le statut du job OCR Article.
    Réponses possibles : "en_cours" | "termine" | "erreur" | "inconnu"
    """
    status = frappe.cache().get_value(f"ocr_article_status_{job_id}")

    if status == "termine":
        result_raw = frappe.cache().get_value(f"ocr_article_result_{job_id}")
        if result_raw is None:
            return {"status": "termine",
                    "result": {"success": False, "erreur": "Résultat expiré du cache."}}
        try:
            result = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
        except (ValueError, TypeError):
            result = {"success": False, "erreur": str(result_raw)}
        return {"status": "termine", "result": result}

    if status == "erreur":
        erreur_raw = frappe.cache().get_value(f"ocr_article_erreur_{job_id}")
        try:
            erreur = json.loads(erreur_raw) if isinstance(erreur_raw, str) else erreur_raw
        except (ValueError, TypeError):
            erreur = erreur_raw or "Erreur inconnue."
        return {"status": "erreur", "erreur": erreur}

    if status == "en_cours":
        return {"status": "en_cours"}

    return {"status": "inconnu"}



_PATTERNS_CHAMPS_ARTICLE = {
    "item_code":     [r'code\s+article\s*[:=]?\s*([A-Za-z0-9\-_/]+)', r'\bpart\s*no\.?\s*[:=]?\s*([A-Za-z0-9\-_/]+)', r'\bsku\s*[:=]?\s*([A-Za-z0-9\-_/]+)'],
    "item_name":     [r'd[ée]signation\s*[:=]?\s*([^\n\r]{3,80})', r'nom\s+(?:de\s+l[’\']?)?article\s*[:=]?\s*([^\n\r]{3,80})'],
    "item_group":    [r"groupe\s+d[’\']?article\s*[:=]?\s*([^\n\r]{2,50})", r'item\s+group\s*[:=]?\s*([^\n\r]{2,50})'],
    "stock_uom":     [r'unit[ée]\s+de\s+mesure\s*(?:par\s+d[ée]faut)?\s*[:=]?\s*([A-Za-z]{1,10})', r'\budm\s*[:=]?\s*([A-Za-z]{1,10})', r'\buom\s*[:=]?\s*([A-Za-z]{1,10})'],
    "standard_rate": [r'prix\s+(?:de\s+)?vente\s+ht\s*[:=]?\s*([\d\s,.]+)'],
    "last_purchase_rate": [r'prix\s+achat\s+ht\s*[:=]?\s*([\d\s,.]+)'],
    "description":   [r'caract[ée]ristiques?\s*[:=]?\s*([^\n\r]{5,200})', r'sp[ée]cifications?\s*[:=]?\s*([^\n\r]{5,200})'],
    "barcode":       [r'\bean\s*[:=]?\s*(\d{8,14})'],
}

def _extraction_basique_article(texte_brut):
    """
    Extracteur de secours (regex) — à utiliser tant que le vrai
    article_extractor.py (spécifique au projet) n'est pas disponible.
    Retourne (champs, confiances).
    """
    champs = {}
    confiances = {}
    for champ, patterns in _PATTERNS_CHAMPS_ARTICLE.items():
        for pat in patterns:
            m = _re2.search(pat, texte_brut, _re2.IGNORECASE)
            if m:
                valeur = m.group(1).strip()
                if valeur:
                    champs[champ] = valeur
                    confiances[champ] = 60  # confiance modérée, extraction regex générique
                    break
    return champs, confiances
# ──────────────────────────────────────────────────────────────────────
# JOB ASYNCHRONE PRINCIPAL
# ──────────────────────────────────────────────────────────────────────

def _executer_pipeline_article_job(chemin_tmp, nom_fichier, ext,
                                    source_doctype, uploaded_by, job_token):
    try:
        # ── Étape 0 : Rejet rapide sur le nom de fichier ─────────────
        # Évite de lancer l'OCR (60-120s) sur un document évidemment rejeté
        nom_lower = nom_fichier.lower()
        _MOTS_REJET_NOM_CATEGORIE = {
            "traite": "traite", "lettre_change": "traite", "lettre-change": "traite",
            "bill_exchange": "traite", "lc_": "traite", "_lc_": "traite",
            "billet": "traite", "effet": "traite",
            "cheque": "cheque", "chèque": "cheque",
            "nomenclature": "nomenclature", "bom_": "nomenclature",
            "_bom": "nomenclature", "liste_composants": "nomenclature",
            "liste_matieres": "nomenclature",
        }
        for mot, categorie in _MOTS_REJET_NOM_CATEGORIE.items():
            if mot in nom_lower:
                _stocker_resultat(job_token, {
                    "success":       False,
                    "type_document": categorie,
                    "titre":         _titre_rejet_article(categorie),
                    "erreur":        _msg_rejet_article(categorie),
                })
                return
         # ── Étape 1 : OCR ou Excel ───────────────────────────────────
        if ext == ".xlsx":
            from ocr_intelligent.ocr.excel_article_parser import extraire_article_depuis_excel
            resultat_excel = extraire_article_depuis_excel(chemin_tmp)

            if resultat_excel.get("erreur"):
                _stocker_erreur(job_token, f"Erreur lecture Excel : {resultat_excel['erreur']}")
                return

            champs_ocr = resultat_excel.get("champs", {})
            confiances = resultat_excel.get("confiances", {})
            type_doc   = "fiche_article"
            texte_brut = f"[Excel] {nom_fichier} — {len(champs_ocr)} champ(s) extrait(s)"
            score      = 100
            nb_pages   = 1
            methode    = "excel_direct"

            # ── Construire un texte plat à partir de TOUTES les cellules ──
            # (pas seulement des champs déjà mappés) pour pouvoir appliquer
            # les mêmes contrôles de rejet que le PDF/image.
            try:
                import openpyxl
                wb = openpyxl.load_workbook(chemin_tmp, data_only=True, read_only=True)
                cellules = []
                for ws in wb.worksheets:
                    for row in ws.iter_rows(values_only=True):
                        for cell in row:
                            if cell is not None:
                                cellules.append(str(cell))
                texte_excel_brut = " ".join(cellules)
            except Exception:
                texte_excel_brut = " ".join(str(v) for v in champs_ocr.values())

            texte_lower = texte_excel_brut.lower()

            # ── Niveau 1 : Rejet immédiat inconditionnel (mêmes patterns que PDF) ──
            patterns_trouves = [
                _LABELS_REJET_IMMEDIAT[i]
                for i, p in enumerate(_PATTERNS_REJET_IMMEDIAT)
                if p.search(texte_excel_brut)
            ]
            if patterns_trouves:
                categorie = _categorie_depuis_patterns(patterns_trouves) # renvoie déjà un des labels ci-dessus si on l'aligne
                _stocker_resultat(job_token, {
                    "success":       False,
                    "type_document": categorie,
                    "titre":         _titre_rejet_article(categorie),
                    "erreur":        _msg_rejet_article(categorie),
                })
                return

            # ── Niveau 1.5 : Détection structurelle BOM ──
            _MOTS_BOM_STRUCTURE = [
                "repère", "repere", "poste n", "indice", "plan n°", "plan no",
                "ensemble", "sous-ensemble", "sous ensemble", "matière première",
                "qté", "quantité unitaire", "niveau", "code article parent",
                "article parent", "composé de", "entre dans la composition",
            ]
            nb_signaux_bom = sum(1 for m in _MOTS_BOM_STRUCTURE if m in texte_lower)

            if nb_signaux_bom >= 2:
                _stocker_resultat(job_token, {
                    "success":       False,
                    "type_document": "nomenclature",
                    "titre":         _titre_rejet_article("nomenclature"),
                    "erreur":        _msg_rejet_article("nomenclature"),
                })
                return
        else:
            from ocr_intelligent.ocr.ocr_engine import get_engine

            moteur    = get_engine()
            resultat_ocr = moteur.extraire_texte(chemin_tmp)

            texte_brut = resultat_ocr.get("texte", "") or ""
            score      = resultat_ocr.get("score_confiance", 0)
            methode    = resultat_ocr.get("moteur", "inconnu")
            nb_pages   = 1
            texte_lower = texte_brut.lower()

            if not texte_brut.strip():
                _stocker_resultat(job_token, {
                    "success":       False,
                    "type_document": "inconnu",
                    "titre":         _titre_rejet_article("inconnu"),
                    "erreur": (
                        "Aucun texte n'a pu être extrait du document.\n"
                        "Vérifiez que le fichier est lisible (image nette, PDF non corrompu)."
                    ),
                })
                return

            # ── Niveau 1 : Rejet immédiat inconditionnel ──
            patterns_trouves = [
                _LABELS_REJET_IMMEDIAT[i]
                for i, p in enumerate(_PATTERNS_REJET_IMMEDIAT)
                if p.search(texte_brut)
            ]
            if patterns_trouves:
                categorie = _categorie_depuis_patterns(patterns_trouves)
                _stocker_resultat(job_token, {
                    "success":       False,
                    "type_document": categorie,
                    "titre":         _titre_rejet_article(categorie),
                    "erreur":        _msg_rejet_article(categorie),
                })
                return

            # ── Niveau 1.5 : Détection structurelle BOM ──
            _MOTS_BOM_STRUCTURE = [
                "repère", "repere", "poste n", "indice", "plan n°", "plan no",
                "ensemble", "sous-ensemble", "sous ensemble", "matière première",
                "qté", "quantité unitaire", "niveau", "code article parent",
                "article parent", "composé de", "entre dans la composition",
            ]
            nb_signaux_bom = sum(1 for m in _MOTS_BOM_STRUCTURE if m in texte_lower)
            if nb_signaux_bom >= 2:
                _stocker_resultat(job_token, {
                    "success":       False,
                    "type_document": "nomenclature",
                    "titre":         _titre_rejet_article("nomenclature"),
                    "erreur":        _msg_rejet_article("nomenclature"),
                })
                return

            # ── Extraction des champs article ──
            try:
                from ocr_intelligent.ocr.article_extractor import extraire_champs_article
                resultat_extraction = extraire_champs_article(texte_brut)
                champs_ocr = resultat_extraction.get("champs", {})
                confiances = resultat_extraction.get("confiances", {})
            except ImportError:
                # Extracteur dédié introuvable → secours regex générique
                champs_ocr, confiances = _extraction_basique_article(texte_brut)

            # ── Niveau 2 : Confirmation — au moins 1 signal fiche article ──
            signaux_article = [s for s in _SIGNAUX_FICHE_ARTICLE if s in texte_lower]
            type_doc = "fiche_article" if (signaux_article or champs_ocr) else "inconnu"

            if type_doc == "inconnu":
                _stocker_resultat(job_token, {
                    "success":       False,
                    "type_document": "inconnu",
                    "titre":         _titre_rejet_article("inconnu"),
                    "erreur":        _msg_rejet_article("inconnu"),
                })
                return
        # ── Étape 5 : Mapping vers fieldnames ERPNext ─────────────────
        champs_remplis = {}
        for champ_ocr_key, fieldname in MAPPING_ARTICLE.items():
            val = champs_ocr.get(champ_ocr_key)
            if val and str(val).strip():
                champs_remplis[fieldname] = val

        # ── Étape 5b : Validation des champs Link ─────────────────────
        # item_group : vérifier que la valeur existe, sinon fallback
        if "item_group" in champs_remplis:
            raw_group = str(champs_remplis["item_group"]).strip()
            exists = frappe.db.exists("Item Group", raw_group)
            if not exists:
                # Recherche floue robuste sur tous les groupes disponibles
                groupes_db = [g["name"] for g in frappe.get_all(
                    "Item Group", fields=["name"], limit_page_length=0
                )]

                def _norm_group(v):
                    v = (v or "").strip().lower()
                    v = v.replace("’", "'")
                    v = re.sub(r"[^a-z0-9]+", " ", v)
                    v = re.sub(r"\s+", " ", v).strip()
                    return v

                val_l = _norm_group(raw_group)
                match = next((g for g in groupes_db if _norm_group(g) == val_l), None)
                if not match:
                    candidates = []
                    for g in groupes_db:
                        g_norm = _norm_group(g)
                        if not g_norm:
                            continue
                        # val_l contenu dans le nom du groupe → bonne direction
                        if val_l and val_l in g_norm:
                            candidates.append(g)
                        # nom du groupe contenu dans val_l → seulement si le groupe
                        # est suffisamment long (≥60% de val_l) pour éviter qu'un
                        # code court comme "CONS" (4 car.) matche "consommables" (12 car.)
                        elif g_norm and g_norm in val_l and len(g_norm) >= max(5, int(len(val_l) * 0.6)):
                            candidates.append(g)
                    if candidates:
                        # Prendre le candidat le plus spécifique (nom le plus long)
                        match = max(candidates, key=lambda g: len(_norm_group(g)))

                if not match:
                    # Dernier recours : essayer le code Sage brut (ex: "CONS", "ACCP")
                    # si la BD utilise les codes Sage comme noms de groupes
                    sage_code = champs_ocr.get("custom_categorie_sage", "")
                    if sage_code and frappe.db.exists("Item Group", sage_code):
                        match = sage_code
                    else:
                        # Essayer aussi une correspondance partielle sur le code Sage
                        if sage_code and groupes_db:
                            sage_norm = _norm_group(sage_code)
                            for g in groupes_db:
                                g_norm = _norm_group(g)
                                if sage_norm and (sage_norm == g_norm or sage_norm in g_norm):
                                    match = g
                                    break

                if match:
                    champs_remplis["item_group"] = match
                else:
                    # Groupe introuvable → supprimer du résultat, le champ restera vide
                    del champs_remplis["item_group"]

        # stock_uom : vérifier que l'UDM existe, sinon fallback sur la 1re UDM disponible
        if "stock_uom" in champs_remplis:
            exists = frappe.db.exists("UOM", champs_remplis["stock_uom"])
            if not exists:
                # Recherche floue
                udms_db = [u["name"] for u in frappe.get_list(
                    "UOM", fields=["name"], limit=100
                )]
                val_l = champs_remplis["stock_uom"].lower()
                match = next(
                    (u for u in udms_db if val_l in u.lower() or u.lower() in val_l),
                    None
                )
                if match:
                    champs_remplis["stock_uom"] = match
                else:
                    # UDM introuvable → supprimer du résultat, le champ restera vide
                    del champs_remplis["stock_uom"]

        # Valider les champs UOM Sage (purchase_uom, sales_uom, weight_uom)
        for uom_field in ("purchase_uom", "sales_uom", "weight_uom"):
            if uom_field not in champs_remplis:
                continue
            if not frappe.db.exists("UOM", champs_remplis[uom_field]):
                udms_db = udms_db if 'udms_db' in dir() else [
                    u["name"] for u in frappe.get_list("UOM", fields=["name"], limit=100)
                ]
                val_l = champs_remplis[uom_field].lower()
                match = next(
                    (u for u in udms_db if val_l in u.lower() or u.lower() in val_l),
                    None
                )
                if match:
                    champs_remplis[uom_field] = match
                else:
                    del champs_remplis[uom_field]

        # ── Étape 5.5 : Correction OCR du code article (zéros superflus) ─
        # PaddleOCR/Tesseract peut lire "ACP0011" comme "ACP00011" (zero en trop).
        # Si le code extrait n'existe pas mais qu'une variante avec un zéro de moins
        # existe dans ERPNext, on corrige silencieusement.
        code_raw = champs_remplis.get("item_code")
        if code_raw:
            import re as _re
            _m = _re.match(r'^([A-Za-z]+)(0{2,})(\d+)$', str(code_raw).strip())
            if _m:
                _prefix, _zeros, _suffix = _m.groups()
                if not frappe.db.exists("Item", str(code_raw).strip()):
                    for _n in range(len(_zeros) - 1, 0, -1):
                        _candidate = _prefix + "0" * _n + _suffix
                        if frappe.db.exists("Item", _candidate):
                            champs_remplis["item_code"] = _candidate
                            break

        # ── Étape 6 : Vérification doublon sur item_code ──────────────
        code_ocr = champs_remplis.get("item_code")
        if code_ocr:
            existe = frappe.db.get_value(
                "Item",
                {"item_code": str(code_ocr).strip()},
                ["name", "item_name"],
                as_dict=True,
            )
            if existe:
                _stocker_resultat(job_token, {
                    "success":        True,
                    "doublon":        True,
                    "doublon_name":   existe["name"],
                    "doublon_label":  existe.get("item_name", ""),
                    "item_code":      code_ocr,
                    "champs_remplis": champs_remplis,
                    "type_document":  type_doc,
                    "score_confiance": score,
                })
                return

       # ── Étape 7 : Sauvegarde OCR Document ────────────────────────
        statut       = "Validé" if len(champs_remplis) >= 3 else "Validation requise"
        code_pour_lien = champs_remplis.get("item_code")

        ocr_doc_name = None
        existants    = frappe.get_list(
            "OCR Document",
            filters={"document_name": nom_fichier},
            fields=["name"], limit=1,
        )
        if existants:
            ocr_doc_name = existants[0]["name"]
            frappe.db.set_value("OCR Document", ocr_doc_name, {
                "extracted_text":  texte_brut,
                "extracted_field": json.dumps(champs_ocr, ensure_ascii=False, indent=2),
                "confidence_score": score,
                "status":          statut,
                "uploaded_by":     uploaded_by,
                "linked_doctype":  "Item" if code_pour_lien else None,
                "linked_docname":  code_pour_lien,
           })
        else:
            doc = frappe.get_doc({
                "doctype":          "OCR Document",
                "document_name":    nom_fichier,
                "uploaded_by":      uploaded_by,
                "confidence_score": score,
                "extracted_text":   texte_brut,
                "extracted_field":  json.dumps(champs_ocr,
                                               ensure_ascii=False, indent=2),
                "status":           statut,
                "linked_doctype":   "Item" if code_pour_lien else None,
                "linked_docname":   code_pour_lien,
            })
            doc.insert(ignore_permissions=True)
            ocr_doc_name = doc.name

        # ── Étape 7b : Attacher le fichier original ───────────────────
        try:
            deja_joint = frappe.db.exists("File", {
                "attached_to_doctype": "OCR Document",
                "attached_to_name":    ocr_doc_name,
                "file_name":           nom_fichier,
            })
            if not deja_joint:
                with open(chemin_tmp, "rb") as _f:
                    contenu_fichier = _f.read()

                file_doc = frappe.get_doc({
                    "doctype":             "File",
                    "file_name":           nom_fichier,
                    "attached_to_doctype": "OCR Document",
                    "attached_to_name":    ocr_doc_name,
                    "attached_to_field":   "file_url",
                    "is_private":          1,
                    "content":             contenu_fichier,
                })
                file_doc.insert(ignore_permissions=True)

                frappe.db.set_value(
                    "OCR Document", ocr_doc_name,
                    "file_url", file_doc.file_url
                )
        except Exception as _e:
            frappe.log_error(frappe.get_traceback(),
                             "OCR Article — Échec attachement fichier")

        frappe.db.commit()

        # ── Étape 8 : Résultat ────────────────────────────────────────
        if not champs_remplis:
            _stocker_resultat(job_token, {
                "success":         False,
                "nom_fichier":     nom_fichier,
                "ocr_document_id": ocr_doc_name,
                "score_confiance": score,
                "type_document":   type_doc,
                "texte_extrait":   texte_brut[:300],
                "erreur": (
                    f"Fiche analysée (type : {type_doc}) "
                    "mais aucun champ article n'a pu être extrait. "
                    "Vérifiez la qualité du document."
                ),
                "conseil": "Préférez un PDF natif ou une image nette ≥ 300 DPI.",
            })
            return

        _stocker_resultat(job_token, {
            "success":         True,
            "nom_fichier":     nom_fichier,
            "type_document":   type_doc,
            "champs_remplis":  champs_remplis,
            "confiances":      confiances,
            "score_confiance": score,
            "nombre_pages":    nb_pages,
            "methode_ocr":     methode,
            "ocr_document_id": ocr_doc_name,
            "texte_extrait":   texte_brut[:500],
            "message": (
                f"{len(champs_remplis)} champ(s) rempli(s) "
                f"(type : {type_doc}, score OCR : {score}%)"
            ),
        })

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "OCR Article Pipeline Job Error")
        _stocker_erreur(job_token, f"Erreur inattendue : {e}")

    finally:
        if os.path.exists(chemin_tmp):
            try:
                os.remove(chemin_tmp)
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────────
# OCR ENHANCED (passe 2 — images floues)
# ──────────────────────────────────────────────────────────────────────

def _ocr_enhanced(chemin_img: str, ext: str) -> str:
    """Passe OCR avec preprocessing agressif (même logique que ocr_pipeline.py)."""
    try:
        if ext == ".pdf":
            from pdf2image import convert_from_path
            pages = convert_from_path(chemin_img, dpi=300, first_page=1, last_page=1)
            if not pages:
                return ""
            img = cv2.cvtColor(np.array(pages[0].convert("RGB")), cv2.COLOR_RGB2BGR)
        else:
            img = cv2.imread(chemin_img)
            if img is None:
                pil = PILImage.open(chemin_img).convert("RGB")
                img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        if img is None:
            return ""

        h, w = img.shape[:2]
        if w < 1600:
            scale = 1600 / max(w, 1)
            img   = cv2.resize(img, None, fx=scale, fy=scale,
                               interpolation=cv2.INTER_LANCZOS4)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        for sigma in (2, 4):
            gaussian = cv2.GaussianBlur(gray, (0, 0), sigma)
            gray     = cv2.addWeighted(gray, 2.0, gaussian, -1.0, 0)

        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        gray  = clahe.apply(gray)
        gray  = cv2.fastNlMeansDenoising(gray, None, 15, 7, 21)

        _, bin_otsu = cv2.threshold(gray, 0, 255,
                                    cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        bin_adapt   = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 8
        )

        meilleur = ""
        for arr in (gray, bin_otsu, bin_adapt):
            for psm in (6, 4, 11, 3):
                try:
                    txt = pytesseract.image_to_string(
                        PILImage.fromarray(arr), lang="fra+eng",
                        config=f"--oem 1 --psm {psm}"
                    )
                    if len(txt.split()) > len(meilleur.split()):
                        meilleur = txt
                except Exception:
                    continue
        return meilleur
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────────────
# HELPERS CACHE
# ──────────────────────────────────────────────────────────────────────

def _stocker_resultat(job_token, result):
    frappe.cache().set_value(
        f"ocr_article_result_{job_token}",
        json.dumps(result, ensure_ascii=False),
        expires_in_sec=3600,
    )
    frappe.cache().set_value(
        f"ocr_article_status_{job_token}", "termine", expires_in_sec=3600
    )


def _stocker_erreur(job_token, message):
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    frappe.cache().set_value(
        f"ocr_article_erreur_{job_token}",
        json.dumps(message, ensure_ascii=False),
        expires_in_sec=3600,
    )
    frappe.cache().set_value(
        f"ocr_article_status_{job_token}", "erreur", expires_in_sec=3600
    )


# ──────────────────────────────────────────────────────────────────────
# CORRECTION EXTENSION (copie locale de ocr_pipeline.py)
# ──────────────────────────────────────────────────────────────────────

def _corriger_extension(nom, ct, contenu):
    ext = os.path.splitext(nom)[1].lower()
    if ext in [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".xlsx"]:
        return nom, ext
    map_ct = {
        "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
        "image/tiff": ".tiff", "image/bmp": ".bmp", "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xlsx",
    }
    ct_clean = (ct or "").split(";")[0].strip()
    if ct_clean in map_ct:
        return nom + map_ct[ct_clean], map_ct[ct_clean]
    if contenu:
        sig = contenu[:8]
        if sig[:4] == b'\x89PNG':  return nom + ".png",  ".png"
        if sig[:2] == b'\xff\xd8': return nom + ".jpg",  ".jpg"
        if sig[:4] == b'%PDF':     return nom + ".pdf",  ".pdf"
        if sig[:2] == b'BM':       return nom + ".bmp",  ".bmp"
    return nom, ext if ext else ""