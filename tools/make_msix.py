# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""PyInstaller 결과 폴더 → 마이크로소프트 스토어 제출용 MSIX (서명 없음 — 스토어가 서명한다).

    python tools/make_msix.py dist/ImageManager ImageManager-store.msix [--root .] [--version 0.6.5] [--no-pack]

- 제품 ID 3값은 파트너 센터 「제품 관리 → 제품 ID」 그대로 (2026-10-24 예약: UDev ImageManager)
- 스토어는 버전 네 번째 자리가 0 이어야 받는다 → APP_VERSION 0.6.5 = 0.6.5.0
- --root = 버전·아이콘을 읽을 소스 폴더 (CI 는 스크립트를 따로 받아 빌드한 태그 폴더를 넘긴다)
- makeappx 는 윈도우 SDK 에 있다(깃허브 windows-latest 러너에 설치돼 있음). --no-pack 이면 작업 폴더만 만든다
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

IDENTITY_NAME = "UDevApp.UDevImageManager"
PUBLISHER = "CN=DBFCF296-058F-44DE-984B-D43C3BCADADB"
PUBLISHER_DISPLAY = "UDevApp"
DISPLAY_NAME = "UDev ImageManager"          # 파트너 센터에 예약한 이름과 같아야 제출이 통과한다
DESCRIPTION = "키보드로 사진을 넘겨 보며 여러 폴더로 분류하는 듀얼 패널 이미지 관리자"

# 이름 → 정사각 크기 (Wide 는 별도). targetsize-*_altform-unplated = 작업 표시줄·시작 메뉴에서 배경판 없이 쓰는 아이콘
ASSETS = {
    "StoreLogo.png": 50,
    "Square44x44Logo.png": 44,
    "Square150x150Logo.png": 150,
    "Square44x44Logo.targetsize-16_altform-unplated.png": 16,
    "Square44x44Logo.targetsize-24_altform-unplated.png": 24,
    "Square44x44Logo.targetsize-32_altform-unplated.png": 32,
    "Square44x44Logo.targetsize-48_altform-unplated.png": 48,
    "Square44x44Logo.targetsize-256_altform-unplated.png": 256,
}

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap rescap">
  <Identity Name="{name}" Publisher="{publisher}" Version="{version}" ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>{display}</DisplayName>
    <PublisherDisplayName>{publisher_display}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.22621.0" />
  </Dependencies>
  <Resources>
    <Resource Language="ko-KR" />
  </Resources>
  <Applications>
    <Application Id="ImageManager" Executable="ImageManager.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="{display}" Description="{description}"
                          BackgroundColor="transparent"
                          Square150x150Logo="Assets\\Square150x150Logo.png"
                          Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" />
      </uap:VisualElements>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def app_version() -> str:
    src = open(os.path.join(ROOT, "imagemanager", "app.py"), encoding="utf-8").read()
    return re.search(r'APP_VERSION = "([^"]+)"', src).group(1)


def msix_version(v: str) -> str:
    parts = [int(p) for p in v.split(".")][:3]
    parts += [0] * (3 - len(parts))
    return ".".join(map(str, parts)) + ".0"


def make_assets(out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    src = Image.open(os.path.join(ROOT, "imagemanager", "icons", "icon_1024.png")).convert("RGBA")
    for name, size in ASSETS.items():
        src.resize((size, size), Image.LANCZOS).save(os.path.join(out_dir, name))
    wide = Image.new("RGBA", (310, 150), (0, 0, 0, 0))
    wide.paste(src.resize((120, 120), Image.LANCZOS), (95, 15))
    wide.save(os.path.join(out_dir, "Wide310x150Logo.png"))


def find_makeappx() -> str:
    found = shutil.which("makeappx")
    if found:
        return found
    hits = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\makeappx.exe"))
    if not hits:
        sys.exit("makeappx.exe 를 찾지 못했습니다 (윈도우 SDK 필요)")
    return hits[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dist", help="PyInstaller 결과 폴더 (ImageManager.exe 가 있는 곳)")
    ap.add_argument("out", help="만들 .msix 경로")
    ap.add_argument("--root", default=None, help="기본 = 이 스크립트의 상위 폴더")
    ap.add_argument("--version", default=None, help="기본 = imagemanager/app.py 의 APP_VERSION")
    ap.add_argument("--no-pack", action="store_true", help="작업 폴더만 만들고 makeappx 는 건너뜀")
    args = ap.parse_args()
    global ROOT
    if args.root:
        ROOT = os.path.abspath(args.root)

    if not os.path.isfile(os.path.join(args.dist, "ImageManager.exe")) and not args.no_pack:
        sys.exit(f"{args.dist} 에 ImageManager.exe 가 없습니다")
    stage = os.path.abspath(args.out) + ".stage"
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    shutil.copytree(args.dist, stage)
    make_assets(os.path.join(stage, "Assets"))
    version = msix_version(args.version or app_version())
    with open(os.path.join(stage, "AppxManifest.xml"), "w", encoding="utf-8") as f:
        f.write(MANIFEST.format(name=IDENTITY_NAME, publisher=PUBLISHER, version=version,
                                display=escape(DISPLAY_NAME), publisher_display=escape(PUBLISHER_DISPLAY),
                                description=escape(DESCRIPTION)))
    print(f"MSIX 작업 폴더: {stage} (버전 {version})")
    if args.no_pack:
        return
    subprocess.run([find_makeappx(), "pack", "/d", stage, "/p", args.out, "/o"], check=True)
    print(f"완성: {args.out}")


if __name__ == "__main__":
    main()
