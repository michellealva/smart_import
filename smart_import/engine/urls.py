"""Where to send the user to view a record we created.

App-agnostic: any app can register a `smart_import_record_url` hook to map its
doctypes to its own frontend routes. We also ship built-in routes for Frappe
CRM (only applied when CRM is installed). Anything unmapped falls back to the
universal desk URL (/app/...).
"""

from urllib.parse import quote

import frappe

# doctype -> (owning app, frontend path template). Applied only when the owning
# app is installed, so this stays inert on benches without that app.
_FRONTEND_ROUTES = {
    "CRM Lead": ("crm", "/crm/leads/{name}"),
    "CRM Deal": ("crm", "/crm/deals/{name}"),
    "Contact": ("crm", "/crm/contacts/{name}"),
    "CRM Organization": ("crm", "/crm/organizations/{name}"),
}


def _installed_apps():
    try:
        return set(frappe.get_installed_apps())
    except Exception:
        return set()


def _desk_url(doctype, name):
    return "/app/{}/{}".format(frappe.scrub(doctype).replace("_", "-"), quote(str(name)))


def record_url(doctype, name):
    """A URL to view one created record — the app's frontend if it has one,
    otherwise desk."""
    # 1. an app's own mapping wins
    for fn in frappe.get_hooks("smart_import_record_url") or []:
        try:
            url = frappe.get_attr(fn)(doctype, name)
            if url:
                return url
        except Exception:
            continue

    # 2. built-in frontend routes, only if the owning app is installed
    route = _FRONTEND_ROUTES.get(doctype)
    if route and route[0] in _installed_apps():
        return route[1].format(name=quote(str(name)))

    # 3. desk fallback — always valid
    return _desk_url(doctype, name)


def app_home_url(doctypes):
    """Where 'Open your app' should go: the frontend home of the first imported
    doctype that has one, else desk."""
    apps = _installed_apps()
    for dt in doctypes:
        route = _FRONTEND_ROUTES.get(dt)
        if route and route[0] in apps:
            return "/" + route[1].strip("/").split("/")[0]
    return "/app"
