# ACA AI Mapping — ACA Desktop Sales Invoice MVP

Aplikasi web untuk mengubah **Excel customer** menjadi **template Excel Sales Invoice ACA Accurate Desktop**.

Prinsip desain:

1. AI hanya membaca **nama kolom + sample baris** untuk menyarankan mapping.
2. AI tidak memproses seluruh workbook dan tidak boleh mengarang kode customer/item/master.
3. Setelah mapping disetujui user, transformasi seluruh data dikerjakan Python secara deterministic.
4. Output ditulis ke `target_template.xlsx` yang berasal dari template ACA Desktop asli.

## Target template

Sheet: `Data`

Template memiliki 57 kolom, dari `BRANCHCODE` sampai `DPINCLUSIVETAX`.

Field minimum yang divalidasi MVP:

- `INVOICENO`
- `INVOICEDATE`
- `CUSTOMERID`
- `ITEMNO`
- `QUANTITY`
- `UNITPRICE`

Daftar ini adalah aturan MVP converter dan dapat diubah di `schemas/aca_desktop_sales_invoice.json` tanpa mengubah engine.

## Fitur

- Upload `.xlsx` / `.xlsm`
- OpenAI / ChatGPT mapping
- DeepSeek mapping
- Fallback heuristic tanpa AI
- Review dan edit mapping manual
- Constant value per target field
- Preview hasil 20 baris
- Validasi field minimum
- Simpan mapping profile ke SQLite
- Download Excel hasil menggunakan template ACA Desktop
- Arsitektur schema-based agar nanti mudah menambah Purchase Invoice, Journal Voucher, dll.

## Menjalankan lokal

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Buka `http://localhost:8080`.

## Integrasi OpenAI / ChatGPT API

Buat API key OpenAI lalu isi:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.5
```

Aplikasi menggunakan official Python SDK dan **Responses API**. Provider hanya menerima header target, header source, dan sample data (default 20 baris), bukan seluruh Excel.

Model dapat diganti lewat environment variable tanpa mengubah source code.

## Integrasi DeepSeek

Isi:

```env
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

DeepSeek menyediakan API yang kompatibel dengan OpenAI SDK. Source memakai SDK `openai` yang sama dengan `base_url` DeepSeek.

## Tanpa AI

Untuk testing tanpa biaya API:

```env
AI_PROVIDER=heuristic
```

Aplikasi melakukan header matching sederhana. Mapping tetap bisa diperbaiki manual di UI.

## Railway

Upload project ini ke GitHub, lalu deploy repository ke Railway.

Variables minimum:

```env
SECRET_KEY=ganti-dengan-random-secret
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.5
MAX_SAMPLE_ROWS=20
MAX_UPLOAD_MB=25
```

atau DeepSeek:

```env
SECRET_KEY=ganti-dengan-random-secret
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
MAX_SAMPLE_ROWS=20
MAX_UPLOAD_MB=25
```

Start command:

```bash
gunicorn main:app --bind 0.0.0.0:$PORT --timeout 120
```

`Procfile` sudah disediakan.

## Flow aplikasi

```text
Excel Customer
   ↓
Read header + sample 20 row
   ↓
AI / heuristic mapping
   ↓
User review/edit mapping
   ↓
Python deterministic transform
   ↓
Validation
   ↓
Write ke target_template.xlsx
   ↓
Download ACA_Desktop_Sales_Invoice.xlsx
```

## Security / privacy notes

- Jangan commit `.env` atau API key ke GitHub.
- Pada desain ini, AI hanya menerima sample baris. Jika data customer sensitif, kurangi `MAX_SAMPLE_ROWS`, gunakan data masking, atau gunakan provider/region yang sesuai kebijakan perusahaan.
- File upload pada MVP disimpan di storage lokal/ephemeral. Untuk produksi multi-user, pindahkan file ke object storage dan tambahkan lifecycle deletion.
- SQLite cocok untuk MVP. Untuk production multi-instance, pindahkan mapping profile ke PostgreSQL.

## Menambah modul baru

Engine sudah dipisahkan menjadi:

- `schemas/` — definisi target template
- `services/ai_service.py` — provider AI
- `services/excel_service.py` — deterministic transformer
- `services/storage_service.py` — saved mapping

Untuk modul baru, buat schema + template target dan kemudian generalisasi routing agar user dapat memilih platform/module.
