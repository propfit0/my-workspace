"""주간 보고서 엑셀·PDF 저장."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .report import (CATEGORIES, CATEGORY_LABEL, COLUMNS, export_rows, period_text,
                     summary_lines)

NAVY = "1F3A5F"
TITLE = "고운하지흉부외과의원 보험 자문 주간 보고서"


# ---- 엑셀 ---------------------------------------------------------------
def write_xlsx(report: dict, path: Path, mask: bool):
    rows = export_rows(report, mask)
    wb = Workbook()
    thin = Side(style="thin", color="D5DAE1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor=NAVY)
    headers = ["구분", *COLUMNS, "지난 보고 대비 변경"]

    def table(ws, start_row, items):
        for j, h in enumerate(headers, 1):
            c = ws.cell(start_row, j, h)
            c.font = Font(name="맑은 고딕", bold=True, color="FFFFFF")
            c.fill = head_fill
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = border
        r = start_row + 1
        for key, cells, change in items:
            vals = [CATEGORY_LABEL[key], *cells, change]
            for j, v in enumerate(vals, 1):
                c = ws.cell(r, j, v)
                c.font = Font(name="맑은 고딕", size=10)
                c.alignment = Alignment(wrap_text=True, vertical="top")
                c.border = border
            r += 1
        for j, w in enumerate([8, 12, 14, 12, 12, 16, 14, 56, 36], 1):
            ws.column_dimensions[chr(64 + j)].width = w
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.freeze_panes = ws.cell(start_row + 1, 1)
        return r

    # 요약
    ws = wb.active
    ws.title = "요약"
    ws["A1"] = TITLE
    ws["A1"].font = Font(name="맑은 고딕", size=16, bold=True, color=NAVY)
    ws["A2"] = f"보고 기간: {period_text(report)}    작성: {report['generated_at'][:16]}"
    ws["A2"].font = Font(name="맑은 고딕", size=10, color="666666")
    r = 4
    for line in summary_lines(report):
        ws.cell(r, 1, line).font = Font(name="맑은 고딕", size=11)
        r += 1
    r += 1
    ws.cell(r, 1, "구분별 건수").font = Font(name="맑은 고딕", bold=True, color=NAVY)
    r += 1
    for key, title in CATEGORIES:
        ws.cell(r, 1, title).font = Font(name="맑은 고딕")
        ws.cell(r, 4, report["counts"][key]).font = Font(name="맑은 고딕")
        r += 1
    ws.column_dimensions["A"].width = 60

    # 이번 주 신규·변경·종결
    ws2 = wb.create_sheet("이번 주 변동")
    table(ws2, 1, [x for x in rows if x[0] != "unchanged"])
    # 진행 중 전체
    ws3 = wb.create_sheet("진행 중 전체")
    table(ws3, 1, [x for x in rows if x[0] != "closed"])
    wb.save(path)


# ---- PDF ----------------------------------------------------------------
_FONT_READY = False


def _register_fonts():
    global _FONT_READY
    if _FONT_READY:
        return
    fonts = Path("C:/Windows/Fonts")
    regular = next((fonts / n for n in ("malgun.ttf", "NanumGothic.ttf", "gulim.ttc") if (fonts / n).exists()), None)
    if regular is None:
        raise RuntimeError("한글 글꼴(맑은 고딕)을 찾을 수 없어 PDF를 만들 수 없습니다.")
    bold = fonts / "malgunbd.ttf"
    pdfmetrics.registerFont(TTFont("KR", str(regular)))
    pdfmetrics.registerFont(TTFont("KR-B", str(bold if bold.exists() else regular)))
    _FONT_READY = True


def _esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br/>"))


def write_pdf(report: dict, path: Path, mask: bool):
    _register_fonts()
    navy = colors.HexColor("#" + NAVY)
    base = ParagraphStyle("b", fontName="KR", fontSize=8.5, leading=11.5)
    small = ParagraphStyle("s", parent=base, fontSize=8, textColor=colors.HexColor("#a05a00"))
    head = ParagraphStyle("h", parent=base, fontName="KR-B", textColor=colors.white)
    h1 = ParagraphStyle("h1", fontName="KR-B", fontSize=17, textColor=navy, leading=22)
    h2 = ParagraphStyle("h2", fontName="KR-B", fontSize=11.5, textColor=navy, leading=16, spaceBefore=10,
                        keepWithNext=1)
    gray = ParagraphStyle("g", parent=base, textColor=colors.HexColor("#666666"))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("KR", 8)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawString(15 * mm, 8 * mm, "고운하지흉부외과의원 · 환자 정보 포함 문서 — 취급에 유의하십시오")
        canvas.drawRightString(landscape(A4)[0] - 15 * mm, 8 * mm, f"{doc.page}쪽")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=15 * mm,
                            rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=15 * mm,
                            title=TITLE, author="보험 자문")
    story = [Paragraph(TITLE, h1),
             Paragraph(f"보고 기간 {period_text(report)} · 작성 {report['generated_at'][:16]}"
                       f"{' · 환자명 마스킹' if mask else ''}", gray), Spacer(1, 4 * mm)]
    box = Table([[Paragraph("<br/>".join(_esc(x) for x in summary_lines(report)),
                            ParagraphStyle("sum", parent=base, fontSize=10, leading=15))]],
                colWidths=[doc.width])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F5F8")),
                             ("LINEBEFORE", (0, 0), (0, -1), 3, navy),
                             ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 7),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.append(box)

    rows = export_rows(report, mask)
    col_w = [32, 28, 22, 22, 30, 24, 0]
    col_w = [w * mm for w in col_w]
    col_w[-1] = doc.width - sum(col_w[:-1])
    for key, title in CATEGORIES:
        sel = [r for r in rows if r[0] == key]
        story.append(Paragraph(f"{title} ({len(sel)}건)", h2))
        if not sel:
            story.append(Paragraph("해당 없음", gray))
            continue
        data = [[Paragraph(h, head) for h in COLUMNS]]
        extra = []
        for _, cells, change in sel:
            data.append([Paragraph(_esc(v), base) for v in cells])
            if change:
                data.append([Paragraph("▸ 지난 보고 대비 변경: " + _esc(change), small)] + [""] * 6)
                extra.append(len(data) - 1)
        t = Table(data, colWidths=col_w, repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), navy), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#D5DAE1")),
                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        style += [("SPAN", (0, i), (-1, i)) for i in extra]
        t.setStyle(TableStyle(style))
        story.append(t)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
