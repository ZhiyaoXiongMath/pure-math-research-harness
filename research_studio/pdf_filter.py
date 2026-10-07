"""Linux seccomp floor for the native offline renderer (data, not legacy runtime)."""
import contextlib,errno,fcntl,hashlib,os,platform,struct,sys
from .util import require,PMRSError
DENIED=('ptrace','process_vm_readv','process_vm_writev','io_uring_setup','io_uring_enter','io_uring_register',
        'connect','accept','accept4','bind','listen','getpeername','getsockname','shutdown','sendto','sendmmsg',
        'recvmmsg','getsockopt','setsockopt')
NUMBERS={
 'x86_64':dict(zip(('socket','socketpair','connect','accept','sendto','shutdown','bind','listen','getsockname','getpeername','setsockopt','getsockopt','ptrace','accept4','recvmmsg','sendmmsg','process_vm_readv','process_vm_writev','io_uring_setup','io_uring_enter','io_uring_register'),(41,53,42,43,44,48,49,50,51,52,54,55,101,288,299,307,310,311,425,426,427))),
 'aarch64':dict(zip(('ptrace','socket','socketpair','bind','listen','accept','connect','getsockname','getpeername','sendto','setsockopt','getsockopt','shutdown','accept4','recvmmsg','sendmmsg','process_vm_readv','process_vm_writev','io_uring_setup','io_uring_enter','io_uring_register'),(117,198,199,200,201,202,203,204,205,206,208,209,210,242,243,269,270,271,425,426,427)))}
ARCH={'x86_64':0xC000003E,'aarch64':0xC00000B7}
ALLOW=0x7FFF0000;KILL=0x80000000;DENY=0x00050000|errno.EPERM

def compile_filter(arch=None):
    arch=arch or platform.machine();require(arch in ARCH and sys.byteorder=='little','PDF_ARCH_UNSUPPORTED',arch)
    ins=[(0x20,0,0,4),(0x15,1,0,ARCH[arch]),(6,0,0,KILL),(0x20,0,0,0)]
    if arch=='x86_64':ins.extend([(0x45,0,1,0x40000000),(6,0,0,KILL)])
    for name in sorted(DENIED):ins.extend([(0x15,0,1,NUMBERS[arch][name]),(6,0,0,DENY)])
    for name in ('socket','socketpair'):
        ins.extend([(0x15,0,4,NUMBERS[arch][name]),(0x20,0,0,16),(0x15,1,0,1),(6,0,0,DENY),(6,0,0,ALLOW)])
    ins.append((6,0,0,ALLOW));return b''.join(struct.pack('<HBBI',*x) for x in ins)

@contextlib.contextmanager
def sealed_filter():
    fd=-1
    try:
        fd=os.memfd_create('pmrs-pdf-seccomp',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
        require(fd>=3,'PDF_FILTER_FD','Separate descriptor required');os.write(fd,compile_filter())
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL)
        os.lseek(fd,0,0);yield fd
    except (AttributeError,OSError) as exc:raise PMRSError('PDF_FILTER_UNAVAILABLE',str(exc)) from exc
    finally:
        if fd>=0:os.close(fd)
