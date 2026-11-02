import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import backup, exporters, report  # noqa: E402
from app.db import Repository  # noqa: E402
from app import migrate, secure_store  # noqa: E402
from app.secure_store import (CorruptFile, DeviceKeyUnavailable, NeedMigration, SecretRequired,  # noqa: E402
                              SecureStore, WrongPassword)
from tests.sample_data import populate  # noqa: E402


@pytest.fixture()
def repo(tmp_path):
    store = SecureStore(tmp_path / "t.gjdb")
    store.create()
    return Repository(store)


def test_encrypted_file_has_no_plaintext(repo):
    populate(repo, 3)
    raw = repo.store.path.read_bytes()
    assert "테스트환자".encode() not in raw
    assert b"SQLite format" not in raw


def _legacy(tmp_path, name="old.gjdb", password="비밀번호1234"):
    """이전 버전(비밀번호 방식) 데이터 파일을 만든다."""
    s = SecureStore(tmp_path / name)
    rec = s.create(password)
    r = Repository(s)
    populate(r, 5)
    cid = r.list_cases()[0]["id"]
    r.add_note(cid, "예전 진행 기록")
    r.delete_case(r.list_cases()[1]["id"])  # 휴지통 상태도 보존되는지 확인
    s.close()
    return tmp_path / name, rec


def test_new_store_opens_without_password(tmp_path):
    s = SecureStore(tmp_path / "a.gjdb")
    rec = s.create()
    Repository(s).add_case({"patient": "가상A"})
    s.close()
    assert b"GJ02" == (tmp_path / "a.gjdb").read_bytes()[:4]
    assert "가상A".encode() not in (tmp_path / "a.gjdb").read_bytes()
    s2 = SecureStore(tmp_path / "a.gjdb")
    s2.open(device=True)  # 비밀번호 없이 열림
    assert Repository(s2).counts()["total"] == 1
    s3 = SecureStore(tmp_path / "a.gjdb")
    s3.open(recovery_key=rec.lower())  # 복구 키로도 열림
    assert Repository(s3).counts()["total"] == 1


def test_other_pc_needs_recovery_key_then_binds(tmp_path, monkeypatch):
    s = SecureStore(tmp_path / "a.gjdb")
    rec = s.create()
    Repository(s).add_case({"patient": "가상A"})
    s.close()

    def fail(_):
        raise OSError("다른 PC")
    monkeypatch.setattr(secure_store, "dpapi_unprotect", fail)
    s2 = SecureStore(tmp_path / "a.gjdb")
    with pytest.raises(DeviceKeyUnavailable):
        s2.open(device=True)
    with pytest.raises(WrongPassword):
        s2.open(recovery_key="AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA")
    s2.open(recovery_key=rec)
    s2.set_device_key()  # 이 PC에 연결
    s2.close()
    monkeypatch.undo()
    s3 = SecureStore(tmp_path / "a.gjdb")
    s3.open(device=True)
    assert Repository(s3).counts()["total"] == 1


def test_legacy_requires_migration_then_data_identical(tmp_path):
    path, rec = _legacy(tmp_path)
    with pytest.raises(NeedMigration):
        SecureStore(path).open(device=True)
    s = SecureStore(path)
    s.open(password="비밀번호1234")
    before = migrate._fingerprint(s.conn)
    s.close()
    info = migrate.migrate_legacy(path, "비밀번호1234", folder=tmp_path / "전환전")
    assert list((tmp_path / "전환전").glob("*old.gjdb"))  # 원본이 그대로 보관됨
    s2 = SecureStore(path)
    s2.open(device=True)
    assert migrate._fingerprint(s2.conn) == before  # 환자 정보·기록·휴지통까지 동일
    r = Repository(s2)
    assert r.counts()["total"] == 5 and len(r.trash()) == 1
    s2.close()
    # 기존 복구 키는 계속 유효
    s3 = SecureStore(path)
    s3.open(recovery_key=rec)
    assert migrate._fingerprint(s3.conn) == before
    assert info["recovery_key"] is None


def test_legacy_migration_with_recovery_key_and_wrong_secret(tmp_path):
    path, rec = _legacy(tmp_path)
    original = path.read_bytes()
    with pytest.raises(WrongPassword):
        migrate.migrate_legacy(path, "틀린비밀번호", folder=tmp_path / "f")
    assert path.read_bytes() == original  # 실패해도 원본 그대로
    info = migrate.migrate_legacy(path, rec, folder=tmp_path / "f")
    assert info["recovery_key"] == rec
    SecureStore(path).open(device=True)


def test_migration_failure_restores_original(tmp_path, monkeypatch):
    path, _ = _legacy(tmp_path)
    original = path.read_bytes()
    monkeypatch.setattr(SecureStore, "set_device_key",
                        lambda self: (_ for _ in ()).throw(RuntimeError("강제 실패")))
    with pytest.raises(migrate.MigrationError):
        migrate.migrate_legacy(path, "비밀번호1234", folder=tmp_path / "f")
    assert path.read_bytes() == original
    monkeypatch.undo()
    s = SecureStore(path)
    s.open(password="비밀번호1234")  # 여전히 예전 방식으로 열림
    assert Repository(s).counts()["total"] == 5


def test_corrupt_main_falls_back_to_prev(tmp_path):
    s = SecureStore(tmp_path / "a.gjdb")
    s.create()
    r = Repository(s)
    r.add_case({"patient": "가상A"})
    r.add_case({"patient": "가상B"})
    s.close()
    p = tmp_path / "a.gjdb"
    data = bytearray(p.read_bytes())
    data[-5] ^= 0xFF  # 본문 손상
    p.write_bytes(bytes(data))
    s2 = SecureStore(p)
    s2.open(device=True)
    assert s2.recovered_from_prev
    assert Repository(s2).counts()["total"] == 1  # 직전 저장 상태


def test_case_numbers_and_duplicates(repo):
    a = repo.add_case({"patient": "홍가상", "insurer": "A보험"})
    b = repo.add_case({"patient": "홍가상", "insurer": "B보험"})
    c = repo.add_case({"patient": "홍가상", "insurer": "A보험", "surgery_date": "2026-05-01"})
    nos = [repo.get_case(i)["case_no"] for i in (a, b, c)]
    assert len(set(nos)) == 3 and nos[0].endswith("0001") and nos[2].endswith("0003")


def test_notes_accumulate_and_never_lost(repo):
    cid = repo.add_case({"patient": "가상"}, "첫 기록")
    repo.add_note(cid, "둘째 기록")
    nid = repo.notes(cid)[0]["id"]
    repo.edit_note(nid, "둘째 기록(수정)")
    assert repo.note_revisions(nid)[0]["body"] == "둘째 기록"
    repo.delete_note(nid)
    assert len(repo.notes(cid)) == 1
    assert len(repo.notes(cid, include_deleted=True)) == 2
    repo.restore_note(nid)
    assert len(repo.notes(cid)) == 2


def test_closed_and_filters(repo):
    populate(repo, 8)
    c = repo.counts()
    assert c["total"] == 9 and c["open"] + c["closed"] == 9
    assert all(r["result"] == "" for r in repo.list_cases(view="open"))
    assert all(r["result"] != "" for r in repo.list_cases(view="closed"))
    assert len(repo.list_cases(search="테스트환자01")) == 2  # 같은 환자 2건
    assert repo.list_cases(search="%")  == []  # 와일드카드 이스케이프


def test_trash_restore(repo):
    cid = repo.add_case({"patient": "가상"}, "x")
    repo.delete_case(cid)
    assert repo.counts()["total"] == 0 and len(repo.trash()) == 1
    repo.restore_case(cid)
    assert repo.counts()["total"] == 1


def _force_dates(repo, cid, created, updated=None, closed=None):
    repo.conn.execute("UPDATE cases SET created_at=?, updated_at=?, closed_at=? WHERE id=?",
                      (created, updated or created, closed, cid))
    repo.conn.execute("UPDATE notes SET created_at=?, updated_at=? WHERE case_id=?",
                      (created, updated or created, cid))


def test_weekly_report_categories_and_diff(repo):
    old = repo.add_case({"patient": "유지환자", "status": "접수"}, "예전 기록")
    chg = repo.add_case({"patient": "변경환자", "status": "접수"}, "예전 기록")
    fin = repo.add_case({"patient": "종결환자", "status": "접수"}, "예전 기록")
    for c in (old, chg, fin):
        _force_dates(repo, c, "2026-10-01 09:00:00")
    # 1주차 보고서 확정
    r1 = report.build_report(repo, date(2026, 10, 12), date(2026, 10, 18))
    assert r1["counts"]["unchanged"] == 3 and r1["totals"]["open"] == 3
    repo.save_report(r1)
    # 2주차에 변경 발생
    repo.update_case(chg, {"status": "서류 요청"})
    repo.add_note(chg, "서류 요청함")
    repo.update_case(fin, {"result": "지급"})
    new = repo.add_case({"patient": "신규환자"}, "신규")
    repo.conn.execute("UPDATE cases SET updated_at='2026-10-20 10:00:00', created_at='2026-10-20 10:00:00' WHERE id=?", (new,))
    repo.conn.execute("UPDATE notes SET created_at='2026-10-20 10:00:00' WHERE case_id=?", (new,))
    repo.conn.execute("UPDATE cases SET updated_at='2026-10-21 10:00:00' WHERE id=?", (chg,))
    repo.conn.execute("UPDATE notes SET created_at='2026-10-21 10:00:00' WHERE case_id=? AND body=?", (chg, "서류 요청함"))
    repo.conn.execute("UPDATE cases SET closed_at='2026-10-22 10:00:00', updated_at='2026-10-22 10:00:00' WHERE id=?", (fin,))
    r2 = report.build_report(repo, date(2026, 10, 19), date(2026, 10, 25))
    by = {c["patient"]: c for c in r2["cases"]}
    assert by["유지환자"]["category"] == "unchanged"  # 변경 없어도 누락되지 않음
    assert by["변경환자"]["category"] == "changed"
    assert by["종결환자"]["category"] == "closed"
    assert by["신규환자"]["category"] == "new"
    assert any("접수 → 서류 요청" in x for x in by["변경환자"]["changes"])
    assert r2["delta"] == {"total": 1, "open": 0, "closed": 1}
    # 보고서 본문 스냅샷은 이후 데이터가 바뀌어도 변하지 않음
    rid = repo.save_report(r2)
    repo.update_case(chg, {"patient": "이름바뀜"})
    assert [c["patient"] for c in repo.get_report(rid)["cases"] if c["case_no"] == by["변경환자"]["case_no"]] == ["변경환자"]


def test_mask_and_exports(repo, tmp_path):
    populate(repo, 5)
    rep = report.build_report(repo, *report.default_period())
    assert report.mask_name("김철수") == "김○○" and report.mask_name("남") == "남"
    for mask in (False, True):
        x = tmp_path / f"r{mask}.xlsx"
        p = tmp_path / f"r{mask}.pdf"
        exporters.write_xlsx(rep, x, mask)
        exporters.write_pdf(rep, p, mask)
        assert x.stat().st_size > 2000 and p.read_bytes()[:4] == b"%PDF"
    html = report.report_html(rep, True)
    assert "테스트환자01" not in html and "테○○○○○" in html


def test_backup_restore_roundtrip(repo, tmp_path):
    populate(repo, 4)
    dest = backup.manual_backup(repo.store, tmp_path / "b1")
    info = backup.inspect_backup(dest)  # 이 PC에서는 비밀번호·키 없이 자동으로 열림
    assert info["total"] == 5
    repo.add_case({"patient": "백업후추가"})
    assert repo.counts()["total"] == 6
    safety = backup.restore(repo.store, info["plain"], folder=tmp_path / "bk")
    assert repo.counts()["total"] == 5
    assert backup.inspect_backup(safety)["total"] == 6  # 복원 전 상태가 보관됨


def test_backup_opens_elsewhere_only_with_recovery_key(tmp_path, monkeypatch):
    s = SecureStore(tmp_path / "a.gjdb")
    rec = s.create()
    populate(Repository(s), 3)
    dest = backup.manual_backup(s, tmp_path / "bk")
    monkeypatch.setattr(secure_store, "dpapi_unprotect",
                        lambda _: (_ for _ in ()).throw(OSError("다른 PC")))
    with pytest.raises(SecretRequired):
        backup.inspect_backup(dest)
    with pytest.raises(WrongPassword):
        backup.inspect_backup(dest, secret="AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA")
    assert backup.inspect_backup(dest, secret=rec)["total"] == 4


def test_old_version_backup_still_restorable(tmp_path):
    path, rec = _legacy(tmp_path)
    old_backup = tmp_path / "old_backup.gjbak"
    old_backup.write_bytes(path.read_bytes())  # 이전 버전이 만든 백업과 같은 형식
    with pytest.raises(SecretRequired):
        backup.inspect_backup(old_backup)
    assert backup.inspect_backup(old_backup, secret="비밀번호1234")["total"] == 5
    assert backup.inspect_backup(old_backup, secret=rec)["total"] == 5
    with pytest.raises(WrongPassword):
        backup.inspect_backup(old_backup, secret="틀림")


def test_auto_backup_prunes(repo, tmp_path):
    for _ in range(4):
        backup.auto_backup(repo.store, keep=2, folder=tmp_path / "ab")
        import time; time.sleep(1.05)
    assert len(list((tmp_path / "ab").glob("*.gjbak"))) == 2


def test_drafts(repo):
    repo.set_draft("case:1", "작성 중")
    assert repo.get_draft("case:1") == "작성 중"
    repo.set_draft("case:1", "  ")
    assert repo.get_draft("case:1") == ""
