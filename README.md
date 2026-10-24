# ACA AI Mapping — Flexible Excel Mapper

MVP untuk mengubah Excel sumber/customer agar mengikuti **format Excel ACA yang di-upload user**.

## Flow
1. Upload **Format Excel ACA Default** (.xlsx/.xlsm).
2. Upload **Excel Data Sumber**.
3. Klik **Jalankan Mapping**.
4. AI membaca header + sample source dan header + sample target.
5. Review/koreksi mapping.
6. Preview hasil.
7. Download output. Workbook target yang di-upload dipakai sebagai dasar sehingga urutan kolom dan style tetap dipertahankan.

AI hanya menghasilkan aturan mapping. Semua row ditransformasi oleh Python, bukan oleh AI.

## OpenAI GPT-6 Luna
Railway Variables:
```env
SECRET_KEY=your-long-secret
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-6-luna
OPENAI_REASONING_EFFORT=low
MAX_SAMPLE_ROWS=20
MAX_UPLOAD_MB=25
```

## DeepSeek
```env
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

## Tanpa AI
```env
AI_PROVIDER=heuristic
```

## Railway
Start command:
```bash
gunicorn main:app --bind 0.0.0.0:$PORT --timeout 120
```

## Catatan template ACA
- Header target diasumsikan berada di baris pertama sheet pertama.
- Output mempertahankan workbook target, sheet, urutan kolom, width/style/formula/header lain sejauh tidak berada pada data rows yang diganti.
- Row 2 dipakai sebagai style sample untuk data hasil mapping.
- Jika template target berisi contoh data, data dari row 2 ke bawah akan dihapus ketika output dibuat.

## Pengembangan berikutnya
Engine ini sudah tidak hard-coded ke 57 field Sales Invoice, sehingga dapat dipakai sebagai dasar untuk modul ACA Desktop lain dengan cara cukup upload target template yang berbeda. Untuk production berikutnya disarankan menambah: pemilihan sheet, multi-row header, transformation rules, lookup master, dan mapping profile berdasarkan signature target + source.
