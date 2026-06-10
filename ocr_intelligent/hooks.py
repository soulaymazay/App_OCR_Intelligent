app_name = "ocr_intelligent"
app_title = "OCR Intelligent"
app_publisher = "OCR automatique pour les documents financiers"
app_description = "Bayoudh Metal"
app_email = "soulaymazay@gmail.com"
app_license = "MIT"

# ─────────────────────────────────────────────────────────────────────
# JS chargé dans toutes les pages du bureau Frappe
# ─────────────────────────────────────────────────────────────────────

app_include_js = [
    "/assets/ocr_intelligent/js/ocr_form.js?v=6",
    "/assets/ocr_intelligent/js/ocr_article_form.js?v=4",
    "/assets/ocr_intelligent/js/ocr_bom_form.js?v=1"
]

boot_session = "ocr_intelligent.api.boot.ensure_party_types_boot"

# ─────────────────────────────────────────────────────────────────────
# Hook sur File : déclenche l'OCR automatique après chaque upload
# ─────────────────────────────────────────────────────────────────────

doc_events = {
    "File": {
        "after_insert": "ocr_intelligent.api.auto_create_document.auto_create_ocr_document"
    },
    "Payment Entry": {
        "validate": "ocr_intelligent.api.validators.validate_cheque_date",
        "after_insert": "ocr_intelligent.api.auto_create_document.enregistrer_document_module_dans_ocr"
    },
    "Purchase Invoice": {
        "after_insert": "ocr_intelligent.api.auto_create_document.enregistrer_document_module_dans_ocr"
    },
    "Sales Invoice": {
        "after_insert": "ocr_intelligent.api.auto_create_document.enregistrer_document_module_dans_ocr"
    },
    "Item": {
        "after_insert": "ocr_intelligent.api.auto_create_document.enregistrer_document_module_dans_ocr"
    },
    "Purchase Order": {
        "after_insert": "ocr_intelligent.api.auto_create_document.enregistrer_document_module_dans_ocr"
    },
    "Sales Order": {
        "after_insert": "ocr_intelligent.api.auto_create_document.enregistrer_document_module_dans_ocr"
    },
    "Purchase Receipt": {
        "after_insert": "ocr_intelligent.api.auto_create_document.enregistrer_document_module_dans_ocr"
    },
    "Delivery Note": {
        "after_insert": "ocr_intelligent.api.auto_create_document.enregistrer_document_module_dans_ocr"
    }
}
