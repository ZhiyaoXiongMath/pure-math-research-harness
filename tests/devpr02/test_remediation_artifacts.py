"""REV02-CI-01: freeze unique source-defined IDs, not a mutable count or old OK.

All evidence here is a synthetic fixture, never an actual CI attestation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import offline_contracts
from scripts import verify_devpr02_artifacts as A

SHA, TREE = 'a' * 40, 'b' * 40


def result_log(ids):
    records = ''.join(name.rsplit('.', 1)[-1] + ' (' + name + ') ... ok\n' for name in ids)
    return (records + '\nRan ' + str(len(ids)) + ' tests in 0.001s\n\nOK\n').encode()


class ArtifactRemediation(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='pmrh-ci-remediation-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'source'
        for rel in (*A.SOURCE_SCRIPTS, 'pmrh/__init__.py', 'pmrh/ports/example.py'):
            path = self.source / rel; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# Synthetic source, not an actual checkout\n')
        self.test_file = self.source / 'tests/devpr02/test_example.py'
        self.test_file.parent.mkdir(parents=True)
        self.test_file.write_text('import unittest\nclass Example(unittest.TestCase):\n'
                                  '    def test_one(self): pass\n    def test_two(self): pass\n')
        (self.root / 'ast').mkdir(); (self.root / 'offline').mkdir()
        self.ids = ('tests.devpr02.test_example.Example.test_one', 'tests.devpr02.test_example.Example.test_two')
        self.log = result_log(self.ids)
        self.receipt = {
            'schema_version':'pmrh.devpr02-ci-receipt/1.0','dto_schema_version':'pmrh.ports/1.0','suite':'devpr02',
            'source_sha':SHA,'checkout_sha':SHA,'checkout_tree':TREE,'exit_code':0,'execution_error':None,
            'pass_fail_status':'PASS','source_unchanged':True,'test_command':['synthetic-python',*offline_contracts.COMMAND_TAIL],
            'test_environment':{'guard':'PYTHON_LEVEL_DEFENSE_IN_DEPTH_ONLY_NOT_OS_SANDBOX','isolated_home':True,
                'synthetic_only':True,'python_minor':'3.11','ci_infrastructure_network':'NOT_MEASURED'},
            'artifact_identity':'pmrh-devpr02-contracts-'+SHA+'-py3.11',
            'research_model_calls':{'count':None,'zero_calls_verified':False,'observed_provider_events':'NOT_MEASURED'},
            'known_unexecuted_checks':offline_contracts.KNOWN_UNEXECUTED,'test_count':2}
        self.refresh_source()
        self.save(self.log, 2)

    def refresh_source(self):
        sources = A.source_fingerprints(self.source)
        self.receipt['source_files_sha256'] = sources
        graph = {'schema':'pmrh.ast-import-baseline/1','architecture_violations':[],'syntax_errors':[],
            'direct_graph':{},'transitive_graph':{},'strongly_connected_components':[],'source_sha256':sources,
            'named_architectural_couplings':[],'counts':{'unresolved_new_layer_imports':0}}
        (self.root / 'ast/dependency-graph.json').write_text(json.dumps(graph))
        (self.root / 'ast/architecture-audit.md').write_text('# DEV-PR-01 synthetic fixture\n')

    def save(self, log, count):
        (self.root / 'offline/unittest.log').write_bytes(log)
        self.receipt['raw_log_sha256'] = hashlib.sha256(log).hexdigest()
        self.receipt['test_count'] = count
        (self.root / 'offline/receipt.json').write_text(json.dumps(self.receipt))

    def validate(self):
        return A.validate(self.root, SHA, TREE, self.source)

    def test_ARTIFACT_positive_all_frozen_IDs_validate(self):
        result = self.validate()
        self.assertEqual(result['test_count'], 2)
        self.assertEqual(result['test_ids'], list(self.ids))
        self.assertEqual(result['test_ids_sha256'], hashlib.sha256('\n'.join(self.ids).encode()).hexdigest())

    def test_ARTIFACT_terminal_failure_after_OK_is_rejected(self):
        self.save(self.log + b'\nFAILED (errors=1)\n', 2)
        with self.assertRaisesRegex(ValueError, 'final success footer'):
            self.validate()

    def test_ARTIFACT_one_test_with_matching_receipt_is_rejected(self):
        self.save(result_log(self.ids[:1]), 1)
        with self.assertRaisesRegex(ValueError, 'complete frozen source suite'):
            self.validate()

    def test_ARTIFACT_duplicate_test_IDs_with_matching_count_rejected(self):
        self.save(result_log((self.ids[0], self.ids[0])), 2)
        with self.assertRaisesRegex(ValueError, 'Duplicate test identities'):
            self.validate()

    def test_unknown_or_inconsistent_method_identity_rejected(self):
        self.save(result_log((self.ids[0], 'tests.devpr02.test_example.Example.test_other')), 2)
        with self.assertRaisesRegex(ValueError, 'complete frozen source suite'):
            self.validate()
        self.save(self.log.replace(b'test_one (', b'test_false ('), 2)
        with self.assertRaisesRegex(ValueError, 'inconsistent identity'):
            self.validate()

    def test_nonpassing_individual_record_cannot_hide_behind_OK(self):
        for status in (b'ERROR', b'FAIL', b'skipped synthetic'):
            self.save(self.log.replace(b'... ok', b'... ' + status, 1), 2)
            with self.assertRaises(ValueError):
                self.validate()

    def test_literal_FAILURE_fixture_output_is_not_a_false_failure(self):
        self.save(b'Synthetic expected error contains FAILED (errors=1), not a result\n' + self.log, 2)
        self.assertEqual(self.validate()['status'], 'PASS')

    def test_new_source_defined_tests_automatically_extend_inventory(self):
        self.test_file.write_text(self.test_file.read_text() + '    def test_three(self): pass\n')
        self.refresh_source()
        self.save(self.log, 2)
        with self.assertRaisesRegex(ValueError, 'complete frozen source suite'):
            self.validate()
        ids = tuple(sorted((*self.ids, 'tests.devpr02.test_example.Example.test_three')))
        self.save(result_log(ids), 3)
        self.assertEqual(self.validate()['test_ids'], list(ids))

    def test_inventory_is_static_and_does_not_execute_source(self):
        self.test_file.write_text('raise RuntimeError("must never execute")\n' + self.test_file.read_text())
        self.assertEqual(A.expected_test_ids(self.source), self.ids)

    def test_duplicate_source_methods_cannot_silently_shrink_inventory(self):
        self.test_file.write_text(self.test_file.read_text() + '    def test_one(self): pass\n')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            A.expected_test_ids(self.source)

    def test_dynamic_collection_and_unaccounted_inheritance_fail_closed(self):
        cases = (
            'import unittest\ndef load_tests(*args): pass\n',
            'import unittest\nclass Case(Base):\n    def test_inherited(self): pass\n',
            'import unittest\nif False:\n    class Case(unittest.TestCase):\n        def test_hidden(self): pass\n',
            'import unittest\nclass Case(unittest.TestCase):\n    test_alias = lambda self: None\n',
            'import unittest\nclass Case(unittest.TestCase):\n    def test_one(self): pass\nCase = None\n',
        )
        for source in cases:
            self.test_file.write_text(source)
            with self.subTest(source=source), self.assertRaises(ValueError):
                A.expected_test_ids(self.source)

    def test_test_identity_overrides_and_decorators_fail_closed(self):
        for source in (
            'import unittest\nclass Case(unittest.TestCase):\n    def id(self): return "fake"\n    def test_one(self): pass\n',
            'import unittest\nclass Case(unittest.TestCase):\n    @unittest.skip("fixture")\n    def test_one(self): pass\n',
        ):
            self.test_file.write_text(source)
            with self.assertRaises(ValueError):
                A.expected_test_ids(self.source)

    def test_contradictory_footer_cannot_be_hidden_by_appending_another_OK(self):
        self.save(self.log + b'FAILED (errors=1)\nRan 2 tests in 0.001s\n\nOK\n', 2)
        with self.assertRaisesRegex(ValueError, 'terminal material'):
            self.validate()
