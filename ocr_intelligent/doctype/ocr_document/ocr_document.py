import frappe
from frappe.model.document import Document

class OCRDocument(Document):

    def before_insert(self):
        # À la création : utiliser l'utilisateur connecté
        if not self.uploaded_by:
            self.uploaded_by = frappe.session.user
        if not self.status:
            self.status = "En attente"

    def before_save(self):
        # Ignorer si c'est une nouvelle insertion (géré par before_insert)
        if self.is_new():
            return
        
        original = frappe.db.get_value(
            "OCR Document", self.name,
            ["uploaded_by", "status"],
            as_dict=True
        )
        if not original:
            return

        # Protéger uploaded_by : garder la valeur originale SAUF si elle était vide
        if original.get("uploaded_by"):
            self.uploaded_by = original["uploaded_by"]

        # Protéger status : ne pas écraser si déjà dans un statut final
        statuts_finaux = {"Validé", "Rejeté"}
        if original.get("status") in statuts_finaux:
            self.status = original["status"]


# ── Hook Purchase Invoice ──────────────────────────────────────────────
def sync_statut_depuis_purchase_invoice(doc, method):
    bill_no = getattr(doc, "bill_no", None)
    if not bill_no:
        return

    ocr_docs = frappe.get_all(
        "OCR Document",
        filters=[["extracted_field", "like", f"%{bill_no}%"]],
        fields=["name", "status"],
        limit=5
    )

    if not ocr_docs:
        return

    if method == "on_submit":
        nouveau_statut = "Validé"
    elif method == "on_cancel":
        nouveau_statut = "En attente"
    else:
        return

    for ocr_doc in ocr_docs:
        frappe.db.set_value("OCR Document", ocr_doc["name"], "status", nouveau_statut)

    frappe.db.commit()