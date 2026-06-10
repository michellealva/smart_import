"""Validate and import data based on the spec.

Key behaviors that make this friendlier than the standard import:
- Missing linked records (sources, industries, organizations...) can be
  created automatically instead of failing the row.
- Link values are matched case-insensitively and fuzzily ("acme corp"
  matches "Acme Corp").
- Dates in any common format are accepted.
- One bad row never stops the import; every failure is logged in plain
  language with its row number.
"""

import datetime
import json
import re
from difflib import get_close_matches

import frappe

SAVEPOINT = "smart_import_row"
MAX_LOG = 1000
MAX_ISSUE_VALUES = 500


class SkipRow(Exception):
    pass


def get_title_fieldname(doctype):
    meta = frappe.get_meta(doctype)
    autoname = meta.autoname or ""
    if autoname.startswith("field:"):
        return autoname.split(":", 1)[1]
    if meta.title_field and meta.title_field != "name":
        return meta.title_field
    return None


def load_link_map(doctype):
    """Map of lowercased name AND title value -> real record name."""
    title_field = get_title_fieldname(doctype)
    fields = ["name"]
    if title_field:
        fields.append(title_field)

    out = {}
    try:
        records = frappe.get_all(doctype, fields=fields, limit_page_length=0)
    except Exception:
        records = []
    for d in records:
        out[str(d.name).strip().lower()] = d.name
        if title_field and d.get(title_field):
            out[str(d.get(title_field)).strip().lower()] = d.name
    return out


def col_index_for(sheet):
    return {h: i for i, h in enumerate(sheet["headers"])}


def cell(row, idx):
    if idx is None or idx >= len(row):
        return None
    return row[idx]


# ---------------------------------------------------------------- validate


def validate(spec, data):
    sheets = {s["name"]: s for s in data["sheets"]}
    issues = []
    entity_reports = []
    imported_doctypes = {e["doctype"] for e in spec["entities"] if e["doctype"]}

    for e in spec["entities"]:
        if not e["doctype"] or e["sheet"] not in sheets:
            continue
        sheet = sheets[e["sheet"]]
        idx = col_index_for(sheet)
        meta = frappe.get_meta(e["doctype"])
        mapped_fields = {c["field"] for c in e["columns"]}

        # 1. required fields not present in the file
        missing_required = []
        for df in meta.fields:
            if (
                df.reqd
                and not df.default
                and df.fieldname not in mapped_fields
                and df.fieldtype not in ("Table", "Table MultiSelect")
                and not df.fetch_from
            ):
                missing_required.append(df.label or df.fieldname)
        if missing_required:
            issues.append(
                {
                    "id": "{}:required".format(e["id"]),
                    "entity": e["id"],
                    "sheet": e["sheet"],
                    "type": "missing_required",
                    "severity": "info",
                    "message": (
                        'Sheet "{}" has no column for: {}. '
                        "Rows may fail if {} requires these."
                    ).format(
                        e["sheet"], ", ".join(missing_required), e["doctype"]
                    ),
                    "options": [],
                }
            )

        # 2. link values that don't exist yet
        for c in e["columns"]:
            target = c.get("link_doctype")
            if not target:
                continue
            # if another sheet in this same file creates these records,
            # they'll exist by the time this sheet imports
            if target in imported_doctypes and target != e["doctype"]:
                continue

            i = idx.get(c["column"])
            values = set()
            for row in sheet["rows"]:
                v = cell(row, i)
                if v not in (None, ""):
                    s = str(v).strip()
                    if s:
                        values.add(s)
            if not values:
                continue

            link_map = load_link_map(target)
            keys = list(link_map.keys())
            missing = []
            for v in sorted(values):
                k = v.lower()
                if k in link_map:
                    continue
                if keys and get_close_matches(k, keys, n=1, cutoff=0.92):
                    continue
                missing.append(v)

            if missing:
                issues.append(
                    {
                        "id": "{}:{}:missing_links".format(e["id"], c["field"]),
                        "entity": e["id"],
                        "sheet": e["sheet"],
                        "type": "missing_links",
                        "severity": "action",
                        "column": c["column"],
                        "field": c["field"],
                        "target_doctype": target,
                        "count": len(missing),
                        "values": missing[:8],
                        "all_values": missing[:MAX_ISSUE_VALUES],
                        "message": (
                            '{} value(s) in column "{}" don\'t exist yet as {} records.'
                        ).format(len(missing), c["column"], target),
                        "options": [
                            {"label": "Create them for me", "value": "create"},
                            {"label": "Leave that field empty", "value": "blank"},
                            {"label": "Skip those rows", "value": "skip"},
                        ],
                        "default": "create",
                    }
                )

        entity_reports.append(
            {
                "id": e["id"],
                "sheet": e["sheet"],
                "doctype": e["doctype"],
                "rows": len(sheet["rows"]),
            }
        )

    return {"issues": issues, "entities": entity_reports}


# ------------------------------------------------------------------ import


def clean_number(value):
    s = re.sub(r"[^\d.\-]", "", str(value))
    return s or "0"


def coerce(col, value):
    """Convert a raw cell into what the field expects."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None

    ftype = col["fieldtype"]

    if ftype == "Date":
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        from dateutil import parser as dateparser

        return dateparser.parse(str(value)).date()

    if ftype == "Datetime":
        if isinstance(value, datetime.datetime):
            return value
        from dateutil import parser as dateparser

        return dateparser.parse(str(value))

    if ftype == "Int":
        return int(float(clean_number(value)))

    if ftype in ("Float", "Currency", "Percent"):
        return float(clean_number(value))

    if ftype == "Check":
        return 1 if str(value).strip().lower() in ("1", "true", "yes", "y") else 0

    if ftype == "Select":
        options = col.get("select_options") or []
        sval = str(value).strip()
        for o in options:
            if o.strip().lower() == sval.lower():
                return o
        raise ValueError(
            '"{}" is not one of the allowed options for {} ({})'.format(
                sval, col["label"], ", ".join(options[:8])
            )
        )

    return str(value)


def create_link_record(doctype, value):
    """Create a simple master record (e.g. a Lead Source) from just its name."""
    value = str(value).strip()
    if not value:
        return None
    title_field = get_title_fieldname(doctype)
    rec = frappe.new_doc(doctype)
    if title_field:
        rec.set(title_field, value)
    else:
        rec.name = value
    rec.flags.ignore_mandatory = True

    frappe.db.savepoint(SAVEPOINT)
    try:
        rec.insert()
        return rec.name
    except frappe.DuplicateEntryError:
        frappe.db.rollback(save_point=SAVEPOINT)
        existing = load_link_map(doctype).get(value.lower())
        return existing
    except Exception:
        frappe.db.rollback(save_point=SAVEPOINT)
        return None


def resolve_link(value, target, link_maps, policy):
    m = link_maps[target]
    key = str(value).strip().lower()
    if not key:
        return None
    if key in m:
        return m[key]

    close = get_close_matches(key, list(m.keys()), n=1, cutoff=0.92)
    if close:
        return m[close[0]]

    if policy == "blank":
        return None
    if policy == "skip":
        raise SkipRow(
            '"{}" doesn\'t exist in {} — row skipped as you chose.'.format(
                value, target
            )
        )
    # default: create
    name = create_link_record(target, value)
    if name:
        m[key] = name
        return name
    raise ValueError(
        'Could not find or create "{}" in {}.'.format(value, target)
    )


def set_progress(session, payload):
    frappe.db.set_value(
        "Smart Import Session",
        session,
        "progress",
        json.dumps(payload, default=str),
        update_modified=False,
    )
    frappe.db.commit()


def run_import(session, decisions=None):
    """Background job: the actual import."""
    from smart_import.engine import reader

    decisions = decisions or {}
    doc = frappe.get_doc("Smart Import Session", session)

    log = []
    imported = failed = skipped = 0
    done = 0

    try:
        data = reader.read_file(doc.source_file)
        spec = json.loads(doc.spec or "{}")
        issue_data = json.loads(doc.issues or "{}")
        issues = {i["id"]: i for i in issue_data.get("issues", [])}
        sheets = {s["name"]: s for s in data["sheets"]}

        link_maps = {}
        policies = {}

        # Step 1 — handle "missing link" decisions up front
        for iid, issue in issues.items():
            if issue.get("type") != "missing_links":
                continue
            action = decisions.get(iid) or issue.get("default") or "create"
            policies[(issue["entity"], issue["field"])] = action
            if action == "create":
                target = issue["target_doctype"]
                link_maps.setdefault(target, load_link_map(target))
                created = 0
                for v in issue.get("all_values") or []:
                    if str(v).strip().lower() in link_maps[target]:
                        continue
                    name = create_link_record(target, v)
                    if name:
                        link_maps[target][str(v).strip().lower()] = name
                        created += 1
                if created:
                    log.append(
                        {
                            "type": "info",
                            "message": "Created {} new {} record(s) from column \"{}\".".format(
                                created, target, issue["column"]
                            ),
                        }
                    )
        frappe.db.commit()

        # Step 2 — import each sheet in dependency order
        active = [
            e
            for e in spec["entities"]
            if e["doctype"] and e["sheet"] in sheets
        ]
        total = sum(len(sheets[e["sheet"]]["rows"]) for e in active)

        for e in active:
            sheet = sheets[e["sheet"]]
            idx = col_index_for(sheet)
            own_title = get_title_fieldname(e["doctype"])

            for col in e["columns"]:
                t = col.get("link_doctype")
                if t and t not in link_maps:
                    link_maps[t] = load_link_map(t)

            for n, row in enumerate(sheet["rows"], start=2):
                frappe.db.savepoint(SAVEPOINT)
                try:
                    values = {"doctype": e["doctype"]}
                    for col in e["columns"]:
                        raw = cell(row, idx.get(col["column"]))
                        if raw is None or (
                            isinstance(raw, str) and not raw.strip()
                        ):
                            continue
                        if col.get("link_doctype"):
                            policy = policies.get(
                                (e["id"], col["field"]), "create"
                            )
                            v = resolve_link(
                                raw, col["link_doctype"], link_maps, policy
                            )
                        else:
                            v = coerce(col, raw)
                        if v is not None:
                            values[col["field"]] = v

                    rec = frappe.get_doc(values)
                    rec.insert()
                    imported += 1

                    # later sheets may link to this record
                    if e["doctype"] in link_maps:
                        link_maps[e["doctype"]][
                            str(rec.name).strip().lower()
                        ] = rec.name
                        if own_title and rec.get(own_title):
                            link_maps[e["doctype"]][
                                str(rec.get(own_title)).strip().lower()
                            ] = rec.name

                except SkipRow as ex:
                    frappe.db.rollback(save_point=SAVEPOINT)
                    skipped += 1
                    log.append(
                        {
                            "type": "skipped",
                            "sheet": e["sheet"],
                            "row": n,
                            "message": str(ex),
                        }
                    )
                except frappe.DuplicateEntryError:
                    frappe.db.rollback(save_point=SAVEPOINT)
                    skipped += 1
                    log.append(
                        {
                            "type": "skipped",
                            "sheet": e["sheet"],
                            "row": n,
                            "message": "A record with the same identity already exists — skipped.",
                        }
                    )
                except Exception as ex:
                    frappe.db.rollback(save_point=SAVEPOINT)
                    failed += 1
                    log.append(
                        {
                            "type": "error",
                            "sheet": e["sheet"],
                            "row": n,
                            "message": str(ex)[:300],
                        }
                    )

                done += 1
                if done % 25 == 0:
                    set_progress(
                        session,
                        {
                            "done": done,
                            "total": total,
                            "sheet": e["sheet"],
                            "imported": imported,
                            "failed": failed,
                            "skipped": skipped,
                        },
                    )

            frappe.db.commit()

        status = "Completed" if failed == 0 else ("Partial" if imported else "Failed")
        set_progress(
            session,
            {
                "done": done,
                "total": total,
                "imported": imported,
                "failed": failed,
                "skipped": skipped,
            },
        )

    except Exception:
        frappe.db.rollback()
        status = "Failed"
        log.append({"type": "error", "message": frappe.get_traceback()[-2000:]})

    frappe.db.set_value(
        "Smart Import Session",
        session,
        {
            "status": status,
            "imported_count": imported,
            "failed_count": failed,
            "skipped_count": skipped,
            "log": json.dumps(log[-MAX_LOG:], default=str),
        },
        update_modified=False,
    )
    frappe.db.commit()
