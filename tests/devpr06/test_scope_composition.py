"""Composed historical source guards; static bytes only, within original S2."""
import ast
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import control_scope, storage_scope

ROOT = Path('/source')
BASE = Path('/baseline')


class ScopeCompositionTests(unittest.TestCase):
    def test_frozen_boundary_and_current_source_both_satisfy_scopes(self):
        for path in storage_scope.SYMBOLS:
            with self.subTest(path=path):
                original=(BASE/path).read_bytes();current=(ROOT/path).read_bytes()
                storage_scope.verify_sections(path,original,current)
                if path in storage_scope.PRECONTROL_PATHS:
                    boundary=storage_scope._precontrol_boundary(path,original)
                    storage_scope.verify_sections(path,original,boundary)
                    control_scope.verify_sections(path,boundary,current)
                    self.assertNotEqual(boundary,current)
        # Older guard tables and source fingerprints retain their exact scope.
        self.assertEqual(set(storage_scope.ORIGINAL_SOURCE_SEGMENT_SHA256),set(storage_scope.SYMBOLS))
        for path in storage_scope.SYMBOLS:
            self.assertEqual(set(storage_scope.ORIGINAL_SOURCE_SEGMENT_SHA256[path]),set(storage_scope.SYMBOLS[path]))

    def test_current_scope_rejects_outside_symbols_alias_and_science_changes(self):
        for path in storage_scope.SYMBOLS:
            original=(BASE/path).read_bytes();current=(ROOT/path).read_bytes()
            with self.subTest(path=path,attack='extra-symbol'),self.assertRaises(ValueError):
                storage_scope.verify_sections(path,original,current+b'\nforbidden_extra_symbol = True\n')
            imports=storage_scope.IMPORTS[path]
            if imports:
                before=imports[0].encode();after=before+b'_invalid_alias'
                self.assertEqual(current.count(before),1)
                with self.subTest(path=path,attack='alias'),self.assertRaises(ValueError):
                    storage_scope.verify_sections(path,original,current.replace(before,after,1))
        # Exact scientific functions and non-owned methods cannot hide inside a
        # file that also contains a permitted DEV06 symbol.
        for path,symbol in [('research_studio/changes.py','live_check'),
                            ('research_studio/host_pool.py','reconcile_pool')]:
            original=(BASE/path).read_bytes();current=(ROOT/path).read_bytes()
            node=next(n for n in ast.parse(current).body if isinstance(n,ast.FunctionDef) and n.name==symbol)
            lines=current.splitlines(keepends=True);lines.insert(node.body[0].lineno-1,b'    forbidden_guard_edit = True\n')
            with self.subTest(path=path,symbol=symbol),self.assertRaises(ValueError):
                storage_scope.verify_sections(path,original,b''.join(lines))
        path='research_studio/native_main.py';original=(BASE/path).read_bytes();current=(ROOT/path).read_bytes()
        cls=next(n for n in ast.parse(current).body if isinstance(n,ast.ClassDef) and n.name=='Service')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and 'Service.'+n.name not in control_scope.SYMBOLS[path])
        lines=current.splitlines(keepends=True);lines.insert(method.body[0].lineno-1,b'        forbidden_guard_edit = True\n')
        with self.assertRaises(ValueError):storage_scope.verify_sections(path,original,b''.join(lines))

    def test_frozen_original_artifact_and_authority_fail_closed(self):
        path='research_studio/changes.py';original=(BASE/path).read_bytes();current=(ROOT/path).read_bytes()
        tampered=original.replace(b'def validator_identity(',b'def validator_identity( ',1)
        self.assertNotEqual(original,tampered)
        self.assertEqual(ast.dump(ast.parse(original)),ast.dump(ast.parse(tampered)))
        with self.assertRaisesRegex(ValueError,'Frozen DEV05 source symbol differs'):
            storage_scope.verify_sections(path,tampered,current)
        with patch.object(storage_scope.ast,'get_source_segment',return_value=None):
            with self.assertRaisesRegex(ValueError,'Frozen DEV05 source segment missing'):
                storage_scope.verify_sections(path,original,current)
        with self.assertRaisesRegex(ValueError,'Frozen DEV05 boundary original differs'):
            storage_scope.verify_sections(path,original+b'\n',current)
        artifact=Path(storage_scope.__file__).with_name('storage_scope_precontrol.json');real=Path.read_bytes
        raw=real(artifact)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),storage_scope.PRECONTROL_SHA256)
        def corrupted(p):return real(p)+b' ' if p==artifact else real(p)
        with patch.object(Path,'read_bytes',corrupted):
            with self.assertRaisesRegex(ValueError,'Frozen pre-control boundary artifact differs'):
                storage_scope.verify_sections(path,original,current)
        def missing(p):
            if p==artifact:raise FileNotFoundError(str(p))
            return real(p)
        with patch.object(Path,'read_bytes',missing),self.assertRaises(FileNotFoundError):
            storage_scope.verify_sections(path,original,current)
        with patch.object(control_scope,'BASE','0'*40):
            with self.assertRaisesRegex(ValueError,'Frozen scope boundary chain differs'):
                storage_scope.verify_sections(path,original,current)
        wider=[*control_scope.SYMBOLS[path],'live_check']
        with patch.dict(control_scope.SYMBOLS,{path:wider}):
            with self.assertRaisesRegex(ValueError,'Exact DEV06 boundary symbols differ'):
                storage_scope.verify_sections(path,original,current)
