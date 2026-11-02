"""주간 보고서 생성(집계·구분·지난 보고서 비교)과 화면용 HTML."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape

from .db import Repository, now

CATEGORIES = [
    ("new", "이번 주 신규 등록"),
    ("changed", "이번 주 진행 내용 변경"),
    ("closed", "이번 주 처리 완료"),
    ("unchanged", "진행 중 (이번 주 변경 없음)"),
]
CATEGORY_LABEL = {
    "new": "신규", "changed": "변경", "closed": "종결", "unchanged": "유지",
}
FIELD_LABELS = [
    ("patient", "환자명"), ("insurer", "보험회사"), ("surgery_date", "수술일자"),
    ("consult_date", "자문일자"), ("status", "현재 진행상황"), ("result", "최종 처리결과"),
]
COLUMNS = ["환자명", "보험회사", "수술일자", "자문일자", "현재 진행상황", "최종 처리결과", "비고"]


def default_period(today: date | None = None) -> tuple[date, date]:
    """오늘이 속한 주의 월요일 ~ 일요일."""
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def mask_name(name: str) -> str:
    name = (name or "").strip()
    if len(name) <= 1:
        return name
    return name[0] + "○" * (len(name) - 1)


def _in(day: str | None, start: str, end: str) -> bool:
    return bool(day) and start <= day[:10] <= end


def _remark(notes_in_period: list[dict], latest: dict | None) -> str:
    items = notes_in_period or ([latest] if latest else [])
    return "\n".join(f"[{n['created_at'][5:10].replace('-', '/')}] {n['body']}" for n in items)


def _diff(cur: dict, prev: dict | None) -> list[str]:
    if prev is None:
        return []
    out = []
    for key, label in FIELD_LABELS:
        a, b = prev.get(key, ""), cur.get(key, "")
        if a != b:
            out.append(f"{label}: {a or '(공란)'} → {b or '(공란)'}")
    return out


def build_report(repo: Repository, start: date, end: date) -> dict:
    s, e = start.isoformat(), end.isoformat()
    prev_report = repo.latest_report_before(s)
    prev_map = {c["case_no"]: c for c in prev_report["cases"]} if prev_report else {}

    rows = repo.conn.execute(
        "SELECT * FROM cases WHERE deleted_at IS NULL AND substr(created_at,1,10)<=? "
        "ORDER BY created_at, id", (e,)).fetchall()

    total = len(rows)
    closed_by_end = [r for r in rows if r["closed_at"] and r["closed_at"][:10] <= e]
    totals = {"total": total, "closed": len(closed_by_end), "open": total - len(closed_by_end)}

    cases = []
    for r in rows:
        is_closed_by_end = bool(r["closed_at"]) and r["closed_at"][:10] <= e
        closed_in = is_closed_by_end and _in(r["closed_at"], s, e)
        if is_closed_by_end and not closed_in:
            continue  # 이전 기간에 이미 종결된 사건은 본문에서 제외(집계에는 포함)
        notes = [dict(n) for n in repo.notes(r["id"])]
        in_period = [n for n in reversed(notes) if _in(n["created_at"], s, e)]
        latest = notes[0] if notes else None
        is_new = _in(r["created_at"], s, e)
        edited = _in(r["updated_at"], s, e)
        if closed_in:
            cat = "closed"
        elif is_new:
            cat = "new"
        elif edited or in_period:
            cat = "changed"
        else:
            cat = "unchanged"
        d = {k: r[k] for k in ("case_no", "patient", "insurer", "surgery_date",
                               "consult_date", "status", "result")}
        # 종결 사건이 보고 기간 이후에 다시 바뀐 경우를 대비해, 기간 종료 시점 값 그대로가 아닌 현재 값을 사용
        d["category"] = cat
        d["remark"] = _remark(in_period, latest)
        prev = prev_map.get(r["case_no"])
        d["changes"] = _diff(d, prev)
        if prev is None and prev_report and not is_new:
            d["changes"].insert(0, "지난 보고서 이후 목록에 추가됨")
        cases.append(d)

    order = {k: i for i, (k, _) in enumerate(CATEGORIES)}
    cases.sort(key=lambda c: (order[c["category"]], c["case_no"]))
    counts = {k: sum(1 for c in cases if c["category"] == k) for k, _ in CATEGORIES}

    delta = None
    if prev_report:
        pt = prev_report["totals"]
        delta = {k: totals[k] - pt[k] for k in ("total", "open", "closed")}
    return {
        "version": 1,
        "period_start": s, "period_end": e,
        "generated_at": now(),
        "prev_period": [prev_report["period_start"], prev_report["period_end"]] if prev_report else None,
        "totals": totals, "delta": delta, "counts": counts, "cases": cases,
    }


# ---- 출력용 행 ---------------------------------------------------------
def export_rows(report: dict, mask: bool):
    """(구분 키, 표시용 행 리스트(7항목), 변경 요약) 목록."""
    out = []
    for c in report["cases"]:
        name = mask_name(c["patient"]) if mask else c["patient"]
        remark, changes = c["remark"], "; ".join(c["changes"])
        if mask and c["patient"].strip():
            # 비고·변경내용에 적힌 환자 이름도 함께 가린다
            remark = remark.replace(c["patient"].strip(), name)
            changes = changes.replace(c["patient"].strip(), name)
        out.append((c["category"], [name, c["insurer"], c["surgery_date"], c["consult_date"],
                                    c["status"], c["result"], remark], changes))
    return out


def period_text(report: dict) -> str:
    a = datetime.fromisoformat(report["period_start"])
    b = datetime.fromisoformat(report["period_end"])
    wk = "월화수목금토일"
    return f"{a:%Y.%m.%d}({wk[a.weekday()]}) ~ {b:%Y.%m.%d}({wk[b.weekday()]})"


def summary_lines(report: dict) -> list[str]:
    t, c, d = report["totals"], report["counts"], report["delta"]
    lines = [f"전체 자문 {t['total']}건  |  진행 중 {t['open']}건  |  처리 완료 {t['closed']}건",
             f"이번 주  신규 {c['new']}건 · 진행 내용 변경 {c['changed']}건 · 처리 완료 {c['closed']}건"]
    if d is not None:
        pp = report["prev_period"]
        lines.append(f"지난 보고({pp[0][5:].replace('-', '.')}~{pp[1][5:].replace('-', '.')}) 대비  "
                     f"전체 {d['total']:+d}건, 진행 중 {d['open']:+d}건, 처리 완료 {d['closed']:+d}건")
    else:
        lines.append("지난 보고서가 없어 이번 기간 기록을 기준으로 구분했습니다.")
    return lines


def report_html(report: dict, mask: bool) -> str:
    """화면 미리보기용 HTML."""
    navy = "#1f3a5f"
    parts = [f"<div style='font-family:Malgun Gothic;color:#222'>",
             f"<h2 style='color:{navy};margin-bottom:2px'>고운하지흉부외과의원 보험 자문 주간 보고서</h2>",
             f"<p style='color:#666;margin-top:0'>보고 기간 {escape(period_text(report))}"
             f" &nbsp;·&nbsp; 작성 {escape(report['generated_at'][:16])}"
             f"{' &nbsp;·&nbsp; 환자명 마스킹' if mask else ''}</p>",
             f"<div style='background:#f3f5f8;padding:8px 12px;border-left:4px solid {navy}'>"]
    parts += [f"{escape(x)}<br>" for x in summary_lines(report)]
    parts.append("</div>")
    rows = export_rows(report, mask)
    for key, title in CATEGORIES:
        sel = [r for r in rows if r[0] == key]
        parts.append(f"<h3 style='color:{navy};margin-bottom:4px'>{title} ({len(sel)}건)</h3>")
        if not sel:
            parts.append("<p style='color:#999'>해당 없음</p>")
            continue
        parts.append("<table border='0' cellspacing='0' cellpadding='5' width='100%' "
                     "style='border-collapse:collapse'>")
        parts.append(f"<tr style='background:{navy};color:white'>"
                     + "".join(f"<th align='left'>{h}</th>" for h in COLUMNS) + "</tr>")
        for _, cells, change in sel:
            tds = "".join(
                f"<td style='border-bottom:1px solid #ddd' valign='top'>"
                f"{escape(str(v)).replace(chr(10), '<br>')}</td>" for v in cells)
            parts.append(f"<tr>{tds}</tr>")
            if change:
                parts.append(f"<tr><td colspan='7' style='color:#a05a00;font-size:small;"
                             f"border-bottom:1px solid #ddd'>▸ 지난 보고 대비 변경: {escape(change)}</td></tr>")
        parts.append("</table>")
    parts.append("</div>")
    return "".join(parts)
