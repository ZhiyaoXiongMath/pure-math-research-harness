"""Language is a frozen policy, never a translation of authoritative inputs."""
from __future__ import annotations
from pmrh.domain.primitives import (
    authored_english,
    authored_with_quotes,
    research_data,
)
import re
from .util import require, sha, canonical

DEFAULT = {"input_languages": ["zh-CN", "en"], "interaction_language": "zh-CN",
           "research_language": "en", "report_language": "en", "preserve_original_sources": True}
# Symmetric lexical expansion only. No claim of semantic equivalence of proofs.
TERM_GROUPS = (
    ("removability", "removable", "可去性", "可去"),
    ("weak", "弱解", "弱延拓"), ("smooth", "regularity", "光滑", "正则性"),
    ("divisor", "除子"), ("residual", "残差"), ("compatibility", "相容", "兼容"),
    ("existence", "存在性", "存在"), ("energy", "能量"), ("flux", "通量"),
    ("lifting", "提升"), ("universal", "universalization", "普遍", "任意曲面"),
    ("counterexample", "反例"), ("proof", "证明"), ("review", "审查", "核查"),
    ("failure", "失败"), ("obligation", "义务", "缺口"),
    ("source", "原文", "来源"), ("shell", "球壳"), ("hermitian", "hermitian–einstein", "he"),
)
INDEX_POLICY = "pmrs.lexical-bilingual/2"

def policy(value=None):
    result = dict(DEFAULT if value is None else value)
    require(set(result) == set(DEFAULT), "LANGUAGE_POLICY_INVALID", "All language fields are required")
    require(result == DEFAULT, "LANGUAGE_POLICY_UNSUPPORTED", "Bilingual input, English research/report and Chinese interaction are required")
    return result

def tokens(text: str) -> set[str]:
    text = text.lower()
    terms = set(re.findall(r"[a-z][a-z0-9_-]{1,}", text))
    for group in TERM_GROUPS:
        if any((term in text if re.search(r'[\u3400-\u9fff]', term) else re.search(r'(?<![a-z0-9_])'+re.escape(term)+r'(?![a-z0-9_])', text)) for term in group):
            terms.update(group)
    return terms


def search_bodies(snapshot, query, blob_get):
    """A read-only bilingual index over exact source and scientific body ranges."""
    from .knowledge import locator
    rows=[];query_tokens=tokens(query)
    entries=[(ref,r['body_sha256']) for ref,r in snapshot.get('records',{}).items()]
    entries += [(ref,s.get('blob_hash',s.get('sha256'))) for ref,s in snapshot.get('sources',{}).items()]
    for ref,h in entries:
        raw=blob_get(h)
        require(sha(raw)==h,'ORIGINAL_BYTES_MISMATCH','Search source bytes changed')
        try:text=raw.decode('utf-8')
        except UnicodeError:continue
        matched=sorted(query_tokens & tokens(text))
        if not matched:continue
        # Locate an actual original term, not the expanded English synonym.
        actual=[m for m in matched if m.lower() in text.lower()]
        if not actual:continue
        term=sorted(actual,key=lambda t:(-len(t),t))[0];start=text.lower().index(term.lower());end=start+len(term)
        rows.append({'ref':ref,'sha256':h,'locator':locator(raw,start,end,'UNICODE_CODEPOINT'),'matched_terms':matched,'authority':'RETRIEVAL_ONLY','semantic_equivalence':'NOT_CERTIFIED'})
    return sorted(rows,key=lambda r:(-len(r['matched_terms']),r['ref']))

def instruction(value=None, *, report=False) -> str:
    p = policy(value)
    return ("Write all new mathematical prose, statements, proofs, plans, reviews and headings in English. "
            "Read Chinese or English original sources without changing their bytes, identities or authority. "
            "Retrieval and translation are not mathematical progress. Keep all conditional and open boundaries. "
            "Operational interaction with the researcher is Chinese. "
            + ("Both lecture and minimal report, including labels, must be English. " if report else ""))

def index_entry(ref, data: bytes, *, path=None):
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        text = ""
    terms = sorted(tokens(text))
    return {"ref": ref, "sha256": sha(data), "bytes": len(data), "path": path,
            "terms": terms, "index_policy": INDEX_POLICY, "authority": "NONE",
            "mathematical_progress": False, "original_preserved": True}

def search(entries, query):
    q = tokens(query)
    rows = [{"ref": e["ref"], "sha256": e["sha256"], "path": e.get("path"),
             "matched_terms": sorted(q & set(e["terms"])), "authority": "RETRIEVAL_ONLY"}
            for e in entries if q & set(e["terms"])]
    return sorted(rows, key=lambda e: (-len(e["matched_terms"]), e["ref"]))


REPORT_LABELS = {'OPEN':'Open', 'CONDITIONAL':'Conditional',
                 'CANDIDATE':'Candidate; not formally certified',
                 'BACKGROUND':'Background', 'INCONCLUSIVE':'Inconclusive'}
