"""가상의 테스트 데이터(실제 환자 정보 아님)."""
from __future__ import annotations

import sqlite3

INSURERS = ["가상손해보험", "테스트생명", "예시화재", "샘플해상", "연습생명"]
STATUSES = ["접수", "서류 요청", "자문 진행 중", "의견서 전달", "병원 회신 대기", "보험사 심사 중"]


def populate(repo, n: int = 12):
    """가상 사건 n건을 만든다. 일부는 종결, 일부는 같은 환자·다른 보험사."""
    ids = []
    for i in range(1, n + 1):
        name = f"테스트환자{i:02d}"
        ids.append(repo.add_case({
            "patient": name, "insurer": INSURERS[i % len(INSURERS)],
            "surgery_date": f"2026-0{1 + i % 9}-1{i % 9}", "consult_date": f"2026-0{1 + i % 9}-2{i % 8}",
            "status": STATUSES[i % len(STATUSES)],
            "result": "지급" if i % 4 == 0 else "",
        }, first_note=f"{name} 최초 접수. 가상 데이터입니다."))
    # 같은 환자가 다른 보험사에 청구한 경우
    ids.append(repo.add_case({"patient": "테스트환자01", "insurer": "예시화재",
                              "status": "접수"}, "동일 환자, 다른 보험사 청구(가상)"))
    return ids
