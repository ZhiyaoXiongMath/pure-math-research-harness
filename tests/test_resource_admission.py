"""Small physical admission checks; no host exhaustion or OS resource limits."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os,subprocess,sys,unittest
from research_studio import resources
from research_studio.util import PMRSError


class PhysicalAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        env=patch.dict(os.environ,{'PMRS_HOST_POOL_ROOT':str(self.root/'host')});env.start();self.addCleanup(env.stop)

    def test_shared_filesystem_reservations_prevent_double_promising_free_bytes(self):
        one=self.root/'one';two=self.root/'two';one.mkdir();two.mkdir()
        with patch('research_studio.resources.shutil.disk_usage') as usage:
            usage.return_value.free=resources.DISK_MARGIN_BYTES+300
            with resources.reserve(one,owner='first-project',temporary_bytes=200,memory_bytes=0,phase='disk'):
                with self.assertRaisesRegex(PMRSError,'RESOURCE_DISK_LOW'):
                    with resources.reserve(two,owner='second-project',temporary_bytes=200,memory_bytes=0,phase='disk'):pass
        self.assertEqual(resources.resource_status()['leases'],[])

    def test_distinct_filesystems_have_independent_disk_ledgers(self):
        if not Path('/dev/shm').is_dir():self.skipTest('No second local filesystem')
        with TemporaryDirectory(dir='/dev/shm') as directory:
            other=Path(directory)
            if self.root.stat().st_dev==other.stat().st_dev:self.skipTest('Only one actual filesystem')
            with patch('research_studio.resources.shutil.disk_usage') as usage:
                usage.return_value.free=resources.DISK_MARGIN_BYTES+300
                with resources.reserve(self.root,owner='disk-one',temporary_bytes=200,memory_bytes=0,phase='disk'):
                    with resources.reserve(other,owner='disk-two',temporary_bytes=200,memory_bytes=0,phase='disk'):
                        self.assertEqual(len({x['device'] for x in resources.resource_status()['leases']}),2)

    def test_memory_wait_does_not_install_limits_or_block_ten_small_clients(self):
        from contextlib import ExitStack
        ample={'total':16*1024*resources.MIB,'available':8*1024*resources.MIB,'margin':512*resources.MIB}
        with patch('research_studio.resources.memory_available',return_value=ample),ExitStack() as clients:
            for n in range(10):clients.enter_context(resources.reserve(self.root,owner='client-'+str(n),temporary_bytes=0,memory_bytes=resources.PHASE_MEMORY['client'],phase='client'))
            with resources.reserve(self.root,owner='prepare-1',temporary_bytes=0,memory_bytes=resources.MAX_PREPARATION_MEMORY):
                with resources.reserve(self.root,owner='prepare-2',temporary_bytes=0,memory_bytes=resources.MAX_PREPARATION_MEMORY):
                    self.assertEqual(len(resources.resource_status()['leases']),12)
            with patch('research_studio.resources.memory_available',return_value={**ample,'available':ample['margin']}):
                with self.assertRaisesRegex(PMRSError,'RESOURCE_WAIT'):
                    with resources.reserve(self.root,owner='wait',temporary_bytes=0,memory_bytes=1):pass

    def test_dead_physical_process_releases_memory_but_retained_disk_waits_for_cleanup(self):
        code="""from research_studio import resources
from pathlib import Path
import sys
root=Path(sys.argv[1])
with resources.reserve(root,owner='retained-evidence',temporary_bytes=100,memory_bytes=1) as lease:lease['retain']=True
"""
        result=subprocess.run([sys.executable,'-B','-c',code,str(self.root)],env=os.environ,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        rows=resources.resource_status()['leases'];self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['memory_bytes'],0);self.assertEqual(rows[0]['temporary_bytes'],100)
        resources.release_owner(self.root,'retained-evidence');self.assertEqual(resources.resource_status()['leases'],[])


if __name__=='__main__':unittest.main()
