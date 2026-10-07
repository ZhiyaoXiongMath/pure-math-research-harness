"""Explicit user dependency setup, separate from research and offline rendering.

Detection is read-only. Downloads and administrator prompts require an explicit
setup action. Only fixed official artifacts or Ubuntu package names are used.
"""
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import fcntl
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid

FIELDS = ('codex', 'tectonic', 'tectonic_cache', 'ca_bundle')
SYSTEM_PACKAGES = ('bubblewrap', 'poppler-utils', 'fontconfig', 'fonts-dejavu-core', 'ca-certificates', 'libseccomp2')
SYSTEM_FONTS = ('DejaVuSerif.ttf', 'DejaVuSans.ttf', 'DejaVuSansMono.ttf')
# Official release bytes checked 2026-10-07. Updating requires a code review;
# there is deliberately no latest-version URL or downloaded shell execution.
ARTIFACTS = {
    'codex': {'label': 'Codex CLI', 'version': '0.160.0',
        'source': 'https://github.com/openai/codex/releases/tag/rust-v0.160.0',
        'url': 'https://github.com/openai/codex/releases/download/rust-v0.160.0/codex-x86_64-unknown-linux-musl.tar.gz',
        'sha256': '306865417d4ee7a927785852910a527f41e1e159add390ac5ae3accb67d44a13',
        'bytes': 109304578, 'member': 'codex-x86_64-unknown-linux-musl'},
    'tectonic': {'label': 'Tectonic', 'version': '0.15.0',
        'source': 'https://github.com/tectonic-typesetting/tectonic/releases/tag/tectonic%400.15.0',
        'url': 'https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz',
        'sha256': 'dfb82876f2986862996e564fa507a9e576e0c1e3bee63c2c1bd677c2543e6407',
        'bytes': 14175003, 'member': 'tectonic'},
}
_LOCK = threading.RLock()


def config_root():
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'pure-math-research-studio/4.0'


def data_root():
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'pure-math-research-studio/4.0/dependencies'


def _no_links(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Dependency storage cannot traverse symbolic links')


def _read_config():
    path = config_root() / 'dependencies.json'; _no_links(path)
    if not path.exists(): return {}
    if path.stat().st_size > 65536: raise ValueError('Dependency configuration exceeds its bound')
    obj = json.loads(path.read_text())
    if not isinstance(obj, dict) or obj.get('schema') != 'pmrs.dependencies/1' or not isinstance(obj.get('paths'), dict) or set(obj['paths']) - set(FIELDS):
        raise ValueError('Invalid dependency configuration')
    if any(not isinstance(v, str) or not Path(v).is_absolute() for v in obj['paths'].values()):
        raise ValueError('Dependency paths must be absolute')
    return obj['paths']


def configured_path(kind):
    return _read_config().get(kind)


@contextmanager
def _write_lock():
    with _LOCK:
        root = config_root(); _no_links(root); root.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(root / '.dependencies.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX); yield
        finally:
            os.close(fd)


def _atomic(path, obj):
    _no_links(path); path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.setup-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(obj, out, ensure_ascii=False, sort_keys=True); out.write('\n'); out.flush(); os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _validate_path(kind, value):
    if kind not in FIELDS or not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError('Unknown or invalid dependency path')
    path = Path(value).expanduser()
    if not path.is_absolute(): raise ValueError('Select an absolute local path')
    path = path.resolve(strict=True)
    if kind == 'tectonic_cache':
        if not path.is_dir(): raise ValueError('Select the Tectonic cache directory, not its parent')
        total = 0
        for item in path.rglob('*'):
            if item.is_symlink(): raise ValueError('Offline cache cannot contain symbolic links')
            if item.is_file(): total += item.stat().st_size
            elif not item.is_dir(): raise ValueError('Offline cache contains a nonregular member')
            if total > 256 * 1024**2: raise ValueError('Offline cache exceeds the renderer limit of 256 MiB')
    else:
        if not path.is_file(): raise ValueError('Select a regular local file')
        if kind in ('codex', 'tectonic') and not os.access(path, os.X_OK): raise ValueError('Selected program is not executable')
        if kind == 'ca_bundle':
            if path.stat().st_size > 4 * 1024**2: raise ValueError('Select a public PEM certificate bundle')
            raw = path.read_bytes()
            if b'-----BEGIN CERTIFICATE-----' not in raw or b'PRIVATE KEY' in raw:
                raise ValueError('Select a public PEM certificate bundle without private keys')
    return str(path)


def configure(paths):
    if not isinstance(paths, dict) or set(paths) - set(FIELDS): raise ValueError('Unregistered dependency setting')
    validated = {k: None if v is None else _validate_path(k, v) for k, v in paths.items()}
    with _write_lock():
        current = _read_config()
        for kind, value in validated.items():
            if value is None: current.pop(kind, None)
            else: current[kind] = value
        _atomic(config_root() / 'dependencies.json', {'schema': 'pmrs.dependencies/1', 'paths': current})
    return status()


def resolve_binary(kind, binary=None):
    """Configured defaults apply across desktop, CLI, login and dispatch.

    Explicit nondefault binary overrides are preserved. A broken selected path
    never silently falls back to a different program.
    """
    selected = configured_path(kind) if binary in (None, kind) and kind in FIELDS else None
    candidate = selected or binary or kind
    found = shutil.which(candidate)
    return str(Path(found).resolve()) if found else None


def _resolved():
    paths = _read_config(); found = {k: None for k in FIELDS}
    for kind in ('codex', 'tectonic'): found[kind] = resolve_binary(kind)
    cache = Path(paths.get('tectonic_cache', str(Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'tectonic')))
    if cache.is_dir(): found['tectonic_cache'] = str(cache)
    candidates = [paths['ca_bundle']] if paths.get('ca_bundle') else ['/etc/ssl/certs/ca-certificates.crt']
    for value in candidates:
        if Path(value).is_file(): found['ca_bundle'] = value; break
    return paths, found


def _jobs():
    root = data_root() / 'jobs'; _no_links(root)
    if not root.exists(): return []
    rows = []
    for path in sorted(root.glob('*.json'))[-30:]:
        _no_links(path)
        if path.stat().st_size > 65536: raise ValueError('Invalid setup job record')
        row = json.loads(path.read_text())
        if row.get('state') == 'RUNNING':
            try: os.kill(row['pid'], 0)
            except (ProcessLookupError, KeyError):
                row = {**row, 'state': 'INTERRUPTED', 'message': '安装进程已停止；可重新明确点击安装。'}
        rows.append(row)
    return rows


def status():
    paths, found = _resolved(); supported = platform.system() == 'Linux' and platform.machine() in ('x86_64', 'amd64')
    components = [{**{k: a[k] for k in ('label', 'version', 'source')}, 'id': key,
                   'installed': bool(found[key]), 'install_available': supported} for key, a in ARTIFACTS.items()]
    system_present = all(shutil.which(n) for n in ('bwrap', 'pdfinfo', 'pdftotext', 'pdftoppm', 'fc-match')) and bool(found['ca_bundle'])
    system_present = system_present and all((Path('/usr/share/fonts/truetype/dejavu') / name).is_file() for name in SYSTEM_FONTS)
    system_present = system_present and any(Path('/usr/lib').glob('*/libseccomp.so.2'))
    components += [{'id': 'pdf_system', 'label': 'Ubuntu PDF 系统组件与字体', 'version': 'Ubuntu repository',
                    'source': 'https://packages.ubuntu.com/', 'installed': bool(system_present),
                    'install_available': bool(shutil.which('pkexec') and Path('/usr/bin/apt-get').is_file())},
                   {'id': 'tex_resources', 'label': 'Tectonic 离线 TeX 资源', 'version': 'Compiler default bundle',
                    'source': 'https://relay.fullyjustified.net/', 'installed': bool(found['tectonic_cache']),
                    'install_available': bool(found['tectonic'])}]
    return {'schema': 'pmrs.setup-status/1', 'paths': paths, 'resolved': found, 'components': components, 'jobs': _jobs(),
            'research_ready': bool(found['codex']), 'pdf_dependencies_present': bool(found['tectonic'] and found['tectonic_cache'] and system_present),
            'readiness_scope': 'PATH_PRESENCE_ONLY; official login, model capabilities and actual isolated rendering are checked separately',
            'model_calls': 0, 'network_calls': 0}


def select(kind):
    if kind not in FIELDS: raise ValueError('Unknown dependency selector')
    picker = shutil.which('zenity')
    if not picker: raise ValueError('未找到图形文件选择器；可在页面路径栏选择本地路径，或从 Ubuntu 软件中心安装 Zenity。')
    args = [picker, '--file-selection', '--title=选择 ' + kind]
    if kind == 'tectonic_cache': args.append('--directory')
    result = subprocess.run(args, capture_output=True, text=True, timeout=300)
    if result.returncode == 1: return {'cancelled': True, 'model_calls': 0}
    if result.returncode: raise ValueError('系统图形文件选择器未能打开')
    return {'cancelled': False, 'setup': configure({kind: result.stdout.strip()}), 'model_calls': 0}


class _OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != 'https' or parsed.hostname not in {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}:
            raise ValueError('Official component download redirected outside the allowed hosts')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(artifact, target):
    opener = urllib.request.build_opener(_OfficialRedirects())
    digest = hashlib.sha256(); total = 0
    with opener.open(urllib.request.Request(artifact['url'], headers={'User-Agent': 'PMRS-component-setup/1'}), timeout=45) as response, target.open('xb') as output:
        while data := response.read(1024 * 1024):
            total += len(data)
            if total > artifact['bytes']: raise ValueError('Official component exceeded its pinned size')
            digest.update(data); output.write(data)
    if total != artifact['bytes'] or digest.hexdigest() != artifact['sha256']:
        raise ValueError('Official component failed its pinned SHA-256 check')


def _extract_binary(archive, member, target):
    with tarfile.open(archive, 'r:gz') as tar:
        rows = tar.getmembers()
        if len(rows) != 1 or rows[0].name != member or not rows[0].isfile() or rows[0].size > 256 * 1024**2:
            raise ValueError('Unexpected official executable archive layout')
        if PurePosixPath(member).name != member: raise ValueError('Invalid executable archive path')
        with tar.extractfile(rows[0]) as source, target.open('xb') as out: shutil.copyfileobj(source, out)
    target.chmod(0o755)


def _install_binary(component, work):
    artifact = ARTIFACTS[component]
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise ValueError('This pinned download supports Ubuntu x86_64; select an existing local executable on other architectures')
    archive = work / 'component.tar.gz'; _download(artifact, archive)
    target = work / component; _extract_binary(archive, artifact['member'], target); archive.unlink()
    checked = subprocess.run([str(target), '--version'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=20, env={'PATH': '/usr/bin:/bin', 'HOME': str(work), 'LANG': 'C.UTF-8'})
    if checked.returncode or artifact['version'] not in checked.stdout.decode(errors='replace')[:300]:
        raise ValueError('Official executable version check failed')
    final = data_root() / (component + '-' + artifact['version'] + '-' + uuid.uuid4().hex[:12])
    target.rename(final); configure({component: str(final)})
    return {'binary': str(final), 'version': artifact['version'], 'source': artifact['source'], 'archive_sha256': artifact['sha256']}


def _install_system(work):
    pkexec = shutil.which('pkexec')
    if not pkexec or not Path('/usr/bin/apt-get').is_file(): raise ValueError('Ubuntu 图形授权服务不可用；请从软件中心安装系统组件。')
    with (work / 'system.log').open('wb') as log:
        result = subprocess.run([pkexec, '/usr/bin/apt-get', 'install', '--no-install-recommends', '-y', *SYSTEM_PACKAGES],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=900)
    if result.returncode: raise ValueError('系统组件安装未完成或图形授权已取消；请检查软件中心后重试。')
    return {'packages': list(SYSTEM_PACKAGES), 'source': 'Configured Ubuntu apt repositories'}


def _prepare_resources(work):
    """Network-enabled preparation uses only our fixed template and no credentials.

    This is an explicit installation operation, never a renderer fallback.
    The subsequent real renderer still unshares network and uses --only-cached.
    """
    binary = resolve_binary('tectonic')
    if not binary: raise ValueError('请先选择或安装 Tectonic')
    from .render import PREAMBLE
    (work / 'resources.tex').write_text(PREAMBLE + 'PMRS offline resource preparation. $a+b=b+a$.\\end{document}\n')
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(work), 'XDG_CACHE_HOME': str(work / 'cache'),
           'XDG_CONFIG_HOME': str(work / 'config'), 'LANG': 'C.UTF-8'}
    ca = configured_path('ca_bundle')
    if ca: env['SSL_CERT_FILE'] = ca
    with (work / 'resources.log').open('wb') as log:
        result = subprocess.run([binary, '--untrusted', '--keep-logs', '--outdir', str(work), str(work / 'resources.tex')],
            cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    if result.returncode: raise ValueError('离线资源准备未完成；请检查网络、编译器与系统字体后重试。')
    cache = work / 'cache/tectonic'; _validate_path('tectonic_cache', str(cache))
    if not any(p.is_file() for p in cache.rglob('*')): raise ValueError('Tectonic did not produce an offline resource cache')
    final = data_root() / ('tectonic-cache-' + uuid.uuid4().hex[:12]); cache.rename(final)
    configure({'tectonic_cache': str(final)})
    return {'cache': str(final), 'source': 'Official compiler default bundle', 'production_render_test': 'NOT_RUN'}


def start_install(component, confirmed=False):
    if confirmed is not True: raise ValueError('明确确认后才可下载组件或打开系统授权窗口')
    if component not in {*ARTIFACTS, 'pdf_system', 'tex_resources'}: raise ValueError('Unknown setup component')
    with _write_lock():
        for row in _jobs():
            if row.get('component') == component and row.get('state') == 'RUNNING': return row
        root = data_root(); _no_links(root); root.mkdir(mode=0o700, parents=True, exist_ok=True)
        job = {'job_id': uuid.uuid4().hex, 'component': component, 'state': 'RUNNING', 'pid': os.getpid(),
               'started_at': time.time(), 'message': '正在安装所选组件。研究未启动。', 'model_calls': 0}
        record = root / 'jobs' / (job['job_id'] + '.json'); _atomic(record, job)
    def run():
        try:
            with tempfile.TemporaryDirectory(prefix='.install-', dir=root) as temporary:
                work = Path(temporary)
                result = _install_binary(component, work) if component in ARTIFACTS else (_install_system(work) if component == 'pdf_system' else _prepare_resources(work))
            completed = {**job, 'state': 'SUCCEEDED', 'message': '组件安装完成；可重新检查设置。', 'result': result}
        except Exception as exc:
            completed = {**job, 'state': 'FAILED', 'message': str(exc)[:500]}
        completed['finished_at'] = time.time(); _atomic(record, completed)
    threading.Thread(target=run, name='pmrs-setup-' + component, daemon=True).start()
    return job
