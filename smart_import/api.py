import json

import frappe

from smart_import.engine import importer, mapper, reader


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

    spec, plan = mapper.build_spec(data, overrides)
    doc.spec = json.dumps(spec, default=str)
    doc.plan = json.dumps(plan, default=str)
    doc.save()
    frappe.db.commit()
    return plan


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
def status(session):
    doc = frappe.get_doc("Smart Import Session", session)
    log = json.loads(doc.log or "[]")
    return {
        "status": doc.status,
        "progress": json.loads(doc.progress or "{}"),
        "imported": doc.imported_count or 0,
        "failed": doc.failed_count or 0,
        "skipped": doc.skipped_count or 0,
        "log": log[:100],
    }
