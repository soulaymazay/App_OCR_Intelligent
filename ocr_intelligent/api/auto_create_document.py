
import frappe
import os
import json
import time
import hashlib

EXTENSIONS_ACCEPTEES = frozenset([".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"])
 #Détection PDF texte vs scanné
def _is_pdf_textuel(path):
    try:
        import fitz
        doc = fitz.open(path)
        text = doc[0].get_text().strip()
        return len(text) > 50
    except:
        return False
        
    #Hook déclencheur
def auto_create_ocr_document(doc, method):
    ext = os.path.splitext(doc.file_name or "")[1].lower()
    if ext not in EXTENSIONS_ACCEPTEES:
        return

    if frappe.db.exists("OCR Document", {"file_url": doc.file_url}):
        return
    # Résolution de chemin
    chemin = _get_chemin_fichier(doc)
    if not chemin:
        return

    ocr_doc = frappe.get_doc({
        "doctype": "OCR Document",
        "document_name": doc.file_name,
        "file_url": doc.file_url,
        "uploaded_by": frappe.session.user,
        "status": "En attente",
    })
    ocr_doc.insert(ignore_permissions=True)

    frappe.enqueue(
        "ocr_intelligent.api.auto_create_document.traiter_ocr_en_arriere_plan",
        queue="short",
        timeout=25,
        ocr_doc_name=ocr_doc.name,
        chemin=chemin,
    )
# Le worker
def traiter_ocr_en_arriere_plan(ocr_doc_name, chemin):
    try:
        frappe.db.set_value("OCR Document", ocr_doc_name, "status", "En cours")
        _t_start = time.time()

        
        if chemin.endswith(".pdf") and _is_pdf_textuel(chemin):
            import fitz
            doc = fitz.open(chemin)
            texte = "\n".join([p.get_text() for p in doc])
            res_ocr = {
                "texte": texte,
                "score_confiance": 95,
                "moteur": "pdf_text"
            }
        else:
            from ocr_intelligent.ocr.ocr_engine import get_engine
            engine = get_engine()
            res_ocr = engine.extraire_texte(chemin)

        # Vérification timeout manuel
        if time.time() - _t_start > 25:
            frappe.logger().warning(f"[OCR] Timeout 25s dépassé : {chemin}")
            frappe.db.set_value("OCR Document", ocr_doc_name, "status", "Rejeté")
            return

        frappe.db.set_value("OCR Document", ocr_doc_name,
            "confidence_score", res_ocr["score_confiance"])
        frappe.db.set_value("OCR Document", ocr_doc_name,
            "extracted_text", res_ocr["texte"])
        frappe.db.set_value("OCR Document", ocr_doc_name,
            "status", "Validé")

    except Exception:
        frappe.db.set_value("OCR Document", ocr_doc_name, "status", "Rejeté")
        frappe.logger().error(f"[OCR] Erreur pipeline : {frappe.get_traceback()}")

def _get_chemin_fichier(doc):
    """Retourne le chemin absolu d'un fichier uploadé."""
    site_path = frappe.get_site_path()
    if doc.file_url:
        nom = doc.file_url.replace("/private/files/", "").replace("/files/", "")
        for c in [
            os.path.join(site_path, "private", "files", nom),
            os.path.join(site_path, "public",  "files", nom),
        ]:
            if os.path.exists(c):
                return c
    return None

def enregistrer_document_module_dans_ocr(doc, method):
    """
    Hook appelé après l'insertion de documents (Payment Entry, Purchase Invoice, Item, etc.)
    
    NOTE: L'attachement du fichier OCR source est géré directement dans les fonctions de création
    (create_purchase_invoice_from_log, create_payment_entry_from_invoice) ou côté client JS
    (ocr_article_form.js, ocr_bom_form.js).
    
    Cette fonction existe pour éviter les erreurs AttributeError et pourrait être utilisée
    à l'avenir pour tracker les documents créés manuellement vs OCR.
    """
    pass

@frappe.whitelist()
def attacher_copie_originale(doctype, docname, file_url):
    """API
    Attache un fichier existant à un document ERPNext.
    Fonction générique utilisée par tous les modules OCR (Article, BOM, Payment Entry, etc.)
    """ 
    try:
        frappe.logger().info(f"[OCR] attacher_copie_originale: {doctype}/{docname} ← {file_url}")
        
        if not doctype or not docname or not file_url:
            return {"success": False, "erreur": "Paramètres manquants"}
        
        # Vérifier que le document existe
        if not frappe.db.exists(doctype, docname):
            return {"success": False, "erreur": f"Document {doctype}/{docname} introuvable"}
        
        # Chercher le document File correspondant à l'URL
        file_docs = frappe.get_all(
            "File",
            filters={"file_url": file_url},
            fields=["name", "attached_to_doctype", "attached_to_name", "file_name"],
            limit=1
        )

        
        if not file_docs:
            nom_fichier = os.path.basename(file_url)
            frappe.logger().warning(f"[OCR] file_url non trouvé, recherche par file_name: {nom_fichier}")
            file_docs = frappe.get_all(
                "File",
                filters={"file_name": nom_fichier},
                fields=["name", "attached_to_doctype", "attached_to_name", "file_name", "file_url"],
                order_by="creation desc",
                limit=1
            )
        
        if not file_docs:
            frappe.logger().error(f"[OCR] Fichier introuvable dans tabFile: {file_url}")
            return {"success": False, "erreur": f"Fichier {file_url} introuvable dans tabFile"}
        
        file_doc = file_docs[0]
        
        # Si déjà attaché au bon document, ne rien faire
        if file_doc.get("attached_to_doctype") == doctype and file_doc.get("attached_to_name") == docname:
            return {"success": True, "message": "Fichier déjà attaché"}
        
        # Attacher le fichier au document en utilisant SQL direct (évite les problèmes avec set_value dict)
        frappe.db.sql("""
            UPDATE `tabFile` 
            SET attached_to_doctype = %s, attached_to_name = %s 
            WHERE name = %s
        """, (doctype, docname, file_doc["name"]))
        frappe.db.commit()
        
        frappe.logger().info(f"[OCR] Fichier {file_doc['name']} attaché à {doctype}/{docname}")
        return {"success": True, "message": "Fichier attaché avec succès"}
        
    except Exception as e:
        frappe.logger().error(f"[OCR] Erreur lors de l'attachement du fichier: {str(e)}")
        return {"success": False, "erreur": str(e)}
    