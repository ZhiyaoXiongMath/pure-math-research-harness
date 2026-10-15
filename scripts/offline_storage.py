#!/usr/bin/env python3
"""DEV05 S2 launcher: no product imports outside a verified bwrap sandbox."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--oracle', type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    oracle = args.oracle.resolve(strict=True)
    out = args.out.resolve()
    if out == source or source in out.parents or out == oracle or oracle in out.parents:
        parser.error('Evidence output must be outside both read-only source trees')
    out.mkdir(parents=True, exist_ok=False)
    receipt = {'status': 'NOT_EXECUTED', 'source': {}, 'oracle': {},
               'interpreter': sys.version, 'command': None, 'isolation': 'NOT_ESTABLISHED'}
    for label, tree in (('source', source), ('oracle', oracle)):
        for path in sorted(tree.rglob('*')):
            relative = path.relative_to(tree)
            if any(part in {'.git', '__pycache__'} for part in relative.parts) or path.suffix == '.pyc':
                continue
            if path.is_file():
                if path.is_symlink() or not path.resolve().is_relative_to(tree):
                    raise ValueError('Source inventory cannot follow links')
                receipt[label][str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    frozen = json.loads((source/'tests/devpr05/oracle-manifest.json').read_text())
    receipt['oracle_manifest_matches'] = receipt['oracle'] == frozen['files']
    receipt['declared_oracle_head'] = frozen['head']
    receipt['declared_oracle_tree'] = frozen['tree']
    if not receipt['oracle_manifest_matches']:
        receipt['reason'] = 'FROZEN_ORACLE_MISMATCH'
        (out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        return 77
    bwrap = shutil.which('bwrap')
    if not bwrap:
        receipt['reason'] = 'BWRAP_UNAVAILABLE'
        (out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
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
    for name, value in environment.items():
        command += ['--setenv', name, value]
    command += [sys.executable, '-B', '/source/scripts/storage_sandbox.py',
                '--host-net', os.readlink('/proc/self/ns/net')]
    receipt['command'] = command
    (out/'command.json').write_text(json.dumps(command, indent=2)+'\n')
    result = subprocess.run(command, capture_output=True, text=True, timeout=300,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    (out/'stdout.log').write_text(result.stdout)
    (out/'stderr.log').write_text(result.stderr)
    probe = next((line[len('S2_PROBES '):] for line in result.stdout.splitlines()
                  if line.startswith('S2_PROBES ')), None)
    if probe is not None:
        receipt['probes'] = json.loads(probe)
        receipt['isolation'] = 'VERIFIED'
        receipt['status'] = 'PASS' if result.returncode == 0 else 'FAIL'
    else:
        receipt['reason'] = 'ISOLATION_NOT_ESTABLISHED_NO_PRODUCT_FALLBACK'
    receipt['exit_code'] = result.returncode
    receipt['stdout_sha256'] = hashlib.sha256(result.stdout.encode()).hexdigest()
    receipt['stderr_sha256'] = hashlib.sha256(result.stderr.encode()).hexdigest()
    (out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({'status': receipt['status'], 'isolation': receipt['isolation'],
                      'exit_code': result.returncode, 'logs': str(out)}, sort_keys=True))
    return result.returncode if probe is not None else 77


if __name__ == '__main__':
    raise SystemExit(main())
