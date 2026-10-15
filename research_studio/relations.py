"""Compatibility facade for the single pmrh.domain.relations implementation."""
from pmrh.domain.relations import (
    FIELDS,
    PREMISES,
    REGISTRY,
    TYPES,
    _acyclic,
    acyclic,
    affected_supports,
    closure,
    edges,
    is_premise,
    kind_of,
    premise_closure,
    relation,
    validate_relation,
    validate_support_graph,
)
