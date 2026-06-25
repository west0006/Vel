# -*- mode: python ; coding: utf-8 -*-
"""
Vel 桌面宠物 PyInstaller 打包配置。
"""

import os

PROJECT_ROOT = SPECPATH

a = Analysis(
    ['main.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        ('config/settings.yaml', 'config'),
        ('config/secrets.yaml', 'config'),
        ('config/easter_eggs.yaml', 'config'),
        ('data/db/schema.sql', 'data/db'),
        ('ui/resources/styles.qss', 'ui/resources'),
        ('ui/resources/icons', 'ui/resources/icons'),
        ('ui/resources/animations/pet_svg', 'ui/resources/animations/pet_svg'),
    ],
    hiddenimports=[
        'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.QtSvg', 'PyQt5.sip',
        'apscheduler.schedulers.qt', 'apscheduler.triggers.cron',
        'apscheduler.triggers.interval', 'apscheduler.triggers.date',
        'cryptography', 'cryptography.hazmat.primitives.ciphers.aead',
        'numpy', 'dateparser', 'yaml', 'faiss', 'faiss.swigfaiss',
        'duckduckgo_search', 'requests',
        'json', 'logging', 'threading', 'sqlite3', 'hashlib',
        'uuid', 'pathlib', 'secrets', 'base64', 're', 'random', 'ctypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pandas', 'scipy', 'torch', 'tensorflow'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='Vel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False, upx=True, upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None, entitlements_file=None,
    icon= None,
)