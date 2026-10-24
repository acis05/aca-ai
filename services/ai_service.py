from __future__ import annotations
import json,os,re
from openai import OpenAI
from .heuristic_service import build_heuristic_mapping

def _extract_json(text):
    text=(text or '').strip(); text=re.sub(r'^```(?:json)?\s*','',text); text=re.sub(r'\s*```$','',text)
    s=text.find('{'); e=text.rfind('}')
    if s>=0 and e>s: text=text[s:e+1]
    return json.loads(text)

def _prompt(source_headers,source_samples,schema):
    targets=[{'name':x['name'],'description':x.get('description','')} for x in schema['target_columns']]
    return f'''Anda adalah engine mapping Excel untuk ACA AI Mapping.
Tugas: petakan Excel SUMBER ke Excel TARGET ACA berdasarkan nama kolom dan contoh data.
AI hanya membuat aturan mapping, bukan mengubah seluruh file dan tidak boleh mengarang kode/data master.

SOURCE HEADERS:\n{json.dumps(source_headers,ensure_ascii=False)}
SOURCE SAMPLE:\n{json.dumps(source_samples,ensure_ascii=False,default=str)}
TARGET HEADERS + CONTOH:\n{json.dumps(targets,ensure_ascii=False)}
TARGET SAMPLE DARI TEMPLATE ACA:\n{json.dumps(schema.get('target_samples',[]),ensure_ascii=False,default=str)}

Aturan:
1. Gunakan nama header SOURCE persis pada field source.
2. Jangan mengarang customer/item/account/warehouse code.
3. Jika tidak yakin, jangan paksa mapping dan tulis catatan.
4. Return JSON saja:
{{"target_rules":{{"TARGET":{{"mode":"direct","source":"SOURCE","confidence":0.95,"reason":"..."}}}},"notes":["..."],"provider":"ai"}}
'''

def analyze_mapping(source_headers,samples,schema,provider=None):
    provider=(provider or os.getenv('AI_PROVIDER','heuristic')).lower()
    if provider=='heuristic': return build_heuristic_mapping(source_headers,schema)
    prompt=_prompt(source_headers,samples,schema)
    if provider=='openai':
        key=os.getenv('OPENAI_API_KEY')
        if not key: raise RuntimeError('OPENAI_API_KEY belum diisi.')
        model=os.getenv('OPENAI_MODEL','gpt-6-luna'); client=OpenAI(api_key=key)
        response=client.responses.create(model=model,reasoning={'effort':os.getenv('OPENAI_REASONING_EFFORT','low')},instructions='Return valid JSON only. Do not invent business data.',input=prompt)
        data=_extract_json(response.output_text); data['provider']=f'openai:{model}'; return data
    if provider=='deepseek':
        key=os.getenv('DEEPSEEK_API_KEY')
        if not key: raise RuntimeError('DEEPSEEK_API_KEY belum diisi.')
        model=os.getenv('DEEPSEEK_MODEL','deepseek-chat'); client=OpenAI(api_key=key,base_url=os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com'))
        response=client.chat.completions.create(model=model,messages=[{'role':'system','content':'Return valid JSON only. Do not invent business data.'},{'role':'user','content':prompt}],temperature=0)
        data=_extract_json(response.choices[0].message.content); data['provider']=f'deepseek:{model}'; return data
    raise ValueError(f'AI_PROVIDER tidak dikenal: {provider}')
