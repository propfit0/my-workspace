from PySide6.QtCore import QDate
from PySide6.QtWidgets import QCheckBox, QDateEdit, QHBoxLayout, QWidget


class OptionalDateEdit(QWidget):
    """날짜 선택(달력). 체크를 끄면 '미정(공란)'."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.check = QCheckBox("날짜 지정")
        self.edit = QDateEdit()
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd")
        self.edit.setDate(QDate.currentDate())
        self.edit.setEnabled(False)
        self.check.toggled.connect(self.edit.setEnabled)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.check)

    def value(self) -> str:
        return self.edit.date().toString("yyyy-MM-dd") if self.check.isChecked() else ""

    def set_value(self, iso: str):
        d = QDate.fromString(iso or "", "yyyy-MM-dd")
        self.check.setChecked(d.isValid())
        if d.isValid():
            self.edit.setDate(d)
