import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """테스트가 실제 데이터 폴더(%APPDATA%\\고운하지자문)를 절대 건드리지 않도록 격리한다."""
    monkeypatch.setenv("GOUN_DATA_DIR", str(tmp_path / "_appdata"))
