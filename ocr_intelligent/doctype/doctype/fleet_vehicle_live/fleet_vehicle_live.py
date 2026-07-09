# -*- coding: utf-8 -*-
# Copyright (c) 2026, Logistique

import frappe
from frappe.model.document import Document


class FleetVehicleLive(Document):
    """Position GPS live d'un véhicule de la flotte."""

    def validate(self):
        if self.vehicule and not self.immatriculation:
            self.immatriculation = frappe.db.get_value("Vehicule", self.vehicule, "immatriculation") or self.vehicule

        if self.latitude is not None and not (-90 <= float(self.latitude) <= 90):
            frappe.throw("Latitude invalide (doit être entre -90 et 90)")
        if self.longitude is not None and not (-180 <= float(self.longitude) <= 180):
            frappe.throw("Longitude invalide (doit être entre -180 et 180)")

        if self.niveau_batterie is not None:
            self.niveau_batterie = max(0, min(100, int(self.niveau_batterie)))

        if self.signal_gsm is not None:
            self.signal_gsm = max(0, int(self.signal_gsm))
