"""가상 데이터가 들어 있는 연습용 데이터 파일을 만든다.

실행: python -m tests.seed_demo <폴더>   
실제 데이터 폴더와는 완전히 분리된 폴더에만 만든다.
"""
import sys
from pathlib import Path

from app.db import Repository
from app.secure_store import SecureStore
from tests.sample_data import populate

if __name__ == "__main__":
    folder = Path(sys.argv[1])
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / "자문현황.gjdb"
    if f.exists():
        print("이미 연습용 데이터가 있습니다.")
    else:
        store = SecureStore(f)
        store.create()
        populate(Repository(store), 12)
        store.close()
        print("연습용 데이터 생성 완료.")
