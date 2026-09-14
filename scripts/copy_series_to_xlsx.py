"""
Copia todas las hojas de los archivos de Series a amberes_data.xlsx.
- Usa Series.xlsx como fuente principal (76 hojas)
- Agrega hojas únicas de otros archivos que no estén en Series.xlsx
- Preserva las 11 hojas formateadas existentes en amberes_data.xlsx
"""
import os, pandas as pd
from openpyxl import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, PatternFill, Alignment

SERIES_DIR = '/Users/pedrofuentes/Documents/Series'
DEST = "/Users/pedrofuentes/Library/CloudStorage/OneDrive-Personal/Documentos/amberes_data.xlsx"

# Orden de prioridad: Series.xlsx tiene la versión más completa de casi todo
SOURCES = [
    'Series.xlsx',           # base principal (76 hojas)
    'Series diarias.xlsx',   # datos diarios más detallados (mismo contenido pero más fresco)
    'IPIs.xlsx',
    'Series Argy.xlsx',
    'Economia Real.xlsx',
    'Internacional.xlsx',
    'RECA.xlsx',
]

# Leer hojas ya existentes en amberes_data.xlsx (para preservarlas)
wb_dest = load_workbook(DEST)
existing_sheets = set(wb_dest.sheetnames)
print(f"Hojas existentes en amberes_data.xlsx: {sorted(existing_sheets)}")

# Recopilar todas las hojas únicas de las fuentes (primera aparición gana)
seen = set(existing_sheets)  # no pisar las hojas formateadas
sheets_to_copy = []  # [(source_file, sheet_name)]

for fname in SOURCES:
    path = f'{SERIES_DIR}/{fname}'
    wb_src = load_workbook(path, read_only=True, data_only=True)
    for sh in wb_src.sheetnames:
        if sh not in seen:
            seen.add(sh)
            sheets_to_copy.append((fname, sh))
    wb_src.close()

print(f"\nHojas a copiar: {len(sheets_to_copy)}")

# Copiar cada hoja usando pandas (más rápido que openpyxl para datos planos)
errors = []
for i, (fname, shname) in enumerate(sheets_to_copy):
    try:
        path = f'{SERIES_DIR}/{fname}'
        df = pd.read_excel(path, sheet_name=shname, header=None)

        # Limitar filas: hojas con más de 5000 filas son raramente útiles completas
        # Para series diarias, tomar solo desde 2020
        if len(df) > 5000:
            # buscar fila con fecha >= 2020
            start_row = 0
            for ri, row in df.iterrows():
                val = row.iloc[0]
                if hasattr(val, 'year') and val.year >= 2020:
                    start_row = ri
                    break
                elif isinstance(val, str) and '2020' in val:
                    start_row = ri
                    break
            if start_row > 0:
                header_rows = df.iloc[:min(5, start_row)]
                data_rows = df.iloc[start_row:]
                df = pd.concat([header_rows, data_rows]).reset_index(drop=True)

        # Crear sheet en destino
        ws = wb_dest.create_sheet(title=shname[:31])  # Excel max 31 chars

        # Escribir filas
        for row in dataframe_to_rows(df, index=False, header=False):
            ws.append(row)

        print(f"  [{i+1}/{len(sheets_to_copy)}] {shname} ({len(df)} filas) ← {fname}")

    except Exception as e:
        errors.append((shname, str(e)))
        print(f"  ERROR en [{shname}]: {e}")

# Guardar
print(f"\nGuardando amberes_data.xlsx ...")
wb_dest.save(DEST)
size = os.path.getsize(DEST) / (1024*1024)
print(f"✓ Guardado: {DEST}")
print(f"✓ Tamaño: {size:.1f} MB")
print(f"✓ Total hojas: {len(wb_dest.sheetnames)}")
if errors:
    print(f"\nErrores ({len(errors)}):")
    for sh, e in errors: print(f"  {sh}: {e}")
