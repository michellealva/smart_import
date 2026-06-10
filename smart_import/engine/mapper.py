"""Guess which doctype each sheet belongs to and map columns to fields.

Produces a "spec" (the full machine-readable mapping) and a "plan"
(the friendly summary shown to the user).
"""

import re
from difflib import SequenceMatcher

import frappe

SKIP_FIELDTYPES = {
    "Section Break",
    "Column Break",
    "Tab Break",
    "HTML",
    "Button",
    "Image",
    "Fold",
    "Heading",
    "Table",
    "Table MultiSelect",
    "Attach",
    "Attach Image",
    "Signature",
    "Geolocation",
    "Barcode",
}

DEFAULT_CANDIDATES = [
    "CRM Organization",
    "CRM Lead",
    "CRM Deal",
    "Contact",
    "Address",
    "Lead",
    "Customer",
    "Supplier",
    "Item",
]

# Common header words mapped to likely fieldname fragments, to help fuzzy matching
SYNONYMS = {
    "company": "organization",
    "companyname": "organization",
    "phonenumber": "phone",
    "mobilenumber": "mobileno",
    "emailaddress": "email",
}


def normalize(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def candidate_doctypes():
    names = []
    for dt in (frappe.get_hooks("smart_import_doctypes") or []) + DEFAULT_CANDIDATES:
        if dt not in names:
            names.append(dt)

    out = []
    for dt in names:
        if not frappe.db.exists("DocType", dt):
            continue
        meta = frappe.get_meta(dt)
        if meta.istable or meta.issingle:
            continue
        out.append(dt)
    return out


def importable_fields(doctype):
    meta = frappe.get_meta(doctype)
    return [df for df in meta.fields if df.fieldtype not in SKIP_FIELDTYPES]


def build_field_index(doctype):
    index = {}
    for df in importable_fields(doctype):
        index[normalize(df.label)] = df
        index[normalize(df.fieldname)] = df
    return index


def match_columns(headers, doctype):
    """Return {header: docfield or None}."""
    index = build_field_index(doctype)
    mapping = {}
    used = set()

    for h in headers:
        nh = normalize(h)
        nh = SYNONYMS.get(nh, nh)
        df = index.get(nh)

        if df is None:
            best, best_score = None, 0.0
            for key, candidate in index.items():
                score = similarity(nh, key)
                if score > best_score:
                    best, best_score = candidate, score
            if best_score >= 0.85:
                df = best

        if df and df.fieldname not in used:
            mapping[h] = df
            used.add(df.fieldname)
        else:
            mapping[h] = None
    return mapping


def score_doctype(headers, doctype):
    if not headers:
        return 0.0
    mapping = match_columns(headers, doctype)
    matched = len([h for h in headers if mapping[h]])
    return matched / len(headers)


def build_entity(entity_id, sheet, doctype):
    entity = {
        "id": entity_id,
        "sheet": sheet["name"],
        "doctype": doctype or "",
        "rows": len(sheet["rows"]),
        "columns": [],
        "unmapped": [],
    }
    if not doctype:
        entity["unmapped"] = list(sheet["headers"])
        return entity

    mapping = match_columns(sheet["headers"], doctype)
    for h in sheet["headers"]:
        df = mapping[h]
        if df:
            col = {
                "column": h,
                "field": df.fieldname,
                "label": df.label or df.fieldname,
                "fieldtype": df.fieldtype,
            }
            if df.fieldtype == "Link":
                col["link_doctype"] = df.options
            if df.fieldtype == "Select":
                col["select_options"] = [
                    o for o in (df.options or "").split("\n") if o.strip()
                ]
            entity["columns"].append(col)
        else:
            entity["unmapped"].append(h)
    return entity


def order_entities(entities):
    """Sheets that others link to get imported first."""
    by_doctype = {}
    for e in entities:
        if e["doctype"] and e["doctype"] not in by_doctype:
            by_doctype[e["doctype"]] = e

    ordered = []
    placed = set()

    def place(entity):
        if entity["id"] in placed:
            return
        placed.add(entity["id"])
        for col in entity.get("columns", []):
            target = col.get("link_doctype")
            dep = by_doctype.get(target)
            if dep and dep["id"] != entity["id"]:
                place(dep)
        ordered.append(entity)

    for e in entities:
        place(e)
    return ordered


def build_spec(data, overrides=None):
    """overrides: {entity_id: doctype or ""} chosen by the user in the Review step."""
    overrides = overrides or {}
    candidates = candidate_doctypes()

    entities = []
    for i, sheet in enumerate(data["sheets"]):
        entity_id = "e{}".format(i)
        if entity_id in overrides:
            chosen = overrides[entity_id]
        else:
            best, best_score = "", 0.0
            for dt in candidates:
                s = score_doctype(sheet["headers"], dt)
                if s > best_score:
                    best, best_score = dt, s
            chosen = best if best_score >= 0.3 else ""
        entities.append(build_entity(entity_id, sheet, chosen))

    entities = order_entities(entities)
    spec = {"version": "1", "entities": entities, "overrides": overrides}
    plan = build_plan(spec, candidates)
    return spec, plan


def build_plan(spec, candidates=None):
    candidates = candidates or candidate_doctypes()
    available = [{"label": dt, "value": dt} for dt in candidates]

    entities = []
    for e in spec["entities"]:
        entities.append(
            {
                "id": e["id"],
                "sheet": e["sheet"],
                "doctype": e["doctype"],
                "rows": e["rows"],
                "mapped": len(e["columns"]),
                "unmapped": e["unmapped"],
                "links": sorted(
                    {
                        c["link_doctype"]
                        for c in e["columns"]
                        if c.get("link_doctype")
                    }
                ),
            }
        )
    return {
        "entities": entities,
        "available_doctypes": available,
        "order": [e["id"] for e in spec["entities"] if e["doctype"]],
    }
