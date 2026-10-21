# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""윈도우 — 휴지통 `X:\\$Recycle.Bin\\<SID>\\` 의 `$I<id>`(메타)+`$R<id>`(본체) 짝 추적 (2026-10-19 윈도우 실측).

삭제 전후 `$I` 목록 차이로 항목을 잡고, 되돌리기 = `$R` 을 원래 경로로 + `$I` 삭제.
"""
import logging
import os
import shutil
from pathlib import Path

try:
    from send2trash import send2trash
except ImportError:          # 없으면 app 이 삭제를 막는다(영구 삭제 방지)
    send2trash = None

from ._common import no_op, sanitize_isdir

APP_MENU = False               # 설정…·정보를 앱 메뉴로 (맥 관례) / 아니면 「파일」 메뉴
CMD_BACKSPACE_DELETE = False

before_qapp = no_op
after_qapp = no_op
install_key_monitor = no_op


def setup_logging(logger: logging.Logger):
    logger.addHandler(logging.NullHandler())


def sanitize_path(path, allow_home: bool = True) -> str:
    return sanitize_isdir(path, allow_home)


def confirm_delete(parent, paths) -> bool:
    return True


def _recycle_info_files(path: str) -> set:
    """path 가 있는 드라이브의 휴지통 `$I*` 파일 집합 (읽을 수 있는 SID 폴더만)."""
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    base = Path(drive + os.sep) / "$Recycle.Bin"
    found = set()
    try:
        for sid_dir in base.iterdir():
            try:
                for f in sid_dir.iterdir():
                    if f.name.startswith("$I"):
                        found.add(str(f))
            except OSError:
                continue
    except OSError:
        pass
    return found


def trash(path: str) -> str:
    # Qt 경로는 `C:/a/b` 슬래시인데 send2trash 윈도우 백엔드는 `\\?\` 접두에 백슬래시만 받는다
    # → FileNotFoundError. normpath 로 OS 구분자에 맞춘다 (2026-10-19 실측)
    path = os.path.normpath(path)
    before = _recycle_info_files(path)
    send2trash(path)
    new = _recycle_info_files(path) - before
    return str(next(iter(new))) if len(new) == 1 else ""


def restore(token: str, dst: str):
    info = Path(token)
    body = info.with_name("$R" + info.name[2:])
    if not body.exists():
        raise FileNotFoundError(f"휴지통 본체 없음: {body}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(str(body), dst)
    try:
        info.unlink()
    except OSError:
        pass
