# Smart Import

A friendly data import tool for Frappe apps (CRM, ERPNext, or any custom app).

Upload an Excel or CSV file — even one with multiple sheets — and Smart Import
figures out the rest:

- Guesses what each sheet is (Organizations, Contacts, Leads...)
- Matches your column names to the right fields, even if they don't match exactly
  ("Phone Number" finds "Mobile No")
- Imports sheets in the right order so everything connects properly
- Creates missing things automatically (a new Lead Source, a Company a contact
  mentions) instead of failing
- Accepts dates in any common format
- One bad row never stops the import — you get a plain-language report at the end
- Imports **child tables (line items)** from a flattened sheet — repeat the parent
  columns per row and they're grouped into one record with many line items
- **Download a ready-to-fill template** for any doctype, with related records and
  line-item columns laid out for you
- After importing, links open the record in its app — a frontend app's own page
  (e.g. CRM) when it has one, otherwise the desk form

Open it at: **`http://yoursite:8000/smart-import`**

---

## Compatibility

- **Frappe:** v15 (stable) and up — verified to run on v15 through `develop`.
  Uses only long-stable framework APIs, no version-specific branches.
- **Python:** 3.10+
- **App-agnostic:** requires only `frappe`; works with any installed app's
  doctypes (CRM, ERPNext, custom apps).
- The frontend bundles its own `frappe-ui`, so it's independent of the bench's
  frappe-ui version.

---

## Installing on a local bench

You need a working Frappe bench (v15+).

```bash
cd ~/frappe-bench          # or wherever your bench lives
bench get-app https://github.com/michellealva/smart_import
bench --site YOUR_SITE_NAME install-app smart_import
bench --site YOUR_SITE_NAME clear-cache
```

Replace `YOUR_SITE_NAME` with your site (for example `crm.localhost`).

The frontend is already built and included, so that's it. Start your bench
(`bench start`) and open `/smart-import` in the browser while logged in as
Administrator.

## Try it immediately

There's a sample file at `samples/sample_crm_data.xlsx` with a "Companies"
sheet and a "Contacts" sheet. One contact mentions a company that isn't in
the file — on purpose — so you can see the auto-create feature work.

## Rebuilding the frontend (only after changing frontend code)

```bash
cd apps/smart_import/frontend
npm install
npm run build
bench --site YOUR_SITE_NAME clear-cache
```

## How it works (for the curious)

- `smart_import/engine/reader.py` — opens .xlsx/.csv files
- `smart_import/engine/mapper.py` — guesses doctypes, matches columns, groups
  flattened child-table rows
- `smart_import/engine/importer.py` — checks for problems, then imports safely
- `smart_import/engine/template.py` — builds downloadable fill-in templates
- `smart_import/engine/urls.py` — resolves where a created record opens
  (frontend app vs desk; extend via the `smart_import_record_url` hook)
- `smart_import/api.py` — the endpoints the wizard screen talks to
- `frontend/` — the wizard UI (Vue 3 + frappe-ui)

Each import is saved as a **Smart Import Session** document, so you can always
see past imports and their logs at `/app/smart-import-session`.

## Adding more target doctypes

By default Smart Import recognizes CRM and common doctypes. Any app can add
its own by declaring this in its `hooks.py`:

```python
smart_import_doctypes = ["My Custom Doctype", "Another One"]
```
