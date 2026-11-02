"""설정 · 백업/복원 · 휴지통 · 주간 보고서 창."""
from __future__ import annotations

import os
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QTextBrowser, QVBoxLayout)

from .. import backup, exporters, report
from ..db import Repository
from ..paths import backup_dir
from ..secure_store import CorruptFile, SecretRequired, WrongPassword
from .auth import RecoveryKeyDialog, ask_secret


def _docs_dir() -> str:
    d = Path.home() / "Documents"
    return str(d if d.exists() else Path.home())


# ---------------------------------------------------------------- 설정
class SettingsDialog(QDialog):
    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("설정")
        self.resize(520, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("현재 진행상황 선택 목록 (한 줄에 하나)"))
        self.statuses = QPlainTextEdit("\n".join(repo.statuses()))
        lay.addWidget(self.statuses)
        lay.addWidget(QLabel("최종 처리결과 선택 목록 (한 줄에 하나)"))
        self.results = QPlainTextEdit("\n".join(repo.results()))
        lay.addWidget(self.results)
        note = QLabel("목록에 없는 내용도 사건 입력 시 직접 적을 수 있습니다.")
        note.setObjectName("sub")
        lay.addWidget(note)
        rk = QPushButton("복구 키 보기 / 저장")
        rk.clicked.connect(self._show_recovery)
        lay.addWidget(rk)
        row = QHBoxLayout()
        row.addStretch(1)
        c = QPushButton("취소")
        c.clicked.connect(self.reject)
        s = QPushButton("저장")
        s.setObjectName("primary")
        s.clicked.connect(self._save)
        row.addWidget(c)
        row.addWidget(s)
        lay.addLayout(row)

    @staticmethod
    def _lines(box):
        out = []
        for ln in box.toPlainText().splitlines():
            ln = ln.strip()
            if ln and ln not in out:
                out.append(ln)
        return out

    def _save(self):
        self.repo.set_setting("statuses", self._lines(self.statuses))
        self.repo.set_setting("results", self._lines(self.results))
        self.accept()

    def _show_recovery(self):
        key = self.repo.get_setting("recovery_key", "")
        if key:
            RecoveryKeyDialog(key, self).exec()
        else:
            QMessageBox.information(
                self, "복구 키",
                "이 데이터는 이전 버전에서 만든 복구 키를 계속 사용합니다.\n"
                "그때 보관해 둔 복구 키를 그대로 사용하세요. (프로그램은 그 키 문자열을 알지 못합니다.)")


# ---------------------------------------------------------------- 백업/복원
class BackupDialog(QDialog):
    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.restored = False
        self.setWindowTitle("백업 및 복원")
        self.resize(520, 330)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "<b>백업</b>은 암호화된 상태 그대로 저장됩니다.<br>"
            "(다른 PC에서 열려면 <b>복구 키</b>가 필요합니다. [설정]에서 확인하세요.)<br>"
            "USB 등 다른 저장장치에도 정기적으로 보관해 두세요."))
        b1 = QPushButton("지금 백업 파일 저장…")
        b1.setObjectName("primary")
        b1.clicked.connect(self._backup)
        lay.addWidget(b1)
        b2 = QPushButton("자동 백업 폴더 열기")
        b2.clicked.connect(lambda: os.startfile(str(backup_dir())))
        lay.addWidget(b2)
        lay.addWidget(QLabel(
            "<b>복원</b>은 백업 파일을 먼저 미리 확인한 뒤 진행합니다.<br>"
            "복원 직전의 현재 데이터는 자동으로 따로 보관되므로, 잘못 복원해도 되돌릴 수 있습니다."))
        b3 = QPushButton("백업 파일에서 복원…")
        b3.clicked.connect(self._restore)
        lay.addWidget(b3)
        lay.addStretch(1)
        c = QPushButton("닫기")
        c.clicked.connect(self.accept)
        lay.addWidget(c)

    def _backup(self):
        name = f"고운하지자문_백업_{datetime.now():%Y%m%d_%H%M}{backup.EXT}"
        path, _ = QFileDialog.getSaveFileName(self, "백업 저장", str(Path(_docs_dir()) / name),
                                              f"자문 백업 (*{backup.EXT})")
        if path:
            dest = backup.manual_backup(self.repo.store, Path(path))
            QMessageBox.information(self, "백업 완료", f"저장했습니다.\n{dest}")

    def _restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "복원할 백업 선택", str(backup_dir()),
                                              f"자문 백업 (*{backup.EXT})")
        if not path:
            return
        info = None
        secret = None
        while info is None:
            try:
                info = backup.inspect_backup(Path(path), secret=secret)
            except SecretRequired:
                secret = ask_secret(
                    self, "백업 열기",
                    "이 PC에서 자동으로 열 수 없는 백업입니다.\n복구 키를 입력하세요. (이전 버전 백업이면 예전 비밀번호도 가능)")
                if secret is None:
                    return
            except WrongPassword:
                secret = ask_secret(self, "다시 입력", "입력한 복구 키(또는 비밀번호)가 올바르지 않습니다. 다시 입력하세요.")
                if secret is None:
                    return
            except CorruptFile as exc:
                return QMessageBox.critical(self, "열 수 없음", str(exc))
        now_c = self.repo.counts()
        msg = (f"<b>복원할 백업</b> (저장 {info['saved_at']})<br>"
               f"전체 {info['total']}건 · 진행 중 {info['open']}건 · 처리 완료 {info['closed']}건 · 저장된 보고서 {info['reports']}건<br><br>"
               f"<b>현재 데이터</b><br>전체 {now_c['total']}건 · 진행 중 {now_c['open']}건 · 처리 완료 {now_c['closed']}건<br><br>"
               "복원하면 <b>현재 데이터가 백업 내용으로 바뀝니다.</b><br>"
               "(현재 데이터는 복원 직전에 자동 보관됩니다.)")
        if QMessageBox.question(self, "복원 미리보기", msg) != QMessageBox.Yes:
            return
        text, ok = QInputDialog.getText(self, "복원 최종 확인", "계속하려면 '복원'이라고 입력하세요.")
        if not ok or text.strip() != "복원":
            return QMessageBox.information(self, "취소", "복원하지 않았습니다.")
        safety = backup.restore(self.repo.store, info["plain"])
        self.restored = True
        QMessageBox.information(self, "복원 완료", f"복원했습니다.\n복원 직전 데이터 보관 위치:\n{safety}")
        self.accept()


# ---------------------------------------------------------------- 휴지통
class TrashDialog(QDialog):
    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.changed = False
        self.setWindowTitle("삭제한 사건 (휴지통)")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("삭제한 사건은 여기에 보관됩니다. 복원하거나 완전히 삭제할 수 있습니다."))
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        r = QPushButton("선택 사건 복원")
        r.clicked.connect(self._restore)
        d = QPushButton("완전히 삭제")
        d.setObjectName("danger")
        d.clicked.connect(self._purge)
        c = QPushButton("닫기")
        c.clicked.connect(self.accept)
        row.addWidget(r)
        row.addWidget(d)
        row.addStretch(1)
        row.addWidget(c)
        lay.addLayout(row)
        self._load()

    def _load(self):
        self.list.clear()
        for c in self.repo.trash():
            it = QListWidgetItem(f"{c['case_no']}  {c['patient']} / {c['insurer']}   (삭제 {c['deleted_at'][:16]})")
            it.setData(Qt.UserRole, c["id"])
            self.list.addItem(it)

    def _cur(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _restore(self):
        cid = self._cur()
        if cid:
            self.repo.restore_case(cid)
            self.changed = True
            self._load()

    def _purge(self):
        cid = self._cur()
        if cid and QMessageBox.warning(
                self, "완전히 삭제", "이 사건과 모든 진행 기록이 영구 삭제되며 되돌릴 수 없습니다.\n계속할까요?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.repo.purge_case(cid)
            self._load()


# ---------------------------------------------------------------- 주간 보고서
class ReportDialog(QDialog):
    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.report: dict | None = None
        self.saved_id: int | None = None
        self.setWindowTitle("주간 보고서")
        self.resize(1000, 760)
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        s, e = report.default_period()
        self.start = QDateEdit(QDate(s.year, s.month, s.day))
        self.end = QDateEdit(QDate(e.year, e.month, e.day))
        for w in (self.start, self.end):
            w.setCalendarPopup(True)
            w.setDisplayFormat("yyyy-MM-dd (ddd)")
        top.addWidget(QLabel("보고 기간"))
        top.addWidget(self.start)
        top.addWidget(QLabel("~"))
        top.addWidget(self.end)
        b = QPushButton("이번 주(월~일)")
        b.clicked.connect(self._this_week)
        top.addWidget(b)
        b = QPushButton("지난 주")
        b.clicked.connect(self._last_week)
        top.addWidget(b)
        top.addStretch(1)
        self.mask = QCheckBox("환자명 마스킹(김○○)")
        top.addWidget(self.mask)
        lay.addLayout(top)

        row = QHBoxLayout()
        row.addWidget(QLabel("저장된 보고서 불러오기"))
        self.saved = QComboBox()
        self.saved.setMinimumWidth(380)
        row.addWidget(self.saved)
        row.addStretch(1)
        lay.addLayout(row)

        self.view = QTextBrowser()
        lay.addWidget(self.view, 1)
        self.state = QLabel("")
        self.state.setObjectName("sub")
        lay.addWidget(self.state)

        btns = QHBoxLayout()
        self.b_save = QPushButton("보고서 확정 저장")
        self.b_xlsx = QPushButton("엑셀로 저장")
        self.b_pdf = QPushButton("PDF로 저장")
        self.b_pdf.setObjectName("primary")
        close = QPushButton("닫기")
        for x in (self.b_save, self.b_xlsx, self.b_pdf):
            btns.addWidget(x)
        btns.addStretch(1)
        btns.addWidget(close)
        lay.addLayout(btns)

        self.start.dateChanged.connect(self._rebuild)
        self.end.dateChanged.connect(self._rebuild)
        self.mask.toggled.connect(self._render)
        self.saved.activated.connect(self._load_saved)
        self.b_save.clicked.connect(self._confirm)
        self.b_xlsx.clicked.connect(lambda: self._export("xlsx"))
        self.b_pdf.clicked.connect(lambda: self._export("pdf"))
        close.clicked.connect(self.accept)
        self._fill_saved()
        self._rebuild()

    # ---- 기간 ------------------------------------------------------
    def _set_period(self, s: date, e: date):
        for w, d in ((self.start, s), (self.end, e)):
            w.blockSignals(True)
            w.setDate(QDate(d.year, d.month, d.day))
            w.blockSignals(False)

    def _this_week(self):
        self._set_period(*report.default_period())
        self._rebuild()

    def _last_week(self):
        self._set_period(*report.default_period(date.today() - timedelta(days=7)))
        self._rebuild()

    def _dates(self):
        return self.start.date().toPython(), self.end.date().toPython()

    def _rebuild(self, *_):
        s, e = self._dates()
        if e < s:
            self.report = None
            self.view.setHtml("<p style='color:#a33'>종료일이 시작일보다 빠릅니다. 기간을 확인해 주세요.</p>")
            self._enable(False)
            return
        self.report = report.build_report(self.repo, s, e)
        self.saved_id = None
        self._enable(True)
        self.state.setText("미리보기입니다. 아직 확정 저장되지 않았습니다. (엑셀·PDF 저장 시 자동으로 확정 저장됩니다)")
        self._render()

    def _render(self, *_):
        if self.report:
            self.view.setHtml(report.report_html(self.report, self.mask.isChecked()))

    def _enable(self, on: bool):
        for b in (self.b_save, self.b_xlsx, self.b_pdf):
            b.setEnabled(on)

    # ---- 저장된 보고서 ---------------------------------------------
    def _fill_saved(self):
        self.saved.clear()
        self.saved.addItem("— 선택 —", None)
        for r in self.repo.reports():
            self.saved.addItem(f"{r['period_start']} ~ {r['period_end']}   (확정 {r['created_at'][:16]})", r["id"])

    def _load_saved(self, idx):
        rid = self.saved.itemData(idx)
        if not rid:
            return
        rep = self.repo.get_report(rid)
        self.report, self.saved_id = rep, rid
        s = date.fromisoformat(rep["period_start"])
        e = date.fromisoformat(rep["period_end"])
        self._set_period(s, e)
        self._enable(True)
        self.state.setText(f"{rep['generated_at'][:16]}에 확정 저장된 보고서입니다. 작성 당시 내용 그대로 표시됩니다.")
        self._render()

    # ---- 확정 / 내보내기 -------------------------------------------
    def _confirm(self) -> bool:
        if not self.report:
            return False
        if self.saved_id is None:
            self.saved_id = self.repo.save_report(self.report)
            self.state.setText("확정 저장되었습니다. 이후 데이터가 바뀌어도 이 보고서 내용은 변하지 않습니다.")
            self._fill_saved()
        return True

    def _export(self, kind: str):
        if not self.report:
            return
        r = self.report
        if self.mask.isChecked() is False and QMessageBox.question(
                self, "개인정보 확인",
                "환자 실명이 포함된 파일이 만들어집니다.\n병원에 전달하는 용도로만 사용하고, 보관·전달에 유의하세요.\n계속할까요?"
        ) != QMessageBox.Yes:
            return
        ext = "xlsx" if kind == "xlsx" else "pdf"
        name = f"주간보고서_{r['period_start'].replace('-', '')}-{r['period_end'].replace('-', '')}.{ext}"
        filt = "엑셀 (*.xlsx)" if kind == "xlsx" else "PDF (*.pdf)"
        path, _ = QFileDialog.getSaveFileName(self, "보고서 저장", str(Path(_docs_dir()) / name), filt)
        if not path:
            return
        try:
            self._confirm()
            (exporters.write_xlsx if kind == "xlsx" else exporters.write_pdf)(r, Path(path), self.mask.isChecked())
        except PermissionError:
            return QMessageBox.warning(self, "저장 실패", "파일이 다른 프로그램에서 열려 있습니다. 닫고 다시 시도해 주세요.")
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return QMessageBox.critical(self, "저장 실패", f"보고서를 저장하지 못했습니다.\n{exc}")
        if QMessageBox.question(self, "저장 완료", f"저장했습니다.\n{path}\n\n파일을 지금 열어 볼까요?") == QMessageBox.Yes:
            os.startfile(path)
