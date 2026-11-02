# Build with the project-local build environment; only allowlisted assets ship.
from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH)
browser = root / '.tools/node_modules/agent-browser/bin/agent-browser-win32-x64.exe'
if not browser.is_file():
    browser = Path(os.environ.get('APPDATA', '')) / 'npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe'
if not browser.is_file():
    raise SystemExit('Build requires agent-browser 0.39.1 native Windows binary.')
psycopg_data, psycopg_binaries, psycopg_imports = collect_all('psycopg_binary')
analysis = Analysis(
    [str(root / 'desktop_launcher.py')], pathex=[str(root)],
    binaries=psycopg_binaries + [(str(browser), 'tools')],
    datas=psycopg_data + [(str(root / 'room_search/static'), 'room_search/static'),
                        (str(root / 'room_search/semesters.json'), 'room_search')],
    hiddenimports=psycopg_imports + collect_submodules('room_search', filter=lambda name: '.test' not in name),
    excludes=['unittest', 'pytest'], noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, analysis.binaries, analysis.datas, [],
    name='RoomSearch', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False)
