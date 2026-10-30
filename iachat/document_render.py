"""Render user-owned workspace text into downloadable office documents.

The model produces bounded UTF-8 text, never binary, macros or code.
Rendering is deterministic, uses in-memory buffers and executes no user content.
"""
from __future__ import annotations

import csv
import re
from html import escape
from io import BytesIO, StringIO
from pathlib import PurePath

from .file_workspace import WorkspaceError

MAX_OUTPUT_BYTES = 4_000_000
MAX_SPREADSHEET_ROWS = 2000
MAX_SPREADSHEET_COLUMNS = 50


def _markdown_line(line: str) -> tuple[str, str]:
    stripped = line.strip()
    if stripped.startswith("#"):
        level = len(stripped) - len(stripped.lstrip("#"))
        if 1 <= level <= 3 and stripped[level:level + 1] == " ":
            return ("heading" + str(level), stripped[level:].strip())
    if stripped.startswith(("- ", "* ")):
        return ("bullet", stripped[2:].strip())
    return ("paragraph", line)


def _render_pdf(content: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    buffer = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="IAChatBody", parent=styles["BodyText"],
                              fontName="Helvetica", fontSize=10, leading=14, spaceAfter=7))
    styles.add(ParagraphStyle(name="IAChatBullet", parent=styles["IAChatBody"],
                              leftIndent=16, firstLineIndent=-9))
    story = []
    for line in content.splitlines():
        kind, text = _markdown_line(line)
        if not text.strip():
            story.append(Spacer(1, 7))
        elif kind.startswith("heading"):
            story.append(Paragraph(escape(text), styles["Heading" + kind[-1]]))
        elif kind == "bullet":
            story.append(Paragraph("&#8226; " + escape(text), styles["IAChatBullet"]))
        else:
            story.append(Paragraph(escape(text), styles["IAChatBody"]))
    if not story:
        story.append(Paragraph(" ", styles["IAChatBody"]))
    document = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=48,
                                 rightMargin=48, topMargin=48, bottomMargin=48,
                                 title="Documento de IAchat")
    document.build(story)
    return buffer.getvalue()


def _render_docx(content: str) -> bytes:
    from docx import Document
    from docx.shared import Pt

    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    for line in content.splitlines():
        kind, text = _markdown_line(line)
        if kind.startswith("heading"):
            document.add_heading(text, level=int(kind[-1]))
        elif kind == "bullet":
            document.add_paragraph(text, style="List Bullet")
        else:
            document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()



# Only same-sheet, bounded range aggregates are ever interpreted as formulas.
# Excel stores English function names in OOXML even for Spanish-language UIs.
_SAFE_AGGREGATE = re.compile(
    r"^=(SUM|SUMA|AVERAGE|PROMEDIO|COUNT|CONTAR|MIN|MAX)"
    r"\(([A-Z]{1,2})([1-9][0-9]{0,3}):([A-Z]{1,2})([1-9][0-9]{0,3})\)$",
    re.IGNORECASE,
)
_AGGREGATE_NAMES = {"SUMA": "SUM", "PROMEDIO": "AVERAGE", "CONTAR": "COUNT"}
_NUMERIC_HEADER = re.compile(
    r"(?i)\b(?:importe|monto|valor|precio|costo|cantidad|total|saldo)\b"
)


def _safe_formula(value: str) -> str | None:
    match = _SAFE_AGGREGATE.fullmatch(value.strip())
    if not match:
        return None
    func, col_a, row_a, col_b, row_b = match.groups()
    from openpyxl.utils.cell import column_index_from_string
    if (int(row_a) < 2
            or col_a.upper() != col_b.upper()
            or column_index_from_string(col_a.upper()) > MAX_SPREADSHEET_COLUMNS
            or int(row_a) > int(row_b)
            or int(row_b) > MAX_SPREADSHEET_ROWS):
        return None
    name = _AGGREGATE_NAMES.get(func.upper(), func.upper())
    return f"={name}({col_a.upper()}{row_a}:{col_b.upper()}{row_b})"


def spreadsheet_needs_auto_total(instruction: str) -> bool:
    return bool(
        re.search(r"(?i)\b(?:total|suma|sumatoria)\b", instruction)
        and re.search(r"(?i)\b(?:autom[aá]tic[oa]|f[oó]rmula|calculad[oa]|calcule|sume)\b", instruction)
    )


def ensure_spreadsheet_auto_total(content: str) -> str:
    """Add a bounded, recalculating SUM row with room for future entries."""
    from openpyxl.utils import get_column_letter
    try:
        rows = list(csv.reader(StringIO(content, newline=""), strict=True))
    except (csv.Error, UnicodeError) as exc:
        raise WorkspaceError("invalid_spreadsheet_csv") from exc
    if not rows or len(rows[0]) < 2 or len(rows[0]) > MAX_SPREADSHEET_COLUMNS:
        raise WorkspaceError("spreadsheet_missing_columns")
    headers = rows[0]
    candidates = [i for i, value in enumerate(headers) if _NUMERIC_HEADER.search(value)]
    if not candidates:
        raise WorkspaceError("spreadsheet_total_column_missing")
    # Keep an existing data table, but replace a model-supplied summary with
    # one known-safe formula. Never trust an arbitrary formula from the model.
    if len(rows) > 1 and rows[-1] and rows[-1][0].strip().casefold() in ("total", "suma", "sumatoria"):
        rows.pop()
    width = len(headers)
    if any(len(row) > width for row in rows[1:]):
        raise WorkspaceError("spreadsheet_inconsistent_columns")
    if len(rows) >= MAX_SPREADSHEET_ROWS:
        raise WorkspaceError("spreadsheet_limit_reached")
    target = candidates[0]
    while len(rows) < min(101, MAX_SPREADSHEET_ROWS - 1):
        rows.append([""] * width)
    total = [""] * width
    total[0 if target != 0 else 1] = "TOTAL"
    col = get_column_letter(target + 1)
    total[target] = f"=SUM({col}2:{col}{len(rows)})"
    rows.append(total)
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue()


def _render_xlsx(content: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.calcMode = "auto"
    sheet = workbook.active
    sheet.title = "Datos"
    sheet.freeze_panes = "A2"
    widths: list[int] = []
    numeric_columns: set[int] = set()
    try:
        reader = csv.reader(StringIO(content, newline=""), strict=True)
        for row_number, row in enumerate(reader, 1):
            if row_number > MAX_SPREADSHEET_ROWS or len(row) > MAX_SPREADSHEET_COLUMNS:
                raise WorkspaceError("spreadsheet_limit_reached")
            if row_number == 1:
                numeric_columns = {
                    i for i, header in enumerate(row, 1)
                    if _NUMERIC_HEADER.search(header)
                }
            for column_number, value in enumerate(row, 1):
                if len(value) > 32767:
                    raise WorkspaceError("spreadsheet_cell_too_large")
                cell = sheet.cell(row=row_number, column=column_number)
                formula = _safe_formula(value) if row_number > 1 else None
                if formula:
                    cell.value = formula
                    cell.data_type = "f"
                elif (row_number > 1 and column_number in numeric_columns
                      and re.fullmatch(r"-?\d+(?:\.\d+)?", value.strip())):
                    number = value.strip()
                    cell.value = float(number) if "." in number else int(number)
                    cell.number_format = "#,##0.00"
                else:
                    # CSV formula injection stays inert unless the exact
                    # same-sheet aggregate allowlist accepts the formula.
                    cell.value = value
                    cell.data_type = "s"
                if row_number == 1:
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = PatternFill("solid", fgColor="25466A")
                    cell.alignment = Alignment(wrap_text=True)
                if len(widths) < column_number:
                    widths.append(10)
                widths[column_number - 1] = min(40, max(widths[column_number - 1], len(value) + 2))
    except (csv.Error, UnicodeError) as exc:
        raise WorkspaceError("invalid_spreadsheet_csv") from exc
    if sheet.max_row > 1 and sheet.max_column:
        sheet.auto_filter.ref = sheet.dimensions
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()

def render_download(name: str, content: str) -> tuple[bytes, str]:
    """Return bytes and MIME type. All input comes from an authenticated workspace."""
    extension = PurePath(name).suffix.lower()
    if extension == ".pdf":
        payload, media_type = _render_pdf(content), "application/pdf"
    elif extension == ".docx":
        payload, media_type = (_render_docx(content),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    elif extension == ".xlsx":
        payload, media_type = (_render_xlsx(content),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        payload, media_type = content.encode("utf-8"), "application/octet-stream"
    if len(payload) > MAX_OUTPUT_BYTES:
        raise WorkspaceError("rendered_file_too_large")
    return payload, media_type
