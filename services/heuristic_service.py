import re

ALIASES = {
    "INVOICENO": ["invoice no","invoice number","no invoice","nomor invoice","no faktur","nomor faktur","invoice","inv no"],
    "INVOICEDATE": ["invoice date","tanggal invoice","tgl invoice","tanggal faktur","tgl faktur","date"],
    "CUSTOMERID": ["customer id","customer code","cust code","kode customer","kode pelanggan","customer no","cust no"],
    "CURRENCYNAME": ["currency","currency name","mata uang","currency code"],
    "RATE": ["rate","kurs","exchange rate"],
    "DESCRIPTION": ["description","desc","keterangan","catatan","notes"],
    "WAREHOUSEID": ["warehouse","warehouse id","gudang","kode gudang"],
    "PURCHASEORDERNO": ["po no","po number","purchase order","customer po","nomor po"],
    "TERMSID": ["term","terms","payment term","syarat pembayaran"],
    "SHIPDATE": ["ship date","delivery date","tanggal kirim","tgl kirim"],
    "ITEMNO": ["item no","item code","kode item","kode barang","sku","product code","product id"],
    "QUANTITY": ["quantity","qty","jumlah","kuantitas"],
    "ITEMUNIT": ["unit","uom","satuan","item unit"],
    "UNITPRICE": ["unit price","price","harga","harga satuan","selling price"],
    "ITEMOVDESC": ["item description","product name","nama barang","nama item","item desc"],
    "ITEMDISCPC": ["item discount","discount item","disc item","diskon item","item disc %"],
    "TAXCODES": ["tax code","tax codes","kode pajak","pajak"],
    "PROJECTID": ["project","project id","kode project"],
    "DEPTID": ["department","department id","dept","kode departemen"],
    "SOID": ["sales order","so no","sales order no"],
    "DOID": ["delivery order","do no","delivery order no"],
    "TAXNO": ["tax no","tax number","nomor pajak","no faktur pajak"],
    "BRANCHCODE": ["branch","branch code","kode cabang","cabang"],
}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def build_heuristic_mapping(source_headers, schema):
    normalized = {h: norm(h) for h in source_headers}
    rules = {}
    notes = []
    for target in [x["name"] for x in schema["target_columns"]]:
        aliases = [norm(target)] + [norm(x) for x in ALIASES.get(target, [])]
        best = None
        best_score = 0
        for h, nh in normalized.items():
            score = 0
            if nh in aliases:
                score = 1.0
            elif any(a and (a in nh or nh in a) for a in aliases):
                score = 0.78
            if score > best_score:
                best, best_score = h, score
        if best:
            rules[target] = {"mode":"direct","source":best,"confidence":best_score,"reason":"heuristic header match"}
    for req in schema.get("required_targets", []):
        if req not in rules:
            notes.append(f"Field wajib {req} belum ditemukan otomatis.")
    return {"target_rules": rules, "notes": notes, "provider": "heuristic"}
