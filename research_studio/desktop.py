"""Desktop launcher: one background service per local workspace, reopenable UI."""
import argparse
import fcntl
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from .util import canonical,atomic,loads,read,safe_path
from .localization import translate,load_preferences
from . import __version__


def default_workspace():
    return Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'pure-math-research-studio/4.2.2/workspace'


def service(root,port=0):
    from .workspace import Workspace
    from .ui import app_handler
    root=safe_path(Path(root));runtime=root/'runtime';runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (runtime/'service.lock').open('a+b') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 0
        token=secrets.token_urlsafe(32)
        workspace=Workspace(root);workspace.recover_backend_state()
        server=ThreadingHTTPServer(('127.0.0.1',port),app_handler(workspace,token));server.daemon_threads=True
        record={'url':f'http://127.0.0.1:{server.server_port}','token':token,'pid':os.getpid()}
        atomic(runtime/'service.json',canonical(record));os.chmod(runtime/'service.json',0o600)
        workspace.start_maintenance()
        try:server.serve_forever(poll_interval=.2)
        finally:
            workspace.stop_maintenance();server.server_close();(runtime/'service.json').unlink(missing_ok=True)
    return 0


def running(root):
    try:
        r=loads(read(root/'runtime/service.json'))
        # Local metadata is not allowed to redirect the browser to another host.
        from urllib.parse import urlsplit
        u=urlsplit(r['url'])
        if u.scheme!='http' or u.hostname!='127.0.0.1' or not u.port:return None
        with urllib.request.urlopen(r['url'],timeout=2) as response:
            if response.status!=200:return None
        return r
    except (OSError,ValueError):return None


def launch(root,*,open_browser=True):
    root=safe_path(Path(root));root.mkdir(parents=True,exist_ok=True,mode=0o700)
    record=running(root)
    if not record:
        runtime=root/'runtime';runtime.mkdir(exist_ok=True,mode=0o700)
        with (runtime/'service.log').open('ab') as log:
            bootstrap='import sys;sys.path.insert(0,sys.argv[1]);from research_studio.desktop import main;raise SystemExit(main(sys.argv[2:]))'
            subprocess.Popen([sys.executable,'-c',bootstrap,str(Path(__file__).resolve().parent.parent),'--serve','--workspace',str(root)],
                             stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,close_fds=True)
        for _ in range(100):
            record=running(root)
            if record:break
            time.sleep(.1)
        if not record:raise RuntimeError(translate('native.launch_failed',load_preferences(root)['ui_locale']))
    url=record['url']+'/#session='+record['token']
    if open_browser:webbrowser.open(url,new=2)
    return {'url':url,'pid':record['pid']}


def main(argv=None):
    p=argparse.ArgumentParser(description=f'Open the local PMRS {__version__} workspace')
    p.add_argument('--workspace',type=Path,default=default_workspace());p.add_argument('--serve',action='store_true')
    p.add_argument('--port',type=int,default=0);p.add_argument('--no-browser',action='store_true');a=p.parse_args(argv)
    if a.serve:return service(a.workspace,a.port)
    launch(a.workspace,open_browser=not a.no_browser);return 0


if __name__=='__main__':raise SystemExit(main())
