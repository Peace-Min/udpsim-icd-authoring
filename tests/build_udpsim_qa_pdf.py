"""Build the selectable-text synthetic PDF fixture; requires local reportlab."""
from __future__ import annotations

import argparse
from html import escape
from pathlib import Path
import re
import textwrap


def build(source: Path, output: Path):
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted, Spacer, PageBreak
    except ImportError as exc:
        raise SystemExit('reportlab is required to rebuild this fixture; provision it offline or use the bundled Python runtime.') from exc

    text = source.read_text(encoding='utf-8')
    common_start = text.index('SECTION 1 -')
    message_start = text.index('SECTION 3 -')
    boundary_start = text.index('SECTION 4 -')
    common = text[common_start:message_start].strip()
    detail = text[message_start:boundary_start].strip()
    scope = text[boundary_start:].strip()

    def fact(name):
        match = re.search(r'^' + re.escape(name) + r':\s*(.+)$', detail, re.M)
        if not match:
            raise ValueError('Missing source fact: ' + name)
        return match.group(1)

    output.parent.mkdir(parents=True, exist_ok=True)
    title = ParagraphStyle('Title', fontName='Helvetica-Bold', fontSize=20, leading=26, textColor=colors.HexColor('#142B4A'), spaceAfter=18)
    heading = ParagraphStyle('Heading', fontName='Helvetica-Bold', fontSize=12, leading=18, textColor=colors.HexColor('#142B4A'), spaceAfter=12)
    body = ParagraphStyle('Body', fontName='Helvetica', fontSize=10, leading=15, alignment=TA_LEFT, spaceAfter=10)
    code = ParagraphStyle('Code', fontName='Courier', fontSize=9, leading=14, spaceAfter=12)

    def para(value, style=body):
        return Paragraph(escape(value), style)

    def block(value):
        wrapped = []
        for line in value.splitlines():
            wrapped.extend(textwrap.wrap(line, width=88, replace_whitespace=False, drop_whitespace=False) or [''])
        return Preformatted('\n'.join(wrapped), code)

    story = [para('Synthetic Window Control', title), para('1. Common definitions', heading),
             para('Revision QA-WINDOW-20261030. Independent test data, unrelated to operational ICDs.'),
             para('The simulator represents the controller. All multibyte wire integers are little endian.'),
             para('No automatic padding, scaling, checksum or trailing bytes are present.'),
             block(common), para('Dependency note: messages on pages 2-3 use this common header and enum.'), PageBreak(),
             para('Message inventory', title), para('2. Requested extraction range', heading),
             para('Task: define only SET_WINDOW from physical PDF pages 2-3. Follow the common definitions on page 1.'),
             block('\n'.join(['Code: ' + fact('Code'), 'Name: ' + fact('Name'), 'ID: ' + fact('ID'),
                              'Direction in device documentation: ' + fact('Direction in device documentation'),
                              'Total wire length: ' + fact('Total wire length')])),
             para('Detailed body layout: page 3. Header roles and RunState values: page 1.'),
             para('Identifiers are canonical XML identifiers. Array indexes start at 0. Header fields are not repeated in the body.'),
             para('This inventory does not introduce any additional messages.'), PageBreak(),
             para('Message detail', title), para('3. SET_WINDOW', heading), block(detail),
             para('Common header and enum: page 1. Use the simulator role when converting the device direction.'),
             Spacer(1, 18), block(scope)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#CBD5E1'))
        canvas.line(42, 42, A4[0] - 42, 42)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#475569'))
        canvas.drawString(42, 27, 'SYNTHETIC QA FIXTURE - QA-WINDOW-20261030')
        canvas.drawRightString(A4[0] - 42, 27, f'Physical PDF page {doc.page} / 3')
        canvas.restoreState()

    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=42, leftMargin=42, topMargin=44, bottomMargin=62,
                            title='Synthetic Window Control QA', author='Peace.Skillbank synthetic fixtures')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=root / 'tests/fixtures/udpsim-opencode-qa/window-spec-excerpt.txt')
    parser.add_argument('--output', type=Path, default=root / 'tests/fixtures/udpsim-opencode-qa/document.pdf')
    args = parser.parse_args()
    build(args.input, args.output)
    print('SYNTHETIC_PDF_CREATED ' + str(args.output))
