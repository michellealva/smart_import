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


def doctype_from_sheet_name(name):
    """If a sheet is named after an importable doctype, return it.

    Matches the exact doctype name first (our templates name tabs after the
    doctype), then a normalized fallback so minor punctuation/case differs ok.
    """
    name = (name or "").strip()
    if not name:
        return None

    def _ok(dt):
        meta = frappe.get_meta(dt)
        return not meta.istable and not meta.issingle

    if frappe.db.exists("DocType", name) and _ok(name):
        return name

    target = normalize(name)
    for row in frappe.get_all("DocType", filters={"istable": 0, "issingle": 0}, pluck="name"):
        if normalize(row) == target:
            return row
    return None


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
    return [
        df
        for df in meta.fields
        if df.fieldtype not in SKIP_FIELDTYPES and not getattr(df, "is_virtual", 0)
    ]


# column that links a child (line-item) row to its parent row
REF_COLUMN = "Ref"


def child_tables(doctype):
    """Single-level child tables of a doctype (Table fields; Table MultiSelect
    is intentionally excluded for now)."""
    out = []
    for df in frappe.get_meta(doctype).fields:
        if df.fieldtype == "Table" and df.options:
            out.append(
                {
                    "table_fieldname": df.fieldname,
                    "child_doctype": df.options,
                    "label": df.label or df.fieldname,
                }
            )
    return out


def all_importable_doctypes():
    """Every doctype a user could import into — app-agnostic.

    Excludes child tables, single doctypes, and ones the user can't create.
    """
    rows = frappe.get_all(
        "DocType",
        filters={"istable": 0, "issingle": 0},
        fields=["name"],
        order_by="name asc",
    )
    out = []
    for r in rows:
        if frappe.has_permission(r.name, "create"):
            out.append(r.name)
    return out


INTERNAL_FIELDS = {
    "naming_series",
    "amended_from",
    "lft",
    "rgt",
    "old_parent",
}

VERBOSE_FIELDTYPES = {
    "Text Editor",
    "Code",
    "HTML Editor",
    "Markdown Editor",
    "JSON",
    "Long Text",
    "Text",
}


def field_options(doctype):
    """Importable fields of a doctype, for the field-picker dropdowns.

    `suggested` marks the "useful" everyday columns we tick by default in the
    simple view: required fields, plus ordinary editable fields, minus
    read-only / hidden / internal / long-text ones.
    """
    out = []
    for df in importable_fields(doctype):
        reqd = bool(df.reqd)
        suggested = reqd or (
            not getattr(df, "hidden", 0)
            and not getattr(df, "read_only", 0)
            and df.fieldname not in INTERNAL_FIELDS
            and df.fieldtype not in VERBOSE_FIELDTYPES
        )
        opt = {
            "fieldname": df.fieldname,
            "label": df.label or df.fieldname,
            "fieldtype": df.fieldtype,
            "reqd": reqd,
            "suggested": suggested,
        }
        if df.fieldtype == "Link":
            opt["link_doctype"] = df.options
        if df.fieldtype == "Select":
            opt["select_options"] = [o for o in (df.options or "").split("\n") if o.strip()]
        out.append(opt)
    return out


def field_options_full(doctype):
    """Parent fields plus each child table's fields, for the column picker."""
    return {
        "parent": field_options(doctype),
        "children": [
            {
                "table_fieldname": ct["table_fieldname"],
                "label": ct["label"],
                "child_doctype": ct["child_doctype"],
                "fields": field_options(ct["child_doctype"]),
            }
            for ct in child_tables(doctype)
        ],
    }


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


def _column_detail(h, df, table_fieldname=None, child_doctype=None):
    """Build the full per-column descriptor for a header mapped to docfield df.

    When `table_fieldname` is given the column targets a child-table field (a
    line-item column in a flattened sheet) rather than a parent field.
    """
    col = {
        "column": h,
        "field": df.fieldname,
        "label": df.label or df.fieldname,
        "fieldtype": df.fieldtype,
        "target": "child" if table_fieldname else "parent",
    }
    if table_fieldname:
        col["table_fieldname"] = table_fieldname
        col["child_doctype"] = child_doctype
    if df.fieldtype == "Link":
        col["link_doctype"] = df.options
    if df.fieldtype == "Select":
        col["select_options"] = [
            o for o in (df.options or "").split("\n") if o.strip()
        ]
    return col


def _cell_for(col):
    """The per-column entry shown in the mapping editor."""
    return {
        "column": col["column"],
        "field": col["field"],
        "target": col.get("target", "parent"),
        "table_fieldname": col.get("table_fieldname"),
    }


def child_field_targets(doctype):
    """{table_fieldname: {child_doctype, label, by_name: {fieldname: docfield}}}.

    The importable fields of each child table, so a flattened sheet can map a
    column straight onto a line-item field.
    """
    out = {}
    for ct in child_tables(doctype):
        out[ct["table_fieldname"]] = {
            "child_doctype": ct["child_doctype"],
            "label": ct["label"],
            "by_name": {df.fieldname: df for df in importable_fields(ct["child_doctype"])},
        }
    return out


def build_child_field_index(doctype):
    """{normalized label/fieldname: (table_fieldname, child_doctype, docfield)}."""
    index = {}
    for tf, info in child_field_targets(doctype).items():
        for fn, df in info["by_name"].items():
            index.setdefault(normalize(df.label), (tf, info["child_doctype"], df))
            index.setdefault(normalize(fn), (tf, info["child_doctype"], df))
    return index


def match_prefixed_child(doctype, header):
    """Recognize a "Table: Field" header (the convention our templates emit for
    line-item columns) and map it straight to that child field.

    e.g. "Products: Product Code" -> the `products` table's `product_code` field.
    Deterministic (label/fieldname match, no fuzz), so it takes precedence over
    the auto guesses and never collides with a parent field.
    Returns (table_fieldname, child_doctype, docfield) or None.
    """
    if ":" not in header:
        return None
    prefix, rest = header.split(":", 1)
    tkey, fkey = normalize(prefix), normalize(rest)
    if not tkey or not fkey:
        return None
    for tf, info in child_field_targets(doctype).items():
        if normalize(info["label"]) != tkey and normalize(tf) != tkey:
            continue
        for fn, df in info["by_name"].items():
            if normalize(df.label) == fkey or normalize(fn) == fkey:
                return (tf, info["child_doctype"], df)
    return None


def match_child_columns(headers, doctype, skip):
    """Match still-unmapped headers onto child-table fields.

    Parent fields win first (callers pass already-matched headers in `skip`);
    this only fills the gaps, so ordinary parent imports are unaffected.
    Returns {header: (table_fieldname, child_doctype, docfield)}.
    """
    index = build_child_field_index(doctype)
    out = {}
    used = set()
    for h in headers:
        if h in skip:
            continue
        nh = normalize(h)
        nh = SYNONYMS.get(nh, nh)
        hit = index.get(nh)
        if hit is None:
            best, best_score = None, 0.0
            for key, cand in index.items():
                score = similarity(nh, key)
                if score > best_score:
                    best, best_score = cand, score
            if best_score >= 0.85:
                hit = best
        if hit and (hit[0], hit[2].fieldname) not in used:
            out[h] = hit
            used.add((hit[0], hit[2].fieldname))
    return out


def build_entity(entity_id, sheet, doctype, column_overrides=None):
    """column_overrides: {column_name: fieldname or ""} chosen by the user.

    An empty string forces "don't import this column"; a bare fieldname forces a
    parent-field mapping; a dotted "table_fieldname.fieldname" forces a
    child-table (line-item) mapping; a column not present falls back to the auto
    guess (parent first, then child tables).
    """
    column_overrides = column_overrides or {}
    entity = {
        "id": entity_id,
        "sheet": sheet["name"],
        "doctype": doctype or "",
        "rows": len(sheet["rows"]),
        "columns": [],
        "unmapped": [],
        # full per-column view for the mapping editor (every header, in order)
        "cells": [],
    }
    if not doctype:
        entity["unmapped"] = list(sheet["headers"])
        entity["cells"] = [
            {"column": h, "field": "", "target": "", "table_fieldname": None}
            for h in sheet["headers"]
        ]
        return entity

    auto = match_columns(sheet["headers"], doctype)
    fields_by_name = {df.fieldname: df for df in importable_fields(doctype)}
    child_targets = child_field_targets(doctype)
    auto_child = match_child_columns(
        sheet["headers"], doctype, {h for h, df in auto.items() if df}
    )

    for h in sheet["headers"]:
        col = None
        if h in column_overrides:
            chosen = column_overrides[h]
            if chosen and "." in chosen:
                tf, fn = chosen.split(".", 1)
                info = child_targets.get(tf)
                df = info["by_name"].get(fn) if info else None
                if df:
                    col = _column_detail(h, df, tf, info["child_doctype"])
            elif chosen:
                df = fields_by_name.get(chosen)
                if df:
                    col = _column_detail(h, df)
        else:
            pc = match_prefixed_child(doctype, h)
            if pc:
                tf, cd, df = pc
                col = _column_detail(h, df, tf, cd)
            elif auto.get(h):
                col = _column_detail(h, auto[h])
            elif h in auto_child:
                tf, cd, df = auto_child[h]
                col = _column_detail(h, df, tf, cd)

        if col:
            entity["columns"].append(col)
            entity["cells"].append(_cell_for(col))
        else:
            entity["unmapped"].append(h)
            entity["cells"].append(
                {"column": h, "field": "", "target": "", "table_fieldname": None}
            )
    return entity


def guess_group_key(doctype, entity, sheet):
    """Best column to group flattened rows into one parent record.

    Prefers the column mapped to the parent's naming/title field; else a parent
    column whose values repeat (so blocks of rows share a parent); else the
    first parent column.
    """
    parent_cols = [c for c in entity["columns"] if c.get("target") != "child"]
    if not parent_cols:
        return ""
    headers_by_field = {c["field"]: c["column"] for c in parent_cols}

    meta = frappe.get_meta(doctype)
    autoname = meta.autoname or ""
    if autoname.startswith("field:"):
        fn = autoname.split(":", 1)[1]
        if fn in headers_by_field:
            return headers_by_field[fn]
    if meta.title_field and meta.title_field in headers_by_field:
        return headers_by_field[meta.title_field]

    idx = {h: i for i, h in enumerate(sheet["headers"])}
    best, best_repeat = "", 1.0
    for c in parent_cols:
        i = idx.get(c["column"])
        if i is None:
            continue
        vals = [
            str(r[i]).strip().lower()
            for r in sheet["rows"]
            if i < len(r) and str(r[i]).strip()
        ]
        distinct = len(set(vals))
        if not distinct:
            continue
        repeat = len(vals) / distinct
        if repeat > best_repeat:
            best, best_repeat = c["column"], repeat
    return best or parent_cols[0]["column"]


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


def build_spec(data, overrides=None, column_overrides=None, group_keys=None):
    """overrides: {entity_id: doctype or ""} chosen in the Review step.
    column_overrides: {entity_id: {column: fieldname or ""}} from the field picker.
    group_keys: {entity_id: column} chosen for flattened child-table grouping.
    """
    overrides = overrides or {}
    column_overrides = column_overrides or {}
    group_keys = group_keys or {}
    candidates = candidate_doctypes()
    sheets = data["sheets"]

    # 1. guess the (parent) doctype for each sheet
    chosen = []
    for i, sheet in enumerate(sheets):
        entity_id = "e{}".format(i)
        if entity_id in overrides:
            chosen.append(overrides[entity_id])
            continue
        dt = doctype_from_sheet_name(sheet["name"])
        if not dt:
            best, best_score = "", 0.0
            for cd in candidates:
                s = score_doctype(sheet["headers"], cd)
                if s > best_score:
                    best, best_score = cd, s
            dt = best if best_score >= 0.3 else ""
        chosen.append(dt)

    # 2. identify child sheets: a still-unmapped sheet named after a child
    #    doctype of one of the parents above is that parent's line-item tab
    child_link = {}  # sheet index -> (parent_index, table_fieldname, child_doctype)
    table_map = {}  # child_doctype (normalized) -> [(parent_index, table_fieldname, child_doctype)]
    for i, dt in enumerate(chosen):
        if not dt:
            continue
        for ct in child_tables(dt):
            table_map.setdefault(normalize(ct["child_doctype"]), []).append(
                (i, ct["table_fieldname"], ct["child_doctype"])
            )
    for i, sheet in enumerate(sheets):
        if chosen[i] or ("e{}".format(i) in overrides):
            continue
        matches = table_map.get(normalize(sheet["name"]))
        if matches:
            pidx, tfield, child_dt = matches[0]
            chosen[i] = child_dt
            child_link[i] = (pidx, tfield, child_dt)

    # 3. build entities
    entities = []
    for i, sheet in enumerate(sheets):
        entity_id = "e{}".format(i)
        e = build_entity(entity_id, sheet, chosen[i], column_overrides.get(entity_id))
        if i in child_link:
            pidx, tfield, _ = child_link[i]
            e["is_child"] = True
            e["parent_entity"] = "e{}".format(pidx)
            e["table_fieldname"] = tfield
        # flattened sheet with line-item columns: pick how rows group into a parent
        if any(c.get("target") == "child" for c in e["columns"]):
            gk = group_keys.get(entity_id)
            if gk is None:
                gk = guess_group_key(e["doctype"], e, sheet)
            e["group_key"] = gk or ""
        entities.append(e)

    entities = order_entities(entities)
    spec = {
        "version": "1",
        "entities": entities,
        "overrides": overrides,
        "column_overrides": column_overrides,
        "group_keys": group_keys,
    }
    plan = build_plan(spec, candidates)
    return spec, plan


def required_fields(doctype):
    """Fields a record must have, that the import is responsible for supplying."""
    meta = frappe.get_meta(doctype)
    out = []
    for df in meta.fields:
        if (
            df.reqd
            and not df.default
            and df.fieldtype not in ("Table", "Table MultiSelect")
            and not df.fetch_from
        ):
            out.append({"fieldname": df.fieldname, "label": df.label or df.fieldname})
    return out


def build_plan(spec, candidates=None):
    candidates = candidates or candidate_doctypes()
    available = [{"label": dt, "value": dt} for dt in candidates]

    entities = []
    for e in spec["entities"]:
        # only parent-field mappings satisfy a parent required field
        mapped_fields = {
            c["field"] for c in e["columns"] if c.get("target") != "child"
        }
        req = []
        if e["doctype"]:
            for rf in required_fields(e["doctype"]):
                req.append({**rf, "satisfied": rf["fieldname"] in mapped_fields})

        # line-item columns grouped by the child table they fill
        tf_labels = (
            {ct["table_fieldname"]: ct["label"] for ct in child_tables(e["doctype"])}
            if e["doctype"]
            else {}
        )
        child_summary = {}
        for c in e["columns"]:
            if c.get("target") == "child":
                tf = c["table_fieldname"]
                cs = child_summary.setdefault(
                    tf,
                    {
                        "table_fieldname": tf,
                        "label": tf_labels.get(tf, tf),
                        "child_doctype": c.get("child_doctype"),
                        "columns": [],
                    },
                )
                cs["columns"].append(c["column"])

        entities.append(
            {
                "id": e["id"],
                "sheet": e["sheet"],
                "doctype": e["doctype"],
                "rows": e["rows"],
                "mapped": len(e["columns"]),
                "unmapped": e["unmapped"],
                # full per-column mapping for the field picker
                "cells": e.get("cells", []),
                "required": req,
                # child (line-item) sheet info, if any
                "is_child": e.get("is_child", False),
                "parent_entity": e.get("parent_entity"),
                "table_fieldname": e.get("table_fieldname"),
                # flattened child-table import
                "has_children": bool(child_summary),
                "child_tables": list(child_summary.values()),
                "group_key": e.get("group_key"),
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
        # only top-level (non-child) records define the import order
        "order": [e["id"] for e in spec["entities"] if e["doctype"] and not e.get("is_child")],
    }
