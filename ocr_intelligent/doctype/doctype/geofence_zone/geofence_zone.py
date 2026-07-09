# -*- coding: utf-8 -*-
# Copyright (c) 2026, Logistique

import json

import frappe
from frappe.model.document import Document


class GeofenceZone(Document):
    """Zone géographique de geofencing."""

    def validate(self):
        if self.type_zone == "Cercle":
            if self.latitude_centre is None or self.longitude_centre is None:
                frappe.throw("Une zone circulaire nécessite un centre (latitude/longitude)")
            if not self.rayon_metres or float(self.rayon_metres) <= 0:
                self.rayon_metres = 500
            self._validate_gps_point(self.latitude_centre, self.longitude_centre)
            return

        if self.type_zone in ("Polygone", "Rectangle"):
            if not self.coordonnees_polygone:
                frappe.throw("Une zone polygone/rectangle nécessite des coordonnées JSON")
            try:
                coords = json.loads(self.coordonnees_polygone)
            except (ValueError, TypeError):
                frappe.throw("Coordonnées polygone : JSON invalide. Format attendu : [[lat1, lon1], [lat2, lon2], ...]")
            if not isinstance(coords, list) or len(coords) < 3:
                frappe.throw("Le polygone doit contenir au moins 3 points")
            for point in coords:
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    frappe.throw("Chaque point doit être [latitude, longitude]")
                self._validate_gps_point(point[0], point[1])

    def _validate_gps_point(self, lat, lon):
        try:
            lat = float(lat)
            lon = float(lon)
        except Exception:
            frappe.throw(f"Point GPS invalide : [{lat}, {lon}]")
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            frappe.throw(f"Point GPS hors limites : [{lat}, {lon}]")
