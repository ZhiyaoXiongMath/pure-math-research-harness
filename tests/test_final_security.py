"""Preserved PDF confinement invariants; no provider or sandbox execution."""
from pathlib import Path
from unittest.mock import patch
import os, fcntl, struct, tempfile, unittest
from research_studio import pdf_filter as f
from research_studio.util import PMRSError
from research_studio.render import validate_tex, PREAMBLE, check_mounts, sandbox_command

def interpret(program,nr,arch,domain=1):
    data=struct.pack('<IIQ6Q',nr,arch,0,domain,0,0,0,0,0);ins=list(struct.iter_unpack('<HBBI',program));i=0;a=0
    for _ in range(512):
        op,t,ff,k=ins[i]
        if op==0x20:a=struct.unpack_from('<I',data,k)[0]
        elif op==0x15:i+=t if a==k else ff
        elif op==0x45:i+=t if a&k else ff
        elif op==6:return k
        else:raise AssertionError('Unknown emitted BPF')
        i+=1
    raise AssertionError('BPF does not terminate')

class SecurityTests(unittest.TestCase):
    def test_retained_restricted_syscall_floor_for_two_architectures(self):
        for arch in f.ARCH:
            program=f.compile_filter(arch)
            for call in f.DENIED:self.assertEqual(interpret(program,f.NUMBERS[arch][call],f.ARCH[arch]),f.DENY)
            for name in ('socket','socketpair'):
                self.assertEqual(interpret(program,f.NUMBERS[arch][name],f.ARCH[arch],1),f.ALLOW)
                for domain in (0,2,10,16):self.assertEqual(interpret(program,f.NUMBERS[arch][name],f.ARCH[arch],domain),f.DENY)
    def test_foreign_architecture_and_x32_rejected(self):
        p=f.compile_filter('x86_64');self.assertEqual(interpret(p,0,0),f.KILL);self.assertEqual(interpret(p,0x40000000,f.ARCH['x86_64']),f.KILL)
    def test_filter_sealed_and_closed(self):
        with f.sealed_filter() as fd:
            self.assertEqual(os.read(fd,4096),f.compile_filter());self.assertTrue(fcntl.fcntl(fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC)
            with self.assertRaises(OSError):os.write(fd,b'changed')
        with self.assertRaises(OSError):os.fstat(fd)
    def test_filter_failure_has_no_fallback(self):
        with patch('research_studio.pdf_filter.os.memfd_create',side_effect=OSError('no memfd')):
            with self.assertRaisesRegex(PMRSError,'PDF_FILTER_UNAVAILABLE'):
                with f.sealed_filter():self.fail('unexpected bypass')
    def test_unsafe_tex_and_macros_rejected(self):
        for body in (r'\input{/etc/passwd}',r'\write18{whoami}',r'\def\x{bad}',r'\csname input\endcsname{a}',r'\usepackage{evil}',r'^^5cinput{a}'):
            with self.assertRaises(PMRSError):validate_tex(body)
    def test_english_host_template(self):
        import re
        self.assertFalse(re.search('[\u3400-\u9fff]',PREAMBLE));self.assertIn('{article}',PREAMBLE);self.assertIn('{Theorem}',PREAMBLE)
    def test_nested_mount_and_daemon_alias_fail_closed(self):
        root='1 0 8:1 / / rw - ext4 disk rw\n'
        check_mounts(['/usr'],root)
        for extra in ('2 1 8:1 /extra /usr/bin rw - ext4 d rw\n',f'2 1 8:1 /tmp/codex-daemon-{os.geteuid()} /usr rw - ext4 d rw\n'):
            with self.assertRaises(PMRSError):check_mounts(['/usr'],root+extra)
    def test_namespace_chain_contains_no_root_bind_or_network_fallback(self):
        with tempfile.TemporaryDirectory() as tmp,patch('research_studio.render.tool',return_value='/usr/bin/bwrap'),patch('research_studio.render.check_mounts'):
            cmd=sandbox_command(Path(tmp),['/usr/bin/true'],3)
            for flag in ('--unshare-user','--unshare-pid','--unshare-ipc','--unshare-net','--cap-drop','--seccomp'):self.assertIn(flag,cmd)
            self.assertNotIn('--share-net',cmd);self.assertNotIn('--unshare-user-try',cmd)

if __name__ == '__main__': unittest.main()
