"""이전 버전(비밀번호 방식) 데이터를 비밀번호 없는 방식으로 안전하게 전환한다.

순서: ① 원본 그대로 복사 보관 → ② 변환 → ③ 다시 열어 내용 동일 여부 검증 → 실패하면 원본 복구.
"""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path

from .paths import data_dir
from .secure_store import (CorruptFile, NeedMigration, SecureStore, WrongPassword)


class MigrationError(Exception):
    pass


def _fingerprint(conn) -> str:
    h = hashlib.sha256()
    for line in conn.iterdump():
        h.update(line.encode("utf-8"))
    return h.hexdigest()


def migrate_legacy(path: Path, secret: str, folder: Path | None = None) -> dict:
    """secret: 예전 비밀번호 또는 복구 키. 성공하면 {'recovery_key': 입력한 복구 키 또는 None}."""
    path = Path(path)
    folder = Path(folder) if folder else data_dir() / "전환전_백업"
    store = SecureStore(path)
    used_recovery = None
    try:
        store.open(password=secret)
    except WrongPassword:
        store.open(recovery_key=secret)  # 둘 다 틀리면 WrongPassword 가 그대로 올라간다
        used_recovery = secret
    before = _fingerprint(store.conn)

    # ① 원본 보관(전환 도중 무슨 일이 생겨도 되돌릴 수 있도록)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    originals = {}
    for src in (path, store.prev_path):
        if src.exists():
            originals[src] = src.read_bytes()
            shutil.copyfile(src, folder / f"{stamp}_{src.name}")

    try:
        store.set_device_key()          # ② 변환
        store.close()
        check = SecureStore(path)       # ③ 검증
        check.open(device=True)
        after = _fingerprint(check.conn)
        check.close()
        if after != before:
            raise MigrationError("전환 후 내용이 원본과 일치하지 않습니다.")
    except Exception as exc:  # noqa: BLE001
        for src, data in originals.items():  # 원본 복구
            src.write_bytes(data)
        if isinstance(exc, MigrationError):
            raise
        raise MigrationError(f"전환 중 오류가 발생하여 원본을 그대로 유지했습니다. ({type(exc).__name__})") from exc
    return {"recovery_key": used_recovery, "backup_folder": folder}
