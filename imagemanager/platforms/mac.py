# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""맥 — `~/.Trash` 추적, 삭제 전 미리보기 확인 창, `~/Library/Logs` 로그, 메뉴 막대·Dock 이름과 아이콘,
한글 입력 상태 단축키(NSEvent 네이티브 키 모니터). 함정 정리 = `/qtapp` 스킬 2장."""
import logging
import os
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout

try:
    from send2trash import send2trash
except ImportError:          # 없으면 app 이 삭제를 막는다(영구 삭제 방지)
    send2trash = None

TRASH_DIR = Path.home() / ".Trash"
LOG_FILE = Path.home() / "Library" / "Logs" / "ImageManager.log"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".ico"}
APP_MENU = True               # 설정…·정보를 앱 메뉴로 (맥 관례) / 아니면 「파일」 메뉴
CMD_BACKSPACE_DELETE = True        # Cmd+Backspace = 휴지통 (맥 표준)
logger = logging.getLogger("ImageManager")


def setup_logging(lg: logging.Logger):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    lg.info("=" * 40)
    lg.info("ImageManager start")


def before_qapp(app_name: str):
    """메뉴 막대 앱 이름 — venv 파이썬으로 바로 실행하면 Python.app 의 CFBundleName(「Python」)이 쓰인다.
    NSApplication 이 만들어지기 전에 번들 정보를 덮어써야 반영된다. (Dock 마우스오버 이름은 .app 빌드로만)"""
    try:
        from Foundation import NSBundle, NSProcessInfo
        info = NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = app_name
            info["CFBundleDisplayName"] = app_name
        NSProcessInfo.processInfo().setProcessName_(app_name)
    except Exception:
        pass


def after_qapp(app, icon):
    """Dock 아이콘 — PyInstaller 빌드에서도 런타임에 설정."""
    try:
        from AppKit import NSApplication, NSImage
        from PySide6.QtCore import QBuffer, QIODevice
        pix = icon.pixmap(512, 512)
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        pix.save(buf, "PNG")
        ns_img = NSImage.alloc().initWithData_(buf.data())
        if ns_img is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(ns_img)
    except Exception:
        pass


def sanitize_path(path, allow_home: bool = True) -> str:
        """저장된 경로가 stale 이면 $HOME fallback (또는 빈 문자열).

        - macOS 시스템 루트 (/, /Users, /System, /Library) — QFileSystemModel 이
          빈 화면 보이는 경우 잦아 사용자 홈으로 자동 회복
        - /Volumes/<name>/... — 마운트 안 되어 있으면 fallback (네트워크 끊김 회피)
        - 존재 안 하는 경로 — fallback
        """
        home = str(Path.home())
        if not path:
            return home if allow_home else ""
        path = str(path)
        if path in ("/", "/Users", "/System", "/Library"):
            return home if allow_home else ""
        if path.startswith("/Volumes/"):
            parts = path.split("/", 3)
            if len(parts) >= 3:
                mount_root = "/" + parts[1] + "/" + parts[2]
                if not os.path.ismount(mount_root):
                    return home if allow_home else ""
        if not os.path.isdir(path):
            return home if allow_home else ""
        return path


# ---------------------------------------------------------------------------
# 삭제 확인 — 미리보기 + 파일명 + 휴지통/취소 (파일명만으로 판단 어려운 경우가 많다)
# ---------------------------------------------------------------------------
class DeleteConfirmDialog(QDialog):
    """삭제 확인 다이얼로그. 파일명이 이상한 경우 많아 미리보기로 실수 방지."""

    THUMB_MAX = 360

    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("휴지통으로 이동")
        self.setMinimumWidth(420)
        self.resize(440, 540)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        first = paths[0]
        ext = os.path.splitext(first)[1].lower()
        thumb_loaded = False
        if ext in IMAGE_EXTS and os.path.isfile(first):
            pix = QPixmap(first)
            if not pix.isNull():
                pix = pix.scaled(
                    self.THUMB_MAX, self.THUMB_MAX,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                img_lbl = QLabel()
                img_lbl.setPixmap(pix)
                img_lbl.setAlignment(Qt.AlignCenter)
                img_lbl.setStyleSheet(
                    "background: #1e1e1e; border: 1px solid #444; padding: 4px;"
                )
                layout.addWidget(img_lbl)
                thumb_loaded = True
        if not thumb_loaded:
            placeholder = QLabel("(미리보기 없음 — 이미지 파일 아님)")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setFixedHeight(60)
            placeholder.setStyleSheet(
                "color: #888; background: #2a2a2a; border: 1px solid #444;"
            )
            layout.addWidget(placeholder)

        if len(paths) == 1:
            name_lbl = QLabel(f"<b>{os.path.basename(first)}</b>")
        else:
            name_lbl = QLabel(
                f"<b>{len(paths)} 개 항목</b> "
                f"<span style='color:#888'>(첫 항목: {os.path.basename(first)})</span>"
            )
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl)

        path_lbl = QLabel(os.path.dirname(first))
        path_lbl.setStyleSheet("color: #888; font-size: 10pt;")
        path_lbl.setAlignment(Qt.AlignCenter)
        path_lbl.setWordWrap(True)
        layout.addWidget(path_lbl)

        msg_lbl = QLabel(
            "이 파일을 휴지통으로 이동하시겠습니까?"
            if len(paths) == 1
            else "선택한 항목들을 휴지통으로 이동하시겠습니까?"
        )
        msg_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg_lbl)

        btn_box = QDialogButtonBox()
        self.trash_btn = btn_box.addButton(
            "휴지통으로", QDialogButtonBox.AcceptRole
        )
        self.cancel_btn = btn_box.addButton(
            "취소", QDialogButtonBox.RejectRole
        )
        # macOS PyInstaller 빌드에서 QDialogButtonBox.accepted/rejected 시그널이
        # role 기반 매핑으로 button click 까지 도달 안 하는 사례 → 버튼에 직접 연결.
        self.trash_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.trash_btn.setDefault(True)
        self.trash_btn.setAutoDefault(True)
        layout.addWidget(btn_box)


def confirm_delete(parent, paths) -> bool:
    dlg = DeleteConfirmDialog(paths, parent=parent)
    rv = dlg.exec()
    logger.info(f"  삭제 확인 창 = {rv}")
    return rv == QDialog.Accepted


def _snapshot() -> set:
    if not TRASH_DIR.exists():
        return set()
    return set(TRASH_DIR.iterdir())


def trash(path: str) -> str:
    """휴지통으로 보내고, `~/.Trash` 에 새로 생긴 항목 경로를 표식으로 돌려준다(못 찾으면 "").
    외장 드라이브는 `/Volumes/<드라이브>/.Trashes` 로 가서 못 찾는다 → 되돌리기 불가(todo)."""
    try:
        before = _snapshot()
    except Exception:
        logger.exception("  휴지통 목록(전) 실패")
        before = set()
    send2trash(path)
    try:
        new = _snapshot() - before
    except Exception:
        logger.exception("  휴지통 목록(후) 실패")
        new = set()
    token = str(next(iter(new))) if len(new) == 1 else ""
    logger.info(f"  trash {path!r} → {token!r}")
    return token


def restore(token: str, dst: str):
    body = Path(token)
    if not body.exists():
        raise FileNotFoundError(f"휴지통 본체 없음: {body}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(str(body), dst)


# ---------------------------------------------------------------------------
# 한글 입력 상태 단축키 — 물리 키코드로 가로챈다
# ---------------------------------------------------------------------------
def install_key_monitor(window):
        """macOS NSEvent monitor 로 IME 우회 단축키 등록.

        - keyCode 는 macOS 물리 키 코드 (HIToolbox/Events.h)
        - return None = 이벤트 차단 (Qt 까지 안 감), return event = 통과
        - Cmd/Ctrl/Alt 동반 시는 통과 (시스템 단축키 보호)
        - QLineEdit 포커스 시는 통과 (필터 입력)
        - Shift 동반은 무시 (Shift+N 같은 키는 _handle_key 에서 처리)
        """
        try:
            from AppKit import NSEvent
        except Exception as e:
            # 🔴 pyobjc 가 없으면 W/S/A/D/Q/E/C/Space/M/I/1~9 단축키가 전부 죽는다.
            # 조용히 넘어가면 「단축키가 안 먹는다」로만 보여 원인 추적이 어렵다.
            logger.error(
                "pyobjc(AppKit) 로드 실패 — 단축키가 동작하지 않습니다. "
                "`pip install pyobjc-framework-Cocoa` 후 재실행하세요. (%s: %s)",
                type(e).__name__, e,
            )
            try:
                QMessageBox.warning(
                    window, "단축키 비활성",
                    "pyobjc(AppKit) 가 설치되지 않아 키보드 단축키가 동작하지 않습니다.\n\n"
                    "터미널에서 아래를 실행한 뒤 다시 켜 주세요.\n\n"
                    "    pip install pyobjc-framework-Cocoa",
                )
            except Exception:
                pass
            return

        NSEventMaskKeyDown = 1 << 10
        # Cmd/Ctrl/Opt/Shift modifier 비트
        MOD_CMD   = 1 << 20
        MOD_OPT   = 1 << 19
        MOD_CTRL  = 1 << 18
        MOD_SHIFT = 1 << 17
        BLOCKING_MODS = MOD_CMD | MOD_OPT | MOD_CTRL | MOD_SHIFT

        # macOS virtual key codes
        # 왼손 = 왼쪽 source / 오른손 = 오른쪽 타겟 (v3). 1~9 는 숫자패드도 등록
        kc = {
            0x0D: lambda: window._move_source_cursor(-1),    # W
            0x01: lambda: window._move_source_cursor(+1),    # S
            0x00: window._source_up,                          # A — 상위 폴더 (0.6.3)
            0x02: window._source_enter,                       # D — 폴더 진입
            0x0C: lambda: window._goto_sibling_image(-1),    # Q — 이전 사진
            0x0E: lambda: window._goto_sibling_image(+1),    # E — 다음 사진
            0x08: lambda: window._run_file_op("copy"),       # C
            0x31: lambda: window._run_file_op("move"),       # Space
            0x2E: lambda: window._run_file_op("move"),       # M
            0x22: lambda: window.preview.toggle_exif(),      # I
            0x09: window._view_fullscreen,                  # V — 전체화면 (0.6.1)
            0x53: lambda: window.left.select_at(0),          # keypad 1
            0x54: lambda: window.left.select_at(1),          # keypad 2
            0x55: lambda: window.left.select_at(2),          # keypad 3
            0x56: lambda: window.left.select_at(3),          # keypad 4
            0x57: lambda: window.left.select_at(4),          # keypad 5
            0x58: lambda: window.left.select_at(5),          # keypad 6
            0x59: lambda: window.left.select_at(6),          # keypad 7
            0x5B: lambda: window.left.select_at(7),          # keypad 8
            0x5C: lambda: window.left.select_at(8),          # keypad 9
            0x12: lambda: window.left.select_at(0),          # 1
            0x13: lambda: window.left.select_at(1),          # 2
            0x14: lambda: window.left.select_at(2),          # 3
            0x15: lambda: window.left.select_at(3),          # 4
            0x17: lambda: window.left.select_at(4),          # 5
            0x16: lambda: window.left.select_at(5),          # 6
            0x1A: lambda: window.left.select_at(6),          # 7
            0x1C: lambda: window.left.select_at(7),          # 8
            0x19: lambda: window.left.select_at(8),          # 9
            # Forward Delete (0x75) 는 NSEvent 에 등록하지 않음.
            # Qt eventFilter 가 Qt.Key_Delete 로 처리 → NSEvent + Qt 중복 호출 방지
            # (NSEvent return None 해도 Qt QNSView 가 이미 받은 사본 처리하는 macOS 동작)
        }

        # Shift+숫자열 = 그 패널로 바로 이동 (Shift 는 위 kc 에서 막히므로 별도 표)
        kc_shift = {
            0x12: 0, 0x13: 1, 0x14: 2, 0x15: 3, 0x17: 4, 0x16: 5, 0x1A: 6, 0x1C: 7, 0x19: 8,
        }

        debug_keys = bool(os.environ.get("IMGMGR_DEBUG_KEYS"))

        def handler(event):
            try:
                if debug_keys:
                    logger.info(f"  NSEvent keyCode={int(event.keyCode())} flags={int(event.modifierFlags()):#x}")
                # autorepeat 차단 (Del 키 살짝 길게 누름 = 두 번째 호출 방지)
                if bool(event.isARepeat()):
                    return None
                # 전체화면 보기 중 (0.5.12): A/D/←/→ 넘김, Esc/Return/Enter/Space/F 닫기, 나머지 차단
                fsv = getattr(window, "_fullscreen", None)
                if fsv is not None and window._fullscreen_open_now():
                    code = int(event.keyCode())
                    if code in (0, 123):        # A, ←
                        fsv.step(-1)
                    elif code in (2, 124):      # D, →
                        fsv.step(+1)
                    elif code == 48:            # Tab — 정보창 보기/안 보기
                        fsv.toggle_info()
                    elif code == 50:            # ` / ~ — 하단 바 고정
                        fsv.toggle_bar_pin()
                    elif code == 33:            # [ — 축소
                        fsv.zoom_by(1 / fsv.ZOOM_STEP)
                    elif code == 30:            # ] — 확대
                        fsv.zoom_by(fsv.ZOOM_STEP)
                    elif code in (53, 36, 76, 49, 3, 9):   # Esc, Return, Enter, Space, F, V
                        fsv.close()
                    return None
                mods = int(event.modifierFlags()) & BLOCKING_MODS
                if mods == MOD_SHIFT and int(event.keyCode()) in kc_shift:
                    if QApplication.activeModalWidget() is not None:
                        return event
                    if isinstance(QApplication.focusWidget(), QLineEdit):
                        return event
                    window._send_to_panel(kc_shift[int(event.keyCode())])
                    return None
                if mods:
                    return event
                # 모달 대화상자(충돌·삭제확인·이름변경) 중엔 통과 — Space 등이 새지 않도록
                if QApplication.activeModalWidget() is not None:
                    return event
                focus = QApplication.focusWidget()
                if isinstance(focus, QLineEdit):
                    return event
                slot = kc.get(int(event.keyCode()))
                if slot is None:
                    return event
                slot()
                return None    # 차단 (Qt 까지 안 감)
            except Exception:
                logger.exception("NSEvent handler error")
                return event

        # GC 방지로 self 에 보관 (Qt-PyObjC 통합에서 reference 끊기면 monitor 죽음)
        window._native_key_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, handler
        )
        window._native_key_handler = handler          # 파이썬 쪽 참조도 유지
        logger.info(f"네이티브 키 모니터 설치: {window._native_key_monitor is not None}")
