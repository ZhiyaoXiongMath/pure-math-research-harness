#!/usr/bin/env python3
"""Clickable Ubuntu installer; privileged package installation requires a GUI action."""
from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def dialog(*args):
    executable = shutil.which('zenity')
    if not executable: raise RuntimeError('The graphical installer requires Zenity')
    return subprocess.run([executable, '--title=PMRS 安装', *args], text=True, capture_output=True)


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
        dialog('--error', '--text=未找到系统图形授权服务。请从软件中心安装列出的组件，然后重新运行安装器。\n' + '\n'.join(packages))
        return False
    reply = dialog('--question', '--ok-label=安装这些组件', '--cancel-label=暂不安装',
        '--text=报告功能需要以下 Ubuntu 系统组件。点击安装后，系统会请求管理员授权。应用本身将安装在你的个人目录。\n\n' + '\n'.join(packages))
    if reply.returncode != 0: return False
    # No shell, arbitrary package names or user-supplied commands are accepted.
    allowed = {'bubblewrap', 'poppler-utils', 'fontconfig', 'fonts-dejavu-core', 'ca-certificates', 'libseccomp2'}
    if set(packages) - allowed: raise ValueError('Unregistered system dependency')
    with tempfile.TemporaryDirectory(prefix='pmrs-system-install-') as temporary:
        log_path = Path(temporary) / 'installation.log'
        with log_path.open('wb') as log:
            process = subprocess.Popen(['pkexec', '/usr/bin/apt-get', 'install', '--no-install-recommends', '-y', *packages], stdout=log, stderr=subprocess.STDOUT)
            progress = subprocess.Popen(['zenity', '--progress', '--pulsate', '--no-cancel', '--auto-close',
                '--title=安装报告组件', '--text=系统正在安装所选组件；完成前请保留授权窗口。'], stdin=subprocess.PIPE, text=True)
            code = process.wait()
            if progress.stdin: progress.stdin.close()
            progress.wait()
        if code:
            dialog('--text-info', '--width=760', '--height=480', '--filename=' + str(log_path), '--title=系统组件安装未完成')
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
                        '--title=选择 PMRS 4.0.0 安装位置')
        if choice.returncode != 0: return 0
        base = Path(choice.stdout.strip()); target = base / 'Pure-Math-Research-Studio' / manifest['version']
        launcher_dir = target.parent / (manifest['version'] + '-launchers')
        app_dir = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'applications'
        question = dialog('--question', '--ok-label=安装', '--cancel-label=取消',
            '--text=将安装 PMRS ' + manifest['version'] + ' 到：\n' + str(target) + '\n\n应用菜单将新增“纯数学研究工作室 4.0.0”。安装不会启动付费模型研究，也不会改动已有项目。')
        if question.returncode != 0: return 0
        missing = missing_packages()
        if missing: install_system_packages(missing)
        # Use the same persisted dependency settings as the browser and runtime.
        # Choosing a file does not invoke it or begin any research.
        sys.path.insert(0, str(ROOT))
        from research_studio import setup
        current = setup.status()['resolved']
        for kind, label in [('codex', 'Codex CLI'), ('tectonic', 'Tectonic 报告编译器'), ('tectonic_cache', 'Tectonic 离线资源目录')]:
            if current.get(kind): continue
            question = dialog('--question', '--ok-label=选择已有本地路径', '--cancel-label=稍后在网页设置',
                '--text=尚未找到 ' + label + '。可现在选择已有文件或目录，也可稍后在网页“设置”中选择路径或点击安装官方组件。\n\n缺少报告组件不会阻止无 PDF 的研究；缺少 CLI 时仍可浏览工作区。')
            if question.returncode == 0: setup.select(kind)
        result = installer.install(ROOT, target, launcher_dir, use_venv=True, desktop_dir=app_dir)
        answer = dialog('--question', '--ok-label=打开研究工作区', '--cancel-label=完成',
            '--text=PMRS 已安装。可从应用菜单打开“纯数学研究工作室 4.0.0”。首次配置会检查模型登录和报告依赖；不会自动开始研究。')
        if answer.returncode == 0:
            subprocess.Popen([result['desktop_launcher']], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    except Exception as exc:
        dialog('--error', '--width=660', '--text=安装未完成：\n' + str(exc) + '\n\n已有研究项目保持不变。可重新选择一个空安装目录后重试。')
        return 1


if __name__ == '__main__': raise SystemExit(main())
