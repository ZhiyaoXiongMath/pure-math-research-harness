"""Regression coverage for real-host PDF dependency discovery. No model calls."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_studio import render
from research_studio.util import PMRSError


class RenderDependencyTests(unittest.TestCase):
    def test_system_poppler_wins_over_unmounted_path_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);system=root/'system';wrappers=root/'wrappers'
            system.mkdir();wrappers.mkdir()
            for directory in (system,wrappers):
                exe=directory/'pdfinfo';exe.write_text('#!/bin/sh\nexit 0\n');exe.chmod(0o755)
            with patch.dict(os.environ,{'PATH':str(wrappers)},clear=True),patch.object(render,'SYSTEM_BIN',system):
                self.assertEqual(render.tool('pdfinfo'),str(system/'pdfinfo'))

    def test_explicit_tool_override_is_honored_and_never_silently_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'pdfinfo';exe.write_text('#!/bin/sh\nexit 0\n');exe.chmod(0o755)
            with patch.dict(os.environ,{'RS_PDFINFO_BINARY':str(exe)}):
                self.assertEqual(render.tool('pdfinfo'),str(exe))
                exe.unlink()
                with self.assertRaisesRegex(PMRSError,'PDF_TOOL_MISSING'):render.tool('pdfinfo')

    def test_path_only_compiler_remains_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);exe=root/'tectonic';exe.write_text('#!/bin/sh\nexit 0\n');exe.chmod(0o755)
            with patch.dict(os.environ,{'PATH':tmp},clear=True),patch.object(render,'SYSTEM_BIN',root/'absent'):
                self.assertEqual(render.tool('tectonic'),str(exe))

    def test_ca_file_is_read_only_without_mounting_private_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=root/'public-ca.pem';bundle.write_text('-----BEGIN CERTIFICATE-----\nfixture\n')
            work=root/'scratch';work.mkdir(mode=0o700)
            with patch.object(render,'CA_BUNDLES',(str(bundle),)),patch.object(render,'tool',return_value='/usr/bin/bwrap'),patch.object(render,'check_mounts'):
                command=render.sandbox_command(work,['/usr/bin/true'],3)
            mounts=[command[i+1:i+3] for i,x in enumerate(command) if x=='--ro-bind']
            self.assertIn([str(bundle),render.SANDBOX_CA],mounts)
            self.assertFalse(any(src in ('/','/etc','/etc/ssl','/etc/ssl/private') for src,_ in mounts))
            self.assertIn('--unshare-net',command);self.assertIn('--seccomp',command)

    def test_missing_ca_has_actionable_error_and_doctor_does_not_claim_render_pass(self):
        with patch.object(render,'CA_BUNDLES',()):
            with self.assertRaisesRegex(PMRSError,'PDF_CA_BUNDLE_MISSING'):render.ca_bundle()
            info=render.doctor()
            self.assertIn('ca-certificates',info['missing']);self.assertIsNone(info['ca_bundle'])
            self.assertEqual(info['production_render_test'],'NOT_RUN')

    def test_invalid_ca_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.pem';p.write_text('not a public certificate')
            with patch.object(render,'CA_BUNDLES',(str(p),)):
                with self.assertRaisesRegex(PMRSError,'PDF_CA_BUNDLE_INVALID'):render.ca_bundle()
