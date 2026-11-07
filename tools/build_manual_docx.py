"""Build the English DOCX handbook from the maintained Markdown sources."""
from pathlib import Path
import re
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "BACCARAT_AGENT_DEVELOPER_GUIDE.docx"
chapters = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]

def clean_markdown(s):
    s = s.strip()
    s = re.sub(r'\*\*(.*?)\*\*', r'\1', s)
    s = s.replace('`','')
    return s

def set_repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    tblHeader = OxmlElement('w:tblHeader')
    tblHeader.set(qn('w:val'),'true')
    trPr.append(tblHeader)

def set_shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'),color)
    tcPr.append(shd)

def page_field(p):
    fld = OxmlElement('w:fldSimple')
    fld.set(qn('w:instr'), 'PAGE')
    p._p.append(fld)

def write_code(doc, code_lines):
    if not code_lines:
        return
    p = doc.add_paragraph(style='CodeBlock')
    for i,line in enumerate(code_lines):
        # wrap paths/CLI only visually, source markdown retains exact commands
        if len(line)>110:
            line = '\n'.join(line[j:j+108] for j in range(0,len(line),108))
        p.add_run(line + ('\n' if i+1 < len(code_lines) else ''))
    p.paragraph_format.keep_together = False

def add_table(doc, table_rows):
    if len(table_rows)<2: return
    cleaned=[[clean_markdown(v) for v in row] for row in table_rows]
    if cleaned[1] and all(re.match(r'^:?-{3,}:?$',v.replace(' ','')) for v in cleaned[1]):
        cleaned.pop(1)
    ncols=len(cleaned[0])
    if ncols>5:
        # long markdown tables are made paragraphs to avoid tiny PDF text
        for row in cleaned:
            doc.add_paragraph('  |  '.join(row), style='CodeBlock')
        return
    table=doc.add_table(rows=0, cols=ncols)
    table.style='Table Grid'
    table.alignment=WD_TABLE_ALIGNMENT.CENTER
    for ridx,row in enumerate(cleaned):
        cells=table.add_row().cells
        for c, value in enumerate(row[:ncols]):
            cells[c].text=value
            for p in cells[c].paragraphs:
                p.paragraph_format.space_after=Pt(2)
                for run in p.runs:
                    run.font.size=Pt(8.5)
                    if ridx==0:
                        run.bold=True;run.font.color.rgb=RGBColor(255,255,255)
            if ridx==0:
                set_shade(cells[c],'0F766E')
        if ridx==0: set_repeat_header(table.rows[-1])
    doc.add_paragraph('')


def main():
    doc=Document()
    section=doc.sections[0]
    section.top_margin=Inches(.75)
    section.bottom_margin=Inches(.75)
    section.left_margin=Inches(.85)
    section.right_margin=Inches(.75)
    section.header_distance=Inches(.32)
    section.footer_distance=Inches(.36)

    styles=doc.styles
    normal=styles['Normal']
    normal.font.name='Liberation Sans'
    normal.font.size=Pt(9.5)
    normal.font.color.rgb=RGBColor(36,51,70)
    normal.paragraph_format.space_after=Pt(6)
    normal.paragraph_format.line_spacing=1.15
    for name,size,color in [('Title',23,(18,45,70)),('Heading 1',15,(15,80,85)),('Heading 2',12,(16,95,98)),('Heading 3',10.5,(20,95,105))]:
        st=styles[name]
        st.font.name='Liberation Sans';st.font.size=Pt(size)
        st.font.bold=True
        st.font.color.rgb=RGBColor(*color)
        st.paragraph_format.space_before=Pt(12)
        st.paragraph_format.space_after=Pt(6)
        st.paragraph_format.keep_with_next=True
    code = styles.add_style('CodeBlock',1)
    code.font.name='DejaVu Sans Mono';code.font.size=Pt(7.3)
    code.font.color.rgb=RGBColor(36,61,76)
    code.paragraph_format.space_after=Pt(7)
    code.paragraph_format.left_indent=Inches(.08)
    code.paragraph_format.right_indent=Inches(.08)
    code.paragraph_format.line_spacing=1.05

    header=section.header.paragraphs[0]
    header.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    run=header.add_run('BACCARAT ANALYTICS AGENT  |  DEVELOPER GUIDE')
    run.font.size=Pt(7.7)
    run.font.color.rgb=RGBColor(82,102,120)
    footer=section.footer.paragraphs[0]
    footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run('Technical handbook • Page ').font.size=Pt(8)
    page_field(footer)

    cover=doc.add_paragraph()
    cover.alignment=WD_ALIGN_PARAGRAPH.LEFT
    cover.space_before=Pt(80)
    title=cover.add_run('BACCARAT\nMULTI-TABLE\nANALYTICS AGENT')
    title.font.name='Liberation Sans';title.font.size=Pt(27)
    title.bold=True;title.font.color.rgb=RGBColor(19,57,83)
    sub=doc.add_paragraph('IMPLEMENTATION AND CODEBASE HANDBOOK')
    sub.style='Subtitle'
    sub.runs[0].font.size=Pt(15)
    doc.add_paragraph('Docker Compose • Python • Playwright • OpenCV • PostgreSQL • Excel')
    doc.add_paragraph('Version 2.0 • 22 October 2026')
    p=doc.add_paragraph('SCOPE: Multi-table observation and historical reporting prototype. It does not place bets or claim to predict the next round. Demo data does not come from a real website.')
    p.paragraph_format.space_before=Pt(25)
    if (ROOT/'output/roi_preview.png').exists():
        doc.add_picture(str(ROOT/'output/roi_preview.png'),width=Inches(6.7))
        cap=doc.add_paragraph('Synthetic six-table image for ROI checks; not a real betting screen.')
        cap.alignment=WD_ALIGN_PARAGRAPH.CENTER
        for run in cap.runs:run.font.size=Pt(8)
    doc.add_page_break()
    doc.add_heading('CONTENTS AND READING ORDER', level=1)
    doc.add_paragraph('Run the demo first. Then read the source in this order: CLI, config, vision, browser, validator, adapter contract, pipeline, storage, analytics, and report. The Markdown files remain the editable source.')
    for c in chapters:
        doc.add_paragraph(c.stem.replace('-',' ').replace('_',' '),style='List Bullet')
    doc.add_paragraph('Configuration and source code are in the same project. Use this Word file for reading and the Markdown files for editing.')

    for source in chapters:
        doc.add_page_break()
        lines=source.read_text(encoding='utf-8').splitlines()
        in_code=False; code_lines=[]; table_rows=[]
        def flush_table():
            nonlocal table_rows
            if table_rows:
                add_table(doc,table_rows)
                table_rows=[]
        for line in lines:
            stripped=line.strip()
            if stripped.startswith('```'):
                flush_table()
                if in_code:
                    write_code(doc,code_lines)
                    code_lines=[]
                    in_code=False
                else:
                    in_code=True
                continue
            if in_code:
                code_lines.append(line)
                continue
            if stripped.startswith('|') and stripped.endswith('|'):
                table_rows.append([item.strip() for item in stripped.strip('|').split('|')])
                continue
            flush_table()
            if not stripped:continue
            if stripped.startswith('#'):
                depth=len(stripped)-len(stripped.lstrip('#'))
                heading=clean_markdown(stripped[depth:].strip())
                doc.add_heading(heading, level=max(1,min(3,depth)))
            elif stripped.startswith('>'):
                p=doc.add_paragraph(clean_markdown(stripped[1:]))
                p.paragraph_format.left_indent=Inches(.24)
                if p.runs: p.runs[0].italic=True
            elif stripped.startswith(('- ', '* ')):
                doc.add_paragraph(clean_markdown(stripped[2:]),style='List Bullet')
            elif re.match(r'^\d+\.\s',stripped):
                doc.add_paragraph(clean_markdown(re.sub(r'^\d+\.\s','',stripped)),style='List Number')
            else:
                doc.add_paragraph(clean_markdown(stripped))
        flush_table()
        if code_lines:write_code(doc,code_lines)
    doc.save(OUTPUT)
    print(f'created {OUTPUT}, chapters={len(chapters)}')

if __name__=='__main__':main()
