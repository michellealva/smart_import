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

Open it at: **`http://yoursite:8000/smart-import`**

---

## Installing on a local bench

You need a working Frappe bench (the same one running your CRM).

```bash
cd ~/frappe-bench          # or wherever your bench lives
bench get-app /path/to/smart_import
bench --site YOUR_SITE_NAME install-app smart_import
bench --site YOUR_SITE_NAME clear-cache
```

Replace `/path/to/smart_import` with the folder this README is in, and
`YOUR_SITE_NAME` with your site (for example `crm.localhost`).

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
- `smart_import/engine/mapper.py` — guesses doctypes and matches columns
- `smart_import/engine/importer.py` — checks for problems, then imports safely
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
