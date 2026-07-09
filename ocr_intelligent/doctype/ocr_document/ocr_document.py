# -*- coding: utf-8 -*-
import frappe
from frappe.model.document import Document

# Mapping docstatus ERPNext → champ "status" OCR Document
_DOCSTATUS_TO_STATUT = {
    0: "En attente",
    1: "Validé",
    2: "Rejeté",
}


class OCRDocument(Document):

    # ── Hooks cycle de vie ────────────────────────────────────────────

    def before_insert(self):
        if not self.uploaded_by or self.uploaded_by == "Guest":
            self.uploaded_by = frappe.session.user
        if not self.status:
            self.status = "En attente"

    def before_save(self):
        if self.is_new():
            return

        original = frappe.db.get_value(
            "OCR Document", self.name,
            ["uploaded_by", "status"],
            as_dict=True
        )
        if not original:
            return

        # Protéger uploaded_by
        orig_user = original.get("uploaded_by")
        if orig_user and orig_user not in ("Guest", ""):
            self.uploaded_by = orig_user
        elif self.uploaded_by in ("Guest", "", None):
            self.uploaded_by = frappe.session.user

        # Empêcher rétrogradation manuelle vers "En attente"
        statuts_finaux = {"Validé", "Rejeté"}
        orig_statut = original.get("status")
        if orig_statut in statuts_finaux and self.status == "En attente":
            self.status = orig_statut

    def after_insert(self):
        self._sync_statut_depuis_doc_lie()

    def on_update(self):
        self._sync_statut_depuis_doc_lie()

    # ── Sync interne (doc lié → OCR Document) ────────────────────────

    def _sync_statut_depuis_doc_lie(self):
        """
        Synchronise 'status' avec le docstatus du document ERPNext lié.
        Utilise les champs linked_docname + linked_doctype si disponibles.
        """
        doc_lie       = self.get("linked_docname")
        type_document = self.get("linked_doctype")
        if not doc_lie or not type_document:
            return
        try:
            linked     = frappe.get_doc(type_document, doc_lie)
            new_statut = _DOCSTATUS_TO_STATUT.get(linked.docstatus)
            if new_statut and self.status != new_statut:
                frappe.db.set_value(
                    "OCR Document", self.name, "status", new_statut,
                    update_modified=False
                )
                self.status = new_statut
        except frappe.DoesNotExistError:
            pass


# ══════════════════════════════════════════════════════════════════════
# SYNC : Purchase Invoice / Payment Entry → OCR Document
# Appelée par hooks.py on_submit + on_cancel
# ══════════════════════════════════════════════════════════════════════

def sync_statut_depuis_purchase_invoice(doc, method=None):
    """
    Sync déclenchée par on_submit, on_cancel, ou on_update (workflow).
    Lit docstatus ET workflow_state pour couvrir les deux cas.
    """

    # ── Mapping depuis workflow_state (si Workflow actif) ─────────────
    WORKFLOW_TO_STATUT = {
        "En Attente":          "En attente",
        "Pending":             "En attente",
        "Approved":            "Validé",
        "Approuvé":            "Validé",
        "Validé":              "Validé",
        "Rejected":            "Rejeté",
        "Rejeté":              "Rejeté",
        "Cancelled":           "Rejeté",
        "Annulé":              "Rejeté",
    }

    # ── Mapping depuis docstatus (soumission standard) ─────────────────
    DOCSTATUS_TO_STATUT = {
        0: "En attente",
        1: "Validé",
        2: "Rejeté",
    }

    # Priorité : workflow_state d'abord, puis docstatus
    workflow_state = doc.get("workflow_state") or ""
    new_statut = (
        WORKFLOW_TO_STATUT.get(workflow_state)
        or DOCSTATUS_TO_STATUT.get(doc.docstatus)
    )

    if not new_statut:
        return

    # ── Chercher les OCR Documents liés ───────────────────────────────
    ocr_docs = frappe.get_all(
        "OCR Document",
        filters={"linked_docname": doc.name, "linked_doctype": doc.doctype},
        fields=["name", "status"],
    )

    if not ocr_docs and getattr(doc, "bill_no", None):
        ocr_docs = frappe.get_all(
            "OCR Document",
            filters=[["extracted_field", "like", f"%{doc.bill_no}%"]],
            fields=["name", "status"],
            limit=5,
        )

    updated = 0
    for ocr in ocr_docs:
        if ocr.status != new_statut:
            frappe.db.set_value(
                "OCR Document", ocr.name, "status", new_statut,
                update_modified=False
            )
            updated += 1

    if updated:
        frappe.db.commit()
        frappe.logger().info(
            f"[OCR] sync: {updated} doc(s) → '{new_statut}' "
            f"via workflow_state='{workflow_state}' / docstatus={doc.docstatus}"
        )

# ══════════════════════════════════════════════════════════════════════
# SYNC : OCR Document "Validé" → soumet la Purchase Invoice liée
# Appelée par hooks.py on_update sur OCR Document
# ══════════════════════════════════════════════════════════════════════

def sync_statut_vers_purchase_invoice(doc, method=None):
    """
    Quand OCR Document passe à "Validé" → soumet la Purchase Invoice liée.
    Quand OCR Document passe à "Rejeté" → ajoute un commentaire.
    """
    if method != "on_update":
        return

    statut_en_base = frappe.db.get_value("OCR Document", doc.name, "status")
    if statut_en_base not in ("Validé", "Rejeté"):
        return

    inv_name = None
    if doc.get("linked_doctype") == "Purchase Invoice" and doc.get("linked_docname"):
        inv_name = doc.linked_docname
    else:
        inv_name = _trouver_invoice_depuis_ocr(doc)

    if not inv_name:
        return

    # ── Sauvegarder l'utilisateur AVANT d'élever les droits ──────────
    utilisateur_original = frappe.session.user  # ← CORRECTION

    try:
        frappe.set_user("Administrator")

        inv = frappe.get_doc("Purchase Invoice", inv_name)
        if inv.docstatus != 0:
            return  # Déjà soumise ou annulée

        if statut_en_base == "Validé":
            if _facture_prete_a_soumettre(inv):
                inv.submit()
                frappe.db.commit()
                frappe.publish_realtime(
                    event="msgprint",
                    message=f"Facture {inv_name} soumise automatiquement suite à la validation OCR.",
                    user=utilisateur_original,   # ← CORRECTION
                )
            else:
                frappe.publish_realtime(
                    event="msgprint",
                    message=(
                        f"OCR validé mais la facture {inv_name} est incomplète "
                        "(fournisseur, articles ou date manquants). "
                        "Complétez-la manuellement."
                    ),
                    user=utilisateur_original,   # ← CORRECTION
                )

        elif statut_en_base == "Rejeté":
            frappe.get_doc({
                "doctype":           "Comment",
                "comment_type":      "Info",
                "reference_doctype": "Purchase Invoice",
                "reference_name":    inv_name,
                "content":           "Document OCR rejeté — vérification manuelle requise.",
            }).insert(ignore_permissions=True)
            frappe.db.commit()

    except Exception as e:
        frappe.log_error(
            f"Erreur sync OCR → Purchase Invoice {inv_name} : {e}",
            "OCR Document Sync"
        )
    finally:
        frappe.set_user(utilisateur_original)   # ← CORRECTION : toujours réinitialiser


# ── Utilitaires ───────────────────────────────────────────────────────

def _trouver_invoice_depuis_ocr(ocr_doc):
    """Cherche une Purchase Invoice brouillon via bill_no dans extracted_field."""
    import json
    try:
        champs  = json.loads(ocr_doc.extracted_field or "{}")
        bill_no = champs.get("bill_no") or champs.get("numero_facture")
        if not bill_no:
            return None
        return frappe.db.get_value(
            "Purchase Invoice",
            {"bill_no": str(bill_no).strip(), "docstatus": 0},
            "name"
        )
    except Exception:
        return None


def _facture_prete_a_soumettre(inv):
    """Vérifie les champs minimaux avant soumission automatique."""
    return bool(inv.supplier and inv.items and inv.posting_date)
def sync_statut_item_dans_ocr(doc, method=None):
    """
    Synchronise le statut de l'OCR Document lié quand le workflow_state
    de l'Item change (ex: 'En Attente' → 'Approved').
    """
    WORKFLOW_TO_STATUT = {
        "En Attente":  "En attente",
        "Pending":     "En attente",
        "Approved":    "Validé",
        "Approuvé":    "Validé",
        "Validé":      "Validé",
        "Rejected":    "Rejeté",
        "Rejeté":      "Rejeté",
        "Cancelled":   "Rejeté",
        "Annulé":      "Rejeté",
    }

    workflow_state = doc.get("workflow_state") or ""
    new_statut = WORKFLOW_TO_STATUT.get(workflow_state)

    if not new_statut:
        return

    ocr_docs = frappe.get_all(
        "OCR Document",
        filters={"linked_docname": doc.name, "linked_doctype": "Item"},
        fields=["name", "status"],
    )

    if not ocr_docs and getattr(doc, "item_code", None):
        ocr_docs = frappe.get_all(
            "OCR Document",
            filters=[["extracted_field", "like", f"%{doc.item_code}%"]],
            fields=["name", "status"],
            limit=5,
        )

    updated = 0
    for ocr in ocr_docs:
        if ocr.status != new_statut:
            frappe.db.set_value(
                "OCR Document", ocr.name, "status", new_statut,
                update_modified=False
            )
            updated += 1

    if updated:
        frappe.db.commit()
        frappe.logger().info(
            f"[OCR] sync Item: {updated} doc(s) → '{new_statut}' "
            f"via workflow_state='{workflow_state}'"
        )
def sync_statut_bom_dans_ocr(doc, method=None):
    """
    Synchronise le statut de l'OCR Document lié quand le BOM change
    de statut (docstatus et/ou workflow_state).
    Évite que les BOM déjà approuvés/soumis restent affichés dans la
    vue 'factures traités' avec un mauvais statut.
    """
    WORKFLOW_TO_STATUT = {
        "En Attente":  "En attente",
        "Pending":     "En attente",
        "Approved":    "Validé",
        "Approuvé":    "Validé",
        "Validé":      "Validé",
        "Rejected":    "Rejeté",
        "Rejeté":      "Rejeté",
        "Cancelled":   "Rejeté",
        "Annulé":      "Rejeté",
    }
    DOCSTATUS_TO_STATUT = {
        0: "En attente",
        1: "Validé",
        2: "Rejeté",
    }

    workflow_state = doc.get("workflow_state") or ""
    new_statut = (
        WORKFLOW_TO_STATUT.get(workflow_state)
        or DOCSTATUS_TO_STATUT.get(doc.docstatus)
    )

    if not new_statut:
        return

    ocr_docs = frappe.get_all(
        "OCR Document",
        filters={"linked_docname": doc.name, "linked_doctype": "BOM"},
        fields=["name", "status"],
    )

    if not ocr_docs and getattr(doc, "item", None):
        ocr_docs = frappe.get_all(
            "OCR Document",
            filters=[["extracted_field", "like", f"%{doc.item}%"]],
            fields=["name", "status"],
            limit=5,
        )

    updated = 0
    for ocr in ocr_docs:
        if ocr.status != new_statut:
            frappe.db.set_value(
                "OCR Document", ocr.name, "status", new_statut,
                update_modified=False
            )
            updated += 1

    if updated:
        frappe.db.commit()
        frappe.logger().info(
            f"[OCR] sync BOM: {updated} doc(s) → '{new_statut}' "
            f"via workflow_state='{workflow_state}' / docstatus={doc.docstatus}"
        )        

# ══════════════════════════════════════════════════════════════════════
# SYNC : Payment Entry → OCR Document
# Appelée par hooks.py on_update / on_submit / on_cancel sur Payment Entry
# ══════════════════════════════════════════════════════════════════════

def sync_statut_depuis_payment_entry(doc, method=None):
    """
    Sync déclenchée par on_submit, on_cancel, ou on_update (workflow)
    sur Payment Entry. Lit docstatus ET workflow_state.
    """
    WORKFLOW_TO_STATUT = {
        "En Attente":  "En attente",
        "Pending":     "En attente",
        "Approved":    "Validé",
        "Approuvé":    "Validé",
        "Validé":      "Validé",
        "Rejected":    "Rejeté",
        "Rejeté":      "Rejeté",
        "Cancelled":   "Rejeté",
        "Annulé":      "Rejeté",
    }
    DOCSTATUS_TO_STATUT = {
        0: "En attente",
        1: "Validé",
        2: "Rejeté",
    }

    workflow_state = doc.get("workflow_state") or ""
    new_statut = (
        WORKFLOW_TO_STATUT.get(workflow_state)
        or DOCSTATUS_TO_STATUT.get(doc.docstatus)
    )

    if not new_statut:
        return

    ocr_docs = frappe.get_all(
        "OCR Document",
        filters={"linked_docname": doc.name, "linked_doctype": doc.doctype},
        fields=["name", "status"],
    )

    if not ocr_docs and getattr(doc, "reference_no", None):
        ocr_docs = frappe.get_all(
            "OCR Document",
            filters=[["extracted_field", "like", f"%{doc.reference_no}%"]],
            fields=["name", "status"],
            limit=5,
        )

    updated = 0
    for ocr in ocr_docs:
        if ocr.status != new_statut:
            frappe.db.set_value(
                "OCR Document", ocr.name, "status", new_statut,
                update_modified=False
            )
            updated += 1

    if updated:
        frappe.db.commit()
        frappe.logger().info(
            f"[OCR] sync Payment Entry: {updated} doc(s) → '{new_statut}' "
            f"via workflow_state='{workflow_state}' / docstatus={doc.docstatus}"
        )        