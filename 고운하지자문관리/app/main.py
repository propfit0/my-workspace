"""프로그램 시작점. 비밀번호 없이 바로 메인 화면이 열린다."""
from __future__ import annotations

import sys
import traceback
from datetime import datetime

from PySide6.QtCore import QLockFile
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from .db import Repository
from .paths import APP_TITLE, backup_dir, data_dir, data_file
from .secure_store import (CorruptFile, DeviceKeyUnavailable, NeedMigration, SecureStore,
                           WrongPassword)
from .ui.auth import LegacyUnlockDialog, RecoveryOpenDialog
from .ui.main_window import MainWindow
from .ui.style import QSS


def _install_excepthook():
    log = data_dir() / "오류기록.txt"

    def hook(etype, value, tb):
        try:  # 환자 정보가 들어갈 수 있는 값은 기록하지 않고 오류 종류와 위치만 남긴다
            frames = "".join(traceback.format_tb(tb))
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {etype.__name__}\n{frames}\n")
        except Exception:  # noqa: BLE001
            pass
        QMessageBox.critical(None, "오류",
                             "예기치 않은 오류가 발생했습니다.\n저장된 자료는 안전합니다.\n"
                             f"프로그램을 다시 실행해 주세요.\n\n({etype.__name__})")

    sys.excepthook = hook


def open_store(store: SecureStore) -> bool:
    """데이터를 연다. 평상시에는 아무 창도 뜨지 않는다. 열지 못하면 False."""
    if not store.exists():
        key = store.create()                      # 처음 실행: 질문 없이 새로 만든다
        Repository(store).set_setting("recovery_key", key)
        Repository(store).set_setting("first_run_notice", True)
        return True
    try:
        store.open(device=True)
    except NeedMigration:                         # 이전 버전(비밀번호) 데이터: 한 번만 전환
        dlg = LegacyUnlockDialog(store.path)
        if dlg.exec() != LegacyUnlockDialog.Accepted:
            return False
        store.open(device=True)
        repo = Repository(store)
        if dlg.result_info and dlg.result_info.get("recovery_key"):
            repo.set_setting("recovery_key", dlg.result_info["recovery_key"])
        QMessageBox.information(
            None, "전환 완료",
            "데이터를 비밀번호 없는 방식으로 전환했습니다. 모든 환자 정보와 진행 기록이 그대로입니다.\n\n"
            f"전환 전 원본은 아래 폴더에 보관했습니다.\n{dlg.result_info['backup_folder']}")
    except DeviceKeyUnavailable:                  # 다른 PC·다른 계정: 복구 키로 연 뒤 이 PC에 연결
        dlg = RecoveryOpenDialog(store)
        if dlg.exec() != RecoveryOpenDialog.Accepted:
            return False
        if dlg.key_used:
            Repository(store).set_setting("recovery_key", dlg.key_used)
    except (CorruptFile, WrongPassword) as exc:
        QMessageBox.critical(
            None, APP_TITLE,
            f"데이터 파일을 열 수 없습니다.\n({exc})\n\n"
            f"자동 백업 폴더의 백업 파일로 복원할 수 있습니다.\n{backup_dir()}")
        return False
    if store.recovered_from_prev:
        QMessageBox.warning(None, "데이터 복구",
                            "데이터 파일 일부가 손상되어 직전 저장 상태로 열었습니다.\n"
                            "마지막 저장 직전의 입력이 일부 보이지 않을 수 있으니 확인해 주세요.")
    return True


def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 10))
    app.setStyleSheet(QSS)
    app.setApplicationName(APP_TITLE)
    _install_excepthook()

    lock = QLockFile(str(data_dir() / "실행중.lock"))
    if not lock.tryLock(200):
        QMessageBox.information(None, APP_TITLE, "프로그램이 이미 실행 중입니다.\n작업 표시줄을 확인해 주세요.")
        return 0

    store = SecureStore(data_file())
    if not open_store(store):
        return 0
    win = MainWindow(store)
    win.show()
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
