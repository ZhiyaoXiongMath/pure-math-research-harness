"""Exact manuscript ranges and deterministic local revision assembly.

Only this host code splices a local revision. Author text, manuscript text and
quoted user material never select a different project, version or byte range.
"""
from copy import deepcopy
import re
from .util import require, sha

SECTION = re.compile(rb'(?m)^\\section\{([^{}\r\n]+)\}[^\S\r\n]*(?:\r?\n|$)')


def sections(body):
    raw = body.encode('utf-8') if isinstance(body, str) else body
    require(isinstance(raw, bytes), 'REPORT_BODY_REQUIRED', 'Exact manuscript bytes required.')
    matches = list(SECTION.finditer(raw)); result = []
    for index, match in enumerate(matches):
        start = match.start(); end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        title = match.group(1).decode('utf-8')
        result.append({'id': 'SECTION-' + str(index + 1) + '-' + sha(match.group(1))[:12],
                       'number': index + 1, 'title': title, 'start_byte': start,
                       'end_byte': end, 'sha256': sha(raw[start:end])})
    return result


def normalize_scope(body, scope):
    require(isinstance(scope, dict), 'REPORT_REVISION_SCOPE', 'Explicit full or exact section scope required.')
    if scope == {'kind': 'FULL'}:
        return deepcopy(scope)
    require(set(scope) == {'kind', 'sections'} and scope['kind'] == 'SECTIONS'
            and isinstance(scope['sections'], list) and scope['sections']
            and all(isinstance(s, str) for s in scope['sections'])
            and len(set(scope['sections'])) == len(scope['sections']),
            'REPORT_REVISION_SCOPE', 'A unique nonempty list of selected section identities is required.')
    directory = sections(body); selected = set(scope['sections'])
    require(selected <= {s['id'] for s in directory}, 'REPORT_REVISION_SCOPE', 'Selected section is absent from the exact old manuscript.')
    return {'kind': 'SECTIONS', 'sections': [s['id'] for s in directory if s['id'] in selected],
            'ranges': [s for s in directory if s['id'] in selected]}


def assemble(old, scope, replacements):
    """Preserve every unselected byte, including comments and whitespace."""
    require(isinstance(replacements, list) and len(replacements) == len(scope['ranges']),
            'REPORT_REVISION_RANGE', 'Return each selected section exactly once.')
    supplied = {}
    for row in replacements:
        require(isinstance(row, dict) and set(row) == {'section_id', 'body'}
                and isinstance(row['body'], str) and row['section_id'] not in supplied,
                'REPORT_REVISION_RANGE', 'Each replacement requires one exact section identity and body.')
        supplied[row['section_id']] = row['body'].encode('utf-8')
    require(set(supplied) == set(scope['sections']), 'REPORT_REVISION_RANGE', 'Author cannot enlarge the selected section scope.')
    cursor = 0; parts = []; preserved = []
    for row in scope['ranges']:
        start, end = row['start_byte'], row['end_byte']
        require(sha(old[start:end]) == row['sha256'], 'REPORT_CONTENT_STALE', 'Selected original section bytes changed.')
        unchanged = old[cursor:start]; parts.append(unchanged)
        preserved.append({'start_byte': cursor, 'end_byte': start, 'sha256': sha(unchanged)})
        replacement = supplied[row['id']]
        heading = SECTION.match(old[start:end]); new_heading = SECTION.match(replacement)
        require(heading and new_heading and heading.group(1) == new_heading.group(1)
                and len(sections(replacement)) == 1,
                'REPORT_REVISION_RANGE', 'Local revision retains its selected heading and cannot insert other sections.')
        parts.append(replacement); cursor = end
    parts.append(old[cursor:]); preserved.append({'start_byte': cursor, 'end_byte': len(old), 'sha256': sha(old[cursor:])})
    return b''.join(parts), preserved
