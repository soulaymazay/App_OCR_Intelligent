// ocr_article_form.js - Groupe Bayoudh Metal
// Bouton OCR dans le formulaire Article (Item) ERPNext

// ─────────────────────────────────────────────────────────────────────
// CONFIGURATION
// ─────────────────────────────────────────────────────────────────────
const OCR_ARTICLE_CONFIG = {
    pipeline_endpoint:    "ocr_intelligent.api.ocr_article_pipeline.pipeline_article",
    statut_endpoint:      "ocr_intelligent.api.ocr_article_pipeline.get_ocr_article_statut",
    poll_interval_ms:     2500,
    poll_max_attempts:    80,
    score_warning_seuil:  65,

    // ── LISTE UNIQUE DE VÉRITÉ pour les champs obligatoires ──────────
    // Générée automatiquement depuis OCR_ARTICLE_DIALOG_FIELDS (sensitivity === 1)
    // Ne plus maintenir cette liste manuellement — voir _get_champs_obligatoires()
    champs_obligatoires: null, // sera peuplé après la définition de OCR_ARTICLE_DIALOG_FIELDS

    labels: {
        item_code:                        "Code Article",
        item_name:                        "Nom de l'article",
        item_group:                       "Groupe d'article",
        stock_uom:                        "Unité de mesure (stock)",
        purchase_uom:                     "Unité d'achat",
        sales_uom:                        "Unité de vente",
        standard_rate:                    "Prix de base (HT)",
        last_purchase_rate:               "Prix d'achat",
        valuation_method:                 "Méthode de valorisation",
        valuation_rate:                   "Taux de valorisation",
        description:                      "Description",
        disabled:                         "Désactivé",
        custom_statut_article:            "Statut article",
        custom_nature:                    "Nature",
        custom_gestion_stock:             "Gestion stock",
        custom_mode_gestion:              "Mode gestion",
        custom_famille_cout:              "Famille coût",
        custom_code_comptable:            "Code comptable",
        custom_niveau_taxe:               "Niveau taxe",
        custom_type_article:              "Type d'article",
        custom_fournisseur_principal:     "Fournisseur principal",
        is_stock_item:                    "Maintenir Stock",
        weight_per_unit:                  "Poids de l'US",
        weight_uom:                       "Unité poids",
        min_order_qty:                    "Qté minimum commande",
        safety_stock:                     "Stock de sécurité",
        warranty_period:                  "Garantie (mois)",
        has_batch_no:                     "Gestion par lot",
        has_serial_no:                    "Gestion par série",
        custom_designation2:              "Désignation 2",
        custom_designation3:              "Désignation 3",
        custom_cle_recherche:             "Clé recherche",
        custom_ligne_produit:             "Ligne de produit",
        custom_norme:                     "Norme",
        custom_code_ean:                  "Code EAN",
        custom_ref_douaniere:             "Référence douanière",
        custom_soumis_deb:                "Soumis à la DEB",
        custom_acces_gestionnaire:        "Accès gestionnaire",
        custom_infos_produit:             "Informations produits",
        custom_texte_production:          "Texte production",
        custom_texte_preparation:         "Texte préparation",
        custom_carac_technique:           "Carac. technique",
        custom_forme:                     "Forme",
        custom_dim_long:                  "Diam / Long / Ep.",
        custom_dim_larg:                  "Larg / Ep inf",
        custom_epaisseur:                 "Épaisseur",
        custom_long_barre:                "Long barre/Cor",
        custom_couleur_sup:               "Couleur Tôle Sup",
        custom_couleur_inf:               "Couleur Tôle Inf",
        custom_film:                      "Film",
        custom_type_tole:                 "Type Tôle",
        custom_stock_negatif:             "Stock < 0 autorisé",
        custom_tracabilite:               "Traçabilité",
        custom_titre_pct:                 "Titre (en %)",
        custom_coef_dlu:                  "Coefficient DLU",
        custom_article_remplacement:      "Article remplacement",
        custom_designation_remplacement:  "Désignation remplacement",
        custom_gestion_peremption:        "Gestion péremption",
        custom_statut_peremption:         "Statut péremption",
        custom_delai_peremption:          "Délai péremption",
        custom_delai_recontrol:           "Délai recontrôle",
        custom_statut_recontrol:          "Statut recontrôle",
        custom_compteur_lot:              "Compteur lot",
    }
};

// ─────────────────────────────────────────────────────────────────────
// HOOK FRAPPE — formulaire Item
// ─────────────────────────────────────────────────────────────────────
frappe.ui.form.on("Item", {

    refresh(frm) {
        _ocr_article_ajouter_bouton(frm);
        _ocr_article_afficher_tableau_sites(frm);
    },

    validate(frm) {
        // ── Récupérer la liste UNIQUE depuis OCR_ARTICLE_DIALOG_FIELDS ──
        const obligatoires = _get_champs_obligatoires();

        // ── Effacer les anciens messages ─────────────────────────────
        obligatoires.forEach(function(def) {
            if (frm.fields_dict[def.frappe]) {
                frm.set_df_property(def.frappe, "description", "");
            }
        });

        const champs_manquants = [];

        obligatoires.forEach(function(def) {
            const val = frm.doc[def.frappe];
            const vide = (
                val === null ||
                val === undefined ||
                String(val).trim() === "" ||
                val === 0
            );
            if (vide) {
                champs_manquants.push(def.label);
                // ── Message inline sous le champ ─────────────────────
                if (frm.fields_dict[def.frappe]) {
                    frm.set_df_property(
                        def.frappe,
                        "description",
                        `<span style="color:#dc3545;font-weight:500;">
                            ⛔ Ce champ est obligatoire — doit être saisi manuellement
                        </span>`
                    );
                }
            }
        });

        frm.refresh_fields();

        if (champs_manquants.length > 0) {
            frappe.msgprint({
                title: __("Champs obligatoires manquants"),
                indicator: "red",
                message: __(
                    "Les champs suivants sont obligatoires et doivent être saisis manuellement :<br><br>"
                    + "<b>" + champs_manquants.join(", ") + "</b>"
                )
            });
            frappe.validated = false; // ← BLOQUE l'enregistrement
        }
    }
});

// ─────────────────────────────────────────────────────────────────────
// SOURCE UNIQUE DE VÉRITÉ — champs obligatoires (sensitivity === 1)
// ─────────────────────────────────────────────────────────────────────
function _get_champs_obligatoires() {
    return OCR_ARTICLE_DIALOG_FIELDS.filter(
        def => def.frappe && def.sensitivity === 1
    );
}

// ─────────────────────────────────────────────────────────────────────
// DÉFINITION DES CHAMPS DU DIALOG DE VALIDATION
// sensitivity === 1 → obligatoire (bloquant partout)
// sensitivity === 2 → recommandé
// sensitivity === 3 → optionnel
// ─────────────────────────────────────────────────────────────────────
const OCR_ARTICLE_DIALOG_FIELDS = [

    // ═══════════════════════════════════════════════════════════════════
    // EN-TÊTE ARTICLE
    // ═══════════════════════════════════════════════════════════════════
    { section: "En-tête article" },
    {
        ocr: "item_code", frappe: "item_code", label: "Code Article",
        type: "Data", sensitivity: 1,
        aliases: ["code_article", "reference", "ref", "sku", "part_number", "item_code"],
    },
    {
        ocr: "item_name", frappe: "item_name", label: "Nom de l'article",
        type: "Data", sensitivity: 1,
        aliases: ["nom_article", "designation", "libelle", "product_name", "item_name"],
    },
    {
        ocr: "item_group", frappe: "item_group", label: "Groupe d'article",
        type: "Link", options: "Item Group", sensitivity: 1,
        aliases: ["groupe_article", "groupe", "category", "categorie", "item_group"],
    },
    {
        ocr: "disabled", frappe: "disabled", label: "Désactivé",
        type: "Check", sensitivity: 2,
        aliases: ["statut", "actif", "disabled"],
    },
    {
        ocr: "custom_statut_article", frappe: "custom_statut_article",
        label: "Statut article", type: "Data", sensitivity: 1,
        aliases: ["statut_article", "custom_statut_article"],
    },

    // ═══════════════════════════════════════════════════════════════════
    // ONGLET IDENTIFICATION
    // ═══════════════════════════════════════════════════════════════════
    { section: "Identification" },
    {
        ocr: "custom_designation2", frappe: "custom_designation2",
        label: "Désignation 2", type: "Data", sensitivity: 2,
        aliases: ["designation_2", "custom_designation2"],
    },
    {
        ocr: "custom_designation3", frappe: "custom_designation3",
        label: "Désignation 3", type: "Data", sensitivity: 3,
        aliases: ["designation_3", "custom_designation3"],
    },

    { section: "Identification — Divers" },
    {
        ocr: "custom_cle_recherche", frappe: "custom_cle_recherche",
        label: "Clé recherche", type: "Data", sensitivity: 3,
        aliases: ["cle_recherche", "custom_cle_recherche"],
    },
    {
        ocr: "custom_ligne_produit", frappe: "custom_ligne_produit",
        label: "Ligne de produit", type: "Data", sensitivity: 3,
        aliases: ["ligne_produit", "custom_ligne_produit"],
    },
    {
        ocr: "barcode", frappe: "custom_code_ean",
        label: "Code EAN", type: "Data", sensitivity: 2,
        aliases: ["barcode", "code_ean", "ean", "custom_code_ean"],
    },
    {
        ocr: "custom_norme", frappe: "custom_norme",
        label: "Norme", type: "Data", sensitivity: 3,
        aliases: ["norme", "custom_norme"],
    },
    {
        ocr: "custom_acces_gestionnaire", frappe: "custom_acces_gestionnaire",
        label: "Accès gestionnaire", type: "Data", sensitivity: 3,
        aliases: ["acces_gestionnaire", "custom_acces_gestionnaire"],
    },

    { section: "Identification — Informations CEE" },
    {
        ocr: "custom_soumis_deb", frappe: "custom_soumis_deb",
        label: "Soumis à la DEB", type: "Check", sensitivity: 3,
        aliases: ["soumis_deb", "custom_soumis_deb"],
    },
    {
        ocr: "custom_ref_douaniere", frappe: "custom_ref_douaniere",
        label: "Référence douanière", type: "Data", sensitivity: 3,
        aliases: ["ref_douaniere", "custom_ref_douaniere"],
    },

    { section: "Identification — Lien" },
    {
        ocr: "custom_infos_produit", frappe: "custom_infos_produit",
        label: "Informations produits", type: "Data", sensitivity: 3,
        aliases: ["infos_produit", "informations_produit", "custom_infos_produit"],
    },

    { section: "Identification — Physique" },
    {
        ocr: "custom_epaisseur", frappe: "custom_epaisseur",
        label: "Épaisseur", type: "Data", sensitivity: 3,
        aliases: ["epaisseur", "custom_epaisseur"],
    },
    {
        ocr: "custom_long_barre", frappe: "custom_long_barre",
        label: "Long barre/Cor", type: "Data", sensitivity: 3,
        aliases: ["long_barre", "custom_long_barre"],
    },
    {
        ocr: "custom_couleur_sup", frappe: "custom_couleur_sup",
        label: "Couleur Tôle Sup", type: "Data", sensitivity: 3,
        aliases: ["couleur_sup", "custom_couleur_sup"],
    },
    {
        ocr: "custom_couleur_inf", frappe: "custom_couleur_inf",
        label: "Couleur Tôle Inf", type: "Data", sensitivity: 3,
        aliases: ["couleur_inf", "custom_couleur_inf"],
    },
    {
        ocr: "custom_film", frappe: "custom_film",
        label: "Film", type: "Data", sensitivity: 3,
        aliases: ["film", "custom_film"],
    },
    {
        ocr: "custom_type_tole", frappe: "custom_type_tole",
        label: "Type Tôle", type: "Data", sensitivity: 3,
        aliases: ["type_tole", "custom_type_tole"],
    },

    { section: "Identification — Utilisation" },
    {
        ocr: "description", frappe: "description", label: "Description",
        type: "Small Text", sensitivity: 2,
        aliases: ["caracteristiques", "specifications", "details", "description"],
    },
    {
        ocr: "custom_texte_production", frappe: "custom_texte_production",
        label: "Texte production", type: "Check", sensitivity: 3,
        aliases: ["texte_production", "custom_texte_production"],
    },
    {
        ocr: "custom_texte_preparation", frappe: "custom_texte_preparation",
        label: "Texte préparation", type: "Check", sensitivity: 3,
        aliases: ["texte_preparation", "custom_texte_preparation"],
    },

    { section: "Identification — Familles statistiques" },
    {
        ocr: "custom_carac_technique", frappe: "custom_carac_technique",
        label: "Carac. technique", type: "Data", sensitivity: 3,
        aliases: ["carac_technique", "custom_carac_technique"],
    },
    {
        ocr: "custom_nature", frappe: "custom_nature",
        label: "Nature", type: "Data", sensitivity: 1,
        aliases: ["nature", "custom_nature"],
    },
    {
        ocr: "custom_forme", frappe: "custom_forme",
        label: "Forme", type: "Data", sensitivity: 3,
        aliases: ["forme", "custom_forme"],
    },
    {
        ocr: "custom_dim_long", frappe: "custom_dim_long",
        label: "Diam / Long / Ep.", type: "Data", sensitivity: 3,
        aliases: ["dim_long", "custom_dim_long"],
    },
    {
        ocr: "custom_dim_larg", frappe: "custom_dim_larg",
        label: "Larg / Ep inf", type: "Data", sensitivity: 3,
        aliases: ["dim_larg", "custom_dim_larg"],
    },

    // ═══════════════════════════════════════════════════════════════════
    // ONGLET GESTION
    // ═══════════════════════════════════════════════════════════════════
    { section: "Gestion — Gestion stock" },
    {
        ocr: "custom_gestion_stock", frappe: "custom_gestion_stock",
        label: "Gestion stock", type: "Data", sensitivity: 1,
        aliases: ["gestion_stock_label", "custom_gestion_stock"],
    },
    {
        ocr: "is_stock_item", frappe: "is_stock_item", label: "Maintenir Stock",
        type: "Check", sensitivity: 2,
        aliases: ["gestion_stock", "stock_gere", "is_stock_item"],
    },

    { section: "Gestion — Paramètres stocks" },
    {
        ocr: "custom_stock_negatif", frappe: "custom_stock_negatif",
        label: "Stock < 0 autorisé", type: "Check", sensitivity: 3,
        aliases: ["stock_negatif", "custom_stock_negatif"],
    },
    {
        ocr: "custom_mode_gestion", frappe: "custom_mode_gestion",
        label: "Mode gestion", type: "Data", sensitivity: 1,
        aliases: ["mode_gestion", "custom_mode_gestion"],
    },
    {
        ocr: "custom_tracabilite", frappe: "custom_tracabilite",
        label: "Traçabilité", type: "Data", sensitivity: 3,
        aliases: ["tracabilite", "custom_tracabilite"],
    },
    {
        ocr: "custom_titre_pct", frappe: "custom_titre_pct",
        label: "Titre (en %)", type: "Float", sensitivity: 3,
        aliases: ["titre_pct", "custom_titre_pct"],
    },
    {
        ocr: "custom_article_remplacement", frappe: "custom_article_remplacement",
        label: "Article remplacement", type: "Data", sensitivity: 3,
        aliases: ["article_remplacement", "custom_article_remplacement"],
    },
    {
        ocr: "custom_designation_remplacement", frappe: "custom_designation_remplacement",
        label: "Désignation remplacement", type: "Data", sensitivity: 3,
        aliases: ["designation_remplacement", "custom_designation_remplacement"],
    },

    { section: "Gestion — Recontrôle / Péremption" },
    {
        ocr: "custom_gestion_peremption", frappe: "custom_gestion_peremption",
        label: "Gestion péremption", type: "Data", sensitivity: 3,
        aliases: ["gestion_peremption", "custom_gestion_peremption"],
    },
    {
        ocr: "custom_statut_peremption", frappe: "custom_statut_peremption",
        label: "Statut péremption", type: "Data", sensitivity: 3,
        aliases: ["statut_peremption", "custom_statut_peremption"],
    },
    {
        ocr: "custom_delai_peremption", frappe: "custom_delai_peremption",
        label: "Délai péremption", type: "Data", sensitivity: 3,
        aliases: ["delai_peremption", "custom_delai_peremption"],
    },
    {
        ocr: "custom_delai_recontrol", frappe: "custom_delai_recontrol",
        label: "Délai recontrôle", type: "Data", sensitivity: 3,
        aliases: ["delai_recontrol", "custom_delai_recontrol"],
    },
    {
        ocr: "custom_statut_recontrol", frappe: "custom_statut_recontrol",
        label: "Statut recontrôle", type: "Data", sensitivity: 3,
        aliases: ["statut_recontrol", "custom_statut_recontrol"],
    },
    {
        ocr: "custom_coef_dlu", frappe: "custom_coef_dlu",
        label: "Coefficient DLU", type: "Float", sensitivity: 3,
        aliases: ["coef_dlu", "custom_coef_dlu"],
    },

    { section: "Gestion — Gestion lot" },
    {
        ocr: "has_batch_no", frappe: "has_batch_no", label: "Gestion par lot",
        type: "Check", sensitivity: 3,
        aliases: ["gestion_lot", "lot", "has_batch_no"],
    },
    {
        ocr: "custom_compteur_lot", frappe: "custom_compteur_lot",
        label: "Compteur lot", type: "Data", sensitivity: 3,
        aliases: ["compteur_lot", "custom_compteur_lot"],
    },

    { section: "Gestion — Gestion série" },
    {
        ocr: "has_serial_no", frappe: "has_serial_no", label: "Gestion par série",
        type: "Check", sensitivity: 3,
        aliases: ["gestion_serie", "serie", "has_serial_no"],
    },
    {
        ocr: "custom_compteur_serie", frappe: "custom_compteur_serie",
        label: "Compteur série", type: "Data", sensitivity: 3,
        aliases: ["compteur_serie", "custom_compteur_serie"],
    },

    { section: "Gestion — Coûts" },
    {
        ocr: "custom_famille_cout", frappe: "custom_famille_cout",
        label: "Famille coût", type: "Data", sensitivity: 1,
        aliases: ["famille_cout", "custom_famille_cout"],
    },
    {
        ocr: "custom_methode_valorisation", frappe: "custom_methode_valorisation",
        label: "Méthode valorisation (Sage)", type: "Data", sensitivity: 3,
        aliases: ["custom_methode_valorisation"],
    },
    {
        ocr: "valuation_method", frappe: "valuation_method",
        label: "Méthode de valorisation",
        type: "Select",
        options: "\nFIFO\nMoving Average\nLIFO",
        sensitivity: 2,
        aliases: ["methode_valorisation", "valuation_method"],
    },
    {
        ocr: "valuation_rate", frappe: "valuation_rate",
        label: "Taux de valorisation",
        type: "Currency", sensitivity: 3,
        aliases: ["taux_valorisation", "valuation_rate"],
    },

    // ═══════════════════════════════════════════════════════════════════
    // ONGLET UNITÉS
    // ═══════════════════════════════════════════════════════════════════
    { section: "Unités" },
    {
        ocr: "stock_uom", frappe: "stock_uom", label: "Unité stock (US)",
        type: "Link", options: "UOM", sensitivity: 1,
        aliases: ["uom", "unite", "unite_mesure", "unite_stock", "stock_uom"],
    },
    {
        ocr: "custom_densite", frappe: "custom_densite",
        label: "Densité", type: "Float", sensitivity: 3,
        aliases: ["densite", "custom_densite"],
    },
    {
        ocr: "custom_format_etiquette_us", frappe: "custom_format_etiquette_us",
        label: "Format étiquette US", type: "Data", sensitivity: 3,
        aliases: ["format_etiquette_us", "custom_format_etiquette_us"],
    },
    {
        ocr: "weight_uom", frappe: "weight_uom", label: "Unité poids",
        type: "Link", options: "UOM", sensitivity: 3,
        aliases: ["unite_poids", "weight_uom"],
    },
    {
        ocr: "weight_per_unit", frappe: "weight_per_unit", label: "Poids de l'US",
        type: "Float", sensitivity: 3,
        aliases: ["poids", "poids_us", "poids_net", "weight", "weight_per_unit"],
    },
    {
        ocr: "custom_unite_volume", frappe: "custom_unite_volume",
        label: "Unité volume", type: "Data", sensitivity: 3,
        aliases: ["unite_volume", "custom_unite_volume"],
    },
    {
        ocr: "custom_volume_us", frappe: "custom_volume_us",
        label: "Volume de l'US", type: "Float", sensitivity: 3,
        aliases: ["volume_us", "custom_volume_us"],
    },
    {
        ocr: "purchase_uom", frappe: "purchase_uom", label: "Unité achat (UA)",
        type: "Link", options: "UOM", sensitivity: 1,
        aliases: ["unite_achat", "ua", "purchase_uom"],
    },
    {
        ocr: "custom_coef_ua_us", frappe: "custom_coef_ua_us",
        label: "Coef UA-US", type: "Float", sensitivity: 3,
        aliases: ["coef_ua_us", "custom_coef_ua_us"],
    },
    {
        ocr: "sales_uom", frappe: "sales_uom", label: "Unité vente (UV)",
        type: "Link", options: "UOM", sensitivity: 1,
        aliases: ["unite_vente", "uv", "sales_uom"],
    },
    {
        ocr: "custom_coef_uv_us", frappe: "custom_coef_uv_us",
        label: "Coef UV-US", type: "Float", sensitivity: 3,
        aliases: ["coef_uv_us", "custom_coef_uv_us"],
    },
    {
        ocr: "custom_modifiable_uv", frappe: "custom_modifiable_uv",
        label: "Modifiable (coef UV)", type: "Check", sensitivity: 3,
        aliases: ["modifiable_uv", "custom_modifiable_uv"],
    },
    {
        ocr: "custom_uom_stat", frappe: "custom_uom_stat",
        label: "Unité statistique", type: "Data", sensitivity: 3,
        aliases: ["uom_stat", "unite_statistique", "custom_uom_stat"],
    },
    {
        ocr: "custom_coef_ustat_us", frappe: "custom_coef_ustat_us",
        label: "Coef Ustat-US", type: "Float", sensitivity: 3,
        aliases: ["coef_ustat_us", "custom_coef_ustat_us"],
    },
    {
        ocr: "custom_uom_cee", frappe: "custom_uom_cee",
        label: "Unité CEE", type: "Data", sensitivity: 3,
        aliases: ["uom_cee", "unite_cee", "custom_uom_cee"],
    },
    {
        ocr: "custom_coef_ucee_us", frappe: "custom_coef_ucee_us",
        label: "Coef UCEE-US", type: "Float", sensitivity: 3,
        aliases: ["coef_ucee_us", "custom_coef_ucee_us"],
    },

    { section: "Unités — Conditionnement" },
    {
        ocr: "custom_uom_conditionnement", frappe: "custom_uom_conditionnement",
        label: "Unité conditionnement", type: "Data", sensitivity: 3,
        aliases: ["uom_conditionnement", "unite_conditionnement", "custom_uom_conditionnement"],
    },

    // ═══════════════════════════════════════════════════════════════════
    // ONGLET COMPTABILITÉ
    // ═══════════════════════════════════════════════════════════════════
    { section: "Comptabilité — Données comptables" },
    {
        ocr: "custom_code_comptable", frappe: "custom_code_comptable",
        label: "Code comptable", type: "Data", sensitivity: 1,
        aliases: ["code_comptable", "custom_code_comptable"],
    },
    {
        ocr: "custom_libelle_comptable", frappe: "custom_libelle_comptable",
        label: "Libellé comptable", type: "Data", sensitivity: 3,
        aliases: ["libelle_comptable", "custom_libelle_comptable"],
    },
    {
        ocr: "custom_niveau_taxe", frappe: "custom_niveau_taxe",
        label: "Niveau taxe", type: "Data", sensitivity: 1,
        aliases: ["niveau_taxe", "custom_niveau_taxe"],
    },
    {
        ocr: "custom_libelle_taxe", frappe: "custom_libelle_taxe",
        label: "Libellé taxe", type: "Data", sensitivity: 3,
        aliases: ["libelle_taxe", "custom_libelle_taxe"],
    },

    { section: "Comptabilité — Immobilisation" },
    {
        ocr: "custom_immobilisable", frappe: "custom_immobilisable",
        label: "Immobilisable", type: "Check", sensitivity: 3,
        aliases: ["immobilisable", "custom_immobilisable"],
    },

    // ═══════════════════════════════════════════════════════════════════
    // ONGLET VENTE
    // ═══════════════════════════════════════════════════════════════════
    { section: "Vente — Données vente" },
    {
        ocr: "custom_type_article", frappe: "custom_type_article",
        label: "Type d'article", type: "Data", sensitivity: 1,
        aliases: ["type_article", "custom_type_article"],
    },
    {
        ocr: "custom_type_composition", frappe: "custom_type_composition",
        label: "Type composition", type: "Select",
        options: "\nArticle normal\nComposé nomenclature\nComposé kit",
        sensitivity: 2,
        aliases: ["type_composition", "custom_type_composition"],
    },
    {
        ocr: "custom_article_substitution", frappe: "custom_article_substitution",
        label: "Article substitution", type: "Data", sensitivity: 3,
        aliases: ["article_substitution", "custom_article_substitution"],
    },
    {
        ocr: "custom_date_substitution", frappe: "custom_date_substitution",
        label: "Date substitution", type: "Date", sensitivity: 3,
        aliases: ["date_substitution", "custom_date_substitution"],
    },

    { section: "Vente — Quantités" },
    {
        ocr: "custom_tolerance_reliquat", frappe: "custom_tolerance_reliquat",
        label: "Tolérance reliquat %", type: "Float", sensitivity: 3,
        aliases: ["tolerance_reliquat", "custom_tolerance_reliquat"],
    },
    {
        ocr: "min_order_qty", frappe: "min_order_qty", label: "Qté minimum commande",
        type: "Float", sensitivity: 3,
        aliases: ["qte_min", "quantite_minimum", "min_order_qty"],
    },
    {
        ocr: "custom_qte_max_vente", frappe: "custom_qte_max_vente",
        label: "Quantité maximale (vente)", type: "Float", sensitivity: 3,
        aliases: ["qte_max_vente", "quantite_maximale", "custom_qte_max_vente"],
    },

    { section: "Vente — Prix" },
    {
        ocr: "standard_rate", frappe: "standard_rate", label: "Prix de base (HT)",
        type: "Currency", sensitivity: 1,
        aliases: ["prix_vente", "prix_ht", "sale_price", "standard_rate"],
    },
    {
        ocr: "custom_marge_minimale", frappe: "custom_marge_minimale",
        label: "Marge minimale", type: "Currency", sensitivity: 3,
        aliases: ["marge_minimale", "custom_marge_minimale"],
    },
    {
        ocr: "custom_prix_theorique", frappe: "custom_prix_theorique",
        label: "Prix théorique", type: "Currency", sensitivity: 3,
        aliases: ["prix_theorique", "custom_prix_theorique"],
    },
    {
        ocr: "custom_prix_plancher", frappe: "custom_prix_plancher",
        label: "Prix plancher", type: "Currency", sensitivity: 3,
        aliases: ["prix_plancher", "custom_prix_plancher"],
    },

    { section: "Vente — Divers" },
    {
        ocr: "warranty_period", frappe: "warranty_period", label: "Garantie (mois)",
        type: "Int", sensitivity: 3,
        aliases: ["garantie", "duree_garantie", "warranty", "warranty_period"],
    },
    {
        ocr: "custom_autorisation_pret", frappe: "custom_autorisation_pret",
        label: "Autorisation prêt", type: "Check", sensitivity: 3,
        aliases: ["autorisation_pret", "custom_autorisation_pret"],
    },
    {
        ocr: "custom_contremarque_vente", frappe: "custom_contremarque_vente",
        label: "Contremarque (vente)", type: "Check", sensitivity: 3,
        aliases: ["contremarque_vente", "custom_contremarque_vente"],
    },
    {
        ocr: "custom_qte_directe", frappe: "custom_qte_directe",
        label: "Qté directe", type: "Float", sensitivity: 3,
        aliases: ["qte_directe", "custom_qte_directe"],
    },
    {
        ocr: "custom_texte_vente", frappe: "custom_texte_vente",
        label: "Texte vente", type: "Check", sensitivity: 3,
        aliases: ["texte_vente", "custom_texte_vente"],
    },

    // ═══════════════════════════════════════════════════════════════════
    // ONGLET APRÈS-VENTE
    // ═══════════════════════════════════════════════════════════════════
    { section: "Après-vente — Contrats modèles" },
    {
        ocr: "custom_creation_parc_client", frappe: "custom_creation_parc_client",
        label: "Création de parc client", type: "Check", sensitivity: 3,
        aliases: ["creation_parc_client", "custom_creation_parc_client"],
    },
    {
        ocr: "custom_categorie_coupon", frappe: "custom_categorie_coupon",
        label: "Catégorie de coupon", type: "Data", sensitivity: 3,
        aliases: ["categorie_coupon", "custom_categorie_coupon"],
    },
    {
        ocr: "custom_contrat_pret", frappe: "custom_contrat_pret",
        label: "Contrat de prêt", type: "Data", sensitivity: 3,
        aliases: ["contrat_pret", "custom_contrat_pret"],
    },
    {
        ocr: "custom_contrat_garantie", frappe: "custom_contrat_garantie",
        label: "Contrat de garantie", type: "Data", sensitivity: 3,
        aliases: ["contrat_garantie", "custom_contrat_garantie"],
    },
    {
        ocr: "custom_contrat_service", frappe: "custom_contrat_service",
        label: "Contrat de service", type: "Data", sensitivity: 3,
        aliases: ["contrat_service", "custom_contrat_service"],
    },

    { section: "Après-vente — Points et jetons" },
    {
        ocr: "custom_debit_points", frappe: "custom_debit_points",
        label: "Débit de points", type: "Float", sensitivity: 3,
        aliases: ["debit_points", "custom_debit_points"],
    },
    {
        ocr: "custom_valeur_nulle_points", frappe: "custom_valeur_nulle_points",
        label: "Valeur nulle prise en compte", type: "Check", sensitivity: 3,
        aliases: ["valeur_nulle_points", "custom_valeur_nulle_points"],
    },
    {
        ocr: "custom_jetons_crediter", frappe: "custom_jetons_crediter",
        label: "Jetons à créditer", type: "Float", sensitivity: 3,
        aliases: ["jetons_crediter", "custom_jetons_crediter"],
    },
    {
        ocr: "custom_frequence_points", frappe: "custom_frequence_points",
        label: "Fréquence des points", type: "Data", sensitivity: 3,
        aliases: ["frequence_points", "custom_frequence_points"],
    },

    { section: "Après-vente — Nomenclature" },
    {
        ocr: "custom_alt_nomenclature_sav", frappe: "custom_alt_nomenclature_sav",
        label: "Alt. nomenclature SAV", type: "Data", sensitivity: 3,
        aliases: ["alt_nomenclature_sav", "custom_alt_nomenclature_sav"],
    },

    { section: "Après-vente — Type de consommation" },
    {
        ocr: "custom_type_article_sav", frappe: "custom_type_article_sav",
        label: "Type d'article SAV", type: "Data", sensitivity: 3,
        aliases: ["type_article_sav", "custom_type_article_sav"],
    },
    {
        ocr: "custom_sortie_stock_defaut", frappe: "custom_sortie_stock_defaut",
        label: "Sortie de stock par défaut", type: "Check", sensitivity: 3,
        aliases: ["sortie_stock_defaut", "custom_sortie_stock_defaut"],
    },
    {
        ocr: "custom_unite_jours", frappe: "custom_unite_jours",
        label: "Unité pour les jours", type: "Data", sensitivity: 3,
        aliases: ["unite_jours", "custom_unite_jours"],
    },
    {
        ocr: "custom_unite_heures", frappe: "custom_unite_heures",
        label: "Unité pour les heures", type: "Data", sensitivity: 3,
        aliases: ["unite_heures", "custom_unite_heures"],
    },
    {
        ocr: "custom_unite_minutes", frappe: "custom_unite_minutes",
        label: "Unité pour les minutes", type: "Data", sensitivity: 3,
        aliases: ["unite_minutes", "custom_unite_minutes"],
    },
    {
        ocr: "custom_coef_jour_heures", frappe: "custom_coef_jour_heures",
        label: "Coef Jour - Heures", type: "Float", sensitivity: 3,
        aliases: ["coef_jour_heures", "custom_coef_jour_heures"],
    },

    // ═══════════════════════════════════════════════════════════════════
    // ONGLET APPRO
    // ═══════════════════════════════════════════════════════════════════
    { section: "Appro" },
    {
        ocr: "safety_stock", frappe: "safety_stock", label: "Stock de sécurité",
        type: "Float", sensitivity: 3,
        aliases: ["stock_securite", "stock_mini", "safety_stock"],
    },
    {
        ocr: "custom_stock_max", frappe: "custom_stock_max",
        label: "Stock maximum", type: "Float", sensitivity: 2,
        aliases: ["stock_maximum", "stock_max", "custom_stock_max"],
    },
    {
        ocr: "custom_seuil_reappro", frappe: "custom_seuil_reappro",
        label: "Seuil de réappro", type: "Float", sensitivity: 2,
        aliases: ["seuil_reappro", "reorder_level", "custom_seuil_reappro"],
    },
    {
        ocr: "custom_qte_mini_reappro", frappe: "custom_qte_mini_reappro",
        label: "Qté mini réappro", type: "Float", sensitivity: 3,
        aliases: ["qte_mini_reappro", "reorder_qty", "custom_qte_mini_reappro"],
    },
    {
        ocr: "custom_categorie_abc", frappe: "custom_categorie_abc",
        label: "Catégorie ABC", type: "Data", sensitivity: 2,
        aliases: ["categorie_abc", "abc_class", "custom_categorie_abc"],
    },
    {
        ocr: "custom_mode_inventaire", frappe: "custom_mode_inventaire",
        label: "Mode inventaire", type: "Data", sensitivity: 2,
        aliases: ["mode_inventaire", "inventory_mode", "custom_mode_inventaire"],
    },
    {
        ocr: "custom_taille_lot", frappe: "custom_taille_lot",
        label: "Taille du lot", type: "Float", sensitivity: 3,
        aliases: ["taille_lot", "custom_taille_lot"],
    },
    {
        ocr: "custom_mode_retrait", frappe: "custom_mode_retrait",
        label: "Mode retrait de stock", type: "Data", sensitivity: 3,
        aliases: ["mode_retrait", "custom_mode_retrait"],
    },
    {
        ocr: "custom_gestion_emplacement", frappe: "custom_gestion_emplacement",
        label: "Gestion emplacement", type: "Check", sensitivity: 3,
        aliases: ["gestion_emplacement", "custom_gestion_emplacement"],
    },
    {
        ocr: "custom_acheteur_approv", frappe: "custom_acheteur_approv",
        label: "Acheteur / Approv.", type: "Data", sensitivity: 3,
        aliases: ["acheteur_approv", "custom_acheteur_approv"],
    },

    { section: "Appro — Stock par site" },
    { sites_table: true },

    // ═══════════════════════════════════════════════════════════════════
    // ONGLET FOURNISSEURS
    // ═══════════════════════════════════════════════════════════════════
    { section: "Fournisseurs — Données fournisseur" },
    {
        ocr: "custom_fournisseur_principal", frappe: "custom_fournisseur_principal",
        label: "Fournisseur principal", type: "Data", sensitivity: 1,
        aliases: ["fournisseur_principal", "custom_fournisseur_principal"],
    },
    {
        ocr: "custom_ref_fournisseur", frappe: "custom_ref_fournisseur",
        label: "Réf. fournisseur", type: "Data", sensitivity: 3,
        aliases: ["ref_fournisseur", "custom_ref_fournisseur"],
    },
    {
        ocr: "custom_ean_fournisseur", frappe: "custom_ean_fournisseur",
        label: "Code EAN fournisseur", type: "Data", sensitivity: 3,
        aliases: ["ean_fournisseur", "custom_ean_fournisseur"],
    },
    {
        ocr: "custom_blocage_fournisseur", frappe: "custom_blocage_fournisseur",
        label: "Blocage fournisseur", type: "Data", sensitivity: 3,
        aliases: ["blocage_fournisseur", "custom_blocage_fournisseur"],
    },
    {
        ocr: "custom_coef_frais_approche", frappe: "custom_coef_frais_approche",
        label: "Coef frais approche", type: "Float", sensitivity: 3,
        aliases: ["coef_frais_approche", "custom_coef_frais_approche"],
    },
    {
        ocr: "custom_three_way_match", frappe: "custom_three_way_match",
        label: "Three-way match", type: "Check", sensitivity: 3,
        aliases: ["three_way_match", "custom_three_way_match"],
    },

    { section: "Fournisseurs — Achat" },
    {
        ocr: "last_purchase_rate", frappe: "last_purchase_rate", label: "Prix d'achat",
        type: "Currency", sensitivity: 2,
        aliases: [
            "prix_achat", "prix_achat_standard", "purchase_price",
            "purchase_rate", "last_purchase_price", "buy_price",
            "cout_achat", "last_purchase_rate",
        ],
    },
    {
        ocr: "custom_conditionnement_achat", frappe: "custom_conditionnement_achat",
        label: "Conditionnement achat", type: "Data", sensitivity: 3,
        aliases: ["conditionnement_achat", "custom_conditionnement_achat"],
    },
    {
        ocr: "custom_coef_uc_ua", frappe: "custom_coef_uc_ua",
        label: "Coef UC-UA", type: "Float", sensitivity: 3,
        aliases: ["coef_uc_ua", "custom_coef_uc_ua"],
    },

    { section: "Fournisseurs — Qualité" },
    {
        ocr: "custom_priorite_fournisseur", frappe: "custom_priorite_fournisseur",
        label: "Priorité fournisseur", type: "Int", sensitivity: 3,
        aliases: ["priorite_fournisseur", "custom_priorite_fournisseur"],
    },
    {
        ocr: "custom_note_qualite", frappe: "custom_note_qualite",
        label: "Note qualité", type: "Float", sensitivity: 3,
        aliases: ["note_qualite", "custom_note_qualite"],
    },
    {
        ocr: "custom_soumis_controle", frappe: "custom_soumis_controle",
        label: "Soumis à contrôle", type: "Data", sensitivity: 3,
        aliases: ["soumis_controle", "custom_soumis_controle"],
    },
    {
        ocr: "custom_frequence_controle", frappe: "custom_frequence_controle",
        label: "Fréquence contrôle", type: "Int", sensitivity: 3,
        aliases: ["frequence_controle", "custom_frequence_controle"],
    },
    {
        ocr: "custom_numero_controle", frappe: "custom_numero_controle",
        label: "Numéro contrôle", type: "Data", sensitivity: 3,
        aliases: ["numero_controle", "custom_numero_controle"],
    },
    {
        ocr: "custom_fiche_qualite", frappe: "custom_fiche_qualite",
        label: "Fiche qualité", type: "Data", sensitivity: 3,
        aliases: ["fiche_qualite", "custom_fiche_qualite"],
    },

    { section: "Fournisseurs — Divers" },
    {
        ocr: "custom_majoration_cee", frappe: "custom_majoration_cee",
        label: "Majoration CEE", type: "Float", sensitivity: 3,
        aliases: ["majoration_cee", "custom_majoration_cee"],
    },
    {
        ocr: "custom_contremarque_fournisseur", frappe: "custom_contremarque_fournisseur",
        label: "Contremarque (fournisseur)", type: "Check", sensitivity: 3,
        aliases: ["contremarque_fournisseur", "custom_contremarque_fournisseur"],
    },

    { section: "Fournisseurs — Sous-traitance" },
    {
        ocr: "custom_alt_sous_traitance", frappe: "custom_alt_sous_traitance",
        label: "Alt sous-traitance", type: "Data", sensitivity: 3,
        aliases: ["alt_sous_traitance", "custom_alt_sous_traitance"],
    },
    {
        ocr: "custom_delai_sous_traitance", frappe: "custom_delai_sous_traitance",
        label: "Délai sous-traitance", type: "Data", sensitivity: 3,
        aliases: ["delai_sous_traitance", "custom_delai_sous_traitance"],
    },
];

// ─────────────────────────────────────────────────────────────────────
// Peupler OCR_ARTICLE_CONFIG.champs_obligatoires depuis la source unique
// ─────────────────────────────────────────────────────────────────────
OCR_ARTICLE_CONFIG.champs_obligatoires = _get_champs_obligatoires().map(d => d.frappe);

// ─────────────────────────────────────────────────────────────────────
// TABLEAU STOCK PAR SITE — rendu dans le formulaire Item
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_afficher_tableau_sites(frm) {
    const FIELD = "custom_sites_appro";
    const fd    = frm.fields_dict[FIELD];
    if (!fd) return;

    frm.$wrapper.find(".ocr-sites-table-render").remove();
    frm.toggle_display(FIELD, false);

    const raw = frm.doc[FIELD] || "";
    if (!raw) return;

    try {
        const sites = JSON.parse(raw);
        if (!sites || !sites.length) return;

        const rows = sites.map(s => `
            <tr>
                <td style="padding:5px 8px;border:1px solid #dee2e6;font-weight:600;white-space:nowrap">${frappe.utils.escape_html(s.code || "")} — ${frappe.utils.escape_html(s.label || "")}</td>
                <td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right">${s.safety_stock  ?? 0}</td>
                <td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right">${s.stock_max     ?? 0}</td>
                <td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right">${s.reorder_level ?? 0}</td>
                <td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right">${s.reorder_qty   ?? 0}</td>
                <td style="padding:5px 8px;border:1px solid #dee2e6;text-align:right">${s.lot_size      ?? 0}</td>
                <td style="padding:5px 8px;border:1px solid #dee2e6">${frappe.utils.escape_html(s.categorie_abc   || "")}</td>
                <td style="padding:5px 8px;border:1px solid #dee2e6">${frappe.utils.escape_html(s.mode_inventaire || "")}</td>
                <td style="padding:5px 8px;border:1px solid #dee2e6">${frappe.utils.escape_html(s.mode_retrait    || "")}</td>
                <td style="padding:5px 8px;border:1px solid #dee2e6;text-align:center">${s.gestion_emplacement ? "✓" : ""}</td>
            </tr>`).join("");

        const html = `
            <div class="ocr-sites-table-render frappe-field-group" style="margin:8px 15px 12px;">
                <label class="control-label" style="font-size:12px;font-weight:600;color:#6c757d;
                        text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:6px;">
                    Stock par site (Sage ERP)
                </label>
                <div style="overflow-x:auto">
                    <table style="width:100%;border-collapse:collapse;font-size:12px">
                        <thead style="background:#f0f4f8">
                            <tr>
                                <th style="padding:5px 8px;border:1px solid #dee2e6;text-align:left">Site</th>
                                <th style="padding:5px 8px;border:1px solid #dee2e6">Stock sécu.</th>
                                <th style="padding:5px 8px;border:1px solid #dee2e6">Stock max</th>
                                <th style="padding:5px 8px;border:1px solid #dee2e6">Seuil réappro</th>
                                <th style="padding:5px 8px;border:1px solid #dee2e6">Qté mini réappro</th>
                                <th style="padding:5px 8px;border:1px solid #dee2e6">Taille lot</th>
                                <th style="padding:5px 8px;border:1px solid #dee2e6">Cat. ABC</th>
                                <th style="padding:5px 8px;border:1px solid #dee2e6">Mode inventaire</th>
                                <th style="padding:5px 8px;border:1px solid #dee2e6">Mode retrait</th>
                                <th style="padding:5px 8px;border:1px solid #dee2e6">Emplac.</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>`;

        $(fd.$wrapper).after($(html));

    } catch (e) {
        console.warn("[OCR Article] Erreur rendu tableau sites:", e);
    }
}

// ─────────────────────────────────────────────────────────────────────
// BOUTON PRINCIPAL
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_ajouter_bouton(frm) {
    frm.add_custom_button(
        __("📄 OCR Fiche Article"),
        () => _ocr_article_ouvrir_dialog(frm),
        __("OCR")
    );
}

// ─────────────────────────────────────────────────────────────────────
// DIALOG UPLOAD
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_ouvrir_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title:  __("OCR — Fiche Technique Article"),
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "info_html",
                options: `
                    <div style="
                        background:#f0f7ff;
                        border:1px solid #b3d4f5;
                        border-radius:6px;
                        padding:12px 16px;
                        margin-bottom:12px;
                        font-size:13px;
                        color:#2c5f8a;
                    ">
                        <strong>📋 Documents acceptés :</strong><br>
                        Fiche technique produit · Catalogue fournisseur · Étiquette produit<br>
                        <span style="color:#666;font-size:12px;">
                            Formats : PDF, PNG, JPG, TIFF, BMP, XLSX, SVG &nbsp;|&nbsp; Taille : 2 KB – 15 MB
                        </span>
                    </div>
                `,
            },
            {
                fieldtype:   "Attach",
                fieldname:   "fichier_fiche",
                label:       __("Fiche technique à analyser"),
                reqd:        1,
                description: __("Glissez-déposez ou cliquez pour sélectionner"),
            },
            {
                fieldtype: "HTML",
                fieldname: "progression_html",
                options:   `<div id="ocr_article_progress" style="display:none;margin-top:8px;"></div>`,
            },
        ],
        primary_action_label: __("🔍 Analyser"),
        primary_action(values) {
            if (!values.fichier_fiche) {
                frappe.msgprint(__("Veuillez sélectionner une fiche technique."));
                return;
            }
            _ocr_article_lancer_analyse(frm, dialog, values.fichier_fiche);
        },
    });

    dialog.show();
}

// ─────────────────────────────────────────────────────────────────────
// LANCEMENT ANALYSE
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_lancer_analyse(frm, dialog, file_url) {
    _ocr_article_set_progress(dialog, "info", "⏳ Envoi du document au moteur OCR…");
    dialog.get_primary_btn().prop("disabled", true).text(__("Analyse en cours…"));

    frappe.call({
        method:  OCR_ARTICLE_CONFIG.pipeline_endpoint,
        args:    { file_url, source_doctype: "Item" },
        callback(r) {
            if (!r.message || !r.message.success) {
                const err = (r.message && r.message.erreur) || __("Erreur inconnue.");
                _ocr_article_set_progress(dialog, "danger",
                    `❌ Impossible de démarrer l'analyse : ${err}`);
                dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
                return;
            }
            const job_id = r.message.job_id;
            _ocr_article_set_progress(dialog, "info",
                "🔄 Analyse en cours (fiche technique)… veuillez patienter.");
            _ocr_article_polling(frm, dialog, job_id, 0, file_url);
        },
        error() {
            _ocr_article_set_progress(dialog, "danger",
                "❌ Erreur de communication avec le serveur.");
            dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
        },
    });
}

// ─────────────────────────────────────────────────────────────────────
// POLLING
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_polling(frm, dialog, job_id, tentative, source_file_url) {
    if (tentative >= OCR_ARTICLE_CONFIG.poll_max_attempts) {
        _ocr_article_set_progress(dialog, "warning",
            "⏰ Délai d'attente dépassé. Veuillez réessayer.");
        dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
        return;
    }

    setTimeout(() => {
        frappe.call({
            method:  OCR_ARTICLE_CONFIG.statut_endpoint,
            args:    { job_id },
            callback(r) {
                const data = r.message || {};

                if (data.status === "en_cours") {
                    const dots = ".".repeat((tentative % 3) + 1);
                    _ocr_article_set_progress(dialog, "info",
                        `🔄 Analyse en cours${dots} (${Math.round(tentative * OCR_ARTICLE_CONFIG.poll_interval_ms / 1000)}s)`);
                    _ocr_article_polling(frm, dialog, job_id, tentative + 1, source_file_url);
                    return;
                }

                if (data.status === "erreur") {
                    _ocr_article_set_progress(dialog, "danger",
                        `❌ Erreur : ${data.erreur || "Erreur inconnue."}`);
                    dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
                    return;
                }

                if (data.status === "termine") {
                    const res = data.result || {};
                    if (source_file_url) res._source_file_url = source_file_url;
                    _ocr_article_traiter_resultat(frm, dialog, res);
                    return;
                }

                _ocr_article_polling(frm, dialog, job_id, tentative + 1, source_file_url);
            },
            error() {
                _ocr_article_polling(frm, dialog, job_id, tentative + 1, source_file_url);
            },
        });
    }, OCR_ARTICLE_CONFIG.poll_interval_ms);
}

// ─────────────────────────────────────────────────────────────────────
// TRAITEMENT DU RÉSULTAT
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_traiter_resultat(frm, dialog, result) {

    if (result.doublon) {
        dialog.hide();
        frappe.confirm(
            `<div style="padding:8px 0;">
                <b>⚠️ Article déjà existant</b><br><br>
                Un article avec le code <b>${result.item_code || ""}</b>
                existe déjà dans ERPNext :<br>
                <b>${result.doublon_label || result.doublon_name}</b><br><br>
                Voulez-vous ouvrir cet article existant ?
            </div>`,
            () => frappe.set_route("Form", "Item", result.doublon_name),
            () => {}
        );
        return;
    }

    if (!result.success) {
        _ocr_article_set_progress(dialog, "danger",
            `❌ ${result.erreur || "Analyse échouée."}`
            + (result.conseil ? `<br><small>💡 ${result.conseil}</small>` : "")
        );
        dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
        return;
    }

    const champs_base = result.champs_remplis || {};
    const champs_alt  = result.form_fields || {};
    const champs = Object.assign({}, champs_alt, champs_base);
    const score  = result.score_confiance || 0;

    if (!Object.keys(champs).length) {
        _ocr_article_set_progress(dialog, "warning",
            "⚠️ Aucun champ article extrait. Vérifiez la qualité du document.");
        dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
        return;
    }

    dialog.hide();
    _ocr_article_dialog_validation(frm, champs, score, result);
}

// ─────────────────────────────────────────────────────────────────────
// DIALOG VALIDATION
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_dialog_validation(frm, champs, score, result) {
    champs = (champs && typeof champs === "object") ? champs : {};
    const confiances = (result && result.confiances) || {};
    let _sites_appro_data = [];

    const score_color = score >= 80 ? "#28a745" : score >= 60 ? "#fd7e14" : "#dc3545";
    const score_icon  = score >= 80 ? "✅" : score >= 60 ? "⚠️" : "❌";

    // ── Résumé + légende des marqueurs ──────────────────────────────
    const summary_html = `
        <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:6px;
                    padding:10px 14px;margin-bottom:10px;font-size:13px;color:#495057;">
            ${score_icon} Score OCR :
            <b style="color:${score_color};">${score}%</b>
            &nbsp;|&nbsp; Type détecté :
            <b>${frappe.utils.escape_html(result.type_document || "fiche_article")}</b>
            &nbsp;|&nbsp; ${Object.keys(champs).length} champ(s) extrait(s)
            ${score < OCR_ARTICLE_CONFIG.score_warning_seuil
                ? `<br><span style="color:#856404;">⚠ Score faible — vérifiez les champs avant validation.</span>`
                : ""}
        </div>
        <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:6px;
                    padding:8px 14px;margin-bottom:12px;font-size:12px;color:#5d4037;">
            <b>Légende :</b>
            &nbsp;⛔ Obligatoire non rempli — saisie manuelle requise
            &nbsp;·&nbsp; ⚠ Confiance faible — à vérifier
            &nbsp;·&nbsp; ✓ Extrait avec bonne confiance
        </div>`;

    const fields = [{ fieldtype: "HTML", fieldname: "ocr_resume", options: summary_html }];

    for (const def of OCR_ARTICLE_DIALOG_FIELDS) {
        if (!def.frappe) {
            if (def.section) {
                fields.push({ fieldtype: "Section Break", label: __(def.section) });
            } else if (def.sites_table) {
                const raw = champs["custom_sites_appro"] || "";
                let html = "";
                if (raw) {
                    try {
                        const sites = JSON.parse(raw);
                        _sites_appro_data = sites;
                        const inp = (idx, field, val, type, w) =>
                            `<input type="${type}" data-site-idx="${idx}" data-field="${field}"
                             value="${val}"
                             style="width:${w};border:1px solid #ced4da;border-radius:3px;
                                    padding:2px 4px;font-size:11px;
                                    ${type === "number" ? "text-align:right" : ""}"
                            >`;
                        const chk = (idx, field, checked) =>
                            `<input type="checkbox" data-site-idx="${idx}" data-field="${field}"
                             ${checked ? "checked" : ""}
                             style="cursor:pointer;width:16px;height:16px"
                            >`;
                        const rows = sites.map((s, idx) => `
                            <tr>
                                <td style="padding:4px 6px;border:1px solid #dee2e6;font-weight:600;white-space:nowrap">${s.code || ""} — ${s.label || ""}</td>
                                <td style="padding:2px 4px;border:1px solid #dee2e6">${inp(idx, "safety_stock",  s.safety_stock  ?? 0, "number", "65px")}</td>
                                <td style="padding:2px 4px;border:1px solid #dee2e6">${inp(idx, "stock_max",     s.stock_max     ?? 0, "number", "65px")}</td>
                                <td style="padding:2px 4px;border:1px solid #dee2e6">${inp(idx, "reorder_level", s.reorder_level ?? 0, "number", "65px")}</td>
                                <td style="padding:2px 4px;border:1px solid #dee2e6">${inp(idx, "reorder_qty",   s.reorder_qty   ?? 0, "number", "65px")}</td>
                                <td style="padding:2px 4px;border:1px solid #dee2e6">${inp(idx, "lot_size",      s.lot_size      ?? 0, "number", "55px")}</td>
                                <td style="padding:2px 4px;border:1px solid #dee2e6">${inp(idx, "categorie_abc",     s.categorie_abc    || "", "text", "80px")}</td>
                                <td style="padding:2px 4px;border:1px solid #dee2e6">${inp(idx, "mode_inventaire",   s.mode_inventaire  || "", "text", "110px")}</td>
                                <td style="padding:2px 4px;border:1px solid #dee2e6">${inp(idx, "mode_retrait",      s.mode_retrait     || "", "text", "90px")}</td>
                                <td style="padding:2px 4px;border:1px solid #dee2e6;text-align:center">${chk(idx, "gestion_emplacement", s.gestion_emplacement)}</td>
                            </tr>`.trim()
                        ).join("");
                        html = `
                            <div style="overflow-x:auto;margin:6px 0">
                                <table style="width:100%;border-collapse:collapse;font-size:12px">
                                    <thead style="background:#f0f4f8">
                                        <tr>
                                            <th style="padding:4px 8px;border:1px solid #dee2e6;text-align:left">Site</th>
                                            <th style="padding:4px 8px;border:1px solid #dee2e6">Stock sécu.</th>
                                            <th style="padding:4px 8px;border:1px solid #dee2e6">Stock max</th>
                                            <th style="padding:4px 8px;border:1px solid #dee2e6">Seuil réappro</th>
                                            <th style="padding:4px 8px;border:1px solid #dee2e6">Qté mini réappro</th>
                                            <th style="padding:4px 8px;border:1px solid #dee2e6">Taille lot</th>
                                            <th style="padding:4px 8px;border:1px solid #dee2e6">Cat. ABC</th>
                                            <th style="padding:4px 8px;border:1px solid #dee2e6">Mode inventaire</th>
                                            <th style="padding:4px 8px;border:1px solid #dee2e6">Mode retrait</th>
                                            <th style="padding:4px 8px;border:1px solid #dee2e6">Emplac.</th>
                                        </tr>
                                    </thead>
                                    <tbody>${rows}</tbody>
                                </table>
                            </div>`;
                    } catch (e) {
                        html = `<p style="color:#dc3545">⚠ Impossible de lire les données multi-sites.</p>`;
                    }
                } else {
                    html = `<p style="color:#6c757d;font-style:italic">Aucune donnée multi-sites extraite.</p>`;
                }
                fields.push({ fieldtype: "HTML", fieldname: "sites_appro_html", options: html });
            }
            continue;
        }

        // ── Résolution de la valeur OCR ──────────────────────────────
        let val = "";
        for (const key of [def.frappe, def.ocr, ...(def.aliases || [])].filter(Boolean)) {
            const candidate = champs[key];
            if (candidate !== undefined && candidate !== null && String(candidate).trim() !== "") {
                val = candidate;
                break;
            }
        }

        if (def.type === "Currency" && val !== "") {
            const converted = _ocr_article_convertir_montant(val);
            val = converted > 0 ? converted : "";
        } else if (def.type === "Check" && val !== "") {
            val = parseInt(val) || 0;
        } else if ((def.type === "Float" || def.type === "Int") && val !== "") {
            const n = parseFloat(String(val).replace(",", "."));
            val = (isFinite(n) && n !== 0) ? n : "";
        }

        const _valIsEmpty = (
            val === "" || val === null || val === undefined ||
            ((def.type === "Currency" || def.type === "Float" || def.type === "Int") && val === 0)
        );

       
        const field = {
            fieldtype: def.type,
            fieldname: def.frappe,
            label:     def.label,
            // Pour les champs vides, mettre "" plutôt que undefined
            // afin que Frappe initialise le champ et crée la help-box
            default:   _valIsEmpty ? "" : val,
        };
        if (def.options) field.options = def.options;

        // ── Description / marqueur ───────────────────────────────────
        const conf = confiances[def.ocr];

        if (def.sensitivity === 1) {
            field.reqd = 1;
            if (_valIsEmpty) {
                // Champ obligatoire non rempli par l'OCR
                field.description = `<span style="color:#dc3545;font-weight:500;">
                    ⛔ Ce champ est obligatoire — doit être saisi manuellement
                </span>`;
                // CORRECTIF : Frappe force 0 sur Currency/Float/Int même sans default
                if (["Currency", "Float", "Int"].includes(def.type)) {
                    field.default = "";
                }
            } else if (conf !== undefined && conf < 0.55) {
                // Rempli mais confiance faible
                field.description = `<span style="color:#856404;">
                    ⚠ Confiance faible — vérifiez cette valeur
                </span>`;
            } else {
                // Rempli avec bonne confiance
                field.description = `<span style="color:#28a745;">
                    ✓ Extrait avec bonne confiance
                </span>`;
            }
        } else if (conf !== undefined && conf < 0.55) {
            // Champ non-obligatoire mais confiance faible
            field.description = `<span style="color:#856404;">
                ⚠ Confiance faible — vérifiez cette valeur
            </span>`;
        }

        fields.push(field);
    }  // ← fin du for (const def of OCR_ARTICLE_DIALOG_FIELDS)

    // ── Création du dialog ───────────────────────────────────────────
    const d = new frappe.ui.Dialog({
        title                 : __("Formulaire OCR à valider"),
        fields                : fields,
        size                  : "large",
        primary_action_label  : __("Enregistrer"),
        secondary_action_label: __("Appliquer sans enregistrer"),

        secondary_action() {
            const manquants = _ocr_article_valider_obligatoires(d);
            if (manquants.length) {
                _ocr_article_afficher_erreurs_dialog(d, manquants);
                return;
            }
            const vals = d.get_values() || {};
            const sites_json = _lire_sites_depuis_dom(d, _sites_appro_data);
            if (sites_json) vals.custom_sites_appro = sites_json;
            d.hide();
            _ocr_article_appliquer_au_formulaire(frm, vals, false, result);
        },

        primary_action(vals) {
            const manquants = _ocr_article_valider_obligatoires(d);
            if (manquants.length) {
                _ocr_article_afficher_erreurs_dialog(d, manquants);
                return;
            }
            vals = vals || {};
            const sites_json = _lire_sites_depuis_dom(d, _sites_appro_data);
            if (sites_json) vals.custom_sites_appro = sites_json;
            d.hide();
            _ocr_article_appliquer_au_formulaire(frm, vals, true, result);
        },
    });

    d.show();

    // ── Après affichage : surligner les champs obligatoires vides ────
    // ── Après affichage : marquer les champs obligatoires vides ────
    [300, 800, 1500].forEach(delay => {
        setTimeout(() => _ocr_article_marquer_champs_obligatoires(d), delay);
    });
}

// ─────────────────────────────────────────────────────────────────────
// SURLIGNAGE VISUEL des champs obligatoires vides dans le dialog
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_marquer_champs_obligatoires(dialog) {
    const obligatoires = _get_champs_obligatoires();
    obligatoires.forEach(function(def) {
        const fd = dialog.fields_dict[def.frappe];
        if (!fd || !fd.$wrapper) return;

        const $input = fd.$wrapper.find("input.form-control, textarea.form-control").first();
        const val_dom = $input.length ? ($input.val() || "") : "";
        const val_frappe = dialog.get_value(def.frappe);

        const est_vide = (
            (val_dom === "" || val_dom === "0") &&
            (val_frappe === null || val_frappe === undefined ||
             String(val_frappe).trim() === "" || val_frappe === 0)
        );

        // Chercher la help-box, la créer si absente
        let $help = fd.$wrapper.find("p.help-box");
        if (!$help.length) {
            $help = $('<p class="help-box small text-muted"></p>');
            fd.$wrapper.find(".control-input-wrapper, .form-group").last().append($help);
        }

        if (!est_vide) {
            $input.css({ "border-color": "", "box-shadow": "" });
            $help.html("").hide();
            return;
        }

        $input.css({
            "border-color": "#dc3545",
            "box-shadow":   "0 0 0 0.15rem rgba(220,53,69,.15)",
        });

        $help
            .html(`<span style="color:#dc3545;font-weight:500;">
                ⛔ Obligatoire — saisie manuelle requise
            </span>`)
            .show();
    });
}

function _ocr_article_surligner_champs_obligatoires(dialog) {
    _ocr_article_marquer_champs_obligatoires(dialog);
}//────────────────────────────────────────────────────────────────────
// AFFICHAGE ERREURS DANS LE DIALOG (sans fermer)
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_afficher_erreurs_dialog(dialog, manquants) {
    frappe.msgprint({
        title    : __("Champs obligatoires manquants"),
        message  : __("Veuillez renseigner les champs suivants avant de continuer :")
                   + "<ul style='margin:8px 0 0 0;padding-left:20px'>"
                   + manquants.map(l => `<li><b>${l}</b></li>`).join("")
                   + "</ul>"
                   + `<p style="margin-top:8px;color:#6c757d;font-size:12px;">
                       Ces champs sont encadrés en rouge dans le formulaire.
                      </p>`,
        indicator: "red",
    });
    // Re-surligner après l'affichage du message
    _ocr_article_surligner_champs_obligatoires(dialog);
}

// ─────────────────────────────────────────────────────────────────────
// VALIDATION DES CHAMPS OBLIGATOIRES DU DIALOG
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_valider_obligatoires(dialog) {
    const obligatoires = _get_champs_obligatoires();
    const manquants = [];
    for (const def of obligatoires) {
        const val = dialog.get_value(def.frappe);
        const vide = (
            val === null      ||
            val === undefined ||
            String(val).trim() === "" ||
            val === 0
        );
        if (vide) manquants.push(def.label);
    }
    return manquants;
}

// ─────────────────────────────────────────────────────────────────────
// LECTURE DES VALEURS DU TABLEAU SITES DEPUIS LE DOM DU DIALOG
// ─────────────────────────────────────────────────────────────────────
function _lire_sites_depuis_dom(d, sites_original) {
    try {
        if (!sites_original || !sites_original.length) return null;
        const inputs = d.$wrapper.find("input[data-site-idx]");
        if (!inputs.length) return null;
        const sites = JSON.parse(JSON.stringify(sites_original));
        inputs.each(function () {
            const idx   = parseInt($(this).data("site-idx"));
            const field = $(this).data("field");
            if (isNaN(idx) || !field || !sites[idx]) return;
            if ($(this).attr("type") === "checkbox") {
                sites[idx][field] = this.checked;
            } else if ($(this).attr("type") === "number") {
                sites[idx][field] = parseFloat($(this).val()) || 0;
            } else {
                sites[idx][field] = $(this).val() || "";
            }
        });
        return JSON.stringify(sites, null, 2);
    } catch (e) {
        console.warn("[OCR Article] _lire_sites_depuis_dom error:", e);
        return null;
    }
}

// ─────────────────────────────────────────────────────────────────────
// APPLICATION AU FORMULAIRE
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_appliquer_au_formulaire(frm, vals, enregistrer, result) {
    vals = (vals && typeof vals === "object") ? vals : {};
    const champs_remplis = [];
    const champs_ignores = [];

    const ocr_data = Object.assign(
        {},
        (result && result.form_fields)    || {},
        (result && result.champs_remplis) || {}
    );

    for (const def of OCR_ARTICLE_DIALOG_FIELDS) {
        const field = def.frappe;
        const val   = vals[field];

        if (val === null || val === undefined || String(val).trim() === "") continue;

        if (!frm.fields_dict[field]) {
            champs_ignores.push(field);
            continue;
        }

        if (field === "item_code" && frm.doc[field] && String(frm.doc[field]).trim() !== "") {
            champs_ignores.push(field);
            continue;
        }

        let normalized;
        if (def.type === "Currency") {
            normalized = _ocr_article_convertir_montant(val);
        } else if (def.type === "Check") {
            normalized = parseInt(val) || 0;
        } else if (def.type === "Float") {
            normalized = parseFloat(String(val).replace(",", ".")) || 0;
        } else if (def.type === "Int") {
            normalized = parseInt(val) || 0;
        } else {
            normalized = val;
        }

        if ((def.type === "Currency" || def.type === "Float" || def.type === "Int")
                && normalized === 0) {
            const ocr_val = ocr_data[def.frappe] !== undefined
                ? ocr_data[def.frappe]
                : ocr_data[def.ocr];
            const ocr_num = (ocr_val !== undefined && ocr_val !== null)
                ? parseFloat(String(ocr_val).replace(",", "."))
                : NaN;
            if (isNaN(ocr_num) || ocr_num === 0) {
                champs_ignores.push(field);
                continue;
            }
        }

        frm.set_value(field, normalized);
        champs_remplis.push(OCR_ARTICLE_CONFIG.labels[field] || field);
    }

    frm.dirty();
    frm.refresh_fields();

    // ── Remplissage reorder_levels (multi-site Sage ERP) ─────────────
    const sites_appro_raw = vals.custom_sites_appro
        || (result && result.champs_remplis && result.champs_remplis.custom_sites_appro)
        || (result && result.form_fields    && result.form_fields.custom_sites_appro)
        || "";
    if (sites_appro_raw) {
        try {
            const sites = JSON.parse(sites_appro_raw);
            const sites_non_nuls = sites.filter(s =>
                (s.reorder_level && s.reorder_level !== 0) ||
                (s.reorder_qty   && s.reorder_qty   !== 0) ||
                (s.safety_stock  && s.safety_stock  !== 0)
            );
            if (sites_non_nuls.length > 0) {
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype:          "Warehouse",
                        filters:          [["disabled", "=", 0]],
                        fields:           ["name", "warehouse_name"],
                        limit_page_length: 100,
                    },
                    callback(r) {
                        const warehouses         = (r && r.message) || [];
                        const reorder_rows_added = [];
                        for (const site of sites_non_nuls) {
                            const label_lower = (site.label || site.code || "").toLowerCase();
                            const wh = warehouses.find(w =>
                                w.warehouse_name.toLowerCase().includes(label_lower)
                                || label_lower.includes(w.warehouse_name.toLowerCase())
                                || (w.name || "").toLowerCase().includes(label_lower)
                            );
                            if (!wh) continue;
                            const child = frappe.model.add_child(frm.doc, "reorder_levels");
                            frappe.model.set_value(child.doctype, child.name, "warehouse",                wh.name);
                            frappe.model.set_value(child.doctype, child.name, "warehouse_reorder_level", site.reorder_level || 0);
                            frappe.model.set_value(child.doctype, child.name, "warehouse_reorder_qty",   site.reorder_qty   || 0);
                            frappe.model.set_value(child.doctype, child.name, "material_request_type",   "Purchase");
                            reorder_rows_added.push(`${site.code} → ${wh.name}`);
                        }
                        if (reorder_rows_added.length > 0) {
                            frm.refresh_field("reorder_levels");
                            frappe.show_alert({
                                message:   `📦 Niveaux de réappro configurés pour : ${reorder_rows_added.join(", ")}`,
                                indicator: "blue",
                            }, 6);
                        }
                    },
                });
            }
        } catch (e) {
            console.warn("[OCR Article] custom_sites_appro JSON parse error:", e);
        }
    }

    if (result && result.ocr_document_id) {
        console.log("[OCR Article] OCR Document :", result.ocr_document_id);
    }

    if (enregistrer) {
        frm.save()
            .then(() => {
                frappe.show_alert({ message: __("Article sauvegardé."), indicator: "green" }, 4);
                const _doctype = frm.doctype;
                const _docname = frm.doc.name || frm.docname;
                const _furl    = result && result._source_file_url;
                if (_furl && _docname) {
                    frappe.call({
                        method:  "ocr_intelligent.api.auto_create_document.attacher_copie_originale",
                        args:    { doctype: _doctype, docname: _docname, file_url: _furl },
                        freeze:  false,
                        callback(r) {
                            const res = r && r.message;
                            if (res && res.success) {
                                const target = (cur_frm && cur_frm.docname === _docname)
                                    ? cur_frm : frm;
                                target.reload_doc();
                            } else {
                                frappe.show_alert({
                                    message:   __("Fichier sauvegardé mais non attaché automatiquement."),
                                    indicator: "orange",
                                }, 5);
                            }
                        },
                        error() {
                            frappe.show_alert({
                                message:   __("Impossible d'attacher le fichier source."),
                                indicator: "orange",
                            }, 5);
                        },
                    });
                }
            })
            .catch(() => frappe.show_alert({
                message:   __("Champs appliqués, enregistrement échoué."),
                indicator: "orange",
            }, 6));
    }

    if (champs_remplis.length > 0) {
        const liste = champs_remplis.map(l => `<li>${l}</li>`).join("");
        frappe.show_alert({
            message: `
                <b>✅ ${champs_remplis.length} champ(s) appliqué(s) :</b>
                <ul style="margin:4px 0 0 0;padding-left:18px;">${liste}</ul>
                ${champs_ignores.length > 0
                    ? `<small style="color:#6c757d;">${champs_ignores.length} champ(s) ignoré(s)</small>`
                    : ""}
            `,
            indicator: "green",
        }, 6);
    } else {
        frappe.msgprint({
            title    : __("OCR Article"),
            message  : __("Aucun champ n'a pu être rempli automatiquement."),
            indicator: "orange",
        });
    }
}

// ─────────────────────────────────────────────────────────────────────
// UTILITAIRE : Conversion montant
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_convertir_montant(val) {
    if (!val && val !== 0) return 0;
    if (typeof val === "number") return isFinite(val) ? val : 0;
    let s = String(val).trim()
        .replace(/[\u00A0\u202F]/g, " ")
        .replace(/\s*(?:TND|DT|EUR|€|\$)\s*/gi, "")
        .replace(/\s+/g, "");
    if (s.includes(",") && s.includes(".")) {
        s = s.lastIndexOf(",") > s.lastIndexOf(".")
            ? s.replace(/\./g, "").replace(",", ".")
            : s.replace(/,/g, "");
    } else if (s.includes(",")) {
        s = s.replace(/\./g, "").replace(",", ".");
    }
    const n = parseFloat(s);
    return isNaN(n) ? 0 : n;
}

// ─────────────────────────────────────────────────────────────────────
// UTILITAIRE UI — barre de progression colorée
// ─────────────────────────────────────────────────────────────────────
function _ocr_article_set_progress(dialog, type, message) {
    const colors = {
        info:    { bg: "#d1ecf1", border: "#bee5eb", text: "#0c5460" },
        success: { bg: "#d4edda", border: "#c3e6cb", text: "#155724" },
        warning: { bg: "#fff3cd", border: "#ffc107", text: "#856404" },
        danger:  { bg: "#f8d7da", border: "#f5c6cb", text: "#721c24" },
    };
    const c    = colors[type] || colors.info;
    const $div = dialog.$wrapper.find("#ocr_article_progress");
    $div.html(`
        <div style="
            background:${c.bg};
            border:1px solid ${c.border};
            color:${c.text};
            border-radius:5px;
            padding:8px 12px;
            font-size:13px;
        ">
            ${message}
        </div>
    `).show();
}