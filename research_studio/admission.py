"""Single final validator facade; no preview or recovery-specific fallback."""
from .changes import validate_response, live_check, revalidate

def validate(task,snapshot,raw,mode='preflight',blob_get=None):
    return validate_response(task,snapshot,raw,mode,blob_get)

def evaluate(task,state,raw,*,live=False,blob_get=None):
    return validate_response(task,state,raw,'live' if live else 'preflight',blob_get)
