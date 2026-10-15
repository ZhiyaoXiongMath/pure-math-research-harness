"""Single native journal/blob/record/HEAD engine. No legacy runtime imports."""
from __future__ import annotations
from contextlib import contextmanager, closing
from copy import deepcopy
import fcntl,os,sqlite3,tempfile
from pathlib import Path
from pmrh.domain.primitives import canonical, sha, loads, require, PMRSError
from .io import safe_path, read, immutable, atomic, now, bounded_canonical, disk_preflight
from .native_format import SCHEMA_VERSION, COMMIT_SCHEMA, policy

CHECKPOINT_INTERVAL = 128

CHECKPOINT_RETAIN = 4

CHECKPOINT_CACHE_BYTES = 128 * 1024**2

CHECKPOINT_STATE_BYTES = 48 * 1024**2

SCIENCE_MAPS = frozenset(('records', 'objects', 'sources',
    'supports', 'qualifications', 'inferences', 'production_events', 'result_families',
    'withdrawals', 'relations', 'accepted_requests', 'knowledge_changes',
    'selection_events', 'attempt_outcomes', 'translations'))

CONTROL_MAPS = frozenset(('instances', 'missions', 'visits', 'candidates', 'capabilities',
    'scope_versions', 'control_events', 'human_decisions', 'handoffs', 'obligations',
    'consumers', 'obligation_bindings', 'budget_grants', 'fences', 'active_reports', 'requests',
    'corrections', 'retry_grants', 'retired_consumers', 'selected_reports', 'project_budget', 'handoff_adoptions', 'max_workers',
    'main_decisions','communication_links','communication_link_revisions','delegation_observations','consumer_controls','live_main_dispatches'))

EXECUTION_MAPS = frozenset(('tasks', 'requests', 'attempt_groups', 'budget_grants', 'leases',
    'execution_events', 'usage', 'obligations', 'consumers', 'obligation_bindings',
    'captures', 'responses', 'missions', 'visits', 'instances', 'fences', 'dispatch_plans',
    'round_deliveries', 'scheduler_state', 'review_executions', 'retry_grants','coverage_plans',
    'strategies','human_directions','main_decisions'))

REPORT_MAPS = frozenset(('reports', 'report_events', 'active_reports', 'report_receipts','budget_grants','report_authorizations'))

EPHEMERAL = frozenset(('knowledge_commit', '_head', '_snapshot_sequence'))

def _native_only(state):
    """Reject unsupported imported authority; never convert stored projects."""
    unsupported=('legacy_artifacts','legacy_mappings','imports','migration','historical_facts')
    require(not any(state.get(key) for key in unsupported),'UNSUPPORTED_PROJECT_DATA','Imported historical project data is not supported')
    usage=state.get('historical_usage',{})
    require(isinstance(usage,dict) and not any(value is not None for value in usage.values()),
            'UNSUPPORTED_PROJECT_DATA','Imported historical usage is not supported')
    require(not any(q.get('evidence_origin')=='LEGACY_ASSERTION' for q in state.get('qualifications',{}).values()),
            'UNSUPPORTED_PROJECT_DATA','Historical proof credentials are not supported')
    require(not any(r.get('historical_only') for r in state.get('reports',{}).values()),
            'UNSUPPORTED_PROJECT_DATA','Imported report wrappers are not supported')

def _persistent(state):
    return {k: v for k, v in state.items() if k not in EPHEMERAL}

def _diff(before, after):
    """Sparse top-level collection deltas; growing event lists use append only."""
    result = {}
    for key in sorted(set(before) | set(after)):
        if key in EPHEMERAL or before.get(key) == after.get(key) and key in before and key in after:
            continue
        if key not in after:
            result[key] = {'op': 'delete'}
        elif isinstance(before.get(key), dict) and isinstance(after[key], dict):
            old, new = before[key], after[key]
            result[key] = {'op': 'map', 'set': {k: v for k, v in new.items() if k not in old or old[k] != v},
                           'delete': sorted(set(old) - set(new))}
        elif isinstance(before.get(key), list) and isinstance(after[key], list) and after[key][:len(before[key])] == before[key]:
            result[key] = {'op': 'append', 'items': after[key][len(before[key]):]}
        else:
            result[key] = {'op': 'replace', 'value': after[key]}
    return result

def _apply_delta(state, delta):
    for key, item in delta.items():
        op = item['op']
        if op == 'delete':
            state.pop(key, None)
        elif op == 'replace':
            state[key] = deepcopy(item['value'])
        elif op == 'append':
            state.setdefault(key, []).extend(deepcopy(item['items']))
        elif op == 'map':
            target = state.setdefault(key, {})
            target.update(deepcopy(item['set']))
            for name in item['delete']:
                target.pop(name, None)
        else:
            require(False, 'JOURNAL_INVALID', 'Unknown delta operation')

class Journal:
    _read_file = staticmethod(read)
    _other_control_maps = frozenset()
    def __init__(self, root, *, reader=None):
        # DEV03's query supplies an already confined, read-only directory
        # context. Ordinary callers retain the original path/I/O behavior.
        self.root = safe_path(Path(root)) if reader is None else Path(root).absolute()
        self._reader = reader
        if reader is not None:
            require(self.root == reader.root, 'PATH_INVALID', 'Reader root differs')
        self._read_head = None
        self._read_marker = None

    def _marker(self):
        if self._reader is not None and self._read_marker is not None:
            return deepcopy(self._read_marker)
        marker = loads(self._read_file(self.root/'project.json') if self._reader is None else
                       self._reader.read('project.json', 65536))
        require(marker.get('schema') == SCHEMA_VERSION, 'NATIVE_SCHEMA_REQUIRED',
                'Only the current native project format is supported; no format conversion is available')
        if self._reader is not None:
            self._read_marker = deepcopy(marker)
        return marker

    def _head(self):
        self._marker()
        if self._reader is not None and self._read_head is not None:
            return deepcopy(self._read_head)
        head = loads(self._read_file(self.root/'HEAD') if self._reader is None else
                     self._reader.read('HEAD', 16384))
        require(set(head) == {'sequence', 'commit', 'path'}, 'JOURNAL_INVALID', 'Invalid HEAD fields')
        if self._reader is not None:
            self._read_head = deepcopy(head)
        return head

    def _commit_record(self, head):
        if self._reader is not None:
            require(isinstance(head, dict) and set(head) == {'sequence', 'commit', 'path'} and
                    type(head['sequence']) is int and head['sequence'] >= 1 and
                    isinstance(head['commit'], str) and len(head['commit']) == 64 and
                    all(c in '0123456789abcdef' for c in head['commit']),
                    'JOURNAL_INVALID', 'Invalid read boundary')
        raw = (self._read_file(safe_path(self.root, head['path'])) if self._reader is None else
               self._reader.read(head['path']))
        require(sha(raw) == head['commit'], 'COMMIT_CHANGED', 'Journal commit digest differs')
        entry = loads(raw)
        required = {'schema', 'sequence', 'previous_commit', 'base_knowledge_commit',
                    'knowledge_delta_ref', 'control_delta_ref', 'report_delta_ref',
                    'registry_delta_ref', 'accepted_request_bindings', 'events', 'actor', 'at'}
        require(set(entry) == required, 'JOURNAL_INVALID', 'Unknown commit fields')
        require(entry['schema'] in (COMMIT_SCHEMA, 'pmrh.commit/1'),
                'UNSUPPORTED_SCHEMA_VERSION', 'Unknown commit format')
        require(entry['sequence'] == head['sequence'], 'JOURNAL_INVALID', 'Sequence differs')
        require(head['path'] == f"journal/{entry['sequence']:012d}-{head['commit']}.json" and canonical(entry) == raw,
                'JOURNAL_INVALID', 'Noncanonical commit identity')
        from .format import validate_entry
        validate_entry(entry)
        previous = entry['previous_commit']
        require(previous is None and entry['sequence'] == 1 or isinstance(previous, dict) and
                previous['sequence'] == entry['sequence']-1, 'JOURNAL_INVALID', 'Noncontiguous journal')
        return entry

    def read_snapshot(self, commit=None):
        marker = self._marker()
        published_history = self.history()
        head = deepcopy(published_history[-1][0])
        if commit is not None:
            while head['commit'] != commit:
                head = self._commit_record(head)['previous_commit']
                require(head is not None, 'SNAPSHOT_NOT_FOUND', 'Commit is not in this project journal')
        selected_head = deepcopy(head)
        pending = []
        state = None
        while head:
            entry = self._commit_record(head)
            # A checkpoint is a disposable reference projection, bound to the
            # verified commit and state digest in its immutable wrapper.
            path = self.root/'checkpoints'/f"{head['commit']}.json"
            checkpoint = None
            have_checkpoint = False
            if self._reader is not None:
                raw = self._reader.read(f"checkpoints/{head['commit']}.json", missing_ok=True)
                if raw is not None:
                    checkpoint = loads(raw)
                    have_checkpoint = True
            elif path.exists():
                try:
                    checkpoint = loads(self._read_file(path))
                    have_checkpoint = True
                except PMRSError as exc:
                    # Another writer may have pruned this disposable projection
                    # after exists(). The immutable journal remains authoritative.
                    if exc.code != 'FILE_UNAVAILABLE' or path.exists():
                        raise
                    pending.append(entry)
                    head = entry['previous_commit']
                    continue
            if have_checkpoint:
                require(set(checkpoint) == {'commit', 'state', 'state_sha256'}, 'CHECKPOINT_INVALID', 'Unknown checkpoint')
                require(checkpoint['commit'] == head['commit'] and sha(canonical(checkpoint['state'])) == checkpoint['state_sha256'],
                        'CHECKPOINT_CHANGED', 'Checkpoint digest differs')
                # The digest must be certified by the same immutable commit.
                evidence = [e for e in entry['events'] if e.get('type') == 'CHECKPOINT']
                require(len(evidence) == 1 and evidence[0]['state_sha256'] == checkpoint['state_sha256'],
                        'CHECKPOINT_CHANGED', 'Checkpoint is not bound to its commit')
                state = checkpoint['state']
                break
            pending.append(entry)
            head = entry['previous_commit']
        if state is None:
            state = {}
        for entry in reversed(pending):
            for field in ('knowledge_delta_ref', 'control_delta_ref', 'report_delta_ref', 'registry_delta_ref'):
                if entry[field]:
                    _apply_delta(state, loads(self.read_blob(entry[field])))
        require(state.get('schema') == SCHEMA_VERSION and state.get('project_id') == marker['project_id'],
                'NATIVE_SCHEMA_REQUIRED', 'Project and journal identities differ')
        require(state.get('synthetic_test_only') is marker.get('synthetic_test_only'),
                'SYNTHETIC_BOUNDARY_CHANGED', 'Test provenance cannot be relabelled')
        _native_only(state)
        policy(state['language_policy'])
        from .format import scan
        self._last_index = scan(self, published_history, _apply_delta,
                                allow_missing_envelopes=getattr(self, '_allow_event_gaps', False))
        state['knowledge_commit'] = selected_head['commit']
        state['_head'] = selected_head
        state['_snapshot_sequence'] = selected_head['sequence']
        return state

    def read(self):
        state = self.read_snapshot()
        return state, dict(state['_head'])

    def _publish(self, previous, before, after, *, actor, events, base=None, accepted=None,
                 at=None, checkpoint_interval=None):
        from .format import publication_schema
        schema = publication_schema(self, previous, events)
        before, after = _persistent(before), _persistent(after)
        delta = _diff(before, after)
        if not delta and not events:
            return {'commit': previous['commit'], 'sequence': previous['sequence'], 'outcome': 'NO_CHANGE'}
        # Content envelopes are verified at their real supplied paths, never
        # accepted merely because a snapshot still contains an intact copy.
        for ref, record in after.get('records', {}).items():
            if ref not in before.get('records', {}):
                immutable(self.root/'records'/f'{ref}.json', canonical(record))
        self._fault('after_records')
        groups = {'knowledge_delta_ref': {}, 'control_delta_ref': {}, 'report_delta_ref': {}, 'registry_delta_ref': {}}
        for key, item in delta.items():
            field = ('knowledge_delta_ref' if key in SCIENCE_MAPS else
                     'report_delta_ref' if key in REPORT_MAPS else
                     'control_delta_ref' if key in CONTROL_MAPS | EXECUTION_MAPS | self._other_control_maps else 'registry_delta_ref')
            groups[field][key] = item
        sequence = 1 if previous is None else previous['sequence'] + 1
        events = deepcopy(events)
        checkpoint = sequence == 1 or sequence % (checkpoint_interval or CHECKPOINT_INTERVAL) == 0
        state_raw = None
        if checkpoint:
            state_raw = bounded_canonical(after, CHECKPOINT_STATE_BYTES)
            events.append({'type': 'CHECKPOINT', 'state_sha256': sha(state_raw)})
        entry = {'schema': schema, 'sequence': sequence, 'previous_commit': previous,
                 'base_knowledge_commit': base or (previous['commit'] if previous else None),
                 **{k: self.put_blob(canonical(v)) if v else None for k, v in groups.items()},
                 'accepted_request_bindings': accepted or [], 'events': events, 'actor': actor, 'at': now() if at is None else at}
        raw = canonical(entry)
        digest = sha(raw)
        path = f'journal/{sequence:012d}-{digest}.json'
        immutable(self.root/path, raw)
        self._fault('after_commit')
        if checkpoint:
            # Assemble the small wrapper around the already bounded exact state;
            # do not serialize the same complete projection three times.
            wrapper = b'{"commit":' + canonical(digest) + b',"state":' + state_raw + b',"state_sha256":' + canonical(sha(state_raw)) + b'}'
            immutable(self.root/'checkpoints'/f'{digest}.json', wrapper)
        self._fault('before_head')
        head = {'sequence': sequence, 'commit': digest, 'path': path}
        atomic(self.root/'HEAD', canonical(head))
        self._fault('after_head')
        if checkpoint:
            self._prune_checkpoints(digest)
        return {'commit': digest, 'sequence': sequence, 'outcome': 'COMMITTED', 'events': events}

    def _prune_checkpoints(self, current):
        """Bound only the native disposable checkpoint directory, never evidence.

        Latest publication is protected. Historical reads can replay missing
        projections from the retained immutable journal and delta blobs.
        """
        folder = safe_path(self.root, 'checkpoints')
        rows = []
        for path in folder.iterdir():
            if path.suffix != '.json' or len(path.stem) != 64 or any(c not in '0123456789abcdef' for c in path.stem):
                continue  # Unknown files are not ours to collect.
            safe_path(path)
            if path.is_file():
                info = path.stat()
                rows.append((path.stem == current, info.st_mtime_ns, path.name, info.st_size, path))
        used = count = 0
        for protected, _, _, size, path in sorted(rows, reverse=True):
            if protected or count < CHECKPOINT_RETAIN and used + size <= CHECKPOINT_CACHE_BYTES:
                used += size; count += 1
            else:
                path.unlink(missing_ok=True)

    def _fault(self, boundary):
        """Explicit test injection hook; never configured by project data."""
        hook = getattr(self, '_test_fault_hook', None)
        if hook:
            hook(boundary)

    @contextmanager
    def _locked(self):
        self._marker()
        path = safe_path(self.root, '.runtime/writer.lock')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def put_blob(self, data):
        require(isinstance(data, bytes), 'BLOB_BYTES_REQUIRED', 'Content must be exact bytes')
        digest = sha(data)
        if not (self.root/'blobs'/digest).exists():
            disk_preflight(self.root, len(data))
        immutable(self.root/'blobs'/digest, data)
        return digest

    def blob(self, value):
        # Read or preserve exact bytes through the native blob API.
        return self.put_blob(value) if isinstance(value, bytes) else self.read_blob(value)

    def read_blob(self, digest):
        return self._read_blob(digest, 256*1024*1024)

    def _read_blob(self, digest, maximum):
        require(isinstance(digest, str) and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
                'BLOB_ID_INVALID', 'Expected SHA-256 digest')
        data = (self._read_file(safe_path(self.root, 'blobs/'+digest), maximum) if self._reader is None else
                self._reader.read('blobs/'+digest, maximum))
        require(sha(data) == digest, 'BLOB_CHANGED', digest)
        return data

    def read_record(self, ref):
        require(isinstance(ref, str) and ref.startswith('KR-') and len(ref) == 67,
                'RECORD_REF_INVALID', 'Exact KR revision required')
        from pmrh.domain.knowledge import identify
        record = loads(self._read_file(safe_path(self.root, 'records/'+ref+'.json')) if self._reader is None else
                       self._reader.read('records/'+ref+'.json'))
        body = self.read_blob(record['body_sha256'])
        require(identify(record, body) == ref, 'RECORD_CHANGED', ref)
        return record

    def audit(self):
        state, head = self.read()
        count, seen = 0, set()
        replay = []
        while head:
            require(head['commit'] not in seen, 'JOURNAL_CYCLE', 'Repeated commit')
            seen.add(head['commit'])
            entry = self._commit_record(head)
            for field in ('knowledge_delta_ref', 'control_delta_ref', 'report_delta_ref', 'registry_delta_ref'):
                if entry[field]:
                    self.read_blob(entry[field])
            replay.append(entry)
            head = entry['previous_commit']
            count += 1
        rebuilt = {}
        for entry in reversed(replay):
            for field in ('knowledge_delta_ref', 'control_delta_ref', 'report_delta_ref', 'registry_delta_ref'):
                if entry[field]:
                    _apply_delta(rebuilt, loads(self.read_blob(entry[field])))
        require(rebuilt == _persistent(state), 'CHECKPOINT_CHANGED', 'Full journal replay differs from checkpoint view')
        for ref, record in state.get('records', {}).items():
            require(self._read_file(safe_path(self.root, 'records/'+ref+'.json')) == canonical(record), 'RECORD_CHANGED', ref)
            self.read_blob(record['body_sha256'])
        # Every declared blob reference, including captures and original source bytes,
        # is checked without guessing that unreferenced files are admitted.
        def verify(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in ('body_sha256', 'capture_sha256', 'raw_sha256', 'blob_sha256', 'snapshot_sha256', 'packet_sha256') and child is not None:
                        self.read_blob(child)
                    verify(child)
            elif isinstance(value, list):
                for child in value: verify(child)
        verify(state)
        for source in state.get('sources',{}).values():self.read_blob(source['blob_hash'])
        for duty in state.get('obligations',{}).values():self.read_blob(duty['definition']['criterion_body_ref'])
        for task in state.get('tasks',{}).values():
            for field in ('input_packet_ref','prompt_ref'):self.read_blob(task[field])
        for request in state.get('requests',{}).values():
            if request.get('capture_ref'):self.read_blob(request['capture_ref'])
        for report in state.get('reports',{}).values():
            if report.get('snapshot_ref'):self.read_blob(report['snapshot_ref'])
            for digest in report.get('blobs',[]):self.read_blob(digest)
        # read() has verified the complete explicitly declared extension closure.
        return {'valid': True, 'commit': state['knowledge_commit'], 'commits': count,
                'records': len(state['records']), 'instances': len(state['instances']), 'model_calls': 0}

    def orphans(self):
        """Read-only inventory; no orphan capture or original is deleted."""
        referenced = set()
        # Only published commits are authoritative; unreferenced journal files
        # do not admit their blobs.
        head = self._head()
        while head:
            entry = self._commit_record(head)
            for key in ('knowledge_delta_ref', 'control_delta_ref', 'report_delta_ref', 'registry_delta_ref'):
                if entry[key]: referenced.add(entry[key])
            head = entry['previous_commit']
        state = self.read_snapshot()
        def refs(value):
            if isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value): referenced.add(value)
            elif isinstance(value, dict):
                for child in value.values(): refs(child)
            elif isinstance(value, list):
                for child in value: refs(child)
        refs(state)
        referenced.update(self._last_index.closure)
        return {'dry_run': True, 'unreferenced_blobs': sorted(p.name for p in (self.root/'blobs').iterdir() if p.is_file() and p.name not in referenced), 'deleted': 0}

    def rebuild_projection(self):
        state, head = self.read()
        directory = safe_path(self.root, '.runtime')
        path = safe_path(directory, 'projection.sqlite')
        for suffix in ('-wal', '-shm', '-journal'):
            require(not safe_path(directory, 'projection.sqlite'+suffix).exists(), 'PROJECTION_SIDECAR_PRESENT', 'Close projection readers first')
        fd, name = tempfile.mkstemp(prefix='.projection-', suffix='.sqlite', dir=directory)
        os.close(fd)
        temporary = Path(name)
        try:
            with closing(sqlite3.connect(temporary)) as conn:
                conn.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
                conn.execute('INSERT INTO metadata VALUES (?,?)', ('commit', head['commit']))
                conn.execute('CREATE TABLE records(ref TEXT PRIMARY KEY,kind TEXT,body TEXT)')
                for ref, record in state['records'].items():
                    body = self.read_blob(record['body_sha256']).decode('utf-8')
                    conn.execute('INSERT INTO records VALUES (?,?,?)', (ref, record['kind'], body))
                conn.commit()
            safe_path(directory, 'projection.sqlite')
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return {'authority': 'REBUILDABLE_PROJECTION', 'commit': head['commit'], 'records': len(state['records'])}

    def history(self):
        """Capture published ancestry, including entries hidden by checkpoints."""
        head = self._head()
        rows, seen = [], set()
        while head:
            require(head['commit'] not in seen, 'JOURNAL_CYCLE', 'Repeated commit')
            seen.add(head['commit'])
            entry = self._commit_record(head)
            rows.append((deepcopy(head), entry))
            head = entry['previous_commit']
        rows.reverse()
        extended = False
        for _, entry in rows:
            require(not extended or entry['schema'] == 'pmrh.commit/1',
                    'JOURNAL_INVALID', 'Extended lineage cannot downgrade')
            if not extended and entry['schema'] == 'pmrh.commit/1':
                require(any(e.get('type') == 'PMRH_PORT_SCOPE_BOUND' for e in entry['events']),
                        'JOURNAL_INVALID', 'Extension must begin with an explicit scope binding')
            extended |= entry['schema'] == 'pmrh.commit/1'
        if extended:
            require(len(rows) <= 4096 and sum(len(canonical(e)) for _, e in rows) <= 128 * 1024**2,
                    'RESOURCE_LIMIT', 'Extension history exceeds read budget')
        return rows
