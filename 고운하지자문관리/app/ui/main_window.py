from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QComboBox, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPushButton, QRadioButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .. import backup
from ..db import Repository
from ..paths import APP_TITLE
from ..secure_store import SecureStore
from .auth import RecoveryKeyDialog
from .case_dialog import CaseDialog
from .dialogs import BackupDialog, ReportDialog, SettingsDialog, TrashDialog

COLS = ["환자명", "보험회사", "수술일자", "자문일자", "현재 진행상황", "최종 처리결과", "비고"]

def _card(label: str):
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 10, 18, 10)
    num = QLabel("0")
    num.setObjectName("cardNum")
    txt = QLabel(label)
    txt.setObjectName("cardLabel")
    lay.addWidget(num)
    lay.addWidget(txt)
    return f, num


class MainWindow(QMainWindow):
    def __init__(self, store: SecureStore):
        super().__init__()
        self.store = store
        self.repo = Repository(store)
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 780)
        self._build()
        self.refresh()
        QTimer.singleShot(400, self._first_run_notice)

    # ---- 화면 구성 ---------------------------------------------------
    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        box = QVBoxLayout()
        t = QLabel("고운하지흉부외과의원")
        t.setObjectName("title")
        s = QLabel("보험 자문 진행 현황")
        s.setObjectName("sub")
        box.addWidget(t)
        box.addWidget(s)
        head.addLayout(box)
        head.addStretch(1)
        for text, fn in (("백업·복원", self._backup),
                         ("휴지통", self._trash), ("설정", self._settings)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            head.addWidget(b)
        lay.addLayout(head)

        cards = QHBoxLayout()
        f1, self.n_total = _card("전체 자문")
        f2, self.n_open = _card("진행 중")
        f3, self.n_closed = _card("처리 완료")
        for f in (f1, f2, f3):
            cards.addWidget(f)
        self.breakdown = QLabel("")
        self.breakdown.setObjectName("sub")
        self.breakdown.setWordWrap(True)
        cards.addWidget(self.breakdown, 1)
        lay.addLayout(cards)

        bar = QHBoxLayout()
        add = QPushButton("＋ 신규 등록")
        add.setObjectName("primary")
        add.clicked.connect(self._new)
        bar.addWidget(add)
        self.search = QLineEdit()
        self.search.setPlaceholderText("환자명 또는 보험회사 검색")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        self.search.textChanged.connect(self.refresh)
        bar.addWidget(self.search)
        self.view_group = QButtonGroup(self)
        for i, (text, key) in enumerate((("전체", "all"), ("진행 중", "open"), ("처리 완료", "closed"))):
            rb = QRadioButton(text)
            rb.setProperty("key", key)
            rb.setChecked(i == 0)
            self.view_group.addButton(rb)
            rb.toggled.connect(lambda on: on and self.refresh())
            bar.addWidget(rb)
        self.f_status = QComboBox()
        self.f_result = QComboBox()
        self.f_status.currentIndexChanged.connect(self.refresh)
        self.f_result.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.f_status)
        bar.addWidget(self.f_result)
        bar.addStretch(1)
        rep = QPushButton("주간 보고서")
        rep.setObjectName("primary")
        rep.clicked.connect(self._report)
        bar.addWidget(rep)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        for i, w in enumerate((110, 130, 100, 100, 150, 120)):
            self.table.setColumnWidth(i, w)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.cellDoubleClicked.connect(lambda *_: self._edit())
        lay.addWidget(self.table, 1)

        foot = QHBoxLayout()
        b = QPushButton("선택 사건 수정 / 진행 기록")
        b.clicked.connect(self._edit)
        d = QPushButton("선택 사건 삭제")
        d.setObjectName("danger")
        d.clicked.connect(self._delete)
        foot.addWidget(b)
        foot.addWidget(d)
        foot.addStretch(1)
        hint = QLabel("행을 더블클릭하면 상세 내용과 진행 기록을 볼 수 있습니다.")
        hint.setObjectName("sub")
        foot.addWidget(hint)
        lay.addLayout(foot)
        self._fill_filters()

    def _fill_filters(self):
        for combo, first, items in ((self.f_status, "진행상황: 전체", self.repo.statuses()),
                                    (self.f_result, "처리결과: 전체", self.repo.results())):
            cur = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(first, "")
            used = {r[0] for r in self.repo.conn.execute(
                "SELECT DISTINCT %s FROM cases WHERE deleted_at IS NULL AND %s<>''" % (
                    ("status",) * 2 if combo is self.f_status else ("result",) * 2))}
            for it in list(items) + sorted(used - set(items)):
                combo.addItem(it, it)
            idx = combo.findData(cur)
            combo.setCurrentIndex(max(idx, 0))
            combo.blockSignals(False)

    # ---- 데이터 표시 -------------------------------------------------
    def _view_key(self) -> str:
        return next((b.property("key") for b in self.view_group.buttons() if b.isChecked()), "all")

    def refresh(self, *_):
        rows = self.repo.list_cases(self.search.text(), self._view_key(),
                                    self.f_status.currentData() or "", self.f_result.currentData() or "")
        self.table.setRowCount(len(rows))
        for r, c in enumerate(rows):
            note = (c["latest_note"] or "").strip()
            first = note.splitlines()[0] if note else ""
            vals = [c["patient"], c["insurer"], c["surgery_date"], c["consult_date"], c["status"],
                    c["result"], first[:80] + ("…" if len(first) > 80 or "\n" in note else "")]
            closed = bool(c["result"])
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 0:
                    it.setData(Qt.UserRole, c["id"])
                if j == 6 and note:
                    it.setToolTip(note[:600])
                if closed:
                    it.setForeground(QBrush(QColor("#8a9099")))
                elif j == 4:
                    it.setForeground(QBrush(QColor("#1f3a5f")))
                self.table.setItem(r, j, it)
        cnt = self.repo.counts()
        self.n_total.setText(str(cnt["total"]))
        self.n_open.setText(str(cnt["open"]))
        self.n_closed.setText(str(cnt["closed"]))
        res = " · ".join(f"{r['result']} {r['n']}" for r in self.repo.result_counts())
        sts = " · ".join(f"{r['status'] or '(미입력)'} {r['n']}" for r in self.repo.status_counts())
        self.breakdown.setText(f"<b>진행 중 현황</b>  {sts or '-'}<br><b>처리 결과</b>  {res or '-'}")

    def _current_id(self):
        r = self.table.currentRow()
        it = self.table.item(r, 0) if r >= 0 else None
        return it.data(Qt.UserRole) if it else None

    # ---- 동작 -------------------------------------------------------
    def _new(self):
        CaseDialog(self.repo, None, self).exec()
        self._fill_filters()
        self.refresh()

    def _edit(self):
        cid = self._current_id()
        if cid is None:
            return QMessageBox.information(self, "안내", "목록에서 사건을 먼저 선택해 주세요.")
        CaseDialog(self.repo, cid, self).exec()
        self._fill_filters()
        self.refresh()

    def _delete(self):
        cid = self._current_id()
        if cid is None:
            return QMessageBox.information(self, "안내", "목록에서 사건을 먼저 선택해 주세요.")
        c = self.repo.get_case(cid)
        if QMessageBox.question(self, "사건 삭제",
                                f"'{c['patient']} / {c['insurer']}' 사건을 삭제할까요?\n"
                                "휴지통으로 이동하며, 언제든 복원할 수 있습니다.") == QMessageBox.Yes:
            self.repo.delete_case(cid)
            self.refresh()

    def _report(self):
        ReportDialog(self.repo, self).exec()

    def _backup(self):
        dlg = BackupDialog(self.repo, self)
        dlg.exec()
        if dlg.restored:
            self._fill_filters()
            self.refresh()

    def _trash(self):
        TrashDialog(self.repo, self).exec()
        self.refresh()

    def _settings(self):
        if SettingsDialog(self.repo, self).exec():
            self._fill_filters()
            self.refresh()

    def _notice_marker(self):
        """'안내했음' 표시 파일. 데이터 파일과 같은 폴더에 두며, 데이터 안(DB)의 표시와는 별개다.

        백업을 복원해 DB 안의 표시가 예전 값으로 되돌아가도 안내가 다시 뜨지 않게 한다.
        """
        return self.store.path.parent / "복구키안내완료.txt"

    def _first_run_notice(self):
        """복구 키 안내는 데이터를 처음 만든 직후 단 한 번만 보여 준다."""
        flag = self.repo.get_setting("first_run_notice", False)
        marker = self._notice_marker()
        if marker.exists():
            if flag:  # DB 안의 표시가 되살아난 경우(예: 옛 백업 복원) 정리만 하고 안내하지 않는다
                self.repo.set_setting("first_run_notice", False)
            return
        if not flag:
            return
        # 안내창을 띄우기 '전에' 먼저 기록한다(창을 닫거나 프로그램이 꺼져도 다시 뜨지 않도록)
        try:
            marker.write_text("복구 키 보관 안내를 이미 표시했습니다. 이 파일을 지우지 마세요.\n", encoding="utf-8")
        except OSError:
            pass
        self.repo.set_setting("first_run_notice", False)
        text = "\n".join([
            "이 프로그램은 비밀번호 없이 열립니다. 데이터는 이 PC의 Windows 계정으로 암호화되어 있습니다.",
            "",
            "PC를 바꾸거나 Windows를 다시 설치한 뒤 데이터·백업을 열려면 복구 키가 필요합니다.",
            "지금 복구 키를 확인하고 저장해 둘까요? ([설정]에서 언제든 다시 볼 수 있습니다)"])
        if QMessageBox.question(self, "복구 키 보관 안내", text) == QMessageBox.Yes:
            key = self.repo.get_setting("recovery_key", "")
            if key:
                RecoveryKeyDialog(key, self).exec()

    # (이전 자동 잠금 기능은 제거되었습니다)
    # ---- 종료 --------------------------------------------------------
    def closeEvent(self, ev):
        try:
            if self.store.is_open:
                backup.auto_backup(self.store)
                self.store.close()
        except Exception:  # noqa: BLE001  (종료는 막지 않는다)
            pass
        ev.accept()
