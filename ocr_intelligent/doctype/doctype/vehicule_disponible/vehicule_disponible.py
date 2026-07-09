# Copyright (c) 2026
import frappe
from frappe.model.document import Document


class VehiculeDisponible(Document):

    # ── CRUD virtuel ──────────────────────────────
    def db_insert(self, *args, **kwargs):
        pass

    def db_update(self, *args, **kwargs):
        pass

    def delete(self, ignore_permissions=False, force=False):
        pass

    def load_from_db(self):
        vehicule = frappe.db.get_value(
            "Vehicule",
            self.name,
            ["name", "immatriculation", "marque", "modele", "type_de_vehicule"],
            as_dict=True
        )
        if vehicule:
            self.update(vehicule)

    # ── GET DOC ───────────────────────────────────
    @staticmethod
    def get_doc(args):
        vehicule = frappe.db.get_value(
            "Vehicule",
            args.get("name"),
            ["name", "immatriculation", "marque", "modele", "type_de_vehicule"],
            as_dict=True
        )
        if not vehicule:
            frappe.throw("Véhicule introuvable")
        doc = frappe.new_doc("Vehicule Disponible")
        doc.update(vehicule)
        doc.name = vehicule.name
        return doc

    # ── LISTE ─────────────────────────────────────
    @staticmethod
    def get_list(args):
        debut = args.get("date_debut")
        fin = args.get("date_fin")
        exclure = args.get("exclure") or "new"
        limite = int(args.get("page_length") or 100)

        # Texte de recherche (pour le champ Link)
        txt = args.get("txt") or args.get("search_term") or ""

        tous = frappe.db.sql("""
            SELECT
                name,
                immatriculation,
                marque,
                modele,
                type_de_vehicule
            FROM `tabVehicule`
            WHERE statut NOT IN ('En maintenance', 'Hors service')
            AND (
                immatriculation LIKE %(txt)s
                OR marque LIKE %(txt)s
                OR modele LIKE %(txt)s
            )
            ORDER BY immatriculation ASC
            LIMIT %(limite)s
        """, {
            "txt": f"%{txt}%",
            "limite": limite
        }, as_dict=True)

        # Filtrer les conflits de réservation si dates fournies
        if debut and fin:
            bloques_rows = frappe.db.sql("""
                SELECT DISTINCT vehicule_assigne
                FROM `tabReservation Vehicule`
                WHERE statut_de_la_reservation NOT IN (
                    'Terminée', 'Refusée', 'Annulée', 'Brouillon'
                )
                AND name != %(exclure)s
                AND date_debut_reelle < %(fin)s
                AND date_fin_reelle > %(debut)s
                AND vehicule_assigne IS NOT NULL
                AND vehicule_assigne != ''
            """, {
                "debut": debut,
                "fin": fin,
                "exclure": exclure
            }, as_list=True)

            bloques = {r[0] for r in bloques_rows}
            tous = [v for v in tous if v["name"] not in bloques]

        # ⚠️ FORMAT CRITIQUE : Frappe search_widget attend des dicts avec "name"
        # On s'assure que chaque entrée a bien "name" = immatriculation
        resultat = []
        for v in tous:
            resultat.append(frappe._dict({
                "name": v.get("name") or v.get("immatriculation"),
                "immatriculation": v.get("immatriculation", ""),
                "marque": v.get("marque", ""),
                "modele": v.get("modele", ""),
                "type_de_vehicule": v.get("type_de_vehicule", "")
            }))

        return resultat

    # ── COUNT ──────────────────────────────────────
    @staticmethod
    def get_count(args):
        return len(VehiculeDisponible.get_list(args))