"""Read actual CLI capabilities and delegate sign-in to the official client.

No credential files, login tokens, or raw model instructions enter the web API.
"""
import json
import os
import shutil
import subprocess
import threading
import tempfile
import time
import sys
import importlib.util
import importlib.metadata
from copy import deepcopy
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
from .util import require, identity, canonical, sha
from .runner import environment
from .setup import resolve_binary

_ISOLATION_CACHE={}
_ISOLATION_LOCK=threading.Lock()


def isolation_probe(binary='codex',catalog=None):
    """No-inference startup inspection of the installed CLI's native mode.

    This never redirects a Responses request or fabricates model output. Native
    debug rendering measures automatic context; the request's system/MCP text
    is measured separately. Online behavior remains unverified until real work.
    """
    from .runner import doctor,permissions,client_profile_arguments,client_profile_body,CLIENT_PROFILE_REVISION,CLIENT_SYSTEM_INSTRUCTIONS
    from . import task_tools,tasks
    executable=resolve_binary('codex',binary);require(executable,'CODEX_UNAVAILABLE','Official Codex CLI is required.')
    if catalog is None:
        p=subprocess.run([executable,'debug','models'],capture_output=True,text=True,timeout=30,env=environment())
        require(p.returncode==0 and len(p.stdout)<16*1024**2,'MODEL_CAPABILITY_UNKNOWN','Cannot inspect the installed model catalog.')
        catalog=json.loads(p.stdout)
    catalog_bytes=canonical(catalog);stat=Path(executable).stat()
    schemas=[sha(canonical({'tools':task_tools.tool_definitions(kind),'instructions':task_tools.INSTRUCTIONS})) for kind in (None,'MAIN')]
    profiles=[sha(client_profile_body(kind)) for kind in (None,'MAIN')]
    main_definitions={d['name']:d for d in task_tools.tool_definitions('MAIN')}
    require(all(main_definitions.get(d['name'])==d for d in task_tools.tool_definitions(None)),'CLIENT_INPUT_UNVERIFIED','MAIN inventory must contain the identical worker inventory.')
    config_path=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml'
    debug_config_digest=sha(config_path.read_bytes()) if config_path.is_file() else None
    key=(str(executable),stat.st_size,stat.st_mtime_ns,sha(catalog_bytes),tuple(profiles),tuple(schemas),debug_config_digest)
    with _ISOLATION_LOCK:
        if key in _ISOLATION_CACHE:return _ISOLATION_CACHE[key]
        boundary=doctor(executable)
        observed={'ready':False,'source':'installed Codex model catalog + native debug prompt-input; no model inference',
            'model_calls':0,'sandbox':boundary,'internal_delegation':True,'model_catalog_sha256':sha(catalog_bytes),
            'requested_policy':{'model':'gpt-6-astra','reasoning_effort':'ultra'},
            'resolved_client_mode':{'mode':'ultra','features.multi_agent':True,'source':'native catalog + explicit CLI configuration'},
            'observed_transport':None,'online_mode_verified':False,
            'delegation_policy':{'allowed':True,'pmrs_count_limit':None,'pmrs_concurrency_limit':None,'pmrs_depth_limit':None,'pmrs_token_limit':None}}
        with tempfile.TemporaryDirectory(prefix='pmrs-startup-') as tmp:
            work=Path(tmp)/'work';work.mkdir()
            for name in ('task.json','packet.json','prompt.md'):(work/name).write_text('{}')
            for name in ('materials','report-inputs'):(work/name).mkdir()
            profile=client_profile_arguments(Path(tmp)/'client-system.md',actor_kind='MAIN')
            row=next((r for r in catalog.get('models',[]) if r.get('slug')=='gpt-6-astra'),{})
            context=row.get('max_context_window') if row.get('supports_experimental_context') else row.get('context_window')
            require(type(context) is int and context>0,'CONTEXT_LIMIT','Installed catalog lacks a concrete context window.')
            options=permissions(executable,work,'MAIN')+profile+['-c','model="gpt-6-astra"','-c','model_reasoning_effort="ultra"','-c','model_context_window='+str(context)]
            # Debug has no ignore-user-config flag. Explicitly replace host
            # MCP inventories for this local rendering; runtime exec ignores
            # user config entirely. No credential or global config is modified.
            env=environment()
            command=[executable,'--no-daemon',*options,'-c','mcp_servers={}','debug','prompt-input',tasks.INPUT_BOOTSTRAP]
            p=subprocess.run(command,cwd=work,capture_output=True,text=True,timeout=30,env=env)
            require(p.returncode==0,'CLIENT_INPUT_UNVERIFIED','Native prompt rendering failed: '+p.stderr[-1200:])
            items=json.loads(p.stdout);require(isinstance(items,list),'CLIENT_INPUT_UNVERIFIED','Native input rendering must return message list.')
            bootstrap=tasks.INPUT_BOOTSTRAP.strip();matches=[item for item in items if item.get('role')=='user' and any(c.get('text','').strip()==bootstrap for c in item.get('content',[]))]
            require(len(matches)==1,'CLIENT_INPUT_UNVERIFIED','Native rendered bootstrap is missing.')
            wire=canonical(items);main_profile=client_profile_body('MAIN')
            # debug prompt-input omits base instructions and native tool schema.
            # Count our exact replacement instructions and explicit inventory;
            # reserve 64 KiB for the version-bound native tools/wire wrapper.
            # This is a disclosed conservative reserve, never observed transport.
            native_reserve=65536
            measured=len(wire)-len(bootstrap.encode())+len(canonical(main_profile.decode()))
            tool_bytes=len(canonical(task_tools.tool_definitions('MAIN')))
            measured+=tool_bytes+native_reserve
            occurrences=wire.decode().count(str(work));path_reserve=occurrences*max(0,512-len(str(work).encode()))
            evidence={'revision':'pmrs.client-input-evidence/2','profile_revision':CLIENT_PROFILE_REVISION,
                'system_instructions_sha256':sha(CLIENT_SYSTEM_INSTRUCTIONS.encode()),'covered_profile_sha256':profiles,
                'binary_identity':{'path':str(Path(executable).resolve()),'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns},
                'model_catalog_sha256':sha(catalog_bytes),'observed_input_sha256':sha(wire),
                'observed_non_task_input_bytes':measured,'environment_variation_reserve_bytes':path_reserve+2048,
                'observed_work_path_bytes':len(str(work).encode()),'environment_work_path_occurrences':occurrences,
                'fixed_environment_variation_reserve_bytes':2048,
                'profile_wire_bytes_by_actor':{key:len(canonical(client_profile_body(kind).decode())) for key,kind in (('WORKER',None),('MAIN','MAIN'))},
                'non_task_input_bytes':measured+path_reserve+2048,'maximum_work_path_bytes':512,
                'task_tools_included':True,'covered_tool_schema_hashes':schemas,'superset_bound':'VERIFIED_MAIN_INVENTORY_CONTAINS_WORKER_INVENTORY',
                'components':[{'type':item.get('type'),'role':item.get('role'),'bytes':len(canonical(item)),'sha256':sha(canonical(item))} for item in items],
                'native_tools_wire_reserve_bytes':native_reserve,'native_tools_measurement':'EXPLICIT_CONSERVATIVE_RESERVE_NOT_OBSERVED_TRANSPORT',
                'bootstrap_body_counted_by':'tasks.request_budget','counter':'UTF8_BYTES_CONSERVATIVE_BOUND',
                'effective_arguments':options,'debug_user_config_sha256':debug_config_digest,'runtime_user_config':'IGNORED','configured_context_window':context,'input_rendering':'NATIVE_DEBUG_PROMPT_INPUT'}
            row=next((r for r in catalog.get('models',[]) if r.get('slug')=='gpt-6-astra'),{})
            mode=any(r.get('effort')=='ultra' for r in row.get('supported_reasoning_levels',[]))
            observed.update(ready=bool(boundary['ready'] and mode),client_input_evidence=evidence,
                            unsupported_reason=None if mode else 'Installed model catalog does not advertise Astra Ultra.')
        _ISOLATION_CACHE[key]=observed;return observed


def derive_task_input_evidence(policy,store_root,task_id,actor_kind=None):
    """Derive a task bound from measured bytes and exact profile/path deltas.

    No content is dropped or estimated away.  The original MAIN observation
    remains embedded; only repeated work-path bytes and the exact registered
    worker instruction string differ. The executor validates this binding.
    """
    from .runner import client_profile_body,CLIENT_PROFILE_REVISION
    from . import task_tools
    source=policy.get('executor_contract',{}).get('client_input_evidence')
    if not source:return None
    required={'observed_non_task_input_bytes','observed_work_path_bytes','environment_work_path_occurrences',
              'fixed_environment_variation_reserve_bytes','profile_wire_bytes_by_actor'}
    if not required<=set(source):return {'client_input_evidence':deepcopy(source),'prompt_overhead_tokens':policy.get('prompt_overhead_tokens',source['non_task_input_bytes'])}
    base=source.get('observed_evidence',source)
    current_schema=sha(canonical({'tools':task_tools.tool_definitions(actor_kind),'instructions':task_tools.INSTRUCTIONS}))
    if base.get('profile_revision')!=CLIENT_PROFILE_REVISION or sha(client_profile_body(actor_kind)) not in base.get('covered_profile_sha256',[]) or current_schema not in base.get('covered_tool_schema_hashes',[]):
        # A software upgrade changes executable input bytes, not user scope,
        # grant, model policy or remaining calls. Freeze fresh no-inference
        # startup metadata in this new request; original requests stay exact.
        observed=isolation_probe(base.get('binary_identity',{}).get('path','codex'))
        require(observed.get('ready'),'CLIENT_INPUT_UNVERIFIED','Updated client startup metadata is unavailable')
        fresh=deepcopy(observed['client_input_evidence'])
        require(fresh.get('configured_context_window')==policy['executor_contract'].get('model_context_window'),'CONTEXT_LIMIT','Native context configuration changed; explicit capacity review is required')
        fresh['refresh']={'reason':'SOFTWARE_INPUT_PROFILE_CHANGED','original_authorization_input_evidence_sha256':sha(canonical(base)),'model_calls':0,'authorization_unchanged':True}
        base=fresh
    result=deepcopy(base)
    work=str((Path(store_root)/'runs'/task_id/'work').absolute())
    require(len(work.encode())<=4096 and all(c not in work for c in ('"','\\','<','>','&','\n','\r')),
            'CLIENT_INPUT_UNVERIFIED','This work path cannot use the verified linear CLI environment representation.')
    kind='MAIN' if actor_kind=='MAIN' else 'WORKER';actual_wire=len(canonical(client_profile_body(actor_kind).decode()))
    require(base['profile_wire_bytes_by_actor'].get(kind)==actual_wire,
            'CLIENT_INPUT_UNVERIFIED','Actual task system/tool instructions differ from the measured profile.')
    path_delta=base['environment_work_path_occurrences']*(len(work.encode())-base['observed_work_path_bytes'])
    profile_delta=actual_wire-base['profile_wire_bytes_by_actor']['MAIN']
    bound=base['observed_non_task_input_bytes']+path_delta+profile_delta+base['fixed_environment_variation_reserve_bytes']
    if actor_kind=='MAIN':
        from .native_main import native_binary
        _,native=native_binary()
        # Native Goal objective is limited to 4000 Unicode characters. Reserve
        # four UTF-8 bytes each plus exact turn/bootstrap/metadata framing.
        native_context_reserve=4000*4+8192
        bound+=native_context_reserve
        result['native_main_input']={'native_client':native,'automatic_goal_and_turn_reserve_bytes':native_context_reserve,
            'persistent_history':'NATIVE_RUNTIME_COMPACTION_WITHIN_CONFIGURED_CONTEXT','root_turn_admission_required':True}
    require(bound>=0,'CLIENT_INPUT_UNVERIFIED','Invalid measured input derivation.')
    result.update(non_task_input_bytes=bound,maximum_work_path_bytes=len(work.encode()),
                  expected_work_path_sha256=sha(work.encode()),expected_profile_sha256=sha(client_profile_body(actor_kind)),
                  derivation={'schema':'pmrs.task-client-input-derivation/1','observed_input_sha256':base['observed_input_sha256'],
                     'observed_non_task_input_bytes':base['observed_non_task_input_bytes'],'work_path_byte_delta':path_delta,
                     'exact_profile_wire_byte_delta':profile_delta,'fixed_environment_reserve_bytes':base['fixed_environment_variation_reserve_bytes'],
                     'actor_kind':kind,'result_bytes':bound},observed_evidence=deepcopy(base))
    return {'client_input_evidence':result,'prompt_overhead_tokens':bound}


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
    try:catalog=json.loads(p.stdout);raw=catalog['models']
    except (ValueError,KeyError):raise ValueError('Invalid Codex model catalog')
    isolation=isolation_probe(executable,catalog)
    models={}
    for row in raw:
        slug=row['slug'];window=row.get('max_context_window') if row.get('supports_experimental_context') else row.get('context_window')
        models[slug]={'reasoning_efforts':[r['effort'] for r in row.get('supported_reasoning_levels',[]) if r['effort']!='ultra' or isolation['ready']],
                     'service_tiers':['default']+[s['id'] for s in row.get('service_tiers',[])],
                     'context_window_tokens':int(window*row.get('effective_context_window_percent',100)//100) if type(window) is int else None,
                     'configured_context_window':window,'ultra_available':isolation['ready'] and any(r['effort']=='ultra' for r in row.get('supported_reasoning_levels',[]))}
    return {'source':'codex debug models + native prompt-input startup inspection','revision':identity({'models':models,'isolation':isolation}),'executor':'codex',
            'internal_delegation':True,'ultra_configuration_ready':isolation['ready'],'isolated_ultra_verified':False,'isolation_evidence':isolation,'models':models}


def policy(binary='codex',model='gpt-6-astra'):
    client=status(binary);require(client['authenticated'],'CODEX_LOGIN_REQUIRED','请在设置页面通过官方 Codex 登录，再开始研究。')
    evidence=capabilities(binary);row=evidence['models'].get(model,{})
    require(row.get('context_window_tokens'),'CONTEXT_LIMIT','模型目录未提供可验证的上下文容量。')
    # The CLI's effective context is the governing input limit. This executor
    # has no verified smaller output cap, so reserve the full published model
    # maximum rather than pretending a requested budget is enforced by the CLI.
    require(model=='gpt-6-astra','CONTEXT_LIMIT','此模型尚未登记输出容量证据；请选用已登记模型。')
    input_evidence=evidence['isolation_evidence'].get('client_input_evidence')
    require(input_evidence,'CLIENT_INPUT_UNVERIFIED','Cannot freeze unmeasured installed CLI automatic input.')
    capacity={'model_id':model,'capacity_source':'codex debug models advertised maximum context with explicit model_context_window override and effective percent; https://developers.openai.com/api/docs/models/gpt-6-astra output capacity verified 2026-10-07',
              'capacity_revision':evidence['revision'],'context_window_tokens':row['context_window_tokens'],
              'model_max_output_tokens':128000,'tokenizer_revision':'byte-BPE conservative UTF-8 byte upper bound/1',
              'tokenizer_byte_bound_verified':True,'token_count_bound':'UTF8_BYTES'}
    optional={}
    for package in ('sympy',):
        available=importlib.util.find_spec(package) is not None
        try:version=importlib.metadata.version(package) if available else None
        except importlib.metadata.PackageNotFoundError:version=None
        optional[package]={'available':available,'version':version}
    return {'model_capabilities':evidence,'capacity':capacity,'reserved_output_tokens':128000,'safety_margin_tokens':2048,
            'prompt_overhead_tokens':input_evidence['non_task_input_bytes'],
            'executor_contract':{'executor':'codex','sandbox':'required','environment_revision':client.get('version','unknown'),
              'client_input_evidence':input_evidence,'model_context_window':row['configured_context_window'],
              'requested_policy':{'model':model,'main_client_mode':'ultra'},'resolved_client_mode':evidence['isolation_evidence']['resolved_client_mode'],
              'observed_transport':None,'delegation_policy':evidence['isolation_evidence']['delegation_policy'],
              'capabilities':{'python':{'available':True,'version':sys.version.split()[0]},'optional_packages':optional,
                              'network':False,'internal_delegation':'MAIN_UNRESTRICTED_WORKER_DISABLED','internal_delegation_limits':None,'task_tools':'REQUEST_SCOPED_STDIO_PREFLIGHT_REQUIRED',
                              'source_repair_executor':False}}}


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
