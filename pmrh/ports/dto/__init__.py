"""Public DTO namespaces and strict wire helpers, schema v1.0.

The parent pmrh.ports.interfaces statically imports the typed Port contracts,
which loads every DTO module. Keep this initializer lightweight to avoid
DTO-module -> package-export -> DTO-module dependency cycles. No module is
chosen or dynamically imported by a wire value.
"""
from . import enums
from .wire import SCHEMA_VERSION, ContractViolation, DTO, decode_wire

__all__ = ["enums", "SCHEMA_VERSION", "ContractViolation", "DTO", "decode_wire"]
