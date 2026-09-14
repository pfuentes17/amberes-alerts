"""
update_estado.py — Actualiza columna D (Último dato) en la hoja ESTADO
leyendo la última fecha de cada hoja referenciada en amberes_data.xlsx.

Uso: python3 scripts/update_estado.py
"""
from openpyxl import load_workbook
from datetime import datetime, date
import re

XLSX = '/Users/pedrofuentes/Library/CloudStorage/OneDrive-Personal/Documentos/amberes_data.xlsx'

QUARTER_MONTH = {'I': 1, 'II': 4, 'III': 7, 'IV': 10, '1': 1, '2': 4, '3': 7, '4': 10}

def parse_text_period(val):
    """Convierte strings como '2025 IV', '2026 Q2', '2025 II' a date."""
    if not isinstance(val, str):
        return None
    s = val.strip()
    # "YYYY I/II/III/IV"
    m = re.match(r'(\d{4})\s+(I{1,3}V?|IV|I|II|III)', s)
    if m:
        y, q = int(m.group(1)), m.group(2)
        return date(y, QUARTER_MONTH.get(q, 1), 1)
    # "YYYY QN" or "YYYY Q1"
    m = re.match(r'(\d{4})\s+Q(\d)', s)
    if m:
        y, q = int(m.group(1)), m.group(2)
        return date(y, QUARTER_MONTH.get(q, 1), 1)
    return None


def get_last_date(wb, sheet_name):
    """Detecta columna de fechas y devuelve la última fecha."""
    if sheet_name not in wb.sheetnames:
        return None
    ws = wb[sheet_name]

    # --- Special case: EPH (pivoted — years in row 3, quarters in row 4) ---
    if sheet_name == 'EPH':
        rows = list(ws.iter_rows(min_row=3, max_row=4, values_only=True))
        year_row, qtr_row = rows[0], rows[1]
        last_year, last_qtr = None, None
        for i in range(len(year_row) - 1, -1, -1):
            y = year_row[i]
            q = qtr_row[i] if i < len(qtr_row) else None
            if y and re.match(r'Año \d{4}', str(y)):
                last_year = int(str(y).split()[-1])
                last_qtr = str(q) if q else '1° trimestre'
                break
        if last_year:
            qmap = {'1° trimestre': 1, '2° trimestre': 4, '3° trimestre': 7, '4° trimestre': 10}
            m = qmap.get(last_qtr, 1)
            return date(last_year, m, 1)
        return None

    # --- General: scan for datetime OR text period in col A ---
    date_col = None
    first_data_row = None
    has_text_dates = False

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), 1):
        for col_idx, val in enumerate(row):
            if isinstance(val, (datetime, date)) and not isinstance(val, bool):
                date_col = col_idx + 1
                first_data_row = row_idx
                break
            if isinstance(val, str) and parse_text_period(val):
                date_col = col_idx + 1
                first_data_row = row_idx
                has_text_dates = True
                break
        if date_col:
            break

    if not date_col:
        return None

    last_date = None
    for row in ws.iter_rows(min_row=first_data_row, min_col=date_col, max_col=date_col, values_only=True):
        val = row[0]
        if isinstance(val, datetime):
            d = val.date()
        elif isinstance(val, date) and not isinstance(val, bool):
            d = val
        elif has_text_dates and isinstance(val, str):
            d = parse_text_period(val)
        else:
            continue
        if d and (last_date is None or d > last_date):
            last_date = d

    return last_date


def run():
    print(f"Cargando {XLSX}...")
    wb = load_workbook(XLSX)
    ws = wb['ESTADO']

    updated, skipped, not_found = 0, 0, []

    for row in ws.iter_rows(min_row=5, max_row=200):
        serie_cell = row[0]
        d_cell = row[3]
        e_cell = row[4]
        f_cell = row[5]

        serie = serie_cell.value
        if not serie or str(serie).startswith('▸') or str(serie).strip() == '':
            continue
        if d_cell.value == '—':
            skipped += 1
            continue

        last_date = get_last_date(wb, serie)

        if last_date is None:
            not_found.append(serie)
            continue

        d_cell.value = datetime(last_date.year, last_date.month, last_date.day)
        d_cell.number_format = 'DD/MM/YYYY'

        col_d = d_cell.column_letter
        col_e = e_cell.column_letter
        row_n = e_cell.row

        if not (isinstance(e_cell.value, str) and e_cell.value.startswith('=')):
            e_cell.value = f'=INT(TODAY()-{col_d}{row_n})'
            e_cell.number_format = '0'

        if not (isinstance(f_cell.value, str) and f_cell.value.startswith('=')):
            f_cell.value = f'=IF({col_e}{row_n}="—","?",IF({col_e}{row_n}<30,"✓",IF({col_e}{row_n}<=90,"!","✗")))'

        updated += 1
        print(f"  ✓ {serie:<38} → {last_date.strftime('%d/%m/%Y')}")

    # Header dinámico
    for row in ws.iter_rows(min_row=1, max_row=3):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and 'revisión' in cell.value and not cell.value.startswith('='):
                cell.value = '="Última revisión: "&TEXT(TODAY(),"DD/MM/YYYY")&"   |   Rojo > 90d · Ámbar 30–90d · Verde < 30d"'

    wb.save(XLSX)
    print(f"\nListo — {updated} actualizadas, {skipped} omitidas (—), {len(not_found)} sin fecha.")
    if not_found:
        print(f"Sin fecha detectable: {not_found}")


if __name__ == '__main__':
    run()
