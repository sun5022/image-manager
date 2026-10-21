# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""리눅스 — XDG 휴지통(`~/.local/share/Trash/{info,files}`), 삭제 확인 창 없음, 로그 없음."""
import logging
import os
import shutil
from pathlib import Path

try:
    from send2trash import send2trash
except ImportError:          # 없으면 app 이 삭제를 막는다(영구 삭제 방지)
    send2trash = None

from ._common import no_op, sanitize_isdir

TRASH_INFO_DIR = Path.home() / ".local/share/Trash/info"
TRASH_FILES_DIR = Path.home() / ".local/share/Trash/files"
APP_MENU = False               # 설정…·정보를 앱 메뉴로 (맥 관례) / 아니면 「파일」 메뉴
CMD_BACKSPACE_DELETE = False

before_qapp = no_op
after_qapp = no_op
install_key_monitor = no_op       # 리눅스는 한글 입력 상태에서도 Qt 가 영문 키를 받는다


def setup_logging(logger: logging.Logger):
    logger.addHandler(logging.NullHandler())


def sanitize_path(path, allow_home: bool = True) -> str:
    return sanitize_isdir(path, allow_home)


def confirm_delete(parent, paths) -> bool:
    return True                   # 팝업 없음 — 되돌리기로 복원


def _snapshot() -> set:
    if not TRASH_INFO_DIR.exists():
        return set()
    return set(TRASH_INFO_DIR.glob("*.trashinfo"))


def trash(path: str) -> str:
    """휴지통으로 보내고, 새로 생긴 .trashinfo 경로를 표식으로 돌려준다(못 찾으면 "")."""
    before = _snapshot()
    send2trash(path)
    new = _snapshot() - before
    return str(next(iter(new))) if len(new) == 1 else ""


def restore(token: str, dst: str):
    info = Path(token)
    body = TRASH_FILES_DIR / info.name[: -len(".trashinfo")]
    if not body.exists():
        raise FileNotFoundError(f"휴지통 본체 없음: {body}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(str(body), dst)
    try:
        info.unlink()
    except OSError:
        pass
