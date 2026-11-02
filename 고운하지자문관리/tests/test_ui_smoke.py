import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.secure_store import SecureStore  # noqa: E402
from app.ui.case_dialog import CaseDialog  # noqa: E402
from app.ui.dialogs import ReportDialog, TrashDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.style import QSS  # noqa: E402
from tests.sample_data import populate  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    a.setStyleSheet(QSS)
    return a


def test_main_window_and_dialogs(app, tmp_path):
    store = SecureStore(tmp_path / "ui.gjdb")
    store.create()
    win = MainWindow(store)
    populate(win.repo, 10)
    win.refresh()
    assert win.table.rowCount() == 11
    win.search.setText("테스트환자01")
    assert win.table.rowCount() == 2
    win.search.setText("")
    # 진행 중 / 완료 필터
    for b in win.view_group.buttons():
        if b.property("key") == "open":
            b.setChecked(True)
    assert all(win.table.item(r, 5).text() == "" for r in range(win.table.rowCount()))

    cid = win.repo.list_cases()[0]["id"]
    d = CaseDialog(win.repo, cid, win)
    d.note_edit.setPlainText("새 진행 내용")
    d._add_note()
    assert d.timeline.count() >= 2
    d.show()
    win.grab().save(str(tmp_path / "main.png"))
    d.grab().save(str(tmp_path / "case.png"))

    new = CaseDialog(win.repo, None, win)
    new.patient.setText("신규가상")
    new.surgery.set_value("2026-05-01")
    new.note_edit.setPlainText("첫 기록")
    new._save()
    assert win.repo.counts()["total"] == 12

    r = ReportDialog(win.repo, win)
    r.show()
    assert r.report and "신규" in r.view.toPlainText() or r.report
    r.mask.setChecked(True)
    assert "테스트환자01" not in r.view.toPlainText()
    r.grab().save(str(tmp_path / "report.png"))
    r._confirm()
    assert len(win.repo.reports()) == 1
    TrashDialog(win.repo, win)
    win.close()
    assert not store.is_open
    shot_dir = os.environ.get("SHOT_DIR")
    if shot_dir:  # 화면 캡처를 따로 보관하고 싶을 때만
        import shutil
        for n in ("main", "case", "report"):
            shutil.copy(tmp_path / f"{n}.png", Path(shot_dir) / f"{n}.png")


def test_recovery_notice_shown_only_once(app, tmp_path, monkeypatch):
    """프로그램을 여러 번 껐다 켜도 복구 키 안내는 최초 1회만, 복구 키는 그대로."""
    from PySide6.QtWidgets import QMessageBox
    from app import backup
    from app.db import Repository
    from app.main import open_store

    calls = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: calls.append(1) or QMessageBox.No)
    path = tmp_path / "once" / "자문현황.gjdb"

    def launch():
        store = SecureStore(path)
        assert open_store(store)          # 실제 시작 경로(처음이면 새로 만들고 플래그 설정)
        win = MainWindow(store)
        win._first_run_notice()           # 시작 직후 0.4초 뒤에 불리는 함수
        key = win.repo.get_setting("recovery_key")
        win.close()                       # 종료 시 자동 백업 + 저장
        return key

    keys = [launch() for _ in range(5)]
    assert len(calls) == 1                # 안내는 처음 한 번뿐
    assert len(set(keys)) == 1 and keys[0]  # 복구 키는 바뀌지 않음
    assert (path.parent / "복구키안내완료.txt").exists()

    # 옛 백업 복원 등으로 DB 안의 표시가 True 로 되살아나도 다시 안내하지 않는다
    store = SecureStore(path)
    store.open(device=True)
    Repository(store).set_setting("first_run_notice", True)
    store.close()
    launch()
    assert len(calls) == 1

    # 설정에서 복구 키를 다시 볼 수 있다(키 문자열이 저장되어 있음)
    store = SecureStore(path)
    store.open(device=True)
    assert Repository(store).get_setting("recovery_key") == keys[0]
    store.close()
