#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""ImageManager 회귀 테스트 — 화면 없이(offscreen) 실제 MainWindow 를 띄워 시나리오를 돈다.

    python tests/test_offscreen.py            # 지금 OS 의 platforms 모듈로
    python tests/test_offscreen.py linux      # mac | linux | windows 를 강제 (휴지통 등 OS 기능은 그 OS 에서만 의미)

격리 (`/qtapp` 스킬 1장):
  - 설정은 앱 이름을 「ImageManagerTest」로 바꿔 따로 저장 → 사용자 설정을 건드리지 않는다
  - 작업 폴더는 임시 폴더, 파일 조작 전마다 소스 루트가 그 안인지 확인(아니면 즉시 종료)
  - 창을 띄우지 않으므로 사용자가 다른 창에 치는 키를 가로채지 않는다
맥 네이티브 키 경로(NSEvent 모니터·IME)는 여기서 안 잡힌다 → 실앱 + osascript 로 따로 확인.
"""
import os
import shutil
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(HERE), "sample", "unsorted")
if len(sys.argv) > 1:
    os.environ["IMGMGR_PLATFORM"] = sys.argv[1]
sys.path.insert(0, os.path.dirname(HERE))
from imagemanager import app as im  # noqa: E402
from imagemanager import platforms  # noqa: E402
target = f"imagemanager (platform={platforms.name()})"
im.APP_NAME = "ImageManagerTest"          # 설정 격리 — QSettings(APP_ORG, APP_NAME)

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QRadioButton  # noqa: E402

D = tempfile.mkdtemp(prefix="imgmgr_test_")
shutil.copytree(SAMPLE, os.path.join(D, "unsorted"))
for d in ("fruit", "vehicle/car", "vehicle/ship", "dog"):
    os.makedirs(os.path.join(D, d))
U = os.path.join(D, "unsorted")
F, V, G = (os.path.join(D, d) for d in ("fruit", "vehicle", "dog"))

app = QApplication([])
app.setOrganizationName(im.APP_ORG)
app.setApplicationName(im.APP_NAME)
QSettings(im.APP_ORG, im.APP_NAME).clear()
src, cur, tg, _ = im.parse_cli_args(["image-manager", os.path.join(U, "photo_01.png"), "-t", F, "-t", V, "-t", G])
w = im.MainWindow(start_path=src, start_cursor_file=cur, start_targets=tg)
w.show()
w.activateWindow()
w.raise_()

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))


def guard():
    root = os.path.abspath(w.source_tree.current_root_path())
    if not root.startswith(os.path.abspath(D)):
        print("ABORT: 소스 루트가 테스트 폴더 밖:", root)
        os._exit(3)


def press(widget, key, mods=Qt.NoModifier):
    getattr(w, "_seen_key_ts", set()).clear()           # 맥 중복 키 차단 — 합성 키는 타임스탬프가 같다
    w.eventFilter(widget, QKeyEvent(QEvent.KeyPress, key, mods))


def ls(p):
    return sorted(f for f in os.listdir(p) if not f.startswith("."))


def name(p):
    return os.path.basename(p or "") or "-"


def panel(i):
    return w.left._panels[i]


def active():
    p = w.left.active_panel()
    return f"{name(p.path())}:{name(p.tree.current_path())}"


# ── 시나리오 (각 단계 사이 파일 작업 워커가 끝나도록 간격) ──────────────────────
def s01():
    check("시작 파일 커서", name(w.source_tree.current_path()) == "photo_01.png", name(w.source_tree.current_path()))
    guard(); w._send_to_panel(0)                                            # Shift+1


def s02():
    check("Shift+1 → fruit 로 이동", ls(F) == ["photo_01.png"], str(ls(F)))
    check("보낸 사진이 미니 프리뷰에", name(panel(0)._mini_path) == "photo_01.png", name(panel(0)._mini_path))
    check("이동 후 다음 파일 커서", name(w.source_tree.current_path()) == "photo_02.png", name(w.source_tree.current_path()))
    w._undo_last()


def s03():
    check("Undo → 원위치", "photo_01.png" in ls(U) and ls(F) == [], str(ls(F)))
    check("Undo 후 미니 프리뷰 비움", panel(0)._mini_path is None, str(panel(0)._mini_path))
    w._cursor_on_file(os.path.join(U, "photo_01.png"))


def s04():
    press(w.source_tree, Qt.Key_S) if sys.platform != "darwin" else w._move_source_cursor(+1)   # 맥 S 는 네이티브 경로
    guard(); w._send_to_panel(0)


def s05():
    check("커서 이동 후 보내기 = 1장만(선택 누적 X)", ls(F) == ["photo_02.png"], str(ls(F)))
    w.left.select_at(0)
    w._move_target_cursor(+1)
    check("타겟 커서 = 파일", name(panel(0).tree.current_path()) == "photo_02.png", active())
    guard(); press(panel(0).tree, Qt.Key_Left, Qt.ShiftModifier)          # Shift+← 되돌리기


def s06():
    check("Shift+← 소스로 되돌리기", ls(F) == [] and "photo_02.png" in ls(U), str(ls(F)))
    check("되돌린 파일에 소스 커서", name(w.source_tree.current_path()) == "photo_02.png", name(w.source_tree.current_path()))
    w._pref_returnKey = w._return_key = "backspace"
    w._cursor_on_file(os.path.join(U, "photo_03.png"))


def s07():
    guard(); w._send_to_panel(0)


def s08():
    w.left.select_at(0); w._move_target_cursor(+1)
    press(panel(0).tree, Qt.Key_Left, Qt.ShiftModifier)                    # backspace 설정이면 Shift+← 는 상위로
    check("설정=Shift+Backspace 일 때 Shift+← 는 되돌리지 않음", ls(F) == ["photo_03.png"], str(ls(F)))
    panel(0).tree.set_root_path(F)


def s09():
    w.left.select_at(0)
    w._panel_cursor_on_file(panel(0), os.path.join(F, "photo_03.png"))
    if name(panel(0).tree.current_path()) != "photo_03.png":
        check("Shift+Backspace 준비(타겟 커서)", False, active())
    guard()
    getattr(w, "_seen_key_ts", set()).clear()
    ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.ShiftModifier)
    handled = w.eventFilter(panel(0).tree, ev)



def s10():
    check("Shift+Backspace 되돌리기", ls(F) == [] and "photo_03.png" in ls(U), str(ls(F)))
    w._pref_returnKey = w._return_key = "left"
    # ↑/↓ 와 Shift+↑/↓ (fruit 빈 폴더 → vehicle(car, ship 하위 폴더) → dog)
    w.left.select_at(0)
    seq = [active()]
    for k, m in [(Qt.Key_Down, 0), (Qt.Key_Down, 0), (Qt.Key_Down, 0), (Qt.Key_Down, 0),
                 (Qt.Key_Up, Qt.ShiftModifier), (Qt.Key_Up, Qt.ShiftModifier)]:
        press(w.left.active_panel().tree, k, m or Qt.NoModifier)
        seq.append(active())
    want = ["fruit:-", "vehicle:-", "vehicle:car", "vehicle:ship", "dog:-", "vehicle:-", "fruit:-"]
    check("↑/↓ 끝에서 패널 넘김 · Shift+↑/↓ 패널 이동 · 패널 진입 시 커서 비움", seq == want, f"{seq}")
    w._cursor_on_file(os.path.join(U, "photo_04.png"))


def s11():
    guard(); w._send_to_panel(1)                                            # Shift+2 — 하위 폴더 있는 패널


def s12():
    check("Shift+2 → 패널 폴더(하위 폴더 아님)", ls(V) == ["car", "photo_04.png", "ship"], str(ls(V)))
    # Enter 키 동작
    w._enter_action = "copy"; w.left.select_at(0)
    w._cursor_on_file(os.path.join(U, "photo_05.png"))


def s13():
    guard(); press(w.source_tree, Qt.Key_Return)


def s14():
    check("Enter=복사", ls(F) == ["photo_05.png"] and "photo_05.png" in ls(U), str(ls(F)))
    w._enter_action = "move"
    w._cursor_on_file(os.path.join(U, "photo_06.png"))


def s14b():
    guard(); press(w.source_tree, Qt.Key_Return)


def s15():
    check("Enter=이동", "photo_06.png" in ls(F) and "photo_06.png" not in ls(U), str(ls(F)))
    # 필터
    w.activateWindow(); w.source_tree.setFocus()
    press(w.source_tree, Qt.Key_Slash)
    check("/ → 필터 칸 포커스", w.filter_edit.isVisible() and QApplication.focusWidget() is w.filter_edit,
          type(QApplication.focusWidget()).__name__)
    QTest.keyClicks(w.filter_edit, "07")
    rows = w._proxy.rowCount(w.source_tree.rootIndex())
    check("필터 「07」 → 1행", rows == 1, str(rows))
    QTest.keyClick(w.filter_edit, Qt.Key_Backspace)
    check("Backspace 로 필터 글자 지움", w.filter_edit.text() == "0", repr(w.filter_edit.text()))
    press(w.filter_edit, Qt.Key_Home)
    check("Home → 필터 해제", not w.filter_edit.isVisible() and w.filter_edit.text() == "", repr(w.filter_edit.text()))


def s16():
    # 전체화면 — 소스 미리보기에서 열고 넘기면 소스 커서가 따라감
    w._cursor_on_file(os.path.join(U, "photo_07.png"))


def s17():
    w.preview.load(os.path.join(U, "photo_07.png"))
    w._open_fullscreen("source")
    fs = w._fullscreen
    check("전체화면 열림", fs is not None and fs.isVisible())
    if fs:
        fs.step(+1)
        check("전체화면 → 다음 이미지 + 소스 커서 동기", name(fs.current_path()) == name(w.source_tree.current_path()) != "photo_07.png",
              f"{name(fs.current_path())} / {name(w.source_tree.current_path())}")
        fs.close()


def qkey(widget, key, mods=Qt.NoModifier):
    """실제 전달 경로로 키 — 합성 키는 타임스탬프가 같아 중복 차단에 걸리므로 기록을 비운다."""
    getattr(w, "_seen_key_ts", set()).clear()
    QTest.keyClick(widget, key, mods)


def s17b():
    check("전체화면 닫힘", w._fullscreen is None)
    # 실제 전달 경로(QApplication → 앱 전체 필터) — 위젯별 필터 없이도 트리·미리보기가 화살표를 먹지 않는지
    w.left.select_at(1)                     # vehicle (car, ship, photo_04)
    qkey(w.source_tree, Qt.Key_Down)
    check("실전달: 소스 트리 포커스에서 ↓ → 타겟 커서", w.left.active_panel().tree.current_path() is not None, active())
    w.preview.setFocus()
    qkey(w.preview, Qt.Key_Down, Qt.ShiftModifier)
    check("실전달: 미리보기 포커스에서 Shift+↓ → 다음 패널", name(w.left.active_panel().path()) == "dog", active())
    w.left.select_at(1)
    qkey(w.left.active_panel().tree, Qt.Key_Down)   # car
    qkey(w.left.active_panel().tree, Qt.Key_Right)  # car 로 진입
    check("실전달: 타겟 트리에서 → = 하위 폴더 진입(펼치기 아님)", name(w.left.active_panel().tree.current_root_path()) == "car",
          w.left.active_panel().tree.current_root_path())
    qkey(w.left.active_panel().tree, Qt.Key_Left)
    check("실전달: ← = 상위 폴더", name(w.left.active_panel().tree.current_root_path()) == "vehicle",
          w.left.active_panel().tree.current_root_path())


def s19():
    # 버그 ① — 활성 아닌 패널의 미니 프리뷰를 클릭(누름=활성화 → 뗌=전체화면)해도 전체화면이 열려야 한다
    w.left.select_at(0)
    panel(1)._set_mini(os.path.join(V, "photo_04.png"))       # vehicle 미니 프리뷰에 사진
    if os.environ.get("IMGMGR_TEST_DEBUG"):
        hits = []
        panel(1).mini_clicked.connect(lambda: hits.append("mini_clicked"))
        orig = w._open_fullscreen
        w._open_fullscreen = lambda *a, **k: (hits.append(("open", a, panel(1)._mini_path)), orig(*a, **k))
    QTest.mouseClick(panel(1)._mini, Qt.LeftButton)
    if os.environ.get("IMGMGR_TEST_DEBUG"):
        print("DEBUG s19", hits, "| mini_path:", panel(1)._mini_path, "| exists:", os.path.exists(panel(1)._mini_path or ""))
        w._open_fullscreen = orig
    fs = w._fullscreen
    check("[0.6.1] 다른 패널 미니 프리뷰 클릭 → 전체화면", fs is not None and fs.isVisible(), str(fs))
    if fs:
        fs.close()


def s20():
    # 버그 ② — 「열려 있음」 표시만 남은 상태(창은 숨겨짐)에서도 다시 열려야 한다
    w.preview.load(os.path.join(U, "photo_08.png"))
    w._open_fullscreen("source")
    fs = w._fullscreen
    if fs:
        fs.hide()                                              # 닫힘 처리 없이 사라진 상황 흉내
    w._open_fullscreen("source")
    check("[0.6.1] 남은 표시가 있어도 다시 열림", w._fullscreen is not None and w._fullscreen.isVisible())
    fs2 = w._fullscreen
    # 확대·축소 · 휠 · 드래그
    if fs2:
        fs2.handle_key(QKeyEvent(QEvent.KeyPress, Qt.Key_BracketRight, Qt.NoModifier))
        fs2.handle_key(QKeyEvent(QEvent.KeyPress, Qt.Key_BracketRight, Qt.NoModifier))
        check("] 두 번 → 확대 156%", abs(fs2.zoom() - 1.5625) < 0.01, f"{fs2.zoom():.3f}")
        before = fs2._center
        c = fs2.rect().center()
        QTest.mousePress(fs2, Qt.LeftButton, Qt.NoModifier, c)
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF
        mv = QMouseEvent(QEvent.MouseMove, QPointF(c.x() + 80, c.y() + 40), QPointF(c.x() + 80, c.y() + 40),
                         Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(fs2, mv)
        QTest.mouseRelease(fs2, Qt.LeftButton, Qt.NoModifier, c + c.__class__(80, 40))
        check("확대 중 드래그 → 이동(닫히지 않음)", fs2.isVisible() and fs2._center != before, f"{before} → {fs2._center}")
        fs2._bar_zoom_out.click()
        fs2.handle_key(QKeyEvent(QEvent.KeyPress, Qt.Key_BracketLeft, Qt.NoModifier))
        check("− 버튼 · [ → 맞춤 100%", fs2.zoom() == 1.0, f"{fs2.zoom():.3f}")
        idx0 = fs2._idx
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtCore import QPoint
        we = QWheelEvent(QPointF(c), QPointF(c), QPoint(0, 0), QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                         Qt.NoScrollPhase, False)
        QApplication.sendEvent(fs2, we)
        check("휠 아래 → 다음 이미지", fs2._idx == idx0 + 1, f"{idx0} → {fs2._idx}")
        fs2.handle_key(QKeyEvent(QEvent.KeyPress, Qt.Key_V, Qt.NoModifier))
    check("전체화면에서 V → 닫힘", not w._fullscreen_open_now())


def s21():
    # V — 소스 커서의 이미지
    w._cursor_on_file(os.path.join(U, "photo_09.png"))
    w.source_tree.setFocus()
    press(w.source_tree, Qt.Key_V)
    fs = w._fullscreen
    check("V → 소스 커서 이미지 전체화면", fs is not None and name(fs.current_path()) == "photo_09.png",
          name(fs.current_path()) if fs else "없음")
    if fs:
        fs.close()


def s22():
    # V — 타겟 커서가 폴더면 그 안 첫 이미지
    shutil.copy(os.path.join(U, "photo_10.png"), os.path.join(V, "car", "inside.png"))
    w.left.select_at(1)
    w._panel_cursor_on_file(panel(1), os.path.join(V, "car"))
    panel(1).tree.setFocus()
    press(panel(1).tree, Qt.Key_V)
    fs = w._fullscreen
    check("V → 타겟 커서 폴더의 첫 이미지", fs is not None and name(fs.current_path()) == "inside.png",
          name(fs.current_path()) if fs else f"없음 / {w.status_label.text()}")
    if fs:
        fs.close()


def s18():
    # 설정 창
    QTimer.singleShot(300, poke_settings)
    w._show_settings()


_poked = []


def poke_settings():
    from PySide6.QtWidgets import QDialog
    if _poked:
        return
    for d in app.topLevelWidgets():
        if isinstance(d, QDialog) and d.isVisible() and d.findChildren(QRadioButton):
            _poked.append(1)
            rbs = d.findChildren(QRadioButton)
            check("설정 창 라디오 + 설명", len(rbs) >= 5 and all(r.toolTip() for r in rbs), str(len(rbs)))
            for r in rbs:
                if r.text() == "복사":
                    r.setChecked(True)
            check("설정 즉시 저장", QSettings(im.APP_ORG, im.APP_NAME).value("enterAction") == "copy")
            d.reject()
            return
    QTimer.singleShot(200, poke_settings)      # 아직 안 떴으면 다시


def no_unexpected_dialog():
    from PySide6.QtWidgets import QDialog
    if _poked:          # 설정 창 검사 중엔 제외
        return
    for d in app.topLevelWidgets():
        if isinstance(d, QDialog) and d.isVisible() and not d.findChildren(QRadioButton):
            check("예상 못한 대화상자 없음", False, d.windowTitle())
            d.reject()


def finish():
    w.close()
    QSettings(im.APP_ORG, im.APP_NAME).clear()
    shutil.rmtree(D, ignore_errors=True)
    n, ok = len(results), sum(results)
    print(f"\n{ok}/{n} 통과 — {target}")
    app.exit(0 if ok == n else 1)


steps = [s01, s02, s03, s04, s05, s06, s07, s08, s09, s10, s11, s12, s13, s14, s14b, s15, s16, s17, s17b, s19, s20, s21, s22, s18, finish]


def busy():
    wk = getattr(w, "_worker", None)
    return wk is not None and wk.isRunning()


def run_next(i=0):
    """단계를 차례로 — 파일 작업 워커가 끝날 때까지 기다린 뒤 다음 단계 (고정 간격이면 느린 기계에서 거짓 실패)."""
    if i >= len(steps):
        return
    if busy():
        QTimer.singleShot(100, lambda: run_next(i))
        return
    steps[i]()
    if steps[i] is not s18 and steps[i] is not finish:
        QTimer.singleShot(600, no_unexpected_dialog)
    QTimer.singleShot(4000 if steps[i] is s18 else 700, lambda: run_next(i + 1))


QTimer.singleShot(1500, lambda: run_next(0))
sys.exit(app.exec())
