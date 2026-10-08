"""Restricted TeX -> offline, namespace/secure-filter isolated PDF and all PNGs.

No network download, shell escape, sandbox weakening or compiler fallback. The
renderer never invokes a research model; a missing dependency remains an error.
"""
from pathlib import Path
import os,re,shutil,signal,stat,subprocess,tempfile,time
from .util import read,sha,identity,require,safe_path,PMRSError
from .restricted_tex import validate_tex,HOST_MATH_DEFINITIONS,tex_semantic_identity
from .pdf_filter import sealed_filter,compile_filter,DENIED
from .setup import configured_path

PREAMBLE=r'''\documentclass[11pt]{article}
\usepackage{fontspec,amsmath,amssymb,amsthm,mathrsfs,booktabs,longtable,array,calc,xcolor,hyperref,needspace}
\usepackage[a4paper,margin=2.2cm]{geometry}
\setmainfont{DejaVu Serif}
\setsansfont{DejaVu Sans}
\setmonofont{DejaVu Sans Mono}
\hypersetup{hidelinks}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.45em}
\setlength{\emergencystretch}{3em}
\clubpenalty=10000\widowpenalty=10000\displaywidowpenalty=10000
'''+HOST_MATH_DEFINITIONS+'\n\\begin{document}\n'
VERIFIER='''import os,sys
with open('/proc/self/status') as f:d=dict(x.strip().split(':',1) for x in f if ':' in x)
assert all(int(d[k],16)==0 for k in ('CapInh','CapPrm','CapEff','CapAmb'))
assert d['NoNewPrivs'].strip()=='1' and d['Seccomp'].strip()=='2'
for n in os.listdir('/proc/self/fd'):
 if int(n)>2:
  try:os.fstat(int(n))
  except OSError:continue
  raise RuntimeError('unexpected inherited descriptor')
os.execvpe(sys.argv[1],sys.argv[1:],os.environ)
'''
TOOLS=('tectonic','pdfinfo','pdftotext','pdftoppm','fc-match','bwrap')
SYSTEM_BIN=Path('/usr/bin')
CA_BUNDLES=('/etc/ssl/certs/ca-certificates.crt','/etc/pki/tls/certs/ca-bundle.crt','/etc/ssl/cert.pem')
SANDBOX_CA='/etc/ssl/certs/ca-certificates.crt'

def tool(name):
    p=os.environ.get('RS_'+name.upper().replace('-','_')+'_BINARY')
    # System tools and their libraries are already in the mounted /usr tree.
    # A PATH wrapper may refer to an unmounted runtime elsewhere in the home directory.
    if not p and name=='tectonic':p=configured_path('tectonic')
    if not p:
        system=SYSTEM_BIN/name
        p=system if system.is_file() and os.access(system,os.X_OK) else shutil.which(name)
    require(p and Path(p).is_file() and os.access(p,os.X_OK),'PDF_TOOL_MISSING',name)
    return str(Path(p).resolve())

def ca_bundle():
    selected=configured_path('ca_bundle')
    for name in ([selected] if selected else CA_BUNDLES):
        p=Path(name)
        if p.is_file():
            p=p.resolve()
            raw=read(p,4*1024**2)
            require(b'-----BEGIN CERTIFICATE-----' in raw and b'PRIVATE KEY' not in raw,'PDF_CA_BUNDLE_INVALID',str(p))
            return p
    raise PMRSError('PDF_CA_BUNDLE_MISSING','Install system ca-certificates; offline Tectonic still initializes its TLS client')

def cache_root():
    selected=configured_path('tectonic_cache')
    return Path(selected) if selected else Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'tectonic'

def check_mounts(bound,mountinfo):
    records=[];daemon=Path('/tmp')/('codex-daemon-'+str(os.geteuid()))
    def decode(s):return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),s)
    for line in mountinfo.splitlines():
        f=line.split();require(len(f)>9 and '-' in f,'PDF_MOUNT_INVALID','Malformed host mount table')
        records.append((decode(f[3]),Path(decode(f[4]))))
    for p in map(Path,bound):
        candidates=[(r,d) for r,d in records if p.is_relative_to(d)]
        require(candidates,'PDF_MOUNT_INVALID','No matching host mount')
        root,dest=max(candidates,key=lambda rd:len(rd[1].parts))
        require(root.startswith('/'),'PDF_MOUNT_INVALID','Relevant nonpath mount root')
        actual=Path(root)/p.relative_to(dest)
        require(not actual.is_relative_to(daemon),'PDF_DAEMON_ALIAS','A sandbox tool mount aliases a reserved socket directory')
        require(not any(d!=p and d.is_relative_to(p) for _,d in records),'PDF_NESTED_MOUNT','A permitted tree contains an extra mount')

def sandbox_command(work,command,fd):
    work=safe_path(work);require(work.is_dir() and stat.S_IMODE(work.stat().st_mode)==0o700 and work.stat().st_uid==os.geteuid(),
                                 'PDF_WORK_INVALID','Owned isolated mode-0700 scratch required')
    cmd=[tool('bwrap'),'--die-with-parent','--new-session','--unshare-user','--unshare-pid','--unshare-ipc','--unshare-net',
         '--cap-drop','ALL','--ro-bind','/usr','/usr','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/run']
    bound=['/usr',str(work)]
    for name in ('/bin','/sbin','/lib','/lib64'):
        p=Path(name)
        if p.is_symlink():
            require(str(p.resolve()).startswith('/usr/'),'PDF_SYSTEM_ALIAS','Unexpected system link')
            cmd+=['--symlink',os.readlink(p),name]
        elif p.is_dir():cmd+=['--ro-bind',name,name];bound.append(name)
    for name in ('/etc/fonts','/etc/ld.so.cache','/var/cache/fontconfig'):
        p=Path(name)
        if p.exists():require(not p.is_symlink(),'PDF_SYSTEM_ALIAS',name);cmd+=['--ro-bind',name,name];bound.append(name)
    # Only public trust anchors are needed, never all of /etc/ssl (which can contain keys).
    ca=ca_bundle();cmd+=['--ro-bind',str(ca),SANDBOX_CA];bound.append(str(ca))
    exe=Path(command[0]).resolve()
    require(exe.is_file(),'PDF_TOOL_MISSING',str(exe))
    if not str(exe).startswith('/usr/'):
        cmd+=['--ro-bind',str(exe),str(exe)];bound.append(str(exe))
    check_mounts(bound,Path('/proc/self/mountinfo').read_text())
    return cmd+['--bind',str(work),str(work),'--chdir',str(work),'--seccomp',str(fd),'--','/usr/bin/python3','-I','-S','-c',VERIFIER,*command]

def isolated(work,command,timeout=180):
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(work),'XDG_CACHE_HOME':str(work/'.cache'),'XDG_CONFIG_HOME':str(work/'.config'),
         'SSL_CERT_FILE':SANDBOX_CA}
    with sealed_filter() as fd:
        cmd=sandbox_command(work,command,fd)
        cmd=['/usr/bin/prlimit','--as=2147483648','--fsize=67108864','--cpu=240','--nofile=128','--core=0','--',*cmd]
        output=work/('tool-'+str(time.monotonic_ns())+'.log')
        with output.open('wb') as log:
            proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,cwd=work,
                                  close_fds=True,pass_fds=(fd,),start_new_session=True)
            try:proc.wait(timeout=timeout)
            except BaseException:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait();raise
        try:
            b=read(output,64*1024**2)
        finally:
            output.unlink(missing_ok=True)
        require(proc.returncode==0,'PDF_ISOLATED_TOOL_FAILED',b[-4000:].decode(errors='replace'))
        return b

def doctor():
    found={};missing=[]
    for name in TOOLS:
        try:found[name]=tool(name)
        except PMRSError:missing.append(name)
    try:ca=str(ca_bundle())
    except PMRSError:ca=None;missing.append('ca-certificates')
    return {'tools':found,'missing':missing,'ca_bundle':ca,'cache_present':cache_root().is_dir(),'production_render_test':'NOT_RUN',
            'model_calls':0,'network_downloads':0,'message_zh':'工具存在不等于已通过隔离编译；正式报告仍需实际编译与全页审查。'}

class Renderer:
    def resource_estimate(self):
        from .resources import PHASE_MEMORY
        _, files, total = self._cache_inventory()
        # Finite process-tree measurements stay below 400 MiB including eight
        # resident clients. Allow the bounded PDF/page/log buffers plus margin;
        # this estimate is not the subprocess virtual-address-space limit.
        return {'temporary_bytes':total + 256*1024**2, 'memory_bytes':PHASE_MEMORY['render'],
                'cache_bytes':total, 'cache_files':len(files)}

    def _cache_inventory(self):
        from .resources import file_info
        cache=safe_path(cache_root());require(cache.is_dir(),'PDF_CACHE_MISSING','Warm trusted offline TeX resources before running PMRS')
        files={};total=0
        for p in sorted(cache.rglob('*')):
            require(not p.is_symlink(),'PDF_CACHE_SYMLINK','Offline cache cannot contain symbolic links.')
            if p.is_file():
                size=file_info(p)['bytes'];total+=size
                require(total<=256*1024**2 and len(files)<8192,'PDF_CACHE_LIMIT','Offline cache exceeds its 256 MiB or 8192-file preparation budget.')
                files[str(p.relative_to(cache))]=(p,size)
        return cache,files,total

    def __call__(self,body,*,synthetic=False):
        from .resources import reserve
        estimate=self.resource_estimate()
        with reserve(Path(tempfile.gettempdir()),owner='render-'+sha(body),phase='render',
                     temporary_bytes=estimate['temporary_bytes'],memory_bytes=estimate['memory_bytes']):
            return self._render(body,synthetic=synthetic)

    def _render(self,body,*,synthetic=False):
        from .resources import hash_file, copy_file, disk_preflight
        text=validate_tex(body.decode());tex=(PREAMBLE+text+'\n\\end{document}\n').encode()
        bins={n:tool(n) for n in TOOLS};cache,files,total=self._cache_inventory()
        disk_preflight(Path(tempfile.gettempdir()),total+256*1024**2)
        with tempfile.TemporaryDirectory(prefix='pmrs-render-') as tmp:
            work=Path(tmp);cache_hashes={}
            for name,(source,size) in files.items():
                result=copy_file(source,work/'.cache/tectonic'/name,size)
                cache_hashes[name]=result['sha256']
            (work/'report.tex').write_bytes(tex)
            isolated(work,[bins['tectonic'],'--untrusted','--only-cached','--keep-logs','--outdir',str(work),str(work/'report.tex')],240)
            pdf=read(work/'report.pdf',64*1024**2);require(pdf.startswith(b'%PDF-'),'PDF_NOT_GENERATED','A valid PDF header is required')
            info=isolated(work,[bins['pdfinfo'],str(work/'report.pdf')]).decode()
            match=re.search(r'^Pages:\s*(\d+)',info,re.M);require(match and 0<int(match[1])<=120,'PDF_PAGE_COUNT','1-120 pages required')
            count=int(match[1]);extracted=isolated(work,[bins['pdftotext'],str(work/'report.pdf'),'-']).decode('utf-8')
            require(extracted.strip() and '\ufffd' not in extracted,'PDF_TEXT_INVALID','Missing or broken text')
            require(not re.search(r'[\u3400-\u9fff]',extracted),'PDF_LANGUAGE_MISMATCH','English reports cannot acquire Chinese host labels')
            compile_log=read(work/'report.log',64*1024**2).decode(errors='replace')
            require('Missing character:' not in compile_log,'PDF_MISSING_GLYPH','A rendered symbol is missing')
            pages=[]
            for i in range(1,count+1):
                isolated(work,[bins['pdftoppm'],'-png','-r','120','-f',str(i),'-l',str(i),'-singlefile',str(work/'report.pdf'),str(work/('page-'+str(i)))])
                pages.append(read(work/('page-'+str(i)+'.png'),16*1024**2))
                require(sum(map(len,pages))<=128*1024**2,'PDF_RENDER_LIMIT','All-page image total exceeds bound')
            fonts={}
            for family in ('DejaVu Serif','DejaVu Sans','DejaVu Sans Mono'):
                f=isolated(work,[bins['fc-match'],'--format=%{file}',family]).decode()
                require(f.startswith('/usr/'),'PDF_FONT_PATH','Only mounted system font files are allowed');fonts[family]=sha(read(Path(f)))
            sem={'grammar':tex_semantic_identity(),'template':sha(PREAMBLE.encode()),'compiler':hash_file(Path(bins['tectonic']),256*1024**2),
                 'cache':identity(cache_hashes)}
            env={'tools':{n:hash_file(Path(p),256*1024**2) for n,p in bins.items()},'fonts':fonts,
                 'ca_bundle':sha(read(ca_bundle(),4*1024**2)),
                 'seccomp':sha(compile_filter()),'verifier':sha(VERIFIER.encode()),'offline':True,'all_pages_rendered':True,
                 'namespace_isolated':True,'warnings':[l for l in compile_log.splitlines() if 'Overfull' in l or 'Warning:' in l]}
            return {'pdf':pdf,'tex':tex,'pages':pages,'semantic_environment':sem,'environment':env,'synthetic':False}
