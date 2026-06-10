"""Read .xlsx and .csv files into a simple structure:
{"sheets": [{"name": ..., "headers": [...], "rows": [[...], ...]}]}
"""

import csv

import frappe


def get_path(file_url):
    file_doc = frappe.get_doc("File", {"file_url": file_url})
    return file_doc.get_full_path()


def read_file(file_url):
    path = str(get_path(file_url))
    if path.lower().endswith(".csv"):
        sheets = [read_csv(path)]
    else:
        sheets = read_xlsx(path)
    return {"sheets": [s for s in sheets if s["headers"] and s["rows"]]}


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        raw = list(csv.reader(f))

    raw = [r for r in raw if any(str(c).strip() for c in r)]
    headers = [str(h).strip() for h in (raw[0] if raw else [])]
    rows = raw[1:]

    keep = [i for i, h in enumerate(headers) if h]
    headers = [headers[i] for i in keep]
    rows = [[(r[i] if i < len(r) else None) for i in keep] for r in rows]

    return {"name": "Sheet1", "headers": headers, "rows": rows}


def read_xlsx(path):
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        headers = []
        rows = []
        for row in ws.iter_rows(values_only=True):
            if not headers:
                if row and any(c is not None and str(c).strip() for c in row):
                    headers = [str(c).strip() if c is not None else "" for c in row]
                continue
            if row and any(c is not None and str(c).strip() != "" for c in row):
                rows.append(list(row))

        keep = [i for i, h in enumerate(headers) if h]
        headers = [headers[i] for i in keep]
        rows = [[(r[i] if i < len(r) else None) for i in keep] for r in rows]

        sheets.append({"name": ws.title, "headers": headers, "rows": rows})
    wb.close()
    return sheets
