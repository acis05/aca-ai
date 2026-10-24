from __future__ import annotations

import math
from copy import copy
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


def _cell_value(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    return v


def inspect_source(path: str | Path, sample_rows: int = 20):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    header_row = next(rows, None)
    if not header_row:
        raise ValueError("Excel tidak memiliki header.")

    headers = [str(x).strip() if x is not None else "" for x in header_row]
    if not any(headers):
        raise ValueError("Baris pertama Excel kosong. Gunakan baris pertama sebagai header.")
    if len(set(h for h in headers if h)) != len([h for h in headers if h]):
        raise ValueError("Nama kolom source harus unik.")

    samples = []
    for idx, row in enumerate(rows):
        if idx >= sample_rows:
            break
        samples.append({headers[i]: _cell_value(row[i]) for i in range(min(len(headers), len(row))) if headers[i]})
    wb.close()
    return headers, samples, ws.title


def read_source_rows(path: str | Path):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    header = next(it, None)
    if not header:
        wb.close()
        return [], []
    headers = [str(x).strip() if x is not None else "" for x in header]
    rows = []
    for row in it:
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        rows.append({headers[i]: row[i] for i in range(min(len(headers), len(row))) if headers[i]})
    wb.close()
    return headers, rows


def _to_bool01(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y", "ya", "t"}:
        return 1
    if s in {"0", "false", "no", "n", "tidak", "f"}:
        return 0
    return value


def _to_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value).strip()
    # Conservative parser: common Indonesian/customer formats only.
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return value


def transform_value(value: Any, rule: dict, target: str, schema: dict):
    mode = rule.get("mode", "direct")
    if mode == "constant":
        value = rule.get("constant")
    elif mode == "direct":
        pass
    elif mode == "concat":
        # concat handled at row level; kept for future extension
        pass

    normalizer = schema.get("normalizers", {}).get(target)
    if normalizer == "date":
        value = _to_date(value)
    elif normalizer == "boolean_01":
        value = _to_bool01(value)
    return value


def convert_rows(source_rows: list[dict], mapping: dict, schema: dict):
    targets = [x["name"] for x in schema["target_columns"]]
    output = []
    target_rules = mapping.get("target_rules", {})

    for row in source_rows:
        out = {t: None for t in targets}
        for target, rule in target_rules.items():
            if target not in out:
                continue
            mode = rule.get("mode", "direct")
            if mode == "constant":
                raw = rule.get("constant")
            else:
                src = rule.get("source")
                raw = row.get(src) if src else None
            out[target] = transform_value(raw, rule, target, schema)
        output.append(out)
    return output


def validate_output(rows: list[dict], schema: dict):
    required = schema.get("required_targets", [])
    issues = []
    for i, row in enumerate(rows, start=2):
        for col in required:
            v = row.get(col)
            if v is None or (isinstance(v, str) and not v.strip()):
                issues.append(f"Baris {i}: {col} kosong")
                if len(issues) >= 100:
                    return issues
    return issues


def write_target(template_path: str | Path, output_path: str | Path, rows: list[dict], schema: dict):
    wb = load_workbook(template_path)
    ws = wb[schema["sheet_name"]]
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]

    # Snapshot style from the template sample row before removing it, then reuse it
    # for every generated row. This preserves the ACA template's date/number/text style.
    style_snapshot = []
    if ws.max_row >= 2:
        for c_idx in range(1, ws.max_column + 1):
            src = ws.cell(2, c_idx)
            style_snapshot.append({
                "_style": copy(src._style),
                "number_format": src.number_format,
                "alignment": copy(src.alignment),
                "fill": copy(src.fill),
                "font": copy(src.font),
                "border": copy(src.border),
                "protection": copy(src.protection),
            })

    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)

    for r_idx, row in enumerate(rows, start=2):
        for c_idx, header in enumerate(headers, start=1):
            cell = ws.cell(r_idx, c_idx, row.get(header))
            if c_idx <= len(style_snapshot):
                st = style_snapshot[c_idx-1]
                cell._style = copy(st["_style"])
                cell.number_format = st["number_format"]
                cell.alignment = copy(st["alignment"])
                cell.fill = copy(st["fill"])
                cell.font = copy(st["font"])
                cell.border = copy(st["border"])
                cell.protection = copy(st["protection"])

    date_targets = {"INVOICEDATE", "SHIPDATE"}
    for header in date_targets:
        if header in headers:
            c_idx = headers.index(header) + 1
            for r_idx in range(2, 2 + len(rows)):
                ws.cell(r_idx, c_idx).number_format = "dd/mm/yyyy"

    wb.save(output_path)
