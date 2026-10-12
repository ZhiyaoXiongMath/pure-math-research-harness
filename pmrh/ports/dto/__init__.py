"""Public DTO modules, closed schema v1.0; importing never contacts a backend.

Use exact module paths, e.g. pmrh.ports.dto.specs.AgentInvocationSpec. Import all
source-defined DTO modules here so decode_wire has a closed, complete registry.
No caller-supplied module or SDK type is dynamically loaded.
"""
from . import capability, control, core, enums, events, execution, orchestration, specs, storage
from .wire import SCHEMA_VERSION, ContractViolation, DTO, decode_wire

__all__ = [
    "capability", "control", "core", "enums", "events", "execution", "orchestration", "specs", "storage",
    "SCHEMA_VERSION", "ContractViolation", "DTO", "decode_wire",
]
