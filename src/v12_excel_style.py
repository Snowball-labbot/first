"""Extend the contest template's plain borders to every complete daily group."""
from datetime import datetime
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def format_sheet(ws):
    rows, cols = ws.max_row, ws.max_column
    rule = Side(style='thin', color='000000')
    empty = Side()
    starts = [r for r in range(2, rows + 1)
              if isinstance(ws.cell(r, 1).value, datetime)]
    if not starts:
        starts = [2] if ws.title == '充放电量' else list(range(2, rows + 1))
    ends = {s: starts[i + 1] - 1 if i + 1 < len(starts) else rows
            for i, s in enumerate(starts)}
    end = 1
    for r in range(1, rows + 1):
        if r in ends:
            end = ends[r]
        ws.row_dimensions[r].height = 14
        for j in range(1, cols + 1):
            cell = ws.cell(r, j)
            cell.font = Font(name='宋体', size=10, color='000000')
            cell.fill = PatternFill()
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(left=rule, right=rule,
                top=rule if r == 1 or r in ends else empty,
                bottom=rule if r == 1 or r == end else empty)
            if isinstance(cell.value, datetime):
                cell.number_format = 'yyyy/m/d'
            elif isinstance(cell.value, (float, int)):
                cell.number_format = '0.00'
    # Widen date/time columns only enough to display the filled template.
    if cols > 10:
        ws.column_dimensions['A'].width = 14
    else:
        widths = ([14, 18, 14, 14, 12, 14] if cols == 6 else
                  [18, 14, 14, 12, 14] if cols == 5 else
                  [14, 18, 14] if cols == 3 else [18, 14])
        for j, width in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(j)].width = width
