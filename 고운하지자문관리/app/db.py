"""사건·진행기록·보고서 저장소(Repository)."""
from __future__ import annotations

import json
from datetime import datetime

from .secure_store import SecureStore

DEFAULT_STATUSES = ["접수", "서류 요청", "자문 진행 중", "의견서 전달",
                    "병원 회신 대기", "보험사 심사 중", "추가 자료 요청"]
DEFAULT_RESULTS = ["지급", "일부 지급", "부지급", "청구 철회", "기타 종결"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_no TEXT UNIQUE,
    patient TEXT NOT NULL DEFAULT '',
    insurer TEXT NOT NULL DEFAULT '',
    surgery_date TEXT NOT NULL DEFAULT '',
    consult_date TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS case_revisions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    saved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS note_revisions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    saved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    created_at TEXT NOT NULL,
    snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drafts(key TEXT PRIMARY KEY, body TEXT NOT NULL, saved_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_notes_case ON notes(case_id);
"""

CASE_FIELDS = ("patient", "insurer", "surgery_date", "consult_date", "status", "result")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _like(text: str) -> str:
    esc = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


class Repository:
    def __init__(self, store: SecureStore):
        self.store = store
        self.conn.executescript(SCHEMA)
        self.store.save()

    @property
    def conn(self):
        return self.store.conn

    def _commit(self):
        self.store.save()

    # ---- 설정 -------------------------------------------------------
    def get_setting(self, key, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                          (key, json.dumps(value, ensure_ascii=False)))
        self._commit()

    def statuses(self):
        return self.get_setting("statuses", DEFAULT_STATUSES)

    def results(self):
        return self.get_setting("results", DEFAULT_RESULTS)

    # ---- 사건 -------------------------------------------------------
    def _next_case_no(self, year: int) -> str:
        row = self.conn.execute(
            "SELECT case_no FROM cases WHERE case_no LIKE ? ORDER BY case_no DESC LIMIT 1",
            (f"{year}-%",)).fetchone()
        seq = int(row["case_no"].split("-")[1]) + 1 if row else 1
        return f"{year}-{seq:04d}"

    def add_case(self, data: dict, first_note: str = "") -> int:
        t = now()
        vals = {k: (data.get(k) or "").strip() for k in CASE_FIELDS}
        closed_at = t if vals["result"] else None
        case_no = self._next_case_no(int(t[:4]))
        cur = self.conn.execute(
            "INSERT INTO cases(case_no,patient,insurer,surgery_date,consult_date,status,result,"
            "created_at,updated_at,closed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (case_no, vals["patient"], vals["insurer"], vals["surgery_date"],
             vals["consult_date"], vals["status"], vals["result"], t, t, closed_at))
        cid = cur.lastrowid
        if first_note.strip():
            self.conn.execute(
                "INSERT INTO notes(case_id,body,created_at,updated_at) VALUES(?,?,?,?)",
                (cid, first_note.strip(), t, t))
        self._commit()
        return cid

    def get_case(self, cid: int):
        return self.conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()

    def update_case(self, cid: int, data: dict):
        old = self.get_case(cid)
        t = now()
        snap = {k: old[k] for k in CASE_FIELDS}
        new = {k: (data.get(k) if k in data else old[k]) or "" for k in CASE_FIELDS}
        new = {k: v.strip() for k, v in new.items()}
        if new == snap:
            return
        self.conn.execute("INSERT INTO case_revisions(case_id,snapshot,saved_at) VALUES(?,?,?)",
                          (cid, json.dumps(snap, ensure_ascii=False), t))
        closed_at = old["closed_at"]
        if new["result"] and not old["result"]:
            closed_at = t
        elif not new["result"]:
            closed_at = None
        self.conn.execute(
            "UPDATE cases SET patient=?,insurer=?,surgery_date=?,consult_date=?,status=?,"
            "result=?,updated_at=?,closed_at=? WHERE id=?",
            (new["patient"], new["insurer"], new["surgery_date"], new["consult_date"],
             new["status"], new["result"], t, closed_at, cid))
        self._commit()

    def delete_case(self, cid: int):
        self.conn.execute("UPDATE cases SET deleted_at=? WHERE id=?", (now(), cid))
        self._commit()

    def restore_case(self, cid: int):
        self.conn.execute("UPDATE cases SET deleted_at=NULL WHERE id=?", (cid,))
        self._commit()

    def purge_case(self, cid: int):
        """휴지통의 사건을 영구 삭제한다(되돌릴 수 없음)."""
        self.conn.execute("DELETE FROM note_revisions WHERE note_id IN "
                          "(SELECT id FROM notes WHERE case_id=?)", (cid,))
        self.conn.execute("DELETE FROM notes WHERE case_id=?", (cid,))
        self.conn.execute("DELETE FROM case_revisions WHERE case_id=?", (cid,))
        self.conn.execute("DELETE FROM cases WHERE id=? AND deleted_at IS NOT NULL", (cid,))
        self._commit()

    def trash(self):
        return self.conn.execute(
            "SELECT * FROM cases WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()

    def list_cases(self, search="", view="all", status="", result=""):
        sql = ("SELECT c.*, (SELECT body FROM notes n WHERE n.case_id=c.id AND n.deleted_at IS NULL "
               "ORDER BY n.created_at DESC, n.id DESC LIMIT 1) AS latest_note "
               "FROM cases c WHERE c.deleted_at IS NULL")
        args: list = []
        if search.strip():
            sql += " AND (c.patient LIKE ? ESCAPE '\\' OR c.insurer LIKE ? ESCAPE '\\')"
            args += [_like(search.strip())] * 2
        if view == "open":
            sql += " AND c.result=''"
        elif view == "closed":
            sql += " AND c.result<>''"
        if status:
            sql += " AND c.status=?"
            args.append(status)
        if result:
            sql += " AND c.result=?"
            args.append(result)
        sql += " ORDER BY (c.result<>''), c.updated_at DESC, c.id DESC"
        return self.conn.execute(sql, args).fetchall()

    def counts(self):
        r = self.conn.execute(
            "SELECT COUNT(*) t, SUM(result='') o, SUM(result<>'') c "
            "FROM cases WHERE deleted_at IS NULL").fetchone()
        return {"total": r["t"] or 0, "open": r["o"] or 0, "closed": r["c"] or 0}

    def result_counts(self):
        return self.conn.execute(
            "SELECT result, COUNT(*) n FROM cases WHERE deleted_at IS NULL AND result<>'' "
            "GROUP BY result ORDER BY n DESC").fetchall()

    def status_counts(self):
        return self.conn.execute(
            "SELECT status, COUNT(*) n FROM cases WHERE deleted_at IS NULL AND result='' "
            "GROUP BY status ORDER BY n DESC").fetchall()

    # ---- 진행 기록 ---------------------------------------------------
    def notes(self, cid: int, include_deleted=False):
        sql = "SELECT * FROM notes WHERE case_id=?"
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        sql += " ORDER BY created_at DESC, id DESC"
        return self.conn.execute(sql, (cid,)).fetchall()

    def add_note(self, cid: int, body: str):
        body = body.strip()
        if not body:
            return None
        t = now()
        cur = self.conn.execute(
            "INSERT INTO notes(case_id,body,created_at,updated_at) VALUES(?,?,?,?)",
            (cid, body, t, t))
        self.conn.execute("UPDATE cases SET updated_at=? WHERE id=?", (t, cid))
        self.conn.execute("DELETE FROM drafts WHERE key=?", (f"case:{cid}",))
        self._commit()
        return cur.lastrowid

    def edit_note(self, nid: int, body: str):
        row = self.conn.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
        body = body.strip()
        if not row or not body or body == row["body"]:
            return
        t = now()
        self.conn.execute("INSERT INTO note_revisions(note_id,body,saved_at) VALUES(?,?,?)",
                          (nid, row["body"], t))
        self.conn.execute("UPDATE notes SET body=?, updated_at=? WHERE id=?", (body, t, nid))
        self.conn.execute("UPDATE cases SET updated_at=? WHERE id=?", (t, row["case_id"]))
        self._commit()

    def note_revisions(self, nid: int):
        return self.conn.execute(
            "SELECT * FROM note_revisions WHERE note_id=? ORDER BY id DESC", (nid,)).fetchall()

    def delete_note(self, nid: int):
        """기록은 지워지지 않고 '삭제됨' 표시만 된다(복구 가능)."""
        row = self.conn.execute("SELECT case_id FROM notes WHERE id=?", (nid,)).fetchone()
        t = now()
        self.conn.execute("UPDATE notes SET deleted_at=? WHERE id=?", (t, nid))
        if row:
            self.conn.execute("UPDATE cases SET updated_at=? WHERE id=?", (t, row["case_id"]))
        self._commit()

    def restore_note(self, nid: int):
        self.conn.execute("UPDATE notes SET deleted_at=NULL WHERE id=?", (nid,))
        self._commit()

    # ---- 임시 저장(초안) ---------------------------------------------
    def get_draft(self, key: str) -> str:
        row = self.conn.execute("SELECT body FROM drafts WHERE key=?", (key,)).fetchone()
        return row["body"] if row else ""

    def set_draft(self, key: str, body: str):
        if body.strip():
            self.conn.execute("INSERT OR REPLACE INTO drafts(key,body,saved_at) VALUES(?,?,?)",
                              (key, body, now()))
        else:
            self.conn.execute("DELETE FROM drafts WHERE key=?", (key,))
        self._commit()

    def clear_draft(self, key: str):
        self.conn.execute("DELETE FROM drafts WHERE key=?", (key,))
        self._commit()

    # ---- 보고서 ------------------------------------------------------
    def save_report(self, report: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO reports(period_start,period_end,created_at,snapshot) VALUES(?,?,?,?)",
            (report["period_start"], report["period_end"], now(),
             json.dumps(report, ensure_ascii=False)))
        self._commit()
        return cur.lastrowid

    def reports(self):
        return self.conn.execute(
            "SELECT id,period_start,period_end,created_at FROM reports "
            "ORDER BY period_end DESC, id DESC").fetchall()

    def get_report(self, rid: int):
        row = self.conn.execute("SELECT snapshot FROM reports WHERE id=?", (rid,)).fetchone()
        return json.loads(row["snapshot"]) if row else None

    def latest_report_before(self, start_iso: str):
        row = self.conn.execute(
            "SELECT snapshot FROM reports WHERE period_end<? ORDER BY period_end DESC, id DESC LIMIT 1",
            (start_iso,)).fetchone()
        return json.loads(row["snapshot"]) if row else None
