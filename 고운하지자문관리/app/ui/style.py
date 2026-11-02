NAVY = "#1f3a5f"

QSS = f"""
* {{ font-family: 'Malgun Gothic'; font-size: 10pt; color: #222; }}
QWidget {{ background: #fafafa; }}
QDialog, QMainWindow {{ background: #fafafa; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 15pt; font-weight: bold; color: {NAVY}; }}
QLabel#sub {{ color: #777; }}
QFrame#card {{ background: white; border: 1px solid #e3e6ea; border-radius: 8px; }}
QFrame#card QLabel {{ background: white; }}
QLabel#cardNum {{ font-size: 20pt; font-weight: bold; color: {NAVY}; }}
QLabel#cardLabel {{ color: #777; }}
QPushButton {{ background: white; border: 1px solid #c9ced6; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background: #f0f3f7; }}
QPushButton:disabled {{ color: #aaa; }}
QPushButton#primary {{ background: {NAVY}; color: white; border: 1px solid {NAVY}; font-weight: bold; }}
QPushButton#primary:hover {{ background: #2b4d7d; }}
QPushButton#danger {{ color: #a33; }}
QLineEdit, QComboBox, QDateEdit, QPlainTextEdit, QTextBrowser, QSpinBox, QListWidget {{
    background: white; border: 1px solid #d3d8df; border-radius: 6px; padding: 4px 6px; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {NAVY}; }}
QTableWidget {{ background: white; border: 1px solid #e3e6ea; border-radius: 8px;
    gridline-color: #eef0f3; selection-background-color: #dfe8f5; selection-color: #111; }}
QTableWidget::item {{ padding: 4px; }}
QHeaderView::section {{ background: {NAVY}; color: white; padding: 7px; border: none; font-weight: bold; }}
QRadioButton, QCheckBox {{ background: transparent; spacing: 6px; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px; border: 1px solid #9aa3af; background: white; }}
QRadioButton::indicator:checked {{ border: 1px solid {NAVY}; background: qradialgradient(cx:.5, cy:.5, radius:.5,
    fx:.5, fy:.5, stop:0 {NAVY}, stop:.55 {NAVY}, stop:.6 white, stop:1 white); }}
QCheckBox::indicator {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid #9aa3af; background: white; }}
QCheckBox::indicator:checked {{ border: 1px solid {NAVY}; background: {NAVY}; }}
QToolTip {{ background: white; color: #222; border: 1px solid #ccc; }}
"""
