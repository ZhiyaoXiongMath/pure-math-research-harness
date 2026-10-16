"""Bounded DEV05 S2 probe/guard/test helper. Standard library until probes pass."""
import argparse
import errno
import json
import os
from pathlib import Path
import socket
import sys
import unittest


def probes(host_net):
    result = {}
    for tree in ('/source', '/baseline'):
        target = Path(tree)/'README.md'
        assert target.is_file()
        try:
            fd = os.open(target, os.O_WRONLY | os.O_APPEND)
        except OSError as exc:
            assert exc.errno in (errno.EROFS, errno.EACCES, errno.EPERM)
            result[tree+'_write'] = errno.errorcode[exc.errno]
        else:
            os.close(fd)
            raise AssertionError('Read-only source probe allowed append-open')
    scratch = Path('/tmp/tests/probe'); scratch.write_bytes(b'synthetic')
    os.link(scratch, '/tmp/tests/probe-link')
    assert scratch.stat().st_ino == Path('/tmp/tests/probe-link').stat().st_ino
    result['scratch_write_and_real_link'] = 'PASS'
    assert scratch.stat().st_dev != Path('/source/README.md').stat().st_dev
    assert scratch.stat().st_dev != Path('/baseline/README.md').stat().st_dev
    for tree in ('/source', '/baseline'):
        try:
            os.link(tree+'/README.md', '/tmp/tests/cross-link')
        except OSError as exc:
            assert exc.errno in (errno.EXDEV, errno.EROFS, errno.EPERM, errno.EACCES)
            result[tree+'_cross_link'] = errno.errorcode[exc.errno]
        else:
            raise AssertionError('Source hardlink escaped readonly filesystem')
    for path in ('/root/.ssh', '/home', '/outside-canary', '/input', '/control'):
        assert not Path(path).exists(), path
    result['outside_hidden'] = 'PASS'
    namespace = os.readlink('/proc/self/ns/net')
    assert namespace != host_net
    result['network_namespace'] = namespace
    network = None
    try:
        network = socket.socket(); network.settimeout(1)
        network.connect(('198.51.100.1', 443))
    except OSError as exc:
        assert exc.errno in (errno.ENETUNREACH, errno.EPERM, errno.EACCES)
        result['network_unreachable'] = errno.errorcode[exc.errno]
    else:
        raise AssertionError('Network is reachable')
    finally:
        if network is not None:
            network.close()
    allowed = {'PATH', 'HOME', 'TMPDIR', 'PYTHONDONTWRITEBYTECODE', 'PYTHONNOUSERSITE',
               'PIP_NO_INDEX', 'LANG', 'PWD', 'LC_CTYPE'}
    assert set(os.environ) <= allowed and os.environ['HOME'] == '/tmp/home'
    assert os.environ['TMPDIR'] == '/tmp/tests'
    result['cleared_environment'] = sorted(os.environ)
    Path('/tmp/tests/s2-probes.json').write_text(json.dumps(result, sort_keys=True))
    print('S2_PROBES '+json.dumps(result, sort_keys=True), flush=True)


def install_guard():
    """Defense in depth; the OS mounts/namespaces provide the S2 boundary."""
    cleared_environment = dict(os.environ)
    def allowed(executable, argv):
        return (os.fspath(executable) == sys.executable and type(argv) in (list, tuple) and
                len(argv) >= 4 and list(argv[:3]) == [sys.executable, '-B', '/source/tests/devpr05/child.py'] and
                argv[3] in ('oracle', 'query', 'retry', 'crash', 'compete', 'lock') and
                all(type(a) is str and '\x00' not in a for a in argv))
    def audit(event, args):
        if event.startswith('socket.') or event in ('os.system', 'os.exec', 'os.fork', 'os.forkpty'):
            raise PermissionError('DEV05 offline execution boundary')
        if event == 'os.posix_spawn' and not (allowed(args[0], args[1]) and
                                               dict(os.environ if args[2] is None else args[2]) == cleared_environment):
            raise PermissionError('Unlisted offline spawn')
        if event == 'subprocess.Popen':
            executable, argv, cwd, environment = args
            if not (allowed(executable, argv) and environment is None and
                    dict(os.environ) == cleared_environment and cwd in (None, '/source')):
                raise PermissionError('Unlisted offline subprocess')
    sys.addaudithook(audit)


def run_suite(suite, *, stream=None):
    discovered = suite.countTestCases()
    if discovered == 0:
        raise ValueError('EMPTY_TEST_DISCOVERY: no DEV05 tests found')
    result = unittest.TextTestRunner(verbosity=2, stream=stream).run(suite)
    passed = (result.wasSuccessful() and result.testsRun == discovered and
              not result.skipped and not result.expectedFailures)
    print('S2_RESULT '+json.dumps({'discovered': discovered, 'tests': result.testsRun,
          'failures': len(result.failures), 'errors': len(result.errors),
          'skipped': len(result.skipped), 'expected_failures': len(result.expectedFailures),
          'status': 'PASS' if passed else 'FAIL'}, sort_keys=True), flush=True)
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host-net', required=True)
    args = parser.parse_args()
    probes(args.host_net)
    install_guard()
    sys.path.insert(0, '/source')
    suite = unittest.defaultTestLoader.discover('/source/tests/devpr05', pattern='test_*.py', top_level_dir='/source')
    return run_suite(suite)


if __name__ == '__main__':
    raise SystemExit(main())
