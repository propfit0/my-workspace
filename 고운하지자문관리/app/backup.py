"""백업·복원. 백업 파일은 암호화된 데이터 파일을 그대로 복사한 것이다."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .paths import backup_dir
from .secure_store import SecureStore, decrypt_any

EXT = ".gjbak"


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _prune(prefix: str, keep: int, folder: Path):
    files = sorted(folder.glob(f"{prefix}*{EXT}"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def auto_backup(store: SecureStore, keep: int = 30, folder: Path | None = None) -> Path:
    folder = folder or backup_dir()
    dest = folder / f"자동_{_stamp()}{EXT}"
    store.export_container(dest)
    _prune("자동_", keep, folder)
    return dest


def manual_backup(store: SecureStore, dest: Path) -> Path:
    dest = Path(dest)
    if dest.suffix != EXT:
        dest = dest.with_suffix(EXT)
    store.export_container(dest)
    return dest


def inspect_backup(path: Path, secret: str | None = None) -> dict:
    """백업 파일을 열어 내용을 요약한다(현재 데이터에는 영향 없음).

    secret 이 없으면 이 PC에서 자동으로 열어 보고, 안 되면 SecretRequired 가 발생한다.
    secret 은 복구 키(또는 이전 버전 백업의 예전 비밀번호).
    """
    blob = Path(path).read_bytes()
    _, _, plain = decrypt_any(blob, secret)
    conn = sqlite3.connect(":memory:")
    conn.deserialize(plain)
    try:
        r = conn.execute("SELECT COUNT(*), SUM(result=''), SUM(result<>'') "
                         "FROM cases WHERE deleted_at IS NULL").fetchone()
        reports = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    finally:
        conn.close()
    return {
        "plain": plain,
        "saved_at": datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        "total": r[0] or 0, "open": r[1] or 0, "closed": r[2] or 0, "reports": reports,
    }


def restore(store: SecureStore, plain: bytes, folder: Path | None = None) -> Path:
    """현재 데이터를 먼저 보관한 뒤 백업 내용으로 교체한다."""
    folder = folder or backup_dir()
    safety = folder / f"복원전_{_stamp()}{EXT}"
    store.export_container(safety)
    _prune("복원전_", 10, folder)
    store.replace_data(plain)
    return safety
