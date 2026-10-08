#!/usr/bin/env python3
"""Build reproducible source/release ZIPs and a wheel, using only the stdlib."""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
import datetime
from pathlib import Path
import re
import subprocess
import sys
import zipfile
import gzip
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT/'research_studio/__init__.py').read_text())[1]
WHEEL_VERSION = VERSION
PREFIX = 'Pure-Math-Research-Studio-' + VERSION
SOURCE_DATE_EPOCH = int(os.environ.get('SOURCE_DATE_EPOCH', '315532800'))
FIXED_TIME = datetime.datetime.fromtimestamp(max(SOURCE_DATE_EPOCH, 315532800), datetime.timezone.utc).timetuple()[:6]
REQUIRED_DOCS = ['README.md', 'README.zh-CN.md', 'LICENSE', 'pyproject.toml',
    'CHANGELOG-4.1.0.md', 'ARCHITECTURE-4.1.0.md',
    'TEST-REPORT-4.1.0.md', 'UBUNTU-E2E-GUIDE.md', 'ACCEPTANCE-SCOPE-4.1.0.md']
EXCLUDED = {'.git', '__pycache__', '.venv'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()


def files(require_docs=True):
    result = {}
    for p in sorted(ROOT.rglob('*')):
        rel = p.relative_to(ROOT)
        if (EXCLUDED.intersection(rel.parts) or rel.parts[0] in ('build', 'dist')
                or any(s.endswith('.egg-info') for s in rel.parts)):
            continue
        if p.is_symlink():
            raise ValueError('Release input symlink: '+str(rel))
        if p.is_file() and p.suffix not in ('.pyc', '.pyo'):
            if p.name.startswith('.env'):
                raise ValueError('Credential file is not a release input: '+str(rel))
            result[rel.as_posix()] = p.read_bytes()
    if require_docs:
        for name in REQUIRED_DOCS:
            if name not in result:
                raise ValueError('Missing required document: '+name)
    forbidden = ('historical/', 'research_studio/migration/', 'development/', 'validation/')
    for name in result:
        if name.startswith(forbidden):
            raise ValueError('Non-product legacy or private evidence input: ' + name)
    return result


def wheel(members):
    dist = 'pure_math_research_studio'
    info = f'{dist}-{WHEEL_VERSION}.dist-info'
    rows = {p:b for p,b in members.items() if p.startswith('research_studio/')}
    metadata = (f'Metadata-Version: 2.4\nName: pure-math-research-studio\nVersion: {WHEEL_VERSION}\n'
        'Summary: Shared mathematical research kernel with independent TRW, TFDW and SURVEY workflows\n'
        'Requires-Python: >=3.11\nLicense-Expression: Apache-2.0\nLicense-File: LICENSE\n'
        'Description-Content-Type: text/markdown\n\n').encode()+members['README.md']
    rows.update({info+'/METADATA':metadata, info+'/licenses/LICENSE':members['LICENSE'],
        info+'/WHEEL':b'Wheel-Version: 1.0\nGenerator: PMRS offline release writer\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
        info+'/entry_points.txt':b'[console_scripts]\npure-math-research-studio = research_studio.cli:main\nresearch-studio = research_studio.cli:main\npmrs-desktop = research_studio.desktop:main\n',
        info+'/top_level.txt':b'research_studio\n'})
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for p,b in sorted(rows.items()):
        writer.writerow([p, 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).rstrip(b'=').decode(), len(b)])
    writer.writerow([info+'/RECORD', '', ''])
    rows[info+'/RECORD'] = record.getvalue().encode()
    stream = io.BytesIO()
    write_zip(stream, rows)
    return f'{dist}-{WHEEL_VERSION}-py3-none-any.whl', stream.getvalue()


def write_zip(destination, members):
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path,data in sorted(members.items()):
            entry = zipfile.ZipInfo(path, FIXED_TIME)
            entry.create_system = 3
            entry.external_attr = (0o100755 if path.endswith(('.sh', '.desktop')) else 0o100644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, data, compresslevel=9)


def debian_installer(release):
    """Small, reproducible GUI bootstrap package; no maintainer scripts or fetches."""
    base = 'usr/lib/pmrs-installer/' + VERSION
    launcher = ('[Desktop Entry]\nType=Application\nName=Install Pure Math Research Studio ' + VERSION + '\n'
        'Name[zh_CN]=安装纯数学研究工作室 ' + VERSION + '\nExec=/usr/bin/python3 /' + base + '/scripts/install-gui.py\n'
        'Icon=applications-science\nTerminal=false\nCategories=Education;Science;\n').encode()
    data = {base + '/' + path: raw for path, raw in release.items()}
    data['usr/share/applications/pmrs-installer-' + VERSION + '.desktop'] = launcher
    control = ('Package: pmrs4-graphical-installer\nVersion: ' + WHEEL_VERSION + '\nArchitecture: all\n'
        'Maintainer: PMRS contributors\nSection: science\nPriority: optional\n'
        'Depends: python3 (>= 3.11), python3-venv, zenity\n'
        'Description: Graphical offline installer for Pure Math Research Studio\n'
        ' Includes the verified PMRS release and its offline wheel.\n').encode()
    def tar_bytes(rows):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as tar:
            directories = sorted({parent.as_posix() for path in rows for parent in Path(path).parents if parent.as_posix() != '.'}, key=lambda p:(len(Path(p).parts),p))
            for path in directories:
                item = tarfile.TarInfo('./' + path); item.type=tarfile.DIRTYPE; item.mode=0o755; item.mtime=SOURCE_DATE_EPOCH; tar.addfile(item)
            for path, raw in sorted(rows.items()):
                item = tarfile.TarInfo('./' + path); item.size=len(raw); item.mode=0o755 if path.endswith(('.desktop','.sh')) else 0o644
                item.mtime=SOURCE_DATE_EPOCH; tar.addfile(item, io.BytesIO(raw))
        return gzip.compress(buffer.getvalue(), compresslevel=9, mtime=SOURCE_DATE_EPOCH)
    archive = bytearray(b'!<arch>\n')
    for name, raw in [('debian-binary', b'2.0\n'), ('control.tar.gz', tar_bytes({'control':control})), ('data.tar.gz', tar_bytes(data))]:
        header = f'{name + "/":<16}{SOURCE_DATE_EPOCH:<12}{0:<6}{0:<6}{"100644":<8}{len(raw):<10}`\n'.encode('ascii')
        if len(header) != 60: raise ValueError('Invalid Debian archive header')
        archive.extend(header); archive.extend(raw)
        if len(raw) % 2: archive.extend(b'\n')
    audit = {'format':'DEBIAN_AR_TAR','files':{path:{'bytes':len(raw),'sha256':digest(raw)} for path,raw in sorted(data.items())},
             'control':{'bytes':len(control),'sha256':digest(control)},'maintainer_scripts':[]}
    return 'pmrs4-graphical-installer_' + WHEEL_VERSION + '_all.deb', bytes(archive), audit


def build(out):
    members = files()
    out = out.absolute()
    if any(p.is_symlink() for p in (out,*out.parents)):
        raise ValueError('Build output must not traverse symlinks')
    out = out.resolve()
    if out.is_relative_to(ROOT):
        raise ValueError('Build outside the source tree without symlinks')
    out.mkdir(parents=True, exist_ok=True)
    names = [PREFIX+'-source.zip', PREFIX+'-release.zip']
    wheel_name, wheel_data = wheel(members)
    audit_name = 'FINAL-ARTIFACT-AUDIT.json'
    if any((out/p).exists() for p in [*names,wheel_name,audit_name,'SHA256SUMS.txt','pmrs4-graphical-installer_' + WHEEL_VERSION + '_all.deb']):
        raise ValueError('Use a new build directory; artifacts are not overwritten')
    try:
        commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,stderr=subprocess.DEVNULL).decode().strip()
        tree = subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT).decode().strip()
        dirty = bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT))
    except (OSError, subprocess.CalledProcessError):
        commit,tree,dirty = None,None,None
    build_info = {'product_version':VERSION,'wheel_version':WHEEL_VERSION,'commit':commit,'tree':tree,
        'working_tree_changed':dirty,'source_content_sha256':digest(encoded({p:digest(b) for p,b in members.items()})),
        'source_date_epoch':SOURCE_DATE_EPOCH,'release_qualification':'NOT_EVALUATED_BY_BUILD','model_calls':0}
    release = {p:b for p,b in members.items() if p in REQUIRED_DOCS or p.startswith(('research_studio/','examples/'))
               or p in ('scripts/install-local.py','scripts/install-gui.py','scripts/prepare-release.py','scripts/verify-pdf.py','Install-PMRS.desktop','INSTALL-HELP.html')}
    release['BUILD-INFO.json'] = encoded(build_info)
    release['wheels/'+wheel_name] = wheel_data
    release['RELEASE-MANIFEST.json'] = encoded({'schema':'pmrs.release/1','version':VERSION,
        'files':{p:{'bytes':len(b),'sha256':digest(b),'mode':0o755 if p.endswith(('.desktop','.sh')) else 0o644} for p,b in sorted(release.items())}})
    source = dict(members)
    source['BUILD-INFO.json'] = encoded(build_info)
    source['SOURCE-MANIFEST.json'] = encoded({'schema':'pmrs.source-manifest/1',
        'files':{p:{'bytes':len(b),'sha256':digest(b)} for p,b in sorted(source.items())}})
    for name,values in zip(names,(source,release)):
        target = out/name
        write_zip(target, {PREFIX+'/'+p:b for p,b in values.items()})
        with zipfile.ZipFile(target) as z:
            if z.testzip() is not None:
                raise ValueError('ZIP CRC mismatch: '+name)
            for p,b in values.items():
                if z.read(PREFIX+'/'+p) != b:
                    raise ValueError('ZIP content mismatch: '+p)
    (out/wheel_name).write_bytes(wheel_data)
    deb_name, deb_data, deb_audit = debian_installer(release)
    if (out/deb_name).exists(): raise ValueError('Graphical installer package already exists')
    (out/deb_name).write_bytes(deb_data)
    deb_audit.update({'bytes':len(deb_data),'sha256':digest(deb_data)})
    payload_names = [*names,wheel_name]
    audits = {}
    for name in payload_names:
        raw = (out/name).read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if z.testzip() is not None: raise ValueError('Artifact ZIP CRC mismatch: '+name)
            if len(z.namelist()) != len(set(z.namelist())): raise ValueError('Duplicate artifact members: '+name)
            audits[name] = {'bytes':len(raw),'sha256':digest(raw),'files':{
                p:{'bytes':len(z.read(p)),'sha256':digest(z.read(p))} for p in sorted(z.namelist())}}
    (out/audit_name).write_bytes(encoded({'schema':'pmrs.final-artifact-audit/1',
        'qualification':'ARTIFACT_INTEGRITY_ONLY','source_date_epoch':SOURCE_DATE_EPOCH,
        'self_binding':'FINAL-ARTIFACT-AUDIT.json is bound by SHA256SUMS.txt',
        'artifacts':audits,'installer_packages':{deb_name:deb_audit}}))
    result = {'status':'PASS','qualification':'ARTIFACT_INTEGRITY_ONLY','build':build_info,'artifacts':[
        {'filename':p,'bytes':(out/p).stat().st_size,'sha256':digest((out/p).read_bytes())}
        for p in [*payload_names,deb_name,audit_name]]}
    (out/'SHA256SUMS.txt').write_text(''.join(a['sha256']+'  '+a['filename']+'\n' for a in result['artifacts']))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        members = files()
        name,data = wheel(members)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert z.testzip() is None
        print(json.dumps({'status':'PASS','files':len(members),'wheel':name,'offline':True}))
    elif args.out:
        print(json.dumps(build(args.out),indent=2))
    else:
        parser.error('--out or --check is required')
