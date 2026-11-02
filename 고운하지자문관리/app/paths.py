import os
from pathlib import Path

APP_TITLE = "고운하지흉부외과의원 보험 자문 현황"


def data_dir() -> Path:
    """데이터 폴더. 환경변수 GOUN_DATA_DIR 로 바꿀 수 있다(테스트용)."""
    env = os.environ.get("GOUN_DATA_DIR")
    base = Path(env) if env else Path(os.environ.get("APPDATA", str(Path.home()))) / "고운하지자문"
    base.mkdir(parents=True, exist_ok=True)
    return base


def data_file() -> Path:
    return data_dir() / "자문현황.gjdb"


def backup_dir() -> Path:
    p = data_dir() / "자동백업"
    p.mkdir(parents=True, exist_ok=True)
    return p
