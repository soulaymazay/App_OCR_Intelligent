# -*- coding: utf-8 -*-
# Copyright (c) 2026, Logistique

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class TrackingAlert(Document):
    """Alerte de tracking."""

    def validate(self):
        if not self.heure_alerte:
            self.heure_alerte = now_datetime()

        if self.est_resolue and not self.resolue_le:
            self.resolue_le = now_datetime()
            self.resolue_par = frappe.session.user

        if self.latitude is not None and not (-90 <= float(self.latitude) <= 90):
            frappe.throw("Latitude alerte invalide")
        if self.longitude is not None and not (-180 <= float(self.longitude) <= 180):
            frappe.throw("Longitude alerte invalide")
