#!/usr/bin/env python3
"""Verify a ZIP, preserve safe file modes, and register its graphical installer.

Advanced delivery preparation; ordinary users may open the generated .deb in
Ubuntu's graphical package installer instead.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--desktop-dir', type=Path, default=Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'applications')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('pmrs_prepare_installer', Path(__file__).with_name('install-local.py'))
    installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
    release = installer.extract_release(args.archive, args.out)
    desktop = installer.register_installer(release, args.desktop_dir)
    print(json.dumps({'release': str(release), 'installer_menu_entry': str(desktop), 'mode_preserved': True,
                      'native_menu_click': 'NOT_RUN', 'model_calls': 0}, ensure_ascii=False))


if __name__ == '__main__': main()
