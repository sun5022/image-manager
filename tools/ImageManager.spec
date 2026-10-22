# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0
# Windows · Linux 실행 파일 빌드 (깃허브 Actions 에서 실행). 맥은 mac/ImageManager.spec + mac/build.sh (고정 서명)
#   pyinstaller --noconfirm tools/ImageManager.spec      (레포 루트에서)
import os, re, sys
ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
APP_VERSION = re.search(r'APP_VERSION = "([^"]+)"', open(os.path.join(ROOT, 'imagemanager', 'app.py'), encoding='utf-8').read()).group(1)
IS_WIN = sys.platform == 'win32'

a = Analysis(
    [os.path.join(ROOT, 'image_manager.py')],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, 'imagemanager', 'icons'), 'icons'),      # 앱 아이콘 (_MEIPASS/icons)
           (os.path.join(ROOT, 'images', 'keymap.png'), 'images'),      # F1 배치도
           (os.path.join(ROOT, 'LICENSE'), '.'), (os.path.join(ROOT, 'NOTICE'), '.')],
    hiddenimports=['send2trash', 'py7zr', 'rarfile',
                   'imagemanager.platforms.windows', 'imagemanager.platforms.linux'],   # platforms.current() 가 동적 import
    excludes=['imagemanager.platforms.mac', 'AppKit', 'Foundation'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='ImageManager',
    console=False,                     # 검은 터미널 창 없이
    icon=os.path.join(ROOT, 'imagemanager', 'icons', 'icon_256.png') if IS_WIN else None,   # Pillow 가 .ico 로 변환
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name='ImageManager')
