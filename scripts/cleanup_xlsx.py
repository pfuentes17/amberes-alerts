"""
Limpieza de amberes_data.xlsx:
  1. Elimina hojas duplicadas / redundantes
  2. Renombra hojas con nombres problemáticos
  3. Reconstruye hoja ÍNDICE
  4. Crea hoja ESTADO (fechas de última actualización por serie)
"""
import os
from datetime import datetime, date
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DEST = "/Users/pedrofuentes/Library/CloudStorage/OneDrive-Personal/Documentos/amberes_data.xlsx"

# ── 1. HOJAS A ELIMINAR ──────────────────────────────────────────────
# Criterio: hojas formateadas cortas que son subconjuntos de hojas raw más largas,
# más hojas de resumen internacionales que duplican las hojas por indicador.
HOJAS_ELIMINAR = {
    # ARG_* formateadas — duplican hojas raw con menos historia
    'ARG_IPC',           # ← raw: IPC (2017→)
    'ARG_EMAE',          # ← raw: EMAE (2004→)
    'ARG_UCII',          # ← raw: UCII (2016→)
    'ARG_IPIMinero',     # ← raw: IPIMin (2006→)
    'ARG_Fiscal',        # ← raw: Resultado Fiscal (1961→)
    'ARG_Recaud',        # ← raw: Recaudacion + Reca
    'ARG_EPH',           # ← raw: EPH (2016→)
    'ARG_BalanzaComercial',  # ← raw: Balanza Comercial Argentina (1990→)
    'ARG_BCRA',          # ← raw: Reservas Internacionales, Tipo de Cambio RM, Base Monetaria
    'ARG_Actividad',     # ← raw: IPI, ISAC, ICC, UCII
    'ARG_Comercio',      # ← raw: Balanza Comercial Argentina
    # Resúmenes internacionales — duplican hojas por indicador
    'US',                # ← raw: CPI-US, PBI-US, PCE-US, Job Report-US, etc.
    'US_CPI',            # ← raw: CPI - US
    'US_PPI',            # ← raw: PPI - US
    'US_Labor',          # ← raw: Job Report - US
    'US_PCE',            # ← raw: PCE - US
    'Brasil',            # ← raw: IPCA-Br, SELIC-Br, Desempleo-Br, etc.
    'BR_CPI',            # ← raw: IPCA - Br
    'BR_Macro',          # ← raw: PBI-Br, IBC-Br, etc.
    'China',             # ← raw: IPC-China, Trade Balance-China
    'CN_Macro',          # ← raw: IPC - China
    'CN_Trade',          # ← raw: Trade Balance - China
    'Eurozona',          # ← raw: Balance Trade EU
    'EU_Trade',          # ← raw: Balance Trade EU
    'Japón',             # ← raw: CPI - JP
    'JP_CPI',            # ← raw: CPI - JP
    # Vacías o sin valor
    'ELLIOT',            # hoja vacía
}

# ── 2. RENOMBRES ──────────────────────────────────────────────────────
RENOMBRES = {
    ' Balance Trade':   'Balanza Comercial US',   # bug: empieza con espacio
    'IPC 2000-2024':    'IPC 2000-',              # el nombre mente — llega a jun 2025
    'Indices':          'Indices ETF US',          # aclarar qué son (SPY, QQQ, etc.)
    'Semaforo':         'Semaforo ARG',
}

# ── 3. METADATOS PARA ÍNDICE Y ESTADO ────────────────────────────────
# (hoja, categoría, descripción, frecuencia, fuente)
CATALOGO = {
    # Argentina — Precios
    'IPC':                  ('ARG · Precios',    'IPC: MoM, YoY, Núcleo, Regulados, Estacionales', 'Mensual',    'INDEC'),
    'IPC 2000-':            ('ARG · Precios',    'IPC histórico: MoM y YoY desde Ene 2000',         'Mensual',    'INDEC'),
    'IPIM':                 ('ARG · Precios',    'Índice de Precios Internos Mayoristas',            'Mensual',    'INDEC'),
    'ICC':                  ('ARG · Precios',    'Índice Costo de Construcción: YoY, MoM, materiales/mano de obra', 'Mensual', 'INDEC'),
    'CBA-CBT':              ('ARG · Precios',    'Canasta Básica Alimentaria y Total (ARS por persona)', 'Mensual', 'INDEC'),
    # Argentina — Actividad
    'EMAE':                 ('ARG · Actividad',  'EMAE general + desestacionalizado: YoY, MoM',     'Mensual',    'INDEC'),
    'IPI':                  ('ARG · Actividad',  'Índice de Producción Industrial: YoY, serie desest.', 'Mensual', 'INDEC'),
    'ISAC':                 ('ARG · Actividad',  'Indicador Sintético de Actividad de la Construcción', 'Mensual', 'INDEC'),
    'IPIMin':               ('ARG · Actividad',  'Índice de Producción Industrial Minero: YoY',     'Mensual',    'INDEC'),
    'UCII':                 ('ARG · Actividad',  'Utilización de la Capacidad Instalada en la Industria', 'Mensual', 'INDEC'),
    'Despacho cemento':     ('ARG · Actividad',  'Despacho de cemento: volumen y YoY',              'Mensual',    'AFCP'),
    'Produccion automotor': ('ARG · Actividad',  'Producción y exportaciones de vehículos',         'Mensual',    'ADEFA'),
    'PBI':                  ('ARG · Actividad',  'PIB trimestral: nivel, QoQ, YoY y componentes',   'Trimestral', 'INDEC'),
    # Argentina — Comercio exterior
    'Balanza Comercial Argentina': ('ARG · Externo', 'Exportaciones e importaciones mensuales (MM USD)', 'Mensual', 'INDEC'),
    'Balance Cambiario BCRA':      ('ARG · Externo', 'Balance cambiario BCRA: Cuenta Corriente, bienes, servicios', 'Mensual', 'BCRA'),
    'Balance Energetico':          ('ARG · Externo', 'Balance energético: exportaciones e importaciones de energía', 'Mensual', 'MINEM'),
    'Balanza de Pagos':            ('ARG · Externo', 'Balanza de pagos completa (cuenta corriente + capital)',       'Trimestral', 'INDEC'),
    'Liq. Agro':                   ('ARG · Externo', 'Liquidación divisas sector agropecuario (MM USD)',            'Mensual', 'CIARA-CEC'),
    'Liq. Agro diaria':            ('ARG · Externo', 'Liquidación agropecuaria diaria (MM USD)',                    'Diaria',  'CIARA-CEC'),
    'Comercializacion Agro':       ('ARG · Externo', 'Comercialización de granos (toneladas)',                      'Mensual', 'MINAGRI'),
    'DJVE Aprobadas':              ('ARG · Externo', 'Declaraciones Juradas de Venta al Exterior aprobadas',        'Diaria',  'AFIP'),
    'Turismo':                     ('ARG · Externo', 'Turismo internacional: llegadas y salidas',                   'Mensual', 'INDEC'),
    # Argentina — Fiscal
    'Resultado Fiscal':     ('ARG · Fiscal',     'Resultado primario y financiero mensual (MM ARS nominales)', 'Mensual', 'MECON'),
    'Recaudacion':          ('ARG · Fiscal',     'Recaudación total y por impuesto (B ARS)',                   'Mensual', 'AFIP'),
    'Reca':                 ('ARG · Fiscal',     'Recaudación detallada: IVA real, Ganancias, variaciones',   'Mensual', 'AFIP'),
    'Reca - Tesoro':        ('ARG · Fiscal',     'Recaudación desglosada por organismo (DGI / DGA)',          'Mensual', 'AFIP'),
    'Vencimientos':         ('ARG · Fiscal',     'Vencimientos de deuda pública en ARS (perfil anual)',       'Anual',   'MECON'),
    'Vencimientos USD':     ('ARG · Fiscal',     'Vencimientos de deuda pública en USD',                     'Anual',   'MECON'),
    'Vencimientos mensuales': ('ARG · Fiscal',   'Vencimientos mensuales de deuda (ARS + USD)',              'Mensual', 'MECON'),
    'Deuda':                ('ARG · Fiscal',     'Stock de deuda pública por acreedor y moneda',             'Trimestral', 'MECON'),
    'Cap. Intereses':       ('ARG · Fiscal',     'Pagos de capital e intereses de deuda pública',            'Mensual', 'MECON'),
    # Argentina — BCRA / Monetario
    'Tipo de Cambio RM':    ('ARG · BCRA',       'Tipo de cambio de referencia BCRA: oficial, mayorista (diario)', 'Diaria', 'BCRA'),
    'Base Monetaria':       ('ARG · BCRA',       'Base monetaria y sus componentes (diario, MM ARS)',              'Diaria', 'BCRA'),
    'Reservas Internacionales': ('ARG · BCRA',   'Reservas brutas y netas BCRA (diario, MM USD)',                  'Diaria', 'BCRA'),
    'Venta Reservas BCRA':  ('ARG · BCRA',       'Ventas diarias de reservas del BCRA (MM USD)',                   'Diaria', 'BCRA'),
    'Depositos':            ('ARG · BCRA',       'Depósitos bancarios del sector privado (diario, MM ARS)',         'Diaria', 'BCRA'),
    'Prestamos':            ('ARG · BCRA',       'Préstamos bancarios al sector privado (diario, MM ARS)',          'Diaria', 'BCRA'),
    'Adelantos BCRA':       ('ARG · BCRA',       'Adelantos transitorios del BCRA al Tesoro (diario)',             'Diaria', 'BCRA'),
    'Depositos del Gobierno': ('ARG · BCRA',     'Depósitos del Gobierno en BCRA (diario)',                        'Diaria', 'BCRA'),
    'Depositos del tesoro (Sistema)': ('ARG · BCRA', 'Depósitos del Tesoro en el sistema financiero',             'Mensual', 'BCRA'),
    'Posicion neta del BCRA': ('ARG · BCRA',     'Posición neta de reservas del BCRA',                            'Diaria', 'BCRA'),
    'Inversion de No residentes': ('ARG · BCRA', 'Inversión de no residentes en activos argentinos',              'Mensual', 'BCRA'),
    'Compras Netas PH':     ('ARG · BCRA',       'Compras netas de dólares del sector personas humanas',           'Mensual', 'BCRA'),
    'LEFIS':                ('ARG · BCRA',       'Letras Fiscales de Liquidez (LEFI): operaciones y tenencias del BCRA', 'Diaria', 'BCRA'),
    # Argentina — Mercados
    'Dolar':                ('ARG · Mercados',   'Tipo de cambio: oficial, mayorista, CCL y bandas',              'Diaria',  'BCRA / mercado'),
    'Dolar-Caucion':        ('ARG · Mercados',   'Tasa de caución en dólares',                                    'Diaria',  'BYMA'),
    'Riesgo Pais':          ('ARG · Mercados',   'Riesgo país (EMBI+): diario desde may 2020',                    'Diaria',  'JP Morgan'),
    'MERVAL USD':           ('ARG · Mercados',   'Índice Merval expresado en USD (CCL)',                           'Diaria',  'BYMA'),
    'Futuros':              ('ARG · Mercados',   'Futuros dólar ROFEX: contratos DLR, open interest, precios',    'Diaria',  'MATBA-ROFEX'),
    'Indices ETF US':       ('ARG · Mercados',   'ETFs de índices US (SPY, QQQ, GLD, etc.): OHLC diario',         'Diaria',  'Yahoo/Finnhub'),
    'Semaforo ARG':         ('ARG · Mercados',   'Semáforo de indicadores: IPC, EMAE, Dólar, Merval (matriz)',    'Mensual', 'Elaboración propia'),
    # Argentina — Social / Laboral
    'EPH':                  ('ARG · Social',     'Encuesta Permanente de Hogares: desempleo, actividad, empleo, subocupación', 'Trimestral', 'INDEC'),
    'Salarios':             ('ARG · Social',     'Índice de salarios privado y público (nominal y real, base oct 2016)', 'Mensual', 'INDEC'),
    'Pobreza':              ('ARG · Social',     'Tasas de pobreza e indigencia por hogares y personas',           'Semestral', 'INDEC'),
    # Argentina — Agro
    'REM':                  ('ARG · Expectativas', 'REM BCRA: proyecciones de inflación mensual por horizonte',   'Mensual', 'BCRA'),
    'LEFIS':                ('ARG · BCRA',       'LEFI: operaciones diarias y tenencias BCRA / bancos',           'Diaria',  'BCRA'),
    # EE.UU.
    'PBI - US':             ('EE.UU.',           'PIB real trimestral: nivel, QoQ anualizado, componentes',       'Trimestral', 'BEA'),
    'CPI - US':             ('EE.UU.',           'CPI: YoY, MoM, CPI Core (base 1982-84=100)',                    'Mensual', 'BLS'),
    'IPC 2000-':            ('EE.UU.',           'IPC Argentina histórico MoM y YoY desde Ene 2000',             'Mensual', 'INDEC'),  # se sobreescribirá
    'PPI - US':             ('EE.UU.',           'PPI: MoM y YoY, final demand y core',                          'Mensual', 'BLS'),
    'PCE - US':             ('EE.UU.',           'PCE: YoY, MoM, PCE Core (deflactor preferido de la Fed)',      'Mensual', 'BEA'),
    'Job Report - US':      ('EE.UU.',           'Nóminas no agrícolas (miles) y tasa de desempleo',             'Mensual', 'BLS'),
    'Initial Claims':       ('EE.UU.',           'Solicitudes iniciales de subsidio de desempleo (semanal)',      'Semanal', 'DOL'),
    'Commercial Balance - US': ('EE.UU.',        'Balanza comercial de bienes y servicios (B USD)',               'Mensual', 'Census Bureau'),
    'Balanza Comercial US': ('EE.UU.',           'Balance comercial US (importaciones y exportaciones)',          'Mensual', 'Census Bureau'),  # renombrado
    'Imports-Exports Prices': ('EE.UU.',         'Índices de precios de importaciones y exportaciones',          'Mensual', 'BLS'),
    # Brasil
    'IPCA - Br':            ('Brasil',           'IPCA (inflación oficial): YoY y MoM',                          'Mensual', 'IBGE'),
    'INPC - Br':            ('Brasil',           'INPC (inflación para trabajadores): YoY y MoM',               'Mensual', 'IBGE'),
    'IPP - Br':             ('Brasil',           'Índice de Precios al Productor (IPP)',                         'Mensual', 'IBGE'),
    'SELIC - Br':           ('Brasil',           'Tasa SELIC: política monetaria del BCB',                       'Mensual', 'BCB'),
    'Desempleo - Br':       ('Brasil',           'Tasa de desempleo (PNAD Continua)',                            'Mensual', 'IBGE'),
    'PBI - Br':             ('Brasil',           'PIB trimestral de Brasil: nivel y variación',                  'Trimestral', 'IBGE'),
    'IBC-Br':               ('Brasil',           'IBC-Br: indicador mensual de actividad económica (proxy PIB)',  'Mensual', 'BCB'),
    'PIM - Br':             ('Brasil',           'Producción Industrial de Brasil',                              'Mensual', 'IBGE'),
    'Cuenta Corriente - Br': ('Brasil',          'Cuenta corriente de Brasil (B USD)',                           'Mensual', 'BCB'),
    'Balanza Comercial - Br': ('Brasil',         'Balanza comercial de Brasil (B USD)',                          'Mensual', 'MDIC'),
    # China
    'IPC - China':          ('China',            'CPI China: YoY (índice base 2015=100)',                        'Mensual', 'NBS'),
    'Trade Balance - China': ('China',           'Balanza comercial China: exportaciones, importaciones, saldo (B USD)', 'Mensual', 'General Administration of Customs'),
    # Eurozona
    'Balance Trade EU':     ('Eurozona',         'Balanza comercial de bienes de la Eurozona (M EUR)',           'Mensual', 'Eurostat'),
    # Japón
    'CPI - JP':             ('Japón',            'CPI Japón: YoY, MoM, CPI Core',                               'Mensual', 'Statistics Japan'),
}

# ── ABRIR WORKBOOK ────────────────────────────────────────────────────
print("Cargando workbook...")
wb = load_workbook(DEST)
print(f"  Hojas originales: {len(wb.sheetnames)}")

# ── PASO 1: RENOMBRAR ─────────────────────────────────────────────────
print("\nRenombrando hojas...")
for viejo, nuevo in RENOMBRES.items():
    if viejo in wb.sheetnames:
        wb[viejo].title = nuevo
        print(f"  [{viejo}] → [{nuevo}]")

# ── PASO 2: ELIMINAR DUPLICADOS ───────────────────────────────────────
print("\nEliminando hojas duplicadas/redundantes...")
eliminadas = []
for sh in HOJAS_ELIMINAR:
    if sh in wb.sheetnames:
        del wb[sh]
        eliminadas.append(sh)
        print(f"  ✗ [{sh}]")
print(f"  Total eliminadas: {len(eliminadas)}")

# ── PASO 3: DETECTAR ÚLTIMA FECHA POR HOJA ───────────────────────────
def ultima_fecha(ws):
    """Busca la última celda con fecha válida en las primeras 3 columnas."""
    ultima = None
    for row in ws.iter_rows(values_only=True):
        for c in row[:3]:
            if hasattr(c, 'year') and 1990 < c.year < 2030:
                if ultima is None or c > ultima:
                    ultima = c
    return ultima

print("\nDetectando fechas de última actualización...")
estado_data = []  # [(hoja, categoria, descripcion, frecuencia, fuente, ultima_fecha)]
for sh in wb.sheetnames:
    if sh in ('ÍNDICE', 'ESTADO'): continue
    ws = wb[sh]
    uf = ultima_fecha(ws)
    meta = CATALOGO.get(sh, ('Sin categoría', sh, '—', 'BCRA'))
    estado_data.append((sh, meta[0], meta[1], meta[2], meta[3], uf))

# ── PASO 4: RECONSTRUIR HOJA ÍNDICE ──────────────────────────────────
print("\nReconstruyendo hoja ÍNDICE...")
if 'ÍNDICE' in wb.sheetnames:
    del wb['ÍNDICE']

wi = wb.create_sheet('ÍNDICE', 0)

# Colores
HDR_BG  = 'FF1e1e22'
HDR_FG  = 'FFFFFFFF'
SEC_BG  = 'FF2d2d32'
SEC_FG  = 'FF00E880'
ROW_BG  = 'FF28282D'
ROW_FG  = 'FFE0E0E0'
ALT_BG  = 'FF232328'

def cell_style(ws, row, col, value, bg=None, fg='FF000000', bold=False, size=10):
    c = ws.cell(row=row, column=col, value=value)
    c.font = Font(name='Calibri', bold=bold, color=fg, size=size)
    if bg:
        c.fill = PatternFill('solid', start_color=bg)
    c.alignment = Alignment(vertical='center', wrap_text=False)
    return c

# Título
wi.merge_cells('A1:F1')
c = wi.cell(row=1, column=1, value='amberes_data.xlsx — Índice de hojas')
c.font = Font(name='Calibri', bold=True, color=HDR_FG, size=14)
c.fill = PatternFill('solid', start_color=HDR_BG)
c.alignment = Alignment(horizontal='center', vertical='center')
wi.row_dimensions[1].height = 28

# Subtítulo
wi.merge_cells('A2:F2')
now_str = datetime.now().strftime('%d/%m/%Y')
c2 = wi.cell(row=2, column=1, value=f'Generado: {now_str}  |  {len(wb.sheetnames)-1} hojas de datos')
c2.font = Font(name='Calibri', color='FF888888', size=9)
c2.fill = PatternFill('solid', start_color=HDR_BG)
c2.alignment = Alignment(horizontal='center', vertical='center')
wi.row_dimensions[2].height = 16

# Header
headers = ['Hoja', 'Categoría', 'Descripción', 'Frecuencia', 'Fuente', 'Último dato']
row = 4
for j, h in enumerate(headers, 1):
    cell_style(wi, row, j, h, bg=HDR_BG, fg=HDR_FG, bold=True, size=10)
wi.row_dimensions[row].height = 20

# Agrupar por categoría
from collections import defaultdict
por_cat = defaultdict(list)
for item in estado_data:
    por_cat[item[1]].append(item)

row = 5
for cat in sorted(por_cat.keys()):
    # Separador de categoría
    wi.merge_cells(f'A{row}:F{row}')
    cell_style(wi, row, 1, cat, bg=SEC_BG, fg=SEC_FG, bold=True, size=10)
    wi.row_dimensions[row].height = 18
    row += 1

    for i, (sh, _, desc, freq, fuente, uf) in enumerate(sorted(por_cat[cat])):
        bg = ROW_BG if i % 2 == 0 else ALT_BG
        cell_style(wi, row, 1, sh,    bg=bg, fg='FF00E880', size=9)
        cell_style(wi, row, 2, cat,   bg=bg, fg=ROW_FG, size=9)
        cell_style(wi, row, 3, desc,  bg=bg, fg=ROW_FG, size=9)
        cell_style(wi, row, 4, freq,  bg=bg, fg='FFAAAAAA', size=9)
        cell_style(wi, row, 5, fuente, bg=bg, fg='FFAAAAAA', size=9)
        uf_str = uf.strftime('%b %Y') if uf else '—'
        uf_color = 'FF00E880' if (uf and uf.year >= 2026) else ('FFE8A044' if (uf and uf.year >= 2025) else 'FFCC4444')
        cell_style(wi, row, 6, uf_str, bg=bg, fg=uf_color, size=9)
        wi.row_dimensions[row].height = 16
        row += 1

# Anchos de columna
wi.column_dimensions['A'].width = 32
wi.column_dimensions['B'].width = 18
wi.column_dimensions['C'].width = 60
wi.column_dimensions['D'].width = 12
wi.column_dimensions['E'].width = 20
wi.column_dimensions['F'].width = 12
wi.freeze_panes = 'A5'

# ── PASO 5: CREAR HOJA ESTADO ─────────────────────────────────────────
print("Creando hoja ESTADO...")
if 'ESTADO' in wb.sheetnames:
    del wb['ESTADO']

we = wb.create_sheet('ESTADO', 1)

we.merge_cells('A1:E1')
c = we.cell(row=1, column=1, value='Estado de actualización de series')
c.font = Font(name='Calibri', bold=True, color=HDR_FG, size=13)
c.fill = PatternFill('solid', start_color=HDR_BG)
c.alignment = Alignment(horizontal='center', vertical='center')
we.row_dimensions[1].height = 26

we.merge_cells('A2:E2')
c2 = we.cell(row=2, column=1, value=f'Actualizar manualmente la columna "Actualizado" cada vez que se edite una serie. Generado: {now_str}')
c2.font = Font(name='Calibri', color='FF888888', size=8)
c2.fill = PatternFill('solid', start_color=HDR_BG)
c2.alignment = Alignment(horizontal='center', vertical='center')

hdrs_e = ['Serie (Hoja)', 'Categoría', 'Frecuencia', 'Último dato en hoja', 'Actualizado manualmente']
row = 4
for j, h in enumerate(hdrs_e, 1):
    c = we.cell(row=row, column=j, value=h)
    c.font = Font(name='Calibri', bold=True, color=HDR_FG, size=10)
    c.fill = PatternFill('solid', start_color=HDR_BG)
    c.alignment = Alignment(vertical='center')
we.row_dimensions[row].height = 20

row = 5
for i, (sh, cat, desc, freq, fuente, uf) in enumerate(sorted(estado_data, key=lambda x: (x[1], x[0]))):
    bg = ROW_BG if i % 2 == 0 else ALT_BG
    uf_str = uf.strftime('%b %Y') if uf else '—'
    for j, (val, fg) in enumerate([
        (sh,     'FF00E880'),
        (cat,    ROW_FG),
        (freq,   'FFAAAAAA'),
        (uf_str, 'FFE0E0E0'),
        ('',     'FFE0E0E0'),  # columna editable
    ], 1):
        c = we.cell(row=row, column=j, value=val)
        c.font = Font(name='Calibri', color=fg, size=9)
        c.fill = PatternFill('solid', start_color=bg)
        c.alignment = Alignment(vertical='center')
    we.row_dimensions[row].height = 15
    row += 1

we.column_dimensions['A'].width = 32
we.column_dimensions['B'].width = 22
we.column_dimensions['C'].width = 12
we.column_dimensions['D'].width = 16
we.column_dimensions['E'].width = 22
we.freeze_panes = 'A5'

# ── GUARDAR ───────────────────────────────────────────────────────────
print(f"\nGuardando...")
wb.save(DEST)
size = os.path.getsize(DEST) / (1024*1024)

print(f"\n{'='*55}")
print(f"✓ amberes_data.xlsx guardado")
print(f"  Hojas originales:   106")
print(f"  Hojas eliminadas:   {len(eliminadas)}")
print(f"  Hojas renombradas:  {len(RENOMBRES)}")
print(f"  Hojas finales:      {len(wb.sheetnames)}")
print(f"  Tamaño:             {size:.1f} MB")
print(f"  Nuevas hojas:       ÍNDICE (posición 0), ESTADO (posición 1)")
