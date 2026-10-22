"""Closed application facade; proposal bytes never mint current authority."""
from pmrh.application.control import Control, AuthorityRegistry
from pmrh.domain.primitives import PMRSError
from pmrh.domain.fastmath.model import FastMathError, check

_ERROR_MAP = {
    'AUTHORIZATION_REQUIRED':'FAST_AUTHORITY_DENIED', 'UNTRUSTED_EVENT':'FAST_AUTHORITY_DENIED',
    'TASK_FENCED':'FAST_STATE_DENIED', 'EXECUTION_UNRESOLVED':'FAST_STATE_DENIED',
    'STALE_CONTROL_VERSION':'FAST_VERSION_CONFLICT', 'VERSION_CONFLICT':'FAST_VERSION_CONFLICT',
    'WRITE_CAS_CONFLICT':'FAST_VERSION_CONFLICT', 'IDEMPOTENCY_CONFLICT':'FAST_IDEMPOTENCY_CONFLICT',
    'ORIGINAL_BYTES_MISMATCH':'FAST_CAPTURE_MISMATCH', 'NOT_FOUND':'FAST_REF_UNAVAILABLE',
    'FILE_UNAVAILABLE':'FAST_REF_UNAVAILABLE', 'BLOB_CHANGED':'FAST_REF_UNAVAILABLE',
    'RESOURCE_LIMIT':'FAST_LIMIT_EXCEEDED', 'UNSUPPORTED_SCHEMA_VERSION':'FAST_SCHEMA_INVALID',
    'UNSUPPORTED_CAPABILITY':'FAST_SCHEMA_INVALID', 'CONTROL_INVALID':'FAST_SCHEMA_INVALID',
}


def _boundary(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except PMRSError as exc:
        # Preserve exact original cause privately; public hidden refs stay opaque.
        code = _ERROR_MAP.get(exc.code,'FAST_INTEGRITY_ERROR')
        raise FastMathError(code,'Fast transaction rejected; original diagnostic retained as cause') from exc


class FastMathService:
    def __init__(self, storage, control):
        check(type(control) is Control and type(control.registry) is AuthorityRegistry and
              getattr(control.storage,'fast',None) is storage and
              storage.control_storage is control.storage and storage.store is control.storage.store and
              getattr(control.storage,'service',None) is control,
              'Trusted same-root Control assembly required','FAST_AUTHORITY_DENIED')
        self.storage = storage
        self.control = control

    def prepare_delta(self,delta,*,read_context,as_of_commit):
        return _boundary(self.storage.prepare,delta,read_context,as_of_commit)

    def capture_delta(self,prepared,*,session,operation_id,idempotency_key,scope,expected_head,
                      owner_epoch,control_version,request_id,capture_ref,receipt_ref):
        return _boundary(self.storage.capture,prepared,session=session,operation_id=operation_id,
            idempotency_key=idempotency_key,scope=scope,expected_head=expected_head,owner_epoch=owner_epoch,
            control_version=control_version,request_id=request_id,capture_ref=capture_ref,receipt_ref=receipt_ref)

    def commit_delta(self,proposal_ref,*,session,operation_id,idempotency_key,scope,expected_head,
                     owner_epoch,control_version,grant_ref,manifest_ref):
        return _boundary(self.storage.apply,proposal_ref,session=session,operation_id=operation_id,
            idempotency_key=idempotency_key,scope=scope,expected_head=expected_head,owner_epoch=owner_epoch,
            control_version=control_version,grant_ref=grant_ref,manifest_ref=manifest_ref)

    def recover_receipt(self,scope,operation_id,session):
        return _boundary(self.storage.recover,scope,operation_id,session)
