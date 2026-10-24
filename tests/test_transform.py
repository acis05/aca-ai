from pathlib import Path
from services.excel_service import build_dynamic_schema, convert_rows, validate_output

ROOT = Path(__file__).resolve().parents[1]

def test_dynamic_schema_from_uploaded_style_template():
    schema = build_dynamic_schema(ROOT / 'target_template.xlsx', 3)
    names = [x['name'] for x in schema['target_columns']]
    assert 'INVOICENO' in names
    assert 'INVOICEDATE' in names
    assert len(names) > 10

def test_basic_direct_mapping():
    schema = build_dynamic_schema(ROOT / 'target_template.xlsx', 3)
    source = [{'Invoice':'INV-001','Tanggal':'24/10/2026','Cust':'C-001','SKU':'IT-001','Qty':2,'Harga':50000}]
    mapping = {'target_rules': {
        'INVOICENO':{'mode':'direct','source':'Invoice'},
        'INVOICEDATE':{'mode':'direct','source':'Tanggal'},
        'CUSTOMERID':{'mode':'direct','source':'Cust'},
        'ITEMNO':{'mode':'direct','source':'SKU'},
        'QUANTITY':{'mode':'direct','source':'Qty'},
        'UNITPRICE':{'mode':'direct','source':'Harga'},
    }}
    rows = convert_rows(source, mapping, schema)
    assert rows[0]['INVOICENO'] == 'INV-001'
    assert rows[0]['CUSTOMERID'] == 'C-001'
    assert rows[0]['QUANTITY'] == 2
    assert validate_output(rows, schema) == []
