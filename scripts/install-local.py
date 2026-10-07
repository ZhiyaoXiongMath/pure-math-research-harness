#!/usr/bin/env python3
"""Install a verified release or its wheel offline into a new user-owned prefix."""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import stat
import unicodedata
import venv
import zipfile


def digest(data): return hashlib.sha256(data).hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    if not name or '\x00' in name or path.is_absolute() or '..' in path.parts or '\\' in name or str(path) != name:
        raise ValueError('Unsafe release member: ' + name)
    return path


def no_symlinks(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symbolic link installation path rejected: ' + str(path))


def verify_release(source):
    manifest = json.loads((source / 'RELEASE-MANIFEST.json').read_text())
    if manifest.get('schema') != 'pmrs.release/1': raise ValueError('Native release manifest required')
    content = {}
    actual = set()
    for path in source.rglob('*'):
        no_symlinks(path)
        if path.is_file(): actual.add(path.relative_to(source).as_posix())
    if actual != set(manifest['files']) | {'RELEASE-MANIFEST.json'}:
        raise ValueError('Release member set differs from its byte-hash inventory')
    for name, meta in manifest['files'].items():
        safe_name(name); path = source / name; no_symlinks(path); raw = path.read_bytes()
        if meta.get('mode', 0o644) not in (0o644, 0o755): raise ValueError('Unsupported release file mode')
        if len(raw) != meta['bytes'] or digest(raw) != meta['sha256']:
            raise ValueError('Release file changed: ' + name)
        content[name] = raw
    for required in ('research_studio/cli.py', 'research_studio/__init__.py', 'research_studio/contracts.py', 'research_studio/workflows/registry.py', 'LICENSE'):
        if required not in content: raise ValueError('Incomplete release: ' + required)
    return manifest, content


def extract_release(archive_path, destination):
    """Extract a new verified release, applying its safe Unix executable modes.

    ZipFile.extractall deliberately does not restore these permission bits.
    This function also rejects traversal, links, aliases and unbound files.
    """
    destination = Path(destination).absolute(); no_symlinks(destination)
    if destination.exists(): raise ValueError('Extraction destination must be new')
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist(); names = [i.filename for i in infos]
        if not names or len(names) > 3000 or len(set(names)) != len(names): raise ValueError('Invalid release member inventory')
        if len({unicodedata.normalize('NFC', n).casefold() for n in names}) != len(names): raise ValueError('Ambiguous release member aliases')
        if sum(i.file_size for i in infos) > 512 * 1024**2: raise ValueError('Release extraction size exceeds bound')
        roots = set()
        for info in infos:
            parts = safe_name(info.filename).parts
            if len(parts) < 2 or info.is_dir() or info.flag_bits & 1 or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG):
                raise ValueError('Nonregular or invalid release member')
            roots.add(parts[0])
        if len(roots) != 1: raise ValueError('One release root required')
        root_name = next(iter(roots)); destination.mkdir(mode=0o700, parents=True)
        try:
            for info in infos:
                path = destination / info.filename; path.parent.mkdir(parents=True, exist_ok=True)
                raw = archive.read(info); path.write_bytes(raw)
                mode = stat.S_IMODE(info.external_attr >> 16)
                if mode not in (0, 0o644, 0o755): raise ValueError('Unsupported release file mode')
                path.chmod(mode or 0o644)
            release = destination / root_name; manifest, _ = verify_release(release)
            for name, meta in manifest['files'].items():
                mode = meta.get('mode', 0o755 if name.endswith(('.desktop', '.sh')) else 0o644)
                if mode not in (0o644, 0o755): raise ValueError('Unsupported manifest file mode')
                (release / name).chmod(mode)
            return release
        except BaseException:
            shutil.rmtree(destination); raise


def register_installer(release, desktop_dir):
    """Register in the user applications menu, which does not need file trust flags."""
    release = Path(release).absolute(); manifest, content = verify_release(release)
    if 'scripts/install-gui.py' not in content: raise ValueError('Graphical installer absent')
    target = Path(desktop_dir).absolute() / ('pmrs-installer-' + manifest['version'] + '.desktop')
    no_symlinks(target); target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists(): raise ValueError('Installer menu entry already exists')
    def quote(value):
        return '"' + str(value).replace('%','%%').replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$') + '"'
    text = ('[Desktop Entry]\nType=Application\nName=Install Pure Math Research Studio ' + manifest['version'] + '\n'
            'Name[zh_CN]=安装纯数学研究工作室 ' + manifest['version'] + '\nExec=/usr/bin/python3 ' + quote(release / 'scripts/install-gui.py') +
            '\nIcon=applications-science\nTerminal=false\nCategories=Education;Science;\n')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755)
    with os.fdopen(fd, 'w') as out: out.write(text); os.fchmod(out.fileno(), 0o755)
    return target


def verify_wheel(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names): raise ValueError('Duplicate wheel member')
        if len({unicodedata.normalize('NFC', n).casefold() for n in names}) != len(names): raise ValueError('Ambiguous wheel member aliases')
        for info in archive.infolist():
            if stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG) or info.flag_bits & 1:
                raise ValueError('Nonregular or encrypted wheel member')
        for name in names: safe_name(name)
        records = [n for n in names if n.endswith('.dist-info/RECORD')]
        if len(records) != 1: raise ValueError('One wheel RECORD required')
        record = records[0]; rows = list(csv.reader(io.StringIO(archive.read(record).decode())))
        if {r[0] for r in rows} != set(names) or len(rows) != len(names): raise ValueError('Wheel RECORD member set differs')
        for name, hashed, size in rows:
            if name == record:
                if hashed or size: raise ValueError('Wheel RECORD cannot hash itself')
                continue
            data = archive.read(name)
            expected = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
            if hashed != expected or str(len(data)) != size: raise ValueError('Wheel content changed: ' + name)
        if archive.testzip() is not None: raise ValueError('Wheel CRC failed')
        return {n: archive.read(n) for n in names}


def desktop_entry(launcher, version='4.0.0'):
    value = str(launcher).replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
    return ('[Desktop Entry]\nType=Application\nName=Pure Math Research Studio ' + version + '\nName[zh_CN]=纯数学研究工作室 ' + version + '\n'
            'Comment=Shared mathematical research workspace\nExec="' + value + '"\n'
            'Icon=applications-science\nTerminal=false\nCategories=Education;Science;Math;\nStartupNotify=true\n')


def install(source, target, bin_dir, *, use_venv=False, desktop_dir=None, runtime_env=None):
    if sys.version_info < (3, 11) or sys.platform != 'linux': raise ValueError('Linux and Python 3.11+ are required')
    source = Path(source).absolute(); target = Path(target).expanduser().absolute(); bin_dir = Path(bin_dir).expanduser().absolute()
    runtime_env = dict(runtime_env or {})
    if set(runtime_env) - {'RS_TECTONIC_BINARY', 'XDG_CACHE_HOME'}: raise ValueError('Unregistered runtime dependency setting')
    names = ('pure-math-research-studio', 'research-studio', 'pmrs-desktop')
    for p in (source, target, bin_dir, *(bin_dir / name for name in names)): no_symlinks(p)
    if target.exists() or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('Choose a new installation prefix outside the release')
    if any((bin_dir / name).exists() for name in names): raise ValueError('Installation launcher already exists; choose another launcher directory')
    manifest, content = verify_release(source)
    desktop = Path(desktop_dir).expanduser().absolute() / ('pmrs-' + manifest['version'] + '.desktop') if desktop_dir else None
    if desktop:
        no_symlinks(desktop)
        if desktop.exists(): raise ValueError('This version already has a desktop entry')
    target.parent.mkdir(parents=True, exist_ok=True); bin_dir.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=0o700); created_launchers = []; desktop_created = False
    try:
        if use_venv:
            venv.EnvBuilder(with_pip=False, symlinks=False).create(target)
            python = target / 'bin/python'
            purelib = Path(subprocess.check_output([str(python), '-I', '-c', 'import sysconfig;print(sysconfig.get_path("purelib"))'], text=True).strip())
            wheels = [(p, b) for p, b in content.items() if p.startswith('wheels/') and p.endswith('.whl')]
            if len(wheels) != 1: raise ValueError('One bundled offline wheel required')
            for name, raw in verify_wheel(wheels[0][1]).items():
                path = purelib / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            library = purelib
        else:
            python = Path(sys.executable); library = target
            for name, raw in content.items():
                path = target / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
                path.chmod(manifest['files'][name].get('mode', 0o755 if name.endswith(('.desktop', '.sh')) else 0o644))
            (target / 'RELEASE-MANIFEST.json').write_bytes((source / 'RELEASE-MANIFEST.json').read_bytes())
        for name in names:
            module = 'research_studio.desktop' if name == 'pmrs-desktop' else 'research_studio.cli'
            code = 'import sys;sys.path.insert(0,' + repr(str(library)) + ');from ' + module + ' import main;raise SystemExit(main())'
            text = '#!' + sys.executable + '\nimport os,sys\nos.environ.update(' + repr(runtime_env) + ')\nos.execv(' + repr(str(python)) + ',[' + repr(str(python)) + ',"-I","-c",' + repr(code) + ',*sys.argv[1:]])\n'
            launcher = bin_dir / name
            fd = os.open(launcher, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755)
            created_launchers.append(launcher)
            with os.fdopen(fd, 'w') as f: f.write(text); os.fchmod(f.fileno(), 0o755)
        if desktop:
            desktop.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(desktop, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755)
            desktop_created = True
            with os.fdopen(fd, 'w') as f: f.write(desktop_entry(bin_dir / 'pmrs-desktop', manifest['version'])); os.fchmod(f.fileno(), 0o755)
        result = {'installed': str(target), 'launcher': str(bin_dir / names[0]), 'desktop_launcher': str(bin_dir / 'pmrs-desktop'),
                  'desktop_entry': str(desktop) if desktop else None, 'version': manifest['version'],
                  'installation_kind': 'OFFLINE_WHEEL_VENV' if use_venv else 'VERIFIED_PREFIX', 'network_calls': 0}
        result['runtime_dependencies'] = runtime_env
        (target / 'INSTALLATION.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    except BaseException:
        for path in created_launchers: path.unlink(missing_ok=True)
        if desktop_created: desktop.unlink(missing_ok=True)
        shutil.rmtree(target)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, required=True); parser.add_argument('--bin-dir', type=Path, required=True)
    parser.add_argument('--venv', action='store_true'); parser.add_argument('--desktop-dir', type=Path)
    args = parser.parse_args()
    print(json.dumps(install(Path(__file__).resolve().parents[1], args.prefix, args.bin_dir,
        use_venv=args.venv, desktop_dir=args.desktop_dir), ensure_ascii=False))


if __name__ == '__main__': main()
