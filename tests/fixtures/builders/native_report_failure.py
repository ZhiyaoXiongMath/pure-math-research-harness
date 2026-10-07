"""Typed native report failure fixture for actual browser recovery stories."""
from research_studio import contracts as C,demo,reports
from research_studio.engine import Engine
from research_studio.runner import FakeExecutor
from research_studio.render import Renderer
from research_studio.util import canonical

def build(root,*,report_first=False):
    e=Engine();store=e.create(root,demo.ARITHMETIC,synthetic=True);target=next(iter(store.read_snapshot()['records']))
    iid=e.new_workflow(store,'TRW',target_ref=target)['instance_id']
    e.authorize(store,iid,{'intent':'Prepare an honest report and preserve a newly identified research gap.',
        'authorized_scope':{'target_refs':[target],'reports':True,'allow_derived_work':True},'obligations':[],
        'report_first_actions':['CONTINUE','END','ADOPT','ADOPT_HANDOFF'] if report_first else []},
        {'max_calls':12,'max_workers':2,'execution_policy':demo.policy()})
    def response(t,s):
        if t['role']!='REPORT_SEMANTIC':return demo.response(t,s)
        payload={'profile':t['report_context']['profile'],'verdict':'REVISE','uncheckable':[],
          'findings':[{'code':'NEW_LEMMA_REQUIRED','anchor':'Statement S1','severity':'BLOCKING',
                       'description':'The supplied candidates do not contain an independently checked argument for the complete target scope.'}]}
        return canonical({'schema':C.RESPONSE_SCHEMA,'task_id':t['task_id'],'request_id':t['request_id'],
                          'payload_kind':'REPORT_REVIEW','payload':payload})
    result=reports.run(store,iid,executor=FakeExecutor(response),policy=demo.policy(),renderer=Renderer())
    assert result['state']=='REPORT_BLOCKED'
    state=store.read_snapshot();entry=state['reports'][result['report_id']]
    assert entry['profiles']['lecture']['render']['environment']['namespace_isolated']
    assert not entry['profiles']['minimal']['body_sha256']
    duty=entry['open_research_requests'][0]['obligation_id'];assert state['obligations'][duty]['projection']['work_state']=='OPEN'
    assert not state['supports'];store.audit()
    return store,{'instance_id':iid,'report_id':result['report_id'],'open_obligation_id':duty,'target_ref':target,
                  'knowledge_commit':state['knowledge_commit'],'synthetic_model_calls':2,'billable_model_calls':0}
