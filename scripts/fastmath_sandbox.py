"""DEV11 finite synthetic test entrypoint; stdlib only until isolation probes."""
import argparse
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest


def probes(host_net, label):
    result={'actor':label}
    for tree in ('/source','/baseline'):
        target=Path(tree)/'README.md'
        if not target.is_file():raise RuntimeError('Missing read-only tree')
        try:fd=os.open(target,os.O_WRONLY|os.O_APPEND)
        except OSError as exc:
            if exc.errno not in (errno.EROFS,errno.EACCES,errno.EPERM):raise
            result[tree+'_append_denied']=repr(exc)
        else:
            os.close(fd);raise RuntimeError('Read-only tree permitted append-open')
    scratch=Path('/tmp/tests')/('probe-'+label)
    scratch.write_bytes(b'DEV11 isolated synthetic probe');scratch.unlink()
    result['scratch_write']='PASS'
    for path in ('/home','/root/.ssh','/outside-canary','/input','/control'):
        if Path(path).exists():raise RuntimeError('Outside path exposed: '+path)
    if os.readlink('/proc/self/ns/net')==host_net:raise RuntimeError('Network namespace not isolated')
    for family, address in ((socket.AF_INET,('198.51.100.1',443)),(socket.AF_INET6,('2001:db8::1',443,0,0))):
        sock=None
        try:
            sock=socket.socket(family,socket.SOCK_STREAM);sock.settimeout(1);sock.connect(address)
        except OSError as exc:
            if exc.errno not in (errno.ENETUNREACH,errno.EPERM,errno.EACCES,errno.EAFNOSUPPORT):raise
            result[str(family)]=repr(exc)
        else:raise RuntimeError('External network reachable')
        finally:
            if sock is not None:sock.close()
    if os.environ.get('HOME')!='/tmp/home' or os.environ.get('TMPDIR')!='/tmp/tests':raise RuntimeError('Fake HOME/TMP missing')
    allowed={'PATH','HOME','TMPDIR','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE','PIP_NO_INDEX','LANG','PWD','LC_CTYPE'}
    if not set(os.environ)<=allowed:raise RuntimeError('Unexpected inherited environment')
    result['environment']=sorted(os.environ)
    return result


def install_guard():
    original=dict(os.environ)
    def reopen_arguments(executable,argv):
        return (executable==sys.executable and type(argv) in (list,tuple) and
            len(argv)==5 and list(argv[:4])==[sys.executable,'-B','/source/scripts/fastmath_sandbox.py','--reopen'] and
            type(argv[4]) is str and str(Path(argv[4]))==argv[4] and
            Path(argv[4]).is_relative_to('/tmp/tests') and Path(argv[4])!=Path('/tmp/tests') and
            '..' not in Path(argv[4]).parts)
    def audit(event,args):
        if event.startswith('socket.') or event in {'os.system','os.exec','os.fork','os.forkpty'}:
            raise PermissionError('DEV11 offline capability denied')
        if event=='subprocess.Popen':
            executable,argv,cwd,env=args
            if not (reopen_arguments(executable,argv) and cwd in (None,'/source') and
                    env is None and dict(os.environ)==original):
                raise PermissionError('Unlisted DEV11 child process')
        if event=='os.posix_spawn':
            # Python3.14 uses this backend for the already approved reopen.
            # The audit event may retain env=None for inherited environment.
            executable,argv,env=args
            if not (reopen_arguments(executable,argv) and (env is None or dict(env)==original) and
                    dict(os.environ)==original and os.getcwd()=='/source'):
                raise PermissionError('Unlisted DEV11 child process')
    sys.addaudithook(audit)


def run_suite(suite):
    def ids(item):
        return [name for child in item for name in ids(child)] if isinstance(item,unittest.TestSuite) else [item.id()]
    names=ids(suite)
    if not names:raise RuntimeError('Empty DEV11 test discovery')
    print('DEV11_TEST_IDS '+json.dumps(names),flush=True)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    passed=result.wasSuccessful() and result.testsRun==len(names) and not result.skipped and not result.expectedFailures
    print('DEV11_RESULT '+json.dumps(dict(discovered=len(names),tests=result.testsRun,failures=len(result.failures),
        errors=len(result.errors),skipped=len(result.skipped),expected_failures=len(result.expectedFailures),
        scope='AUTHORED_SUBCASES_ONLY',package_acceptance='NOT_ASSERTED',status='PASS' if passed else 'FAIL')),flush=True)
    return 0 if passed else 1


def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--host-net');parser.add_argument('--probe-only',action='store_true');parser.add_argument('--reopen')
    parser.add_argument('--suite',choices=('default','ci-core','ci-storage','source04-affected','source07-affected','source09-affected','source10-affected','source11-affected','source11-query','source12-permission','source13-core','source13-business','source16-small','source17-affected','source18-affected','source19-capacity','source20-final-remaining','source21-affected','p01-large','p01-256','p01-256-plus-one','fm13-pilot','fm13-native-pilot'),default='default')
    args=parser.parse_args()
    if args.reopen:
        path=Path(args.reopen)
        if not path.is_relative_to('/tmp/tests') or '..' in path.parts:raise RuntimeError('Synthetic restart path only')
        install_guard();sys.path.insert(0,'/source')
        from pmrh.adapters.storage.journal import Journal
        from pmrh.domain.primitives import canonical,sha
        state=Journal(path).read_snapshot()
        print(json.dumps(dict(commit=state['knowledge_commit'],fast_selected=state.get('fast_selected',{}),
            fast_revisions={k:sha(canonical(v)) for k,v in state.get('fast_revisions',{}).items()})))
        return 0
    if not args.host_net:parser.error('--host-net required')
    result=probes(args.host_net,'child' if args.probe_only else 'parent')
    if args.probe_only:
        print(json.dumps(result));return 0
    child=subprocess.run([sys.executable,'-B','/source/scripts/fastmath_sandbox.py','--host-net',args.host_net,'--probe-only'],capture_output=True,text=True,timeout=15,check=True)
    result['child']=json.loads(child.stdout)
    print('DEV11_PROBES '+json.dumps(result),flush=True)
    install_guard();sys.path.insert(0,'/source')
    if args.suite in {'fm13-pilot','fm13-native-pilot'}:
        # Only the bounded two-batch pilot gets this memory ceiling. P01 large
        # material is a distinct explicitly selected resource plan.
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
        from tests.devpr11.fixtures import fm13_two_batch_pilot,fm13_all_native_two_batch_pilot
        selected=fm13_two_batch_pilot if args.suite=='fm13-pilot' else fm13_all_native_two_batch_pilot
        suite=unittest.TestSuite([unittest.FunctionTestCase(selected)])
    elif args.suite=='source21-affected':
        # Two new standalone pairs only. Default discovery and source20's
        # exact six exclusions/79-method complement stay unchanged.
        from tests.devpr11.test_storage import source21_FM07_persisted_donor_and_open_target
        from tests.devpr11.test_boundaries import source21_P01_01_02_large_material_TaskTools_pair
        suite=unittest.TestSuite([unittest.FunctionTestCase(function) for function in (
            source21_FM07_persisted_donor_and_open_target,
            source21_P01_01_02_large_material_TaskTools_pair)])
    elif args.suite=='source20-final-remaining':
        # Identical discovery to default. Only these six evidence-bound methods
        # are reused; no test is marked skipped and run_suite stays unchanged.
        discovered=unittest.defaultTestLoader.discover('/source/tests/devpr11',pattern='test_*.py',top_level_dir='/source')
        pending=[discovered];full=[]
        while pending:
            item=pending.pop()
            if isinstance(item,unittest.TestSuite):pending.extend(reversed(list(item)))
            else:full.append(item)
        full_ids=[item.id() for item in full]
        reused=(
            'tests.devpr11.test_storage.StorageTests.test_source18_historical_qualified_fast_withdrawal_keeps_current_authority',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source18_P01_07_public_frozen_partial_packet_cannot_deliver_full_body',
            'tests.devpr11.test_control_fast.ControlFastTests.test_source18_FM25_distinct_authenticated_producer_request_and_role',
            'tests.devpr11.test_storage.StorageTests.test_source11_historical_query_rechecks_current_task_permission',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source16_FM16_isolated_review_has_no_fast_title_count_or_body',
            'tests.devpr11.test_storage.StorageTests.test_source10_original_capture_recovery_precedes_successor_MAIN_apply',
        )
        if len(full_ids)!=len(set(full_ids)):
            raise RuntimeError('Duplicate source20 discovered test identity')
        if len(reused)!=len(set(reused)) or any(full_ids.count(name)!=1 for name in reused):
            raise RuntimeError('Missing or duplicate source20 reuse identity')
        selected=[item for item in full if item.id() not in reused]
        selected_ids=[item.id() for item in selected]
        if not selected or len(selected)+len(reused)!=len(full):
            raise RuntimeError('Invalid source20 complementary selection')
        print('DEV11_FULL_DISCOVERED_TEST_IDS '+json.dumps(full_ids),flush=True)
        print('DEV11_REUSED_TEST_IDS '+json.dumps(dict(test_ids=reused,
            source_manifest_sha256='8bc154ba3e789dfbb590e60634817683441b814ce9d3af82da9ddb09271d0783',
            affected_receipt_sha256='ad3d92789f1797e3ce6417a8071d4d40796d5616d798bcb44b1fa0cc0d13f2d1',
            business_receipt_sha256='9701e32089510f42d41b7502820ae680d4440627abdcd3893377478b0ddb57d6',
            scope='ROOT_AUTHORIZED_EVIDENCE_REUSE; NOT_EXECUTED_IN_THIS_RUN')),flush=True)
        print('DEV11_SELECTED_TEST_IDS '+json.dumps(selected_ids),flush=True)
        suite=unittest.TestSuite(selected)
    elif args.suite=='source19-capacity':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
        from tests.devpr11.test_storage import fm19_combined_quantitative_capacity_case
        suite=unittest.TestSuite([unittest.FunctionTestCase(fm19_combined_quantitative_capacity_case)])
    elif args.suite=='source18-affected':
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'tests.devpr11.test_storage.StorageTests.test_source18_historical_qualified_fast_withdrawal_keeps_current_authority',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source18_P01_07_public_frozen_partial_packet_cannot_deliver_full_body',
            'tests.devpr11.test_control_fast.ControlFastTests.test_source18_FM25_distinct_authenticated_producer_request_and_role',
            'tests.devpr11.test_storage.StorageTests.test_source11_historical_query_rechecks_current_task_permission',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source16_FM16_isolated_review_has_no_fast_title_count_or_body',
        ])
    elif args.suite=='source17-affected':
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'tests.devpr11.test_scope.ScopeTests',
            'tests.devpr11.test_storage.StorageTests.test_source17_same_scan_native_closure_new_blob_corruption_and_duplicate_authority',
            'tests.devpr11.test_storage.StorageTests.test_source11_same_query_history_reuse_keeps_checkpoint_and_fresh_ancestry_checks',
            'tests.devpr11.test_storage.StorageTests.test_source11_historical_query_rechecks_current_task_permission',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source16_P01_08_checkpoint_loss_range_and_current_grant',
        ])
    elif args.suite=='source16-small':
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'tests.devpr11.test_storage.StorageTests.test_source16_FM09_two_commands_same_object_and_explicit_reprepare',
            'tests.devpr11.test_storage.StorageTests.test_source16_FM19_disk_refusal_and_damaged_manifest_keep_HEAD',
            'tests.devpr11.test_retrieval.RetrievalTests.test_source16_FM17_pinned_HEAD_during_public_writer_commit',
            'tests.devpr11.test_retrieval.VerifiedBodyTests.test_source16_P01_05_stream_mutation_and_intermediate_symlink',
            'tests.devpr11.test_control_fast.ControlFastTests.test_source16_FM18_FM25_expiry_root_request_and_manifest_retry_pairs',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source16_P01_08_checkpoint_loss_range_and_current_grant',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source16_FM16_isolated_review_has_no_fast_title_count_or_body',
            'tests.devpr11.test_scope.ScopeTests',
        ])
    elif args.suite=='source13-core':
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'tests.devpr11.test_control_fast.ControlFastTests.test_source13_original_native_entry_FORMAT_and_SETTLE_clock_compatibility',
            'tests.devpr11.test_control_fast.ControlFastTests.test_source13_control_v2_rejection_stays_nondurable_and_native_success',
            'tests.devpr11.test_control_fast.ControlFastTests.test_source13_native_rejection_exact_replay_and_current_authority',
            'tests.devpr11.test_storage.StorageTests.test_source09_qualified_fast_lifecycle_boundary_is_not_bypassed',
            'tests.devpr11.test_scope.ScopeTests'])
    elif args.suite=='source13-business':
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'tests.devpr11.test_storage.StorageTests.test_source10_original_capture_recovery_precedes_successor_MAIN_apply'])
    elif args.suite=='source12-permission':
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'tests.devpr11.test_storage.StorageTests.test_source11_historical_query_rechecks_current_task_permission',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source07_control_profiles_ACTIVE_then_revoked_continuation'])
    elif args.suite in ('source11-affected','source11-query'):
        names=[
            'tests.devpr11.test_storage.StorageTests.test_source09_native_qualification_withdrawal_preserves_other_path',
            'tests.devpr11.test_storage.StorageTests.test_source11_same_query_history_reuse_keeps_checkpoint_and_fresh_ancestry_checks',
            'tests.devpr11.test_storage.StorageTests.test_source11_historical_query_rechecks_current_task_permission']
        if args.suite=='source11-affected':
            names.insert(0,'tests.devpr11.test_storage.StorageTests.test_source10_original_capture_recovery_precedes_successor_MAIN_apply')
            names.append('tests.devpr11.test_storage.StorageTests.test_source09_qualified_fast_lifecycle_boundary_is_not_bypassed')
        suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    elif args.suite=='source10-affected':
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'tests.devpr11.test_storage.StorageTests.test_source10_original_capture_recovery_precedes_successor_MAIN_apply',
            'tests.devpr11.test_storage.StorageTests.test_source09_native_qualification_withdrawal_preserves_other_path',
            'tests.devpr11.test_storage.StorageTests.test_source09_qualified_fast_lifecycle_boundary_is_not_bypassed'])
    elif args.suite=='source09-affected':
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'tests.devpr11.test_domain.DomainTests.test_source09_FM02_ordered_witness_quantifier_and_constant_pairs',
            'tests.devpr11.test_domain.DomainTests.test_source09_FM04_two_independent_directions_and_missing_reverse',
            'tests.devpr11.test_domain.DomainTests.test_source09_FM05_common_witness_order_and_AND_OR_survival',
            'tests.devpr11.test_domain.DomainTests.test_source09_FM07_exact_applicability_is_separate_from_donor',
            'tests.devpr11.test_domain.DomainTests.test_source09_FM10_local_failures_do_not_refute_original_target',
            'tests.devpr11.test_storage.StorageTests.test_source09_native_qualification_withdrawal_preserves_other_path',
            'tests.devpr11.test_storage.StorageTests.test_source09_qualified_fast_lifecycle_boundary_is_not_bypassed'])
    elif args.suite=='source07-affected':
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'tests.devpr11.test_boundaries.BoundaryTests.test_source07_native_TaskTools_scope_and_closed_window_pairs',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source07_native_pause_fence_and_superseded_grant_pairs',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source07_control_profiles_ACTIVE_then_revoked_continuation',
            'tests.devpr11.test_boundaries.BoundaryTests.test_source07_native_report_only_paused_read_then_abandon',
            'tests.devpr11.test_boundaries.BoundaryTests.test_P01_07_08_actual_TaskTools_native_range_and_current_revocation',
            'tests.devpr11.test_boundaries.BoundaryTests.test_FM16_FM26_current_task_identity_revocation_and_exposure'])
    elif args.suite=='source04-affected':
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'tests.devpr11.test_boundaries.BoundaryTests.test_P01_07_08_actual_TaskTools_native_range_and_current_revocation',
            'tests.devpr11.test_boundaries.BoundaryTests.test_P01_07_range_delivery_respects_actual_frozen_input_budget',
            'tests.devpr11.test_boundaries.BoundaryTests.test_FM16_FM27_actual_TaskTools_omitted_and_forged_scope_pairs',
            'tests.devpr11.test_storage.StorageTests.test_FM01_FM15_FM24_original_six_revisions_restart_and_exact_hashes',
            'tests.devpr11.test_scope.ScopeTests.test_FM22_reopen_process_guard_rejects_other_argv_and_environment'])
    elif args.suite=='p01-large':
        from tests.devpr11.test_retrieval import p01_large_get_case
        suite=unittest.TestSuite([unittest.FunctionTestCase(p01_large_get_case)])
    elif args.suite in {'p01-256','p01-256-plus-one'}:
        from tests.devpr11.test_retrieval import p01_256_mib_case,p01_256_mib_plus_one_case
        selected=p01_256_mib_case if args.suite=='p01-256' else p01_256_mib_plus_one_case
        suite=unittest.TestSuite([unittest.FunctionTestCase(selected)])
    elif args.suite in ('ci-core','ci-storage'):
        from scripts.offline_fastmath import ci_partition_ids
        discovered=unittest.defaultTestLoader.discover('/source/tests/devpr11',pattern='test_*.py',top_level_dir='/source')
        pending=[discovered];full=[]
        while pending:
            item=pending.pop()
            if isinstance(item,unittest.TestSuite):pending.extend(reversed(list(item)))
            else:full.append(item)
        partition=ci_partition_ids([item.id() for item in full],args.suite)
        print('DEV11_FULL_DISCOVERED_TEST_IDS '+json.dumps(partition['full']),flush=True)
        print('DEV11_SELECTED_TEST_IDS '+json.dumps(partition['selected']),flush=True)
        print('DEV11_COMPLEMENT_TEST_IDS '+json.dumps(partition['complement']),flush=True)
        selected=set(partition['selected'])
        suite=unittest.TestSuite(item for item in full if item.id() in selected)
    else:
        suite=unittest.defaultTestLoader.discover('/source/tests/devpr11',pattern='test_*.py',top_level_dir='/source')
    return run_suite(suite)


if __name__=='__main__':
    raise SystemExit(main())
