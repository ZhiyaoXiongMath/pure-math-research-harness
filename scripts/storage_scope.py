"""DEV05 exact owned symbols; preserves the original and DEV03/04 baselines."""
import ast
import base64
import hashlib
import json
from pathlib import Path
try:
    from scripts import control_scope, fastmath_scope
except ModuleNotFoundError:
    import control_scope, fastmath_scope

BASE = '2c65af1a407c159d6768867bf25c03566c4657c1'
TREE = '2b141b07ea297aa37d6ffb2d85b21e8b6c07bd5c'
SYMBOLS = {'research_studio/changes.py': ['validator_identity'],
 'research_studio/host_pool.py': ['HOST_LIMIT',
                                  'PROJECT_LIMIT',
                                  'INFLIGHT',
                                  'instance_key',
                                  'allocations',
                                  '_view',
                                  'read_status'],
 'research_studio/language.py': ['DEFAULT', 'policy'],
 'research_studio/main_session.py': ['view'],
 'research_studio/native_main.py': ['SCHEMA', 'GATE_REVISION', 'desired', 'view'],
 'research_studio/research_audit.py': ['effective_guidance', 'view'],
 'research_studio/resources.py': ['SERIALIZED_BYTES',
                                  'DISK_MARGIN_BYTES',
                                  'json_bytes',
                                  'bounded_canonical',
                                  'disk_preflight'],
 'research_studio/scheduler.py': ['_cost',
                                  'budget_remaining',
                                  'project_remaining',
                                  'aggregate_project_remaining'],
 'research_studio/strategy.py': ['strategy_id', 'current'],
 'research_studio/util.py': ['now',
                             'safe_path',
                             'read',
                             'fsync_dir',
                             '_same_file_bytes',
                             '_publication_temp',
                             'immutable',
                             'atomic'],
 'research_studio/version.py': ['SCHEMA_VERSION', 'COMMIT_SCHEMA'],
 'research_studio/views.py': ['scope_refs', 'status']}

IMPORTS = {'research_studio/changes.py': [],
 'research_studio/host_pool.py': ['from pmrh.adapters.storage.pool_read import HOST_LIMIT as HOST_LIMIT',
                                  'from pmrh.adapters.storage.pool_read import PROJECT_LIMIT as '
                                  'PROJECT_LIMIT',
                                  'from pmrh.adapters.storage.pool_read import INFLIGHT as INFLIGHT',
                                  'from pmrh.adapters.storage.pool_read import instance_key as instance_key',
                                  'from pmrh.adapters.storage.pool_read import allocations as allocations',
                                  'from pmrh.adapters.storage.pool_read import _view as _view',
                                  'from pmrh.adapters.storage.pool_read import read_status as read_status'],
 'research_studio/language.py': ['from pmrh.adapters.storage.native_format import DEFAULT as DEFAULT',
                                 'from pmrh.adapters.storage.native_format import policy as policy'],
 'research_studio/main_session.py': [],
 'research_studio/native_main.py': ['from pmrh.application.read_projections import NATIVE_SCHEMA as SCHEMA',
                                    'from pmrh.application.read_projections import GATE_REVISION as '
                                    'GATE_REVISION',
                                    'from pmrh.application.read_projections import native_desired as desired',
                                    'from pmrh.application.read_projections import native_view as view'],
 'research_studio/research_audit.py': ['from pmrh.application.read_projections import effective_guidance as '
                                       'effective_guidance',
                                       'from pmrh.application.read_projections import audit_view as view'],
 'research_studio/resources.py': ['from pmrh.adapters.storage.io import SERIALIZED_BYTES as SERIALIZED_BYTES',
                                  'from pmrh.adapters.storage.io import DISK_MARGIN_BYTES as '
                                  'DISK_MARGIN_BYTES',
                                  'from pmrh.adapters.storage.io import json_bytes as json_bytes',
                                  'from pmrh.adapters.storage.io import bounded_canonical as '
                                  'bounded_canonical',
                                  'from pmrh.adapters.storage.io import disk_preflight as disk_preflight'],
 'research_studio/scheduler.py': ['from pmrh.application.read_projections import _cost as _cost',
                                  'from pmrh.application.read_projections import budget_remaining as '
                                  'budget_remaining',
                                  'from pmrh.application.read_projections import project_remaining as '
                                  'project_remaining',
                                  'from pmrh.application.read_projections import aggregate_project_remaining '
                                  'as aggregate_project_remaining'],
 'research_studio/strategy.py': ['from pmrh.application.read_projections import strategy_id as strategy_id',
                                 'from pmrh.application.read_projections import strategy_current as current'],
 'research_studio/util.py': ['from pmrh.adapters.storage.io import now as now',
                             'from pmrh.adapters.storage.io import safe_path as safe_path',
                             'from pmrh.adapters.storage.io import read as read',
                             'from pmrh.adapters.storage.io import fsync_dir as fsync_dir',
                             'from pmrh.adapters.storage.io import _same_file_bytes as _same_file_bytes',
                             'from pmrh.adapters.storage.io import _publication_temp as _publication_temp',
                             'from pmrh.adapters.storage.io import atomic as atomic'],
 'research_studio/version.py': ['from pmrh.adapters.storage.native_format import SCHEMA_VERSION as '
                                'SCHEMA_VERSION',
                                'from pmrh.adapters.storage.native_format import COMMIT_SCHEMA as '
                                'COMMIT_SCHEMA'],
 'research_studio/views.py': ['from pmrh.application.read_projections import scope_refs as scope_refs']}

ORIGINAL_SOURCE_SEGMENT_SHA256 = {'research_studio/changes.py': {'validator_identity': 'dff31af3a2ad53ce3e17af18d66b6b9f59a805024d79f081837fcbab49491c45'},
 'research_studio/host_pool.py': {'HOST_LIMIT': '33ebb52cd05188c36367d0d8c53c9a8125b79750b2918c6e797980348f78a60c',
                                  'INFLIGHT': '7d0d1cc5f681c3c1c20183fd8c731da413eaa86fae91364cee3dd4ffc00e016c',
                                  'PROJECT_LIMIT': 'f7eedb49ffc02bf234882aff8ee19c171a895e05c5f2e71113216a00d24a5811',
                                  '_view': '0cd1fbef3272bbbc8f23469013a56b0607ef687eb0c2dc1e9aa5ddee091cfc42',
                                  'allocations': 'f528f300c065096a20394ee932fc84ae2905a91f0a32e63e2ec8c10524c34f4f',
                                  'instance_key': '5a6cf1885a1f1eda64f82b37a72218fb4e9c8252d17eac45a0d74449eaa573ff',
                                  'read_status': 'f86bc351d86b6b17fb6becf771b31121118571f5d116fb7720c4350a6ed03f62'},
 'research_studio/language.py': {'DEFAULT': '54d65e85f0e797706d9eb2278a52cbcfaa2eed428c123fdb16c2e10c9e1435ac',
                                 'policy': '9687012bf7d4815adeb5e0b6990d3c5d4a52f1e0097808ccd8d86fe9278a613f'},
 'research_studio/main_session.py': {'view': '5fa53a665be7af0fc76e2069fb74117dbc3cddf8dae1672c3d455fc528492825'},
 'research_studio/native_main.py': {'GATE_REVISION': '067c67e0f6fda8350e74234fa1c1fdba84807f9f920f1a7edae66444bae31d5a',
                                    'SCHEMA': 'e176c4417e0fbe72db6ef9958df9bfb35e667db4e1b8a24fe7bb5d344823105a',
                                    'desired': '08cb976fb550d1dfce1d3e4c3037a353e64c61fcab340129c5bab76dd74497b2',
                                    'view': 'a213d4777f02458f23c21c78caa93bab156deb33ce487feae591264dde774913'},
 'research_studio/research_audit.py': {'effective_guidance': '686f51916721c28fa6c9b2bfa781d64755768ec3a07e5fea94fb3bd4542bf930',
                                       'view': 'c184cb558d8574a3c54ec779ef4c37914ab1410f0a86dfb259ae4fe7257933ac'},
 'research_studio/resources.py': {'DISK_MARGIN_BYTES': '59e726ce5b187178df8dccc6cd5e65ccf7af7652a0675c4955d48d230370e62e',
                                  'SERIALIZED_BYTES': '593118acd922a979d9fc0022d028c470922d92321053eaeb18413062336955f6',
                                  'bounded_canonical': '9ce8f457a198be005601828b7bf054126587cad1b5cab3a3e6c2a7ae0087ec6d',
                                  'disk_preflight': 'cbf089f0a1e353716dccc7de55c1c24c061b86fdbb709ab03f66451b66d7e525',
                                  'json_bytes': 'a55bf269aa11922de09cf07a6ba8283d809a572c050e3f70fe541e88b24fb924'},
 'research_studio/scheduler.py': {'_cost': '824162ea4b3c8aec7073b597ff3d83a25f7fd9fed0a794aaa31e7bebc886f7d1',
                                  'aggregate_project_remaining': 'ec7100c04601f6f930f30aa5dd5e5112d7b30cbf6c5608d4cb3a2820a4c17b63',
                                  'budget_remaining': '3a1a1ee1d88eb9b7bcecff052de559e0d53c0d8ba1f91638d1602ee91095c09f',
                                  'project_remaining': 'fb75e5f9ba9e0f521befe52cb58a0997db2d8e2c2418a23a36ba0f98d3fa8507'},
 'research_studio/strategy.py': {'current': '371df5c54835254577069925e792414d6ad0732b9039d061a16922ffe272e9e8',
                                 'strategy_id': 'de15ffd278c3c70b95fa38d1dc62cdd2d04f1a9d709eebb642351912a25c77a5'},
 'research_studio/util.py': {'_publication_temp': 'caa19483deb8cacca8251216c0a7e64fbc1ce613885ce3a338a645472f64dec6',
                             '_same_file_bytes': '803aa2477b851f8c15ec8fcef8ef35f2485fa05c5493b8e182191ebc3a38f341',
                             'atomic': '2ee51f9e29d7851b8bf768a30817a13c406f0e4335e15e900a5330a207124fe5',
                             'fsync_dir': '83ec133b129aca4538d33a74ab233dddf52d3ac43d9b3a08eef132be9163eb3f',
                             'immutable': 'f3a45d1ed31a675f8f25c15bdae2a2fcae07194442f38d083bbc9b7772e9f636',
                             'now': 'a1cf79fcf5b0f575096779d20be6f20a652c98bb9c85bc31b42b1d31c9ac9c23',
                             'read': '29236f7edae68cd02821d40a636b555eb15908f056d22ce911012b123961d9d2',
                             'safe_path': '1af17fffcd85d674f72af3094202c3df888c470cb2744c841d4a4170e7a1411c'},
 'research_studio/version.py': {'COMMIT_SCHEMA': 'f13f2fd09d1564ccdd3f57d4db060b77d95ebb0a728fdbc0de55c2a737010851',
                                'SCHEMA_VERSION': 'd72214f8980e14c5a49c919b93724782e6eb9a4df2856a859a9cb7bdc32dbbae'},
 'research_studio/views.py': {'scope_refs': '0c0ae3c4426e82874ceb79e45116e216e8b45d1deb7630149e49cfe2883df39d',
                              'status': '0d7a003c778c2138cc423ffd1ae9d0382a355c8194970ccfc66f36596f44b020'}}

OWNED_WHOLE = frozenset({'research_studio/store.py', 'research_studio/storage_compat.py', 'research_studio/readonly_query.py'})
PATHS = frozenset(SYMBOLS) | OWNED_WHOLE

TEST_SEAM_PATH = 'tests/devpr03/test_queries.py'
TEST_SEAM_METHOD = 'test_Q04_head_publication_during_query_keeps_main_on_selected_commit'
TEST_SEAM_BASE_SHA256 = '3c19d658b7ddfd6d49028a4c1e12ed9e9c6a962cbc06c6ea50e5014c965faad1'


def verify_test_seam(original, current):
    """SCOPE-02: one mechanical hook change, all other bytes/AST preserved."""
    if hashlib.sha256(original).hexdigest() != TEST_SEAM_BASE_SHA256:
        raise ValueError('SCOPE-02 baseline test bytes differ')
    def split(raw):
        tree = ast.parse(raw)
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'QueryTests']
        methods = [n for c in classes for n in c.body
                   if isinstance(n, ast.FunctionDef) and n.name == TEST_SEAM_METHOD]
        if len(classes) != 1 or len(methods) != 1 or methods[0].decorator_list:
            raise ValueError('SCOPE-02 exact undecorated test method required')
        method = methods[0]; lines = raw.splitlines(keepends=True)
        body = b''.join(lines[method.lineno-1:method.end_lineno])
        outside = b''.join(lines[:method.lineno-1] + lines[method.end_lineno:])
        classes[0].body.remove(method)
        return body, outside, ast.dump(tree, include_attributes=False)
    old, old_bytes, old_ast = split(original)
    new, new_bytes, new_ast = split(current)
    if old_bytes != new_bytes or old_ast != new_ast:
        raise ValueError('Outside SCOPE-02 test method changed')
    replacements = (
        (b'        head = self.existing()\n',
         b'        from pmrh.application import read_projections\n        head = self.existing()\n'),
        (b'original = main_session.view', b'original = read_projections.main_view'),
        (b'def publish_before_main(store, iid, **kwargs):', b'def publish_before_main(snapshot, iid, **kwargs):'),
        (b'return original(store, iid, **kwargs)', b'return original(snapshot, iid, **kwargs)'),
        (b"changed(main_session, 'view', publish_before_main)",
         b"changed(read_projections, 'main_view', publish_before_main)"),
    )
    for before, after in replacements:
        if old.count(before) != 1:
            raise ValueError('SCOPE-02 baseline hook differs')
        old = old.replace(before, after, 1)
    if new != old:
        raise ValueError('SCOPE-02 permits only the exact hook migration; assertions and publication stay unchanged')



# Exact bytes at the accepted DEV05 / pre-DEV06 boundary. Compact replacements
# reconstruct those sources from the already frozen DEV05 input; no Git or
# additional fixture mount is needed inside S2. These hashes are not AST hashes.
PRECONTROL_PATHS = frozenset(['research_studio/changes.py', 'research_studio/host_pool.py', 'research_studio/native_main.py', 'research_studio/scheduler.py', 'research_studio/strategy.py'])
PRECONTROL_SHA256 = 'b427aed90b79ab9e948ab93d0de6d96c29cfed0bd642717549135d8995ab5e85'


def _precontrol_boundary(path, original):
    raw = Path(__file__).with_name('storage_scope_precontrol.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != PRECONTROL_SHA256:
        raise ValueError('Frozen pre-control boundary artifact differs')
    data = json.loads(raw)
    if ((data['dev05_base'], data['dev05_tree']) != (BASE, TREE) or
            (data['dev06_base'], data['dev06_tree']) != (control_scope.BASE, control_scope.TREE) or
            set(data['files']) != PRECONTROL_PATHS or
            set(SYMBOLS) & set(control_scope.SYMBOLS) != PRECONTROL_PATHS):
        raise ValueError('Frozen scope boundary chain differs')
    row = data['files'][path]
    if row['symbols'] != control_scope.SYMBOLS[path]:
        raise ValueError('Exact DEV06 boundary symbols differ: '+path)
    if hashlib.sha256(original).hexdigest() != row['original_sha256']:
        raise ValueError('Frozen DEV05 boundary original differs: '+path)
    parts = []; position = 0
    for start, end, replacement in row['replacements']:
        if not 0 <= position <= start <= end <= len(original):
            raise ValueError('Frozen scope boundary replacement bounds differ: '+path)
        parts.extend((original[position:start], replacement.encode('utf-8')))
        position = end
    boundary = b''.join((*parts, original[position:]))
    if hashlib.sha256(boundary).hexdigest() != row['boundary_sha256']:
        raise ValueError('Frozen pre-control source differs: '+path)
    return boundary


def verify_sections(path, original, current):
    if path in OWNED_WHOLE:
        return  # r1 explicitly owns the shared engine/facade and query wiring.
    def name(node):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)): return node.name
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name): return node.targets[0].id
        return None
    def dump(node):return ast.dump(node, include_attributes=False)
    original_text = original.decode('utf-8')
    before, after = ast.parse(original_text), ast.parse(current)
    for node in before.body:
        symbol = name(node)
        if symbol in SYMBOLS[path]:
            segment = ast.get_source_segment(original_text, node)
            if segment is None:
                raise ValueError('Frozen DEV05 source segment missing: '+path+':'+symbol)
            if hashlib.sha256(segment.encode('utf-8')).hexdigest() != ORIGINAL_SOURCE_SEGMENT_SHA256[path][symbol]:
                raise ValueError('Frozen DEV05 source symbol differs: '+path+':'+symbol)
    approved = {dump(ast.parse(row).body[0]) for row in IMPORTS[path]}
    def outside(tree):
        return [dump(n) for n in tree.body if name(n) not in SYMBOLS[path] and dump(n) not in approved]
    boundary = _precontrol_boundary(path, original) if path in PRECONTROL_PATHS else None
    # Original segment/hash/boundary diagnostics precede the newer stage.
    # Exact historical boundaries remain valid inputs to this direct API.
    if current != boundary and path in fastmath_scope.SYMBOLS:
        data = fastmath_scope.oracle()
        parent = base64.b64decode(data['files'][path]['bytes_base64'], validate=True)
        if current != parent:
            fastmath_scope.verify_file(path, parent, current)
        current = parent
        after = ast.parse(current)
    inherited = ast.parse(boundary) if boundary is not None else after
    if outside(before) != outside(inherited):
        raise ValueError('Outside DEV05 exact symbols changed: '+path)
    if boundary is not None:
        # Compose two independent obligations, never a union of allowed symbols.
        # The current DEV05 aliases/non-DEV06 bodies must still equal this exact
        # accepted boundary; DEV06 cannot reopen earlier ownership wholesale.
        control_scope.verify_sections(path, boundary, current)
    actual = {dump(n) for n in after.body if isinstance(n, ast.ImportFrom)
              and (n.module or '').startswith(('pmrh.adapters.', 'pmrh.application.'))}
    if actual != approved:
        raise ValueError('DEV05 alias imports differ: '+path)

EDGES = frozenset([('research_studio/host_pool.py', 'pmrh/adapters/storage/pool_read.py'),
 ('research_studio/language.py', 'pmrh/adapters/storage/native_format.py'),
 ('research_studio/main_session.py', 'pmrh/application/read_projections.py'),
 ('research_studio/native_main.py', 'pmrh/application/read_projections.py'),
 ('research_studio/readonly_query.py', 'pmrh/adapters/storage/__init__.py'),
 ('research_studio/readonly_query.py', 'pmrh/adapters/storage/io.py'),
 ('research_studio/readonly_query.py', 'pmrh/adapters/storage/journal.py'),
 ('research_studio/readonly_query.py', 'pmrh/adapters/storage/pool_read.py'),
 ('research_studio/readonly_query.py', 'pmrh/application/__init__.py'),
 ('research_studio/readonly_query.py', 'pmrh/application/read_projections.py'),
 ('research_studio/research_audit.py', 'pmrh/application/read_projections.py'),
 ('research_studio/resources.py', 'pmrh/adapters/storage/io.py'),
 ('research_studio/scheduler.py', 'pmrh/application/read_projections.py'),
 ('research_studio/storage_compat.py', 'pmrh/adapters/storage/journal.py'),
 ('research_studio/store.py', 'pmrh/adapters/storage/journal.py'),
 ('research_studio/strategy.py', 'pmrh/application/read_projections.py'),
 ('research_studio/util.py', 'pmrh/adapters/storage/io.py'),
 ('research_studio/version.py', 'pmrh/adapters/storage/native_format.py'),
 ('research_studio/views.py', 'pmrh/application/read_projections.py')])
QUERY_TARGETS = ['pmrh/adapters/storage/__init__.py',
 'pmrh/adapters/storage/io.py',
 'pmrh/adapters/storage/journal.py',
 'pmrh/adapters/storage/pool_read.py',
 'pmrh/application/__init__.py',
 'pmrh/application/read_projections.py',
 'pmrh/ports/dto/__init__.py',
 'pmrh/ports/dto/core.py',
 'pmrh/ports/dto/enums.py',
 'research_studio/util.py']
QUERY_LEGACY_REACH = {'pmrh/__main__.py': ['research_studio/readonly_query.py', 'research_studio/util.py'],
 'pmrh/cli.py': ['research_studio/readonly_query.py', 'research_studio/util.py']}


def verify_dev11_sections(path, original, current, root=None):
    """Explicit final-to-parent composition; historical callers stay unchanged."""
    parent = fastmath_scope.preintegration(path, current, root)
    return verify_sections(path, original, parent)
