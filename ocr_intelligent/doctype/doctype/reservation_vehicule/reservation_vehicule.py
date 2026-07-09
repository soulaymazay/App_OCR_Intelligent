# Copyright (c) 2026, Ramzi haj massoud and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReservationVehicule(Document):
    

    def on_submit(self):
        if self.vehicule_assigne:
            frappe.db.set_value(
                "Vehicule",
                self.vehicule_assigne,
                "statut",
                "En mission"
            )
            frappe.db.commit()

    def on_cancel(self):
        if self.vehicule_assigne:
            frappe.db.set_value(
                "Vehicule",
                self.vehicule_assigne,
                "statut",
                "Disponible"
            )
            frappe.db.commit()
    