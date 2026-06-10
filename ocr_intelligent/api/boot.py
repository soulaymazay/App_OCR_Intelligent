import frappe

_CACHE_KEY = "ocr_intelligent:party_account_types"
_CACHE_TTL = 3600  # 1 heure

_DEFAULT_PARTY_TYPES = {
    "Customer": "Receivable",
    "Supplier": "Payable",
    "Employee": "Payable",
    "Shareholder": "Payable",
}

def _get_party_types():
    rows = frappe.get_all("Party Type", fields=["name", "account_type"])
    return frappe._dict((r["name"], r["account_type"]) for r in rows)

def _ensure_party_types_exist():
    existing = {r["name"] for r in frappe.get_all("Party Type", fields=["name"])}
    created = False
    for party_type, account_type in _DEFAULT_PARTY_TYPES.items():
        if party_type not in existing:
            frappe.get_doc({
                "doctype": "Party Type",
                "party_type": party_type,
                "account_type": account_type,
            }).insert(ignore_permissions=True)
            created = True
    if created:
        frappe.db.commit()

def ensure_party_types_boot(bootinfo):
    if frappe.session.user == "Guest":
        return

    # ── Lecture cache Redis ──
    cached = frappe.cache().get_value(_CACHE_KEY)
    if cached:
        bootinfo.party_account_types = frappe._dict(cached)
        return

    try:
        if not frappe.db.count("Party Type"):
            _ensure_party_types_exist()
        party_types = _get_party_types()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "OCR Party Type Boot")
        party_types = frappe._dict(_DEFAULT_PARTY_TYPES)

    if not party_types:
        party_types = frappe._dict(_DEFAULT_PARTY_TYPES)

    # ── Mise en cache Redis 1h ──
    frappe.cache().set_value(_CACHE_KEY, dict(party_types), expires_in_sec=_CACHE_TTL)
    bootinfo.party_account_types = party_types