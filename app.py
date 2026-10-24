from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from services.ai_service import analyze_mapping
from services.excel_service import inspect_source, read_source_rows, convert_rows, validate_output, write_target
from services.schema_service import load_schema
from services.storage_service import init_db, list_profiles, save_profile, get_profile

ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / "storage" / "uploads"
OUTPUT_DIR = ROOT / "storage" / "outputs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-change-me")
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
init_db()


def file_token_path(token):
    matches = list(UPLOAD_DIR.glob(f"{token}_*"))
    return matches[0] if matches else None


def source_signature(headers):
    return hashlib.sha256("|".join(headers).encode("utf-8")).hexdigest()[:16]


def mapping_from_form(form, schema):
    rules = {}
    for target in [x["name"] for x in schema["target_columns"]]:
        src = (form.get(f"map__{target}") or "").strip()
        constant = (form.get(f"const__{target}") or "").strip()
        if constant:
            rules[target] = {"mode":"constant", "constant":constant, "confidence":1.0, "reason":"manual constant"}
        elif src:
            rules[target] = {"mode":"direct", "source":src, "confidence":1.0, "reason":"manual/approved mapping"}
    return {"target_rules": rules, "notes": [], "provider":"manual-approved"}


@app.get("/")
def index():
    schema = load_schema()
    return render_template("index.html", schema=schema, profiles=list_profiles(), default_provider=os.getenv("AI_PROVIDER","openai"))


@app.post("/analyze")
def analyze():
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect(url_for("index"))
    if not f.filename.lower().endswith((".xlsx", ".xlsm")):
        return "Gunakan file .xlsx atau .xlsm", 400

    token = uuid.uuid4().hex
    filename = secure_filename(f.filename) or "source.xlsx"
    path = UPLOAD_DIR / f"{token}_{filename}"
    f.save(path)

    schema = load_schema()
    sample_rows = int(os.getenv("MAX_SAMPLE_ROWS", "20"))
    headers, samples, source_sheet = inspect_source(path, sample_rows)
    provider = (request.form.get("provider") or os.getenv("AI_PROVIDER","heuristic")).lower()

    try:
        mapping = analyze_mapping(headers, samples, schema, provider=provider)
        ai_error = None
    except Exception as exc:
        # Fail safe: app remains usable even when AI key/quota/provider has problems.
        from services.heuristic_service import build_heuristic_mapping
        mapping = build_heuristic_mapping(headers, schema)
        ai_error = str(exc)

    return render_template(
        "mapping.html",
        schema=schema,
        headers=headers,
        samples=samples[:5],
        mapping=mapping,
        token=token,
        filename=filename,
        source_sheet=source_sheet,
        signature=source_signature(headers),
        ai_error=ai_error,
    )


@app.post("/preview")
def preview():
    schema = load_schema()
    token = request.form.get("token", "")
    path = file_token_path(token)
    if not path:
        return "File upload sudah tidak tersedia. Upload ulang file.", 404

    mapping = mapping_from_form(request.form, schema)
    headers, source_rows = read_source_rows(path)
    converted = convert_rows(source_rows, mapping, schema)
    issues = validate_output(converted, schema)
    profile_name = (request.form.get("profile_name") or "").strip()
    saved_id = None
    if profile_name:
        saved_id = save_profile(profile_name, source_signature(headers), mapping, schema)

    preview_rows = converted[:20]
    visible_targets = [x["name"] for x in schema["target_columns"] if any(r.get(x["name"]) not in (None, "") for r in preview_rows)]
    for req in schema.get("required_targets", []):
        if req not in visible_targets:
            visible_targets.append(req)

    mapping_blob = json.dumps(mapping, ensure_ascii=False)
    return render_template(
        "preview.html",
        schema=schema,
        token=token,
        filename=path.name.split("_",1)[-1],
        mapping_blob=mapping_blob,
        rows=preview_rows,
        visible_targets=visible_targets,
        total=len(converted),
        issues=issues,
        saved_id=saved_id,
    )


@app.post("/download")
def download():
    schema = load_schema()
    token = request.form.get("token", "")
    path = file_token_path(token)
    if not path:
        return "File upload sudah tidak tersedia. Upload ulang file.", 404

    mapping = json.loads(request.form.get("mapping_blob") or "{}")
    _, source_rows = read_source_rows(path)
    converted = convert_rows(source_rows, mapping, schema)
    issues = validate_output(converted, schema)
    if issues:
        return render_template("error.html", title="Belum bisa download", message="Perbaiki mapping field wajib terlebih dahulu.", issues=issues), 400

    out = OUTPUT_DIR / f"ACA_Desktop_Sales_Invoice_{uuid.uuid4().hex[:8]}.xlsx"
    write_target(ROOT / schema["template_file"], out, converted, schema)
    return send_file(out, as_attachment=True, download_name="ACA_Desktop_Sales_Invoice.xlsx")


@app.get("/api/schema")
def api_schema():
    return jsonify(load_schema())


@app.get("/health")
def health():
    return jsonify({"ok":True, "app":"ACA AI Mapping", "module":"ACA Desktop Sales Invoice"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=True)
