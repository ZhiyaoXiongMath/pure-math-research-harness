"""Same-contract native backup/restore with no format conversion."""
from pathlib import Path
import os
import tempfile
import zipfile
from .archive import inventory, bound
from .store import Store
from .util import loads, canonical, sha, require, immutable, read, safe_path, fsync_dir, PMRSError
from .version import SCHEMA_VERSION

BACKUP_SCHEMA = 'pmrs.native-backup/3.4-final-1'


def export_project(store, out):
    out = safe_path(Path(out))
    require(not out.exists() and not out.is_relative_to(store.root), 'EXPORT_DESTINATION', 'Use a new file outside the project')
    out.parent.mkdir(parents=True, exist_ok=True)
    with store._locked():
        store.audit(); state, head = store.read(); files = {}
        for path in sorted(store.root.rglob('*')):
            require(not path.is_symlink(), 'EXPORT_SYMLINK', str(path))
            name = path.relative_to(store.root).as_posix()
            if path.is_dir() or name.startswith('.runtime/'):
                continue
            files[name] = read(path, 256 * 1024**2)
        require(sum(map(len, files.values())) <= 1024**3, 'EXPORT_LIMIT', 'Backup capacity is 1 GiB')
        manifest = {'schema': BACKUP_SCHEMA, 'project_schema': SCHEMA_VERSION, 'project_id': state['project_id'],
                    'head': head, 'files': {p: {'sha256': sha(b), 'bytes': len(b)} for p, b in files.items()},
                    'runtime_backup': True, 'processes_restored': False}
        fd, tmp = tempfile.mkstemp(prefix='.native-backup-incomplete-', dir=out.parent); os.close(fd)
        try:
            with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
                for p, raw in sorted(files.items()): z.writestr(p, raw)
                z.writestr('BACKUP-MANIFEST.json', canonical(manifest))
            verify_backup(tmp); os.link(tmp, out); fsync_dir(out.parent)
        finally:
            Path(tmp).unlink(missing_ok=True)
    return {'path': str(out), 'sha256': sha(read(out, 1024**3)), 'bytes': out.stat().st_size,
            'project_schema': SCHEMA_VERSION, 'model_calls': 0}


def verify_backup(source):
    try:
        data, _ = inventory(source)
    except zipfile.BadZipFile as exc:
        raise PMRSError('NATIVE_BACKUP_REQUIRED', 'A valid current native backup archive is required') from exc
    manifest = loads(data.get('BACKUP-MANIFEST.json', b'{}'))
    require(manifest.get('schema') == BACKUP_SCHEMA and manifest.get('project_schema') == SCHEMA_VERSION,
            'NATIVE_BACKUP_REQUIRED', 'Only current native backups can be restored; other formats are not supported')
    require(manifest.get('runtime_backup') is True and set(data) - {'BACKUP-MANIFEST.json'} == set(manifest['files']),
            'BACKUP_MEMBER_SET', 'Complete native backup member set required')
    for path, meta in manifest['files'].items():
        require(len(bound(data, path, meta['sha256'])) == meta['bytes'], 'BACKUP_HASH', path)
    marker = loads(bound(data, 'project.json'))
    require(marker.get('schema') == SCHEMA_VERSION and marker.get('project_id') == manifest['project_id'],
            'NATIVE_BACKUP_REQUIRED', 'Project identity or schema differs')
    require(loads(bound(data, 'HEAD')) == manifest['head'], 'BACKUP_HEAD_CHANGED', 'Manifest HEAD differs')
    return manifest, {p: b for p, b in data.items() if p != 'BACKUP-MANIFEST.json'}


def restore(source, out):
    source = safe_path(Path(source)); out = safe_path(Path(out))
    require(not out.exists() and not out.is_relative_to(source) and not source.is_relative_to(out),
            'OUTPUT_EXISTS', 'Use a new nonoverlapping destination')
    manifest, files = verify_backup(source)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.native-restore-incomplete-', dir=out.parent) as tmp:
        root = Path(tmp) / 'project'; root.mkdir(mode=0o700)
        for path, raw in files.items(): immutable(safe_path(root, path), raw)
        immutable(root / '.runtime/writer.lock', b'')
        store = Store(root); store.audit()
        from .execution import event
        store.commit_execution(event('NATIVE_RESTORED', {'backup_identity': sha(read(source, 1024**3))}))
        store.audit(); os.rename(root, out); fsync_dir(out.parent)
    return {'path': str(out), 'paused': True, 'old_processes_restored': False,
            'historical_head': manifest['head'], 'model_calls': 0}


backup = export_project
