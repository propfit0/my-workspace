"""사건 등록·수정 창 (7개 항목 + 날짜별 누적 진행 기록)."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from ..db import Repository
from .widgets import OptionalDateEdit


class CaseDialog(QDialog):
    def __init__(self, repo: Repository, case_id: int | None = None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.case_id = case_id
        self.saved = False
        self.setWindowTitle("신규 자문 사건 등록" if case_id is None else "자문 사건 상세")
        self.resize(760, 760 if case_id else 600)

        root = QVBoxLayout(self)
        self.no_label = QLabel("")
        self.no_label.setObjectName("sub")
        root.addWidget(self.no_label)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.patient = QLineEdit()
        self.insurer = QLineEdit()
        self.surgery = OptionalDateEdit()
        self.consult = OptionalDateEdit()
        self.status = QComboBox()
        self.status.setEditable(True)
        self.status.addItems([""] + repo.statuses())
        self.result = QComboBox()
        self.result.setEditable(True)
        self.result.addItems([""] + repo.results())
        self.result.setToolTip("사건이 종결된 경우에만 입력하세요. 진행 중에는 비워 둡니다.")
        form.addRow("환자명", self.patient)
        form.addRow("보험회사", self.insurer)
        form.addRow("수술일자", self.surgery)
        form.addRow("자문일자", self.consult)
        form.addRow("현재 진행상황", self.status)
        form.addRow("최종 처리결과", self.result)
        root.addLayout(form)
        hint = QLabel("※ 최종 처리결과는 사건이 종결된 경우에만 입력하세요(입력하면 '처리 완료'로 분류됩니다).")
        hint.setObjectName("sub")
        root.addWidget(hint)

        self.note_edit = QPlainTextEdit()
        if case_id is None:
            root.addWidget(QLabel("비고 (진행 내용·향후 조치사항)"))
            self.note_edit.setPlaceholderText("처음 기록할 진행 내용을 적어 주세요. 비워 둘 수 있습니다.")
            root.addWidget(self.note_edit, 1)
            self.draft_key = "new"
        else:
            self.draft_key = f"case:{case_id}"
            root.addWidget(QLabel("비고 — 새 진행 내용 추가 (기존 기록은 그대로 보존됩니다)"))
            self.note_edit.setPlaceholderText("새로 진행된 내용과 향후 조치사항을 적고 [기록 추가]를 누르세요.")
            self.note_edit.setFixedHeight(90)
            root.addWidget(self.note_edit)
            addrow = QHBoxLayout()
            addrow.addStretch(1)
            self.add_btn = QPushButton("기록 추가")
            self.add_btn.clicked.connect(self._add_note)
            addrow.addWidget(self.add_btn)
            root.addLayout(addrow)

            head = QHBoxLayout()
            head.addWidget(QLabel("진행 기록 (최신순)"))
            head.addStretch(1)
            self.show_deleted = QCheckBox("삭제된 기록도 보기")
            self.show_deleted.toggled.connect(self._load_notes)
            head.addWidget(self.show_deleted)
            root.addLayout(head)
            self.timeline = QListWidget()
            self.timeline.setWordWrap(True)
            self.timeline.setSelectionMode(QListWidget.SingleSelection)
            root.addWidget(self.timeline, 1)
            row = QHBoxLayout()
            self.b_edit = QPushButton("선택 기록 수정")
            self.b_del = QPushButton("선택 기록 삭제")
            self.b_hist = QPushButton("수정 이력 보기")
            for b in (self.b_edit, self.b_del, self.b_hist):
                row.addWidget(b)
            row.addStretch(1)
            root.addLayout(row)
            self.b_edit.clicked.connect(self._edit_note)
            self.b_del.clicked.connect(self._delete_note)
            self.b_hist.clicked.connect(self._history)

        btns = QHBoxLayout()
        btns.addStretch(1)
        close = QPushButton("닫기")
        close.clicked.connect(self.reject)
        self.save_btn = QPushButton("저장" if case_id else "등록")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._save)
        btns.addWidget(close)
        btns.addWidget(self.save_btn)
        root.addLayout(btns)

        if case_id is not None:
            self._load_case()
            self._load_notes()
        draft = repo.get_draft(self.draft_key)
        if draft:
            self.note_edit.setPlainText(draft)
            self.note_edit.setPlaceholderText("")
        self._dirty_snapshot = self._values()
        # 작성 중인 글 자동 임시 저장(비정상 종료 대비)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(2500)
        self._timer.timeout.connect(self._store_draft)
        self.note_edit.textChanged.connect(self._timer.start)

    # ---- 값 --------------------------------------------------------
    def _values(self) -> dict:
        return {
            "patient": self.patient.text().strip(), "insurer": self.insurer.text().strip(),
            "surgery_date": self.surgery.value(), "consult_date": self.consult.value(),
            "status": self.status.currentText().strip(), "result": self.result.currentText().strip(),
        }

    def _load_case(self):
        c = self.repo.get_case(self.case_id)
        self.no_label.setText(f"관리번호 {c['case_no']}  ·  등록 {c['created_at'][:16]}")
        self.patient.setText(c["patient"])
        self.insurer.setText(c["insurer"])
        self.surgery.set_value(c["surgery_date"])
        self.consult.set_value(c["consult_date"])
        for combo, val in ((self.status, c["status"]), (self.result, c["result"])):
            combo.setCurrentText(val)

    def _store_draft(self):
        self.repo.set_draft(self.draft_key, self.note_edit.toPlainText())

    # ---- 저장 ------------------------------------------------------
    def _save(self):
        vals = self._values()
        if not vals["patient"]:
            if QMessageBox.question(self, "확인", "환자명이 비어 있습니다. 이대로 저장할까요?") != QMessageBox.Yes:
                return
        if self.case_id is None:
            self.case_id = self.repo.add_case(vals, self.note_edit.toPlainText())
            self.repo.clear_draft("new")
        else:
            self.repo.update_case(self.case_id, vals)
        self.saved = True
        self.accept()

    def reject(self):
        if self.case_id is not None and self._values() != self._dirty_snapshot:
            r = QMessageBox.question(self, "저장하지 않은 변경", "변경한 내용을 저장할까요?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.Save:
                self.repo.update_case(self.case_id, self._values())
                self.saved = True
        self._store_draft()  # 쓰던 글은 버리지 않고 임시 보관
        super().reject()

    # ---- 진행 기록 ---------------------------------------------------
    def _add_note(self):
        text = self.note_edit.toPlainText().strip()
        if not text:
            return
        self.repo.update_case(self.case_id, self._values())
        self.repo.add_note(self.case_id, text)
        self._timer.stop()
        self.note_edit.clear()
        self.saved = True
        self._dirty_snapshot = self._values()
        self._load_notes()

    def _load_notes(self):
        self.timeline.clear()
        monday = date.today() - timedelta(days=date.today().weekday())
        this_week = monday.isoformat()
        notes = self.repo.notes(self.case_id, include_deleted=self.show_deleted.isChecked())
        past_header_added = False
        any_current = any(n["created_at"][:10] >= this_week for n in notes)
        if any_current:
            self._separator("▼ 이번 주 기록")
        for n in notes:
            is_current = n["created_at"][:10] >= this_week
            if not is_current and not past_header_added:
                self._separator("▼ 과거 기록")
                past_header_added = True
            stamp = n["created_at"][:16]
            edited = f"  (수정 {n['updated_at'][5:16]})" if n["updated_at"] != n["created_at"] else ""
            deleted = "  [삭제됨]" if n["deleted_at"] else ""
            item = QListWidgetItem(f"{stamp}{edited}{deleted}\n{n['body']}")
            item.setData(Qt.UserRole, n["id"])
            item.setData(Qt.UserRole + 1, bool(n["deleted_at"]))
            if n["deleted_at"]:
                item.setForeground(QBrush(QColor("#aaa")))
                f = QFont()
                f.setStrikeOut(True)
                item.setFont(f)
            elif not is_current:
                item.setForeground(QBrush(QColor("#777")))
            self.timeline.addItem(item)

    def _separator(self, text):
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        item.setForeground(QBrush(QColor("#1f3a5f")))
        f = QFont()
        f.setBold(True)
        item.setFont(f)
        self.timeline.addItem(item)

    def _selected(self):
        it = self.timeline.currentItem()
        if not it or it.data(Qt.UserRole) is None:
            QMessageBox.information(self, "안내", "먼저 목록에서 기록을 선택해 주세요.")
            return None
        return it

    def _edit_note(self):
        it = self._selected()
        if not it:
            return
        nid = it.data(Qt.UserRole)
        if it.data(Qt.UserRole + 1):
            return QMessageBox.information(self, "안내", "삭제된 기록입니다. 삭제 취소 후 수정하세요.")
        cur = it.text().split("\n", 1)[1]
        text, ok = QInputDialog.getMultiLineText(self, "기록 수정",
                                                 "수정 전 내용은 '수정 이력'에 보관됩니다.", cur)
        if ok and text.strip():
            self.repo.edit_note(nid, text)
            self.saved = True
            self._load_notes()

    def _delete_note(self):
        it = self._selected()
        if not it:
            return
        nid = it.data(Qt.UserRole)
        if it.data(Qt.UserRole + 1):
            self.repo.restore_note(nid)
        else:
            if QMessageBox.question(self, "기록 삭제",
                                    "이 기록을 목록에서 숨깁니다.\n(완전히 지워지지 않으며 '삭제된 기록도 보기'에서 되살릴 수 있습니다.)"
                                    ) != QMessageBox.Yes:
                return
            self.repo.delete_note(nid)
        self.saved = True
        self._load_notes()

    def _history(self):
        it = self._selected()
        if not it:
            return
        revs = self.repo.note_revisions(it.data(Qt.UserRole))
        if not revs:
            return QMessageBox.information(self, "수정 이력", "수정된 적이 없는 기록입니다.")
        text = "\n\n".join(f"[{r['saved_at'][:16]} 수정 직전 내용]\n{r['body']}" for r in revs)
        QMessageBox.information(self, "수정 이력", text)
