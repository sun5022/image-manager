#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""
ImageManager — 공통 코드 (맥·리눅스·윈도우 한 벌, 0.6.0~)

OS별 차이(휴지통·삭제 확인·경로 검증·로그·앱 이름·한글 입력 단축키)는 `platforms/` 에만 있다.
여기서 OS 이름으로 분기하지 말고 PLATFORM 의 함수를 부를 것 — 쌍둥이 파일을 손으로 맞추던 구조에서
쌍둥이 누락 버그가 반복돼 2026-10-20 하나로 합쳤다.

Layout:
  LEFT  = 위 미리보기 + 아래 source 트리 (왼손 WASD · Q/E · C/Space)
  RIGHT = 다중 타겟 패널 스택 (오른손 화살표 · PgUp/PgDn · 1~9)
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QDir, QEvent, QFileInfo, QItemSelectionModel, QModelIndex, QObject,
    QPoint, QRectF, QSettings, QSize, QSortFilterProxyModel, Qt, QThread,
    QTimer, Signal,
)
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QGuiApplication, QIcon, QImageReader, QKeyEvent, QKeySequence,
    QPainter, QPixmap, QShortcut, QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
    QFileSystemModel, QGraphicsScene, QGraphicsView, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QRadioButton,
    QScrollArea,
    QSizePolicy, QSplitter, QStatusBar, QStyle, QToolButton, QTreeView, QVBoxLayout,
    QWidget, QFrame, QGraphicsDropShadowEffect,
)

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None  # graceful fallback

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".ico"}
ARCHIVE_EXTS = {".zip", ".cbz", ".rar", ".cbr", ".7z", ".cb7"}
APP_ORG = "udevapp"
APP_NAME = "ImageManager"
APP_VERSION = "0.6.5"
APP_AUTHOR = "유데브앱 최형선 (UDevApp, HyungSun Choi)"
APP_LICENSE = "Apache License 2.0"
APP_SITE = "https://udevapp.co.kr"
APP_REPO = "https://github.com/sun5022/image-manager"

# Shift+숫자열 → 패널 번호(0-based). 숫자패드는 Shift 시 NumLock 이 풀려 화살표가 되므로 제외
_SHIFT_DIGIT_KEYS = {
    Qt.Key_Exclam: 0, Qt.Key_At: 1, Qt.Key_NumberSign: 2, Qt.Key_Dollar: 3, Qt.Key_Percent: 4,
    Qt.Key_AsciiCircum: 5, Qt.Key_Ampersand: 6, Qt.Key_Asterisk: 7, Qt.Key_ParenLeft: 8,
}

from . import platforms  # noqa: E402

PLATFORM = platforms.current()     # mac / linux / windows — OS별 차이는 전부 여기로
logger = logging.getLogger("ImageManager")

# 실제 경로로 — 윈도우 TEMP 가 짧은 이름(ABCDEF~1)이면 Qt 가 주는 긴 경로와 어긋나 압축 판정이 틀린다 (0.6.5)
EXTRACT_BASE = Path(os.path.realpath(tempfile.gettempdir())) / "imgmgr_extract"


# ---------------------------------------------------------------------------
# File operation worker
# ---------------------------------------------------------------------------
@dataclass
class FileOp:
    kind: str            # "copy" | "move"
    src: str
    dst: str             # final destination path (file, not directory)


class FileOpWorker(QThread):
    progress = Signal(int, int, str)   # done, total, current
    finished_ok = Signal(list)         # list[FileOp] for undo
    error = Signal(str)

    def __init__(self, ops: list[FileOp], parent=None):
        super().__init__(parent)
        self._ops = ops

    def run(self):
        done_ops: list[FileOp] = []
        total = len(self._ops)
        for i, op in enumerate(self._ops, 1):
            try:
                dst_dir = os.path.dirname(op.dst)
                if not dst_dir or not os.path.isdir(dst_dir):
                    # Create missing parent dir on demand (handles
                    # "destination folder doesn't exist / is empty" case)
                    os.makedirs(dst_dir, exist_ok=True)

                # dst is already conflict-resolved by main thread
                # (overwrite kept, skip filtered out, rename → unique path)
                final_dst = op.dst

                if op.kind == "copy":
                    if os.path.isdir(op.src):
                        if os.path.isdir(final_dst):
                            shutil.rmtree(final_dst)
                        shutil.copytree(op.src, final_dst)
                    else:
                        shutil.copy2(op.src, final_dst)
                elif op.kind == "move":
                    shutil.move(op.src, final_dst)
                done_ops.append(op)
                self.progress.emit(i, total, op.src)
            except Exception as e:
                self.error.emit(f"{op.kind} {op.src} → {op.dst}\n{e}")
                break
        self.finished_ok.emit(done_ops)


def _norm_key(path: str) -> str:
    """경로 사전 키 정규화 — 윈도우는 Qt 가 `C:/a/b`, pathlib 이 `C:\\a\\b` 를 주므로 그대로 비교하면 어긋난다
    (2026-10-19 윈도우 실측: 압축 안에서 Q 가 압축 부모로 못 감). 대소문자도 OS 규칙대로."""
    return os.path.normcase(os.path.normpath(path))


def _unique_path(path: str) -> str:
    """Return path that does not collide; appends ' (N)' before extension."""
    if not os.path.exists(path):
        return path
    p = Path(path)
    stem, suffix, parent = p.stem, p.suffix, p.parent
    n = 1
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return str(candidate)
        n += 1


# ---------------------------------------------------------------------------
# Preview widget
# ---------------------------------------------------------------------------
class PreviewView(QGraphicsView):
    clicked = Signal()   # 클릭(드래그 아님) → 전체화면 (0.5.12)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#33363b"))  # 사진 색 판단이 쉬운 중간 차콜
        self._pixmap_item = None
        self._exif_label = QLabel(self)
        self._exif_label.setStyleSheet(
            "background: rgba(0,0,0,160); color: white; padding: 6px;"
            "font-family: monospace; font-size: 11px;"
        )
        self._exif_label.hide()
        self._exif_label.move(8, 8)
        self._current_path: Optional[str] = None
        self._fit_on_next = True

    def load(self, path: Optional[str]):
        self._scene.clear()
        self._pixmap_item = None
        self._current_path = path
        self._exif_label.hide()
        if not path or not os.path.isfile(path):
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in IMAGE_EXTS:
            return
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            return
        pm = QPixmap.fromImage(img)
        self._pixmap_item = self._scene.addPixmap(pm)
        self._scene.setSceneRect(QRectF(pm.rect()))
        self._fit_on_next = True
        self.resetTransform()
        self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def mousePressEvent(self, ev):
        # 클릭(드래그 아님) → 전체화면 (0.5.12). 드래그 스크롤은 그대로 QGraphicsView 가 처리
        self._press_pos = ev.position().toPoint()
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if ev.button() == Qt.LeftButton and self._pixmap_item is not None:
            if (ev.position().toPoint() - getattr(self, "_press_pos", ev.position().toPoint())).manhattanLength() < 6:
                self.clicked.emit()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._pixmap_item and self._fit_on_next:
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def wheelEvent(self, ev: QWheelEvent):
        if not self._pixmap_item:
            return
        self._fit_on_next = False
        factor = 1.25 if ev.angleDelta().y() > 0 else 1 / 1.25
        self.scale(factor, factor)

    def toggle_exif(self):
        if not self._current_path:
            return
        if self._exif_label.isVisible():
            self._exif_label.hide()
            return
        info = QFileInfo(self._current_path)
        reader = QImageReader(self._current_path)
        size = reader.size()
        text = (
            f"File : {info.fileName()}\n"
            f"Path : {info.absolutePath()}\n"
            f"Size : {info.size():,} bytes\n"
            f"Image: {size.width()} × {size.height()}\n"
            f"Mtime: {info.lastModified().toString('yyyy-MM-dd HH:mm:ss')}"
        )
        self._exif_label.setText(text)
        self._exif_label.adjustSize()
        self._exif_label.show()


class FullscreenViewer(QWidget):
    """이미지 클릭 → 전체화면 보기 (0.5.12). ←/→·A/D = 같은 폴더의 이전/다음 이미지(끝에서 순환),
    Esc/Enter/Space/F/클릭 = 닫기. 넘길 때마다 on_change(path) 로 원래 트리의 커서를 따라 옮겨
    닫은 뒤 바로 이어서 분류할 수 있다. 떠 있는 동안 다른 단축키(이동·삭제 등)는 막는다."""

    INFO_MODES = {"show": None, "1": 1000, "5": 5000, "10": 10000, "hide": -1}   # 설정값 → 숨김까지 ms (None=계속, -1=안 보기)

    def __init__(self, parent, files: list, idx: int, on_change, on_close, info_mode: str = "5",
                 at_end: str = "folder", on_folder=None):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setStyleSheet("background: black;")
        self.setCursor(Qt.ArrowCursor)
        self._files, self._idx = list(files), idx
        self._on_change, self._on_close = on_change, on_close
        # 끝에서 동작 (0.5.15): wrap=처음으로(안내) / folder=다음·이전 폴더(on_folder(direction) → (files, idx) 또는 None) / stop=멈춤(안내)
        self._at_end = at_end if at_end in ("wrap", "folder", "stop") else "wrap"
        self._on_folder = on_folder
        self._pm = None
        self._zoom = 1.0                 # 1.0 = 화면 맞춤. [ ] · − + · 최대 16배 (0.6.1)
        self._center = None              # 확대 중 화면 가운데에 올 이미지 좌표 (None = 이미지 가운데)
        self._drag_from = None           # 드래그 시작 (마우스 위치, 그때의 center)
        self._dragged = False            # 드래그였으면 손 뗄 때 닫지 않는다
        self._wheel_acc = 0              # 휠 누적 (트랙패드의 잘게 쪼개진 값 모으기)
        self._wheel_last = 0.0
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("color: #bbb; font-size: 14px;")
        # ── 플로팅 정보창 (꿀뷰식, 0.5.13): 왼쪽 위 반투명 상자. Tab = 보기/안 보기, ✕ = 안 보기(+안내)
        self._info_mode = info_mode if info_mode in self.INFO_MODES else "5"
        self._info_user_hidden = False      # 사용자가 Tab/✕ 로 감춘 상태 (넘겨도 다시 안 뜸)
        # 정보 카드 — 왼쪽 아래 반투명 카드, 왼쪽 초록 포인트 바(앱의 활성 패널 색), 굵은 파일명 + 회색 메타 + 키 힌트.
        # (꿀뷰의 「왼쪽 위 흰 글씨 + 둥근 ✕」 와는 다른 모양으로 — 사용자 요청 2026-10-19)
        self._info = QFrame(self)
        self._info.setObjectName("FsInfo")
        self._info.setStyleSheet(
            "#FsInfo { background: rgba(18, 20, 24, 200); border: 1px solid rgba(255,255,255,28); border-radius: 10px; }"
            "#FsInfo QLabel { background: transparent; }"
            "#FsInfoBar { background: #3fb950; border-radius: 2px; }")
        shadow = QGraphicsDropShadowEffect(self._info)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 160))
        self._info.setGraphicsEffect(shadow)
        outer = QHBoxLayout(self._info)
        outer.setContentsMargins(12, 10, 16, 10)
        outer.setSpacing(12)
        bar = QFrame()
        bar.setObjectName("FsInfoBar")
        bar.setFixedWidth(4)
        outer.addWidget(bar)
        il = QVBoxLayout()
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(3)
        outer.addLayout(il)
        self._info_lines = [QLabel(), QLabel(), QLabel()]      # 0 힌트(Tab) · 1 파일명 · 2 메타
        self._info_lines[0].setStyleSheet("color: #8b949e; font-size: 11px;")
        self._info_lines[1].setStyleSheet("color: white; font-size: 15px; font-weight: bold;")
        self._info_lines[2].setStyleSheet("color: #c9d1d9; font-size: 13px;")
        for lb in self._info_lines:
            il.addWidget(lb)
        self._info_timer = QTimer(self)
        self._info_timer.setSingleShot(True)
        self._info_timer.timeout.connect(self._info.hide)
        # 안내 토스트 (✕ 눌렀을 때)
        self._toast = QLabel(self)
        self._toast.setAlignment(Qt.AlignCenter)
        self._toast.setStyleSheet(
            "color: white; background: rgba(18,20,24,210); border: 1px solid rgba(255,255,255,28);"
            " padding: 8px 16px; border-radius: 8px; font-size: 13px;")
        self._toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast.hide)
        # ── 하단 플로팅 바 (0.5.14): 마우스를 아래쪽으로 가져가면 뜨고, 벗어나면 잠시 뒤 사라짐. 「고정」(`~`)이면 계속
        self.setMouseTracking(True)
        self._label.setMouseTracking(True)
        # 「고정」은 설정에 저장 — 전체화면을 닫았다 다시 열어도 고정 상태로 바로 보인다 (사용자 지시 2026-10-19)
        self._bar_pinned = bool(QSettings(APP_ORG, APP_NAME).value("fullscreenBarPinned", False, type=bool))
        self._bar = QFrame(self)
        self._bar.setObjectName("FsBar")
        self._bar.setStyleSheet(
            "#FsBar { background: rgba(18, 20, 24, 215); border: 1px solid rgba(255,255,255,28); border-radius: 10px; }"
            "#FsBar QToolButton { color: #e6edf3; background: transparent; border: 1px solid transparent; border-radius: 6px;"
            "  font-size: 13px; padding: 5px 10px; }"
            "#FsBar QToolButton:hover { background: rgba(255,255,255,24); border-color: rgba(255,255,255,40); }"
            "#FsBar QToolButton:checked { background: rgba(63,185,80,50); color: #3fb950; border-color: rgba(63,185,80,120); }"
            "#FsBar QLabel#FsBarPos { color: #3fb950; font-size: 13px; font-weight: bold; background: rgba(63,185,80,28);"
            "  border-radius: 6px; padding: 4px 10px; }"
            "#FsBarAccent { background: #3fb950; border-radius: 2px; }")
        bl = QHBoxLayout(self._bar)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(6)
        accent = QFrame()
        accent.setObjectName("FsBarAccent")
        accent.setFixedWidth(4)
        bl.addWidget(accent)

        def _btn(text, tip, slot, checkable=False):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.setCheckable(checkable)
            b.clicked.connect(slot)
            bl.addWidget(b)
            return b
        self._bar_prev = _btn("◀  이전", "이전 (← / A)", lambda: self.step(-1))
        self._bar_pos = QLabel()
        self._bar_pos.setObjectName("FsBarPos")
        bl.addWidget(self._bar_pos)
        self._bar_next = _btn("다음  ▶", "다음 (→ / D · 휠)", lambda: self.step(+1))
        bl.addSpacing(10)
        self._bar_zoom_out = _btn("−", "축소 ( [ )", lambda: self.zoom_by(1 / self.ZOOM_STEP))
        self._bar_zoom = QLabel()
        self._bar_zoom.setObjectName("FsBarPos")
        bl.addWidget(self._bar_zoom)
        self._bar_zoom_in = _btn("+", "확대 ( ] ) — 확대 중엔 드래그로 이동", lambda: self.zoom_by(self.ZOOM_STEP))
        bl.addSpacing(10)
        self._bar_info = _btn("정보  Tab", "정보 카드 보기/안 보기 (Tab)", self.toggle_info)
        self._bar_pin = _btn("고정  ~", "바를 항상 보이기 (~)", self.toggle_bar_pin, checkable=True)
        self._bar_close = _btn("닫기  Esc", "전체화면 닫기 (Esc)", self.close)
        self._bar.hide()
        self._bar_timer = QTimer(self)
        self._bar_timer.setSingleShot(True)
        self._bar_timer.timeout.connect(self._bar_autohide)
        self._bar_pin.setChecked(self._bar_pinned)
        self._show_current()
        if self._bar_pinned:
            self.show_bar()

    def current_path(self):
        return self._files[self._idx] if 0 <= self._idx < len(self._files) else None

    def _show_current(self):
        path = self.current_path()
        self._pm = None
        self._zoom, self._center = 1.0, None      # 넘기면 맞춤으로
        if path and os.path.isfile(path):
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            img = reader.read()
            if not img.isNull():
                self._pm = QPixmap.fromImage(img)
        self._update_info(path)
        if self._pm is None:
            self._label.setPixmap(QPixmap())
            self._label.setText("(이미지를 열 수 없음)")
        else:
            self._label.setText("")
        self._fit()

    def _fit(self):
        self._label.setGeometry(self.rect())
        self._render()
        self._info.adjustSize()
        self._info.move(24, 24)   # 왼쪽 위 (사용자 지시 2026-10-19)
        self._info.raise_()
        self._bar.adjustSize()
        self._bar.move((self.width() - self._bar.width()) // 2, self.height() - self._bar.height() - 24)   # 아래 가운데 (사용자 지시)
        self._bar.raise_()
        if self._toast.isVisible():
            self._place_toast()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._fit()

    # ── 확대·축소·이동 (0.6.1) ──
    ZOOM_STEP = 1.25
    ZOOM_MAX = 16.0

    def _base_scale(self) -> float:
        pw, ph = self._pm.width(), self._pm.height()
        return min(self.width() / pw, self.height() / ph) if pw and ph else 1.0

    def _render(self):
        """맞춤(1.0)이면 화면에 맞춰 축소, 확대 중이면 보이는 영역만 잘라서 확대 — 큰 사진을 통째로 키우지 않는다."""
        self._bar_zoom.setText(f"{round(self._zoom * 100)}%")
        if self._pm is None or self.width() <= 0 or self.height() <= 0:
            return
        if self._zoom <= 1.0001:
            self._label.setPixmap(self._pm.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            return
        pw, ph = self._pm.width(), self._pm.height()
        scale = self._base_scale() * self._zoom
        vis_w, vis_h = min(pw, self.width() / scale), min(ph, self.height() / scale)
        cx, cy = self._center if self._center else (pw / 2, ph / 2)
        cx = min(max(cx, vis_w / 2), pw - vis_w / 2)          # 이미지 밖으로 못 나가게
        cy = min(max(cy, vis_h / 2), ph - vis_h / 2)
        self._center = (cx, cy)
        src = QRectF(cx - vis_w / 2, cy - vis_h / 2, vis_w, vis_h).toAlignedRect().intersected(self._pm.rect())
        crop = self._pm.copy(src)
        self._label.setPixmap(crop.scaled(max(1, round(src.width() * scale)), max(1, round(src.height() * scale)),
                                          Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def zoom_by(self, factor: float):
        if self._pm is None:
            return
        self._zoom = min(max(self._zoom * factor, 1.0), self.ZOOM_MAX)
        if self._zoom <= 1.0001:
            self._zoom, self._center = 1.0, None
        self._render()
        self.setCursor(Qt.OpenHandCursor if self._zoom > 1.0 else Qt.ArrowCursor)

    def zoom(self) -> float:
        return self._zoom

    def wheelEvent(self, ev):
        """휠 = 이전/다음 (끝에서는 설정 「전체화면 끝에서」대로). 트랙패드의 잘게 쪼개진 값은 모아서 한 칸."""
        import time
        self._wheel_acc += ev.angleDelta().y()
        now = time.monotonic()
        if abs(self._wheel_acc) >= 120 and now - self._wheel_last >= 0.15:
            self.step(-1 if self._wheel_acc > 0 else +1)
            self._wheel_acc = 0
            self._wheel_last = now
        ev.accept()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_from = (ev.position(), self._center)
            self._dragged = False
        super().mousePressEvent(ev)

    def step(self, direction: int):
        if not self._files:
            return
        new = self._idx + direction
        if 0 <= new < len(self._files):
            self._idx = new
        else:
            forward = direction > 0
            if self._at_end == "stop":
                self.show_toast("마지막 이미지입니다" if forward else "처음 이미지입니다")
                return
            if self._at_end == "folder":
                res = None
                if self._on_folder is not None:
                    try:
                        res = self._on_folder(direction)
                    except Exception:
                        res = None
                if res:
                    self._files, self._idx = list(res[0]), res[1]
                    folder = os.path.basename(os.path.dirname(self._files[self._idx]))
                    self.show_toast(("다음 폴더: " if forward else "이전 폴더: ") + folder)
                else:
                    self.show_toast("다음 폴더가 없습니다" if forward else "이전 폴더가 없습니다")
                    return
            else:   # wrap
                self._idx = 0 if forward else len(self._files) - 1
                self.show_toast("처음 이미지입니다" if forward else "마지막 이미지입니다")
        self._show_current()
        try:
            self._on_change(self.current_path())
        except Exception:
            pass

    # ── 정보창 ──
    def _update_info(self, path):
        """현재 이미지 정보로 상자를 채우고, 설정에 따라 보이기/타이머/숨기기."""
        name = os.path.basename(path) if path else ""
        dims = ""
        if self._pm is not None:
            fmt = os.path.splitext(path)[1].lstrip(".").upper() if path else ""
            depth = self._pm.depth()
            mode = "RGBA32" if depth == 32 else ("RGB24" if depth == 24 else f"{depth}bit")
            dims = f"{self._pm.width()}×{self._pm.height()}  {fmt} {mode}"
        size = mtime = ""
        if path and os.path.isfile(path):
            info = QFileInfo(path)
            b = info.size()
            size = f"{b / 1024 / 1024:.1f}MB" if b >= 1024 * 1024 else f"{b / 1024:.1f}KB"
            mtime = info.lastModified().toString("yyyy-MM-dd HH:mm")
        meta = "  ·  ".join(x for x in (f"{self._idx + 1} / {len(self._files)}", dims, size, mtime) if x)
        texts = ["Tab  보기 / 안 보기", name or "(없음)", meta]
        for lb, t in zip(self._info_lines, texts):
            lb.setText(t)
            lb.setVisible(bool(t))
        self._info.adjustSize()
        self._apply_info_mode()
        self._bar_pos.setText(f"{self._idx + 1} / {len(self._files)}")
        self._bar.adjustSize()

    def _apply_info_mode(self):
        """설정값대로: 계속 보기 / N초 후 숨김 / 안 보기. 사용자가 감췄으면 그대로 둔다."""
        self._info_timer.stop()
        ms = self.INFO_MODES.get(self._info_mode)
        if ms == -1 or self._info_user_hidden:
            self._info.hide()
            return
        self._info.show()
        self._info.raise_()
        if ms:
            self._info_timer.start(ms)

    def info_visible(self) -> bool:
        return self._info.isVisible()

    def toggle_info(self):
        """Tab — 정보창 보기/안 보기. 다시 보이면 타이머도 다시 센다."""
        if self._info.isVisible():
            self._info_timer.stop()
            self._info.hide()
            self._info_user_hidden = True
        else:
            self._info_user_hidden = False
            if self.INFO_MODES.get(self._info_mode) == -1:
                # 「안 보기」 설정에서 Tab 은 그때만 보여 준다 (다음 사진으로 넘기면 다시 숨김)
                self._info_timer.stop()
                self._info.show()
                self._info.raise_()
            else:
                self._apply_info_mode()

    def show_toast(self, text: str, ms: int = 3000):
        self._toast.setText(text)
        self._toast.adjustSize()
        self._place_toast()
        self._toast.show()
        self._toast.raise_()
        self._toast_timer.start(ms)

    def _place_toast(self):
        self._toast.move(self.width() - self._toast.width() - 24, 24)   # 오른쪽 위 (사용자 지시 2026-10-19)

    # ── 하단 바 ──
    BAR_HOVER_ZONE = 120   # 아래쪽 몇 px 안에 마우스가 오면 바를 띄울지

    def bar_visible(self) -> bool:
        return self._bar.isVisible()

    def show_bar(self):
        self._bar_timer.stop()
        self._bar.show()
        self._bar.raise_()

    def _bar_autohide(self):
        if not self._bar_pinned:
            self._bar.hide()

    def toggle_bar_pin(self, checked=None):
        """「고정」 — 바를 항상 보이기 (`~`). 버튼 클릭·키 양쪽에서 부른다."""
        self._bar_pinned = (not self._bar_pinned) if checked is None else bool(checked)
        self._bar_pin.setChecked(self._bar_pinned)
        QSettings(APP_ORG, APP_NAME).setValue("fullscreenBarPinned", self._bar_pinned)
        if self._bar_pinned:
            self.show_bar()
        else:
            self._bar_timer.start(1200)

    def mouseMoveEvent(self, ev):
        if self._drag_from is not None and self._zoom > 1.0 and (ev.buttons() & Qt.LeftButton):
            start, center = self._drag_from
            d = ev.position() - start
            if self._dragged or abs(d.x()) + abs(d.y()) > 4:
                self._dragged = True
                self.setCursor(Qt.ClosedHandCursor)
                scale = self._base_scale() * self._zoom
                cx, cy = center if center else (self._pm.width() / 2, self._pm.height() / 2)
                self._center = (cx - d.x() / scale, cy - d.y() / scale)
                self._render()
            return
        y = ev.position().y()
        if y >= self.height() - self.BAR_HOVER_ZONE:
            self.show_bar()
        elif self._bar.isVisible() and not self._bar_pinned and not self._bar_timer.isActive():
            self._bar_timer.start(900)
        super().mouseMoveEvent(ev)

    def handle_key(self, ev) -> bool:
        k = ev.key()
        if k in (Qt.Key_Left, Qt.Key_A):
            self.step(-1)
        elif k in (Qt.Key_Right, Qt.Key_D):
            self.step(+1)
        elif k in (Qt.Key_Tab, Qt.Key_Backtab):
            self.toggle_info()
        elif k in (Qt.Key_QuoteLeft, Qt.Key_AsciiTilde):
            self.toggle_bar_pin()
        elif k == Qt.Key_BracketLeft:
            self.zoom_by(1 / self.ZOOM_STEP)
        elif k == Qt.Key_BracketRight:
            self.zoom_by(self.ZOOM_STEP)
        elif k in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space, Qt.Key_F, Qt.Key_V):
            self.close()
        return True   # 전체화면 중엔 나머지 단축키를 삼킨다

    def keyPressEvent(self, ev):
        self.handle_key(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            dragged, self._dragged, self._drag_from = self._dragged, False, None
            if dragged:                    # 확대 중 드래그 = 이동. 닫지 않는다
                self.setCursor(Qt.OpenHandCursor)
                return
            # 바 위(버튼 사이 빈 곳)를 눌렀을 땐 닫지 않는다
            if self._bar.isVisible() and self._bar.geometry().contains(ev.position().toPoint()):
                return
            self.close()

    def closeEvent(self, ev):
        super().closeEvent(ev)
        try:
            self._on_close()
        except Exception:
            pass


class ClickableLabel(QLabel):
    """클릭 신호를 내는 QLabel — 타겟 미니 프리뷰 → 전체화면 (0.5.12)."""
    clicked = Signal()

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()


# ---------------------------------------------------------------------------
# Tree panel (used for both source and targets)
# ---------------------------------------------------------------------------
class FilteredFsModel(QSortFilterProxyModel):
    """Optional regex filter on the source QFileSystemModel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._regex: Optional[re.Pattern] = None
        # 이동으로 사라진 경로. sshfs 등 FUSE 마운트는 파일 감시가 안 돼
        # QFileSystemModel 이 행을 안 지운다 → 여기서 숨긴다. 존재하면(Undo) 다시 보임
        self._gone: set[str] = set()

    def mark_gone(self, paths):
        self._gone.update(paths)
        self.invalidateFilter()

    def set_regex(self, pattern: str):
        if not pattern:
            self._regex = None
        else:
            try:
                self._regex = re.compile(pattern, re.IGNORECASE)
            except re.error:
                self._regex = None
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model: QFileSystemModel = self.sourceModel()
        idx = model.index(source_row, 0, source_parent)
        if self._gone:
            p = model.filePath(idx)
            if p in self._gone and not os.path.exists(p):
                return False
        if self._regex is None:
            return True
        if model.isDir(idx):
            return True
        name = model.fileName(idx)
        return bool(self._regex.search(name))


class PathTreeView(QTreeView):
    """Tree bound to a path, with helpers for nav/selection."""
    pathChanged = Signal(str)

    def __init__(self, model: QFileSystemModel, proxy: Optional[FilteredFsModel] = None, parent=None):
        super().__init__(parent)
        self._fs_model = model
        self._proxy = proxy
        self.setModel(proxy if proxy else model)
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setUniformRowHeights(True)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder)
        for col in (1, 2, 3):  # hide size/type/date by default
            self.setColumnHidden(col, True)
        self.setEditTriggers(QTreeView.EditKeyPressed | QTreeView.SelectedClicked)

    # --- index translation helpers ---
    def _src_idx(self, idx: QModelIndex) -> QModelIndex:
        return self._proxy.mapToSource(idx) if self._proxy else idx

    def _from_src(self, src: QModelIndex) -> QModelIndex:
        return self._proxy.mapFromSource(src) if self._proxy else src

    # --- path API ---
    def set_root_path(self, path: str):
        if not path or not os.path.isdir(path):
            return
        src_root = self._fs_model.setRootPath(path)
        view_root = self._from_src(src_root)
        self.setRootIndex(view_root)
        self.pathChanged.emit(path)

    def current_root_path(self) -> str:
        root_view = self.rootIndex()
        src = self._src_idx(root_view)
        return self._fs_model.filePath(src)

    def focusInEvent(self, event):
        # Qt 는 커서가 없는 트리에 포커스가 들어오면 첫 항목을 자동으로 고른다.
        # 타겟 패널에선 그 첫 항목(하위 폴더)이 보낼 곳이 돼 버리므로 커서 없음 상태를 유지한다
        had = self.currentIndex().isValid()
        super().focusInEvent(event)
        if not had and self.currentIndex().isValid():
            self.selectionModel().clear()
            self.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.Clear)

    def selected_paths(self) -> list[str]:
        paths: list[str] = []
        for idx in self.selectionModel().selectedRows(0):
            src = self._src_idx(idx)
            paths.append(self._fs_model.filePath(src))
        return paths

    def current_path(self) -> Optional[str]:
        idx = self.currentIndex()
        if not idx.isValid():
            return None
        return self._fs_model.filePath(self._src_idx(idx))

    # --- nav ---
    def enter_or_expand(self):
        idx = self.currentIndex()
        if not idx.isValid():
            return
        src = self._src_idx(idx)
        path = self._fs_model.filePath(src)
        if self._fs_model.isDir(src):
            self.set_root_path(path)

    def go_up(self):
        root = self.current_root_path()
        if not root:
            return
        parent = os.path.dirname(root.rstrip("/"))
        if parent and os.path.isdir(parent) and parent != root:
            self.set_root_path(parent)


# ---------------------------------------------------------------------------
# Left target panel (one entry in the scroll stack)
# ---------------------------------------------------------------------------
class TargetPanel(QWidget):
    mini_clicked = Signal()   # 미니 프리뷰 클릭 → 전체화면 (0.5.12)
    activated = Signal(object)        # self
    closeRequested = Signal(object)   # self

    def __init__(self, fs_model: QFileSystemModel, path: str, parent=None):
        super().__init__(parent)
        self._active = False

        self._header = QWidget(self)
        self._header.setObjectName("TargetPanelHeader")
        self._header.setAutoFillBackground(True)
        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(8, 4, 8, 4)
        self._index_label = QLabel("(?)")
        self._index_label.setObjectName("TargetIndexLabel")
        # 헤더 = 폴더 이름만 (전체 경로는 툴팁). 긴 경로 라벨이 최소 폭을 밀어 올려
        # 폴더명·✕ 가 화면 밖으로 잘리던 문제 (v3, 2026-10-06)
        self._path_label = QLabel()
        self._path_label.setObjectName("TargetPathLabel")
        self._path_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._path_label.setMinimumWidth(0)
        self._set_path_text(path)
        self._close_btn = QToolButton()
        self._close_btn.setObjectName("TargetCloseBtn")
        self._close_btn.setText("✕")
        self._close_btn.setAutoRaise(True)
        self._close_btn.clicked.connect(lambda: self.closeRequested.emit(self))
        h_lay.addWidget(self._index_label)
        h_lay.addWidget(self._path_label, 1)
        h_lay.addWidget(self._close_btn)

        self.tree = PathTreeView(fs_model, proxy=None, parent=self)
        self.tree.set_root_path(path)
        self.tree.pathChanged.connect(self._set_path_text)

        # Mini preview on the LEFT side of the panel body — shows current
        # selection (if image) so the user can see what's already in this target.
        self._mini = ClickableLabel()
        self._mini.setObjectName("TargetMiniPreview")
        self._mini.setAlignment(Qt.AlignCenter)
        self._mini.setMinimumWidth(60)
        self._mini.setScaledContents(False)
        self._mini.setText("(미리보기 없음)")
        self._mini_path: Optional[str] = None
        self._mini.clicked.connect(self.mini_clicked)
        self.tree.selectionModel().currentChanged.connect(self._on_current_changed)

        # Body: horizontal splitter — [Preview] | [Tree]
        self._body = QSplitter(Qt.Horizontal, self)
        self._body.setChildrenCollapsible(False)
        self._body.addWidget(self._mini)
        self._body.addWidget(self.tree)
        self._body.setStretchFactor(0, 1)
        self._body.setStretchFactor(1, 2)
        self._body.setSizes([180, 360])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._header)
        lay.addWidget(self._body, 1)

        self.setMinimumHeight(180)
        self._apply_style()
        self.tree.installEventFilter(self)

    def _on_current_changed(self, current, _prev):
        # 미니 프리뷰는 커서가 「파일」일 때만 바꾼다. 커서가 비거나 폴더면 마지막 사진을 그대로 둔다 —
        # 패널 클릭(누름=활성화 → 포커스 → Qt 가 첫 항목(하위 폴더)을 자동 선택)에서 미니 프리뷰가 폴더로 바뀌어
        # 뗄 때 열 사진이 없어지고 「폴더가 선택」된 것처럼 보였다 (0.6.1, 사용자 실사용 지적)
        if not current.isValid():
            return
        path = self.tree._fs_model.filePath(current)
        if os.path.isfile(path):
            self._set_mini(path)

    def _set_mini(self, path: Optional[str]):
        self._mini_path = path
        if not path or not os.path.isfile(path):
            self._mini.clear()
            self._mini.setText("(폴더 / 선택 없음)")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in IMAGE_EXTS:
            self._mini.clear()
            self._mini.setText("(이미지 아님)")
            return
        pm = QPixmap(path)
        if pm.isNull():
            self._mini.clear()
            self._mini.setText("(로드 실패)")
            return
        scaled = pm.scaled(
            self._mini.width() - 8, self._mini.height() - 8,
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._mini.setPixmap(scaled)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # Rescale current preview on width change
        if self._mini_path:
            self._set_mini(self._mini_path)

    def _set_path_text(self, path: str):
        p = path.rstrip("/") or "/"
        self._path_label.setText(os.path.basename(p) or p)
        self._path_label.setToolTip(p)
        self._header.setToolTip(p)

    def path(self) -> str:
        return self.tree.current_root_path()

    def set_active(self, active: bool):
        if self._active == active:
            return
        self._active = active
        self._apply_style()

    def set_index(self, idx: int):
        self._index_label.setText(f"({idx})")

    def _apply_style(self):
        if self._active:
            self.setStyleSheet(
                "TargetPanel { border: 3px solid #4caf50; border-radius: 4px; background: #1b1f1b; }"
                "QWidget#TargetPanelHeader { background: #2e7d32; border-top-left-radius: 2px; border-top-right-radius: 2px; }"
                "QLabel#TargetPathLabel { color: #ffffff; font-weight: bold; font-size: 12px; }"
                "QLabel#TargetIndexLabel { background: #1b5e20; color: #ffffff; padding: 2px 8px; "
                "border-radius: 3px; font-weight: bold; font-size: 12px; }"
                "QLabel#TargetMiniPreview { background: #2a2d31; color: #666666; border-right: 1px solid #2e7d32; }"
                "QToolButton#TargetCloseBtn { color: #ffffff; }"
            )
        else:
            self.setStyleSheet(
                "TargetPanel { border: 1px solid #3a3a3a; border-radius: 4px; background: #181818; }"
                "QWidget#TargetPanelHeader { background: #262626; border-top-left-radius: 2px; border-top-right-radius: 2px; }"
                "QLabel#TargetPathLabel { color: #888888; font-weight: normal; font-size: 12px; }"
                "QLabel#TargetIndexLabel { background: #333333; color: #aaaaaa; padding: 2px 8px; "
                "border-radius: 3px; font-size: 12px; }"
                "QLabel#TargetMiniPreview { background: #26282c; color: #555555; border-right: 1px solid #2a2a2a; }"
                "QToolButton#TargetCloseBtn { color: #888888; }"
            )

    def mousePressEvent(self, ev):
        self.activated.emit(self)
        super().mousePressEvent(ev)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.FocusIn or ev.type() == QEvent.MouseButtonPress:
            self.activated.emit(self)
        return super().eventFilter(obj, ev)


# ---------------------------------------------------------------------------
# Left container — scroll area holding many TargetPanels + add button
# ---------------------------------------------------------------------------
class LeftPane(QWidget):
    activeChanged = Signal(object)  # TargetPanel
    panelAdded = Signal(object)     # TargetPanel

    def __init__(self, fs_model: QFileSystemModel, parent=None):
        super().__init__(parent)
        self._fs_model = fs_model
        self._panels: list[TargetPanel] = []
        self._active: Optional[TargetPanel] = None

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._splitter = QSplitter(Qt.Vertical, self._inner)
        self._splitter.setChildrenCollapsible(False)

        inner_lay = QVBoxLayout(self._inner)
        inner_lay.setContentsMargins(4, 4, 4, 4)
        inner_lay.setSpacing(4)
        inner_lay.addWidget(self._splitter, 1)

        self._add_btn = QPushButton("+ 타겟 폴더 추가")
        self._add_btn.clicked.connect(self._on_add_clicked)
        inner_lay.addWidget(self._add_btn)

        self._scroll.setWidget(self._inner)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._scroll)

    # --- panel management ---
    def add_panel(self, path: str) -> Optional[TargetPanel]:
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "폴더 없음", f"폴더가 없습니다:\n{path}")
            return None
        panel = TargetPanel(self._fs_model, path, self._inner)
        panel.activated.connect(self._on_panel_activated)
        panel.closeRequested.connect(self._on_panel_close)
        self._splitter.addWidget(panel)
        self._panels.append(panel)
        self._renumber()
        self.panelAdded.emit(panel)
        self.set_active(panel)
        return panel

    def _renumber(self):
        for i, p in enumerate(self._panels):
            p.set_index(i + 1)

    def select_at(self, idx0: int) -> bool:
        """0-based index. Returns True if a panel was selected."""
        if 0 <= idx0 < len(self._panels):
            self.set_active(self._panels[idx0])
            return True
        return False

    def _on_add_clicked(self):
        start = self._active.path() if self._active else str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "타겟 폴더 선택", start)
        if d:
            self.add_panel(d)

    def _on_panel_close(self, panel: TargetPanel):
        if panel not in self._panels:
            return
        self._panels.remove(panel)
        panel.setParent(None)
        panel.deleteLater()
        self._renumber()
        if self._active is panel:
            self._active = None
            if self._panels:
                self.set_active(self._panels[0])
            else:
                self.activeChanged.emit(None)

    def _on_panel_activated(self, panel: TargetPanel):
        self.set_active(panel)

    def set_active(self, panel: Optional[TargetPanel]):
        if panel is self._active:
            return
        for p in self._panels:
            p.set_active(p is panel)
        self._active = panel
        if panel is not None:
            self._scroll.ensureWidgetVisible(panel, 0, 40)
            panel.tree.selectionModel().clear()
            panel.tree.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.Clear)
            panel.tree.setFocus()
            # 커서를 첫 항목에 자동으로 놓지 않는다 — 첫 항목이 하위 폴더면 숫자·Shift+숫자·Space 가
            # 패널 폴더가 아니라 그 하위 폴더로 보내 버린다. 하위 폴더는 ↓ 로 직접 고른다
        self.activeChanged.emit(panel)

    def active_panel(self) -> Optional[TargetPanel]:
        return self._active

    def select_next(self, direction: int):
        if not self._panels:
            return
        if self._active is None:
            self.set_active(self._panels[0])
            return
        idx = self._panels.index(self._active)
        new_idx = max(0, min(len(self._panels) - 1, idx + direction))
        if new_idx != idx:
            self.set_active(self._panels[new_idx])

    def panel_paths(self) -> list[str]:
        return [p.path() for p in self._panels]


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, start_path: Optional[str] = None,
                 start_cursor_file: Optional[str] = None,
                 start_targets: Optional[list[str]] = None):
        super().__init__()
        # CLI 인자 — 없으면 None/[] 이고 _load_settings 가 기존 세션을 복원한다.
        # 종료 시 저장(closeEvent)은 인자 유무와 무관하게 "현재 열려 있는 경로"를
        # 그대로 쓰므로, 인자로 열었다가 다른 폴더로 이동해도 그 폴더가 저장된다.
        self._cli_source = start_path
        self._cli_cursor_file = start_cursor_file
        self._cli_targets = list(start_targets or [])

        self.setWindowTitle(APP_NAME)
        self.resize(1500, 900)

        # Shared filesystem models (one per use to avoid root-conflict surprises).
        self._left_fs = QFileSystemModel(self)
        self._left_fs.setRootPath("")
        self._left_fs.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot | QDir.AllDirs)

        self._right_fs = QFileSystemModel(self)
        self._right_fs.setRootPath("")
        self._right_fs.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot | QDir.AllDirs)

        self._proxy = FilteredFsModel(self)
        self._proxy.setSourceModel(self._right_fs)

        # Right side
        self.preview = PreviewView(self)
        self.source_tree = PathTreeView(self._right_fs, proxy=self._proxy, parent=self)
        self.source_tree.selectionModel().currentChanged.connect(self._on_source_current_changed)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("필터 (정규식) — Enter = 목록으로 · Esc/Home = 해제")
        self.filter_edit.textChanged.connect(self._proxy.set_regex)
        self.filter_edit.hide()

        # 메인(source) 탐색기 헤더 — 경로 라벨 + ⌂(홈) + 📁(폴더 선택) 버튼.
        # stale 상태 (Backspace 로 / 도달 후 빈 화면 등) 즉시 회복용.
        self.source_header = QWidget(self)
        sh_lay = QHBoxLayout(self.source_header)
        sh_lay.setContentsMargins(4, 2, 4, 2)
        sh_lay.setSpacing(4)
        self.source_path_lbl = QLabel("")
        self.source_path_lbl.setStyleSheet("color: #aaa; font-size: 10pt;")
        # 긴 경로가 창 최소 폭을 붙잡지 않게 — 좁으면 뒤가 잘리고, 전체 경로는 툴팁 (세로 녹화용 좁은 창, 0.6.2)
        self.source_path_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.source_path_lbl.setMinimumWidth(1)
        sh_lay.addWidget(self.source_path_lbl, 1)
        home_btn = QToolButton()
        home_btn.setText("⌂")
        home_btn.setToolTip("홈 폴더로 (필터 해제)")
        home_btn.clicked.connect(lambda: (self._clear_filter() if self.filter_edit.isVisible() else None,
                                          self.source_tree.set_root_path(str(Path.home()))))
        sh_lay.addWidget(home_btn)
        open_btn = QToolButton()
        open_btn.setText("📁")
        open_btn.setToolTip("폴더 선택…")
        open_btn.clicked.connect(self._pick_source_folder)
        sh_lay.addWidget(open_btn)
        self.source_tree.pathChanged.connect(self.source_path_lbl.setText)
        self.source_tree.pathChanged.connect(self.source_path_lbl.setToolTip)

        right_bottom = QWidget(self)
        rb_lay = QVBoxLayout(right_bottom)
        rb_lay.setContentsMargins(0, 0, 0, 0)
        rb_lay.setSpacing(2)
        rb_lay.addWidget(self.source_header)
        rb_lay.addWidget(self.filter_edit)
        rb_lay.addWidget(self.source_tree, 1)

        self.right_splitter = QSplitter(Qt.Vertical, self)
        self.right_splitter.addWidget(self.preview)
        self.right_splitter.addWidget(right_bottom)
        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 2)

        # Left side
        self.left = LeftPane(self._left_fs, self)

        # Main splitter — source(프리뷰+트리) 왼쪽 | 타겟 스택 오른쪽 (v3, 2026-10-06)
        # 변수명 left/right_splitter 는 v2 이름 유지 — 화면 위치는 반대다.
        self.main_splitter = QSplitter(Qt.Horizontal, self)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.addWidget(self.left)
        self.main_splitter.setStretchFactor(0, 2)
        self.main_splitter.setStretchFactor(1, 1)
        # 타겟 스택 최소 폭 — 헤더(번호·폴더명·✕)와 + 버튼이 잘리지 않게. 340 → 260 (세로 9:16 녹화 창 540px 용, 0.6.2)
        self.left.setMinimumWidth(260)
        self.main_splitter.setChildrenCollapsible(False)
        self.setCentralWidget(self.main_splitter)

        # Status bar
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.status.addPermanentWidget(self.progress)
        self.status_label = QLabel("준비됨.")
        self.status.addWidget(self.status_label, 1)

        self._build_menu()

        # Undo stack
        self._undo_stack: list[list[FileOp]] = []
        self._worker: Optional[FileOpWorker] = None

        # Extracted archives: temp_dir_path -> original archive path
        self._extracted: dict[str, str] = {}

        # Global key filter
        QApplication.instance().installEventFilter(self)

        # ←/→ 를 타겟 조작으로 쓰는 위젯 목록 (트리의 접기/펼치기보다 먼저 가로챔 — 앱 전체 필터가 위젯보다 먼저 받는다)
        self._install_image_nav_shortcuts(self.source_tree)
        # Also install on each target tree (left panels) so ←/→ works wherever
        # the user has focus (filter edit excluded — has its own text cursor)
        self.left.panelAdded.connect(self._on_panel_added)

        # 미리보기(사진)에 포커스가 있어도 ↑/↓·Shift+↑/↓ 가 타겟 커서·패널 이동으로 가도록 등록
        # (2026-10-19 윈도우 실사용 지적: 사진 클릭 뒤 화살표가 QGraphicsView 스크롤로 먹힘)
        self._install_image_nav_shortcuts(self.preview)
        self._fullscreen = None
        self.preview.clicked.connect(lambda: self._open_fullscreen("source"))
        # 맥: 한글 입력 상태에서도 단축키 — 물리 키코드로 가로챔 (리눅스·윈도우는 할 일 없음)
        PLATFORM.install_key_monitor(self)
        self._load_settings()

    # --- 전체화면 보기 (0.5.12) ---
    @staticmethod
    def _image_files_in(folder: str) -> list:
        try:
            names = os.listdir(folder)
        except OSError:
            return []
        return [os.path.join(folder, n) for n in sorted(names, key=str.lower)
                if os.path.splitext(n)[1].lower() in IMAGE_EXTS and os.path.isfile(os.path.join(folder, n))]

    def _fullscreen_open_now(self) -> bool:
        """전체화면이 실제로 떠 있나. 「열려 있음」 표시만 남고 창은 없는 경우(비정상 종료 등)를 걸러낸다 —
        남아 있으면 이후 열기가 전부 막혀 「몇 번 쓰면 사진을 눌러도 안 열림」이 됐다 (0.6.1)."""
        fs = self._fullscreen
        if fs is None:
            return False
        try:
            import shiboken6
            alive = shiboken6.isValid(fs) and fs.isVisible()
        except Exception:
            alive = False
        if not alive:
            self._fullscreen = None
        return alive

    def _view_fullscreen(self):
        """V — 커서의 이미지를 전체화면으로. 폴더면 그 안 첫 이미지부터(넘기면 그 폴더 안을 돈다).
        포커스가 타겟 트리에 있으면 그 패널, 아니면 소스."""
        tree, _ = self._active_tree_and_dir()
        panel = None if tree is self.source_tree else self.left.active_panel()
        path = tree.current_path() if tree is not None else None
        if not path and panel is None:
            path = self.preview._current_path
        if not path:
            self._flash("전체화면으로 볼 이미지·폴더에 커서를 두세요.")
            return
        if os.path.isdir(path):
            files = self._image_files_in(path)
            if not files:
                self._flash(f"이미지가 없는 폴더입니다: {os.path.basename(path)}")
                return
            self._open_fullscreen("folder", panel, path=files[0])
        elif os.path.splitext(path)[1].lower() in IMAGE_EXTS:
            self._open_fullscreen("source" if panel is None else "target", panel, path=path)
        else:
            self._flash("이미지 파일이 아닙니다.")

    def _open_fullscreen(self, kind: str, panel=None, path: Optional[str] = None):
        """소스 미리보기(kind='source') / 타겟 미니 프리뷰(kind='target') 클릭·V → 전체화면.
        넘기면 그 트리의 커서도 따라가, 닫은 뒤 이어서 분류할 수 있다.
        kind='folder' — V 로 하위 폴더를 연 경우: 그 폴더 안만 돌고 트리 커서는 건드리지 않는다."""
        if self._fullscreen_open_now():
            return
        if kind == "folder":
            on_change = (lambda p: None)
        elif kind == "source":
            path = path or self.preview._current_path
            on_change = self._cursor_on_file
        else:
            if panel is None:
                return
            path = path or panel._mini_path

            def on_change(p, panel=panel):
                self._panel_cursor_on_file(panel, p)
                panel._set_mini(p)
        if not path or not os.path.isfile(path) or os.path.splitext(path)[1].lower() not in IMAGE_EXTS:
            return
        files = self._image_files_in(os.path.dirname(path))
        key = os.path.normcase(os.path.abspath(path))
        idx = next((i for i, f in enumerate(files) if os.path.normcase(os.path.abspath(f)) == key), 0)
        if not files:
            files, idx = [path], 0
        on_folder = (None if kind == "folder" else
                     (lambda d, panel=(panel if kind == "target" else None): self._fullscreen_sibling_folder(d, panel)))
        self._fullscreen = FullscreenViewer(self, files, idx, on_change, self._fullscreen_closed,
                                            info_mode=getattr(self, "_pref_fullscreenInfo", "5"),
                                            at_end=getattr(self, "_pref_fullscreenAtEnd", "folder"),
                                            on_folder=on_folder)
        # 창이 어떤 경로로 사라지든(닫기·삭제) 「열려 있음」 표시를 지운다
        self._fullscreen.destroyed.connect(lambda *_: setattr(self, "_fullscreen", None))
        self._fullscreen.showFullScreen()
        self._fullscreen.activateWindow()
        self._fullscreen.setFocus()

    def _fullscreen_closed(self):
        self._fullscreen = None
        self.activateWindow()

    def _fullscreen_sibling_folder(self, direction: int, panel=None):
        """전체화면 「다음/이전 폴더로 넘어가기」 — 지금 보는 폴더(소스, 또는 타겟 패널 폴더)와 같은 상위 폴더 안에서
        이미지가 있는 다음/이전 폴더. 찾으면 그 트리도 그 폴더로 옮기고 (files, idx) 를 돌려준다. 없으면 None."""
        tree = panel.tree if panel is not None else self.source_tree
        cur = os.path.abspath(tree.current_root_path())
        parent = os.path.dirname(cur)
        if not parent or parent == cur:
            return None
        try:
            sibs = sorted((d for d in os.listdir(parent) if os.path.isdir(os.path.join(parent, d))), key=str.lower)
        except OSError:
            return None
        names = [os.path.normcase(d) for d in sibs]
        me = os.path.normcase(os.path.basename(cur))
        if me not in names:
            return None
        i = names.index(me)
        rng = range(i + 1, len(sibs)) if direction > 0 else range(i - 1, -1, -1)
        for j in rng:
            folder = os.path.join(parent, sibs[j])
            files = self._image_files_in(folder)
            if files:
                tree.set_root_path(folder)
                return files, (0 if direction > 0 else len(files) - 1)
        return None

    def _panel_cursor_on_file(self, panel, path: str) -> bool:
        tree = panel.tree
        m = tree.model()
        root = tree.rootIndex()
        name = os.path.basename(path)
        for r in range(m.rowCount(root)):
            idx = m.index(r, 0, root)
            if m.data(idx) == name:
                tree.selectionModel().setCurrentIndex(
                    idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
                tree.scrollTo(idx)
                return True
        return False

    def _install_image_nav_shortcuts(self, widget):
        # 위젯별 installEventFilter 는 하지 않는다 — 앱 전체 필터와 겹치면 같은 키가 필터를 두 번 탄다(맥 실측).
        # 앱 전체 필터가 위젯의 keyPressEvent 보다 먼저 받으므로 집합만 유지 (obj 비교용).
        if not hasattr(self, "_image_nav_widgets"):
            self._image_nav_widgets = set()
        self._image_nav_widgets.add(widget)

    def _on_panel_added(self, panel):
        self._install_image_nav_shortcuts(panel.tree)
        panel.mini_clicked.connect(lambda p=panel: self._open_fullscreen("target", p))

    def _move_source_cursor(self, direction: int):
        tree = self.source_tree
        cur = tree.currentIndex()
        if not cur.isValid():
            root = tree.rootIndex()
            new = tree.model().index(0, 0, root)
        else:
            new = tree.indexBelow(cur) if direction > 0 else tree.indexAbove(cur)
        if new.isValid():
            tree.selectionModel().setCurrentIndex(
                new, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
            )
            tree.scrollTo(new)

    def _move_target_cursor(self, direction: int):
        panel = self.left.active_panel()
        if panel is None:
            return
        tree = panel.tree
        cur = tree.currentIndex()
        if not cur.isValid():
            # 커서 없음(= 패널 폴더) — ↓ 는 첫 항목, ↑ 는 마지막 항목부터
            root = tree.rootIndex()
            rows = tree.model().rowCount(root)
            new = tree.model().index(0 if direction > 0 else rows - 1, 0, root) if rows else QModelIndex()
        else:
            new = tree.indexBelow(cur) if direction > 0 else tree.indexAbove(cur)
        if new.isValid():
            tree.selectionModel().setCurrentIndex(new, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            tree.scrollTo(new)
        else:
            # 맨 위·맨 아래에 닿았거나 폴더가 비었으면 → 이전·다음 타겟 패널로
            self.left.select_next(-1 if direction < 0 else +1)

    # --- settings ---
    def _settings(self) -> QSettings:
        return QSettings(APP_ORG, APP_NAME)

    def _load_settings(self):
        s = self._settings()
        geo = s.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        main_state = s.value("mainSplitterV3")
        if main_state:
            self.main_splitter.restoreState(main_state)
        else:
            # 첫 실행 — 소스 62 : 타겟 38
            w = max(self.width(), 1000)
            self.main_splitter.setSizes([int(w * 0.62), int(w * 0.38)])
        right_state = s.value("rightSplitter")
        if right_state:
            self.right_splitter.restoreState(right_state)
        source_path = PLATFORM.sanitize_path(s.value("sourcePath"), allow_home=True)
        # CLI 인자가 있으면 세션 경로 대신 그 경로로 연다. 같은 검증을 태워
        # 쓸 수 없는 경로(없음·파일·미마운트)면 세션 경로로 폴백.
        if self._cli_source:
            cli_path = PLATFORM.sanitize_path(self._cli_source, allow_home=False)
            if cli_path:
                source_path = cli_path
            else:
                self._flash(f"열 수 없는 경로 — 지난 세션 경로로 폴백: {self._cli_source}")
        self.source_tree.set_root_path(source_path)
        target_paths = s.value("targetPaths", []) or []
        if isinstance(target_paths, str):
            target_paths = [target_paths]
        if self._cli_targets:
            target_paths = self._cli_targets
        for p in target_paths:
            sp = PLATFORM.sanitize_path(p, allow_home=False)
            if sp:
                self.left.add_panel(sp)
        if self._cli_cursor_file:
            self._cursor_on_file(self._cli_cursor_file, verify=3)  # 시작 때만 재확인 — 사용 중엔 커서를 뺏지 않게

    def _cursor_on_file(self, file_path: str, tries: int = 20, verify: int = 0):
        """source 트리에서 특정 파일에 커서를 놓는다 ("open with" 용도).

        QFileSystemModel 은 디렉터리를 비동기로 읽으므로 set_root_path 직후엔
        인덱스가 아직 없다 → 나올 때까지 50ms 간격 재시도 (최대 1초).
        """
        if not os.path.isfile(file_path):
            return
        src = self._right_fs.index(file_path)
        view = self._proxy.mapFromSource(src) if self._proxy else src
        if src.isValid() and view.isValid():
            self.source_tree.selectionModel().setCurrentIndex(
                view, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
            )
            self.source_tree.scrollTo(view)
            self.source_tree.setFocus()
            # 디렉터리 읽기 도중 정렬이 바뀌면 커서가 「줄 번호」로 남아 옆 파일로 밀린다 →
            # 잠시 뒤 실제 파일과 대조해 어긋났으면 다시 놓는다 (최대 3회)
            if verify > 0:
                QTimer.singleShot(250, lambda: self._recheck_cursor(file_path, verify - 1))
            return
        if tries > 0:
            QTimer.singleShot(50, lambda: self._cursor_on_file(file_path, tries - 1, verify))

    def _recheck_cursor(self, file_path: str, verify: int):
        if not os.path.isfile(file_path):
            return
        if self.source_tree.current_path() != file_path:
            self._cursor_on_file(file_path, 20, verify)
        elif verify > 0:
            QTimer.singleShot(250, lambda: self._recheck_cursor(file_path, verify - 1))

    def closeEvent(self, ev):
        s = self._settings()
        s.setValue("geometry", self.saveGeometry())
        s.setValue("mainSplitterV3", self.main_splitter.saveState())
        s.setValue("rightSplitter", self.right_splitter.saveState())
        cur_path = self.source_tree.current_root_path()
        # Don't persist a temp-extracted archive path — fall back to archive's parent
        if _norm_key(cur_path) in self._extracted:
            cur_path = os.path.dirname(self._extracted[_norm_key(cur_path)])
        s.setValue("sourcePath", PLATFORM.sanitize_path(cur_path, allow_home=True))
        s.setValue("targetPaths", [p for p in (PLATFORM.sanitize_path(t, allow_home=False)
                                              for t in self.left.panel_paths()) if p])
        self._cleanup_extracted()
        super().closeEvent(ev)

    # --- source tree preview ---
    def _on_source_current_changed(self, current: QModelIndex, _prev: QModelIndex):
        if not current.isValid():
            self.preview.load(None)
            return
        src = self._proxy.mapToSource(current)
        path = self._right_fs.filePath(src)
        if os.path.isfile(path):
            self.preview.load(path)

    # --- global key dispatch ---
    def eventFilter(self, obj, ev):
        # Per-widget arrow key interception. Arrows always operate on the
        # TARGET (오른쪽) regardless of focus — source(왼쪽) uses WASD/Q/E.
        if ev.type() == QEvent.KeyPress and isinstance(ev, QKeyEvent):
            if QApplication.activeModalWidget() is not None:
                return super().eventFilter(obj, ev)
            if self._fullscreen_open_now():
                return self._fullscreen.handle_key(ev)   # 전체화면 중: ←/→·A/D 넘김, Esc 등 닫기, 나머지 차단
            nav_widgets = getattr(self, "_image_nav_widgets", set())
            if obj in nav_widgets:
                key = ev.key()
                if key == Qt.Key_Left and ev.modifiers() & Qt.ShiftModifier \
                        and self._return_key in ("left", "both"):
                    self._return_to_source()
                    return True
                if key == Qt.Key_Left:
                    self._target_up()
                    return True
                if key == Qt.Key_Right:
                    self._target_enter()
                    return True
            if self._handle_key(ev):
                return True
        return super().eventFilter(obj, ev)

    def _handle_key(self, ev: QKeyEvent) -> bool:
        # 모달 대화상자(충돌·이름변경·새 폴더)가 떠 있으면 키를 넘긴다 —
        # Space/Enter/글자 키가 대화상자 대신 본창 동작으로 새지 않도록
        if QApplication.activeModalWidget() is not None:
            return False
        # 같은 키(키+타임스탬프)가 두 번 오면 무시 — 맥은 한 키를 창·위젯에 두 번 전달하고,
        # 대화상자가 닫힌 뒤 큐에 남은 키가 다시 온다. 🔴 「처리한 키만」 기록한다 — 처리 안 한 키까지
        # 기록하면 두 번째 전달(= 실제 입력창으로 가는 것)이 버려져 필터 칸에 글자가 안 들어간다 (2026-10-19)
        key_ts = (ev.key(), int(ev.timestamp()))
        if not hasattr(self, "_seen_key_ts"):
            self._seen_key_ts = set()
        if key_ts in self._seen_key_ts:
            return True
        handled = self._handle_key_once(ev)
        if handled:
            if len(self._seen_key_ts) > 200:
                self._seen_key_ts.clear()
            self._seen_key_ts.add(key_ts)
        return handled

    def _handle_key_once(self, ev: QKeyEvent) -> bool:
        # Don't hijack typing in the filter edit
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit) and focus is self.filter_edit:
            if ev.key() in (Qt.Key_Escape, Qt.Key_Home):
                self._clear_filter()
                return True
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
                # 필터는 걸어 둔 채 목록으로 — 이어서 W/S·Space 로 분류
                self.source_tree.setFocus()
                return True
            return False   # Backspace·글자 입력은 필터 칸이 처리

        key = ev.key()
        mods = ev.modifiers()

        # Ctrl+Z — undo
        if key == Qt.Key_Z and mods & Qt.ControlModifier:
            self._undo_last()
            return True

        # ↑/↓ — 오른손 = 타겟 커서 (포커스 무관), Shift+↑/↓ = 타겟 패널 이동 (PgUp/PgDn 과 같음)
        if key in (Qt.Key_Up, Qt.Key_Down) and mods & Qt.ShiftModifier:
            self.left.select_next(-1 if key == Qt.Key_Up else +1)
            return True
        if key in (Qt.Key_Up, Qt.Key_Down):
            self._move_target_cursor(-1 if key == Qt.Key_Up else +1)
            return True

        # F2 / F7 / Shift+N / Delete / I / Slash
        if key == Qt.Key_F2:
            self._rename_selected()
            return True
        if key == Qt.Key_F7 or (key == Qt.Key_N and mods & Qt.ShiftModifier):
            self._new_folder()
            return True
        if key == Qt.Key_Delete:
            self._delete_selected()
            return True
        if key == Qt.Key_I and not (mods & (Qt.ControlModifier | Qt.AltModifier)):
            self.preview.toggle_exif()
            return True
        if key == Qt.Key_V and not (mods & (Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier)):
            self._view_fullscreen()        # V = 커서의 이미지(폴더면 첫 이미지) 전체화면
            return True
        if key == Qt.Key_Slash:
            self.filter_edit.show()
            self.filter_edit.setFocus()
            self.filter_edit.selectAll()
            return True

        if key == Qt.Key_Home and self.filter_edit.isVisible():
            self._clear_filter()
            return True
        if key == Qt.Key_F1:
            self._show_help()
            return True

        plain = not (mods & (Qt.ControlModifier | Qt.AltModifier))

        # 왼손 = 왼쪽 source — W/A/S/D 를 화살표처럼 (0.6.3, 사용자 결정 2026-10-22):
        #   W/S 커서 · A 상위 폴더 · D 폴더 진입 (타겟 쪽 ←/→ 와 짝) · Q/E 이전/다음 사진(폴더 건너뜀)
        if plain and key == Qt.Key_W:
            self._move_source_cursor(-1)
            return True
        if plain and key == Qt.Key_S:
            self._move_source_cursor(+1)
            return True
        if plain and key == Qt.Key_A:
            self._source_up()
            return True
        if plain and key == Qt.Key_D:
            self._source_enter()
            return True
        if plain and key == Qt.Key_Q:
            self._goto_sibling_image(-1)
            return True
        if plain and key == Qt.Key_E:
            self._goto_sibling_image(+1)
            return True

        # 왼손 액션: C 복사 · Space/M 이동 (source → Active 타겟)
        if plain and key == Qt.Key_C:
            self._run_file_op("copy")
            return True
        if plain and key in (Qt.Key_Space, Qt.Key_M):
            self._run_file_op("move")
            return True

        # 오른손 = 오른쪽 타겟: PgUp/PgDn 패널 전환 · 1~9(숫자패드 포함) 직접 선택
        #                     Backspace/Enter = ←/→ 와 같음 (상위 / 진입)
        if key == Qt.Key_PageUp:
            self.left.select_next(-1)
            return True
        if key == Qt.Key_PageDown:
            self.left.select_next(+1)
            return True
        # Shift+숫자 = 그 패널로 바로 이동. Qt 는 Shift+1 을 Key_Exclam 으로 준다(미국·한국 배열)
        if key in _SHIFT_DIGIT_KEYS:
            self._send_to_panel(_SHIFT_DIGIT_KEYS[key])
            return True
        if Qt.Key_1 <= key <= Qt.Key_9 and mods & Qt.ShiftModifier:
            self._send_to_panel(key - Qt.Key_1)
            return True
        if Qt.Key_1 <= key <= Qt.Key_9:
            self.left.select_at(key - Qt.Key_1)
            return True
        if PLATFORM.CMD_BACKSPACE_DELETE and key == Qt.Key_Backspace and (mods & (Qt.ControlModifier | Qt.MetaModifier)):
            self._delete_selected()       # 맥 Cmd+Backspace = 휴지통 (Qt 는 Cmd 를 ControlModifier 로 준다)
            return True
        if key == Qt.Key_Backspace and mods & Qt.ShiftModifier and self._return_key in ("backspace", "both"):
            self._return_to_source()
            return True
        if key == Qt.Key_Backspace:
            self._target_up()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self._enter_action in ("move", "copy"):
                self._run_file_op(self._enter_action)
            else:
                self._target_enter()
            return True

        return False

    def _source_up(self):
        """source 상위 폴더. 압축 추출본 안이면 압축 원본의 부모로."""
        cur_root = self.source_tree.current_root_path()
        if _norm_key(cur_root) in self._extracted:
            archive_parent = os.path.dirname(self._extracted[_norm_key(cur_root)])
            self.source_tree.set_root_path(archive_parent)
        else:
            self.source_tree.go_up()

    def _source_enter(self):
        """source 커서의 폴더 진입 / 압축파일 추출 진입."""
        idx = self.source_tree.currentIndex()
        if not idx.isValid():
            return
        src = self._proxy.mapToSource(idx)
        path = self._right_fs.filePath(src)
        if self._right_fs.isDir(src):
            self.source_tree.enter_or_expand()
        elif self._is_archive(path):
            self._enter_archive(path)

    def _target_up(self):
        p = self.left.active_panel()
        if p:
            p.tree.go_up()

    def _target_enter(self):
        p = self.left.active_panel()
        if p:
            p.tree.enter_or_expand()

    def _send_to_panel(self, idx0: int):
        """Shift+숫자 — 그 번호 패널을 고르고 바로 이동 (숫자 → Space 를 한 번에)."""
        if self.left.select_at(idx0):
            self._run_file_op("move")
        else:
            self._flash(f"{idx0 + 1}번 타겟 패널이 없습니다.")

    # 설정 항목 — (설정 키, 제목, 기본값, [(값, 라벨, 설명)])
    _SETTINGS_SPEC = [
        ("enterAction", "Enter 키 동작", "move", [
            ("enter", "폴더 진입", "타겟 패널에서 커서의 하위 폴더로 들어갑니다 (→ 와 같음)"),
            ("move", "이동", "고른 사진을 활성 타겟 폴더로 옮깁니다 (Space 와 같음) — 오른손만으로 분류"),
            ("copy", "복사", "고른 사진을 활성 타겟 폴더에 복사합니다 (C 와 같음) — 원본은 그대로"),
        ]),
        ("returnKey", "소스로 되돌리기 키", "left", [
            ("left", "Shift + ←", "타겟 커서의 파일을 왼쪽 소스 폴더로 되돌립니다 (이동, 되돌리기 키로 취소)"),
            ("backspace", "Shift + Backspace", "타겟 커서의 파일을 왼쪽 소스 폴더로 되돌립니다 (이동, 되돌리기 키로 취소)"),
            ("both", "둘 다 사용", "Shift + ← 와 Shift + Backspace 어느 쪽을 눌러도 되돌립니다"),
        ]),
        ("fullscreenInfo", "전체화면 정보 보기", "5", [
            ("show", "계속 보기", "전체화면에서 파일명·번호·크기 정보창을 계속 띄웁니다 (Tab 으로 감출 수 있음)"),
            ("1", "1초 후 숨김", "사진을 넘길 때마다 1초만 보여 주고 감춥니다 (Tab 으로 다시 보기)"),
            ("5", "5초 후 숨김", "사진을 넘길 때마다 5초만 보여 주고 감춥니다 (Tab 으로 다시 보기)"),
            ("10", "10초 후 숨김", "사진을 넘길 때마다 10초만 보여 주고 감춥니다 (Tab 으로 다시 보기)"),
            ("hide", "안 보기", "정보창을 띄우지 않습니다 (전체화면에서 Tab 을 누르면 그때만 보임)"),
        ]),
        ("fullscreenAtEnd", "전체화면 끝에서 (마지막/처음 이미지에서 넘길 때)", "folder", [   # 기본 = 폴더 넘김 (0.6.4, 사용자 결정)
            ("wrap", "다시 처음으로 돌아가기", "마지막 다음은 첫 이미지로 갑니다 (「처음 이미지입니다」 표시)"),
            ("folder", "다음/이전 폴더로 넘어가기", "같은 상위 폴더 안의 다음/이전 폴더(이미지 있는)로 넘어가고, 그 트리(소스 또는 타겟 패널)도 그 폴더로 옮깁니다"),
            ("stop", "아무것도 하지 않음", "끝에서 멈추고 「마지막/처음 이미지입니다」만 표시합니다"),
        ]),
    ]

    def _load_prefs(self):
        st = self._settings()
        for key, _title, default, choices in self._SETTINGS_SPEC:
            v = st.value(key, default)
            if v not in [c[0] for c in choices]:
                v = default
            setattr(self, "_pref_" + key, v)
        self._enter_action = self._pref_enterAction
        self._return_key = self._pref_returnKey

    def _show_settings(self):
        """설정 창 — 라디오 버튼, 마우스를 올리면 설명. 고르는 즉시 적용·저장."""
        dlg = QDialog(self)
        dlg.setWindowTitle("설정")
        lay = QVBoxLayout(dlg)
        st = self._settings()
        for key, title, _default, choices in self._SETTINGS_SPEC:
            box = QGroupBox(title)
            bl = QVBoxLayout(box)
            group = QButtonGroup(box)
            cur = getattr(self, "_pref_" + key)
            for value, label, tip in choices:
                rb = QRadioButton(label)
                rb.setToolTip(tip)
                rb.setChecked(value == cur)
                group.addButton(rb)
                bl.addWidget(rb)

                def _pick(checked, k=key, v=value, lab=label, t=title):
                    if not checked:
                        return
                    setattr(self, "_pref_" + k, v)
                    st.setValue(k, v)
                    self._enter_action = self._pref_enterAction
                    self._return_key = self._pref_returnKey
                    self._flash(f"{t}: {lab}")
                rb.toggled.connect(_pick)
            lay.addWidget(box)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        btns.button(QDialogButtonBox.Close).setText("닫기")
        lay.addWidget(btns)
        dlg.setMinimumWidth(360)
        dlg.exec()

    def _build_menu(self):
        """메뉴 막대 — 설정…(맥=앱 메뉴 Cmd+, / 그 외=파일 메뉴) · 도움말(단축키 F1 · 정보)."""
        self._load_prefs()
        # 설정… — 맥은 앱 메뉴(ImageManager > 설정…, Cmd+,)로 자동 이동, 그 외는 파일 메뉴
        act_pref = QAction("설정…", self)
        act_pref.setMenuRole(QAction.PreferencesRole)
        act_pref.setShortcut(QKeySequence.Preferences if not QKeySequence(QKeySequence.Preferences).isEmpty()
                             else QKeySequence("Ctrl+,"))
        act_pref.triggered.connect(self._show_settings)
        if not PLATFORM.APP_MENU:
            # 리눅스·윈도우 — 「파일 > 설정… / 종료」
            mfile = self.menuBar().addMenu("파일")
            mfile.addAction(act_pref)
            mfile.addSeparator()
            act_quit = QAction("종료", self)
            act_quit.setShortcut(QKeySequence("Ctrl+Q"))
            act_quit.triggered.connect(self.close)
            mfile.addAction(act_quit)
        m = self.menuBar().addMenu("도움말")
        act_keys = QAction("단축키 (F1)", self)
        act_keys.triggered.connect(self._show_help)
        m.addAction(act_keys)
        m.addSeparator()
        act_about = QAction("정보", self)
        act_about.setMenuRole(QAction.NoRole)
        act_about.triggered.connect(self._show_about)
        m.addAction(act_about)
        if PLATFORM.APP_MENU:
            # 맥 — 앱 메뉴(ImageManager ▸)로 자동 이동: 「ImageManager 정보」·「설정… ⌘,」
            act_about_app = QAction(f"{APP_NAME} 정보", self)
            act_about_app.setMenuRole(QAction.AboutRole)
            act_about_app.triggered.connect(self._show_about)
            m.addAction(act_about_app)
            m.addAction(act_pref)

    def _show_about(self):
        """정보 — 버전·개발자·사이트·소스 주소."""
        box = QMessageBox(self)
        box.setWindowTitle(f"{APP_NAME} 정보")
        box.setIconPixmap(self.windowIcon().pixmap(64, 64))
        box.setTextFormat(Qt.RichText)
        box.setTextInteractionFlags(Qt.TextBrowserInteraction)
        box.setText(
            f"<h3>{APP_NAME} {APP_VERSION}</h3>"
            "<p>키보드로 사진을 넘겨 보며 폴더로 분류하는 듀얼 패널 이미지 관리자</p>"
            f"<p>개발: {APP_AUTHOR}<br>"
            f'사이트: <a href="{APP_SITE}">{APP_SITE}</a><br>'
            f'소스: <a href="{APP_REPO}">{APP_REPO}</a></p>'
            f"<p>무료 · {APP_LICENSE} — 다시 배포할 때는 NOTICE 파일을 함께</p>"
        )
        for lbl in box.findChildren(QLabel):
            lbl.setOpenExternalLinks(True)
        box.exec()

    def _clear_filter(self):
        """필터 해제 — 글자 지우고 칸 숨기고 소스 목록으로 포커스."""
        self.filter_edit.clear()
        self.filter_edit.hide()
        self.source_tree.setFocus()
        self._flash("필터 해제")

    def _show_help(self):
        """F1 — 키보드 배치도 (images/keymap.png)."""
        # 소스 실행 = 레포의 images/, 빌드(.app) 실행 = 번들 안 images/ (_MEIPASS)
        cands = [Path(__file__).resolve().parent.parent / "images" / "keymap.png"]
        if getattr(sys, "_MEIPASS", None):
            cands.insert(0, Path(sys._MEIPASS) / "images" / "keymap.png")
        img = next((c for c in cands if c.exists()), cands[-1])
        dlg = QDialog(self)
        dlg.setWindowTitle("단축키 — F1")
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        pm = QPixmap(str(img))
        if pm.isNull():
            lbl.setText(f"배치도 이미지를 찾지 못함: {img}")
        else:
            lbl.setPixmap(pm.scaledToWidth(min(pm.width(), 1400), Qt.SmoothTransformation))
        lay.addWidget(lbl)
        dlg.exec()

    def _goto_sibling_image(self, direction: int):
        """Move source-tree selection to prev/next IMAGE in the current folder
        (skipping folders and non-image files). Wraps within the folder."""
        root = self.source_tree.rootIndex()
        if not root.isValid():
            return
        proxy = self._proxy
        fs = self._right_fs
        rows = proxy.rowCount(root)
        if rows == 0:
            return

        image_view_rows: list[int] = []
        for r in range(rows):
            v_idx = proxy.index(r, 0, root)
            s_idx = proxy.mapToSource(v_idx)
            if fs.isDir(s_idx):
                continue
            name = fs.fileName(s_idx)
            ext = os.path.splitext(name)[1].lower()
            if ext in IMAGE_EXTS:
                image_view_rows.append(r)

        if not image_view_rows:
            return

        cur = self.source_tree.currentIndex()
        cur_row = cur.row() if cur.isValid() and cur.parent() == root else -1
        if cur_row in image_view_rows:
            pos = image_view_rows.index(cur_row)
            new_pos = (pos + direction) % len(image_view_rows)
        else:
            new_pos = 0 if direction >= 0 else len(image_view_rows) - 1

        target_row = image_view_rows[new_pos]
        target_idx = proxy.index(target_row, 0, root)
        self.source_tree.selectionModel().setCurrentIndex(
            target_idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
        )
        self.source_tree.scrollTo(target_idx)

    def _pick_source_folder(self):
        """메인 탐색기 폴더 선택 다이얼로그 — 헤더의 📁 버튼."""
        start = self.source_tree.current_root_path() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "메인 탐색기 폴더 선택", start)
        if folder:
            self.source_tree.set_root_path(folder)

    def _select_source_current(self):
        """source 트리의 currentIndex 를 selection 에 동기화. 화살표 이동 후
        + 워커 완료 후 호출 — preview 와 selection 이 항상 같이 가도록."""
        cur = self.source_tree.currentIndex()
        if cur.isValid():
            self.source_tree.selectionModel().setCurrentIndex(
                cur, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
            )

    # --- file ops ---
    def _run_file_op(self, kind: str):
        srcs = self.source_tree.selected_paths()
        srcs = [s for s in srcs if os.path.exists(s)]
        if not srcs:
            # Fallback: selection 이 비어도 preview 되고 있는 currentIndex 파일을 대상으로.
            # M/Del 직후 다음 행으로 자동 이동된 경우, focus 가 왼쪽인 채 다시 M 눌러도 동작.
            cur = self.source_tree.current_path()
            if cur and os.path.isfile(cur):
                srcs = [cur]
        if not srcs:
            self._flash("소스에서 선택된 파일이 없습니다.")
            return
        target = self.left.active_panel()
        if target is None:
            QMessageBox.warning(
                self, "활성 타겟 없음",
                "활성 타겟 패널이 없습니다. 오른쪽 아래 [+ 타겟 폴더 추가] 버튼으로 추가하세요."
            )
            return
        # active panel tree 안에서 폴더에 cursor 있으면 그 폴더를 destination 으로
        # (들어가지 않은 채 선택만 한 상태 — 회색 포커스 — 도 포함)
        dst_dir = target.path()
        cur = target.tree.current_path()
        if cur and cur != dst_dir and os.path.isdir(cur):
            dst_dir = cur

        # === 핵심: 폴더가 없거나 비어있다고 실패하면 안 됨 ===
        if not dst_dir:
            QMessageBox.warning(self, "타겟 오류", "활성 타겟에 경로가 없습니다.")
            return
        if not os.path.isdir(dst_dir):
            reply = QMessageBox.question(
                self, "타겟 폴더 없음",
                f"타겟 폴더가 없습니다:\n{dst_dir}\n\n만들까요?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            try:
                os.makedirs(dst_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "폴더 만들기 실패", str(e))
                return

        ops = self._resolve_ops(srcs, dst_dir, kind)
        if ops is None:
            return
        if not ops:
            self._flash("작업할 항목이 없습니다.")
            return
        self._advance_to = (
            self._next_source_file({op.src for op in ops}) if kind == "move" else None
        )
        self._start_worker(ops)

    def _resolve_ops(self, srcs: list, dst_dir: str, kind: str) -> Optional[list]:
        """같은 이름 충돌을 미리 물어 FileOp 목록을 만든다. 「모두 취소」면 None."""
        # Pre-resolve conflicts (ask user before starting worker)
        ops: list[FileOp] = []
        apply_all: Optional[str] = None  # 'overwrite' | 'skip' | 'rename'
        multi = len(srcs) > 1
        for s in srcs:
            base = os.path.basename(s.rstrip("/"))
            dst = os.path.join(dst_dir, base)
            if os.path.exists(dst):
                # Self-copy guard
                if os.path.abspath(s) == os.path.abspath(dst):
                    continue
                choice = apply_all
                if choice is None:
                    choice, remember = self._ask_conflict(s, dst, multi)
                    if choice == "cancel":
                        return None
                    if remember:
                        apply_all = choice
                if choice == "skip":
                    continue
                if choice == "rename":
                    dst = _unique_path(dst)
                # 'overwrite' → use dst as-is (worker will overwrite)
            ops.append(FileOp(kind=kind, src=s, dst=dst))

        return ops

    def _return_to_source(self):
        """Shift+← — 타겟 커서의 파일을 왼쪽 소스 폴더로 되돌린다(이동). Ctrl/Cmd+Z 로 취소 가능."""
        panel = self.left.active_panel()
        if panel is None:
            return
        path = panel.tree.current_path()
        # 파일만 — 폴더째 되돌리면 분류해 둔 묶음이 통째로 옮겨진다
        if not path or not os.path.isfile(path):
            self._flash("타겟에서 되돌릴 파일에 커서를 두세요 (↑/↓). 폴더는 되돌리지 않습니다.")
            return
        dst_dir = self.source_tree.current_root_path()
        if not dst_dir or not os.path.isdir(dst_dir):
            self._flash("소스 폴더가 올바르지 않습니다.")
            return
        # 소스가 압축파일을 임시로 푼 폴더면 금지 — 앱을 닫을 때 임시 폴더와 함께 지워진다
        if _norm_key(os.path.realpath(dst_dir)).startswith(_norm_key(str(EXTRACT_BASE))):
            self._flash("소스가 압축파일 안(임시 폴더)이라 되돌리지 않습니다 — 압축 밖 폴더로 나간 뒤 다시.")
            return
        if os.path.dirname(os.path.abspath(path)) == os.path.abspath(dst_dir):
            self._flash("이미 소스 폴더에 있는 파일입니다.")
            return
        ops = self._resolve_ops([path], dst_dir, "move")
        if not ops:
            return
        self._returning = True
        self._start_worker(ops)

    def _next_source_file(self, skip: set) -> Optional[str]:
        """이동 대상(skip)을 뺀 다음 파일 경로 (아래 방향만)."""
        tree = self.source_tree
        cur = tree.currentIndex()
        if not cur.isValid():
            return None
        # 아래로만 찾는다. 위로 거슬러 올라가면 Space 연타 시 앞 파일들이
        # 의도 없이 딸려 간다 → 마지막이면 None (호출 측이 선택을 비움)
        idx = tree.indexBelow(cur)
        while idx.isValid():
            p = self._right_fs.filePath(self._proxy.mapToSource(idx))
            if p not in skip and os.path.isfile(p):
                return p
            idx = tree.indexBelow(idx)
        return None

    def _advance_source_after_move(self, done_ops: list):
        """M 완료 후 — 옮긴 파일을 목록에서 숨기고 기억해 둔 다음 파일로 커서 이동."""
        moved = [op.src for op in done_ops if op.kind == "move"]
        if not moved:
            return
        self._proxy.mark_gone(moved)
        nxt = getattr(self, "_advance_to", None)
        self._advance_to = None
        view = self._proxy.mapFromSource(self._right_fs.index(nxt)) if nxt else QModelIndex()
        if not view.isValid():
            # 마지막 파일이었음 — 행 삭제 시 Qt 가 current 를 위 행으로 옮기므로
            # 명시적으로 비운다. 다음 M/Space 는 「선택 없음」으로 아무것도 안 옮김
            self.source_tree.selectionModel().clear()
            self.source_tree.selectionModel().setCurrentIndex(
                QModelIndex(), QItemSelectionModel.Clear
            )
            self.preview.load(None)
            self._flash("마지막 파일이었습니다 — 아래에 남은 파일 없음 (A/W 로 위 파일 선택)")
            return
        if view.isValid():
            self.source_tree.selectionModel().setCurrentIndex(
                view, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
            )
            self.source_tree.scrollTo(view)

    def _ask_conflict(self, src: str, dst: str, multi: bool) -> tuple[str, bool]:
        """Show conflict dialog. Returns (choice, apply_to_all).
        choice: 'overwrite' | 'skip' | 'rename' | 'cancel'"""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("같은 이름 파일 존재")
        box.setText(f"이미 존재합니다:  {os.path.basename(dst)}")
        try:
            src_sz = os.path.getsize(src)
            dst_sz = os.path.getsize(dst)
            box.setInformativeText(
                f"위치: {dst}\n"
                f"원본 크기: {src_sz:,} bytes\n"
                f"기존 크기: {dst_sz:,} bytes"
            )
        except OSError:
            box.setInformativeText(f"위치: {dst}")
        overwrite_btn = box.addButton("덮어쓰기", QMessageBox.AcceptRole)
        skip_btn = box.addButton("건너뛰기", QMessageBox.RejectRole)
        rename_btn = box.addButton("이름 바꾸기 (N)", QMessageBox.ActionRole)
        cancel_btn = box.addButton("모두 취소", QMessageBox.DestructiveRole)
        box.setDefaultButton(skip_btn)
        apply_cb: Optional[QCheckBox] = None
        if multi:
            apply_cb = QCheckBox("나머지에도 적용")
            box.setCheckBox(apply_cb)
        box.exec()
        clicked = box.clickedButton()
        remember = apply_cb.isChecked() if apply_cb is not None else False
        if clicked is overwrite_btn:
            return ("overwrite", remember)
        if clicked is rename_btn:
            return ("rename", remember)
        if clicked is cancel_btn:
            return ("cancel", False)
        return ("skip", remember)

    def _start_worker(self, ops: list[FileOp]):
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "작업 중", "다른 파일 작업이 진행 중입니다.")
            return
        self._worker = FileOpWorker(ops, self)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(ops))
        self.progress.setValue(0)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished_ok.connect(self._on_worker_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_worker_progress(self, done, total, current):
        self.progress.setValue(done)
        self.status_label.setText(f"[{done}/{total}] {os.path.basename(current)}")

    def _on_worker_done(self, done_ops: list):
        self.progress.setVisible(False)
        self.status_label.setText(f"완료: {len(done_ops)}개")
        if done_ops:
            self._undo_stack.append(done_ops)
        if getattr(self, "_returning", False):
            # Shift+← 되돌리기 — 돌아온 파일을 소스에 다시 보이게 하고 그 파일에 커서
            self._returning = False
            panel = self.left.active_panel()
            if panel is not None:
                panel._set_mini(None)
            self._proxy.invalidateFilter()
            if done_ops:
                self._cursor_on_file(done_ops[-1].dst)
                self._flash(f"소스로 되돌림: {os.path.basename(done_ops[-1].dst)}")
            return
        # 보낸 사진을 그 타겟 패널 미니 프리뷰에 — 커서는 그대로(하위 폴더 지정에 쓰이므로)
        last = next((op for op in reversed(done_ops) if op.kind in ("copy", "move")), None)
        panel = self.left.active_panel()
        if last and panel is not None:
            panel._set_mini(last.dst)
        # M(이동) 후 — 기억해 둔 다음 파일로 커서 이동 (selection 까지)
        self._advance_source_after_move(done_ops)

    def _on_worker_error(self, msg: str):
        self._advance_to = None
        self._returning = False
        self.progress.setVisible(False)
        self.status_label.setText("오류.")
        QMessageBox.critical(self, "파일 작업 실패", msg)

    def _undo_last(self):
        if not self._undo_stack:
            self._flash("되돌릴 작업이 없습니다.")
            return
        last = self._undo_stack.pop()
        # Reverse each: move-back for moves; delete copies for copies.
        rev_ops: list[FileOp] = []
        for op in reversed(last):
            try:
                if op.kind == "move":
                    # move back: dst -> src
                    src_dir = os.path.dirname(op.src)
                    if not os.path.isdir(src_dir):
                        os.makedirs(src_dir, exist_ok=True)
                    shutil.move(op.dst, op.src)
                elif op.kind == "copy":
                    if os.path.isdir(op.dst):
                        shutil.rmtree(op.dst)
                    elif os.path.isfile(op.dst):
                        os.remove(op.dst)
                elif op.kind == "trash":
                    if not op.dst:          # 휴지통에서 항목을 못 찾았던 삭제 — 되돌릴 수 없음
                        continue
                    PLATFORM.restore(op.dst, _unique_path(op.src))
                rev_ops.append(op)
            except Exception as e:
                QMessageBox.critical(self, "되돌리기 실패", f"{op}\n{e}")
                break
        self.status_label.setText(f"되돌림: {len(rev_ops)}개")
        # 되돌려서 사라진 파일을 보여 주던 미니 프리뷰는 비운다
        for p in self.left._panels:
            if p._mini_path and not os.path.exists(p._mini_path):
                p._set_mini(None)
        # 이동 Undo — 숨겨 둔 행을 다시 보이게 하고 되돌린 파일에 커서
        self._proxy.invalidateFilter()
        back = [op.src for op in rev_ops if op.kind == "move"]
        if back:
            self._cursor_on_file(back[-1])

    # --- aux file actions ---
    def _active_tree_and_dir(self) -> tuple[Optional[PathTreeView], Optional[str]]:
        """Return (tree, current dir) — prefers source tree, then active target."""
        focus = QApplication.focusWidget()
        if focus is self.source_tree or self.source_tree.hasFocus():
            return self.source_tree, self.source_tree.current_root_path()
        tgt = self.left.active_panel()
        if tgt and (focus is tgt.tree or tgt.tree.hasFocus()):
            return tgt.tree, tgt.tree.current_root_path()
        # default to source
        return self.source_tree, self.source_tree.current_root_path()

    def _new_folder(self):
        tree, base = self._active_tree_and_dir()
        if not base or not os.path.isdir(base):
            QMessageBox.warning(self, "새 폴더", "현재 폴더가 올바르지 않습니다.")
            return
        name, ok = QInputDialog.getText(self, "새 폴더", "폴더 이름:")
        if not ok or not name.strip():
            return
        new_path = os.path.join(base, name.strip())
        try:
            os.makedirs(new_path, exist_ok=False)
            self.status_label.setText(f"새 폴더: {new_path}")
        except FileExistsError:
            QMessageBox.warning(self, "새 폴더", "같은 이름의 폴더가 이미 있습니다.")
        except Exception as e:
            QMessageBox.critical(self, "새 폴더", str(e))

    def _rename_selected(self):
        tree, _ = self._active_tree_and_dir()
        if tree is None:
            return
        path = tree.current_path()
        if not path:
            return
        base = os.path.basename(path.rstrip("/"))
        new_name, ok = QInputDialog.getText(self, "이름 변경", "새 이름:", text=base)
        if not ok or not new_name.strip() or new_name == base:
            return
        new_path = os.path.join(os.path.dirname(path), new_name.strip())
        try:
            os.rename(path, new_path)
            self.status_label.setText(f"이름 변경 → {new_name}")
        except Exception as e:
            QMessageBox.critical(self, "이름 변경", str(e))

    def _delete_selected(self):
        # 재진입 막기 — Del 한 번이 어떤 경로로 두 번 들어오는 경우(맥 PyInstaller 실측) 첫 호출이 끝날 때까지 무시
        if getattr(self, "_in_delete", False):
            return
        self._in_delete = True
        try:
            self._delete_selected_impl()
        finally:
            self._in_delete = False

    def _delete_selected_impl(self):
        tree, _ = self._active_tree_and_dir()
        if tree is None:
            return
        paths = tree.selected_paths()
        if not paths:
            self.status_label.setText("선택된 항목이 없습니다.")
            return
        if send2trash is None:
            QMessageBox.critical(
                self, "삭제 불가",
                "send2trash 가 설치되지 않아 삭제하지 않습니다(영구 삭제 방지).\n"
                "설치: pip install send2trash",
            )
            return
        if not PLATFORM.confirm_delete(self, paths):      # 맥: 미리보기 확인 창 / 그 외: 바로
            return

        trash_ops: list[FileOp] = []
        for p in paths:
            try:
                token = PLATFORM.trash(p)                   # 되돌리기용 표식 (못 찾으면 "")
            except Exception as e:
                logger.exception("삭제 실패")
                QMessageBox.critical(self, "삭제 실패", f"{p}\n{e}")
                break
            trash_ops.append(FileOp(kind="trash", src=p, dst=token))

        if trash_ops:
            self._undo_stack.append(trash_ops)
        self.status_label.setText(
            f"휴지통으로: {len(trash_ops)}개"
            + ("" if all(op.dst for op in trash_ops) else "  (일부 항목 Undo 불가)")
        )

    def _flash(self, msg: str):
        self.status_label.setText(msg)

    # --- archive support ---
    @staticmethod
    def _is_archive(path: str) -> bool:
        return (
            os.path.isfile(path)
            and os.path.splitext(path)[1].lower() in ARCHIVE_EXTS
        )

    def _enter_archive(self, archive_path: str):
        try:
            st = os.stat(archive_path)
            key = hashlib.sha1(
                f"{archive_path}|{st.st_size}|{st.st_mtime_ns}".encode()
            ).hexdigest()[:12]
        except OSError as e:
            QMessageBox.critical(self, "압축파일", str(e))
            return
        EXTRACT_BASE.mkdir(parents=True, exist_ok=True)
        temp_dir = EXTRACT_BASE / f"{Path(archive_path).stem}_{key}"

        if not temp_dir.exists() or not any(temp_dir.iterdir()):
            temp_dir.mkdir(parents=True, exist_ok=True)
            self.status_label.setText(f"압축 푸는 중: {os.path.basename(archive_path)} …")
            QApplication.processEvents()
            try:
                self._extract_archive(archive_path, str(temp_dir))
            except Exception as e:
                shutil.rmtree(temp_dir, ignore_errors=True)
                QMessageBox.critical(
                    self, "Archive extract failed",
                    f"{archive_path}\n\n{type(e).__name__}: {e}",
                )
                return

        self._extracted[_norm_key(str(temp_dir))] = archive_path
        self.source_tree.set_root_path(str(temp_dir))
        self.status_label.setText(
            f"Archive: {os.path.basename(archive_path)}  "
            f"(Backspace to exit)"
        )

    @staticmethod
    def _extract_archive(archive_path: str, dest: str):
        ext = os.path.splitext(archive_path)[1].lower()
        if ext in (".zip", ".cbz"):
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(dest)
        elif ext in (".rar", ".cbr"):
            import rarfile
            with rarfile.RarFile(archive_path) as rf:
                rf.extractall(dest)
        elif ext in (".7z", ".cb7"):
            import py7zr
            with py7zr.SevenZipFile(archive_path, mode="r") as sz:
                sz.extractall(path=dest)
        else:
            raise ValueError(f"Unsupported archive type: {ext}")

    def _cleanup_extracted(self):
        for tmp in list(self._extracted.keys()):
            shutil.rmtree(tmp, ignore_errors=True)
        self._extracted.clear()
        # Also try to remove the base dir if it's empty
        try:
            if EXTRACT_BASE.exists() and not any(EXTRACT_BASE.iterdir()):
                EXTRACT_BASE.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
# 우리가 쓰는 옵션 / Qt 가 값을 하나 더 먹는 옵션.
# 후자를 argparse 에 그냥 넘기면 (`-style fusion`) 뒤 토큰이 위치인자 path 로
# 잘못 잡혀 엉뚱한 폴더가 열린다 → 넘기기 전에 옵션+값을 함께 떼어 둔다.
_OUR_OPTS = {"-t", "--target", "-h", "--help"}
_QT_VALUE_OPTS = {
    "style", "stylesheet", "platform", "platformpluginpath", "platformtheme",
    "plugin", "qmljsdebugger", "qwindowgeometry", "qwindowicon",
    "qwindowtitle", "session", "display", "geometry", "name", "title",
    "visual", "ncols", "im", "inputstyle",
    "bg", "background", "fg", "foreground", "btn", "button",
}


def _split_qt_args(tokens: list[str]) -> tuple[list[str], list[str]]:
    """argv[1:] 를 (우리 인자, Qt 로 넘길 인자) 로 분리."""
    ours: list[str] = []
    qt: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        base = t.split("=", 1)[0]
        if base in _OUR_OPTS:
            ours.append(t)
            if base in ("-t", "--target") and "=" not in t and i + 1 < len(tokens):
                i += 1
                ours.append(tokens[i])
        elif t.startswith("-"):
            qt.append(t)
            if "=" not in t and base.lstrip("-") in _QT_VALUE_OPTS and i + 1 < len(tokens):
                i += 1
                qt.append(tokens[i])
        else:
            ours.append(t)
        i += 1
    return ours, qt


def parse_cli_args(argv: list[str]):
    """시작 폴더·타겟 폴더 인자 파싱.

    Qt 자체 인자(`-style fusion`, macOS Finder 가 붙이는 `-psn_*` 등)와 섞여도
    죽지 않도록 먼저 _split_qt_args 로 갈라내고, 남은 것만 argparse 에 넘긴다.
    혹시 빠진 Qt 옵션이 있어도 parse_known_args 라 그대로 Qt 로 흘려보낸다.

    반환: (source_dir, cursor_file, target_dirs, qt_argv)
      - source_dir   : 왼쪽 source 트리를 열 폴더 (인자 없으면 None → 세션 복원)
      - cursor_file  : 파일 경로를 받은 경우 그 파일 (부모 폴더를 열고 커서 올림)
      - target_dirs  : 오른쪽 타겟 패널 폴더 리스트 (없으면 [] → 세션 복원)
    """
    parser = argparse.ArgumentParser(
        prog="image-manager",
        description="듀얼 패널 이미지 관리자. 인자 없이 실행하면 지난 세션 경로로 열립니다.",
    )
    parser.add_argument(
        "path", nargs="?",
        help="왼쪽 source 트리를 열 폴더. 파일을 주면 그 파일의 부모 폴더를 열고 "
             "해당 파일에 커서를 놓습니다 (open with 용도).",
    )
    parser.add_argument(
        "-t", "--target", action="append", default=[], metavar="DIR",
        help="오른쪽 타겟 패널로 열 폴더. 여러 번 지정 가능.",
    )
    ours, qt_rest = _split_qt_args(argv[1:])
    ns, unknown = parser.parse_known_args(ours)
    qt_rest += unknown

    source_dir = None
    cursor_file = None
    if ns.path:
        p = os.path.abspath(os.path.expanduser(ns.path))
        if os.path.isfile(p):
            cursor_file = p
            source_dir = os.path.dirname(p)
        else:
            source_dir = p

    target_dirs = [os.path.abspath(os.path.expanduser(t)) for t in ns.target]
    return source_dir, cursor_file, target_dirs, [argv[0]] + qt_rest


ICON_SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)


def load_app_icon() -> QIcon:
    """imagemanager/icons/icon_*.png (그림 정본 = tools/generate_icon.py). 빌드(.app/exe)에선 번들 안에서 찾는다."""
    icon = QIcon()
    roots = [Path(__file__).resolve().parent / "icons"]
    if getattr(sys, "_MEIPASS", None):
        roots.insert(0, Path(sys._MEIPASS) / "icons")
    for root in roots:
        for size in ICON_SIZES:
            p = root / f"icon_{size}.png"
            if p.exists():
                icon.addFile(str(p), QSize(size, size))
        if not icon.isNull():
            break
    return icon


def main():
    PLATFORM.setup_logging(logger)
    PLATFORM.before_qapp(APP_NAME)                 # 맥: 메뉴 막대 이름 (QApplication 전에)
    src_dir, cursor_file, target_dirs, qt_argv = parse_cli_args(sys.argv)
    app = QApplication(qt_argv)
    app.setOrganizationName(APP_ORG)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    PLATFORM.after_qapp(app, icon)                 # 맥: Dock 아이콘
    w = MainWindow(start_path=src_dir, start_cursor_file=cursor_file,
                   start_targets=target_dirs)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
