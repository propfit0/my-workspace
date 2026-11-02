"""복구 키 안내와, 예외적인 상황(이전 버전 데이터 전환 / 다른 PC에서 열기)에서만 뜨는 창.

평상시에는 아무 창도 뜨지 않고 바로 메인 화면이 열린다.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from ..migrate import MigrationError, migrate_legacy
from ..paths import APP_TITLE
from ..secure_store import CorruptFile, SecureStore, WrongPassword


class RecoveryKeyDialog(QDialog):
    """복구 키 표시. must_confirm=True 이면 보관 확인 후에만 닫힌다."""

    def __init__(self, key: str, parent=None, must_confirm: bool = False):
        super().__init__(parent)
        self.key = key
        self.must_confirm = must_confirm
        self.setWindowTitle("복구 키")
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "<b>복구 키</b>입니다. 이 PC를 바꾸거나 Windows를 다시 설치한 뒤 데이터·백업을 열 때 필요합니다.<br>"
            "종이에 적거나 USB에 저장해 <b>안전한 곳에 따로 보관</b>하세요."))
        box = QLineEdit(key)
        box.setReadOnly(True)
        box.setAlignment(Qt.AlignCenter)
        box.setStyleSheet("font-family: Consolas; font-size: 13pt; padding: 10px;")
        lay.addWidget(box)
        row = QHBoxLayout()
        b1 = QPushButton("클립보드에 복사")
        b1.clicked.connect(lambda: QApplication.clipboard().setText(key))
        b2 = QPushButton("파일로 저장(USB 등)")
        b2.clicked.connect(self._save)
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addLayout(row)
        self.btn = QPushButton("확인")
        self.btn.setObjectName("primary")
        self.btn.clicked.connect(self.accept)
        if must_confirm:
            self.ok = QCheckBox("복구 키를 안전한 곳에 보관했습니다.")
            lay.addWidget(self.ok)
            self.btn.setEnabled(False)
            self.ok.toggled.connect(self.btn.setEnabled)
        lay.addWidget(self.btn)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "복구 키 저장", "고운하지_복구키.txt", "텍스트 (*.txt)")
        if path:
            Path(path).write_text(f"{APP_TITLE} 복구 키\n{self.key}\n", encoding="utf-8")

    def reject(self):
        if not self.must_confirm:
            super().reject()


class LegacyUnlockDialog(QDialog):
    """이전 버전(비밀번호 방식) 데이터를 한 번만 전환한다."""

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path
        self.result_info: dict | None = None
        self.setWindowTitle(APP_TITLE)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        t = QLabel("데이터 전환 (한 번만)")
        t.setObjectName("title")
        lay.addWidget(t)
        msg = QLabel(
            "이전 버전의 비밀번호로 보호된 데이터가 있습니다.<br>"
            "<b>기존 비밀번호를 한 번만 입력</b>하면, 앞으로는 비밀번호 없이 바로 열립니다.<br>"
            "<span style='color:#777'>· 전환 전에 원본을 <b>전환전_백업</b> 폴더에 그대로 보관합니다.<br>"
            "· 전환 후 내용이 같은지 검증하고, 문제가 있으면 원본을 그대로 유지합니다.<br>"
            "· 비밀번호를 잊었다면 복구 키를 입력해도 됩니다.</span>")
        msg.setWordWrap(True)
        lay.addWidget(msg)
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        self.secret.setPlaceholderText("기존 비밀번호 (또는 복구 키)")
        lay.addWidget(self.secret)
        self.err = QLabel("")
        self.err.setStyleSheet("color:#a33")
        self.err.setWordWrap(True)
        lay.addWidget(self.err)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("종료")
        cancel.clicked.connect(self.reject)
        self.go = QPushButton("전환하고 열기")
        self.go.setObjectName("primary")
        self.go.setDefault(True)
        self.go.clicked.connect(self._submit)
        row.addWidget(cancel)
        row.addWidget(self.go)
        lay.addLayout(row)

    def _submit(self):
        text = self.secret.text()
        if not text:
            return
        try:
            self.result_info = migrate_legacy(self.path, text)
        except WrongPassword:
            self.err.setText("비밀번호(또는 복구 키)가 올바르지 않습니다.")
            self.secret.clear()
            return
        except (MigrationError, CorruptFile) as exc:
            self.err.setText(str(exc))
            return
        self.accept()


class RecoveryOpenDialog(QDialog):
    """다른 PC·다른 Windows 계정의 파일 등, 자동으로 열 수 없을 때 복구 키로 연다."""

    def __init__(self, store: SecureStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.key_used = ""
        self.setWindowTitle(APP_TITLE)
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        t = QLabel("복구 키 필요")
        t.setObjectName("title")
        lay.addWidget(t)
        msg = QLabel(
            "이 데이터 파일은 <b>다른 PC 또는 다른 Windows 계정</b>에서 만들어져 자동으로 열 수 없습니다.<br>"
            "복구 키를 입력하면 열리고, 이후에는 이 PC에서 비밀번호 없이 열립니다.")
        msg.setWordWrap(True)
        lay.addWidget(msg)
        self.key = QLineEdit()
        self.key.setPlaceholderText("XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
        lay.addWidget(self.key)
        self.err = QLabel("")
        self.err.setStyleSheet("color:#a33")
        lay.addWidget(self.err)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("종료")
        cancel.clicked.connect(self.reject)
        go = QPushButton("열기")
        go.setObjectName("primary")
        go.setDefault(True)
        go.clicked.connect(self._submit)
        row.addWidget(cancel)
        row.addWidget(go)
        lay.addLayout(row)

    def _submit(self):
        try:
            self.store.open(recovery_key=self.key.text())
            self.store.set_device_key()
            self.key_used = self.key.text().strip()
            self.accept()
        except WrongPassword as exc:
            self.err.setText(str(exc))
        except CorruptFile as exc:
            self.err.setText(str(exc))


def ask_secret(parent, title: str, label: str) -> str | None:
    """백업 복원 시 복구 키(또는 예전 비밀번호) 입력."""
    from PySide6.QtWidgets import QInputDialog
    text, ok = QInputDialog.getText(parent, title, label, QLineEdit.Password)
    return text if ok else None


__all__ = ["RecoveryKeyDialog", "LegacyUnlockDialog", "RecoveryOpenDialog", "ask_secret", "QMessageBox"]
