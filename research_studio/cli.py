"""Advanced CLI over the same application services as the local web workspace."""
import argparse
import json
import sys
from pathlib import Path
from . import __version__
from .util import PMRSError,loads,read,require
from .store import Store
from .engine import Engine


def parser():
    p=argparse.ArgumentParser(prog='pure-math-research-studio',description='PMRS：桌面网页工作区与共享研究内核。')
    p.add_argument('--version',action='version',version=__version__)
    sub=p.add_subparsers(dest='command',required=True)
    desktop=sub.add_parser('desktop',help='打开桌面网页工作区');desktop.add_argument('--workspace',type=Path);desktop.add_argument('--no-browser',action='store_true')
    project=sub.add_parser('project');ps=project.add_subparsers(dest='operation',required=True)
    init=ps.add_parser('init');init.add_argument('--out',type=Path,required=True);init.add_argument('--problem',type=Path,required=True);init.add_argument('--title',default='Mathematical research');init.add_argument('--phenomenon',action='store_true')
    q=ps.add_parser('restore');q.add_argument('source',type=Path);q.add_argument('--out',type=Path,required=True)
    ex=ps.add_parser('export');ex.add_argument('project',type=Path);ex.add_argument('--out',type=Path,required=True)
    wf=sub.add_parser('workflow');ws=wf.add_subparsers(dest='operation',required=True)
    for name in ('new','list','configure-discovery'):
        q=ws.add_parser(name);q.add_argument('project',type=Path)
        if name=='new':q.add_argument('--kind',choices=['TRW','TFDW','SURVEY'],required=True);q.add_argument('--name');q.add_argument('--target');q.add_argument('--target-text',type=Path);q.add_argument('--survey-scope',type=Path)
        if name=='configure-discovery':q.add_argument('--instance',required=True)
        if name!='list':q.add_argument('--brief',type=Path);q.add_argument('--immutable-background',type=Path);q.add_argument('--allowed-axes',type=Path)
    kn=sub.add_parser('knowledge');ks=kn.add_subparsers(dest='operation',required=True)
    for name in ('current','frontier','diff','sources'):
        q=ks.add_parser(name);q.add_argument('project',type=Path);q.add_argument('--instance');q.add_argument('--commit')
        if name=='current':q.add_argument('--query');q.add_argument('--offset',type=int,default=0);q.add_argument('--limit',type=int,default=25)
        if name=='diff':q.add_argument('--from',dest='from_commit',required=True)
    survey=sub.add_parser('survey',help='Scoped literature survey and optional English manuscript')
    ss=survey.add_subparsers(dest='operation',required=True)
    new=ss.add_parser('init');new.add_argument('--out',type=Path,required=True);new.add_argument('--scope',type=Path,required=True);new.add_argument('--title',default='Literature survey')
    for name in ('status','activity','retrieve','freeze','plan','source-status'):
        q=ss.add_parser(name);q.add_argument('project',type=Path);q.add_argument('--instance',required=True)
        if name=='activity':
            q.add_argument('--stage',choices=['S1','S2','S3','S4','S5'],required=True);q.add_argument('--intent',required=True)
            q.add_argument('--max-calls',type=int,required=True);q.add_argument('--max-workers',type=int,default=1);q.add_argument('--model-overrides',type=Path)
            q.add_argument('--allow-reports',action='store_true',default=None)
            q.add_argument('--selected-refs',type=Path);q.add_argument('--source-refs',type=Path);q.add_argument('--role')
        if name=='retrieve':q.add_argument('--plan-ref',required=True)
        if name=='freeze':q.add_argument('--selected-refs',type=Path);q.add_argument('--question-ids',type=Path)
        if name=='source-status':
            q.add_argument('--source-ref',required=True);q.add_argument('--withdrawn',action='store_true');q.add_argument('--version-conflict',action='store_true');q.add_argument('--reason',required=True)
        if name=='plan':
            q.add_argument('--snapshot-ref',required=True);q.add_argument('--profile',choices=['minimal','thematic','lecture'],required=True)
            q.add_argument('--settings',type=Path)
    hf=sub.add_parser('handoff');hs=hf.add_subparsers(dest='operation',required=True)
    for name in ('prepare','adopt'):
        q=hs.add_parser(name);q.add_argument('project',type=Path);q.add_argument('--instance',required=True)
        if name=='prepare':q.add_argument('--direction',choices=['TRW_TO_TFDW','TFDW_TO_TRW','SURVEY_TO_TRW','SURVEY_TO_TFDW'],required=True);q.add_argument('--scope',type=Path,required=True)
        else:q.add_argument('--handoff',required=True);q.add_argument('--decision',type=Path,required=True)
    for name in ('status','audit','rebuild-index','orphans','schedule','prepare','run','pause','decide','resume','report','source','preflight','recover','cancel','reconcile','authorize','start','configure','ui'):
        q=sub.add_parser(name);q.add_argument('project',type=Path)
        if name not in {'audit','rebuild-index','orphans','source','preflight','recover','ui'}:q.add_argument('--instance',required=name not in {'status'})
        if name=='authorize':q.add_argument('--mission',type=Path,required=True);q.add_argument('--budget',type=Path,required=True)
        if name=='start':q.add_argument('--intent',required=True);q.add_argument('--max-calls',type=int,required=True);q.add_argument('--max-workers',type=int,default=1);q.add_argument('--model-overrides',type=Path)
        if name=='configure':q.add_argument('--model-overrides',type=Path);q.add_argument('--reset-scopes',type=Path);q.add_argument('--reason',default='Explicit future task configuration')
        if name=='pause':q.add_argument('--reason',required=True)
        if name=='decide':
            q.add_argument('--action',required=True);q.add_argument('--note',required=True);q.add_argument('--snapshot',required=True);q.add_argument('--candidate');q.add_argument('--report-ref')
        if name=='resume':q.add_argument('--decision',required=True)
        if name=='run':q.add_argument('--max-tasks',type=int,default=32)
        if name=='report':q.add_argument('--check-only',action='store_true');q.add_argument('--prepare-only',action='store_true');q.add_argument('--render-only',action='store_true');q.add_argument('--profile',choices=['lecture','minimal','thematic']);q.add_argument('--plan-ref')
        if name=='source':q.add_argument('--file',type=Path,required=True);q.add_argument('--media-type',default='application/octet-stream')
        if name=='preflight':q.add_argument('--task',required=True);q.add_argument('--response',type=Path,required=True)
        if name in {'recover','cancel','reconcile'}:q.add_argument('--request',required=True)
        if name=='recover':q.add_argument('--check-only',action='store_true')
        if name in {'cancel','reconcile'}:q.add_argument('--reason',required=True)
        if name=='reconcile':q.add_argument('--disposition',required=True,choices=['CONFIRMED_NOT_SENT','ABANDON_UNKNOWN']);q.add_argument('--not-sent-evidence',help='已保存的实际传输证据 source_ref；不能用说明文字代替。')
        if name=='ui':q.add_argument('--port',type=int,default=8765)
    doctor=sub.add_parser('doctor');doctor.add_argument('--codex-binary',default='codex')
    sub.add_parser('model-policy');sub.add_parser('capabilities')
    return p


def execute(a):
    e=Engine();cmd=a.command
    if cmd=='desktop':
        from .desktop import launch,default_workspace
        r=launch(a.workspace or default_workspace(),open_browser=not a.no_browser)
        return {'started':True,'pid':r['pid'],'model_calls':0}
    if cmd=='doctor':
        from .runner import doctor
        from .render import doctor as pdf_doctor
        from .codex_client import status
        return {'client':status(a.codex_binary),'execution':doctor(a.codex_binary),'pdf':pdf_doctor(),'model_calls':0}
    if cmd=='model-policy':
        from .model_policy import describe
        return describe()
    if cmd=='capabilities':
        from .codex_client import capabilities
        return capabilities()
    if cmd=='project':
        if a.operation=='init':
            store=e.create(a.out,read(a.problem),title=a.title,phenomenon=a.phenomenon)
            return {'path':str(store.root),'project_id':store.read_snapshot()['project_id'],'model_calls':0}
        from . import portability
        if a.operation=='restore':return portability.restore(a.source,a.out)
        return portability.export_project(Store(a.project),a.out)
    if cmd=='survey' and a.operation=='init':
        e.create_survey(a.out,loads(read(a.scope)),title=a.title)
        state=Store(a.out).read_snapshot()
        return {'path':str(a.out),'instance_id':next(iter(state['instances'])),'project_id':state['project_id'],'model_calls':0}
    store=Store(a.project)
    if cmd=='survey':
        from . import survey
        if a.operation=='status':return survey.status(store.read_snapshot(),a.instance)
        if a.operation=='retrieve':return survey.retrieve(store,a.instance,a.plan_ref)
        if a.operation=='freeze':return survey.freeze_knowledge(store,a.instance,selected_refs=loads(read(a.selected_refs)) if a.selected_refs else None,question_ids=loads(read(a.question_ids)) if a.question_ids else None)
        if a.operation=='source-status':return survey.mark_source(store,a.instance,a.source_ref,withdrawn=a.withdrawn,version_conflict=a.version_conflict,reason=a.reason)
        if a.operation=='plan':return survey.create_output_plan(store,a.instance,a.snapshot_ref,profile=a.profile,**(loads(read(a.settings)) if a.settings else {}))
        from .codex_client import policy
        result=survey.start_activity(store,a.instance,a.stage,a.intent,max_calls=a.max_calls,max_workers=a.max_workers,policy=policy(),
            model_overrides=loads(read(a.model_overrides)) if a.model_overrides else None,allow_reports=a.allow_reports,
            selected_refs=loads(read(a.selected_refs)) if a.selected_refs else None,
            source_refs=loads(read(a.source_refs)) if a.source_refs else None,role=a.role)
        return result if a.stage=='S5' else e.run_round(store,a.instance)
    if cmd=='workflow':
        if a.operation=='list':return {'instances':list(store.read_snapshot()['instances'].values()),'model_calls':0}
        scope={key:read(path) for key,path in [('phenomenon',a.brief),('immutable_background',a.immutable_background),('allowed_axes',a.allowed_axes)] if path}
        if a.operation=='configure-discovery':return e.configure_discovery(store,a.instance,scope)
        return e.new_workflow(store,a.kind,name=a.name,target_ref=a.target,target=read(a.target_text) if a.target_text else None,discovery_scope=scope,survey_scope=loads(read(a.survey_scope)) if a.survey_scope else None)
    if cmd=='knowledge':
        from . import views
        s=store.read_snapshot(a.commit)
        if a.operation=='current':return views.current(s,store.read_blob,instance_id=a.instance,query=a.query,offset=a.offset,limit=a.limit)
        if a.operation=='diff':return views.diff(store.read_snapshot(a.from_commit),s,instance_id=a.instance)
        return getattr(views,a.operation)(s,store.read_blob,instance_id=a.instance)
    if cmd=='handoff':
        return e.prepare_handoff(store,a.instance,a.direction,loads(read(a.scope))) if a.operation=='prepare' else e.adopt_handoff(store,a.handoff,loads(read(a.decision)))
    if cmd=='status':
        from .operations import status
        return status(store,a.instance)
    if cmd=='audit':return store.audit()
    if cmd=='rebuild-index':return store.rebuild_projection()
    if cmd=='orphans':return store.orphans()
    if cmd=='authorize':return e.authorize(store,a.instance,loads(read(a.mission)),loads(read(a.budget)))
    if cmd=='start':
        from .codex_client import policy
        e.start_round(store,a.instance,a.intent,max_calls=a.max_calls,max_workers=a.max_workers,policy=policy(),
                model_overrides=loads(read(a.model_overrides)) if a.model_overrides else None)
        return e.run_round(store,a.instance)
    if cmd=='configure':return e.update_configuration(store,a.instance,loads(read(a.model_overrides)) if a.model_overrides else [],a.reason,
            reset_scopes=loads(read(a.reset_scopes)) if a.reset_scopes else [])
    if cmd in {'schedule','prepare'}:return getattr(e,cmd)(store,a.instance)
    if cmd=='run':return e.run_round(store,a.instance,max_tasks=a.max_tasks)
    if cmd=='pause':return e.pause(store,a.instance,a.reason)
    if cmd=='decide':return e.decide(store,a.instance,a.action,a.note,snapshot_commit=a.snapshot,candidate_ref=a.candidate,report_ref=a.report_ref)
    if cmd=='resume':return e.resume(store,a.instance,a.decision)
    if cmd=='source':
        from .changes import prepare_material_input
        return store.commit(prepare_material_input(store.read_snapshot(),read(a.file),title=a.file.name,media_type=a.media_type,blob_get=store.read_blob))
    if cmd=='preflight':return e.preflight(store,a.task,read(a.response))
    if cmd=='recover':return e.recover(store,a.request,check_only=a.check_only)
    if cmd in {'cancel','reconcile'}:
        if cmd=='reconcile':return e.reconcile_unknown(store,a.instance,a.request,a.disposition,a.reason,not_sent_evidence_ref=a.not_sent_evidence)
        from .workflow_instances import event
        p={'request_id':a.request,'reason':a.reason,'note':a.reason}
        return store.commit_control(event(store.read_snapshot(),'CANCEL_REQUEST',p,instance_id=a.instance))
    if cmd=='report':
        from . import reports
        from .render import Renderer
        if a.check_only:return reports.prepare(store,a.instance,check_only=True,plan_ref=a.plan_ref)
        is_survey=store.read_snapshot()['instances'][a.instance]['kind']=='SURVEY'
        rid=reports.create(store,a.instance,plan_ref=a.plan_ref,profiles=[a.profile] if is_survey and a.profile else None)
        if a.prepare_only:return reports.prepare(store,a.instance,report_id=rid)
        if a.render_only:return reports.render(store,Renderer(),a.instance,a.profile,report_id=rid)
        return reports.run(store,a.instance,policy=e.policy(store,a.instance),renderer=Renderer(),report_id=rid)
    if cmd=='ui':
        from .ui import serve
        serve(store,a.port);return {'closed':True}
    raise PMRSError('COMMAND_INVALID','Unsupported command')


def main(argv=None):
    try:
        result=execute(parser().parse_args(argv))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (PMRSError,OSError,ValueError,KeyError) as error:
        print(json.dumps({'error':getattr(error,'code','INPUT_INVALID'),'message':str(error)},ensure_ascii=False),file=sys.stderr);return 2
