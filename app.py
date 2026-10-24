from __future__ import annotations
import hashlib,json,os,uuid
from functools import wraps
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for, flash
from werkzeug.utils import secure_filename
from services.ai_service import analyze_mapping
from services.excel_service import inspect_source, read_source_rows, convert_rows, validate_output, write_target, build_dynamic_schema
from services.storage_service import (
    init_db, list_profiles, save_profile, authenticate, get_user, list_users,
    create_user, extend_user, set_user_enabled, reset_user_password
)

ROOT=Path(__file__).resolve().parent
UPLOAD_DIR=ROOT/'storage'/'uploads'; OUTPUT_DIR=ROOT/'storage'/'outputs'
UPLOAD_DIR.mkdir(parents=True,exist_ok=True); OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','dev-change-me'); app.config['MAX_CONTENT_LENGTH']=int(os.getenv('MAX_UPLOAD_MB','25'))*1024*1024
init_db()

def current_user(): return get_user(session.get('user_id')) if session.get('user_id') else None

def login_required(fn):
    @wraps(fn)
    def wrapped(*a,**k):
        u=current_user()
        if not u:
            return redirect(url_for('login',next=request.path))
        if not u['subscription_active']:
            session.clear(); return redirect(url_for('login',expired='1'))
        return fn(*a,**k)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*a,**k):
        u=current_user()
        if not u: return redirect(url_for('login'))
        if not u['is_admin']: return 'Akses admin diperlukan',403
        return fn(*a,**k)
    return wrapped

@app.context_processor
def inject_user(): return {'current_user': current_user()}

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

@app.route('/login',methods=['GET','POST'])
def login():
    if current_user(): return redirect('/admin' if current_user()['is_admin'] else '/')
    error=None
    if request.method=='POST':
        user=authenticate(request.form.get('email'),request.form.get('password'))
        if not user: error='Email atau password salah.'
        elif not user['subscription_active']:
            error='Masa aktif akun sudah habis atau akun dinonaktifkan. Hubungi admin untuk perpanjangan.'
        else:
            session.clear(); session['user_id']=user['id']; return redirect('/admin' if user['is_admin'] else '/')
    if request.args.get('expired')=='1' and not error: error='Masa aktif akun sudah berakhir. Silakan hubungi admin.'
    return render_template('login.html',error=error)

@app.get('/logout')
def logout(): session.clear(); return redirect('/login')

@app.get('/')
@login_required
def index():
    u=current_user()
    return render_template('index.html',profiles=list_profiles(u['id'],u['is_admin']),default_provider=os.getenv('AI_PROVIDER','openai'))

@app.post('/analyze')
@login_required
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
@login_required
def preview():
    token=request.form.get('token',''); spath=file_token_path(token,'source'); tpath=file_token_path(token,'target')
    if not spath or not tpath: return 'File upload sudah tidak tersedia. Upload ulang.',404
    schema=build_dynamic_schema(tpath,5); mapping=mapping_from_form(request.form,schema)
    headers,rows=read_source_rows(spath); converted=convert_rows(rows,mapping,schema); issues=validate_output(converted,schema,mapping)
    profile=(request.form.get('profile_name') or '').strip(); saved_id=None; u=current_user()
    if profile: saved_id=save_profile(profile,signature(headers),mapping,{'platform':'ACA Desktop','module':'Dynamic Template'},u['id'])
    preview_rows=converted[:20]; visible=[x['name'] for x in schema['target_columns'] if any(r.get(x['name']) not in (None,'') for r in preview_rows)]
    return render_template('preview.html',token=token,source_filename=spath.name.split('_',2)[-1],target_filename=tpath.name.split('_',2)[-1],mapping_blob=json.dumps(mapping,ensure_ascii=False),rows=preview_rows,visible_targets=visible,total=len(converted),issues=issues,saved_id=saved_id,mapped_count=len(mapping.get('target_rules',{})),target_count=len(schema['target_columns']))

@app.post('/download')
@login_required
def download():
    token=request.form.get('token',''); spath=file_token_path(token,'source'); tpath=file_token_path(token,'target')
    if not spath or not tpath: return 'File upload sudah tidak tersedia. Upload ulang.',404
    schema=build_dynamic_schema(tpath,5); mapping=json.loads(request.form.get('mapping_blob') or '{}'); _,rows=read_source_rows(spath); converted=convert_rows(rows,mapping,schema); issues=validate_output(converted,schema,mapping)
    if issues: return render_template('error.html',title='Belum bisa download',message='Periksa mapping terlebih dahulu.',issues=issues),400
    out=OUTPUT_DIR/f'ACA_Mapped_{uuid.uuid4().hex[:8]}.xlsx'; write_target(tpath,out,converted,schema)
    return send_file(out,as_attachment=True,download_name='ACA_Mapped_Output.xlsx')

@app.get('/admin')
@admin_required
def admin(): return render_template('admin.html',users=list_users())

@app.post('/admin/users/create')
@admin_required
def admin_create_user():
    try:
        create_user(request.form.get('name'),request.form.get('email'),request.form.get('password'),int(request.form.get('months','1')))
        flash('User berhasil dibuat.','ok')
    except Exception as exc: flash(str(exc),'error')
    return redirect('/admin')

@app.post('/admin/users/<int:user_id>/extend')
@admin_required
def admin_extend_user(user_id):
    try:
        extend_user(user_id,int(request.form.get('months','1'))); flash('Masa aktif berhasil diperpanjang.','ok')
    except Exception as exc: flash(str(exc),'error')
    return redirect('/admin')

@app.post('/admin/users/<int:user_id>/toggle')
@admin_required
def admin_toggle_user(user_id):
    try:
        set_user_enabled(user_id,request.form.get('enabled')=='1'); flash('Status user diperbarui.','ok')
    except Exception as exc: flash(str(exc),'error')
    return redirect('/admin')

@app.post('/admin/users/<int:user_id>/password')
@admin_required
def admin_reset_password(user_id):
    try:
        reset_user_password(user_id,request.form.get('password')); flash('Password user berhasil direset.','ok')
    except Exception as exc: flash(str(exc),'error')
    return redirect('/admin')

@app.get('/health')
def health(): return jsonify({'ok':True,'app':'ACA AI Mapping','mode':'subscription'})

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','8080')),debug=True)
