"""Compatible native Store facade over the one shared disk engine."""
from pmrh.adapters.storage.journal import (
    Journal, CHECKPOINT_INTERVAL, CHECKPOINT_RETAIN, CHECKPOINT_CACHE_BYTES,
    CHECKPOINT_STATE_BYTES, SCIENCE_MAPS, CONTROL_MAPS, EXECUTION_MAPS,
    REPORT_MAPS, EPHEMERAL, _native_only, _persistent, _diff, _apply_delta,
)
from .storage_compat import (
    LegacyWriters, initial_state, SURVEY_MAPS, ASSISTANT_MAPS, NATIVE_MAIN_MAPS,
)
from .util import now, read, canonical, sha, loads, require, safe_path, immutable, atomic, PMRSError

class Store(LegacyWriters, Journal):
    _other_control_maps = SURVEY_MAPS | ASSISTANT_MAPS

    def commit(self, validated, expected_relevant_guards=None, *, admission_recheck=None):
        """Route control-profile captures through the single admission gate."""
        if self.history()[-1][1]['schema'] in ('pmrh.commit/2', 'pmrh.control-fast.commit/1'):
            from pmrh.adapters.storage.control import exact
            task = getattr(validated, '_task', None)
            require(type(task) is dict and getattr(validated, '_raw', None) is not None and admission_recheck is None,
                    'UNSUPPORTED_CAPABILITY', 'Control profile admits only original frozen request captures')
            capture = exact(self, self._marker()['project_id'], 'capture:'+task['request_id'], validated._raw, raw=True)
            return self._control_native('SCIENCE_ADMITTED', {'request_id':task['request_id'], 'capture_ref':capture})
        return super().commit(validated, expected_relevant_guards, admission_recheck=admission_recheck)

    def _publish(self, previous, before, after, *, actor, events, base=None, accepted=None):
        return super()._publish(previous, before, after, actor=actor, events=events,
                                base=base, accepted=accepted, at=now(),
                                checkpoint_interval=CHECKPOINT_INTERVAL)

    def _read_file(self, path, *args, **kwargs):
        return read(path, *args, **kwargs)

    def fastmath_service(self):
        from .storage_compat import assemble_fastmath
        service = getattr(self, '_control_service', None)
        require(service is not None, 'AUTHORIZATION_REQUIRED', 'Trusted control assembly required')
        return assemble_fastmath(service)
