# -*- mode: python ; coding: utf-8 -*-
import re
# 버전 정본 = imagemanager/app.py 의 APP_VERSION
APP_VERSION = re.search(r'APP_VERSION = "([^"]+)"', open('../imagemanager/app.py', encoding='utf-8').read()).group(1)


a = Analysis(
    ['image_manager.py'],
    pathex=['..'],                 # imagemanager 패키지
    binaries=[],
    datas=[('../imagemanager/icons', 'icons'),          # 앱 아이콘 (load_app_icon 이 _MEIPASS/icons 에서 찾음)
           ('../images/keymap.png', 'images')],       # F1 배치도
    hiddenimports=['send2trash', 'Foundation', 'AppKit', 'py7zr', 'rarfile',
                   'imagemanager.platforms.mac'],   # platforms.current() 가 동적 import
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ImageManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ImageManager',
)
app = BUNDLE(
    coll,
    name='ImageManager.app',
    icon='ImageManager.icns',
    bundle_identifier='com.udevapp.ImageManager',
    info_plist={
        'CFBundleName': 'ImageManager',
        'CFBundleDisplayName': 'ImageManager',
        'CFBundleShortVersionString': APP_VERSION,
        'NSHighResolutionCapable': True,
        'NSHumanReadableCopyright': 'Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) · Apache License 2.0',
    },
)
