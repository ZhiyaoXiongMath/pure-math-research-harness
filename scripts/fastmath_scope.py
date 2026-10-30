"""Pinned pre-DEV11 stage followed by exact owned paths and symbols."""
import ast
import base64
import hashlib
import json
from pathlib import Path

PARENT = '48b445f4370922d5535f7b6c4641066bd82fcfdc'
TREE = '1c0d3f9417a6d398168472af47c930991e0efc1b'
ORACLE_SHA256 = 'dc8ef798e09f31928ca683431e14fe962aff8ccbe0303b6e397e461c248866a8'
PATHS = frozenset(['.github/workflows/devpr11-offline.yml', 'config/architecture-exceptions.json', 'docs/development/DEV-PR-11-CONTRACT.md', 'docs/development/DEV-PR-11-DELIVERY.md', 'pmrh/adapters/storage/control.py', 'pmrh/adapters/storage/control_fast.py', 'pmrh/adapters/storage/fastmath.py', 'pmrh/adapters/storage/format.py', 'pmrh/adapters/storage/io.py', 'pmrh/adapters/storage/journal.py', 'pmrh/adapters/storage/pool.py', 'pmrh/application/control.py', 'pmrh/application/fastmath.py', 'pmrh/application/read_projections.py', 'pmrh/domain/contracts.py', 'pmrh/domain/fastmath/__init__.py', 'pmrh/domain/fastmath/model.py', 'pmrh/domain/fastmath/qualification.py', 'pmrh/domain/fastmath/validation.py', 'pmrh/domain/native_response.py', 'pmrh/domain/native_settlement.py', 'research_studio/changes.py', 'research_studio/contracts.py', 'research_studio/execution.py', 'research_studio/knowledge_access.py', 'research_studio/research_audit.py', 'research_studio/storage_compat.py', 'research_studio/store.py', 'research_studio/strategy.py', 'research_studio/task_tools.py', 'research_studio/version.py', 'scripts/architecture_deps.py', 'scripts/check_legacy_scope.py', 'scripts/control_scope.py', 'scripts/domain_scope.py', 'scripts/fastmath_sandbox.py', 'scripts/fastmath_scope.py', 'scripts/offline_fastmath.py', 'scripts/storage_scope.py', 'tests/devpr05/test_extraction_boundaries.py', 'tests/devpr11/__init__.py', 'tests/devpr11/fixtures.py', 'tests/devpr11/test_boundaries.py', 'tests/devpr11/test_control_fast.py', 'tests/devpr11/test_domain.py', 'tests/devpr11/test_retrieval.py', 'tests/devpr11/test_scope.py', 'tests/devpr11/test_storage.py'])
SYMBOLS = {'scripts/control_scope.py': {'verify_sections'}, 'pmrh/adapters/storage/io.py': {'_ConfinedReader.read', '_ConfinedReader._check_unchanged', '_ConfinedReader.read_verified_body', '_ConfinedReader._open_regular', '_BodyVisitor', '_VerifiedBodyRead', '_BodyReadBudget'}, 'pmrh/adapters/storage/pool.py': {'Pool.inspect'}, 'research_studio/changes.py': {'science_projection', '_FORMAT_WIRE_FIELDS', 'format_repair_evidence', '_repair_kcs', 'validator_identity', '_error_diagnostic', '_validate', '_resolve_projection_locators'}, 'research_studio/task_tools.py': {'TaskTools.call', 'tool_definitions'}, 'pmrh/adapters/storage/format.py': {'publication_schema'}, 'pmrh/application/control.py': {'AuthorityRegistry.register_fast_ingress', 'Control.native'}, 'pmrh/adapters/storage/journal.py': {'Journal.history', 'Journal.read_snapshot', 'Journal._publish', 'Journal._commit_record'}, 'pmrh/adapters/storage/control.py': {'ControlStorage.execute', 'command', 'ControlStorage.reduce', 'ControlStorage.combined', 'ControlStorage.event_schema', 'ControlStorage.acquire_native_slot', 'scan', 'ControlStorage.decision_record', 'ControlStorage.validate_transition', 'validate_entry', 'ControlStorage.acquire_slot', 'validate_record'}, 'pmrh/application/read_projections.py': {'_cost', 'aggregate_project_remaining', 'budget_remaining', 'project_remaining', 'strategy_id', 'strategy_current'}, 'pmrh/domain/contracts.py': {'RESPONSE_SCHEMA'}, 'research_studio/contracts.py': {'_compact_authoring_schema', 'validate_authoring', 'schema_diagnostics', '_map_schema', '_compile_authoring', 'authoring_contract'}, 'research_studio/execution.py': {'event', '_request', 'apply_event'}, 'research_studio/research_audit.py': {'PROGRESS', '_append_interval', 'phase', 'transition', 'seconds', 'authoring_schema', 'DEFAULT_POLICY', 'policy'}, 'research_studio/strategy.py': {'_schema_obj', 'PROPOSAL_SCHEMA', 'ROUTE_STATES', 'authoring_schema'}, 'research_studio/version.py': {'RESPONSE_SCHEMA'}, 'scripts/domain_scope.py': {'verify_sections'}, 'tests/devpr05/test_extraction_boundaries.py': {'Extraction.test_exact_symbol_guard_and_shared_compatibility_identity'}}
WHOLE = frozenset({'research_studio/knowledge_access.py','research_studio/storage_compat.py','research_studio/store.py',
 'scripts/architecture_deps.py','scripts/check_legacy_scope.py','scripts/storage_scope.py','config/architecture-exceptions.json'})
EDGES = frozenset({('research_studio/execution.py', 'pmrh/domain/native_settlement.py'), ('research_studio/storage_compat.py', 'pmrh/application/fastmath.py'), ('research_studio/research_audit.py', 'pmrh/domain/native_response.py'), ('research_studio/changes.py', 'pmrh/domain/native_response.py'), ('research_studio/storage_compat.py', 'pmrh/adapters/storage/control_fast.py'), ('research_studio/research_audit.py', 'pmrh/domain/native_settlement.py'), ('research_studio/knowledge_access.py', 'pmrh/domain/fastmath/validation.py'), ('research_studio/contracts.py', 'pmrh/domain/native_response.py'), ('research_studio/version.py', 'pmrh/domain/contracts.py'), ('research_studio/strategy.py', 'pmrh/domain/native_response.py'), ('research_studio/knowledge_access.py', 'pmrh/domain/fastmath/qualification.py'), ('research_studio/knowledge_access.py', 'pmrh/adapters/storage/journal.py'), ('research_studio/knowledge_access.py', 'pmrh/adapters/storage/io.py')})

SCOPE04_PREIMAGES = {'pmrh/application/read_projections.py': '4501f43496bea6fbd5773442138137092ef855064c9a90a37a0c04d19149146c', 'pmrh/domain/contracts.py': '23e82a9d0cfb3f1e10d957b203e21eb42b9793cf89f942cbe90263ad36eed1da', 'research_studio/contracts.py': '6b274390a91ef8063c9e32624942f980db63223a78484f4b2112de6e44352e4f', 'research_studio/execution.py': 'ffa90e5ca68af2136ece0b1545b2b6f825556c0ac11fdf16689a3ed25d4bcf31', 'research_studio/research_audit.py': 'bd39ad6b80109d5938aaa827b56de6b3b12117a7292b99f709586f615d0542e6', 'research_studio/strategy.py': '79ac1d86c05dfd0e0b09b47aa4843799c7ce0ea0842851a6b2d691b2d3ba123a', 'research_studio/version.py': 'f1c55ac148d998c260edc4f89e7a829d5a768fe57b8ba577333c6d6434cb4b23'}
SCOPE04_REEXPORTS = {'pmrh/application/read_projections.py': ['from pmrh.domain.native_settlement import _cost as _cost', 'from pmrh.domain.native_settlement import budget_remaining as budget_remaining', 'from pmrh.domain.native_settlement import project_remaining as project_remaining', 'from pmrh.domain.native_settlement import aggregate_project_remaining as aggregate_project_remaining', 'from pmrh.domain.native_settlement import strategy_id as strategy_id', 'from pmrh.domain.native_settlement import strategy_current as strategy_current'], 'pmrh/domain/contracts.py': [], 'research_studio/contracts.py': ['from pmrh.domain.native_response import authoring_contract as authoring_contract', 'from pmrh.domain.native_response import _compile_authoring as _compile_authoring', 'from pmrh.domain.native_response import _map_schema as _map_schema', 'from pmrh.domain.native_response import _compact_authoring_schema as _compact_authoring_schema', 'from pmrh.domain.native_response import schema_diagnostics as schema_diagnostics', 'from pmrh.domain.native_response import validate_authoring as validate_authoring'], 'research_studio/execution.py': ['from pmrh.domain.native_settlement import _request as _request'], 'research_studio/research_audit.py': ['from pmrh.domain.native_settlement import DEFAULT_POLICY as DEFAULT_POLICY', 'from pmrh.domain.native_response import PROGRESS as PROGRESS', 'from pmrh.domain.native_settlement import seconds as seconds', 'from pmrh.domain.native_settlement import policy as policy', 'from pmrh.domain.native_settlement import phase as phase', 'from pmrh.domain.native_settlement import _append_interval as _append_interval', 'from pmrh.domain.native_response import audit_authoring_schema as authoring_schema'], 'research_studio/strategy.py': ['from pmrh.domain.native_response import PROPOSAL_SCHEMA as PROPOSAL_SCHEMA', 'from pmrh.domain.native_response import ROUTE_STATES as ROUTE_STATES', 'from pmrh.domain.native_response import _schema_obj as _schema_obj', 'from pmrh.domain.native_response import strategy_authoring_schema as authoring_schema'], 'research_studio/version.py': ['from pmrh.domain.contracts import RESPONSE_SCHEMA as RESPONSE_SCHEMA'], 'research_studio/changes.py': ['from pmrh.domain.native_response import _FORMAT_WIRE_FIELDS as _FORMAT_WIRE_FIELDS', 'from pmrh.domain.native_response import _repair_kcs as _repair_kcs', 'from pmrh.domain.native_response import _resolve_projection_locators as _resolve_projection_locators', 'from pmrh.domain.native_response import science_projection as science_projection', 'from pmrh.domain.native_response import _error_diagnostic as _error_diagnostic']}
# Scope06 pins exact source spans, including decorators and the complete final line.
SCOPE04_SYMBOL_SHA256 = {'pmrh/application/read_projections.py': {'_cost': 'cc411a5e10924263fa33ff9f939d6d6382f743ff3986b73ede305bc827c1681c', 'budget_remaining': '3306a4a13840050023b19d7ea6fb3e89c3fef750da944aa5abc1449dd9df77de', 'project_remaining': '7f5db2da938376a1e9dc6fc03dbccbeb26091fbbc764acc2471ec1af1bda1c9c', 'aggregate_project_remaining': '39d1111c26430a37ee05423f33ca031132512359bc06d592272ae7268434062e', 'strategy_id': 'f98945f7a99d02189ca2eede28e7eb0c0ac50d6fd4b10dd277b805d8da143546', 'strategy_current': '81d0e3a1a41ee050e004334fed0ef0ae3fccf7a31257da6981e9a583f45932e8'}, 'pmrh/domain/contracts.py': {'RESPONSE_SCHEMA': '14c9dec6622c32771f6248a1b303a19dc0d5b44619babc45899e862719957cd7'}, 'research_studio/contracts.py': {'authoring_contract': '7cb18ef2c10dbeea4e70d9e7f766e7b649314d955778c9691f5946122cd3be02', '_compile_authoring': 'a29ec8d05e092809b8c85c4a3399dea4a212b14d0ed1fb8b6a9d8fc2009e8aba', '_map_schema': '489c4035260f39ca24f4277b4843f7dcac3bd81f32ea986e6a921199f2fb086c', '_compact_authoring_schema': '192cd832888c4758bdf9f83f61c29222b1b68bb5b199ae0d506429ae9618da54', 'schema_diagnostics': '7dac3cad3adda274b2a95b7ecd270925c419f093f2de0aac47fd70cec1ea850f', 'validate_authoring': '21b42c15c65a3aba7d20bf298d72dc04f842544eae5991f8a7aa13429716362c'}, 'research_studio/execution.py': {'event': '69cd1252b85468efb982046bff4947d808dadd224ddfecc7f5a5813bf402312b', 'apply_event': '2d7e7d62bf24aea0f226f49ee3761dfef0322d8998de353985f166f9c6d8de6b', '_request': 'eff94e2450403639aada289d91ffe7f5aca4b3659378bdc7ec22d846cee72a15'}, 'research_studio/research_audit.py': {'authoring_schema': 'fb5b0ed679c4ddde317d42a01639c9d7d896c74cb78f16014be20924fe2dc865', 'PROGRESS': '466271c546d41ac1b27b33a0f8a5c68231c2f04303859f85ecb7202443387b9a', 'DEFAULT_POLICY': '25811632f84ae9503459afcb4bac01bc806276ae71b8e80a295e5f5c16f0351c', 'seconds': '2e90e16e56b75056a498463916da3044b1c4eda479c85cc7e7d86fb4e3ef3914', 'policy': '43cc1e461fba4073f91609f0bfc179e3ce571df6b74b5285b4d6d939129efe0c', 'phase': '91110664af76626147df38d104fdb9e78c427e43956589ed6589b841e344c5f9', '_append_interval': '256eb9308ac3816e4ccdc72e4834edf6729572328ab82609f1bdab4f20f7f872', 'transition': '06f814fbc1fda082757da2bb07d4289fdb35a525654cbb634df3687a4bde975b'}, 'research_studio/strategy.py': {'_schema_obj': '24219c093aa2fc85fc40577260f474fd36bb1537cc7a4f5425268faea254d45a', 'authoring_schema': '7bd6091871b4ff0d3bf9a9691a871734fcdfa2ffd2c8f0962c5d142462f5544d', 'PROPOSAL_SCHEMA': '3fd67a61bd142b52a375f61631ccf035f77aaa36ec5bc54a38d5a00c87e2ae8d', 'ROUTE_STATES': '0d894b07178635e7b8bc92304f4e90ba03cc626e63c29ab155944a996b4260c8'}, 'research_studio/version.py': {'RESPONSE_SCHEMA': '1b2a51235818c26ea537e71a8c7ccf0b7f9e0547dca2c333de57e05863139f80'}, 'research_studio/changes.py': {'_validate': 'a74c494cbd3a6bbdc09fe37b496403ec15c10dd610b4d7f71b843a5f16146e98', '_FORMAT_WIRE_FIELDS': '5727b8a03d3cfd72c7ad8608edab5b4d596f35696cfee779e7bb6f51ca80aac8', '_repair_kcs': '5f8d793daa20312f1ad357a86f188cd5e767ff81838de9673d59dea755dbb039', '_resolve_projection_locators': '2885458f86c594a06b0a1a67089fa10e65152847042ef02e176d2186e32f3060', 'science_projection': '92989d6ab97bdd5a36ae5c034eec0344aa597a24cb32ae77d680c4e92e7d3ced', '_error_diagnostic': '855c0bffdf1aa0f8822740ee6f59081e01434773db8b5fcb17d124429001488f', 'format_repair_evidence': '7aeb29784343a45595243639ba07af5e95a9b6f3f2ca7738c9325d43daa3aabf'}}
SCOPE06_EXACT_FILES = {'scripts/domain_scope.py': ('f09b3fb27c8f24fcc8eb13ac5e3f510a9deb178e4b51aba62f66f45f57ac81ff', '246f9d3a1c1bbdc7836c9a43c9a51ab2c6a714ee06c16f9d958b0f4498cc8b14'), 'tests/devpr05/test_extraction_boundaries.py': ('84cd680d12da324c019a275ba08d8d849f1ac8a975b5cc8e1e63ad909fac906b', 'b81854bb5e3ed488e6fdde526d36f6f414ba4be074688629a991fdaad2e71a3b')}
MECHANICAL_MOVES = [('research_studio/contracts.py', 'authoring_contract', 'pmrh/domain/native_response.py', 'authoring_contract', []), ('research_studio/contracts.py', '_compile_authoring', 'pmrh/domain/native_response.py', '_compile_authoring', [['        from . import strategy\n', ''], ['strategy.authoring_schema(task)', 'strategy_authoring_schema(task)']]), ('research_studio/contracts.py', '_map_schema', 'pmrh/domain/native_response.py', '_map_schema', []), ('research_studio/contracts.py', '_compact_authoring_schema', 'pmrh/domain/native_response.py', '_compact_authoring_schema', []), ('research_studio/contracts.py', 'schema_diagnostics', 'pmrh/domain/native_response.py', 'schema_diagnostics', []), ('research_studio/contracts.py', 'validate_authoring', 'pmrh/domain/native_response.py', 'validate_authoring', []), ('research_studio/strategy.py', 'PROPOSAL_SCHEMA', 'pmrh/domain/native_response.py', 'PROPOSAL_SCHEMA', []), ('research_studio/strategy.py', 'ROUTE_STATES', 'pmrh/domain/native_response.py', 'ROUTE_STATES', []), ('research_studio/strategy.py', '_schema_obj', 'pmrh/domain/native_response.py', '_schema_obj', []), ('research_studio/strategy.py', 'authoring_schema', 'pmrh/domain/native_response.py', 'strategy_authoring_schema', [['def authoring_schema(', 'def strategy_authoring_schema('], ['    from .research_audit import authoring_schema as audit_schema\n', ''], ['audit_schema()', 'audit_authoring_schema()']]), ('research_studio/research_audit.py', 'PROGRESS', 'pmrh/domain/native_response.py', 'PROGRESS', []), ('research_studio/research_audit.py', 'authoring_schema', 'pmrh/domain/native_response.py', 'audit_authoring_schema', [['def authoring_schema(', 'def audit_authoring_schema(']]), ('research_studio/changes.py', '_FORMAT_WIRE_FIELDS', 'pmrh/domain/native_response.py', '_FORMAT_WIRE_FIELDS', []), ('research_studio/changes.py', '_repair_kcs', 'pmrh/domain/native_response.py', '_repair_kcs', []), ('research_studio/changes.py', '_resolve_projection_locators', 'pmrh/domain/native_response.py', '_resolve_projection_locators', []), ('research_studio/changes.py', 'science_projection', 'pmrh/domain/native_response.py', 'science_projection', []), ('research_studio/changes.py', '_error_diagnostic', 'pmrh/domain/native_response.py', '_error_diagnostic', []), ('pmrh/application/read_projections.py', '_cost', 'pmrh/domain/native_settlement.py', '_cost', []), ('pmrh/application/read_projections.py', 'budget_remaining', 'pmrh/domain/native_settlement.py', 'budget_remaining', []), ('pmrh/application/read_projections.py', 'project_remaining', 'pmrh/domain/native_settlement.py', 'project_remaining', []), ('pmrh/application/read_projections.py', 'aggregate_project_remaining', 'pmrh/domain/native_settlement.py', 'aggregate_project_remaining', []), ('pmrh/application/read_projections.py', 'strategy_id', 'pmrh/domain/native_settlement.py', 'strategy_id', []), ('pmrh/application/read_projections.py', 'strategy_current', 'pmrh/domain/native_settlement.py', 'strategy_current', []), ('research_studio/research_audit.py', 'DEFAULT_POLICY', 'pmrh/domain/native_settlement.py', 'DEFAULT_POLICY', []), ('research_studio/research_audit.py', 'seconds', 'pmrh/domain/native_settlement.py', 'seconds', []), ('research_studio/research_audit.py', 'policy', 'pmrh/domain/native_settlement.py', 'policy', []), ('research_studio/research_audit.py', 'phase', 'pmrh/domain/native_settlement.py', 'phase', [['    from .scheduler import budget_remaining,project_remaining\n', ''], ['    from .strategy import current\n', ''], ['st=current(s,iid)', 'st=strategy_current(s,iid)']]), ('research_studio/research_audit.py', '_append_interval', 'pmrh/domain/native_settlement.py', '_append_interval', []), ('research_studio/research_audit.py', 'transition', 'pmrh/domain/native_settlement.py', 'transition', [['*,at=None', '*,at'], ['    at=at or now();clock=', '    clock=']]), ('research_studio/execution.py', '_request', 'pmrh/domain/native_settlement.py', '_request', [])]


def oracle(root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[1]
    path=root/'scripts/fastmath_scope_preintegration.json'
    if path.is_symlink():raise ValueError('Symlink oracle rejected')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ORACLE_SHA256:raise ValueError('Root-pinned preintegration oracle differs')
    result=json.loads(raw)
    if (result['parent'],result['tree'])!=(PARENT,TREE):raise ValueError('Parent/tree differs')
    if set(result['files']) != set(SYMBOLS)|WHOLE:raise ValueError('Parent file boundary differs')
    for name,row in result['files'].items():
        data=base64.b64decode(row['bytes_base64'],validate=True)
        if hashlib.sha256(data).hexdigest()!=row['sha256'] or row['mode'] not in {'100644','100755'}:
            raise ValueError('Embedded parent bytes/mode differ: '+name)
    for name,digest in result['inherited_guard_hashes'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Inherited guard changed: '+name)
    return result


def _outside(raw,names):
    tree=ast.parse(raw)
    def trim(nodes,prefix=''):
        result=[]
        for node in nodes:
            name=getattr(node,'name',None)
            if isinstance(node,(ast.Assign,ast.AnnAssign)):
                target=node.targets[0] if isinstance(node,ast.Assign) else node.target
                name=target.id if isinstance(target,ast.Name) else None
            if name and prefix+name in names:continue
            if isinstance(node,ast.ClassDef):node.body=trim(node.body,prefix+node.name+'.')
            result.append(node)
        return result
    tree.body=trim(tree.body)
    return ast.dump(tree,include_attributes=False)


def _method_bytes(raw,class_name,method_name):
    tree=ast.parse(raw)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==method_name)
    return b''.join(raw.splitlines(keepends=True)[method.lineno-1:method.end_lineno])


def _io_without_new_imports(raw):
    tree=ast.parse(raw)
    additions={ast.dump(ast.parse(line).body[0],include_attributes=False) for line in (
        'from contextlib import contextmanager','from dataclasses import dataclass',
        'import hashlib','from typing import Protocol')}
    tree.body=[n for n in tree.body if ast.dump(n,include_attributes=False) not in additions]
    return ast.unparse(tree)


def _scope04_tree(raw,path):
    tree=ast.parse(raw)
    allowed={ast.dump(ast.parse(line).body[0],include_attributes=False) for line in SCOPE04_REEXPORTS.get(path,())}
    tree.body=[n for n in tree.body if ast.dump(n,include_attributes=False) not in allowed]
    return ast.unparse(tree)


def _symbol_node(raw,name):
    matches=[]
    for n in ast.parse(raw).body:
        keys={getattr(n,'name',None)}
        if isinstance(n,(ast.Assign,ast.AnnAssign)):
            targets=n.targets if isinstance(n,ast.Assign) else [n.target]
            keys={t.id for target in targets for t in ast.walk(target)
                  if isinstance(t,ast.Name) and isinstance(t.ctx,ast.Store)}
        if isinstance(n,ast.ImportFrom) and len(n.names)==1:
            keys={n.names[0].asname or n.names[0].name}
        if name in keys:matches.append(n)
    if not matches:raise ValueError('Missing exact native symbol: '+name)
    if len(matches)!=1:raise ValueError('Duplicate exact native symbol: '+name)
    return matches[0]


def verify_native_moves(root,data):
    for path,name,destination,new_name,replacements in MECHANICAL_MOVES:
        original=base64.b64decode(data['files'][path]['bytes_base64']).decode()
        expected=ast.get_source_segment(original,_symbol_node(original,name))
        for old,new in replacements:
            if old not in expected:raise ValueError('Native move preimage differs: '+path+':'+name)
            expected=expected.replace(old,new)
        actual=_symbol_node((root/destination).read_bytes(),new_name)
        if ast.dump(ast.parse(expected).body[0],include_attributes=False)!=ast.dump(actual,include_attributes=False):
            raise ValueError('Native mechanical move differs: '+path+':'+name)
    # SETTLE's exact request disposition is the original branch, followed by the
    # shared clock and registration. Other execution branches are symbol-pinned.
    old=base64.b64decode(data['files']['research_studio/execution.py']['bytes_base64']).decode()
    original=ast.get_source_segment(old,_symbol_node(old,'apply_event'))
    branch=original.split("    elif kind=='SETTLE':\n",1)[1].split("    elif kind=='ADMISSION_RECHECKED':",1)[0]
    statements=ast.parse('\n'.join(line[8:] for line in branch.splitlines())).body
    current=_symbol_node((root/'pmrh/domain/native_settlement.py').read_bytes(),'apply_event')
    expected=[ast.dump(n,include_attributes=False) for n in statements]
    actual=[ast.dump(n,include_attributes=False) for n in current.body]
    if not any(actual[i:i+len(expected)]==expected for i in range(len(actual))):
        raise ValueError('Original SETTLE disposition changed')


def verify_file(path,original,current):
    if path in SCOPE06_EXACT_FILES:
        expected_original,expected_current=SCOPE06_EXACT_FILES[path]
        if (hashlib.sha256(original).hexdigest(),hashlib.sha256(current).hexdigest())!=(expected_original,expected_current):
            raise ValueError('Outside exact Scope06 file delta: '+path)
        return True
    if path=='scripts/control_scope.py':
        # Scope05 owns exactly one frozen whole-file delta, not arbitrary edits
        # to the named method or any other historical guard bytes.
        if hashlib.sha256(original).hexdigest()!='dace2caa8827070ef991af813de59bf0fec9616b8b01b2056ff9a848a21c7092' or hashlib.sha256(current).hexdigest()!='17c4ad8adc05f7c2d413a368caaeeda9c079ea9f2c1b75475b7ce17fdb0341dd':
            raise ValueError('Outside exact Scope05 guard hook')
        return True
    if path in SCOPE04_PREIMAGES and hashlib.sha256(original).hexdigest()!=SCOPE04_PREIMAGES[path]:
        raise ValueError('Scope04 preimage differs: '+path)
    for name,digest in SCOPE04_SYMBOL_SHA256.get(path,{}).items():
        node=_symbol_node(current,name)
        start=min([node.lineno]+[d.lineno for d in getattr(node,'decorator_list',())])
        actual=b''.join(current.splitlines(keepends=True)[start-1:node.end_lineno])
        if hashlib.sha256(actual).hexdigest()!=digest:raise ValueError('Outside exact native extraction: '+path+':'+name)
    if path=='pmrh/adapters/storage/control.py':
        before=_method_bytes(original,'ControlStorage','acquire_slot')
        after=_method_bytes(current,'ControlStorage','acquire_slot')
        if hashlib.sha256(before).hexdigest()!='6fc80df169c57c85cded4c7fd5b990c42b20abe95194cb8f22a4eaa9f560ba6e' or before.count(b'command(value);')!=1 or after!=before.replace(b'command(value);',b'command(value, combined=self.combined);',1):
            raise ValueError('Outside exact acquire_slot amendment')
    if path=='pmrh/adapters/storage/io.py':
        if hashlib.sha256(original).hexdigest()!='a1c05e9adb8bf20600e89be10c356137aecc8efa8717f9a5aafc925685abe930' or hashlib.sha256(_method_bytes(current,'_ConfinedReader','read')).hexdigest()!='be7d9c59c7637d0237e330aa02dc4c3dac960c0ab73307441d4ab809d3291833':
            raise ValueError('Outside exact legacy read factoring')
        if _outside(original,SYMBOLS[path])!=_outside(_io_without_new_imports(current),SYMBOLS[path]):
            raise ValueError('Outside DEV11 exact io symbols/imports changed')

    if path=='pmrh/adapters/storage/pool.py':
        # Scope amendment 01 allows only this exact discriminator expansion.
        # Even other edits inside Pool.inspect are outside the amendment.
        old=b"if history[-1][1]['schema'] == SCHEMA:"
        new=b"if history[-1][1]['schema'] in (SCHEMA, 'pmrh.control-fast.commit/1'):"
        if original.count(old)!=1 or current!=original.replace(old,new,1):
            raise ValueError('Outside exact Pool discriminator amendment')
    if path in SYMBOLS and path!='pmrh/adapters/storage/io.py' and _outside(original,SYMBOLS[path])!=_outside(_scope04_tree(current,path),SYMBOLS[path]):
        raise ValueError('Outside DEV11 exact symbols changed: '+path)
    if path=='config/architecture-exceptions.json':
        old=json.loads(original);new=json.loads(current)
        bridge=new.pop('devpr11_fastmath_bridge',None)
        if new!=old or bridge is None or bridge['baseline']!=PARENT or set(bridge['changed_paths'])!=set(SYMBOLS)|WHOLE:
            raise ValueError('Earlier architecture policy changed')
        if {(r['source'],r['target']) for r in bridge['direct_edges']}!=EDGES:
            raise ValueError('DEV11 exact architecture edges differ')
    if path=='research_studio/task_tools.py':
        # All other tool schema tuple values remain exact, including MAIN tools.
        def definitions(raw):
            tree=ast.parse(raw)
            fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='tool_definitions')
            for node in ast.walk(fn):
                if isinstance(node,ast.List):
                    node.elts=[e for e in node.elts if not (isinstance(e,ast.Tuple) and e.elts and
                        isinstance(e.elts[0],ast.Constant) and str(e.elts[0].value).startswith('knowledge_'))]
            return ast.dump(fn,include_attributes=False)
        if definitions(original)!=definitions(current):raise ValueError('Non-knowledge tool schema changed')
        def call_outside(raw):
            tree=ast.parse(raw)
            cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='TaskTools')
            fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='call')
            for node in ast.walk(fn):
                if isinstance(node,ast.If) and isinstance(node.test,ast.Call) and isinstance(node.test.func,ast.Attribute) and node.test.func.attr=='startswith' and node.test.args and isinstance(node.test.args[0],ast.Constant) and node.test.args[0].value=='knowledge_':
                    node.body=[ast.Pass()]
            return ast.dump(fn,include_attributes=False)
        if call_outside(original)!=call_outside(current):raise ValueError('Non-knowledge tool dispatch changed')
    return True


def preintegration(path,current,root=None):
    data=oracle(root)
    if path not in data['files']:return current
    original=base64.b64decode(data['files'][path]['bytes_base64'],validate=True)
    verify_file(path,original,current)
    return original


def verify(root):
    root=Path(root);data=oracle(root)
    for relative,digest in data['baseline_file_sha256'].items():
        path=root/relative
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError('Symlink candidate/source')
        raw=path.read_bytes()
        if relative in data['files']:
            verify_file(relative,base64.b64decode(data['files'][relative]['bytes_base64']),raw)
        elif hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Unowned baseline file changed: '+relative)
    for path in root.rglob('*'):
        relative=path.relative_to(root).as_posix()
        if any(p in {'.git','__pycache__'} for p in path.relative_to(root).parts):continue
        if path.is_symlink():raise ValueError('Symlink source: '+relative)
        if path.is_file() and relative not in data['baseline_file_sha256'] and relative not in PATHS and relative!='scripts/fastmath_scope_preintegration.json':
            raise ValueError('Unlisted source addition: '+relative)
    verify_native_moves(root,data)
    for path in PATHS:
        if not (root/path).is_file():raise ValueError('Missing candidate: '+path)
    return {'parent':PARENT,'tree':TREE,'oracle_sha256':ORACLE_SHA256,'stage':'PARENT_TO_DEV11','status':'PASS'}


if __name__=='__main__':
    print(json.dumps(verify(Path(__file__).resolve().parents[1]),sort_keys=True))
