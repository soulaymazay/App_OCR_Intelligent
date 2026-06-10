// ocr_document.js
// Interface visuelle dédiée :
//   • Vue Liste  : indicateur couleur par statut + badge score OCR + fond coloré par ligne
//   • Vue Formulaire : bandeau statut + panneau côte-à-côte (document original ‖ champs extraits)
//   • Boutons d'action : Valider / Rejeter / Ouvrir document lié

// ═══════════════════════════════════════════════════════════════════════════════
// VUE LISTE : couleurs par statut
// ═══════════════════════════════════════════════════════════════════════════════
frappe.listview_settings["OCR Document"] = {
    add_fields: ["status", "confidence_score", "linked_doctype", "uploaded_by"],

    /** Petit point coloré affiché à gauche de chaque ligne */
    get_indicator(doc) {
        const MAP = {
            "En attente":         ["gray",   "En attente"],
            "En cours":           ["blue",   "En cours d'analyse"],
            "Validation requise": ["orange", "Validation requise"],
            "Validé":             ["green",  "Validé"],
            "Rejeté":             ["red",    "Rejeté"],
        };
        return MAP[doc.status] || ["gray", doc.status];
    },

    /** Formateurs de colonnes */
    formatters: {
        status(value) {
            if (!value) return "";
            const COLORS = {
                "En attente":         "#6c757d",
                "En cours":           "#0d6efd",
                "Validation requise": "#fd7e14",
                "Validé":             "#28a745",
                "Rejeté":             "#dc3545",
            };
            const c = COLORS[value] || "#6c757d";
            return `<span style="
                display:inline-block;padding:2px 11px;border-radius:20px;
                background:${c};color:#fff;font-size:11px;font-weight:700;
                white-space:nowrap;letter-spacing:.2px
            ">${value}</span>`;
        },

        confidence_score(value) {
            if (value == null || value === "") return "—";
            const pct = Math.round(value);
            const c = pct >= 80 ? "#28a745" : pct >= 60 ? "#fd7e14" : "#dc3545";
            return `<span style="color:${c};font-weight:700">${pct} %</span>`;
        },
    },

    /** Injecte un CSS de fond coloré sur les lignes selon l'indicateur */
    onload() {
        if (!document.getElementById("ocr-listview-style")) {
            const s = document.createElement("style");
            s.id = "ocr-listview-style";
            s.textContent = `
                .list-row-container:has(.indicator-pill.green)  { background: rgba(40,167,69,.06) !important; }
                .list-row-container:has(.indicator-pill.red)    { background: rgba(220,53,69,.07) !important; }
                .list-row-container:has(.indicator-pill.orange) { background: rgba(253,126,20,.07) !important; }
                .list-row-container:has(.indicator-pill.blue)   { background: rgba(13,110,253,.05) !important; }
                .list-row-container:has(.indicator-pill.gray)   { background: rgba(108,117,125,.04) !important; }
            `;
            document.head.appendChild(s);
        }
    },
};

// ═══════════════════════════════════════════════════════════════════════════════
// VUE FORMULAIRE : panneau côte-à-côte
// ═══════════════════════════════════════════════════════════════════════════════
frappe.ui.form.on("OCR Document", {
    refresh(frm) {
        _ocr_render_split_view(frm);
        _ocr_add_action_buttons(frm);
    },
    status(frm) {
        _ocr_render_split_view(frm);
    },
});

// ─── Rendu principal ──────────────────────────────────────────────────────────
function _ocr_render_split_view(frm) {
    // Nettoyer le rendu précédent
    $(frm.layout.wrapper).find(".ocr-split-view").remove();

    const file_url  = frm.doc.file_url || "";
    const ex_text   = frm.doc.extracted_text || "";
    const ex_fields = _ocr_parse_json(frm.doc.extracted_field);
    const score     = frm.doc.confidence_score;
    const status    = frm.doc.status || "En attente";

    const STATUS_COLORS = {
        "En attente":         { bg: "#6c757d", light: "rgba(108,117,125,.09)" },
        "En cours":           { bg: "#0d6efd", light: "rgba(13,110,253,.07)"  },
        "Validation requise": { bg: "#fd7e14", light: "rgba(253,126,20,.09)"  },
        "Validé":             { bg: "#28a745", light: "rgba(40,167,69,.08)"   },
        "Rejeté":             { bg: "#dc3545", light: "rgba(220,53,69,.08)"   },
    };
    const sc      = STATUS_COLORS[status] || STATUS_COLORS["En attente"];
    const score_c = score >= 80 ? "#28a745" : score >= 60 ? "#fd7e14" : "#dc3545";

    // ── Prévisualisation du document ──────────────────────────────
    let preview_html;
    if (file_url) {
        const ext = (file_url.split("?")[0].split(".").pop() || "").toLowerCase();
        if (["jpg","jpeg","png","gif","webp","bmp","tiff","tif"].includes(ext)) {
            preview_html = `<img src="${file_url}"
                style="max-width:100%;height:auto;border-radius:6px;
                       box-shadow:0 2px 12px rgba(0,0,0,.14);">`;
        } else if (ext === "pdf") {
            preview_html = `<iframe src="${file_url}"
                style="width:100%;height:580px;border:none;border-radius:6px;"></iframe>`;
        } else {
            preview_html = `
                <a href="${file_url}" target="_blank"
                   style="display:inline-block;margin-top:50px;padding:10px 20px;
                          background:#0d6efd;color:#fff;border-radius:6px;text-decoration:none;
                          font-weight:600">
                    📄 Ouvrir le fichier
                </a>`;
        }
    } else {
        preview_html = `
            <div style="padding:60px 20px;text-align:center;color:#adb5bd;font-size:14px">
                <div style="font-size:48px;margin-bottom:12px">📭</div>
                Aucun fichier joint
            </div>`;
    }

    // ── Tableau des champs extraits ───────────────────────────────
    const SKIP = new Set(["raw","texte_brut","texte","erreurs","errors","warnings","valid","method","message"]);
    let rows_html = "";
    for (const [k, v] of Object.entries(ex_fields)) {
        if (SKIP.has(k)) continue;
        const val = (v === null || v === undefined)
            ? ""
            : (typeof v === "object" ? JSON.stringify(v) : String(v));
        if (!val) continue;
        rows_html += `
            <tr>
                <td style="font-weight:600;white-space:nowrap;padding:6px 10px;
                           color:#495057;font-size:12px;background:#f8f9fa;
                           border-bottom:1px solid #e9ecef;width:40%">
                    ${_ocr_label(k)}
                </td>
                <td style="padding:6px 10px;word-break:break-word;font-size:13px;
                           border-bottom:1px solid #e9ecef">
                    ${_ocr_escape(val)}
                </td>
            </tr>`;
    }
    const fields_section = rows_html
        ? `<table style="width:100%;border-collapse:collapse;border:1px solid #e9ecef;border-radius:6px;overflow:hidden">
               ${rows_html}
           </table>`
        : `<div style="padding:30px;text-align:center;color:#adb5bd;font-size:13px">
               Aucun champ extrait
           </div>`;

    // ── Texte OCR brut (accordéon) ────────────────────────────────
    const text_section = ex_text ? `
        <details style="margin-top:14px;border:1px solid #dee2e6;border-radius:6px;overflow:hidden">
            <summary style="cursor:pointer;font-weight:700;color:#495057;font-size:11px;
                            padding:8px 12px;background:#f8f9fa;text-transform:uppercase;
                            letter-spacing:.5px;user-select:none">
                📝 Texte OCR brut
            </summary>
            <pre style="font-size:11px;max-height:200px;overflow:auto;background:#fff;
                        padding:12px;margin:0;color:#555;line-height:1.5">
${_ocr_escape(ex_text.substring(0, 4000))}${ex_text.length > 4000 ? "\n…" : ""}</pre>
        </details>` : "";

    // ── Document ERP lié ─────────────────────────────────────────
    let linked_section = "";
    if (frm.doc.linked_doctype && frm.doc.linked_docname) {
        const href = `/app/${frappe.router.slug(frm.doc.linked_doctype)}/${encodeURIComponent(frm.doc.linked_docname)}`;
        linked_section = `
            <div style="margin-top:14px;padding:10px 14px;background:#e7f5ff;
                        border-radius:6px;border-left:4px solid #0d6efd;font-size:12px">
                <span style="color:#6c757d">Document ERP lié : </span>
                <a href="${href}" style="font-weight:700;color:#0d6efd">
                    ${_ocr_escape(frm.doc.linked_doctype)} — ${_ocr_escape(frm.doc.linked_docname)}
                </a>
            </div>`;
    }

    // ── Métadonnées ───────────────────────────────────────────────
    const meta_parts = [];
    if (frm.doc.uploaded_by) meta_parts.push(`👤 ${frm.doc.uploaded_by}`);
    if (frm.doc.modified)    meta_parts.push(`📅 ${frappe.datetime.str_to_user(frm.doc.modified)}`);
    const meta_html = meta_parts.length
        ? `<div style="margin-top:12px;font-size:11px;color:#6c757d;border-top:1px solid #f0f0f0;padding-top:10px">
               ${meta_parts.join("&ensp;·&ensp;")}
           </div>`
        : "";

    // ── Assemblage HTML ───────────────────────────────────────────
    const html = `
    <div class="ocr-split-view"
         style="margin:0 0 20px;border-radius:8px;overflow:hidden;
                box-shadow:0 2px 8px rgba(0,0,0,.10);border:1px solid #dee2e6">

        <!-- Bandeau d'en-tête coloré selon statut -->
        <div style="display:flex;align-items:center;gap:10px;padding:11px 16px;
                    background:${sc.light};border-bottom:2px solid ${sc.bg}">
            <span style="font-size:22px">🗂</span>
            <span style="font-weight:700;font-size:14px;flex:1;overflow:hidden;
                         text-overflow:ellipsis;white-space:nowrap">
                ${_ocr_escape(frm.doc.document_name || "—")}
            </span>
            <span style="background:${sc.bg};color:#fff;padding:3px 13px;border-radius:20px;
                         font-size:11px;font-weight:700;white-space:nowrap">
                ${_ocr_escape(status)}
            </span>
            ${score ? `
            <span style="background:${score_c};color:#fff;padding:3px 11px;border-radius:20px;
                         font-size:11px;font-weight:700;white-space:nowrap">
                OCR ${Math.round(score)} %
            </span>` : ""}
        </div>

        <!-- Corps : deux colonnes -->
        <div style="display:grid;grid-template-columns:1fr 1fr;min-height:320px">

            <!-- Colonne gauche : document original -->
            <div style="padding:16px;border-right:1px solid #e9ecef;background:#fafafa;
                        overflow:auto;max-height:660px;
                        display:flex;flex-direction:column;align-items:center">
                <div style="font-weight:700;font-size:10px;text-transform:uppercase;
                            letter-spacing:.6px;color:#6c757d;margin-bottom:12px;
                            align-self:flex-start">
                    Document original
                </div>
                ${preview_html}
            </div>

            <!-- Colonne droite : champs extraits -->
            <div style="padding:16px;background:#fff;overflow:auto;max-height:660px">
                <div style="font-weight:700;font-size:10px;text-transform:uppercase;
                            letter-spacing:.6px;color:#6c757d;margin-bottom:12px">
                    Champs extraits
                </div>
                ${fields_section}
                ${text_section}
                ${linked_section}
                ${meta_html}
            </div>
        </div>
    </div>`;

    // Injerer avant la première section du formulaire
    const $layout = $(frm.layout.wrapper);
    const $first  = $layout.find(".form-section").first();
    if ($first.length) {
        $first.before(html);
    } else {
        $layout.prepend(html);
    }
}

// ─── Boutons d'action ─────────────────────────────────────────────────────────
function _ocr_add_action_buttons(frm) {
    if (["Validation requise", "En attente", "En cours"].includes(frm.doc.status)) {
        frm.add_custom_button(__("✅ Valider"), () => {
            frappe.confirm(__("Confirmer la validation de ce document ?"), () => {
                frm.set_value("status", "Validé");
                frm.save();
            });
        }, __("Actions OCR"));

        frm.add_custom_button(__("❌ Rejeter"), () => {
            frappe.confirm(__("Confirmer le rejet de ce document ?"), () => {
                frm.set_value("status", "Rejeté");
                frm.save();
            });
        }, __("Actions OCR"));
    }

    if (frm.doc.linked_doctype && frm.doc.linked_docname) {
        frm.add_custom_button(__("🔗 Ouvrir le document lié"), () => {
            frappe.set_route("Form", frm.doc.linked_doctype, frm.doc.linked_docname);
        });
    }
}

// ─── Utilitaires ──────────────────────────────────────────────────────────────
function _ocr_parse_json(s) {
    if (!s) return {};
    try { return JSON.parse(s); } catch (e) { return {}; }
}

function _ocr_escape(s) {
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function _ocr_label(key) {
    const M = {
        numero_facture:   "N° Facture",
        fournisseur:      "Fournisseur",
        date:             "Date",
        date_echeance:    "Date d'échéance",
        montant_ht:       "Montant HT",
        montant_tva:      "TVA",
        montant_ttc:      "Montant TTC",
        numero_bl:        "N° Bon de Livraison",
        date_livraison:   "Date Livraison",
        numero_cheque:    "N° Chèque",
        banque:           "Banque",
        montant:          "Montant",
        beneficiaire:     "Bénéficiaire",
        numero_traite:    "N° Traite",
        tireur:           "Tireur",
        tire:             "Tiré",
        domiciliation:    "Domiciliation",
        date_emission:    "Date d'émission",
        rib:              "RIB / IBAN",
        titulaire_compte: "Titulaire du Compte",
        bill_no:          "N° Facture Fournisseur",
        bill_date:        "Date Facture",
        supplier:         "Fournisseur",
        net_total:        "Montant HT",
        grand_total:      "Total TTC",
        reference_no:     "N° Référence",
        reference_date:   "Date Référence",
        paid_amount:      "Montant payé",
        party:            "Partie prenante",
        bank:             "Banque",
        document_type:    "Type de document",
        type_document:    "Type de document",
        confidence:       "Score de confiance",
        score:            "Score",
        numero_commande:  "N° Commande",
        date_commande:    "Date Commande",
        item_name:        "Nom Article",
        item_code:        "Code Article",
        valuation_rate:   "Prix Unitaire",
        barcode:          "Code-barres",
    };
    return M[key] || key.replace(/_/g, " ");
}
