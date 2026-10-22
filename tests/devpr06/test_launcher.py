"""Launcher evidence accounting, executed only inside the same S2 suite."""
import hashlib
import json
import os
import signal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts.offline_control import run_logged


class LauncherTests(unittest.TestCase):
    def test_durable_partial_logs_normal_failure_timeout_interruption_and_incomplete(self):
        for scenario, status, code in [('fail','FAIL',1), ('timeout','TIMEOUT',124),
                ('interrupt','INTERRUPTED',143), ('incomplete','INCOMPLETE',1), ('pass','PASS',0)]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp); receipt={'isolation':'NOT_ESTABLISHED'}
                command=[sys.executable,'-B','/source/tests/devpr06/child.py','launcher',scenario]
                result=run_logged(command,out,receipt,timeout=2 if scenario=='timeout' else 20)
                saved=json.loads((out/'receipt.json').read_bytes())
                self.assertEqual((result,saved['status']),(code,status))
                self.assertEqual(saved,receipt)
                for name in ('stdout','stderr'):
                    raw=(out/(name+'.log')).read_bytes()
                    self.assertIn(('partial '+name).encode(),raw)
                    self.assertEqual(saved[name+'_sha256'],hashlib.sha256(raw).hexdigest())
                self.assertEqual(saved['completed'],scenario in {'fail','incomplete','pass'})
                if scenario in {'timeout','interrupt'}:self.assertLess(saved['exit_code'],0)

    def test_interrupt_at_spawn_return_retains_child_for_bounded_cleanup(self):
        from scripts import offline_control as launcher
        original=launcher.subprocess.Popen; launched=[]
        def spawn(*args,**kwargs):
            child=original(*args,**kwargs);launched.append(child)
            # Deterministic signal before run_logged can assign its child.
            os.kill(os.getpid(),signal.SIGTERM)
            return child
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);receipt={'isolation':'NOT_ESTABLISHED'}
            command=[sys.executable,'-B','/source/tests/devpr06/child.py','launcher','timeout']
            try:
                with patch.object(launcher.subprocess,'Popen',side_effect=spawn):
                    result=run_logged(command,out,receipt,timeout=20)
                self.assertEqual((result,receipt['status'],receipt['signal']),(143,'INTERRUPTED',signal.SIGTERM))
                self.assertEqual(len(launched),1);self.assertIsNotNone(launched[0].poll())
                self.assertLess(receipt['exit_code'],0);self.assertFalse(receipt['completed'])
                self.assertNotIn('drain_error',receipt)
                self.assertEqual(json.loads((out/'receipt.json').read_bytes()),receipt)
                for name in ('stdout','stderr'):
                    self.assertEqual(receipt[name+'_sha256'],hashlib.sha256((out/(name+'.log')).read_bytes()).hexdigest())
            finally:
                for child in launched:
                    if child.poll() is None:child.kill()
                    child.wait(timeout=5)
                    for stream in (child.stdout,child.stderr):
                        if stream is not None:stream.close()

    def test_interrupt_after_pipe_read_preserves_consumed_bytes(self):
        from scripts import offline_control as launcher
        original=launcher.os.read; consumed=[]
        def read(descriptor,size):
            data=original(descriptor,size)
            if data and not consumed:
                consumed.append(data)
                # Deterministic signal after bytes leave the pipe but before
                # run_logged receives/writes them. No timing assumption.
                os.kill(os.getpid(),signal.SIGTERM)
            return data
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);receipt={'isolation':'NOT_ESTABLISHED'}
            command=[sys.executable,'-B','/source/tests/devpr06/child.py','launcher','timeout']
            with patch.object(launcher.os,'read',side_effect=read):
                result=run_logged(command,out,receipt,timeout=20)
            self.assertEqual((result,receipt['status'],receipt['signal']),(143,'INTERRUPTED',signal.SIGTERM))
            self.assertEqual(len(consumed),1);self.assertIn(b'partial ',consumed[0])
            raw=[(out/(name+'.log')).read_bytes() for name in ('stdout','stderr')]
            self.assertTrue(any(consumed[0] in value for value in raw))
            self.assertLess(receipt['exit_code'],0);self.assertFalse(receipt['completed'])
            self.assertNotIn('drain_error',receipt)
            self.assertEqual(json.loads((out/'receipt.json').read_bytes()),receipt)
            for name,value in zip(('stdout','stderr'),raw):
                self.assertEqual(receipt[name+'_sha256'],hashlib.sha256(value).hexdigest())
