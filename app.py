from __future__ import annotations
import hashlib,json,os,uuid
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename
from services.ai_service import analyze_mapping
from services.excel_service import inspect_source, read_source_rows, convert_rows, validate_output, write_target, build_dynamic_schema
from services.storage_service import init_db, list_profiles, save_profile

ROOT=Path(__file__).resolve().parent
UPLOAD_DIR=ROOT/'storage'/'uploads'; OUTPUT_DIR=ROOT/'storage'/'outputs'
UPLOAD_DIR.mkdir(parents=True,exist_ok=True); OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','dev-change-me'); app.config['MAX_CONTENT_LENGTH']=int(os.getenv('MAX_UPLOAD_MB','25'))*1024*1024
init_db()

def file_token_path(token,prefix):
    matches=list(UPLOAD_DIR.glob(f'{prefix}_{token}_*')); return matches[0] if matches else None

def signature(headers): return hashlib.sha256('|'.join(headers).encode()).hexdigest()[:16]

def mapping_from_form(form,schema):
    rules={}
    for target in [x['name'] for x in schema['target_columns']]:
        src=(form.get(f'map__{target}') or '').strip(); const=(form.get(f'const__{target}') or '').strip()
        if const: rules[target]={'mode':'constant','constant':const,'confidence':1.0,'reason':'manual constant'}
        elif src: rules[target]={'mode':'direct','source':src,'confidence':1.0,'reason':'manual/approved mapping'}
    return {'target_rules':rules,'notes':[],'provider':'manual-approved'}

@app.get('/')
def index():
    return render_template('index.html',profiles=list_profiles(),default_provider=os.getenv('AI_PROVIDER','openai'))

@app.post('/analyze')
def analyze():
    source=request.files.get('source_file'); target=request.files.get('target_file')
    if not source or not source.filename or not target or not target.filename: return 'Upload Excel sumber dan Excel target ACA.',400
    for f in (source,target):
        if not f.filename.lower().endswith(('.xlsx','.xlsm')): return 'Gunakan file .xlsx atau .xlsm',400
    token=uuid.uuid4().hex
    sname=secure_filename(source.filename) or 'source.xlsx'; tname=secure_filename(target.filename) or 'target.xlsx'
    spath=UPLOAD_DIR/f'source_{token}_{sname}'; tpath=UPLOAD_DIR/f'target_{token}_{tname}'
    source.save(spath); target.save(tpath)
    samples=int(os.getenv('MAX_SAMPLE_ROWS','20'))
    headers,source_samples,source_sheet=inspect_source(spath,samples)
    schema=build_dynamic_schema(tpath,5)
    provider=(request.form.get('provider') or os.getenv('AI_PROVIDER','heuristic')).lower()
    try: mapping=analyze_mapping(headers,source_samples,schema,provider=provider); ai_error=None
    except Exception as exc:
        from services.heuristic_service import build_heuristic_mapping
        mapping=build_heuristic_mapping(headers,schema); ai_error=str(exc)
    return render_template('mapping.html',schema=schema,headers=headers,samples=source_samples[:5],target_samples=schema.get('target_samples',[])[:3],mapping=mapping,token=token,filename=sname,target_filename=tname,source_sheet=source_sheet,target_sheet=schema['sheet_name'],source_signature=signature(headers),target_signature=signature([x['name'] for x in schema['target_columns']]),ai_error=ai_error)

@app.post('/preview')
def preview():
    token=request.form.get('token',''); spath=file_token_path(token,'source'); tpath=file_token_path(token,'target')
    if not spath or not tpath: return 'File upload sudah tidak tersedia. Upload ulang.',404
    schema=build_dynamic_schema(tpath,5); mapping=mapping_from_form(request.form,schema)
    headers,rows=read_source_rows(spath); converted=convert_rows(rows,mapping,schema); issues=validate_output(converted,schema)
    profile=(request.form.get('profile_name') or '').strip(); saved_id=None
    if profile: saved_id=save_profile(profile,signature(headers),mapping,{'platform':'ACA Desktop','module':'Dynamic Template'})
    preview_rows=converted[:20]; visible=[x['name'] for x in schema['target_columns'] if any(r.get(x['name']) not in (None,'') for r in preview_rows)]
    return render_template('preview.html',token=token,source_filename=spath.name.split('_',2)[-1],target_filename=tpath.name.split('_',2)[-1],mapping_blob=json.dumps(mapping,ensure_ascii=False),rows=preview_rows,visible_targets=visible,total=len(converted),issues=issues,saved_id=saved_id,mapped_count=len(mapping.get('target_rules',{})),target_count=len(schema['target_columns']))

@app.post('/download')
def download():
    token=request.form.get('token',''); spath=file_token_path(token,'source'); tpath=file_token_path(token,'target')
    if not spath or not tpath: return 'File upload sudah tidak tersedia. Upload ulang.',404
    schema=build_dynamic_schema(tpath,5); mapping=json.loads(request.form.get('mapping_blob') or '{}'); _,rows=read_source_rows(spath); converted=convert_rows(rows,mapping,schema); issues=validate_output(converted,schema)
    if issues: return render_template('error.html',title='Belum bisa download',message='Periksa mapping terlebih dahulu.',issues=issues),400
    out=OUTPUT_DIR/f'ACA_Mapped_{uuid.uuid4().hex[:8]}.xlsx'; write_target(tpath,out,converted,schema)
    return send_file(out,as_attachment=True,download_name='ACA_Mapped_Output.xlsx')

@app.get('/health')
def health(): return jsonify({'ok':True,'app':'ACA AI Mapping','mode':'dynamic-target-template'})

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','8080')),debug=True)
