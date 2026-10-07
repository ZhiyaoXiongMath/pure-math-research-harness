"""Bounded, read-only input inventory. No imported Python, SQL or shell is executed."""
from pathlib import Path, PurePosixPath
import stat
import unicodedata
import zipfile
from .util import require, read, sha, identity, safe_path

MAX_FILES=100000
MAX_FILE=256*1024*1024
MAX_TOTAL=1024*1024*1024

def path_ok(name):
    p=PurePosixPath(name)
    require(name and not p.is_absolute() and '..' not in p.parts and '\\' not in name
            and str(p)==name and '\x00' not in name,'IMPORT_PATH_INVALID',name)
    return unicodedata.normalize('NFC',name).casefold()

def inventory(source):
    raw_input=source if isinstance(source,bytes) else None
    source=None if raw_input is not None else safe_path(Path(source));data={};seen=set();total=0
    def add(name,b):
        nonlocal total
        folded=path_ok(name)
        require(folded not in seen,'IMPORT_PATH_COLLISION',name)
        total+=len(b)
        require(len(data)<MAX_FILES and len(b)<=MAX_FILE and total<=MAX_TOTAL,'IMPORT_LIMIT','Bounded importer capacity exceeded; no partial package is produced')
        seen.add(folded);data[name]=b
    if source is not None and source.is_dir():
        before={}
        members=sorted(source.rglob('*'))
        member_names={p.relative_to(source).as_posix() for p in members}
        for p in members:
            require(not p.is_symlink(),'IMPORT_SYMLINK',str(p))
            if p.is_dir():continue
            name=p.relative_to(source).as_posix();b=read(p,MAX_FILE);add(name,b)
            st=p.stat();before[name]=(st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        after_members=sorted(source.rglob('*'))
        require({p.relative_to(source).as_posix() for p in after_members}==member_names,
                'SOURCE_MEMBER_SET_CHANGED','Directory members changed while reading')
        require(all(not p.is_symlink() for p in after_members),'IMPORT_SYMLINK','Directory changed to a symbolic link')
        for name,stamp in before.items():
            p=safe_path(source,name)
            require(p.exists(),'SOURCE_MEMBER_SET_CHANGED',name)
            st=p.stat()
            require((st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)==stamp and sha(read(p,MAX_FILE))==sha(data[name]),
                    'IMPORT_SOURCE_CHANGED',name)
        origin={'kind':'DIRECTORY','path':str(source),'byte_inventory_sha256':identity({k:sha(v) for k,v in data.items()})}
    else:
        raw=raw_input if raw_input is not None else read(source,MAX_TOTAL)
        require(len(raw)<=MAX_TOTAL,'IMPORT_LIMIT','Archive capacity exceeded')
        origin={'kind':'ZIP','name':source.name if source is not None else None,'archive_sha256':sha(raw),'bytes':len(raw)}
        import io
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            require(len(z.infolist())<=MAX_FILES,'IMPORT_LIMIT','Too many archive members')
            require(sum(e.file_size for e in z.infolist())<=MAX_TOTAL,'IMPORT_LIMIT','Expanded archive too large')
            for e in z.infolist():
                if e.is_dir():path_ok(e.filename.rstrip('/'));continue
                mode=e.external_attr>>16
                require(stat.S_IFMT(mode) in (0,stat.S_IFREG) and not e.flag_bits&1,'IMPORT_MEMBER_INVALID',e.filename)
                require(e.file_size<=MAX_FILE and e.file_size/max(1,e.compress_size)<=1000,'IMPORT_LIMIT','Suspicious expansion or member size')
                add(e.filename,z.read(e))
    # Strip exactly one common archive root, never guess a nested authoritative root.
    first={n.split('/')[0] for n in data}
    if origin['kind']=='ZIP' and len(first)==1 and all('/' in n for n in data):
        prefix=next(iter(first))+'/';data={n[len(prefix):]:b for n,b in data.items()};origin['stripped_prefix']=prefix
    return data,origin

def bound(data,path,expected=None):
    path_ok(path);require(path in data,'IMPORT_FILE_MISSING',path)
    value=data[path];require(expected is None or sha(value)==expected,'IMPORT_HASH_MISMATCH',path)
    return value
