"""Unchanged native schema/language validation (DEV05-SCOPE-01)."""
from pmrh.domain.primitives import require

SCHEMA_VERSION = "pmrs.project/4.2.2"

COMMIT_SCHEMA = "pmrs.commit/4.2.2"

DEFAULT = {"input_languages": ["zh-CN", "en"], "interaction_language": "zh-CN",
           "research_language": "en", "report_language": "en", "preserve_original_sources": True}

def policy(value=None):
    result = dict(DEFAULT if value is None else value)
    require(set(result) == set(DEFAULT), "LANGUAGE_POLICY_INVALID", "All language fields are required")
    require(result == DEFAULT, "LANGUAGE_POLICY_UNSUPPORTED", "Bilingual input, English research/report and Chinese interaction are required")
    return result
