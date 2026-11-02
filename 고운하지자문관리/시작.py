import sys


def selftest(folder):
    """exe 안에서 핵심 기능이 동작하는지 점검(GUI 없음, 지정한 임시 폴더에서만 작업)."""
    from pathlib import Path
    from app import backup, exporters, migrate, report
    from app.db import Repository
    from app.secure_store import SecureStore
    f = Path(folder)
    f.mkdir(parents=True, exist_ok=True)
    s = SecureStore(f / "t.gjdb")
    s.create()
    r = Repository(s)
    r.add_case({"patient": "점검환자", "insurer": "가상보험"}, "점검 기록")
    rep = report.build_report(r, *report.default_period())
    exporters.write_xlsx(rep, f / "t.xlsx", True)
    exporters.write_pdf(rep, f / "t.pdf", True)
    b = backup.manual_backup(s, f / "t")
    assert backup.inspect_backup(b)["total"] == 1
    s.close()
    s = SecureStore(f / "t.gjdb")
    s.open(device=True)  # 비밀번호 없이 열림
    assert Repository(s).counts()["total"] == 1
    s.close()
    # 이전 방식(비밀번호) 파일 → 전환
    old = SecureStore(f / "old.gjdb")
    old.create("pw-12345678")
    Repository(old).add_case({"patient": "예전환자"}, "예전 기록")
    old.close()
    migrate.migrate_legacy(f / "old.gjdb", "pw-12345678", folder=f / "전환전")
    s = SecureStore(f / "old.gjdb")
    s.open(device=True)
    assert Repository(s).counts()["total"] == 1
    print("SELFTEST OK")


def migrate_existing(folder, secret):
    """이미 있는 이전 방식 데이터 폴더를 전환하고 건수를 출력한다(시험용)."""
    from pathlib import Path
    from app import migrate
    from app.db import Repository
    from app.secure_store import SecureStore
    p = Path(folder) / "자문현황.gjdb"
    migrate.migrate_legacy(p, secret, folder=Path(folder) / "전환전_백업")
    s = SecureStore(p)
    s.open(device=True)
    c = Repository(s).counts()
    print("MIGRATED", c)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    elif len(sys.argv) > 3 and sys.argv[1] == "--migrate":
        try:
            migrate_existing(sys.argv[2], sys.argv[3])
        except Exception:  # noqa: BLE001  (시험용: 오류 창 대신 종료 코드로 알린다)
            sys.exit(2)
    else:
        from app.main import main
        sys.exit(main())
