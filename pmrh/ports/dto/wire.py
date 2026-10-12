"""Strict, closed-schema, deeply immutable standard-library value objects.

Only exact built-in scalars, enums, tuples and registered DTOs are accepted.
Construction does not coerce strings to numbers/enums or retain mutable input.
Wire arrays/objects are rebuilt as tuples/DTOs; arbitrary Python objects,
unknown members, duplicate JSON members and unknown versions are rejected.
This is a value contract, not a sandbox against object.__setattr__/reflection.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from functools import lru_cache
import hashlib
import json
import types
from typing import Literal, Union, get_args, get_origin, get_type_hints

from .enums import ErrorCode

SCHEMA_VERSION = "pmrh.ports/1.0"
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_TUPLE_ITEMS = 4096
_REGISTRY: dict[str, type] = {}


class ContractViolation(ValueError):
    """Safe diagnostic: never includes rejected values or untrusted key names."""

    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        super().__init__(message)


def require(condition: bool, message: str,
            code: ErrorCode = ErrorCode.INVALID_FIELD) -> None:
    if not condition:
        raise ContractViolation(code, message)


def identifier(value: str) -> None:
    require(bool(value) and len(value) <= 256 and value.strip() == value
            and not any(ord(c) < 33 or ord(c) == 127 for c in value),
            "Expected a nonempty bounded identifier, not free-form content.")


def digest(value: str) -> None:
    require(len(value) == 64 and all(c in "0123456789abcdef" for c in value),
            "Expected an exact lowercase SHA-256 digest.")


def nonnegative(value: int) -> None:
    require(value >= 0, "Expected a nonnegative integer.")


@lru_cache(maxsize=None)
def _hints(cls: type) -> dict:
    # Evaluates only developer-authored annotations, never wire-provided code.
    return get_type_hints(cls)


def _typed(expected, value, *, wire: bool):
    origin, args = get_origin(expected), get_args(expected)
    if origin in (Union, types.UnionType):
        for option in args:
            try:
                return _typed(option, value, wire=wire)
            except ContractViolation:
                pass
        raise ContractViolation(ErrorCode.TYPE_MISMATCH,
                                "Value does not match the declared union.")
    if origin is Literal:
        require(any(type(value) is type(x) and value == x for x in args),
                "Value is outside the declared literal contract.", ErrorCode.INVALID_FIELD)
        return value
    if origin is tuple:
        require(type(value) is (list if wire else tuple),
                "Expected a wire array or immutable constructor tuple.", ErrorCode.TYPE_MISMATCH)
        require(len(value) <= MAX_TUPLE_ITEMS, "Sequence exceeds the contract bound.")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_typed(args[0], x, wire=wire) for x in value)
        require(len(value) == len(args), "Tuple arity differs from the contract.")
        return tuple(_typed(t, x, wire=wire) for t, x in zip(args, value))
    if isinstance(expected, type) and issubclass(expected, Enum):
        if wire:
            require(type(value) is str, "Expected a string enum value.", ErrorCode.TYPE_MISMATCH)
            try:
                return expected(value)
            except ValueError:
                raise ContractViolation(ErrorCode.INVALID_FIELD,
                                        "Unknown enumeration value.") from None
        require(type(value) is expected, "Expected the exact enum type.", ErrorCode.TYPE_MISMATCH)
        return value
    if isinstance(expected, type) and issubclass(expected, DTO):
        if wire:
            return expected.from_wire(value)
        require(type(value) is expected and _REGISTRY.get(expected.__name__) is expected,
                "Expected the exact registered DTO, not an implementation object.",
                ErrorCode.TYPE_MISMATCH)
        return value
    if expected in (str, int, bool, type(None)):
        require(type(value) is expected, "Scalar type differs from the contract.",
                ErrorCode.TYPE_MISMATCH)
        if expected is str:
            try:
                value.encode("utf-8")
            except UnicodeError:
                raise ContractViolation(ErrorCode.INVALID_WIRE, "Invalid Unicode scalar.") from None
        return value
    raise ContractViolation(ErrorCode.TYPE_MISMATCH,
                            "Unsupported type at the DTO boundary.")


def _encode(value):
    if isinstance(value, DTO):
        require(_REGISTRY.get(type(value).__name__) is type(value),
                "Unregistered DTO type.", ErrorCode.INVALID_WIRE)
        return {"dto_type": type(value).__name__,
                **{f.name: _encode(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, Enum):
        return value.value
    if type(value) is tuple:
        return [_encode(x) for x in value]
    if type(value) in (str, int, bool, type(None)):
        return value
    raise ContractViolation(ErrorCode.INVALID_WIRE,
                            "Implementation objects cannot cross the wire boundary.")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ContractViolation(ErrorCode.INVALID_WIRE, "Duplicate JSON object member.")
        result[key] = value
    return result


def _constant(_value):
    raise ContractViolation(ErrorCode.INVALID_WIRE, "Non-finite JSON numbers are prohibited.")


@dataclass(frozen=True, slots=True, kw_only=True)
class DTO:
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        require(type(self.schema_version) is str and self.schema_version == SCHEMA_VERSION,
                "Unsupported DTO schema version; no automatic migration is permitted.",
                ErrorCode.UNSUPPORTED_SCHEMA_VERSION)
        hints = _hints(type(self))
        for f in fields(self):
            _typed(hints[f.name], getattr(self, f.name), wire=False)
        self._validate()

    def _validate(self) -> None:
        """Additional pure invariants, overridden by the declared DTO type."""

    def to_wire(self) -> dict:
        return _encode(self)

    def to_json(self) -> str:
        return json.dumps(self.to_wire(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)

    def wire_digest(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_wire(cls, value):
        require(type(value) is dict, "Expected a JSON object.", ErrorCode.TYPE_MISMATCH)
        require(value.get("schema_version") == SCHEMA_VERSION,
                "Unsupported or missing schema version; no implicit upgrade.",
                ErrorCode.UNSUPPORTED_SCHEMA_VERSION)
        require(type(value.get("dto_type")) is str and value["dto_type"] == cls.__name__
                and _REGISTRY.get(cls.__name__) is cls,
                "Unexpected DTO type identity.", ErrorCode.INVALID_WIRE)
        names = {f.name for f in fields(cls)}
        require(names <= value.keys(), "Required DTO member is missing.", ErrorCode.MISSING_FIELD)
        require(value.keys() == names | {"dto_type"}, "Unknown DTO member.", ErrorCode.INVALID_WIRE)
        hints = _hints(cls)
        return cls(**{name: _typed(hints[name], value[name], wire=True) for name in names})

    @classmethod
    def from_json(cls, text: str):
        require(type(text) is str, "Expected JSON text.", ErrorCode.TYPE_MISMATCH)
        try:
            require(len(text.encode("utf-8")) <= MAX_JSON_BYTES, "Wire document is too large.")
            value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
        except (json.JSONDecodeError, UnicodeError, RecursionError):
            raise ContractViolation(ErrorCode.INVALID_WIRE, "Malformed JSON document.") from None
        return cls.from_wire(value)


def frozen_dto(cls):
    """Register only trusted source-defined dataclasses; not a wire plugin loader."""
    require(cls.__name__ not in _REGISTRY, "Duplicate DTO type registration.")
    value = dataclass(frozen=True, slots=True, kw_only=True)(cls)
    _REGISTRY[value.__name__] = value
    return value


def decode_wire(value: dict) -> DTO:
    require(type(value) is dict and type(value.get("dto_type")) is str,
            "Missing DTO type identity.", ErrorCode.INVALID_WIRE)
    cls = _REGISTRY.get(value["dto_type"])
    require(cls is not None, "Unknown DTO type identity.", ErrorCode.INVALID_WIRE)
    return cls.from_wire(value)
