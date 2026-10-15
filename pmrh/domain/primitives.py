"""Pure encodings, compatible errors and authored-language checks."""
from __future__ import annotations
import hashlib
import json
import re

MAX_JSON = 64 * 1024 * 1024

class PMRSError(ValueError):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")

ResearchStudioError = PMRSError

def require(condition, code, message):
    if not condition:
        raise PMRSError(code, message)

def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

sha256_bytes = sha

def identity(value, prefix="") -> str:
    return prefix + sha(canonical(value))

def loads(data: bytes | str, *, maximum=MAX_JSON):
    require(len(data) <= maximum, "JSON_LIMIT", "JSON exceeds the bounded parser size")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "JSON_DUPLICATE_KEY", key)
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, PMRSError):
            raise
        raise PMRSError("JSON_INVALID", str(exc)) from exc


def authored_english(text: str, field="body"):
    require(isinstance(text, str) and text.strip(), "ENGLISH_TEXT_REQUIRED", field)
    require(not re.search(r"[\u3400-\u9fff]", text), "LANGUAGE_MISMATCH",
            field + ": new prose must be English; retain Chinese quotations as source-bound inputs")

def authored_with_quotes(text, source_quotes=(), field='body'):
    """Screen authored prose while preserving explicitly verified source quotes.

    The caller supplies already byte-verified quotations. This is a syntax
    policy, never a claim of semantic equivalence or accurate translation.
    """
    require(isinstance(text,str) and text.strip(),'ENGLISH_TEXT_REQUIRED',field)
    screened=text
    for quote in source_quotes:
        require(isinstance(quote,str) and quote,'SOURCE_QUOTE_INVALID','Nonempty verified quotation required')
        screened=screened.replace(quote,'[SOURCE_BOUND quotation]')
    authored_english(screened,field)
    return text

def research_data(value):
    """Reject clearly non-English newly authored metadata, never rewrite it.

    This syntactic screen cannot prove natural-language correctness. Independent
    review still checks meaning. Original quotations remain in bound sources.
    """
    if isinstance(value, str):
        if value: authored_english(value, 'data')
    elif isinstance(value, dict):
        for key, item in value.items():
            authored_english(key, 'data key'); research_data(item)
    elif isinstance(value, list):
        for item in value: research_data(item)
