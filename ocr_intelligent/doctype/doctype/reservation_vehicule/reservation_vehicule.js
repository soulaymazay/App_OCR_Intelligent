// =============================================
// Client Script - Reservation Vehicule
// =============================================

frappe.ui.form.on('Reservation Vehicule', {
    refresh: function(frm) {
        const est_responsable = frappe.user.has_role('Responsable logistique') || frappe.user.has_role('System Manager');

        // Cacher la section Assignation pour les Demandeurs
        if (!est_responsable) {
            frm.set_df_property('assignation_section', 'hidden', true);
        } else {
            // Bouton "Suggérer Véhicule" (IA) - visible seulement pour le Responsable logistique
            // Affiche la popup de recommandations ; en cliquant sur "Choisir ce véhicule"
            // sur une carte, le champ "Véhicule assigné" est rempli directement.
            frm.add_custom_button('🤖 Suggérer Véhicule', function() {
                ouvrir_suggestion_vehicule(frm);
            }, __('Assignation'));
        }

        // Indicateur de statut avec couleur
        if (frm.doc.statut_de_la_reservation) {
            const couleurs = {
                "En attente": "orange",
                "Assignée": "blue",
                "En mission": "green",
                "Terminée": "darkgreen",
                "Refusée": "red"
            };
            const couleur = couleurs[frm.doc.statut_de_la_reservation] || "orange";
            frm.page.set_indicator(frm.doc.statut_de_la_reservation, couleur);
        }
    },

    // Calcul automatique de la date de fin quand on change début ou durée
    date_et_heure_de_debut_souhaitee: function(frm) {
        calculer_date_fin(frm);
    },

    la_duree: function(frm) {
        calculer_date_fin(frm);
    }
});


// =============================================
// Suggestion IA de véhicule (popup) - depuis le formulaire
// =============================================

function ouvrir_suggestion_vehicule(frm) {
    // Vérifications minimales avant d'appeler l'IA
    if (!frm.doc.date_et_heure_de_debut_souhaitee) {
        frappe.msgprint({
            title: __('Information manquante'),
            message: __('Veuillez renseigner la "Date et Heure de début souhaitée" avant de demander une suggestion.'),
            indicator: 'orange'
        });
        return;
    }
    if (!frm.doc.la_duree) {
        frappe.msgprint({
            title: __('Information manquante'),
            message: __('Veuillez renseigner "La durée" avant de demander une suggestion.'),
            indicator: 'orange'
        });
        return;
    }

    // date_fin_reelle est calculée automatiquement (calculer_date_fin), sinon fallback sur date_fin_reelle existante
    const date_debut = frm.doc.date_et_heure_de_debut_souhaitee;
    const date_fin = frm.doc.date_fin_reelle || frm.doc.date_et_heure_de_debut_souhaitee;

    frappe.show_alert({ message: __('Analyse IA en cours...'), indicator: 'blue' });

    frappe.call({
        method: 'logistique.ai.api.suggestions.suggest_vehicle',
        args: {
            date_debut: date_debut,
            date_fin: date_fin,
            type_reservation: frm.doc.type_de_vehicule_souhaite || null,
            priorite: frm.doc.priorite || null
        },
        callback: function(r) {
            if (r.message && r.message.status === 'ok') {
                afficher_popup_suggestions(frm, r.message);
            } else {
                frappe.msgprint({
                    title: __('Suggestion IA'),
                    message: (r.message && r.message.message) ? r.message.message : __('Aucune suggestion disponible'),
                    indicator: 'orange'
                });
            }
        }
    });
}

function afficher_popup_suggestions(frm, data) {
    var suggestions = data.suggestions || [];

    if (!suggestions.length) {
        frappe.msgprint(data.message || __('Aucune suggestion disponible'));
        return;
    }

    var html = `
        <style>
            .sugg-summary{margin-bottom:12px;color:#666;font-size:13px;}
            .sugg-list{display:flex;flex-direction:column;gap:12px;max-height:60vh;overflow-y:auto;}
            .sugg-card{border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;}
            .sugg-card.sugg-best{border:2px solid #f1c40f;}
            .sugg-top{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;color:#fff;}
            .sugg-info{display:flex;flex-direction:column;gap:2px;}
            .sugg-crown{margin-right:4px;}
            .sugg-rank{margin-right:6px;opacity:.8;}
            .sugg-score-box{text-align:right;}
            .sugg-score{font-size:20px;font-weight:bold;line-height:1;}
            .sugg-lvl{font-size:12px;}
            .sugg-body{padding:10px 14px;}
            .sugg-bar{height:6px;background:#eee;border-radius:4px;margin-bottom:10px;overflow:hidden;}
            .sugg-fill{height:100%;border-radius:4px;}
            .sugg-reason{font-size:12px;color:#333;margin-bottom:3px;}
            .sugg-warnings{margin-top:6px;}
            .sugg-warning{font-size:12px;color:#c0392b;margin-bottom:3px;}
            .sugg-btns{margin-top:10px;display:flex;gap:8px;}
        </style>
        <div class="sugg-summary">${data.message || ''}</div>
    `;
    html += '<div class="sugg-list">';

    suggestions.forEach(function(s, idx) {
        var isBest = data.best && s.immatriculation === data.best;
        var badgeColors = {
            success: '#27ae60',
            info: '#3498db',
            primary: '#2980b9',
            warning: '#f39c12',
            danger: '#e74c3c'
        };
        var badgeColor = badgeColors[s.css_class] || '#95a5a6';

        html += `
            <div class="sugg-card${isBest ? ' sugg-best' : ''}">
                <div class="sugg-top" style="background:${badgeColor};">
                    <div class="sugg-info">
                        ${isBest ? '<span class="sugg-crown">👑</span>' : `<span class="sugg-rank">#${idx + 1}</span>`}
                        <strong>${s.immatriculation}</strong>
                        <span>${s.marque || ''} ${s.modele || ''}</span>
                    </div>
                    <div class="sugg-score-box">
                        <div class="sugg-score">${s.score}</div>
                        <div class="sugg-lvl">${s.label}</div>
                    </div>
                </div>
                <div class="sugg-body">
                    <div class="sugg-bar"><div class="sugg-fill" style="width:${s.score}%;background:${badgeColor};"></div></div>
                    <div class="sugg-reasons">
                        ${(s.reasons || []).map(r => `<div class="sugg-reason">${r}</div>`).join('')}
                    </div>
                    ${(s.warnings && s.warnings.length) ? `
                    <div class="sugg-warnings">
                        ${s.warnings.map(w => `<div class="sugg-warning">⚠️ ${w}</div>`).join('')}
                    </div>` : ''}
                    <div class="sugg-btns">
                        <button class="btn btn-xs btn-default sugg-open-vehicle" data-vehicle="${s.vehicle}">
                            Ouvrir véhicule
                        </button>
                        <button class="btn btn-xs btn-primary sugg-choose-vehicle"
                            data-vehicle="${s.vehicle}" data-immat="${s.immatriculation}">
                            ✓ Choisir ce véhicule
                        </button>
                    </div>
                </div>
            </div>
        `;
    });

    html += '</div>';

    var d = new frappe.ui.Dialog({
        title: __('🤖 Véhicules Recommandés'),
        size: 'large',
        fields: [
            { fieldname: 'sugg_html', fieldtype: 'HTML' }
        ]
    });
    d.fields_dict.sugg_html.$wrapper.html(html);

    // Ouvrir la fiche du véhicule (sans fermer la popup ni assigner)
    d.$wrapper.find('.sugg-open-vehicle').on('click', function() {
        var vehicle = $(this).data('vehicle');
        frappe.set_route('Form', 'Vehicule', vehicle);
    });

    // "Choisir ce véhicule" : remplit directement le champ "Véhicule assigné"
    // avec le véhicule choisi dans la popup, puis ferme la popup.
    d.$wrapper.find('.sugg-choose-vehicle').on('click', function() {
        var vehicle = $(this).data('vehicle');
        var immat = $(this).data('immat');

        frm.set_value('vehicule_assigne', vehicle).then(function() {
            frm.refresh_field('vehicule_assigne');
            d.hide();
            frappe.show_alert({
                message: __('Véhicule {0} assigné avec succès.', [immat]),
                indicator: 'green'
            });
        });
    });

    d.show();
}


// =============================================
// List View Settings (Demandeur ne voit que ses réservations)
// =============================================

frappe.listview_settings['Reservation Vehicule'] = {
    onload: function(listview) {
        const user = frappe.session.user;

        if (frappe.user.has_role('Demandeur Véhicule') && !frappe.user.has_role('Responsable logistique')) {
            
            listview.filter_area.clear();
            listview.filter_area.add([
                ["Reservation Vehicule", "demandeur", "=", user]
            ]);

            // Empêcher la suppression du filtre
            listview.filter_area.clear = function() {
                frappe.show_alert({
                    message: __("Vous ne pouvez voir que vos propres réservations."),
                    indicator: 'orange'
                });
                setTimeout(() => {
                    listview.filter_area.add([
                        ["Reservation Vehicule", "demandeur", "=", user]
                    ]);
                }, 150);
            };
        }
    }
};