#!/usr/bin/env python3
"""Clickable Ubuntu installer; privileged package installation requires a GUI action."""
from pathlib import Path
import importlib.util
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from research_studio.desktop import default_workspace
from research_studio.localization import load_preferences, translate


def current_locale():
    return load_preferences(default_workspace()).get('ui_locale', 'en')


def tr(key, **params):
    return translate(key, current_locale(), **params)


def dialog(*args):
    executable = shutil.which('zenity')
    if not executable: raise RuntimeError(tr('installer.zenity_required'))
    # Zenity text fields parse Pango markup; display paths/errors as literal text.
    safe_args = ['--text=' + html.escape(arg[7:]) if arg.startswith('--text=') else arg for arg in args]
    return subprocess.run([executable, '--title=' + tr('installer.title'), *safe_args], text=True, capture_output=True)


def missing_packages():
    packages = []
    for command, package in [('bwrap', 'bubblewrap'), ('pdfinfo', 'poppler-utils'), ('fc-match', 'fontconfig')]:
        if shutil.which(command) is None and package not in packages: packages.append(package)
    if not any(Path('/usr/lib').glob('*/libseccomp.so.2')): packages.append('libseccomp2')
    if not Path('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf').is_file(): packages.append('fonts-dejavu-core')
    if not Path('/etc/ssl/certs/ca-certificates.crt').is_file(): packages.append('ca-certificates')
    return packages


def install_system_packages(packages):
    """Called only after the visible user action; never invoked by dependency detection."""
    if not packages: return True
    if not shutil.which('pkexec'):
        dialog('--error', '--text=' + tr('installer.no_authorizer', packages='\n'.join(packages)))
        return False
    reply = dialog('--question', '--ok-label=' + tr('installer.install_components'), '--cancel-label=' + tr('installer.skip_components'),
        '--text=' + tr('installer.components_prompt', packages='\n'.join(packages)))
    if reply.returncode != 0: return False
    # No shell, arbitrary package names or user-supplied commands are accepted.
    allowed = {'bubblewrap', 'poppler-utils', 'fontconfig', 'fonts-dejavu-core', 'ca-certificates', 'libseccomp2'}
    if set(packages) - allowed: raise ValueError(tr('installer.unregistered_dependency'))
    with tempfile.TemporaryDirectory(prefix='pmrs-system-install-') as temporary:
        log_path = Path(temporary) / 'installation.log'
        with log_path.open('wb') as log:
            process = subprocess.Popen(['pkexec', '/usr/bin/apt-get', 'install', '--no-install-recommends', '-y', *packages], stdout=log, stderr=subprocess.STDOUT)
            progress = subprocess.Popen(['zenity', '--progress', '--pulsate', '--no-cancel', '--auto-close',
                '--title=' + tr('installer.components_title'), '--text=' + tr('installer.components_progress')], stdin=subprocess.PIPE, text=True)
            code = process.wait()
            if progress.stdin: progress.stdin.close()
            progress.wait()
        if code:
            dialog('--text-info', '--width=760', '--height=480', '--filename=' + str(log_path), '--title=' + tr('installer.components_failed'))
            return False
    return True


def main():
    if shutil.which('zenity') is None:
        webbrowser.open((ROOT / 'INSTALL-HELP.html').as_uri()); return 1
    try:
        spec = importlib.util.spec_from_file_location('pmrs_local_installer', ROOT / 'scripts/install-local.py')
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        manifest, _ = installer.verify_release(ROOT)
        choice = dialog('--file-selection', '--directory', '--filename=' + str(Path.home() / '.local/share') + '/',
                        '--title=' + tr('installer.choose_location', version=manifest['version']))
        if choice.returncode != 0: return 0
        base = Path(choice.stdout.strip()); target = base / 'Pure-Math-Research-Studio' / manifest['version']
        launcher_dir = target.parent / (manifest['version'] + '-launchers')
        app_dir = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'applications'
        question = dialog('--question', '--ok-label=' + tr('installer.install'), '--cancel-label=' + tr('installer.cancel'),
            '--text=' + tr('installer.confirm', version=manifest['version'], target=str(target)))
        if question.returncode != 0: return 0
        missing = missing_packages()
        if missing: install_system_packages(missing)
        # Use the same persisted dependency settings as the browser and runtime.
        # Choosing a file does not invoke it or begin any research.
        sys.path.insert(0, str(ROOT))
        from research_studio import setup
        current = setup.status()['resolved']
        for kind, label in [('codex', 'Codex CLI'), ('tectonic', tr('installer.tectonic_label')), ('tectonic_cache', tr('installer.cache_label'))]:
            if current.get(kind): continue
            question = dialog('--question', '--ok-label=' + tr('installer.choose_path'), '--cancel-label=' + tr('installer.configure_later'),
                '--text=' + tr('installer.missing_component', component=label))
            if question.returncode == 0: setup.select(kind, ui_locale=current_locale())
        result = installer.install(ROOT, target, launcher_dir, use_venv=True, desktop_dir=app_dir)
        answer = dialog('--question', '--ok-label=' + tr('installer.open_workspace'), '--cancel-label=' + tr('installer.finish'),
            '--text=' + tr('installer.complete', version=manifest['version']))
        if answer.returncode == 0:
            subprocess.Popen([result['desktop_launcher']], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    except Exception as exc:
        dialog('--error', '--width=660', '--text=' + tr('installer.failed', error=str(exc)))
        return 1


if __name__ == '__main__': raise SystemExit(main())
