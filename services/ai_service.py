from __future__ import annotations

import json
import os
import re
from openai import OpenAI

from .heuristic_service import build_heuristic_mapping


def _extract_json(text: str):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end+1]
    return json.loads(text)


def _prompt(source_headers, samples, schema):
    target = [{"name":x["name"], "description":x.get("description","")} for x in schema["target_columns"]]
    required = schema.get("required_targets", [])
    return f"""
Anda adalah engine mapping Excel untuk ACA Accurate Desktop Sales Invoice.
Tugas Anda HANYA membuat aturan mapping kolom. Jangan mengarang kode customer, kode item, akun, gudang, nilai transaksi, atau data master lain.

SOURCE HEADERS:
{json.dumps(source_headers, ensure_ascii=False)}

CONTOH DATA SOURCE (maksimal beberapa baris, hanya untuk memahami arti kolom):
{json.dumps(samples, ensure_ascii=False, default=str)}

TARGET ACA DESKTOP:
{json.dumps(target, ensure_ascii=False)}

TARGET YANG DIANGGAP WAJIB OLEH CONVERTER MVP:
{json.dumps(required, ensure_ascii=False)}

Aturan:
1. Mapping hanya ke target yang benar-benar didukung bukti dari nama header atau contoh data.
2. Jangan menebak kode master. Jika source hanya punya nama customer tetapi target butuh CUSTOMERID, boleh sarankan kolom itu dengan confidence rendah dan warning bahwa lookup master diperlukan; jangan membuat ID.
3. Untuk setiap target yang dapat dipetakan, keluarkan mode=direct, source=<nama header source persis>, confidence 0..1, reason singkat.
4. Jika target sebaiknya konstanta hanya karena format bisnis umum, JANGAN set constant otomatis. Taruh sebagai suggestion/warning saja.
5. Target yang tidak ditemukan tidak perlu dimasukkan ke target_rules.
6. Return JSON SAJA, tanpa markdown, dengan bentuk:
{{
  "target_rules": {{
    "INVOICENO": {{"mode":"direct","source":"...","confidence":0.98,"reason":"..."}}
  }},
  "notes": ["..."],
  "provider": "ai"
}}
""".strip()


def analyze_mapping(source_headers, samples, schema, provider=None):
    provider = (provider or os.getenv("AI_PROVIDER", "heuristic")).lower()
    if provider == "heuristic":
        return build_heuristic_mapping(source_headers, schema)

    prompt = _prompt(source_headers, samples, schema)

    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY belum diisi.")
        client = OpenAI(api_key=key)
        model = os.getenv("OPENAI_MODEL", "gpt-5.5")
        response = client.responses.create(
            model=model,
            instructions="Return valid JSON only. Do not invent business master data.",
            input=prompt,
        )
        data = _extract_json(response.output_text)
        data["provider"] = f"openai:{model}"
        return data

    if provider == "deepseek":
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY belum diisi.")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
        client = OpenAI(api_key=key, base_url=base_url)
        response = client.responses.create(
            model=model,
            instructions="Return valid JSON only. Do not invent business master data.",
            input=prompt,
        )
        data = _extract_json(response.output_text)
        data["provider"] = f"deepseek:{model}"
        return data

    raise ValueError(f"AI_PROVIDER tidak dikenal: {provider}")
