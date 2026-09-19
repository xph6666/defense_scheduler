# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


block_cipher = None

project_modules = [
    module
    for module in collect_submodules('api') + collect_submodules('defense_scheduler')
    if not module.rsplit('.', 1)[-1].startswith('test')
]

hiddenimports = project_modules + [
    'algorithm',
    'waitress',
    'corsheaders',
    'django.contrib.auth.backends',
    'django.contrib.messages.storage.fallback',
    'django.contrib.sessions.backends.db',
    'django.db.backends.sqlite3',
    'docx',
    'openpyxl',
    'openpyxl.cell.rich_text',
    'rest_framework.authtoken',
    'xlrd',
]

excludes = [
    'IPython',
    'bpython',
    'jupyter',
    'llvmlite',
    'matplotlib',
    'numba',
    'pytest',
    '_pytest',
    'scipy',
    'selenium',
    'sqlalchemy',
    'sympy',
    'tensorflow',
    'torch',
    'torchaudio',
    'torchvision',
]

def collect_frontend_dist():
    dist_root = Path('dist').resolve()
    if not dist_root.is_dir():
        raise SystemExit('Frontend build not found. Run npm run build before PyInstaller.')

    return [
        (str(path), str(Path('dist') / path.relative_to(dist_root).parent))
        for path in dist_root.rglob('*')
        if path.is_file()
    ]


datas = collect_frontend_dist()
datas += collect_data_files('django', include_py_files=False)
datas += collect_data_files('rest_framework', include_py_files=False)
# python-docx 依赖包内默认模板（default.docx 等部件），需随包收集
datas += collect_data_files('docx', include_py_files=False)

a = Analysis(
    ['defense_scheduler/desktop_entry.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DefenseScheduler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
