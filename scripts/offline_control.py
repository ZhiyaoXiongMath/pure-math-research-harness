#!/usr/bin/env python3
"""DEV06 S2 launcher: no product imports outside a verified bwrap sandbox."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import selectors
import signal
import time
import traceback
import subprocess
import sys


# Finite whole-suite ceiling: validation004 took 61.848 seconds. The expanded
# shared-pool/replay and closure cases do substantially more fsync/verification;
# 30 minutes allows that work without converting a hang into an unbounded run.
SUITE_TIMEOUT_SECONDS = 1800


class Interrupted(Exception):
    def __init__(self, signum):
        self.signum = signum
        super().__init__('Launcher interrupted by signal '+str(signum))


def durable_json(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as output:
        output.write(json.dumps(value, indent=2)+'\n')
        output.flush(); os.fsync(output.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def run_logged(command, out, receipt, *, timeout=SUITE_TIMEOUT_SECONDS, environment=None):
    """Stream/fsync raw bytes and finalize evidence on all catchable exits.

    A SIGKILL/power loss cannot run finally: the persisted RUNNING receipt is
    deliberately non-success, and already synced partial output remains.
    """
    child = None; started = time.monotonic(); caught = None; pending_signal = None
    receipt.update(status='RUNNING', timeout_seconds=timeout, command=command,
                   started_at=time.time(), completed=False)
    durable_json(out/'receipt.json', receipt)
    handlers = {}
    def interrupt(signum, frame):
        # Never unwind Popen or discard bytes already consumed from a pipe.
        nonlocal pending_signal
        pending_signal = pending_signal or signum
    def check_interrupted():
        if pending_signal is not None:raise Interrupted(pending_signal)
    try:
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            handlers[signum] = signal.signal(signum, interrupt)
        with (out/'stdout.log').open('wb', buffering=0) as stdout, (out/'stderr.log').open('wb', buffering=0) as stderr:
            with selectors.DefaultSelector() as selector:
                check_interrupted()
                child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
                check_interrupted()
                selector.register(child.stdout, selectors.EVENT_READ, stdout)
                selector.register(child.stderr, selectors.EVENT_READ, stderr)
                while selector.get_map():
                    check_interrupted()
                    remaining = timeout-(time.monotonic()-started)
                    if remaining <= 0:raise subprocess.TimeoutExpired(command, timeout)
                    for key, _ in selector.select(min(remaining, 1)):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if data:
                            key.data.write(data); os.fsync(key.data.fileno())
                        else:selector.unregister(key.fileobj)
                        check_interrupted()  # Only after consumed bytes are durable.
                # EOF does not imply process exit. Keep signals responsive even
                # when a child closes both streams and remains alive.
                while child.poll() is None:
                    check_interrupted()
                    remaining = timeout-(time.monotonic()-started)
                    if remaining <= 0:raise subprocess.TimeoutExpired(command, timeout)
                    try:child.wait(timeout=min(remaining, 1))
                    except subprocess.TimeoutExpired:pass
                check_interrupted()
                receipt.update(completed=True, status='FAIL', exit_code=child.returncode)
    except BaseException as exc:
        caught = exc
    finally:
        # Ignore repeated termination during the bounded final drain/receipt.
        for signum in handlers:signal.signal(signum, signal.SIG_IGN)
        # Include a signal arriving after the last normal-path check, before
        # finalization. It must not turn into a successful receipt.
        if caught is None and pending_signal is not None:caught = Interrupted(pending_signal)
        if caught is not None:
            receipt.update(status='TIMEOUT' if isinstance(caught, subprocess.TimeoutExpired) else
                           'INTERRUPTED' if isinstance(caught, (Interrupted, KeyboardInterrupt)) else 'ERROR',
                           exception_type=type(caught).__name__, exception=str(caught))
            if isinstance(caught, Interrupted):receipt['signal'] = caught.signum
        if child is not None:
            if child.poll() is None:child.kill()
            # Killing the bwrap namespace supervisor tears down its namespace.
            # Never launch a fallback child or leave the suite running.
            try:
                tail_out, tail_err = child.communicate(timeout=5)
                for name, data in (('stdout',tail_out), ('stderr',tail_err)):
                    with (out/(name+'.log')).open('ab', buffering=0) as output:
                        output.write(data or b''); os.fsync(output.fileno())
                receipt['exit_code'] = child.returncode
            except BaseException as drain:
                receipt['drain_error'] = type(drain).__name__+': '+str(drain)
        if caught is not None:
            with (out/'stderr.log').open('ab', buffering=0) as output:
                output.write(('LAUNCHER_EXCEPTION '+''.join(traceback.format_exception(caught))).encode())
                os.fsync(output.fileno())
        receipt.update(elapsed_seconds=time.monotonic()-started, finished_at=time.time())
        for name in ('stdout','stderr'):
            path = out/(name+'.log')
            if not path.exists():path.touch()
            receipt[name+'_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        # PASS requires both the pre-import isolation probes and the complete
        # no-skip suite marker, as well as normal process completion.
        markers = {}
        try:
            for line in (out/'stdout.log').read_text(errors='replace').splitlines():
                for prefix in ('DEV06_PROBES ', 'DEV06_RESULT ', 'DEV06_TEST_IDS '):
                    if line.startswith(prefix):markers[prefix.strip()] = json.loads(line[len(prefix):])
            if 'DEV06_PROBES' in markers:
                receipt.update(probes=markers['DEV06_PROBES'], isolation='VERIFIED')
            result = markers.get('DEV06_RESULT', {})
            receipt['suite_result'] = result or None
            receipt['test_ids'] = markers.get('DEV06_TEST_IDS', [])
            complete = (result.get('tests', 0)>0 and result.get('tests') == result.get('discovered') == len(receipt['test_ids']))
            if caught is None:
                receipt['status'] = ('PASS' if receipt.get('exit_code')==0 and receipt.get('isolation')=='VERIFIED' and complete and
                    result.get('status')=='PASS' and all(result.get(k)==0 for k in ('failures','errors','skipped','expected_failures')) else
                    'FAIL' if complete else 'INCOMPLETE')
        except (ValueError, TypeError) as exc:
            receipt.update(status='ERROR', marker_error=str(exc))
        durable_json(out/'receipt.json', receipt)
        for signum, handler in handlers.items():signal.signal(signum, handler)
    return (0 if receipt['status']=='PASS' else 124 if receipt['status']=='TIMEOUT' else
            128+receipt.get('signal',2) if receipt['status']=='INTERRUPTED' else
            receipt.get('exit_code') or 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--oracle', type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    oracle = args.oracle.resolve()
    out = args.out.resolve()
    if out == source or source in out.parents or out == oracle or oracle in out.parents:
        parser.error('Evidence output must be outside both read-only source trees')
    out.mkdir(parents=True, exist_ok=False)
    receipt = {'status': 'NOT_EXECUTED', 'source': {}, 'oracle': {},
               'interpreter': sys.version, 'command': None, 'isolation': 'NOT_ESTABLISHED'}
    durable_json(out/'receipt.json', receipt)
    (out/'stdout.log').touch(); (out/'stderr.log').touch()
    handlers={}
    def interrupt(signum, frame):raise Interrupted(signum)
    for signum in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
        handlers[signum]=signal.signal(signum,interrupt)
    try:
        return launch(source, oracle, out, receipt)
    except BaseException as exc:
        receipt.update(status='INTERRUPTED' if isinstance(exc,(Interrupted,KeyboardInterrupt)) else 'ERROR',
                       exception_type=type(exc).__name__, exception=str(exc))
        if isinstance(exc,Interrupted):receipt['signal']=exc.signum
        with (out/'stderr.log').open('ab', buffering=0) as log:
            log.write(''.join(traceback.format_exception(exc)).encode()); os.fsync(log.fileno())
        for name in ('stdout','stderr'):
            receipt[name+'_sha256'] = hashlib.sha256((out/(name+'.log')).read_bytes()).hexdigest()
        durable_json(out/'receipt.json', receipt)
        return 128+receipt.get('signal',2) if receipt['status']=='INTERRUPTED' else 1
    finally:
        for signum,handler in handlers.items():signal.signal(signum,handler)


def launch(source, oracle, out, receipt):
    for label, tree in (('source', source), ('oracle', oracle)):
        for path in sorted(tree.rglob('*')):
            relative = path.relative_to(tree)
            if any(part in {'.git', '__pycache__'} for part in relative.parts) or path.suffix == '.pyc':
                continue
            if path.is_file():
                if path.is_symlink() or not path.resolve().is_relative_to(tree):
                    raise ValueError('Source inventory cannot follow links')
                receipt[label][str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt['source_manifest_sha256']=hashlib.sha256(json.dumps(receipt['source'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    for name in ('stdout','stderr'):
        receipt[name+'_sha256']=hashlib.sha256((out/(name+'.log')).read_bytes()).hexdigest()
    frozen = json.loads((source/'tests/devpr05/oracle-manifest.json').read_text())
    receipt['oracle_manifest_matches'] = receipt['oracle'] == frozen['files']
    receipt['declared_oracle_head'] = frozen['head']
    receipt['declared_oracle_tree'] = frozen['tree']
    if not receipt['oracle_manifest_matches']:
        receipt['reason'] = 'FROZEN_ORACLE_MISMATCH'
        durable_json(out/'receipt.json', receipt)
        return 77
    bwrap = shutil.which('bwrap')
    if not bwrap:
        receipt['reason'] = 'BWRAP_UNAVAILABLE'
        durable_json(out/'receipt.json', receipt)
        return 77
    command = [bwrap, '--unshare-all', '--die-with-parent', '--new-session']
    for directory in ('/usr', '/bin', '/lib', '/lib64'):
        if Path(directory).exists():
            command += ['--ro-bind', directory, directory]
    prefix = Path(sys.base_prefix).resolve()
    if not prefix.is_relative_to('/usr'):
        command += ['--ro-bind', str(prefix), str(prefix)]
    command += ['--proc', '/proc', '--dev', '/dev', '--ro-bind', str(source), '/source',
                '--ro-bind', str(oracle), '/baseline', '--tmpfs', '/tmp',
                '--dir', '/tmp/home', '--dir', '/tmp/tests', '--chdir', '/source', '--clearenv']
    if (source/'.git').is_dir():
        command += ['--tmpfs', '/source/.git']
    if (oracle/'.git').is_dir():
        command += ['--tmpfs', '/baseline/.git']
    environment = {'PATH': '/usr/bin:/bin', 'HOME': '/tmp/home', 'TMPDIR': '/tmp/tests',
                   'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1', 'PIP_NO_INDEX': '1',
                   'LANG': 'C.UTF-8'}
    receipt['child_environment']=environment
    receipt['launcher_child_environment']={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
    for name, value in environment.items():
        command += ['--setenv', name, value]
    command += [sys.executable, '-B', '/source/scripts/control_sandbox.py',
                '--host-net', os.readlink('/proc/self/ns/net')]
    receipt['command'] = command
    durable_json(out/'command.json', command)
    code = run_logged(command, out, receipt, environment={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    print(json.dumps({'status': receipt['status'], 'isolation': receipt['isolation'],
                      'exit_code': receipt.get('exit_code'), 'logs': str(out)}, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
