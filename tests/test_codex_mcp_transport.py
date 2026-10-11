"""Installed Codex CLI + actual stdio MCP; loopback replaces inference only."""
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,os,shutil,subprocess,threading,time,unittest
from research_studio import runner,demo,task_tools,tasks,codex_client
from research_studio.util import canonical,sha
from tests.test_model_pool import fixture,prepare


class NativeCliMcp(unittest.TestCase):
    @unittest.skipUnless(shutil.which('codex'),'Official CLI is not installed')
    def test_installed_cli_injects_only_scoped_mcp_under_ignore_user_config(self):
        catalog=subprocess.run([shutil.which('codex'),'debug','models'],capture_output=True,text=True,check=True,timeout=25,env=runner.environment()).stdout.encode()
        with TemporaryDirectory(prefix='pmrs-native-cli-') as tmp:
            root=Path(tmp)
            with patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':str(root/'host')}):
                store,iid,policy=fixture(root/'project',1,1);made=prepare(store,iid,policy)[0]
                task=store.read_snapshot()['tasks'][made['task_id']];final=demo.response(task,store.read_snapshot()).decode();seen=[]
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self,*args):pass
                    def do_GET(self):
                        if self.path.split('?')[0]!='/v1/models':self.send_error(404);return
                        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(catalog)
                    def do_POST(self):
                        incoming=json.loads(self.rfile.read(int(self.headers['Content-Length'])));seen.append(incoming)
                        if len(seen)==1:
                            item={'type':'custom_tool_call','id':'fc_pmrs','call_id':'call_pmrs','name':'exec','namespace':'functions',
                                  'input':'const item = ALL_TOOLS.find(x => x.name.endsWith("research_messages_list")); text(await tools[item.name]({}));','status':'completed'}
                        else:
                            item={'type':'message','id':'msg_pmrs','role':'assistant','status':'completed','content':[{'type':'output_text','text':final,'annotations':[]}]}
                        response={'id':'resp_pmrs_'+str(len(seen)),'object':'response','created_at':int(time.time()),'status':'completed','model':'gpt-6-astra',
                                  'output':[item],'usage':{'input_tokens':10,'output_tokens':5,'total_tokens':15}}
                        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                        chunks=[('response.created',{'response':{**response,'status':'in_progress','output':[]}}),
                                ('response.output_item.added',{'output_index':0,'item':item}),
                                ('response.output_item.done',{'output_index':0,'item':item}),('response.completed',{'response':response})]
                        for kind,extra in chunks:
                            self.wfile.write(('event: '+kind+'\ndata: '+json.dumps({'type':kind,**extra})+'\n\n').encode());self.wfile.flush()
                server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                original=runner.permissions
                options={'model_provider':'pmrs_test','model_providers.pmrs_test.name':'PMRS local synthetic inference',
                         'model_providers.pmrs_test.base_url':'http://127.0.0.1:'+str(server.server_port)+'/v1',
                         'model_providers.pmrs_test.wire_api':'responses','model_providers.pmrs_test.requires_openai_auth':False,
                         'model_providers.pmrs_test.supports_websockets':False}
                def permissions(binary,work):return original(binary,work)+[x for k,v in options.items() for x in ('-c',k+'='+json.dumps(v))]
                try:
                    with patch('research_studio.runner.permissions',side_effect=permissions):
                        result=runner.CodexExecutor(timeout=25).execute(store,made['task_id'])
                    self.assertEqual(result['state'],'ACCEPTED')
                    s=store.read_snapshot();deliveries=list(s.get('input_deliveries',{}).values())
                    if not deliveries:
                        diagnostic={'backend_input_items':seen[-1].get('input'),
                                    'stderr':(store.root/'runs'/made['task_id']/'stderr.log').read_text()[-3000:]}
                        output=os.environ.get('PMRS_ACCEPTANCE_OUT')
                        if output:(Path(output)/'native-cli-mcp-first-failure.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
                        outputs=[x for x in seen[-1].get('input',[]) if x.get('type','').endswith('_output')]
                        self.fail('No real MCP delivery: '+json.dumps(outputs)[-3000:]+' stderr='+diagnostic['stderr'])
                    self.assertEqual(len(seen),2)
                    first=canonical(seen[0]['input']).decode()
                    self.assertNotIn('<skills_instructions>',first)
                    self.assertIn(runner.CLIENT_SYSTEM_INSTRUCTIONS.strip(),first)
                    for definition in task_tools.tool_definitions(task.get('actor_kind')):self.assertIn(definition['name'],first)
                    for forbidden in ('spawn_agent','send_message_to_thread','fork_thread','create_thread'):self.assertNotIn(forbidden,first)
                    self.assertEqual([d['tool_name'] for d in deliveries],['research_messages_list'])
                    self.assertTrue(deliveries[0]['confirmed'])
                    self.assertIn('delivery_id',json.dumps(seen[1]['input']))
                    command=json.loads((store.root/'runs'/made['task_id']/'command.json').read_text())
                    self.assertIn('--ignore-user-config',command);self.assertIn('agents.enabled=false',command)
                    self.assertEqual(s['requests'][made['request_id']]['execution_kind'],'SYNTHETIC_TEST_ONLY')
                    output=os.environ.get('PMRS_ACCEPTANCE_OUT')
                    if output:
                        evidence={'state':'PASSED','transport':'installed Codex CLI; loopback synthetic Responses only; real request-scoped stdio MCP',
                                  'paid_model_calls':0,'requests':len(seen),'delivery_tool_names':[d['tool_name'] for d in deliveries],
                                  'tool_input_received_before_final':True,'input_window':s['input_windows'][made['request_id']],
                                  'actual_efforts':[x.get('reasoning') for x in seen],'cli_execution_kind':'SYNTHETIC_TEST_ONLY',
                                  'profile_revision':runner.CLIENT_PROFILE_REVISION,'profile_sha256':sha(runner.client_profile_body(task.get('actor_kind'))),
                                  'host_skills_present':False,'scoped_tool_schema_visible_to_model':True,
                                  'initial_input_bytes':len(canonical(seen[0]['input'])),'initial_input_sha256':sha(canonical(seen[0]['input'])),
                                  'model_catalog_sha256':sha(catalog)}
                        measured=Path(output)/'client-isolation-probe.json'
                        if measured.exists():
                            source=json.loads(measured.read_text())['client_input_evidence']
                            derived=codex_client.derive_task_input_evidence({'executor_contract':{'client_input_evidence':source}},store.root,task['task_id'],task.get('actor_kind'))
                            observed=len(canonical(seen[0]['input']))+len(canonical(seen[0].get('tools',[])))-len(tasks.INPUT_BOOTSTRAP.strip().encode())
                            self.assertLessEqual(observed,derived['prompt_overhead_tokens'])
                            evidence.update(observed_non_task_input_bytes=observed,derived_non_task_input_bound=derived['prompt_overhead_tokens'],
                                            input_derivation=derived['client_input_evidence']['derivation'])
                        Path(output).mkdir(parents=True,exist_ok=True);(Path(output)/'native-cli-mcp-transport.json').write_text(json.dumps(evidence,indent=2)+'\n')
                finally:server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':unittest.main()
