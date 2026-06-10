// ocr_bom_form.js - Groupe Bayoudh Metal
// Bouton OCR dans le formulaire Nomenclature (BOM) ERPNext
// Architecture identique à ocr_article_form.js

// ─────────────────────────────────────────────────────────────────────
// CONFIGURATION
// ─────────────────────────────────────────────────────────────────────
const OCR_BOM_CONFIG = {
    pipeline_endpoint:   "ocr_intelligent.api.ocr_bom_pipeline.pipeline_bom",
    statut_endpoint:     "ocr_intelligent.api.ocr_bom_pipeline.get_ocr_bom_statut",
    poll_interval_ms:    2500,
    poll_max_attempts:   80,       // 80 × 2.5s = 200s max
    score_warning_seuil: 60,

    // Libellés FR pour le résumé
    labels: {
        item:                        "Article (code)",
        item_name:                   "Nom de l'article",
        company:                     "Société",
        quantity:                    "Quantité produite",
        uom:                         "Unité de mesure",
        currency:                    "Devise",
        rm_cost_as_per:              "Prix basé sur",
        routing:                     "Route",
        transfer_material_against:   "Transfert matériel",
        conversion_rate:             "Taux de change",
        is_active:                   "Est Actif",
        is_default:                  "Est Défaut",
        scrap_percentage:            "Taux de perte (%)",
    },
};

// Définition des champs du formulaire de validation (header BOM)
const OCR_BOM_DIALOG_FIELDS = [
    {
        ocr: "item", frappe: "item", label: "Article (code)",
        type: "Link", options: "Item", sensitivity: 1,
        aliases: ["item_code", "article", "code_article"],
    },
    {
        ocr: "item_name", frappe: "item_name", label: "Nom de l'article",
        type: "Data", sensitivity: 2,
        aliases: ["nom_article", "designation"],
    },
    {
        ocr: "company", frappe: "company", label: "Société",
        type: "Link", options: "Company", sensitivity: 1,
        aliases: ["societe", "groupe", "company"],
    },
    {
        ocr: "quantity", frappe: "quantity", label: "Quantité produite",
        type: "Float", sensitivity: 1,
        aliases: ["quantite", "qty", "quantite_produite"],
    },
    {
        ocr: "uom", frappe: "uom", label: "Unité de mesure",
        type: "Link", options: "UOM", sensitivity: 1,
        aliases: ["udm", "unite", "unite_mesure"],
    },
    {
        ocr: "currency", frappe: "currency", label: "Devise",
        type: "Link", options: "Currency", sensitivity: 2,
        aliases: ["devise"],
    },
    {
        ocr: "rm_cost_as_per", frappe: "rm_cost_as_per", label: "Prix basé sur",
        type: "Select", options: "Valuation Rate\nLast Purchase Rate\nPrice List",
        sensitivity: 2,
        aliases: ["cout_base", "price_basis"],
    },
    {
        ocr: "routing", frappe: "routing", label: "Route",
        type: "Link", options: "Routing", sensitivity: 2,
        aliases: ["route", "gamme"],
    },
    {
        ocr: "transfer_material_against", frappe: "transfer_material_against",
        label: "Transfert matériel",
        type: "Select", options: "\nWork Order\nJob Card",
        sensitivity: 2,
        aliases: ["transfert_materiel", "transfer_material"],
    },
    {
        ocr: "conversion_rate", frappe: "conversion_rate", label: "Taux de change",
        type: "Float", sensitivity: 2,
        aliases: ["taux_change", "taux_conversion"],
    },
    {
        ocr: "scrap_percentage", frappe: "scrap_percentage", label: "Taux de perte (%)",
        type: "Percent", sensitivity: 2,
        aliases: ["taux_perte", "rebut", "scrap"],
    },
];

// ─────────────────────────────────────────────────────────────────────
// HOOK FRAPPE — formulaire BOM
// ─────────────────────────────────────────────────────────────────────
frappe.ui.form.on("BOM", {

    refresh(frm) {
        _ocr_bom_ajouter_bouton(frm);
    },
});

// ─────────────────────────────────────────────────────────────────────
// BOUTON PRINCIPAL
// ─────────────────────────────────────────────────────────────────────
function _ocr_bom_ajouter_bouton(frm) {
    frm.add_custom_button(
        __("📄 OCR Nomenclature"),
        () => _ocr_bom_ouvrir_dialog(frm),
        __("OCR")
    );
}

// ─────────────────────────────────────────────────────────────────────
// DIALOG UPLOAD
// ─────────────────────────────────────────────────────────────────────
function _ocr_bom_ouvrir_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title:  __("OCR — Nomenclature (BOM)"),
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
                        Nomenclature imprimée · BOM exportée en PDF · Scan d'une BOM<br>
                        <span style="color:#666;font-size:12px;">
                            Formats : PDF, PNG, JPG, TIFF, BMP, XLSX, SVG &nbsp;|&nbsp; Taille : 2 KB – 15 MB
                        </span>
                    </div>
                `,
            },
            {
                fieldtype:   "Attach",
                fieldname:   "fichier_bom",
                label:       __("Document Nomenclature à analyser"),
                reqd:        1,
                description: __("Glissez-déposez ou cliquez pour sélectionner"),
            },
            {
                fieldtype: "HTML",
                fieldname: "progression_html",
                options:   `<div id="ocr_bom_progress" style="display:none;margin-top:8px;"></div>`,
            },
        ],
        primary_action_label: __("🔍 Analyser"),
        primary_action(values) {
            if (!values.fichier_bom) {
                frappe.msgprint(__("Veuillez sélectionner un document Nomenclature."));
                return;
            }
            _ocr_bom_lancer_analyse(frm, dialog, values.fichier_bom);
        },
    });

    dialog.show();
}

// ─────────────────────────────────────────────────────────────────────
// LANCEMENT ANALYSE
// ─────────────────────────────────────────────────────────────────────
function _ocr_bom_lancer_analyse(frm, dialog, file_url) {
    _ocr_bom_set_progress(dialog, "info", "⏳ Envoi du document au moteur OCR…");
    dialog.get_primary_btn().prop("disabled", true).text(__("Analyse en cours…"));

    frappe.call({
        method:  OCR_BOM_CONFIG.pipeline_endpoint,
        args:    { file_url, source_doctype: "BOM" },
        callback(r) {
            if (!r.message || !r.message.success) {
                const err = (r.message && r.message.erreur) || __("Erreur inconnue.");
                _ocr_bom_set_progress(dialog, "danger",
                    `❌ Impossible de démarrer l'analyse : ${err}`);
                dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
                return;
            }
            _ocr_bom_set_progress(dialog, "info",
                "🔄 Analyse en cours (nomenclature)… veuillez patienter.");
            _ocr_bom_polling(frm, dialog, r.message.job_id, 0, file_url);
        },
        error() {
            _ocr_bom_set_progress(dialog, "danger",
                "❌ Erreur de communication avec le serveur.");
            dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
        },
    });
}

// ─────────────────────────────────────────────────────────────────────
// POLLING
// ─────────────────────────────────────────────────────────────────────
function _ocr_bom_polling(frm, dialog, job_id, tentative, source_file_url) {
    if (tentative >= OCR_BOM_CONFIG.poll_max_attempts) {
        _ocr_bom_set_progress(dialog, "warning",
            "⏰ Délai d'attente dépassé. Veuillez réessayer.");
        dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
        return;
    }

    setTimeout(() => {
        frappe.call({
            method:  OCR_BOM_CONFIG.statut_endpoint,
            args:    { job_id },
            callback(r) {
                const data = r.message || {};

                if (data.status === "en_cours") {
                    const dots = ".".repeat((tentative % 3) + 1);
                    _ocr_bom_set_progress(dialog, "info",
                        `🔄 Analyse en cours${dots} (${Math.round(tentative * OCR_BOM_CONFIG.poll_interval_ms / 1000)}s)`);
                    _ocr_bom_polling(frm, dialog, job_id, tentative + 1, source_file_url);
                    return;
                }

                if (data.status === "erreur") {
                    _ocr_bom_set_progress(dialog, "danger",
                        `❌ Erreur : ${data.erreur || "Erreur inconnue."}`);
                    dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
                    return;
                }

                if (data.status === "termine") {
                    const res = data.result || {};
                    if (source_file_url) res._source_file_url = source_file_url;
                    _ocr_bom_traiter_resultat(frm, dialog, res);
                    return;
                }

                _ocr_bom_polling(frm, dialog, job_id, tentative + 1, source_file_url);
            },
            error() {
                _ocr_bom_polling(frm, dialog, job_id, tentative + 1, source_file_url);
            },
        });
    }, OCR_BOM_CONFIG.poll_interval_ms);
}

// ─────────────────────────────────────────────────────────────────────
// TRAITEMENT DU RÉSULTAT
// ─────────────────────────────────────────────────────────────────────
function _ocr_bom_traiter_resultat(frm, dialog, result) {
    if (!result.success) {
        _ocr_bom_set_progress(dialog, "danger",
            `❌ ${result.erreur || "Analyse échouée."}`);
        dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
        return;
    }

    const champs = result.champs_remplis || {};
    const score  = result.score_confiance || 0;

    // ← Priorité : _source_file_url injecté par polling, puis file_url du backend
    const file_url_final = result._source_file_url || result.file_url || "";
    console.log("[OCR BOM] traiter_resultat - file_url_final:", file_url_final);
    console.log("[OCR BOM] traiter_resultat - result._source_file_url:", result._source_file_url);
    console.log("[OCR BOM] traiter_resultat - result.file_url:", result.file_url);
    
    // Garantir que la valeur est dans result avant de passer aux fonctions suivantes
    result._source_file_url = file_url_final;

    if (!Object.keys(champs).length && !(result.composants || []).length) {
        _ocr_bom_set_progress(dialog, "warning",
            "⚠️ Aucun champ nomenclature extrait. Vérifiez la qualité du document.");
        dialog.get_primary_btn().prop("disabled", false).text(__("🔍 Analyser"));
        return;
    }

    dialog.hide();
    _ocr_bom_dialog_validation(frm, champs, result.composants || [], score, result);
}

// ─────────────────────────────────────────────────────────────────────
// DIALOG VALIDATION
// ─────────────────────────────────────────────────────────────────────
function _ocr_bom_dialog_validation(frm, champs, composants, score, result) {
    champs     = (champs && typeof champs === "object") ? champs : {};
    composants = Array.isArray(composants) ? composants : [];
    const confiances = (result && result.confiances) || {};

    const score_color = score >= 80 ? "#28a745" : score >= 60 ? "#fd7e14" : "#dc3545";
    const score_icon  = score >= 80 ? "✅" : score >= 60 ? "⚠️" : "❌";

    // ── Tableau composants HTML ──────────────────────────────────────
    let composants_html = "";
    if (composants.length) {
        const lignes = composants.map((c, i) => {
            const warn = c.item_exists === false
                ? `<span style="color:#dc3545;" title="Article non trouvé dans ERPNext">⚠</span> `
                : "";
            const code = frappe.utils.escape_html(c.item_code || "");
            const name = frappe.utils.escape_html(c.item_name || "");
            const uom  = frappe.utils.escape_html(c.uom || "");
            return `
                <tr data-comp-index="${i}">
                    <td style="padding:4px 6px;text-align:center;">${i + 1}</td>
                    <td style="padding:4px 6px;white-space:nowrap;">${warn}
                        <input class="input-with-feedback form-control input-xs ocr-bom-code"
                               data-original="${code}"
                               value="${code}"
                               style="min-width:110px;" />
                    </td>
                    <td style="padding:4px 6px;">
                        <input class="input-with-feedback form-control input-xs ocr-bom-name"
                               data-original="${name}"
                               value="${name}"
                               style="min-width:180px;" />
                    </td>
                    <td style="padding:4px 6px;text-align:right;">
                        <input class="input-with-feedback form-control input-xs ocr-bom-qty"
                               data-original="${c.qty || ""}"
                               value="${c.qty || ""}"
                               style="min-width:80px;text-align:right;" />
                    </td>
                    <td style="padding:4px 6px;">
                        <input class="input-with-feedback form-control input-xs ocr-bom-uom"
                               data-original="${uom}"
                               value="${uom}"
                               style="min-width:75px;" />
                    </td>
                    <td style="padding:4px 6px;text-align:right;">
                        <input class="input-with-feedback form-control input-xs ocr-bom-rate"
                               data-original="${c.rate || ""}"
                               value="${c.rate || ""}"
                               style="min-width:90px;text-align:right;" />
                    </td>
                </tr>`;
        }).join("");
        composants_html = `
            <div style="margin-top:12px;">
                <b style="font-size:13px;color:#2c5f8a;">Composants détectés (${composants.length})</b>
                <div style="overflow-x:auto;margin-top:6px;">
                    <table style="width:100%;border-collapse:collapse;font-size:12px;">
                        <thead>
                            <tr style="background:#1b4f72;color:#fff;">
                                <th style="padding:5px 8px;">#</th>
                                <th style="padding:5px 8px;">Code</th>
                                <th style="padding:5px 8px;">Nom</th>
                                <th style="padding:5px 8px;">Qté</th>
                                <th style="padding:5px 8px;">UdM</th>
                                <th style="padding:5px 8px;">Prix</th>
                            </tr>
                        </thead>
                        <tbody>${lignes}</tbody>
                    </table>
                </div>
                <p style="font-size:11px;color:#666;margin-top:4px;">
                    ✏️ Ce tableau est modifiable : vous pouvez corriger les codes/articles avant l'application.<br>
                    ⚠ Articles marqués en rouge n'existent pas encore dans ERPNext.
                </p>
            </div>`;
    }

    const summary_html = `
        <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:6px;
                    padding:10px 14px;margin-bottom:10px;font-size:13px;color:#495057;">
            ${score_icon} Score OCR :
            <b style="color:${score_color};">${score}%</b>
            &nbsp;|&nbsp; Type :
            <b>${frappe.utils.escape_html(result.type_document || "nomenclature")}</b>
            &nbsp;|&nbsp; ${Object.keys(champs).length} champ(s) header
            &nbsp;|&nbsp; ${composants.length} composant(s)
            ${score < OCR_BOM_CONFIG.score_warning_seuil
                ? `<br><span style="color:#856404;">⚠ Score faible — vérifiez les champs avant validation.</span>`
                : ""}
        </div>
        ${composants_html}
        <hr style="margin:12px 0;">
        <b style="font-size:13px;color:#2c5f8a;">Champs généraux</b>`;

    const fields = [{ fieldtype: "HTML", fieldname: "ocr_resume", options: summary_html }];

    for (const def of OCR_BOM_DIALOG_FIELDS) {
        let val = "";
        for (const key of [def.frappe, def.ocr, ...(def.aliases || [])].filter(Boolean)) {
            const candidate = champs[key];
            if (candidate !== undefined && candidate !== null && String(candidate).trim() !== "") {
                val = candidate;
                break;
            }
        }

        const field = {
            fieldtype : def.type,
            fieldname : def.frappe,
            label     : def.label,
            default   : (val !== "" && val !== null && val !== undefined) ? val : undefined,
        };
        if (def.options) field.options = def.options;

        const conf = confiances[def.ocr];
        if (conf !== undefined && conf < 0.55) {
            field.description = __("⚠ Confiance faible — vérifiez cette valeur");
        } else if (!val && def.sensitivity === 1) {
            field.description = __("⛔ Champ obligatoire — non détecté, saisie manuelle requise");
        } else if (val && def.sensitivity === 1) {
            field.description = __("✓ Extrait avec bonne confiance");
        }

        fields.push(field);
    }

    const d = new frappe.ui.Dialog({
        title                 : __("Nomenclature OCR — Validation"),
        fields                : fields,
        size                  : "large",
        primary_action_label  : __("Appliquer et Enregistrer"),
        secondary_action_label: __("Appliquer sans enregistrer"),
        secondary_action() {
            const vals = d.get_values();
            if (!vals) return;
            const composants_edites = _ocr_bom_collecter_composants_depuis_dialog(d, composants);
            d.hide();
            _ocr_bom_appliquer(frm, vals, composants_edites, false, result);
        },
        primary_action(vals) {
            if (!vals) return;
            const composants_edites = _ocr_bom_collecter_composants_depuis_dialog(d, composants);
            d.hide();
            _ocr_bom_appliquer(frm, vals, composants_edites, true, result);
        },
    });

    d.show();
}

function _ocr_bom_parse_nombre_saisi(value) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    const normalized = raw.replace(/\s/g, "").replace(",", ".");
    const n = parseFloat(normalized);
    return Number.isFinite(n) ? n : "";
}

function _ocr_bom_collecter_composants_depuis_dialog(dialog, fallbackComposants) {
    const fallback = Array.isArray(fallbackComposants) ? fallbackComposants : [];
    const wrapper = dialog && dialog.fields_dict && dialog.fields_dict.ocr_resume
        ? dialog.fields_dict.ocr_resume.$wrapper
        : null;

    if (!wrapper || !wrapper.length) return fallback;

    const rows = wrapper.find("tbody tr[data-comp-index]");
    if (!rows.length) return fallback;

    const composants = [];
    rows.each((_, tr) => {
        const row = $(tr);
        const idx = parseInt(row.attr("data-comp-index"), 10);
        const src = Number.isInteger(idx) && fallback[idx] ? fallback[idx] : {};

        const item_code = String(row.find(".ocr-bom-code").val() || "").trim();
        const item_name = String(row.find(".ocr-bom-name").val() || "").trim();
        const uom       = String(row.find(".ocr-bom-uom").val() || "").trim();
        const qty       = _ocr_bom_parse_nombre_saisi(row.find(".ocr-bom-qty").val());
        const rate      = _ocr_bom_parse_nombre_saisi(row.find(".ocr-bom-rate").val());

        const original_code = String(src.item_code || "").trim();
        const code_changed = item_code !== original_code;

        composants.push({
            ...src,
            item_code,
            item_name,
            uom,
            qty,
            rate,
            // Si l'utilisateur corrige le code, on laisse passer même si l'OCR l'avait marqué inexistant.
            item_exists: code_changed ? undefined : src.item_exists,
        });
    });

    return composants;
}

// ─────────────────────────────────────────────────────────────────────
// APPLICATION AU FORMULAIRE
// ─────────────────────────────────────────────────────────────────────
function _ocr_bom_appliquer(frm, vals, composants, enregistrer, result) {
    vals       = (vals && typeof vals === "object") ? vals : {};
    composants = Array.isArray(composants) ? composants : [];
    const source_file_url = (result && result._source_file_url) || "";
    
    console.log("[OCR BOM] source_file_url:", source_file_url);
    console.log("[OCR BOM] result._source_file_url:", result && result._source_file_url);
    console.log("[OCR BOM] result.file_url:", result && result.file_url);
    console.log("[OCR BOM] frm.doc.name:", frm.doc.name);

    const champs_remplis = [];
    const champs_ignores = [];

    // ── Champs header ────────────────────────────────────────────────
    for (const def of OCR_BOM_DIALOG_FIELDS) {
        const field = def.frappe;
        const val   = vals[field];

        if (val === null || val === undefined || String(val).trim() === "") continue;

        if (!frm.fields_dict[field]) {
            champs_ignores.push(field);
            continue;
        }

        frm.set_value(field, val);
        champs_remplis.push(OCR_BOM_CONFIG.labels[field] || field);
    }

    // ── Composants (child table) ─────────────────────────────────────
    const composants_ok      = composants.filter(c => c.item_exists !== false && c.item_code);
    const composants_ignores = composants.filter(c => c.item_exists === false || !c.item_code);

    if (composants_ok.length) {
        console.log(`[OCR BOM] Ajout de ${composants_ok.length} composants`);

        const existing_items   = Array.isArray(frm.doc.items) ? frm.doc.items : [];
        const has_valid_existing = existing_items.some(r => r && r.item_code && r.uom);
        if (!has_valid_existing) {
            console.log(`[OCR BOM] Nettoyage table items (lignes vides)`);
            frm.clear_table("items");
        }

        composants_ok.forEach((comp, idx) => {
            try {
                console.log(`[OCR BOM] Ajout composant ${idx + 1}:`, comp.item_code);
                const row = frappe.model.add_child(frm.doc, "BOM Item", "items");

                if (comp.item_code)              row.item_code         = String(comp.item_code);
                if (comp.item_name)              row.item_name         = String(comp.item_name);
                if (comp.description || comp.item_name) row.description = String(comp.description || comp.item_name);
                if (comp.qty)                    row.qty               = parseFloat(comp.qty) || 1;
                row.uom               = comp.uom        ? String(comp.uom)        : "Nos";
                row.qty_per_unit      = comp.qty_per_unit ? parseFloat(comp.qty_per_unit) : (parseFloat(comp.qty) || 1);
                row.stock_uom         = comp.stock_uom  ? String(comp.stock_uom)  : String(comp.uom || "Nos");
                row.conversion_factor = comp.conversion_factor ? parseFloat(comp.conversion_factor) : 1;
                if (comp.rate)                   row.rate              = parseFloat(comp.rate);

                console.log(`[OCR BOM] Composant ${idx + 1} ajouté avec succès`);
            } catch (err) {
                console.error(`[OCR BOM] Erreur ajout composant ${idx + 1}:`, err);
            }
        });

        frm.refresh_field("items");
        champs_remplis.push(`${composants_ok.length} composant(s)`);
        console.log(`[OCR BOM] refresh_field(items) terminé`);
    }

    frm.refresh();

    // ── Notification résumé ──────────────────────────────────────────
    if (champs_remplis.length) {
        const ignored_info = champs_ignores.length
            ? `<br><small style="color:#888;">Ignorés : ${champs_ignores.join(", ")}</small>`
            : "";
        frappe.show_alert({
            message: `✅ <b>Nomenclature OCR</b> — ${champs_remplis.length} champ(s) appliqué(s) : ${champs_remplis.join(", ")}${ignored_info}`,
            indicator: "green",
        }, 6);
    } else {
        frappe.show_alert({
            message: __("⚠️ Aucun champ OCR appliqué au formulaire."),
            indicator: "orange",
        }, 4);
    }

    // ── Enregistrement ───────────────────────────────────────────────
    if (enregistrer) {
        if (composants.length && !composants_ok.length) {
            frappe.msgprint({
                title: __("Enregistrement bloqué"),
                message: __(
                    "Aucun composant OCR n'est enregistrable ({0} détecté(s)): les codes article détectés n'existent pas dans ERPNext. "
                    + "Créez/corrigez les articles puis relancez l'OCR, ou ajoutez les lignes manuellement."
                ).replace("{0}", String(composants_ignores.length)),
                indicator: "orange",
            });
            return;
        }

        const invalid_rows = (frm.doc.items || []).filter(r => {
            if (!r) return false;
            return !r.item_code || !r.uom || !r.qty;
        });
        if (invalid_rows.length) {
            frappe.msgprint({
                title: __("Champs manquants dans Matières premières"),
                message: __(
                    "Impossible d'enregistrer tant que certaines lignes de la table Articles sont incomplètes "
                    + "(Code article, UdM, Qté)."
                ),
                indicator: "orange",
            });
            return;
        }

        frappe.after_ajax(() => {
            console.log(`[OCR BOM] Sauvegarde BOM avec source_file_url:`, source_file_url);

            frm.save()
                .then(() => {
                    frappe.show_alert({ message: __("✅ Nomenclature enregistrée."), indicator: "green" }, 3);

                    const _doctype = frm.doctype;
                    const _docname = frm.doc.name;
                    const _furl    = result._source_file_url || result.file_url || source_file_url || "";

                    console.log(`[OCR BOM] Post-save: ${_doctype}/${_docname}, file=${_furl}`);

                    if (_furl && _docname && !_docname.startsWith("new-")) {
                        frappe.call({
                            method: "ocr_intelligent.api.auto_create_document.attacher_copie_originale",
                            args: { doctype: _doctype, docname: _docname, file_url: _furl },
                            freeze: false,
                            callback(r) {
                                const res = r && r.message;
                                if (res && res.success) {
                                    frappe.show_alert({ message: __("📎 Fichier original attaché"), indicator: "green" }, 3);
                                    console.log(`[OCR BOM] Fichier attaché avec succès:`, res);
                                } else {
                                    console.warn(`[OCR BOM] Échec attachement:`, res);
                                }
                            },
                            error(err) {
                                console.error(`[OCR BOM] Erreur attachement:`, err);
                            },
                        });
                    } else {
                        console.warn(`[OCR BOM] Attachement ignoré: furl=${_furl}, docname=${_docname}`);
                    }
                })
                .catch(err => {
                    console.error(`[OCR BOM] Save échoué:`, err);
                    frappe.msgprint({
                        title: __("Enregistrement incomplet"),
                        message: __("Le BOM a été rempli mais l'enregistrement a échoué — vérifiez les champs obligatoires (ex: Prix des composants)."),
                        indicator: "orange",
                    });
                });
        });
    }
}



// ─────────────────────────────────────────────────────────────────────
// UTILITAIRES UI
// ─────────────────────────────────────────────────────────────────────
function _ocr_bom_set_progress(dialog, type, message) {
    const el = dialog.$wrapper.find("#ocr_bom_progress");
    if (!el.length) return;

    const colors = {
        info:    { bg: "#e8f4fd", border: "#b3d4f5", text: "#1a5276" },
        danger:  { bg: "#fdf3f3", border: "#f5c6cb", text: "#721c24" },
        warning: { bg: "#fff8e1", border: "#ffe082", text: "#856404" },
        success: { bg: "#e8f8f0", border: "#a3d9b1", text: "#155724" },
    };
    const c = colors[type] || colors.info;

    el.show().html(`
        <div style="
            background:${c.bg};
            border:1px solid ${c.border};
            border-radius:5px;
            padding:10px 14px;
            font-size:12px;
            color:${c.text};
        ">${message}</div>
    `);
}

// ─────────────────────────────────────────────────────────────────────
// ATTACHEMENT DU FICHIER ORIGINAL
// ─────────────────────────────────────────────────────────────────────
function _ocr_bom_attacher_fichier(doctype, docname, file_url) {
    console.log(`[OCR BOM] Tentative d'attachement: ${file_url} → ${doctype}/${docname}`);
    
    if (!file_url || !doctype || !docname) {
        console.warn(`[OCR BOM] Paramètres manquants pour attachement:`, {file_url, doctype, docname});
        return;
    }

    frappe.call({
        method: "ocr_intelligent.api.ocr_bom_pipeline.attacher_fichier_a_document",
        args: {
            doctype: doctype,
            docname: docname,
            file_url: file_url
        },
        callback(r) {
            console.log(`[OCR BOM] Réponse attachement:`, r.message);
            if (r.message && r.message.success) {
                frappe.show_alert({
                    message: __("📎 Fichier original attaché"),
                    indicator: "green"
                }, 3);
            } else if (r.message && r.message.erreur) {
                console.error(`[OCR BOM] Échec attachement: ${r.message.erreur}`);
            }
        },
        error(err) {
            console.error(`[OCR BOM] Erreur lors de l'attachement du fichier:`, err);
        },
    });
}
