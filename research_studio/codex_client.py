"""Read actual CLI capabilities and delegate sign-in to the official client.

No credential files, login tokens, or raw model instructions enter the web API.
"""
import json
import shutil
import subprocess
import threading
from .util import require, identity
from .runner import environment
from .setup import resolve_binary


def status(binary='codex'):
    executable=resolve_binary('codex',binary)
    if not executable:return {'installed':False,'authenticated':False,'model_calls':0}
    try:
        version=subprocess.run([executable,'--version'],capture_output=True,text=True,timeout=10,env=environment())
        auth=subprocess.run([executable,'login','status'],capture_output=True,text=True,timeout=10,env=environment())
        return {'installed':True,'version':version.stdout.strip()[:100],
                'authenticated':auth.returncode==0,'model_calls':0}
    except (OSError,subprocess.TimeoutExpired):
        return {'installed':True,'authenticated':False,'error':'CLIENT_UNAVAILABLE','model_calls':0}


def capabilities(binary='codex'):
    executable=resolve_binary('codex',binary);require(executable,'CODEX_UNAVAILABLE','请先安装官方 Codex CLI，然后重新检查。')
    p=subprocess.run([executable,'debug','models'],capture_output=True,text=True,timeout=30,env=environment())
    require(p.returncode==0 and len(p.stdout)<16*1024**2,'MODEL_CAPABILITY_UNKNOWN','无法读取客户端模型目录，请检查登录与网络后重试。')
    try:raw=json.loads(p.stdout)['models']
    except (ValueError,KeyError):raise ValueError('Invalid Codex model catalog')
    models={}
    for row in raw:
        slug=row['slug'];window=row.get('context_window')
        models[slug]={'reasoning_efforts':[r['effort'] for r in row.get('supported_reasoning_levels',[]) if r['effort']!='ultra'],
                     'service_tiers':['default']+[s['id'] for s in row.get('service_tiers',[])],
                     'context_window_tokens':int(window*row.get('effective_context_window_percent',100)//100) if type(window) is int else None,
                     'ultra_available':False}
    return {'source':'codex debug models','revision':identity(models),'executor':'codex',
            'internal_delegation':False,'isolated_ultra_verified':False,'models':models}


def policy(binary='codex',model='gpt-6-astra'):
    client=status(binary);require(client['authenticated'],'CODEX_LOGIN_REQUIRED','请在设置页面通过官方 Codex 登录，再开始研究。')
    evidence=capabilities(binary);row=evidence['models'].get(model,{})
    require(row.get('context_window_tokens'),'CONTEXT_LIMIT','模型目录未提供可验证的上下文容量。')
    # The CLI's effective context is the governing input limit. This executor
    # has no verified smaller output cap, so reserve the full published model
    # maximum rather than pretending a requested budget is enforced by the CLI.
    require(model=='gpt-6-astra','CONTEXT_LIMIT','此模型尚未登记输出容量证据；请选用已登记模型。')
    capacity={'model_id':model,'capacity_source':'codex debug models effective context; https://developers.openai.com/api/docs/models/gpt-6-astra output capacity verified 2026-10-07',
              'capacity_revision':evidence['revision'],'context_window_tokens':row['context_window_tokens'],
              'model_max_output_tokens':128000,'tokenizer_revision':'byte-BPE conservative UTF-8 byte upper bound/1',
              'tokenizer_byte_bound_verified':True,'token_count_bound':'UTF8_BYTES'}
    return {'model_capabilities':evidence,'capacity':capacity,'reserved_output_tokens':128000,'safety_margin_tokens':2048,
            'executor_contract':{'executor':'codex','sandbox':'required','environment_revision':client.get('version','unknown')}}


class Login:
    """Background official browser login; output is never exposed or persisted."""
    def __init__(self,binary='codex'):
        self.binary=binary;self.process=None;self.lock=threading.Lock();self.result=None
    def start(self):
        with self.lock:
            current=status(self.binary)
            if current['authenticated']:return {**current,'login_state':'ALREADY_AUTHENTICATED'}
            require(current['installed'],'CODEX_UNAVAILABLE','请安装官方客户端后重新检查。')
            if self.process and self.process.poll() is None:return {'login_state':'WAITING_FOR_OFFICIAL_LOGIN'}
            self.process=subprocess.Popen([resolve_binary('codex',self.binary),'login'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                          stdin=subprocess.DEVNULL,env=environment(),start_new_session=True)
            return {'login_state':'WAITING_FOR_OFFICIAL_LOGIN','model_calls':0}
    def inspect(self):
        current=status(self.binary)
        current['login_state']='AUTHENTICATED' if current['authenticated'] else ('WAITING_FOR_OFFICIAL_LOGIN' if self.process and self.process.poll() is None else 'LOGIN_REQUIRED')
        return current
