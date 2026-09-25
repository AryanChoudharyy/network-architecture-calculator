"""Development-only PDF builder: requires reportlab."""
from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parents[1]


def main():
    styles = {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor("#103747"), spaceAfter=8),
        "heading": ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=colors.HexColor("#087f83"), spaceBefore=9, spaceAfter=4),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=8.5, leading=11.4, spaceAfter=5, alignment=TA_LEFT),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor("#64748b"), spaceAfter=8),
    }
    story = []
    text = (ROOT / "docs/protocol.md").read_text(encoding="utf-8")
    for page_index, page in enumerate(text.split("<!-- PAGE BREAK -->")):
        if page_index:
            story.append(PageBreak())
        for block in re.split(r"\n\s*\n", page.strip()):
            if block.startswith("# "):
                title, _, meta = block.partition("\n")
                story.append(Paragraph(escape(title[2:]), styles["title"]))
                if meta:
                    story.append(Paragraph(escape(meta), styles["meta"]))
            elif block.startswith("## "):
                heading, _, body = block.partition("\n")
                story.append(Paragraph(escape(heading[3:]), styles["heading"]))
                if body:
                    for line in body.splitlines() if body.startswith("- ") else [body]:
                        story.append(Paragraph(escape(line), styles["body"]))
            else:
                story.append(Paragraph(escape(block), styles["body"]))
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.line(38, 31, A4[0] - 38, 31)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(38, 20, "BC/1  |  Network Architecture Assignment")
        canvas.drawRightString(A4[0] - 38, 20, str(doc.page))
    SimpleDocTemplate(str(ROOT / "docs/protocol.pdf"), pagesize=A4,
                      rightMargin=38, leftMargin=38, topMargin=32, bottomMargin=42,
                      title="BC/1 Protocol Specification", author="Network Architecture Project").build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    main()
