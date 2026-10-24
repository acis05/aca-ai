import re

COMMON_ALIASES = {
    'INVOICENO':['invoice no','invoice number','no invoice','nomor invoice','no faktur','nomor faktur','inv no'],
    'INVOICEDATE':['invoice date','tanggal invoice','tgl invoice','tanggal faktur','tgl faktur'],
    'CUSTOMERID':['customer id','customer code','cust code','kode customer','kode pelanggan','customer no'],
    'ITEMNO':['item no','item code','kode item','kode barang','sku','product code'],
    'QUANTITY':['quantity','qty','jumlah','kuantitas'],
    'UNITPRICE':['unit price','price','harga','harga satuan','selling price'],
    'WAREHOUSEID':['warehouse','warehouse id','gudang','kode gudang'],
}

def norm(s): return re.sub(r'[^a-z0-9]+',' ',str(s).lower()).strip()

def build_heuristic_mapping(source_headers,schema):
    normalized={h:norm(h) for h in source_headers}; rules={}; notes=[]
    for col in schema['target_columns']:
        target=col['name']; aliases=[norm(target)]+[norm(x) for x in COMMON_ALIASES.get(target.upper(),[])]
        best=None; score=0
        for h,nh in normalized.items():
            s=1.0 if nh in aliases else (0.76 if any(a and (a in nh or nh in a) for a in aliases) else 0)
            if s>score: best,score=h,s
        if best: rules[target]={'mode':'direct','source':best,'confidence':score,'reason':'heuristic header match'}
    if not rules: notes.append('Belum ada mapping otomatis yang cukup yakin. Pilih mapping secara manual atau gunakan AI.')
    return {'target_rules':rules,'notes':notes,'provider':'heuristic'}
