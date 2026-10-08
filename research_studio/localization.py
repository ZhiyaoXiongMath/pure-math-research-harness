"""Display-only localization, independent of frozen research semantics and language."""
import json
from functools import lru_cache
from pathlib import Path
from .util import read

SUPPORTED_LOCALES = ('en', 'zh-CN')


def normalize_locale(locale):
    return locale if locale in SUPPORTED_LOCALES else 'en'


def load_preferences(workspace_root):
    """Read the host preference without mutating research or starting a service."""
    try:
        data = json.loads(read(Path(workspace_root) / 'runtime/preferences.json', maximum=4096))
        return {'ui_locale': normalize_locale(data.get('ui_locale'))}
    except (OSError, ValueError, TypeError, AttributeError):
        return {'ui_locale': 'en'}


@lru_cache(maxsize=2)
def messages(locale='en'):
    locale = normalize_locale(locale)
    root = Path(__file__).with_name('locales')
    result = {}
    for path in [root / f'{locale}.json', *sorted(root.glob(f'*.{locale}.json'))]:
        if path.exists():
            result.update(json.loads(path.read_text(encoding='utf-8')))
    return result


def translate(key, locale='en', **params):
    template = messages(normalize_locale(locale)).get(key, messages('en').get(key, key))
    return template.format_map(params) if params else template


def check_completeness():
    baseline = set(messages('en'))
    return {locale: sorted(baseline - set(messages(locale))) for locale in SUPPORTED_LOCALES}


def build_static_messages():
    """Generate the browser copy from the same canonical resources used by native UI."""
    bundle = {locale: messages(locale) for locale in SUPPORTED_LOCALES}
    return ('/* Generated from research_studio/locales/*.json; do not edit directly. */\n'
            '(function(root){const messages=' + json.dumps(bundle, ensure_ascii=False, separators=(',', ':')) +
            ';root.PMRS_MESSAGES=messages;if(typeof module!=="undefined"&&module.exports)module.exports=messages;})'
            '(typeof window==="undefined"?globalThis:window);\n')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Validate and bundle display translations')
    parser.add_argument('--write-static', action='store_true')
    args = parser.parse_args()
    missing = check_completeness()
    if any(missing.values()):
        raise SystemExit(json.dumps(missing))
    if args.write_static:
        Path(__file__).with_name('static').joinpath('messages.js').write_text(build_static_messages(), encoding='utf-8')
