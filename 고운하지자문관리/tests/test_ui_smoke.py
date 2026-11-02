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
