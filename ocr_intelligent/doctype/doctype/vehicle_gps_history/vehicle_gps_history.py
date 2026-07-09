# -*- coding: utf-8 -*-
# Copyright (c) 2026, Logistique

import frappe
from frappe.model.document import Document


class VehicleGPSHistory(Document):
    """Point d'historique GPS d'un véhicule."""

    def validate(self):
        if self.latitude is not None and not (-90 <= float(self.latitude) <= 90):
            frappe.throw("Latitude invalide")
        if self.longitude is not None and not (-180 <= float(self.longitude) <= 180):
            frappe.throw("Longitude invalide")
