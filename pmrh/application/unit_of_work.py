"""Local staging and current permit orchestration over an injected disk capability.

The trusted policy and intent builder are assembly inputs, never project data.
They must be local, bounded and share the storage writer exclusion contract.
No network, model, concrete adapter or scientific reducer is imported here.
"""
import secrets

from pmrh.domain.primitives import PMRSError
from pmrh.ports.dto import control as P, core as C, enums as E, storage as T
from pmrh.ports.dto.wire import ContractViolation


class UnitOfWork:
    def __init__(self, storage, *, policy=None, intent_builder=None):
        self.storage = storage
        self.policy = policy
        self.intent_builder = intent_builder
        self._transactions = {}
        self._uncertain = set()

    def _error(self, exc, operation):
        try:
            code = E.ErrorCode(getattr(exc, 'code', None))
        except (ValueError, TypeError):
            code = E.ErrorCode.UNOBSERVED
        return C.port_error(code, operation)

    def begin(self, expected):
        try:
            if type(expected) is not T.VersionExpectation:
                return C.port_error(E.ErrorCode.INVALID_FIELD, E.Operation.BEGIN_TRANSACTION)
            expected.to_wire()
            self.storage.validate_boundary(expected)
            tx = T.TransactionHandle(transaction_id='transaction:'+secrets.token_hex(24), expected=expected)
            self._transactions[tx.transaction_id] = (tx, None)
            return tx
        except Exception as exc:
            return self._error(exc, E.Operation.BEGIN_TRANSACTION)

    def _entry(self, transaction):
        if type(transaction) is not T.TransactionHandle:
            return None
        entry = self._transactions.get(transaction.transaction_id)
        return entry if entry is not None and entry[0] == transaction else None

    def stage(self, transaction, batch):
        entry = self._entry(transaction)
        if entry is None:
            return C.port_error(E.ErrorCode.TRANSACTION_CLOSED, E.Operation.STAGE_TRANSACTION)
        if entry[1] is not None and entry[1] != batch:
            return C.port_error(E.ErrorCode.IDEMPOTENCY_CONFLICT, E.Operation.STAGE_TRANSACTION)
        try:
            # Roundtrip validates exact DTO types and the aggregate document bound.
            frozen = T.CommitBatch.from_wire(batch.to_wire())
            staged = T.StagingReceipt(transaction=transaction, batch_digest=frozen.wire_digest(),
                                      state=E.TransactionState.OPEN)
            self._transactions[transaction.transaction_id] = (transaction, frozen)
            return staged
        except (ContractViolation, ValueError, AttributeError) as exc:
            return self._error(exc, E.Operation.STAGE_TRANSACTION)

    def commit_intent(self, transaction):
        entry = self._entry(transaction)
        if entry is None or entry[1] is None:
            raise PMRSError('TRANSACTION_CLOSED', 'No staged transaction')
        if self.policy is None or self.intent_builder is None:
            raise PMRSError('AUTHORIZATION_REQUIRED', 'Trusted local policy context required')
        batch = entry[1]
        staged = T.StagingReceipt(transaction=transaction, batch_digest=batch.wire_digest(), state=E.TransactionState.OPEN)
        intent = self.intent_builder(staged, batch)
        expected = transaction.expected
        if not (type(intent) is P.OperationIntent and intent.operation is E.Operation.COMMIT and
                intent.operation_id == batch.operation_id and intent.scope == expected.boundary.scope and
                intent.payload_digest == staged.wire_digest() and intent.owner_epoch == expected.owner_epoch and
                intent.expected_control_version == expected.expected_control_version):
            raise PMRSError('AUTHORIZATION_REQUIRED', 'Intent does not bind the staged transaction')
        return intent

    def commit(self, transaction, permit):
        entry = self._entry(transaction)
        if entry is None or entry[1] is None:
            return C.port_error(E.ErrorCode.TRANSACTION_CLOSED, E.Operation.COMMIT)
        batch = entry[1]
        try:
            with self.storage.locked():
                intent = self.commit_intent(transaction)
                verified = self.policy.verify(permit, intent)
                if isinstance(verified, C.ErrorEnvelope):
                    return verified
                if not (type(verified) is P.PermitVerification and verified.intent == intent and
                        type(permit) is P.OperationPermit and verified.decision_ref == permit.decision_ref):
                    return C.port_error(E.ErrorCode.AUTHORIZATION_REQUIRED, E.Operation.COMMIT)
                staged = T.StagingReceipt(transaction=transaction, batch_digest=batch.wire_digest(),
                                          state=E.TransactionState.OPEN)
                self._uncertain.add(transaction.transaction_id)
                receipt = self.storage.publish(staged, batch)
                self._uncertain.discard(transaction.transaction_id)
                del self._transactions[transaction.transaction_id]
                return receipt
        except Exception as exc:
            # HEAD may already be durable. Retain original staging for operation
            # lookup; neither rollback nor retry sends any external request.
            return self._error(exc, E.Operation.COMMIT)

    def rollback(self, transaction):
        if self._entry(transaction) is None or transaction.transaction_id in self._uncertain:
            return C.port_error(E.ErrorCode.TRANSACTION_CLOSED, E.Operation.ROLLBACK)
        del self._transactions[transaction.transaction_id]
        return T.RollbackReceipt(transaction_id=transaction.transaction_id, state=E.TransactionState.ROLLED_BACK)
