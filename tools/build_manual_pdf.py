"""Build a readable English PDF handbook from maintained Markdown files.

Requires reportlab. Markdown remains the editable source.
"""
from html import escape
from pathlib import Path
import re
from textwrap import wrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "BACCARAT_AGENT_DEVELOPER_GUIDE.pdf"
SOURCES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
FONT_ROOT = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_ROOT / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_ROOT / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("DejaVuMono", str(FONT_ROOT / "DejaVuSansMono.ttf")))

NAVY = colors.HexColor("#14243C")
TEAL = colors.HexColor("#007B75")
INK = colors.HexColor("#243346")
MUTED = colors.HexColor("#5B6B80")
PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 90

styles = {
    "title": ParagraphStyle("Title", fontName="DejaVu-Bold", fontSize=23, leading=30, textColor=NAVY, spaceAfter=20),
    "h1": ParagraphStyle("H1", fontName="DejaVu-Bold", fontSize=14, leading=19, textColor=TEAL, spaceBefore=14, spaceAfter=8, keepWithNext=True),
    "h2": ParagraphStyle("H2", fontName="DejaVu-Bold", fontSize=11, leading=16, textColor=TEAL, spaceBefore=11, spaceAfter=6, keepWithNext=True),
    "h3": ParagraphStyle("H3", fontName="DejaVu-Bold", fontSize=9.5, leading=14, textColor=NAVY, spaceBefore=9, spaceAfter=5, keepWithNext=True),
    "body": ParagraphStyle("Body", fontName="DejaVu", fontSize=8.7, leading=13.4, textColor=INK, spaceAfter=6),
    "bullet": ParagraphStyle("Bullet", fontName="DejaVu", fontSize=8.5, leading=13, textColor=INK, leftIndent=16, firstLineIndent=-10, spaceAfter=4),
    "code": ParagraphStyle("Code", fontName="DejaVuMono", fontSize=7, leading=10, textColor=INK, leftIndent=7, rightIndent=7, spaceAfter=4),
    "cell": ParagraphStyle("Cell", fontName="DejaVu", fontSize=7.3, leading=10.4, textColor=INK),
    "cell_head": ParagraphStyle("CellHead", fontName="DejaVu-Bold", fontSize=7.3, leading=10.4, textColor=colors.white),
    "sub": ParagraphStyle("Sub", fontName="DejaVu", fontSize=11, leading=17, textColor=MUTED, spaceAfter=15),
}


def clean(value: str) -> str:
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = value.replace("**", "").replace(chr(96), "")
    return escape(value)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("DejaVu", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(45, 28, "BACCARAT ANALYTICS AGENT  |  DEVELOPER GUIDE")
    canvas.drawRightString(PAGE_W - 45, 28, f"Page {doc.page}")
    canvas.restoreState()


def add_table(story: list, raw_rows: list[str]):
    rows = [[item.strip() for item in line.strip().strip("|").split("|")] for line in raw_rows]
    if len(rows) < 2:
        return
    if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in rows[1]):
        rows.pop(1)
    cols = len(rows[0])
    if cols > 5 or any(len(row) != cols for row in rows):
        for row in rows:
            story.append(Paragraph(clean(" | ".join(row)), styles["body"]))
        return
    cell_rows = []
    for index, row in enumerate(rows):
        style = styles["cell_head"] if index == 0 else styles["cell"]
        cell_rows.append([Paragraph(clean(cell), style) for cell in row])
    table = Table(cell_rows, colWidths=[CONTENT_W / cols] * cols, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C5D3DC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([table, Spacer(1, 8)])


def add_code(story: list, lines: list[str]):
    for line in lines:
        chunks = wrap(line.expandtabs(4), 103, break_long_words=True,
                      break_on_hyphens=False, replace_whitespace=False,
                      drop_whitespace=False) or [""]
        for chunk in chunks:
            story.append(Preformatted(escape(chunk), styles["code"]))
    story.append(Spacer(1, 5))


def add_source(story: list, path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    in_code = False
    code_lines = []
    table_lines = []

    def flush_table():
        nonlocal table_lines
        if table_lines:
            add_table(story, table_lines)
            table_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("~~~") or stripped.startswith(chr(96) * 3):
            flush_table()
            if in_code:
                add_code(story, code_lines)
                code_lines = []
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(stripped)
            continue
        flush_table()
        if not stripped:
            story.append(Spacer(1, 3))
        elif stripped == "---":
            story.append(Spacer(1, 8))
        elif stripped.startswith("#"):
            depth = len(stripped) - len(stripped.lstrip("#"))
            story.append(Paragraph(clean(stripped[depth:].strip()),
                                   styles["h1" if depth == 1 else "h2" if depth == 2 else "h3"]))
        elif re.match(r"^[-*]\s", stripped):
            story.append(Paragraph("• " + clean(stripped[2:]), styles["bullet"]))
        elif re.match(r"^\d+\.\s", stripped):
            story.append(Paragraph(clean(stripped), styles["bullet"]))
        elif line.startswith("    "):
            add_code(story, [line[4:]])
        elif stripped.startswith(">"):
            story.append(Paragraph(clean(stripped[1:].strip()), styles["body"]))
        else:
            story.append(Paragraph(clean(stripped), styles["body"]))
    flush_table()
    if code_lines:
        add_code(story, code_lines)


def main():
    story = [
        Spacer(1, 85),
        Paragraph("BACCARAT<br/>MULTI-TABLE<br/>ANALYTICS AGENT", styles["title"]),
        Paragraph("Implementation and codebase handbook", styles["sub"]),
        Paragraph("Docker Compose • Python • Playwright • OpenCV • PostgreSQL • Excel", styles["body"]),
        Paragraph("Version 2.0 • 22 October 2026", styles["body"]),
        Spacer(1, 18),
        Paragraph("Scope: multi-table observation and historical reporting. "
                  "No automated betting or claim of a reliable next-round prediction. "
                  "Demo data is synthetic.", styles["body"]),
        PageBreak(),
        Paragraph("Contents", styles["h1"]),
    ]
    for source in SOURCES:
        story.append(Paragraph(clean(source.stem.replace("-", " ")), styles["body"]))
    for source in SOURCES:
        story.append(PageBreak())
        add_source(story, source)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=45,
                            rightMargin=45, topMargin=44, bottomMargin=45,
                            title="Baccarat Agent Developer Guide",
                            author="Baccarat Agent Project")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"created {OUTPUT}, sources={len(SOURCES)}")


if __name__ == "__main__":
    main()
