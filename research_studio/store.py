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

    def _publish(self, previous, before, after, *, actor, events, base=None, accepted=None):
        return super()._publish(previous, before, after, actor=actor, events=events,
                                base=base, accepted=accepted, at=now(),
                                checkpoint_interval=CHECKPOINT_INTERVAL)

    def _read_file(self, path, *args, **kwargs):
        return read(path, *args, **kwargs)
