# -*- coding: utf-8 -*-
"""
create_item_custom_fields.py — Groupe Bayoudh Metal
Crée tous les champs personnalisés Sage ERP X3 sur le doctype Item d'ERPNext.

Utilisation :
  bench --site ocr.localhost execute \
    "ocr_intelligent.setup.create_item_custom_fields.create_all_fields"
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


# ─────────────────────────────────────────────────────────────────────
# Définition de tous les champs — ordonnés par insert_after en cascade
# ─────────────────────────────────────────────────────────────────────
_CHAMPS = [

    # ── Section : Sage — Identification ────────────────────────────────
    dict(fieldname="custom_sb_identification", fieldtype="Section Break",
         label="Sage — Identification", insert_after="description",
         collapsible=1),
    dict(fieldname="custom_statut_article", fieldtype="Data",
         label="Statut article", insert_after="custom_sb_identification", length=20),
    dict(fieldname="custom_designation2",  fieldtype="Data",
         label="Désignation 2", insert_after="custom_sb_identification", length=140),
    dict(fieldname="custom_designation3",  fieldtype="Data",
         label="Désignation 3", insert_after="custom_designation2",      length=140),
    dict(fieldname="custom_cle_recherche", fieldtype="Data",
         label="Clé recherche", insert_after="custom_designation3",      length=80),
    dict(fieldname="custom_ligne_produit", fieldtype="Data",
         label="Ligne de produit", insert_after="custom_cle_recherche",  length=80),
    dict(fieldname="custom_norme",         fieldtype="Data",
         label="Norme", insert_after="custom_ligne_produit",             length=80),
    dict(fieldname="custom_code_ean",      fieldtype="Data",
         label="Code EAN", insert_after="custom_norme",                  length=20),
    dict(fieldname="custom_ref_douaniere", fieldtype="Data",
         label="Référence douanière", insert_after="custom_code_ean",    length=80),
    dict(fieldname="custom_soumis_deb",    fieldtype="Check",
         label="Soumis à la DEB", insert_after="custom_ref_douaniere",   default=0),
    dict(fieldname="custom_acces_gestionnaire", fieldtype="Data",
         label="Accès gestionnaire", insert_after="custom_soumis_deb",   length=40),
    dict(fieldname="custom_infos_produit", fieldtype="Data",
         label="Informations produits", insert_after="custom_acces_gestionnaire", length=140),
    dict(fieldname="custom_texte_production",  fieldtype="Check",
         label="Texte production",  insert_after="custom_infos_produit",  default=0),
    dict(fieldname="custom_texte_preparation", fieldtype="Check",
         label="Texte préparation", insert_after="custom_texte_production", default=0),

    # ── Section : Familles statistiques + Physique ─────────────────────
    dict(fieldname="custom_sb_familles", fieldtype="Section Break",
         label="Sage — Familles statistiques & Physique",
         insert_after="custom_texte_preparation", collapsible=1),
    dict(fieldname="custom_nature",         fieldtype="Data",
         label="Nature", insert_after="custom_sb_familles",         length=80),
    dict(fieldname="custom_carac_technique",fieldtype="Data",
         label="Carac. technique", insert_after="custom_nature",    length=80),
    dict(fieldname="custom_forme",          fieldtype="Data",
         label="Forme", insert_after="custom_carac_technique",      length=80),
    dict(fieldname="custom_dim_long",       fieldtype="Data",
         label="Diam / Long / Ep.", insert_after="custom_forme",    length=40),
    dict(fieldname="custom_dim_larg",       fieldtype="Data",
         label="Larg / Ep inf", insert_after="custom_dim_long",     length=40),
    dict(fieldname="custom_epaisseur",      fieldtype="Data",
         label="Épaisseur", insert_after="custom_dim_larg",         length=40),
    dict(fieldname="custom_long_barre",     fieldtype="Data",
         label="Long barre/Cor", insert_after="custom_epaisseur",   length=40),
    dict(fieldname="custom_couleur_sup",    fieldtype="Data",
         label="Couleur Tôle Sup", insert_after="custom_long_barre",length=60),
    dict(fieldname="custom_couleur_inf",    fieldtype="Data",
         label="Couleur Tôle Inf", insert_after="custom_couleur_sup",length=60),
    dict(fieldname="custom_film",           fieldtype="Data",
         label="Film", insert_after="custom_couleur_inf",           length=60),
    dict(fieldname="custom_type_tole",      fieldtype="Data",
         label="Type Tôle", insert_after="custom_film",             length=60),

    # ── Section : Sage — Gestion ───────────────────────────────────────
    dict(fieldname="custom_sb_gestion", fieldtype="Section Break",
         label="Sage — Gestion", insert_after="custom_type_tole", collapsible=1),
    dict(fieldname="custom_mode_gestion",   fieldtype="Data",
         label="Mode gestion", insert_after="custom_sb_gestion",   length=60),
    dict(fieldname="custom_gestion_stock",  fieldtype="Data",
         label="Gestion stock", insert_after="custom_mode_gestion", length=60),
    dict(fieldname="custom_stock_negatif",  fieldtype="Check",
         label="Stock < 0 autorisé", insert_after="custom_gestion_stock", default=0),
    dict(fieldname="custom_tracabilite",    fieldtype="Data",
         label="Traçabilité", insert_after="custom_stock_negatif", length=60),
    dict(fieldname="custom_titre_pct",      fieldtype="Float",
         label="Titre (en %)", insert_after="custom_tracabilite"),
    dict(fieldname="custom_coef_dlu",       fieldtype="Float",
         label="Coefficient DLU", insert_after="custom_titre_pct"),
    dict(fieldname="custom_article_remplacement", fieldtype="Data",
         label="Article remplacement", insert_after="custom_coef_dlu", length=80),
    dict(fieldname="custom_designation_remplacement", fieldtype="Data",
         label="Désignation remplacement", insert_after="custom_article_remplacement", length=120),
    dict(fieldname="custom_gestion_peremption", fieldtype="Data",
         label="Gestion péremption", insert_after="custom_designation_remplacement", length=60),
    dict(fieldname="custom_statut_peremption",  fieldtype="Data",
         label="Statut péremption", insert_after="custom_gestion_peremption",  length=60),
    dict(fieldname="custom_delai_peremption",   fieldtype="Data",
         label="Délai péremption", insert_after="custom_statut_peremption",    length=40),
    dict(fieldname="custom_delai_recontrol",    fieldtype="Data",
         label="Délai recontrôle", insert_after="custom_delai_peremption",     length=40),
    dict(fieldname="custom_statut_recontrol",   fieldtype="Data",
         label="Statut recontrôle", insert_after="custom_delai_recontrol",     length=60),
    dict(fieldname="custom_famille_cout",   fieldtype="Data",
         label="Famille coût", insert_after="custom_statut_recontrol",         length=60),
    dict(fieldname="custom_compteur_lot",   fieldtype="Data",
         label="Compteur lot",   insert_after="custom_famille_cout",           length=40),
    dict(fieldname="custom_compteur_serie", fieldtype="Data",
         label="Compteur série", insert_after="custom_compteur_lot",           length=40),

    # ── Section : Sage — Unités avancées ──────────────────────────────
    dict(fieldname="custom_sb_unites", fieldtype="Section Break",
         label="Sage — Unités avancées", insert_after="custom_compteur_serie", collapsible=1),
    dict(fieldname="custom_uom_conditionnement", fieldtype="Data",
         label="Unité conditionnement", insert_after="custom_sb_unites",     length=20),
    dict(fieldname="custom_densite",          fieldtype="Float",
         label="Densité",            insert_after="custom_uom_conditionnement"),
    dict(fieldname="custom_volume_us",        fieldtype="Float",
         label="Volume de l'US",     insert_after="custom_densite"),
    dict(fieldname="custom_format_etiquette_us", fieldtype="Data",
         label="Format étiquette US",insert_after="custom_volume_us",            length=40),
    dict(fieldname="custom_coef_ua_us",       fieldtype="Float",
         label="Coef UA-US",         insert_after="custom_format_etiquette_us"),
    dict(fieldname="custom_coef_uv_us",       fieldtype="Float",
         label="Coef UV-US",         insert_after="custom_coef_ua_us"),
    dict(fieldname="custom_modifiable_uv",    fieldtype="Check",
         label="Modifiable (coef UV)", insert_after="custom_coef_uv_us",        default=0),
    dict(fieldname="custom_uom_stat",         fieldtype="Data",
         label="Unité statistique",  insert_after="custom_modifiable_uv",       length=20),
    dict(fieldname="custom_coef_ustat_us",    fieldtype="Float",
         label="Coef Ustat-US",      insert_after="custom_uom_stat"),
    dict(fieldname="custom_uom_cee",          fieldtype="Data",
         label="Unité CEE",          insert_after="custom_coef_ustat_us",       length=20),
    dict(fieldname="custom_coef_ucee_us",     fieldtype="Float",
         label="Coef UCEE-US",       insert_after="custom_uom_cee"),
    dict(fieldname="custom_unite_volume",     fieldtype="Data",
         label="Unité volume",       insert_after="custom_coef_ucee_us",        length=20),

    # ── Section : Sage — Comptabilité ─────────────────────────────────
    dict(fieldname="custom_sb_compta", fieldtype="Section Break",
         label="Sage — Comptabilité", insert_after="custom_unite_volume", collapsible=1),
    dict(fieldname="custom_code_comptable",    fieldtype="Data",
         label="Code comptable",  insert_after="custom_sb_compta",              length=20),
    dict(fieldname="custom_libelle_comptable", fieldtype="Data",
         label="Libellé comptable", insert_after="custom_code_comptable",       length=40),
    dict(fieldname="custom_niveau_taxe",       fieldtype="Data",
         label="Niveau taxe",    insert_after="custom_libelle_comptable",       length=20),
    dict(fieldname="custom_libelle_taxe",      fieldtype="Data",
         label="Libellé taxe",   insert_after="custom_niveau_taxe",             length=40),
    dict(fieldname="custom_immobilisable",     fieldtype="Check",
         label="Immobilisable",  insert_after="custom_libelle_taxe",            default=0),

    # ── Section : Sage — Vente ────────────────────────────────────────
    dict(fieldname="custom_sb_vente", fieldtype="Section Break",
         label="Sage — Vente", insert_after="custom_immobilisable", collapsible=1),
    dict(fieldname="custom_type_composition", fieldtype="Select",
         label="Type composition",
         options="\nArticle normal\nComposé nomenclature\nComposé kit",
         insert_after="custom_sb_vente"),
    dict(fieldname="custom_article_substitution", fieldtype="Data",
         label="Article substitution", insert_after="custom_type_composition",  length=80),
    dict(fieldname="custom_date_substitution",    fieldtype="Date",
         label="Date substitution", insert_after="custom_article_substitution"),
    dict(fieldname="custom_tolerance_reliquat",   fieldtype="Float",
         label="Tolérance reliquat %", insert_after="custom_date_substitution"),
    dict(fieldname="custom_qte_max_vente",        fieldtype="Float",
         label="Quantité maximale (vente)", insert_after="custom_tolerance_reliquat"),
    dict(fieldname="custom_marge_minimale",       fieldtype="Currency",
         label="Marge minimale", insert_after="custom_qte_max_vente"),
    dict(fieldname="custom_prix_theorique",       fieldtype="Currency",
         label="Prix théorique", insert_after="custom_marge_minimale"),
    dict(fieldname="custom_prix_plancher",        fieldtype="Currency",
         label="Prix plancher",  insert_after="custom_prix_theorique"),
    dict(fieldname="custom_autorisation_pret",    fieldtype="Check",
         label="Autorisation prêt", insert_after="custom_prix_plancher",        default=0),
    dict(fieldname="custom_contremarque_vente",   fieldtype="Check",
         label="Contremarque (vente)", insert_after="custom_autorisation_pret", default=0),
    dict(fieldname="custom_qte_directe",          fieldtype="Float",
         label="Qté directe", insert_after="custom_contremarque_vente"),
    dict(fieldname="custom_texte_vente",          fieldtype="Check",
         label="Texte vente",   insert_after="custom_qte_directe",             default=0),

    # ── Section : Sage — Appro / Stock ────────────────────────────────
    dict(fieldname="custom_sb_appro", fieldtype="Section Break",
         label="Sage — Appro / Stock", insert_after="custom_texte_vente", collapsible=1),
    dict(fieldname="custom_stock_max",           fieldtype="Float",
         label="Stock maximum",        insert_after="custom_sb_appro"),
    dict(fieldname="custom_seuil_reappro",       fieldtype="Float",
         label="Seuil de réappro",     insert_after="custom_stock_max"),
    dict(fieldname="custom_qte_mini_reappro",    fieldtype="Float",
         label="Qté mini réappro",     insert_after="custom_seuil_reappro"),
    dict(fieldname="custom_categorie_abc",       fieldtype="Data",
         label="Catégorie ABC",        insert_after="custom_qte_mini_reappro",  length=20),
    dict(fieldname="custom_mode_inventaire",     fieldtype="Data",
         label="Mode inventaire",      insert_after="custom_categorie_abc",     length=60),
    dict(fieldname="custom_taille_lot",          fieldtype="Float",
         label="Taille du lot",        insert_after="custom_mode_inventaire"),
    dict(fieldname="custom_mode_retrait",        fieldtype="Data",
         label="Mode retrait de stock",insert_after="custom_taille_lot",        length=60),
    dict(fieldname="custom_gestion_emplacement", fieldtype="Check",
         label="Gestion emplacement",  insert_after="custom_mode_retrait",      default=0),
    dict(fieldname="custom_acheteur_approv",     fieldtype="Data",
         label="Acheteur / Approv.",   insert_after="custom_gestion_emplacement", length=60),
    dict(fieldname="custom_sites_appro",         fieldtype="Long Text",
         label="Sites Appro (JSON)",   insert_after="custom_acheteur_approv"),

    # ── Section : Sage — Fournisseurs ─────────────────────────────────
    dict(fieldname="custom_sb_fournisseur", fieldtype="Section Break",
         label="Sage — Fournisseurs", insert_after="custom_sites_appro", collapsible=1),
    dict(fieldname="custom_fournisseur_principal",   fieldtype="Data",
         label="Fournisseur principal",  insert_after="custom_sb_fournisseur",  length=80),
    dict(fieldname="custom_ref_fournisseur",         fieldtype="Data",
         label="Réf. fournisseur",       insert_after="custom_fournisseur_principal", length=60),
    dict(fieldname="custom_ean_fournisseur",         fieldtype="Data",
         label="Code EAN fournisseur",   insert_after="custom_ref_fournisseur", length=20),
    dict(fieldname="custom_blocage_fournisseur",     fieldtype="Data",
         label="Blocage fournisseur",    insert_after="custom_ean_fournisseur", length=20),
    dict(fieldname="custom_coef_frais_approche",     fieldtype="Float",
         label="Coef frais approche",   insert_after="custom_blocage_fournisseur"),
    dict(fieldname="custom_three_way_match",         fieldtype="Check",
         label="Three-way match",        insert_after="custom_coef_frais_approche", default=0),
    dict(fieldname="custom_conditionnement_achat",   fieldtype="Data",
         label="Conditionnement achat",  insert_after="custom_three_way_match", length=40),
    dict(fieldname="custom_coef_uc_ua",              fieldtype="Float",
         label="Coef UC-UA",            insert_after="custom_conditionnement_achat"),
    dict(fieldname="custom_priorite_fournisseur",    fieldtype="Int",
         label="Priorité fournisseur",  insert_after="custom_coef_uc_ua"),
    dict(fieldname="custom_note_qualite",            fieldtype="Float",
         label="Note qualité",          insert_after="custom_priorite_fournisseur"),
    dict(fieldname="custom_soumis_controle",         fieldtype="Data",
         label="Soumis à contrôle",     insert_after="custom_note_qualite",    length=60),
    dict(fieldname="custom_frequence_controle",      fieldtype="Int",
         label="Fréquence contrôle",    insert_after="custom_soumis_controle"),
    dict(fieldname="custom_numero_controle",         fieldtype="Data",
         label="Numéro contrôle",       insert_after="custom_frequence_controle", length=40),
    dict(fieldname="custom_fiche_qualite",           fieldtype="Data",
         label="Fiche qualité",         insert_after="custom_numero_controle", length=80),
    dict(fieldname="custom_majoration_cee",          fieldtype="Float",
         label="Majoration CEE",        insert_after="custom_fiche_qualite"),
    dict(fieldname="custom_contremarque_fournisseur",fieldtype="Check",
         label="Contremarque (fournisseur)", insert_after="custom_majoration_cee", default=0),
    dict(fieldname="custom_alt_sous_traitance",      fieldtype="Data",
         label="Alt sous-traitance",   insert_after="custom_contremarque_fournisseur", length=80),
    dict(fieldname="custom_delai_sous_traitance",    fieldtype="Data",
         label="Délai sous-traitance", insert_after="custom_alt_sous_traitance", length=40),

    # ── Section : Sage — Après-vente ──────────────────────────────────
    dict(fieldname="custom_sb_apres_vente", fieldtype="Section Break",
         label="Sage — Après-vente", insert_after="custom_delai_sous_traitance", collapsible=1),
    dict(fieldname="custom_creation_parc_client",  fieldtype="Check",
         label="Création de parc client",  insert_after="custom_sb_apres_vente", default=0),
    dict(fieldname="custom_categorie_coupon",      fieldtype="Data",
         label="Catégorie de coupon",       insert_after="custom_creation_parc_client", length=60),
    dict(fieldname="custom_contrat_pret",          fieldtype="Data",
         label="Contrat de prêt",           insert_after="custom_categorie_coupon",    length=80),
    dict(fieldname="custom_contrat_garantie",      fieldtype="Data",
         label="Contrat de garantie",       insert_after="custom_contrat_pret",        length=80),
    dict(fieldname="custom_contrat_service",       fieldtype="Data",
         label="Contrat de service",        insert_after="custom_contrat_garantie",    length=80),
    dict(fieldname="custom_debit_points",          fieldtype="Float",
         label="Débit de points",           insert_after="custom_contrat_service"),
    dict(fieldname="custom_valeur_nulle_points",   fieldtype="Check",
         label="Valeur nulle prise en compte", insert_after="custom_debit_points",     default=0),
    dict(fieldname="custom_jetons_crediter",       fieldtype="Float",
         label="Jetons à créditer",         insert_after="custom_valeur_nulle_points"),
    dict(fieldname="custom_frequence_points",      fieldtype="Data",
         label="Fréquence des points",      insert_after="custom_jetons_crediter",     length=60),
    dict(fieldname="custom_alt_nomenclature_sav",  fieldtype="Data",
         label="Alt. nomenclature SAV",     insert_after="custom_frequence_points",    length=80),
    dict(fieldname="custom_type_article_sav",      fieldtype="Data",
         label="Type d'article SAV",        insert_after="custom_alt_nomenclature_sav", length=40),
    dict(fieldname="custom_sortie_stock_defaut",   fieldtype="Check",
         label="Sortie de stock par défaut",insert_after="custom_type_article_sav",   default=0),
    dict(fieldname="custom_unite_jours",           fieldtype="Data",
         label="Unité pour les jours",      insert_after="custom_sortie_stock_defaut", length=20),
    dict(fieldname="custom_unite_heures",          fieldtype="Data",
         label="Unité pour les heures",     insert_after="custom_unite_jours",         length=20),
    dict(fieldname="custom_unite_minutes",         fieldtype="Data",
         label="Unité pour les minutes",    insert_after="custom_unite_heures",        length=20),
    dict(fieldname="custom_coef_jour_heures",      fieldtype="Float",
         label="Coef Jour - Heures",        insert_after="custom_unite_minutes"),
]


def create_all_fields():
    """Point d'entrée — crée tous les champs manquants."""
    crees   = []
    ignores = []
    erreurs = []

    champs_existants = {
        r["fieldname"]
        for r in frappe.db.get_all(
            "Custom Field",
            filters={"dt": "Item"},
            fields=["fieldname"],
        )
    }

    for champ in _CHAMPS:
        fn = champ["fieldname"]
        if fn in champs_existants:
            ignores.append(fn)
            continue
        try:
            create_custom_fields({"Item": [champ]})
            crees.append(fn)
        except Exception as exc:
            erreurs.append(f"{fn}: {exc}")

    frappe.db.commit()

    print(f"\n✅ Champs créés    : {len(crees)}")
    print(f"⏭  Déjà présents   : {len(ignores)}")
    print(f"❌ Erreurs          : {len(erreurs)}")
    if erreurs:
        for e in erreurs:
            print(f"   {e}")
    if crees:
        print("\nNouveaux champs :")
        for f in crees:
            print(f"   + {f}")
