"""Fast mathematical navigation grounded in exact native evidence."""
from .model import FastMathError, FastReadContext, PreparedFastDelta, make_revision
from .validation import validate_delta, native_projection
from .qualification import project

__all__ = ['FastMathError', 'FastReadContext', 'PreparedFastDelta', 'make_revision',
           'validate_delta', 'native_projection', 'project']
