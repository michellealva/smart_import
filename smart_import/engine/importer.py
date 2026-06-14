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


def is_blank(raw):
    return raw is None or (isinstance(raw, str) and not raw.strip())


def _group_rows(sheet, idx, group_key):
    """Group a flattened sheet's rows into one parent record each.

    Rows sharing the same (case-insensitive) value in `group_key` become one
    group, in first-seen order. Rows with a blank key — or no key column — each
    become their own group, so nothing is silently merged.
    """
    gi = idx.get(group_key) if group_key else None
    groups = []
    pos = {}
    blank = 0
    for n, row in enumerate(sheet["rows"], start=2):
        kv = cell(row, gi) if gi is not None else None
        ks = str(kv).strip().lower() if kv is not None else ""
        if ks:
            key = ks
        else:
            key = "\x00blank{}".format(blank)
            blank += 1
        if key not in pos:
            pos[key] = len(groups)
            groups.append((key, []))
        groups[pos[key]][1].append((n, row))
    return groups


def column_value_counts(sheet, idx, column):
    """{distinct value -> rows it appears in} for a column, deduped
    case-insensitively (so 'Contract sent' and 'Contract Sent' are one value)."""
    counts = {}  # lowercased -> count
    seen = {}  # lowercased -> first-seen original casing
    i = idx.get(column)
    for row in sheet["rows"]:
        v = cell(row, i)
        if v in (None, ""):
            continue
        s = str(v).strip()
        if not s:
            continue
        k = s.lower()
        counts[k] = counts.get(k, 0) + 1
        seen.setdefault(k, s)
    return {seen[k]: counts[k] for k in counts}


# ---------------------------------------------------------------- validate


def linkable_values_in_sheets(spec, data, target):
    """Lowercased values present in any sheet that maps to `target`.

    Those records will exist after import, so a reference matching one of them
    is fine — even if the record doesn't exist in the site yet.
    """
    sheets = {s["name"]: s for s in data["sheets"]}
    out = set()
    for e in spec["entities"]:
        if e["doctype"] != target or e["sheet"] not in sheets:
            continue
        for row in sheets[e["sheet"]]["rows"]:
            for v in row:
                if v in (None, ""):
                    continue
                s = str(v).strip().lower()
                if s:
                    out.add(s)
    return out


def _field_key(c):
    """Disambiguate a column's field across parent and child tables."""
    tf = c.get("table_fieldname")
    return "{}.{}".format(tf, c["field"]) if tf else c["field"]


def validate(spec, data):
    sheets = {s["name"]: s for s in data["sheets"]}
    issues = []
    entity_reports = []

    for e in spec["entities"]:
        if not e["doctype"] or e["sheet"] not in sheets:
            continue
        sheet = sheets[e["sheet"]]
        idx = col_index_for(sheet)
        meta = frappe.get_meta(e["doctype"])
        # required-field check applies to parent fields only
        mapped_fields = {c["field"] for c in e["columns"] if c.get("target") != "child"}

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

        # 1b. required fields that ARE mapped but left blank in some rows.
        #     The column exists, so case 1 above won't catch it — but a blank
        #     cell in a mandatory field would fail that record at insert time.
        #     Surface it as a per-value picker (skip those rows, or fill a value).
        required_labels = {
            df.fieldname: (df.label or df.fieldname)
            for df in meta.fields
            if df.reqd
            and not df.default
            and df.fieldtype not in ("Table", "Table MultiSelect")
            and not df.fetch_from
        }
        if required_labels:
            has_child = any(c.get("target") == "child" for c in e["columns"])
            if has_child:
                groups = _group_rows(sheet, idx, e.get("group_key") or "")
            else:
                groups = [
                    (None, [(n, row)])
                    for n, row in enumerate(sheet["rows"], start=2)
                ]
            seen_required = set()
            for c in e["columns"]:
                if c.get("target") == "child":
                    continue
                label = required_labels.get(c["field"])
                if not label or c["field"] in seen_required:
                    continue
                seen_required.add(c["field"])
                ci = idx.get(c["column"])
                # a parent field is blank for a group only when blank in every
                # row of that group (the importer takes the first non-blank cell)
                blank = sum(
                    1
                    for _k, grows in groups
                    if all(is_blank(cell(r, ci)) for _, r in grows)
                )
                if not blank:
                    continue
                choices = []
                if c.get("fieldtype") == "Select" and c.get("select_options"):
                    choices += [
                        {"label": o, "value": o} for o in c["select_options"]
                    ]
                choices += [
                    {"label": "Skip those rows", "value": "__skip__"},
                    {"label": "Type a value to use", "value": "__manual__"},
                ]
                issues.append(
                    {
                        "id": "{}:{}:missing_values".format(e["id"], _field_key(c)),
                        "entity": e["id"],
                        "sheet": e["sheet"],
                        "type": "missing_values",
                        "severity": "action",
                        "column": c["column"],
                        "field": c["field"],
                        "table_fieldname": c.get("table_fieldname"),
                        "fieldtype": c.get("fieldtype"),
                        "count": blank,
                        "message": (
                            '{} row(s) have no value in "{}", but {} requires it.'
                        ).format(blank, c["column"], label),
                        "choices": choices,
                        "values": [
                            {"value": "", "count": blank, "suggestion": "__skip__"}
                        ],
                    }
                )

        # 2. link values that don't exist yet, and 3. dropdown values that
        #    aren't valid options — both surfaced as per-value pickers.
        checked_fields = set()
        for c in e["columns"]:
            # one issue per field, even if two columns map to it (parent and a
            # child field can share a fieldname, so key by table too)
            fkey = _field_key(c)
            if fkey in checked_fields:
                continue
            checked_fields.add(fkey)
            target = c.get("link_doctype")

            if target:
                counts = column_value_counts(sheet, idx, c["column"])
                if not counts:
                    continue
                link_map = load_link_map(target)
                # values that another sheet in this file will create count as
                # "will exist" — but only the values actually present there, so
                # typos that match nothing (existing OR sheet) still get caught.
                will_exist = linkable_values_in_sheets(spec, data, target)
                keys = list(link_map.keys()) + list(will_exist)
                missing = []
                for v in sorted(counts):
                    k = v.lower()
                    if k in link_map or k in will_exist:
                        continue
                    if keys and get_close_matches(k, keys, n=1, cutoff=0.92):
                        continue
                    missing.append(v)

                if missing:
                    issues.append(
                        {
                            "id": "{}:{}:missing_links".format(e["id"], fkey),
                            "entity": e["id"],
                            "sheet": e["sheet"],
                            "type": "link_values",
                            "severity": "action",
                            "column": c["column"],
                            "field": c["field"],
                            "table_fieldname": c.get("table_fieldname"),
                            "fieldtype": "Link",
                            "target_doctype": target,
                            "count": len(missing),
                            "message": (
                                '{} value(s) in column "{}" don\'t exist yet as {} records.'
                            ).format(len(missing), c["column"], target),
                            "choices": [
                                {"label": "Create automatically", "value": "__create__"},
                                {"label": "Leave blank", "value": "__blank__"},
                                {"label": "Skip these rows", "value": "__skip__"},
                                {"label": "Type a value…", "value": "__manual__"},
                            ],
                            "values": [
                                {"value": v, "count": counts[v], "suggestion": "__create__"}
                                for v in missing[:MAX_ISSUE_VALUES]
                            ],
                        }
                    )
                continue

            if c.get("fieldtype") == "Select":
                options = c.get("select_options") or []
                if not options:
                    continue
                opt_lower = {o.strip().lower(): o for o in options}
                counts = column_value_counts(sheet, idx, c["column"])
                bad = [v for v in sorted(counts) if v.strip().lower() not in opt_lower]
                if not bad:
                    continue

                values_payload = []
                for v in bad[:MAX_ISSUE_VALUES]:
                    close = get_close_matches(
                        v.strip().lower(), list(opt_lower.keys()), n=1, cutoff=0.6
                    )
                    suggestion = opt_lower[close[0]] if close else "__blank__"
                    values_payload.append(
                        {"value": v, "count": counts[v], "suggestion": suggestion}
                    )

                issues.append(
                    {
                        "id": "{}:{}:bad_options".format(e["id"], fkey),
                        "entity": e["id"],
                        "sheet": e["sheet"],
                        "type": "select_values",
                        "severity": "action",
                        "column": c["column"],
                        "field": c["field"],
                        "table_fieldname": c.get("table_fieldname"),
                        "fieldtype": "Select",
                        "count": len(bad),
                        "message": (
                            '{} value(s) in column "{}" aren\'t valid options for {}.'
                        ).format(len(bad), c["column"], c.get("label") or c["field"]),
                        # dropdowns only accept their defined options — no free
                        # text, since the user chose to keep dropdowns fixed.
                        "choices": [{"label": o, "value": o} for o in options]
                        + [
                            {"label": "Leave blank", "value": "__blank__"},
                            {"label": "Skip these rows", "value": "__skip__"},
                        ],
                        "values": values_payload,
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


def _match_existing(m, value):
    """Find an existing record by exact or close (fuzzy) match. None if absent."""
    key = str(value).strip().lower()
    if not key:
        return None
    if key in m:
        return m[key]
    close = get_close_matches(key, list(m.keys()), n=1, cutoff=0.92)
    return m[close[0]] if close else None


def _create_link(target, value, link_maps, created_counts):
    name = create_link_record(target, value)
    if name:
        link_maps[target][str(value).strip().lower()] = name
        created_counts[target] = created_counts.get(target, 0) + 1
    return name


def resolve_link_cell(raw, col, link_maps, vd, created_counts):
    """Resolve a Link cell, honouring the user's per-value decision."""
    target = col["link_doctype"]
    link_maps.setdefault(target, load_link_map(target))
    m = link_maps[target]

    existing = _match_existing(m, raw)
    if existing:
        return existing

    choice = vd.get(str(raw).strip().lower())
    if choice == "__blank__":
        return None
    if choice == "__skip__":
        raise SkipRow(
            '"{}" doesn\'t exist in {} — row skipped as you chose.'.format(raw, target)
        )

    # __create__ or no decision -> create from the original value
    if choice in (None, "__create__", ""):
        name = _create_link(target, raw, link_maps, created_counts)
        if name:
            return name
        raise ValueError('Could not find or create "{}" in {}.'.format(raw, target))

    # otherwise the choice is a literal replacement (chosen record or typed)
    replacement = str(choice).strip()
    existing = _match_existing(m, replacement)
    if existing:
        return existing
    name = _create_link(target, replacement, link_maps, created_counts)
    if name:
        return name
    raise ValueError('Could not find or create "{}" in {}.'.format(replacement, target))


def resolve_select_cell(raw, col, vd):
    """Resolve a Select cell, honouring the user's per-value decision."""
    options = col.get("select_options") or []
    opt_lower = {o.strip().lower(): o for o in options}
    s = str(raw).strip()

    if s.lower() in opt_lower:
        return opt_lower[s.lower()]

    choice = vd.get(s.lower())
    if choice in ("__blank__", None, ""):
        return None
    if choice == "__skip__":
        raise SkipRow(
            '"{}" isn\'t a valid option for {} — row skipped as you chose.'.format(
                raw, col["label"]
            )
        )

    # a chosen option or a manually typed value
    replacement = str(choice).strip()
    if replacement.lower() in opt_lower:
        return opt_lower[replacement.lower()]
    return replacement


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
    from smart_import.engine import reader, urls

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
        created_counts = {}

        # Step 1 — collect the user's per-value decisions for each flagged field.
        # value_decisions[(entity_id, field)] = {value_lower: choice}, where a
        # choice is a sentinel (__create__/__blank__/__skip__) or a literal
        # replacement value (a chosen option/record, or a manually typed value).
        value_decisions = {}
        for iid, issue in issues.items():
            if issue.get("type") not in (
                "link_values",
                "select_values",
                "missing_values",
            ):
                continue
            key = (issue["entity"], issue.get("table_fieldname"), issue["field"])
            vd = value_decisions.setdefault(key, {})
            for val, choice in (decisions.get(iid) or {}).items():
                vd[str(val).strip().lower()] = choice
            # fall back to the suggested choice for values the user left untouched
            for entry in issue.get("values", []):
                v = str(entry["value"]).strip().lower()
                vd.setdefault(v, entry.get("suggestion"))

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
            parent_cols = [c for c in e["columns"] if c.get("target") != "child"]
            child_cols = [c for c in e["columns"] if c.get("target") == "child"]

            for col in e["columns"]:
                t = col.get("link_doctype")
                if t and t not in link_maps:
                    link_maps[t] = load_link_map(t)

            def resolve_one(col, raw):
                """Turn a raw cell into a stored value, honouring user decisions."""
                vd = value_decisions.get(
                    (e["id"], col.get("table_fieldname"), col["field"]), {}
                )
                if col.get("link_doctype"):
                    return resolve_link_cell(raw, col, link_maps, vd, created_counts)
                if col.get("fieldtype") == "Select":
                    return resolve_select_cell(raw, col, vd)
                return coerce(col, raw)

            def register_link(rec):
                # later sheets may link to this record
                if e["doctype"] in link_maps:
                    link_maps[e["doctype"]][str(rec.name).strip().lower()] = rec.name
                    if own_title and rec.get(own_title):
                        link_maps[e["doctype"]][
                            str(rec.get(own_title)).strip().lower()
                        ] = rec.name

            def log_created(rec):
                log.append(
                    {
                        "type": "created",
                        "doctype": e["doctype"],
                        "name": rec.name,
                        "sheet": e["sheet"],
                        "route": urls.record_url(e["doctype"], rec.name),
                    }
                )

            # group flattened rows into one parent record each, or import row-by-row
            if child_cols:
                groups = _group_rows(sheet, idx, e.get("group_key") or "")
            else:
                groups = [(None, [(n, row)]) for n, row in enumerate(sheet["rows"], start=2)]

            for _key, grows in groups:
                first_n = grows[0][0]
                frappe.db.savepoint(SAVEPOINT)
                try:
                    values = {"doctype": e["doctype"]}
                    # parent fields: first non-empty cell across the group's rows
                    for col in parent_cols:
                        ci = idx.get(col["column"])
                        raw = next(
                            (
                                cell(r, ci)
                                for _, r in grows
                                if not is_blank(cell(r, ci))
                            ),
                            None,
                        )
                        if is_blank(raw):
                            # honour the user's decision for a blank required
                            # field (skip the row, or fill a chosen/typed value)
                            vd = value_decisions.get(
                                (e["id"], col.get("table_fieldname"), col["field"]),
                                {},
                            )
                            choice = vd.get("")
                            if choice == "__skip__":
                                raise SkipRow(
                                    'Row skipped — no value for required field "{}".'.format(
                                        col.get("label") or col["field"]
                                    )
                                )
                            if choice and choice not in ("__blank__", "__manual__"):
                                raw = choice  # a chosen option or typed value
                            else:
                                continue
                        v = resolve_one(col, raw)
                        if v is not None:
                            values[col["field"]] = v

                    # child rows: one line per source row, grouped by table field
                    tables = {}
                    for _, r in grows:
                        per_table = {}
                        skip_line = False
                        for col in child_cols:
                            raw = cell(r, idx.get(col["column"]))
                            if is_blank(raw):
                                continue
                            try:
                                v = resolve_one(col, raw)
                            except SkipRow:
                                skip_line = True  # "skip these rows" drops the whole line
                                break
                            if v is not None:
                                per_table.setdefault(col["table_fieldname"], {})[
                                    col["field"]
                                ] = v
                        if skip_line:
                            continue
                        for tf, d in per_table.items():
                            if d:
                                tables.setdefault(tf, []).append(d)
                    for tf, rows_list in tables.items():
                        values[tf] = rows_list

                    rec = frappe.get_doc(values)
                    rec.insert()
                    imported += 1
                    log_created(rec)
                    register_link(rec)

                except SkipRow as ex:
                    frappe.db.rollback(save_point=SAVEPOINT)
                    skipped += 1
                    log.append(
                        {"type": "skipped", "sheet": e["sheet"], "row": first_n, "message": str(ex)}
                    )
                except frappe.DuplicateEntryError:
                    frappe.db.rollback(save_point=SAVEPOINT)
                    skipped += 1
                    log.append(
                        {
                            "type": "skipped",
                            "sheet": e["sheet"],
                            "row": first_n,
                            "message": "A record with the same identity already exists — skipped.",
                        }
                    )
                except Exception as ex:
                    frappe.db.rollback(save_point=SAVEPOINT)
                    failed += 1
                    log.append(
                        {"type": "error", "sheet": e["sheet"], "row": first_n, "message": str(ex)[:300]}
                    )

                done += len(grows)
                if done % 25 < len(grows):
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

        for target, n in created_counts.items():
            log.insert(
                0,
                {
                    "type": "info",
                    "message": "Created {} new {} record(s) automatically.".format(
                        n, target
                    ),
                },
            )

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
