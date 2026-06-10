import frappe


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/smart-import"
        raise frappe.Redirect

    context.no_cache = 1
    context.boot = {
        "csrf_token": frappe.sessions.get_csrf_token(),
        "site_name": frappe.local.site,
    }
    return context
