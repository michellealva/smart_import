import json

import frappe

from smart_import.engine import importer, mapper, reader, template, urls


def has_app_permission():
    return "System Manager" in frappe.get_roles()


def _get_session(session):
    doc = frappe.get_doc("Smart Import Session", session)
    doc.check_permission("write")
    return doc


def _attached_file(doc):
    if doc.source_file:
        return doc.source_file
    return frappe.db.get_value(
        "File",
        {
            "attached_to_doctype": "Smart Import Session",
            "attached_to_name": doc.name,
        },
        "file_url",
    )


@frappe.whitelist()
def new_session():
    doc = frappe.new_doc("Smart Import Session")
    doc.status = "Draft"
    doc.insert()
    frappe.db.commit()
    return doc.name


@frappe.whitelist()
def profile(session):
    """Read the uploaded file and build the first plan."""
    doc = _get_session(session)
    file_url = _attached_file(doc)
    if not file_url:
        frappe.throw("Please upload a file first.")

    data = reader.read_file(file_url)
    if not data["sheets"]:
        frappe.throw(
            "We couldn't find any data in this file. "
            "Make sure the first row has column names."
        )

    spec, plan = mapper.build_spec(data)
    doc.source_file = file_url
    doc.spec = json.dumps(spec, default=str)
    doc.plan = json.dumps(plan, default=str)
    doc.status = "Profiled"
    doc.save()
    frappe.db.commit()
    return plan


@frappe.whitelist()
def set_entity_doctype(session, entity_id, doctype=None):
    """User corrected our guess (or chose to skip a sheet) in the Review step."""
    doc = _get_session(session)
    data = reader.read_file(doc.source_file)
    spec = json.loads(doc.spec or "{}")

    overrides = spec.get("overrides") or {}
    overrides[entity_id] = doctype or ""

    # changing the target doctype invalidates any hand-picked column mappings
    # and the grouping choice
    column_overrides = spec.get("column_overrides") or {}
    column_overrides.pop(entity_id, None)
    group_keys = spec.get("group_keys") or {}
    group_keys.pop(entity_id, None)

    spec, plan = mapper.build_spec(data, overrides, column_overrides, group_keys)
    doc.spec = json.dumps(spec, default=str)
    doc.plan = json.dumps(plan, default=str)
    doc.save()
    frappe.db.commit()
    return plan


@frappe.whitelist()
def set_column_mapping(session, entity_id, column, fieldname=None, table_fieldname=None):
    """Field picker: force a spreadsheet column to a chosen field (or '' to skip).

    For a flattened child-table (line-item) column, pass the parent's
    `table_fieldname`; the choice is stored as "table_fieldname.fieldname".
    """
    doc = _get_session(session)
    data = reader.read_file(doc.source_file)
    spec = json.loads(doc.spec or "{}")

    overrides = spec.get("overrides") or {}
    column_overrides = spec.get("column_overrides") or {}
    group_keys = spec.get("group_keys") or {}

    chosen = fieldname or ""
    if chosen and table_fieldname:
        chosen = "{}.{}".format(table_fieldname, chosen)
    column_overrides.setdefault(entity_id, {})[column] = chosen

    spec, plan = mapper.build_spec(data, overrides, column_overrides, group_keys)
    doc.spec = json.dumps(spec, default=str)
    doc.plan = json.dumps(plan, default=str)
    doc.save()
    frappe.db.commit()
    return plan


@frappe.whitelist()
def set_group_key(session, entity_id, column=None):
    """Choose which column groups flattened rows into one parent record."""
    doc = _get_session(session)
    data = reader.read_file(doc.source_file)
    spec = json.loads(doc.spec or "{}")

    overrides = spec.get("overrides") or {}
    column_overrides = spec.get("column_overrides") or {}
    group_keys = spec.get("group_keys") or {}
    group_keys[entity_id] = column or ""

    spec, plan = mapper.build_spec(data, overrides, column_overrides, group_keys)
    doc.spec = json.dumps(spec, default=str)
    doc.plan = json.dumps(plan, default=str)
    doc.save()
    frappe.db.commit()
    return plan


@frappe.whitelist()
def preview(session, limit=8):
    """First few rows of each sheet, so the user can see the data in Review."""
    doc = _get_session(session)
    data = reader.read_file(doc.source_file)
    limit = int(limit)
    return {
        "sheets": [
            {
                "name": s["name"],
                "headers": s["headers"],
                "rows": s["rows"][:limit],
                "total_rows": len(s["rows"]),
            }
            for s in data["sheets"]
        ]
    }


@frappe.whitelist()
def doctype_fields(doctype):
    """Importable fields for a doctype — powers the field-picker dropdowns.

    Returns {parent: [...], children: [{table_fieldname, label, child_doctype,
    fields: [...]}]} so a flattened sheet's columns can target either a parent
    field or a child-table (line-item) field.
    """
    if not has_app_permission():
        frappe.throw("Not permitted", frappe.PermissionError)
    return mapper.field_options_full(doctype)


@frappe.whitelist()
def importable_doctypes():
    """Every doctype the user can import into (any app) — for the doctype picker."""
    if not has_app_permission():
        frappe.throw("Not permitted", frappe.PermissionError)
    return [{"label": dt, "value": dt} for dt in mapper.all_importable_doctypes()]


@frappe.whitelist()
def link_options(doctype, txt=""):
    """Search records of a doctype — powers the value dropdown for Link filters."""
    if not has_app_permission():
        frappe.throw("Not permitted", frappe.PermissionError)
    meta = frappe.get_meta(doctype)
    title = meta.title_field if (meta.title_field and meta.title_field != "name") else None
    fields = ["name"] + ([title] if title else [])
    filters = [["name", "like", "%{}%".format(txt)]] if txt else None
    rows = frappe.get_all(
        doctype, fields=fields, filters=filters, limit_page_length=20, order_by="modified desc"
    )
    out = []
    for r in rows:
        label = (r.get(title) if title else None) or r.get("name")
        out.append({"label": str(label), "value": r.get("name")})
    return out


@frappe.whitelist()
def template_plan(doctype):
    """Root doctype's fields + the linked doctypes that can become extra sheets."""
    if not has_app_permission():
        frappe.throw("Not permitted", frappe.PermissionError)
    return template.plan(doctype)


def _to_frappe_filters(conditions):
    """Turn UI conditions [{field, operator, value}] into frappe.get_all filters."""
    out = []
    for c in conditions or []:
        field, op, val = c.get("field"), c.get("operator"), c.get("value")
        if not field or not op:
            continue
        if op in ("equals", "="):
            out.append([field, "=", val])
        elif op in ("not equals", "!="):
            out.append([field, "!=", val])
        elif op == "contains":
            out.append([field, "like", "%{}%".format(val or "")])
        elif op == "is set":
            out.append([field, "is", "set"])
        elif op == "is not set":
            out.append([field, "is", "not set"])
        elif op == "in":
            vals = val if isinstance(val, list) else [v.strip() for v in str(val or "").split(",") if v.strip()]
            out.append([field, "in", vals])
        elif op in (">", "<", ">=", "<="):
            out.append([field, op, val])
        else:
            out.append([field, "=", val])
    return out


@frappe.whitelist()
def download_template(doctype, fields_map=None, include=None, mode="blank", filters=None, child_map=None):
    """Build a multi-sheet .xlsx template; returned as base64 for the browser.

    fields_map: {doctype: [fieldnames]} selected per sheet.
    child_map: {table_fieldname: [fieldnames]} line-item columns flattened into
    the root sheet.
    """
    import base64

    if not has_app_permission():
        frappe.throw("Not permitted", frappe.PermissionError)

    def _load(v):
        return json.loads(v) if isinstance(v, str) else (v or None)

    content = template.build_workbook(
        doctype,
        _load(fields_map) or {},
        _load(include) or [],
        mode or "blank",
        _to_frappe_filters(_load(filters)),
        _load(child_map) or {},
    )
    return {
        "filename": "{} import template.xlsx".format(doctype),
        "content_b64": base64.b64encode(content).decode(),
    }


@frappe.whitelist()
def validate(session):
    """Dry-run checks: missing linked records, missing required columns."""
    doc = _get_session(session)
    data = reader.read_file(doc.source_file)
    spec = json.loads(doc.spec or "{}")

    result = importer.validate(spec, data)
    doc.issues = json.dumps(result, default=str)
    doc.status = "Validated"
    doc.save()
    frappe.db.commit()
    return result


@frappe.whitelist()
def recheck(session, decisions=None):
    """Dry-run with the user's fixes applied — reports what would import / be
    skipped / still fail, without creating any records."""
    _get_session(session)
    if isinstance(decisions, str):
        decisions = json.loads(decisions or "{}")
    return importer.recheck(session, decisions or {})


@frappe.whitelist()
def start_import(session, decisions=None):
    doc = _get_session(session)
    if isinstance(decisions, str):
        decisions = json.loads(decisions or "{}")

    doc.status = "Importing"
    doc.progress = json.dumps({"done": 0, "total": 0})
    doc.save()
    frappe.db.commit()

    frappe.enqueue(
        "smart_import.engine.importer.run_import",
        session=session,
        decisions=decisions or {},
        queue="long",
        timeout=7200,
        job_name="smart_import_{}".format(session),
    )
    return {"queued": True}


@frappe.whitelist()
def list_sessions(limit=50):
    """Recent imports, newest first — powers the in-app 'Past imports' page."""
    if not has_app_permission():
        frappe.throw("Not permitted", frappe.PermissionError)

    sessions = frappe.get_all(
        "Smart Import Session",
        filters={"status": ["!=", "Draft"]},
        fields=[
            "name",
            "status",
            "imported_count",
            "failed_count",
            "skipped_count",
            "modified",
            "owner",
        ],
        order_by="modified desc",
        limit=int(limit),
    )

    # attach a friendly creator name (falls back to the user id / email)
    owners = list({s.owner for s in sessions if s.owner})
    names = (
        dict(
            frappe.get_all(
                "User",
                filters={"name": ["in", owners]},
                fields=["name", "full_name"],
                as_list=True,
            )
        )
        if owners
        else {}
    )
    for s in sessions:
        s["owner_name"] = names.get(s.owner) or s.owner

    return sessions


@frappe.whitelist()
def status(session):
    doc = frappe.get_doc("Smart Import Session", session)
    log = json.loads(doc.log or "[]")
    created = [e for e in log if e.get("type") == "created"]
    messages = [e for e in log if e.get("type") != "created"]
    # distinct created doctypes, in first-seen order, for the "Open your app" link
    seen, created_doctypes = set(), []
    for e in created:
        if e.get("doctype") and e["doctype"] not in seen:
            seen.add(e["doctype"])
            created_doctypes.append(e["doctype"])
    return {
        "status": doc.status,
        "progress": json.loads(doc.progress or "{}"),
        "imported": doc.imported_count or 0,
        "failed": doc.failed_count or 0,
        "skipped": doc.skipped_count or 0,
        # records actually created, with a link into the app
        "created": created[:200],
        "created_count": len(created),
        "log": messages[:100],
        # where "Open your app" should go (frontend app home, or desk)
        "app_home": urls.app_home_url(created_doctypes),
    }
