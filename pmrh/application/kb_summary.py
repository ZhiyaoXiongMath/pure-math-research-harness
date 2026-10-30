"""Small KB/Summary application over injected native services and existing UoW.

No model is started here. The host supplies its existing storage/policy context
and an already frozen, sealed native request. The currently installed disk
capability is synthetic-only; this module deliberately retains that boundary.
Material, native admission and derived output are separate recoverable commits.
"""
import base64
from copy import deepcopy
from difflib import SequenceMatcher
from datetime import datetime, timezone

from pmrh.application.unit_of_work import UnitOfWork
from pmrh.domain import knowledge as K, relations
from pmrh.domain.primitives import canonical, loads, require, sha, PMRSError
from pmrh.ports.dto import core as C, enums as E, events as V, storage as T


SCHEMA = 'pmrh.kb-summary/1'
PREFIX = 'raw-evidence:kb-summary:'
MEDIA = {'.txt': 'text/plain', '.md': 'text/markdown', '.tex': 'application/x-tex'}
KINDS = ('Context', 'Statement', 'Argument', 'Example', 'SourceEvidence')


def changed_ranges(old, new):
    """Exact UTF-8 line changes, including inserted boundary branches."""
    a, b = old.splitlines(keepends=True), new.splitlines(keepends=True)
    offsets = [0]
    for line in b:
        offsets.append(offsets[-1] + len(line))
    return [{'start': offsets[j], 'end': offsets[k], 'old_start_line': i + 1,
             'old_end_line': h, 'change': tag}
            for tag, i, h, j, k in SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
            if tag != 'equal']


class KnowledgeSummary:
    """Host-side capability, never constructed from a material or project file.

    `allow_ref` is a trusted CURRENT per-reference access decision. It must share
    writer exclusion with policy revocation, as required by TrustedReadContext.
    `authorize` issues the existing UoW permit; no grants are created here.
    """
    def __init__(self, store, uow, *, authorize, expectation, allow_ref, native_changes, knowledge_reader):
        require(store.root == uow.storage.root and callable(allow_ref) and callable(authorize)
                and callable(expectation), 'AUTHORIZATION_REQUIRED', 'Same-root trusted host assembly required')
        self.store, self.storage = store, uow.storage
        require(type(getattr(getattr(self.storage, 'context', None), 'scope', None)) is C.Scope,
                'AUTHORIZATION_REQUIRED', 'Host storage context unavailable')
        self.scope = self.storage.context.scope
        self.authorize, self.expectation, self.allow_ref = authorize, expectation, allow_ref
        self.changes, self.reader = native_changes, knowledge_reader
        self._intent_builder = uow.intent_builder
        self.uow = UnitOfWork(self.storage, policy=uow.policy, intent_builder=self._intent)
        self._pending = {}
        self._check()

    def _check(self, refs=()):
        self.storage.authorize(self.scope)
        state = self.store.read_snapshot()
        require(state['project_id'] == self.scope.project_id, 'AUTHORIZATION_REQUIRED', 'Project differs')
        require(state.get('synthetic_test_only') is True, 'UNSUPPORTED_CAPABILITY',
                'Installed KB/Summary persistence requires synthetic storage; authenticated production host assembly is absent')
        require(self.scope.instance_id in state['instances'], 'AUTHORIZATION_REQUIRED', 'Instance differs')
        require(all(self.allow_ref(ref) is True for ref in refs), 'KNOWLEDGE_FORBIDDEN', 'Reference outside current host scope')
        return state

    def _visible(self, refs, state=None):
        state = self._check() if state is None else state
        closure = relations.premise_closure(refs, state, include_method_sources=True)
        return all(self.allow_ref(ref) is True for ref in closure)

    def _intent(self, staged, batch):
        self._check(self._pending[batch.operation_id])  # runs under UoW's writer lock
        return self._intent_builder(staged, batch)

    def _rows(self, kind):
        self._check()
        with self.storage.view(self.scope) as (store, _, index):
            rows = []
            for row in index.streams[self.scope]:
                ref = row['event'].payload_ref
                if not ref.object_id.startswith(PREFIX):
                    continue
                value = loads(store.read_blob(ref.sha256))
                require(value.get('schema') == SCHEMA, 'CORRUPT_CAPTURE', 'Summary evidence schema differs')
                if value['kind'] == kind and self._visible(value['access_refs']):
                    rows.append((ref, value['data']))
            return rows

    def recover(self, operation_id):
        """Read original operation receipt; absence is not permission to resample."""
        self._check()
        require(isinstance(operation_id, str) and operation_id.startswith('kb-summary:'),
                'KNOWLEDGE_FORBIDDEN', 'Only this adapter\'s operations may be inspected')
        with self.storage.view(self.scope) as (store, _, index):
            rows = [r for r in index.batches.values() if r['batch'].operation_id == operation_id]
            require(len(rows) <= 1, 'IDEMPOTENCY_CONFLICT', 'Operation identity reused')
            if not rows:
                return None
            for write in rows[0]['batch'].evidence:
                require(write.evidence_ref.object_id.startswith(PREFIX), 'KNOWLEDGE_FORBIDDEN', 'Operation outside adapter scope')
                value = loads(store.read_blob(write.evidence_ref.sha256))
                self._check(value['access_refs'])
            return index.receipt(rows[0], duplicate=True)

    def _save(self, kind, data, refs):
        self._check(refs)
        value = dict(schema=SCHEMA, kind=kind, access_refs=sorted(set(refs)), data=data)
        raw = canonical(value)
        key = sha(raw)
        operation = 'kb-summary:' + key
        ref = C.ExactRef(project_id=self.scope.project_id, object_id=PREFIX + kind + ':' + key,
                         revision='1', sha256=key)
        if self.recover(operation) is not None:
            return ref
        boundary = self.storage.current_boundary()
        require(isinstance(boundary, T.ReadBoundary), 'AUTHORIZATION_REQUIRED', 'Read boundary unavailable')
        unobserved = C.ObservedIdentifier(kind=E.ObservationKind.UNOBSERVED, value=None)
        event = V.EventEnvelope(event_id='kb-summary-event:' + key, event_type='EVIDENCE_RECORDED',
            event_domain=E.EventDomain.DIAGNOSTIC, status=E.EventStatus.OBSERVATION,
            project_id=self.scope.project_id, instance_id=self.scope.instance_id,
            journal_id=unobserved, aggregate_id='kb-summary', aggregate_sequence=None,
            journal_sequence=None, commit_ref=None, occurred_at=None,
            observed_at=C.TimePoint(utc=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), clock_source=E.ClockSource.LOCAL_UTC),
            committed_at=None, clock_source=E.ClockSource.LOCAL_UTC, actor_principal_ref=None,
            actor_kind='ADAPTER', correlation_id=operation, causation_id=None,
            operation_id=operation, idempotency_key=operation, invocation_id=None, execution_id=None,
            request_id=None, attempt_id=None, activation_id=None, logical_main_id=None,
            owner_epoch=None, control_version=None, backend_id=unobserved, provider_id=unobserved,
            provider_request_id=unobserved, backend_binding_ref=None, payload_ref=ref,
            raw_evidence_ref=ref, payload_sha256=key, classification=E.Classification.SYNTHETIC_TEST_ONLY,
            trust_origin=E.TrustOrigin.SYNTHETIC_TEST_ONLY, visibility_policy_ref=boundary.visibility_policy_ref)
        batch = T.CommitBatch(operation_id=operation, idempotency_key=operation,
            evidence=(T.EvidenceWrite(evidence_ref=ref, content_base64=base64.b64encode(raw).decode()),), events=(event,))
        tx = self.uow.begin(self.expectation(boundary))
        require(isinstance(tx, T.TransactionHandle), 'SUMMARY_TRANSACTION_UNAVAILABLE', 'Begin failed')
        staged = self.uow.stage(tx, batch)
        require(isinstance(staged, T.StagingReceipt), 'SUMMARY_TRANSACTION_UNAVAILABLE', 'Stage failed')
        self._pending[operation] = tuple(refs)
        permit = self.authorize(self.uow.commit_intent(tx))
        receipt = self.uow.commit(tx, permit)
        require(isinstance(receipt, T.CommitReceipt), 'SUMMARY_COMMIT_UNCERTAIN',
                'Inspect original operation before any continuation: ' + operation)
        return ref

    def register(self, raw, *, material_id, name, origin):
        """Exact user-supplied UTF-8 bytes. Metadata saved != text actually read."""
        self._check()
        require(type(raw) is bytes and 0 < len(raw) <= T.MAX_EVIDENCE_BYTES, 'PAYLOAD_LIMIT', 'MVP supports text up to 1 MiB')
        try:
            raw.decode('utf-8')
        except UnicodeError as exc:
            raise PMRSError('SOURCE_TEXT_UNAVAILABLE', 'Input must be reliable UTF-8 text') from exc
        require(isinstance(name, str) and '.' in name and name[name.rfind('.'):].lower() in MEDIA,
                'UNSUPPORTED_CAPABILITY', 'MVP inputs: .txt, .md and .tex')
        require(all(isinstance(v, str) and 0 < len(v) <= 1024 and '\0' not in v
                    for v in (material_id, origin)), 'RESPONSE_SCHEMA_INVALID', 'Material identity and actual input origin required')
        ref = 'SO-' + sha(raw)
        state = self._check([ref])
        if ref not in state['sources']:
            # Existing original-input admission owns source publication. This is
            # not atomic with the following metadata transaction; ref is stable.
            self.store.commit(self.changes.prepare_material_input(state, raw, name,
                MEDIA[name[name.rfind('.'):].lower()], source_id=ref, blob_get=self.store.read_blob))
        self._check([ref])
        data = dict(material_id=material_id, source_ref=ref, version=sha(raw), name=name,
                    origin=origin, representation='EXACT_UTF8_ORIGINAL', read_coverage=[])
        self._save('material', data, [ref])
        return data

    def read(self, source_ref, ranges=None):
        self._check([source_ref])
        row = self.reader.get(self.store, source_ref)
        raw = row['body'].encode('utf-8')
        ranges = ranges if ranges is not None else [(0, len(raw))]
        locators = [K.locator(raw, start, end) for start, end in ranges]
        return dict(source_ref=source_ref, version=sha(raw), locators=locators,
                    text=[K.validate_locator(loc, self.store.read_blob).decode() for loc in locators])

    def prepare(self, raw, *, material_id, name, origin, request, ranges=None):
        """Both Skills call this; repeated/renamed input returns the saved output."""
        require(isinstance(request, str) and 0 < len(request) <= 8192,
                'RESPONSE_SCHEMA_INVALID', 'Explicit bounded request required')
        material = self.register(raw, material_id=material_id, name=name, origin=origin)
        reading = self.read(material['source_ref'], ranges)
        basis = dict(source_ref=material['source_ref'], request=request, locators=reading['locators'])
        task_key = sha(canonical(basis))
        results = self._rows('result')
        for ref, result in reversed(results):
            if not self._current(result):
                continue
            same_selection = (result['material_id'] == material_id and result['request'] == request and
                [K.validate_locator(loc, self.store.read_blob) for loc in result['reading']] ==
                [part.encode('utf-8') for part in reading['text']])
            if result['task_key'] == task_key or same_selection:
                return dict(status='REUSED', result_ref=ref, result=deepcopy(result),
                            registered_material=material, pinned_version=result['version'])
        previous = next((r for _, r in reversed(results)
                         if r['material_id'] == material_id and r['request'] == request and self._current(r)), None)
        reuse = {}
        if previous:
            for record_ref, uses in previous['bindings'].items():
                if all(any(K.validate_locator(loc, self.store.read_blob) in part.encode()
                           for part in reading['text']) for use in uses for loc in use['locators']):
                    reuse[record_ref] = uses
            # An unchanged sentence is insufficient if one of its native
            # premises/contexts changed. Keep all original records immutable;
            # only the affected consumer set needs a new extraction.
            state = self._check()
            while True:
                removed = [ref for ref in reuse if not
                    (relations.premise_closure([ref], state) & set(previous['bindings'])) <= set(reuse)]
                if not removed:
                    break
                for ref in removed:
                    del reuse[ref]
        old = self.store.read_blob(previous['version']) if previous else b''
        plan = dict(**basis, task_key=task_key, material_id=material_id, version=material['version'],
                    reuse=reuse, changed_ranges=changed_ranges(old, raw),
                    needs_recheck_refs=sorted(set(previous['bindings']) - set(reuse)) if previous else [],
                    previous_result=previous['task_key'] if previous else None,
                    scope=self.scope.to_wire())
        ref = self._save('plan', plan, [material['source_ref'], *reuse])
        return dict(status='NEEDS_CAPTURE', plan_ref=ref, plan=plan, reading=reading)

    def _current(self, result):
        state = self._check()
        refs = set(result['bindings']) | {use['source_ref'] for uses in result['bindings'].values() for use in uses}
        if not self._visible(refs):
            return False
        return self._support_basis(refs, state) == result['support_basis'] and not any(state.get('survey_source_status', {}).get(ref, {}).get(flag)
                       for ref in refs for flag in ('withdrawn', 'version_conflict'))

    def _support_basis(self, refs, state):
        closure = relations.premise_closure(refs, state)
        supports = {key: row for key, row in state['supports'].items()
                    if row.get('statement_ref') in closure or row.get('argument_ref') in closure}
        qualifications = {key: row for key, row in state['qualifications'].items()
                          if any(key in support.get('qualification_refs', []) for support in supports.values())}
        withdrawals = {key: row for key, row in state['withdrawals'].items() if row.get('support_id') in supports}
        return sha(canonical([supports, qualifications, withdrawals]))

    def _plan(self, ref):
        require(type(ref) is C.ExactRef and ref.project_id == self.scope.project_id,
                'KNOWLEDGE_FORBIDDEN', 'Exact plan in this project required')
        found = next((value for saved, value in self._rows('plan') if saved == ref), None)
        require(found is not None and found['scope'] == self.scope.to_wire(), 'KNOWLEDGE_FORBIDDEN', 'Plan unavailable')
        return found

    def complete(self, plan_ref, request_id):
        """Use ORIGINAL registered capture; never invent a task, call or receipt."""
        plan = self._plan(plan_ref)
        state = self._check([plan['source_ref'], *plan['reuse']])
        for ref, result in self._rows('result'):
            if result['task_key'] == plan['task_key'] and self._current(result):
                return dict(status='REUSED', result_ref=ref, result=result)
        request = state['requests'].get(request_id, {})
        task = state['tasks'].get(request.get('task_id'), {})
        require(task.get('instance_id') == self.scope.instance_id and task.get('actor_kind') != 'MAIN',
                'AUTHORIZATION_REQUIRED', 'Existing scoped extraction task required')
        packet = loads(self.store.read_blob(task['input_packet_ref']))
        require(packet.get('kb_summary_plan_ref') == plan_ref.to_wire(), 'AUTHORIZATION_REQUIRED',
                'Frozen host packet must bind this exact material/request plan')
        require(plan['source_ref'] in {i['ref'] for i in task.get('input_manifest', []) if i['kind'] == 'source'},
                'INCOMPLETE_CONTEXT', 'Task did not receive this exact material')
        self._check([i['ref'] for i in task['input_manifest'] if i['kind'] in ('source', 'record')])
        capture = request.get('capture_ref', request.get('capture_hash'))
        require(capture is not None, 'SUMMARY_CAPTURE_REQUIRED', 'Original host capture is missing; do not resample UNKNOWN')
        raw = self.store.read_blob(capture)
        envelope = loads(raw)
        require(envelope.get('payload_kind') == 'KNOWLEDGE_CHANGE', 'AUTHORIZATION_REQUIRED',
                'This adapter accepts extraction, not formal Survey/report/control output')
        change = envelope['payload']
        require(not change.get('new_obligation_proposals') and
                all(op.get('op') in {'NEW', 'REVISE', 'LINK'} for op in change.get('operations', [])),
                'AUTHORIZATION_REQUIRED', 'Extraction cannot create research obligations or change proof support')
        proposal = self.changes.validate_response(task, state, raw, 'live', self.store.read_blob)
        added = set(proposal['receipt']['content_added'])
        require(all(r['kind'] in KINDS for r in proposal.get('records', {}).values()),
                'AUTHORIZATION_REQUIRED', 'Extraction does not perform an independent Assessment')
        # Check the derived-output scope before native publication as well. A
        # rejected citation must not leave newly admitted out-of-scope objects.
        candidate = {**state, 'records': {**state['records'], **proposal.get('records', {})},
                     'relations': [*state['relations'], *proposal.get('relations', [])]}
        productions = {**state['production_events'], **proposal.get('production_events', {})}
        produced = {p['record_ref'] for p in productions.values() if p.get('request_id') == request_id}
        bindings = deepcopy(plan['reuse'])
        for record_ref in sorted(produced):
            require(candidate['records'][record_ref]['kind'] in KINDS, 'AUTHORIZATION_REQUIRED', 'Unsupported extraction kind')
            uses = [use for edge in candidate['relations'] if edge['source_ref'] == record_ref
                    and edge['created_by_event'] == 'CHANGE-' + sha(raw)
                    and edge['type'] in ('SOURCE_PROVENANCE', 'USED_SOURCE') for use in edge['evidence_bindings']]
            require(uses, 'SUMMARY_CITATION_REQUIRED', 'Every extracted object needs exact source provenance')
            for use in uses:
                K.source_use(use, state['sources'], self.store.read_blob)
                require(use['source_ref'] == plan['source_ref'], 'KNOWLEDGE_FORBIDDEN', 'New extraction exceeds selected source')
                for loc in use['locators']:
                    require(any(loc['blob_hash'] == read['blob_hash'] and read['start'] <= loc['start'] < loc['end'] <= read['end']
                                and loc['unit'] == read['unit'] for read in plan['locators']),
                            'KNOWLEDGE_SCOPE_LIMIT', 'Citation exceeds actual declared reading')
            bindings[record_ref] = uses
        require(bindings, 'SUMMARY_CITATION_REQUIRED', 'No extracted or reusable mathematical content')
        refs = set(bindings) | {u['source_ref'] for uses in bindings.values() for u in uses}
        self._check(refs)
        require(self._visible(refs, candidate), 'KNOWLEDGE_FORBIDDEN', 'Record dependencies outside current scope')
        self.store.commit(proposal)  # native lock, live guards, original capture, duplicate recovery
        state = self._check(refs)
        result = dict(task_key=plan['task_key'], material_id=plan['material_id'], version=plan['version'],
                      source_ref=plan['source_ref'], request=plan['request'], reading=plan['locators'], bindings=bindings,
                      request_id=request_id, capture_sha256=capture, reused_refs=sorted(set(bindings) - added),
                      added_refs=sorted(added), classification='SYNTHETIC_TEST_ONLY',
                      support_basis=self._support_basis(refs, state),
                      mathematical_qualification='SOURCE_EXTRACTION_ONLY; NO_INDEPENDENT_PROOF')
        result['markdown'] = self._render(result, state)
        ref = self._save('result', result, refs)
        return dict(status='COMPLETED', result_ref=ref, result=result)

    def _render(self, result, state):
        lines = ['# Summary', '', result['request'], '',
                 'Synthetic engineering fixture. Source extraction; no independent mathematical proof.', '']
        labels = dict(Context='Definitions and notation', Statement='Main results',
                      Argument='Source argument / proof outline', Example='Examples and boundaries', SourceEvidence='Source evidence')
        for kind in KINDS:
            selected = [ref for ref in result['bindings'] if state['records'][ref]['kind'] == kind]
            if not selected:
                continue
            lines.extend(['## ' + labels[kind], ''])
            for ref in selected:
                lines.extend([self.reader.get(self.store, ref)['body'], ''])
                citations = [f"{use['source_ref']} @ {loc['blob_hash']} UTF8 [{loc['start']},{loc['end']})"
                             for use in result['bindings'][ref] for loc in use['locators']]
                lines.extend(['Source: ' + '; '.join(citations) + '. Record: ' + ref, ''])
        lines.extend(['## Coverage', '', 'Only the declared source byte ranges were read. Unprovided text and independent review remain outside scope.', ''])
        return '\n'.join(lines)

    def export(self, result_ref):
        """Return Markdown for an authorized output file; no project mutation."""
        for ref, result in self._rows('result'):
            if ref == result_ref and self._current(result):
                return result['markdown']
        raise PMRSError('KNOWLEDGE_FORBIDDEN', 'Summary unavailable under current permissions or source status')
