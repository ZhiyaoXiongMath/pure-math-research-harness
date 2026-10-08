import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from research_studio.localization import (build_static_messages,check_completeness,load_preferences,messages,translate)


class DisplayLocalizationTests(unittest.TestCase):
    def test_canonical_resources_include_all_literal_and_stage_keys(self):
        self.assertFalse(any(check_completeness().values()))
        root=Path(__file__).resolve().parents[1]/'research_studio'
        self.assertEqual((root/'static/messages.js').read_text(),build_static_messages())
        source=(root/'static/workbench.js').read_text()
        keys=re.findall(r"\bm\(['\"]([^'\"]+)['\"]\)",source)
        self.assertFalse(set(keys)-set(messages('en')))
        self.assertNotIn('innerHTML',source)
        self.assertTrue(messages('en')['native.select_tectonic'])
        self.assertTrue(messages('zh-CN')['installer.title'])

    def test_host_preferences_default_and_fallback_do_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(load_preferences(root),{'ui_locale':'en'})
            self.assertEqual(list(root.iterdir()),[])
            (root/'runtime').mkdir();p=root/'runtime/preferences.json'
            p.write_text(json.dumps({'ui_locale':'zh-CN'}))
            self.assertEqual(load_preferences(root),{'ui_locale':'zh-CN'})
            p.write_text('{broken')
            self.assertEqual(load_preferences(root),{'ui_locale':'en'})
            self.assertEqual(p.read_text(),'{broken')
        self.assertEqual(translate('stage.S4.name','unsupported'),'Readiness review')

    def test_browser_display_invariants(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node is unavailable')
        result=subprocess.run([node,'--test',str(Path(__file__).with_name('locale-workbench.test.js'))],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
