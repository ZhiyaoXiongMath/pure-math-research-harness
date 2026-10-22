"""Pinned pre-DEV11 stage followed by exact owned paths and symbols."""
import ast
import base64
import hashlib
import json
from pathlib import Path

PARENT = '48b445f4370922d5535f7b6c4641066bd82fcfdc'
TREE = '1c0d3f9417a6d398168472af47c930991e0efc1b'
ORACLE_SHA256 = 'fa4823bf89d291d8c8f8d1607aa8d3a513d4d53c932bcaac80411117066a1604'
PATHS = frozenset(['.github/workflows/devpr11-offline.yml', 'config/architecture-exceptions.json', 'docs/development/DEV-PR-11-CONTRACT.md', 'docs/development/DEV-PR-11-DELIVERY.md', 'pmrh/adapters/storage/control.py', 'pmrh/adapters/storage/control_fast.py', 'pmrh/adapters/storage/fastmath.py', 'pmrh/adapters/storage/format.py', 'pmrh/adapters/storage/io.py', 'pmrh/adapters/storage/journal.py', 'pmrh/adapters/storage/pool.py', 'pmrh/application/control.py', 'pmrh/application/fastmath.py', 'pmrh/application/read_projections.py', 'pmrh/domain/contracts.py', 'pmrh/domain/fastmath/__init__.py', 'pmrh/domain/fastmath/model.py', 'pmrh/domain/fastmath/qualification.py', 'pmrh/domain/fastmath/validation.py', 'pmrh/domain/native_response.py', 'pmrh/domain/native_settlement.py', 'research_studio/changes.py', 'research_studio/contracts.py', 'research_studio/execution.py', 'research_studio/knowledge_access.py', 'research_studio/research_audit.py', 'research_studio/storage_compat.py', 'research_studio/store.py', 'research_studio/strategy.py', 'research_studio/task_tools.py', 'research_studio/version.py', 'scripts/architecture_deps.py', 'scripts/check_legacy_scope.py', 'scripts/control_scope.py', 'scripts/fastmath_sandbox.py', 'scripts/fastmath_scope.py', 'scripts/offline_fastmath.py', 'scripts/storage_scope.py', 'tests/devpr11/__init__.py', 'tests/devpr11/fixtures.py', 'tests/devpr11/test_boundaries.py', 'tests/devpr11/test_control_fast.py', 'tests/devpr11/test_domain.py', 'tests/devpr11/test_retrieval.py', 'tests/devpr11/test_scope.py', 'tests/devpr11/test_storage.py'])
SYMBOLS = {'scripts/control_scope.py': {'verify_sections'}, 'pmrh/adapters/storage/io.py': {'_ConfinedReader.read', '_ConfinedReader._open_regular', '_ConfinedReader._check_unchanged', '_VerifiedBodyRead', '_BodyReadBudget', '_ConfinedReader.read_verified_body', '_BodyVisitor'}, 'pmrh/adapters/storage/pool.py': {'Pool.inspect'}, 'research_studio/changes.py': {'validator_identity', '_repair_kcs', '_validate', '_resolve_projection_locators', 'format_repair_evidence', '_FORMAT_WIRE_FIELDS', 'science_projection', '_error_diagnostic'}, 'research_studio/task_tools.py': {'tool_definitions', 'TaskTools.call'}, 'pmrh/adapters/storage/format.py': {'publication_schema'}, 'pmrh/application/control.py': {'Control.native', 'AuthorityRegistry.register_fast_ingress'}, 'pmrh/adapters/storage/journal.py': {'Journal._commit_record', 'Journal._publish', 'Journal.read_snapshot', 'Journal.history'}, 'pmrh/adapters/storage/control.py': {'scan', 'ControlStorage.acquire_native_slot', 'ControlStorage.execute', 'ControlStorage.acquire_slot', 'validate_record', 'ControlStorage.combined', 'ControlStorage.decision_record', 'ControlStorage.reduce', 'command', 'validate_entry', 'ControlStorage.event_schema', 'ControlStorage.validate_transition'}, 'pmrh/application/read_projections.py': {'budget_remaining', 'strategy_id', 'project_remaining', 'aggregate_project_remaining', 'strategy_current', '_cost'}, 'pmrh/domain/contracts.py': {'RESPONSE_SCHEMA'}, 'research_studio/contracts.py': {'validate_authoring', '_compile_authoring', '_compact_authoring_schema', 'authoring_contract', '_map_schema', 'schema_diagnostics'}, 'research_studio/execution.py': {'event', 'apply_event', '_request'}, 'research_studio/research_audit.py': {'seconds', 'policy', '_append_interval', 'PROGRESS', 'transition', 'authoring_schema', 'DEFAULT_POLICY', 'phase'}, 'research_studio/strategy.py': {'authoring_schema', '_schema_obj', 'PROPOSAL_SCHEMA', 'ROUTE_STATES'}, 'research_studio/version.py': {'RESPONSE_SCHEMA'}}
WHOLE = frozenset({'research_studio/knowledge_access.py','research_studio/storage_compat.py','research_studio/store.py',
 'scripts/architecture_deps.py','scripts/check_legacy_scope.py','scripts/storage_scope.py','config/architecture-exceptions.json'})
EDGES = frozenset({('research_studio/execution.py', 'pmrh/domain/native_settlement.py'), ('research_studio/storage_compat.py', 'pmrh/application/fastmath.py'), ('research_studio/research_audit.py', 'pmrh/domain/native_response.py'), ('research_studio/changes.py', 'pmrh/domain/native_response.py'), ('research_studio/storage_compat.py', 'pmrh/adapters/storage/control_fast.py'), ('research_studio/research_audit.py', 'pmrh/domain/native_settlement.py'), ('research_studio/knowledge_access.py', 'pmrh/domain/fastmath/validation.py'), ('research_studio/contracts.py', 'pmrh/domain/native_response.py'), ('research_studio/version.py', 'pmrh/domain/contracts.py'), ('research_studio/strategy.py', 'pmrh/domain/native_response.py'), ('research_studio/knowledge_access.py', 'pmrh/domain/fastmath/qualification.py'), ('research_studio/knowledge_access.py', 'pmrh/adapters/storage/journal.py'), ('research_studio/knowledge_access.py', 'pmrh/adapters/storage/io.py')})

SCOPE04_PREIMAGES = {'pmrh/application/read_projections.py': '4501f43496bea6fbd5773442138137092ef855064c9a90a37a0c04d19149146c', 'pmrh/domain/contracts.py': '23e82a9d0cfb3f1e10d957b203e21eb42b9793cf89f942cbe90263ad36eed1da', 'research_studio/contracts.py': '6b274390a91ef8063c9e32624942f980db63223a78484f4b2112de6e44352e4f', 'research_studio/execution.py': 'ffa90e5ca68af2136ece0b1545b2b6f825556c0ac11fdf16689a3ed25d4bcf31', 'research_studio/research_audit.py': 'bd39ad6b80109d5938aaa827b56de6b3b12117a7292b99f709586f615d0542e6', 'research_studio/strategy.py': '79ac1d86c05dfd0e0b09b47aa4843799c7ce0ea0842851a6b2d691b2d3ba123a', 'research_studio/version.py': 'f1c55ac148d998c260edc4f89e7a829d5a768fe57b8ba577333c6d6434cb4b23'}
SCOPE04_REEXPORTS = {'pmrh/application/read_projections.py': ['from pmrh.domain.native_settlement import _cost as _cost', 'from pmrh.domain.native_settlement import budget_remaining as budget_remaining', 'from pmrh.domain.native_settlement import project_remaining as project_remaining', 'from pmrh.domain.native_settlement import aggregate_project_remaining as aggregate_project_remaining', 'from pmrh.domain.native_settlement import strategy_id as strategy_id', 'from pmrh.domain.native_settlement import strategy_current as strategy_current'], 'pmrh/domain/contracts.py': [], 'research_studio/contracts.py': ['from pmrh.domain.native_response import authoring_contract as authoring_contract', 'from pmrh.domain.native_response import _compile_authoring as _compile_authoring', 'from pmrh.domain.native_response import _map_schema as _map_schema', 'from pmrh.domain.native_response import _compact_authoring_schema as _compact_authoring_schema', 'from pmrh.domain.native_response import schema_diagnostics as schema_diagnostics', 'from pmrh.domain.native_response import validate_authoring as validate_authoring'], 'research_studio/execution.py': ['from pmrh.domain.native_settlement import _request as _request'], 'research_studio/research_audit.py': ['from pmrh.domain.native_settlement import DEFAULT_POLICY as DEFAULT_POLICY', 'from pmrh.domain.native_response import PROGRESS as PROGRESS', 'from pmrh.domain.native_settlement import seconds as seconds', 'from pmrh.domain.native_settlement import policy as policy', 'from pmrh.domain.native_settlement import phase as phase', 'from pmrh.domain.native_settlement import _append_interval as _append_interval', 'from pmrh.domain.native_response import audit_authoring_schema as authoring_schema'], 'research_studio/strategy.py': ['from pmrh.domain.native_response import PROPOSAL_SCHEMA as PROPOSAL_SCHEMA', 'from pmrh.domain.native_response import ROUTE_STATES as ROUTE_STATES', 'from pmrh.domain.native_response import _schema_obj as _schema_obj', 'from pmrh.domain.native_response import strategy_authoring_schema as authoring_schema'], 'research_studio/version.py': ['from pmrh.domain.contracts import RESPONSE_SCHEMA as RESPONSE_SCHEMA'], 'research_studio/changes.py': ['from pmrh.domain.native_response import _FORMAT_WIRE_FIELDS as _FORMAT_WIRE_FIELDS', 'from pmrh.domain.native_response import _repair_kcs as _repair_kcs', 'from pmrh.domain.native_response import _resolve_projection_locators as _resolve_projection_locators', 'from pmrh.domain.native_response import science_projection as science_projection', 'from pmrh.domain.native_response import _error_diagnostic as _error_diagnostic']}
SCOPE04_SYMBOL_SHA256 = {'pmrh/application/read_projections.py': {'_cost': '4f2fd94623c1cda0880764fe01a04fd61c84ef6e43c399f041d1bc7f7da59200', 'budget_remaining': 'b8779b4fc9861b55f13510cdd9a47c235182319341bbb7b14879814e4a164b57', 'project_remaining': '4c946876cb3c34aef41578ba85ebcd4e8bc0a8703fdd4425b7658e5dbe6b1890', 'aggregate_project_remaining': 'fed077fa3ad30c57fe7d9770ede5b938d711e7015f71b3a44c382f3270163795', 'strategy_id': 'e53aef7ea4ccb4c405da2249ac4ac79203431203a9b9a57a3a01f0286cd11fdb', 'strategy_current': '44f56e64988aec8d8a5e1251fc9d1d1ed1e3e5f92429da62102ea81b51fac27a'}, 'pmrh/domain/contracts.py': {'RESPONSE_SCHEMA': 'f03d1be61b9bc6acc23204f7cf12c207290735f0a24e74cae43ba78e70a971b4'}, 'research_studio/contracts.py': {'authoring_contract': 'ae5ee90f6beb178b600f7599cba6559c301d1edbc6230033242cb762917c026c', '_compile_authoring': '14cf429d08e7b5b85e0cfd99959a260bd7d126423d12a43f2e39484b7bce2b64', '_map_schema': '086c8a04981dc63aa354bfc427266975158943dabd837fce0642409c2565b6d8', '_compact_authoring_schema': '2e82af2bb5601b4287b25c185a3ea90c83cd8aa704e46410f3e58d4a0fce4bd7', 'schema_diagnostics': '040c448520c6f532fbe7472c9ab00b22f6514e0b010b01c8f54e3677e4f3381f', 'validate_authoring': '8a051dc4134dea1177ccd7b95cc77711c47d9f3d057b1d1adf3d91160d260928'}, 'research_studio/execution.py': {'event': '11a453af0d0ad15e353da92131facb1cf3e8d112b52b44b334ba0f71a5a5a8f0', 'apply_event': '4edffacab3009b16b60f05aa3dead2ec80a5c18f6b1b681c141d4cb24a462131', '_request': '8da912ec1f4b1dda4aa4fa26506613a9de9c80c9bdcf8c8ebca0cb1b0fa116a3'}, 'research_studio/research_audit.py': {'authoring_schema': '79d11eedb2f37a9039054865ea0e975d8dcd78fa67608b388e5e84a4c2be1749', 'PROGRESS': 'ee70e0e27e0fc603e138ff2035add1c9e89ecf5d0964f6bd2df93378561dc5cd', 'DEFAULT_POLICY': '14b71fb2de134d47dbec53fe617ba9c106e63d1ca0a42b774529b9255d782656', 'seconds': 'b110fc5c74f66a7f581d07d51c4abf53b8580d2d68628d3cb021444d7377cb17', 'policy': '30c1446a15c70283f8c5664962657d83396a67443eeb7075b80461c59d1e5c1a', 'phase': 'd35a4e9d1d65f5a29945916b922924411717a17ad15b4910d0c68c060d912239', '_append_interval': '52ea3e49dea3c28ed6a51e47147b43d6a84e54fbae3f7700e01aeb6705aea9a9', 'transition': '4991a53ed260fea8317d567a71ba099e284c1934e1266c6e571528e37119dd8a'}, 'research_studio/strategy.py': {'_schema_obj': 'ef38c3fbc74668b536bbf14b0f820f95c793709921aef6a7b96857a2e91456d3', 'authoring_schema': '80e92897350d8999578206c9b08f8b275f492b3032007dfa530948b1e573ab07', 'PROPOSAL_SCHEMA': 'e255e386b8642bffa2ec3437c066761fd6284027fd5739d7ef42a4c295b29e30', 'ROUTE_STATES': '00231e0426df9007a1e4bfdd2b334925836f13516ffc9662ca73274984d09b90'}, 'research_studio/version.py': {'RESPONSE_SCHEMA': '0d4e073d84c491bc5b9e746ddf85edda1a00fa442687a96cea5d9035dd7f2046'}, 'research_studio/changes.py': {'_validate': '8539c4105f33fe6b2189ecdfdff9dc4770df5709cdeb8386a8295ca3f3f61264', '_FORMAT_WIRE_FIELDS': '406a3d15e49b2453e00b1d0a52124a8e027a0a874abad720d5c26a68fe309f47', '_repair_kcs': '645b28d040cb2330090e35eb76ba2b800de0dde7a99badfa3aa9a86a5dd1f59c', '_resolve_projection_locators': 'ddd1c9fc1730b9a4fc04f72959ba821560b6eac022d053386a5b57f0e9ba5516', 'science_projection': 'e2b481f9fbbc6cc27e92d28e26b67a099b53435d8ba60ba24d22907ff2a45181', '_error_diagnostic': '42efad2476a642402bc6696596bab9451163b636709e4689b9984db318fae690', 'format_repair_evidence': '551bca9b8c13b03ee18610677e47038695ed7b17483a936470446db9b6e30045'}}
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
    for n in ast.parse(raw).body:
        key=getattr(n,'name',None)
        if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name):key=n.targets[0].id
        if isinstance(n,ast.ImportFrom) and len(n.names)==1:key=n.names[0].asname
        if key==name:return n
    raise ValueError('Missing exact native symbol: '+name)


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
    if path=='scripts/control_scope.py':
        # Scope05 owns exactly one frozen whole-file delta, not arbitrary edits
        # to the named method or any other historical guard bytes.
        if hashlib.sha256(original).hexdigest()!='dace2caa8827070ef991af813de59bf0fec9616b8b01b2056ff9a848a21c7092' or hashlib.sha256(current).hexdigest()!='17c4ad8adc05f7c2d413a368caaeeda9c079ea9f2c1b75475b7ce17fdb0341dd':
            raise ValueError('Outside exact Scope05 guard hook')
        return True
    if path in SCOPE04_PREIMAGES and hashlib.sha256(original).hexdigest()!=SCOPE04_PREIMAGES[path]:
        raise ValueError('Scope04 preimage differs: '+path)
    for name,digest in SCOPE04_SYMBOL_SHA256.get(path,{}).items():
        actual=ast.dump(_symbol_node(current,name),include_attributes=False).encode()
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
