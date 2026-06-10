app_name = "smart_import"
app_title = "Smart Import"
app_publisher = "Smart Import"
app_description = "Friendly, smart data import for Frappe apps"
app_email = "hello@example.com"
app_license = "mit"

# Serve the wizard UI at /smart-import
website_route_rules = [
    {"from_route": "/smart-import/<path:app_path>", "to_route": "smart-import"},
]

add_to_apps_screen = [
    {
        "name": "smart_import",
        "logo": "/assets/smart_import/logo.svg",
        "title": "Smart Import",
        "route": "/smart-import",
        "has_permission": "smart_import.api.has_app_permission",
    }
]
