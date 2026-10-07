"""Actual Ubuntu renderer confinement, separate from deterministic filter tests."""
from pathlib import Path
import errno,json,os,tempfile,unittest
from research_studio.render import doctor,isolated,Renderer
from research_studio.util import PMRSError

class ActualRenderTests(unittest.TestCase):
    def test_real_namespace_seccomp_files_symlinks_and_network_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=root/'isolated';work.mkdir(mode=0o700)
            secret=root/'private.txt';secret.write_text('This must never be visible to the renderer.')
            (work/'escape').symlink_to(secret)
            program='''import os,socket,json,errno
paths=[%r,%r,'/etc/passwd']
for path in paths:
 try:
  with open(path,'rb') as f:f.read()
 except OSError as e:assert e.errno in (errno.ENOENT,errno.EACCES,errno.EPERM)
 else:raise AssertionError('host file escaped the namespace: '+path)
for family in (socket.AF_INET,socket.AF_INET6):
 try:s=socket.socket(family,socket.SOCK_STREAM)
 except OSError as e:assert e.errno==errno.EPERM
 else:s.close();raise AssertionError('network socket was not denied by seccomp')
with open('/proc/self/status') as f:d=dict(x.strip().split(':',1) for x in f if ':' in x)
assert all(int(d[k],16)==0 for k in ('CapInh','CapPrm','CapEff','CapAmb'))
assert d['NoNewPrivs'].strip()=='1' and d['Seccomp'].strip()=='2'
print(json.dumps({'host_files_denied':3,'network_families_denied':2,'capabilities_zero':True,'no_new_privs':True,'seccomp':2}))
'''%(str(secret),str(work/'escape'))
            result=json.loads(isolated(work,['/usr/bin/python3','-I','-S','-c',program]))
            self.assertEqual(result,{'host_files_denied':3,'network_families_denied':2,'capabilities_zero':True,'no_new_privs':True,'seccomp':2})
            with self.assertRaisesRegex(PMRSError,'PDF_ISOLATED_TOOL_FAILED'):
                isolated(work,['/usr/bin/python3','-I','-S','-c','raise RuntimeError("Required isolation fails closed.")'])
            self.assertEqual(secret.read_text(),'This must never be visible to the renderer.')

    def test_actual_doctor_and_tectonic_poppler_fonts_render_all_pages(self):
        d=doctor();self.assertFalse(d['missing']);self.assertTrue(d['cache_present'])
        self.assertEqual(d['production_render_test'],'NOT_RUN');self.assertEqual(d['model_calls'],0);self.assertEqual(d['network_downloads'],0)
        result=Renderer()(b'\\section*{Isolation capability probe}\nA sourced open statement remains open: $x=x$.\\newpage\nThe second page verifies complete raster output.')
        self.assertFalse(result['synthetic']);self.assertTrue(result['pdf'].startswith(b'%PDF-'))
        self.assertEqual(len(result['pages']),2)
        for page in result['pages']:self.assertTrue(page.startswith(b'\x89PNG\r\n\x1a\n'))
        env=result['environment'];self.assertTrue(env['namespace_isolated']);self.assertTrue(env['offline']);self.assertTrue(env['all_pages_rendered'])
        self.assertEqual(set(env['fonts']),{'DejaVu Serif','DejaVu Sans','DejaVu Sans Mono'})
        self.assertEqual(set(env['tools']),{'tectonic','pdfinfo','pdftotext','pdftoppm','fc-match','bwrap'})
        self.assertTrue(all(len(v)==64 for v in env['tools'].values()));self.assertEqual(len(env['seccomp']),64)
        self.assertEqual(len(env['verifier']),64);self.assertTrue(result['semantic_environment']['cache'])

if __name__=='__main__':unittest.main()
