"""
Actualiza todas las series desactualizadas en amberes_data.xlsx desde APIs públicas.
Fuentes: FRED, BCB (Brasil), BCRA, argentinadatos.com, dolarapi.com, INDEC datos.gob.ar
"""
import json, os, time
from datetime import datetime, date, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError
from openpyxl import load_workbook

BASE_DIR = "/Users/pedrofuentes/Library/CloudStorage/OneDrive-Personal/Documentos/Amberes Excel/"
ARCHIVOS = ['Internacional.xlsx', 'Deuda y Cambiario ARG.xlsx', 'Actividad y Precios ARG.xlsx',
            'Fiscal y Sectorial ARG.xlsx', 'Varios ARG.xlsx']
FRED_KEY = 'e4fb63601eef13d8e1d74ee8ffb95888'
HOY = date.today()

resultados = {'ok': [], 'parcial': [], 'manual': [], 'error': []}

def fetch(url, headers=None, timeout=15):
    try:
        req = Request(url, headers=headers or {'User-Agent': 'Mozilla/5.0'})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return None

def fred(series_id, start='2022-01-01', freq=None):
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_KEY}&file_type=json"
           f"&observation_start={start}&sort_order=asc")
    if freq: url += f"&frequency={freq}"
    d = fetch(url)
    if not d or 'observations' not in d: return []
    return [(o['date'], o['value']) for o in d['observations'] if o['value'] != '.']

def bcb(series_id, start='01/01/2022'):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados?formato=json&dataInicial={start}"
    d = fetch(url)
    if not isinstance(d, list): return []
    return [(r['data'], r['valor']) for r in d if 'data' in r and 'valor' in r]

def bcra(variable_id, start='2022-01-01'):
    url = f"https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/{variable_id}?desde={start}"
    d = fetch(url, headers={'Accept': 'application/json'})
    if not d or 'results' not in d: return []
    rows = []
    for r in d['results']:
        for det in r.get('detalle', []):
            rows.append((det['fecha'], det['valor']))
    return rows

def argdata(endpoint):
    return fetch(f"https://api.argentinadatos.com/v1/{endpoint}")

# ── helpers de fecha ──────────────────────────────────────────────────
def parse_date(s):
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y-%m'):
        try: return datetime.strptime(str(s)[:10], fmt).date()
        except: pass
    return None

def to_excel_date(d):
    """Convierte date a datetime para openpyxl."""
    return datetime(d.year, d.month, d.day)

MESES_PT = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
            'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}

print("=" * 60)
print(f"Actualización masiva — {HOY}")
print("=" * 60)

_workbooks = {f: load_workbook(BASE_DIR + f) for f in ARCHIVOS}

class MultiWorkbook:
    """Routea hojas al archivo correcto tras la separación del monolito en 5 archivos (27/07/2026)."""
    def __getitem__(self, sh_name):
        for f in ARCHIVOS:
            if sh_name in _workbooks[f].sheetnames:
                return _workbooks[f][sh_name]
        raise KeyError(sh_name)
    @property
    def sheetnames(self):
        names = []
        for f in ARCHIVOS:
            names.extend(_workbooks[f].sheetnames)
        return names

wb = MultiWorkbook()

def ultima_fecha_sheet(ws):
    ERRORES = {'#DIV/0!','#REF!','#VALUE!','#N/A','None'}
    ultima = None
    for row in ws.iter_rows(values_only=True):
        for c in row[:3]:
            if hasattr(c, 'year') and 1990 < c.year < 2030:
                vals = [x for x in row[1:9] if x is not None and str(x) not in ERRORES and isinstance(x,(int,float))]
                if vals:
                    d = date(c.year, c.month, getattr(c, 'day', 1))
                    if ultima is None or d > ultima: ultima = d
    return ultima

def append_rows(ws, rows):
    """Agrega filas al final de ws."""
    for r in rows:
        ws.append(r)

def update_sheet(sh_name, rows_nuevas, descripcion):
    if sh_name not in wb.sheetnames:
        resultados['error'].append(f"{sh_name}: hoja no encontrada")
        return
    ws = wb[sh_name]
    if not rows_nuevas:
        resultados['error'].append(f"{sh_name}: sin datos de API")
        return
    append_rows(ws, rows_nuevas)
    resultados['ok'].append(f"{sh_name}: +{len(rows_nuevas)} filas ({descripcion})")
    print(f"  ✓ [{sh_name}]: +{len(rows_nuevas)} filas nuevas")

# ════════════════════════════════════════════════════════════════
# 1. FRED — series US e internacionales
# ════════════════════════════════════════════════════════════════
print("\n[FRED] Series EE.UU. e internacionales...")

# Initial Claims (semanal)
sh = 'Initial Claims'
uf = ultima_fecha_sheet(wb[sh])
start = (uf + timedelta(days=7)).isoformat() if uf else '2022-01-01'
data = fred('ICSA', start=start)
rows = []
for dt_str, val in data:
    d = parse_date(dt_str)
    if d: rows.append([to_excel_date(d), int(float(val))])
update_sheet(sh, rows, f"hasta {rows[-1][0].date() if rows else '?'}")
time.sleep(0.3)

# US Trade Balance (mensual, B USD)
sh = 'Commercial Balance - US'
uf = ultima_fecha_sheet(wb[sh])
start = (uf.replace(day=1)).isoformat() if uf else '2022-01-01'
data = fred('BOPGSTB', start=start)
rows = []
for dt_str, val in data:
    d = parse_date(dt_str)
    if d: rows.append([to_excel_date(d), round(float(val)/1000, 2)])  # M→B USD
update_sheet(sh, rows, f"BOPGSTB")
time.sleep(0.3)

# Balanza Comercial US (misma serie, misma hoja)
sh = 'Balanza Comercial US'
uf = ultima_fecha_sheet(wb[sh])
start = (uf.replace(day=1)).isoformat() if uf else '2022-01-01'
data_exp = fred('BOPXGS', start=start)   # exports
data_imp = fred('BOPIGS', start=start)   # imports
time.sleep(0.3)
rows = []
exp_dict = {parse_date(d): float(v) for d,v in data_exp}
imp_dict = {parse_date(d): float(v) for d,v in data_imp}
for d in sorted(set(exp_dict) | set(imp_dict)):
    exp = exp_dict.get(d)
    imp = imp_dict.get(d)
    if exp or imp:
        rows.append([to_excel_date(d), round(exp/1000,2) if exp else None,
                                       round(imp/1000,2) if imp else None,
                                       round((exp-imp)/1000,2) if (exp and imp) else None])
update_sheet(sh, rows, "BOPXGS/BOPIGS")
time.sleep(0.3)

# Import/Export Prices (mensual)
sh = 'Imports-Exports Prices'
uf = ultima_fecha_sheet(wb[sh])
start = (uf.replace(day=1)).isoformat() if uf else '2022-01-01'
data_imp = fred('IR', start=start)     # import price index
data_exp = fred('IQ', start=start)     # export price index
time.sleep(0.3)
rows = []
imp_d = {parse_date(d): float(v) for d,v in data_imp}
exp_d = {parse_date(d): float(v) for d,v in data_exp}
for d in sorted(set(imp_d) | set(exp_d)):
    rows.append([to_excel_date(d), imp_d.get(d), exp_d.get(d)])
update_sheet(sh, rows, "IR/IQ")
time.sleep(0.3)

# US GDP trimestral
sh = 'GDP - US'
uf = ultima_fecha_sheet(wb[sh])
start = '2015-01-01'
data_lvl  = fred('GDPC1', start=start, freq='q')    # nivel real (B USD 2017)
data_qoq  = fred('A191RL1Q225SBEA', start=start, freq='q')  # QoQ anualizado
data_yoy  = fred('A191RO1Q156NBEA', start=start, freq='q')  # YoY
time.sleep(0.3)
rows = []
lvl_d = {parse_date(d): float(v) for d,v in data_lvl}
qoq_d = {parse_date(d): float(v) for d,v in data_qoq}
yoy_d = {parse_date(d): float(v) for d,v in data_yoy}
for d in sorted(set(lvl_d) | set(qoq_d)):
    rows.append([to_excel_date(d), lvl_d.get(d), qoq_d.get(d), yoy_d.get(d)])
# Reemplazar hoja completamente (tiene formato raro sin fechas)
if rows:
    ws = wb[sh]
    ws.delete_rows(2, ws.max_row)
    ws.cell(row=1, column=1, value='Fecha')
    ws.cell(row=1, column=2, value='PIB Real (B USD 2017)')
    ws.cell(row=1, column=3, value='Var QoQ anualizada %')
    ws.cell(row=1, column=4, value='Var YoY %')
    for r in rows:
        ws.append(r)
    resultados['ok'].append(f"{sh}: reconstruido ({len(rows)} trimestres)")
    print(f"  ✓ [{sh}]: {len(rows)} trimestres (GDPC1+A191RL1Q225SBEA+A191RO1Q156NBEA)")
time.sleep(0.3)

# Japan CPI
sh = 'CPI - JP'
uf = ultima_fecha_sheet(wb[sh])
start = (uf.replace(day=1)).isoformat() if uf else '2022-01-01'
data_yoy  = fred('JPNCPIALLMINMEI', start=start)   # YoY %
data_core = fred('JPNCPICORMINMEI', start=start)    # Core YoY %
time.sleep(0.3)
rows = []
yoy_d = {parse_date(d): float(v) for d,v in data_yoy}
cor_d = {parse_date(d): float(v) for d,v in data_core}
for d in sorted(yoy_d):
    rows.append([to_excel_date(d), yoy_d[d], cor_d.get(d)])
update_sheet(sh, rows, "JPNCPIALLMINMEI")
time.sleep(0.3)

# China CPI (FRED)
sh = 'CPI - China'
uf = ultima_fecha_sheet(wb[sh])
start = (uf.replace(day=1)).isoformat() if uf else '2022-01-01'
data = fred('CHNCPIALLMINMEI', start=start)
rows = []
for dt_str, val in data:
    d = parse_date(dt_str)
    if d: rows.append([to_excel_date(d), round(float(val), 2)])
update_sheet(sh, rows, "CHNCPIALLMINMEI")
time.sleep(0.3)

# EU Trade Balance (Eurostat — ext_st_eu27_2020sitc)
sh = 'Balance Trade EU'
uf = ultima_fecha_sheet(wb[sh])
since = uf.strftime('%Y-%m') if uf else '2022-01'
url_eu = (f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
          f"ext_st_eu27_2020sitc?format=JSON&lang=EN&freq=M&sitc06=TOTAL"
          f"&partner=EXT_EU27_2020&geo=EU27_2020&sinceTimePeriod={since}")
eu_resp = fetch(url_eu, timeout=20) or {}
rows = []
if 'dimension' in eu_resp:
    eu_dims = eu_resp['dimension']; eu_ids = eu_resp['id']
    eu_sizes = eu_resp['size']; eu_vals = eu_resp['value']
    eu_flows  = list(eu_dims['stk_flow']['category']['index'].keys())
    eu_indics = list(eu_dims['indic_et']['category']['index'].keys())
    eu_times  = list(eu_dims['time']['category']['index'].keys())
    n_f = eu_sizes[eu_ids.index('stk_flow')]
    n_i = eu_sizes[eu_ids.index('indic_et')]
    n_t = eu_sizes[eu_ids.index('time')]
    trd_i = eu_indics.index('TRD_VAL')
    imp_fi = eu_flows.index('IMP'); exp_fi = eu_flows.index('EXP')
    for t_i, t_str in enumerate(eu_times):
        imp = eu_vals.get(str((imp_fi * n_i + trd_i) * n_t + t_i))
        exp = eu_vals.get(str((exp_fi * n_i + trd_i) * n_t + t_i))
        if imp is not None and exp is not None:
            d = parse_date(t_str + '-01')
            bal = round(float(exp) - float(imp), 2)
            rows.append([to_excel_date(d), round(float(imp),2), round(float(exp),2), bal])
update_sheet(sh, rows, "ext_st_eu27_2020sitc/Eurostat")
time.sleep(0.3)

# ════════════════════════════════════════════════════════════════
# 2. BCB — Brasil
# ════════════════════════════════════════════════════════════════
print("\n[BCB] Series Brasil...")

def bcb_desde(sh_name, series_id, cols, transform=None):
    uf = ultima_fecha_sheet(wb[sh_name]) if sh_name in wb.sheetnames else None
    start_d = (uf + timedelta(days=1)) if uf else date(2022, 1, 1)
    start_str = start_d.strftime('%d/%m/%Y')
    data = bcb(series_id, start=start_str)
    rows = []
    for dt_str, val in data:
        d = parse_date(dt_str)
        if d and d > (uf or date(2000,1,1)):
            v = float(str(val).replace(',','.'))
            if transform: v = transform(v)
            rows.append([to_excel_date(d), round(v, 4)])
    update_sheet(sh_name, rows, f"BCB serie {series_id}")
    time.sleep(0.5)

# IBC-Br (proxy actividad mensual) — serie 24363
bcb_desde('IBC-Br', 24363, ['Fecha','IBC-Br'])

# Desempleo Brasil (PNAD) — serie 24369
bcb_desde('Desempleo - Br', 24369, ['Fecha','Desempleo %'])

# INPC Brasil — serie 188 (MoM %)
bcb_desde('INPC - Br', 188, ['Fecha','INPC MoM %'])

# PIM Brasil (Produccion industrial) — serie 21859
bcb_desde('PIM - Br', 21859, ['Fecha','PIM YoY %'])

# Cuenta corriente Brasil (M USD) — serie 22707
bcb_desde('Cuenta Corriente - Br', 22707, ['Fecha','Cta Corriente M USD'])

# Balanza Comercial Brasil (M USD) — serie 22704
bcb_desde('Balanza Comercial - Br', 22704, ['Fecha','Saldo M USD'])

# PIB Brasil trimestral (YoY %) — serie 22099
sh = 'PIB - Br'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start_str = (uf + timedelta(days=1)).strftime('%d/%m/%Y') if uf else '01/01/2015'
data = bcb(22099, start=start_str)
rows = []
for dt_str, val in data:
    d = parse_date(dt_str)
    if d and d > (uf or date(2000,1,1)):
        rows.append([to_excel_date(d), round(float(str(val).replace(',','.')), 2)])
update_sheet(sh, rows, "BCB serie 22099 (PIB YoY)")
time.sleep(0.5)

# IPP Brasil — serie 27574
bcb_desde('IPP - Br', 27574, ['Fecha','IPP MoM %'])

# ════════════════════════════════════════════════════════════════
# 3. BCRA — Argentina financiero
# ════════════════════════════════════════════════════════════════
print("\n[BCRA] Series Argentina financiero...")

# Tipo de Cambio de Referencia (var 4)
sh = 'Tipo de Cambio RM'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start_str = (uf + timedelta(days=1)).isoformat() if uf else '2022-01-01'
data_tc = bcra(4, start=start_str)
rows_tc = []
seen = set()
for fecha_str, val in data_tc:
    d = parse_date(fecha_str)
    if d and d not in seen and d > (uf or date(2000,1,1)):
        seen.add(d)
        rows_tc.append([to_excel_date(d), round(float(val), 2)])
update_sheet(sh, rows_tc, "BCRA var 4 (TC referencia)")
time.sleep(0.5)

# Posición neta BCRA (var 1)
sh = 'Posición neta del BCRA'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start_str = (uf + timedelta(days=1)).isoformat() if uf else '2024-01-01'
data_pn = bcra(1, start=start_str)
rows_pn = []
seen = set()
for fecha_str, val in data_pn:
    d = parse_date(fecha_str)
    if d and d not in seen and d > (uf or date(2000,1,1)):
        seen.add(d)
        rows_pn.append([to_excel_date(d), round(float(val), 2)])
update_sheet(sh, rows_pn, "BCRA var 1 (posición neta)")
time.sleep(0.5)

# ════════════════════════════════════════════════════════════════
# 4. argentinadatos.com — Riesgo País, Merval, Dólar
# ════════════════════════════════════════════════════════════════
print("\n[argentinadatos.com] Mercados Argentina...")

# Riesgo País
sh = 'Riesgo País'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
data_rp = argdata('finanzas/indices/riesgo-pais')
if isinstance(data_rp, list):
    rows = []
    for r in data_rp:
        d = parse_date(r.get('fecha',''))
        v = r.get('valor')
        if d and v is not None and d > (uf or date(2022,1,1)):
            rows.append([to_excel_date(d), int(v)])
    update_sheet(sh, rows, "argentinadatos riesgo-pais")
else:
    resultados['error'].append(f"{sh}: sin datos de argentinadatos")
time.sleep(0.5)

# Merval USD — calcular desde peso y CCL, o buscar endpoint
sh = 'MERVAL USD'
data_merval = argdata('finanzas/indices/merval')
if isinstance(data_merval, list):
    rows = []
    for r in data_merval:
        d = parse_date(r.get('fecha',''))
        v = r.get('valor')
        if d and v is not None and d > (uf or date(2022,1,1)) if (uf := ultima_fecha_sheet(wb[sh])) else True:
            rows.append([to_excel_date(d), round(float(v), 2)])
    if rows:
        uf2 = ultima_fecha_sheet(wb[sh])
        rows = [r for r in rows if r[0].date() > (uf2 or date(2000,1,1))]
    update_sheet(sh, rows, "argentinadatos merval")
else:
    resultados['error'].append(f"{sh}: sin datos merval")
time.sleep(0.5)

# Dólar (histórico diario)
sh = 'Dólar'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
data_dol = argdata('cotizaciones/dolares/oficial')
if isinstance(data_dol, list):
    rows = []
    for r in data_dol:
        d = parse_date(r.get('fecha',''))
        v = r.get('venta') or r.get('valor')
        if d and v is not None and d > (uf or date(2022,1,1)):
            rows.append([to_excel_date(d), round(float(v), 2)])
    update_sheet(sh, rows, "argentinadatos dolar/oficial")
else:
    resultados['error'].append(f"{sh}: sin datos dolar")
time.sleep(0.5)

# ════════════════════════════════════════════════════════════════
# 5. INDEC datos.gob.ar — series Argentina estadísticas
# ════════════════════════════════════════════════════════════════
print("\n[datos.gob.ar] Series INDEC...")

BASE_DATOS = "https://apis.datos.gob.ar/series/api/series"

def indec_series(series_ids, start='2022-01-01', freq='month', limit=1000):
    ids = ','.join(series_ids)
    url = f"{BASE_DATOS}?ids={ids}&start_date={start}&frequency={freq}&limit={limit}&format=json"
    d = fetch(url)
    if not d or 'data' not in d: return [], []
    return d['data'], d.get('meta', [])

# IPI — Índice de Producción Industrial (serie IPI: 11.3_VVIVP_2004_M_15)
sh = 'IPI'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start = (uf.replace(day=1)).isoformat() if uf else '2022-01-01'
# Nivel general IPI: 11.3_VVIVP_2004_M_15
# YoY: 11.3_VVIVP_2004_M_26
data, meta = indec_series(['11.3_VVIVP_2004_M_15','11.3_VVIVP_2004_M_26'], start=start)
rows = []
for r in data:
    d = parse_date(r[0])
    if d and d > (uf or date(2000,1,1)):
        idx = r[1]  # nivel
        yoy = r[2] if len(r) > 2 else None  # YoY %
        if idx is not None:
            rows.append([to_excel_date(d), round(float(idx),2), round(float(yoy)*100,2) if yoy else None])
update_sheet(sh, rows, "datos.gob.ar IPI")
time.sleep(0.5)

# ISAC — Indicador Sintético de Actividad de la Construcción
sh = 'ISAC'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start = (uf.replace(day=1)).isoformat() if uf else '2022-01-01'
data, _ = indec_series(['11.3_ISAC_2004_M_14','11.3_ISAC_2004_M_27'], start=start)
rows = []
for r in data:
    d = parse_date(r[0])
    if d and d > (uf or date(2000,1,1)):
        idx = r[1]
        yoy = r[2] if len(r) > 2 else None
        if idx is not None:
            rows.append([to_excel_date(d), round(float(idx),2), round(float(yoy)*100,2) if yoy else None])
update_sheet(sh, rows, "datos.gob.ar ISAC")
time.sleep(0.5)

# EMAE
sh = 'EMAE'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start = (uf.replace(day=1)).isoformat() if uf else '2022-01-01'
data, _ = indec_series(['143.3_NO_PR_2004_A_21','143.3_NO_PR_2004_A_33'], start=start)
rows = []
for r in data:
    d = parse_date(r[0])
    if d and d > (uf or date(2000,1,1)):
        idx = r[1]
        yoy = r[2] if len(r) > 2 else None
        if idx is not None:
            rows.append([to_excel_date(d), None, round(float(idx),2), None,
                        round(float(yoy)*100,2) if yoy else None])
update_sheet(sh, rows, "datos.gob.ar EMAE")
time.sleep(0.5)

# IPC Histórico (IPC 2000-)
sh = 'IPC 2000-'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start = (uf.replace(day=1)).isoformat() if uf else '2022-01-01'
data, _ = indec_series(['145.3_INPC_2016_M_19','145.3_INPC_2016_M_26'], start=start)
rows = []
for r in data:
    d = parse_date(r[0])
    if d and d > (uf or date(2000,1,1)):
        mom = r[1]
        yoy = r[2] if len(r) > 2 else None
        if mom is not None:
            rows.append([to_excel_date(d),
                        round(float(mom)*100, 2) if float(mom) < 2 else round(float(mom),2),
                        round(float(yoy)*100, 2) if (yoy and float(yoy) < 2) else (round(float(yoy),2) if yoy else None)])
update_sheet(sh, rows, "datos.gob.ar IPC MoM/YoY")
time.sleep(0.5)

# Turismo (llegadas internacionales)
sh = 'Turismo'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start = (uf.replace(day=1)).isoformat() if uf else '2022-01-01'
data, _ = indec_series(['116.3_VLLANR_0_M_22'], start=start)
rows = []
for r in data:
    d = parse_date(r[0])
    if d and d > (uf or date(2000,1,1)) and r[1] is not None:
        rows.append([to_excel_date(d), int(float(r[1]))])
update_sheet(sh, rows, "datos.gob.ar Turismo")
time.sleep(0.5)

# Liquidación Agropecuaria (CIARA mensual)
sh = 'Liq. Agro'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
data_liq = fetch("https://api.argentinadatos.com/v1/finanzas/liquidaciones/agropecuarias/mensual")
if isinstance(data_liq, list):
    rows = []
    for r in data_liq:
        d = parse_date(r.get('fecha','') or r.get('periodo',''))
        v = r.get('monto') or r.get('valor') or r.get('liquidacion')
        if d and v is not None and d > (uf or date(2022,1,1)):
            rows.append([to_excel_date(d), round(float(v), 2)])
    update_sheet(sh, rows, "argentinadatos liquidaciones agro")
else:
    resultados['manual'].append("Liq. Agro — actualizar desde ciara.org.ar")
time.sleep(0.5)

# Futuros ROFEX (no hay API pública gratuita)
resultados['manual'].append("Futuros ROFEX — requiere cuenta MatbaRofex")

# PBI Argentina trimestral
sh = 'PBI'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start = (uf.replace(day=1)).isoformat() if uf else '2015-01-01'
data, _ = indec_series(['11.3_VBPIB_0_T_36','11.3_VBPIB_0_T_34'], start=start, freq='quarter')
rows = []
for r in data:
    d = parse_date(r[0])
    if d and d > (uf or date(2000,1,1)) and r[1] is not None:
        yoy = r[2] if len(r) > 2 else None
        rows.append([to_excel_date(d), None, round(float(r[1]),2),
                    round(float(yoy)*100,2) if (yoy and abs(float(yoy)) < 5) else (round(float(yoy),2) if yoy else None)])
update_sheet(sh, rows, "datos.gob.ar PIB trimestral")
time.sleep(0.5)

# EPH (Desempleo trimestral)
sh = 'EPH'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start = (uf.replace(day=1)).isoformat() if uf else '2016-01-01'
# Tasa de desempleo EPH: 41.1_TDES_TOTAL_0_T_36 (aprox)
data, _ = indec_series(['41.1_TDES_TOTAL_0_T_36','41.1_TACT_TOTAL_0_T_36'], start=start, freq='quarter')
rows = []
for r in data:
    d = parse_date(r[0])
    if d and d > (uf or date(2000,1,1)) and r[1] is not None:
        desempleo = round(float(r[1])*100,1) if float(r[1]) < 1 else round(float(r[1]),1)
        actividad = None
        if len(r) > 2 and r[2] is not None:
            actividad = round(float(r[2])*100,1) if float(r[2]) < 1 else round(float(r[2]),1)
        rows.append([to_excel_date(d), desempleo, actividad])
update_sheet(sh, rows, "datos.gob.ar EPH")
time.sleep(0.5)

# ════════════════════════════════════════════════════════════════
# 6. Índices ETF US (Finnhub)
# ════════════════════════════════════════════════════════════════
print("\n[Finnhub] ETFs US...")
FINNHUB_KEY = 'd8ou0apr01qn89hv5irgd8ou0apr01qn89hv5is0'
sh = 'Índices ETF US'
uf = ultima_fecha_sheet(wb[sh]) if sh in wb.sheetnames else None
start_ts = int(datetime(uf.year, uf.month, uf.day).timestamp()) if uf else int(datetime(2026,1,1).timestamp())
end_ts = int(datetime.now().timestamp())

rows_etf = {}
for sym in ['SPY','QQQ','GLD','USO','UUP']:
    url = (f"https://finnhub.io/api/v1/stock/candle?symbol={sym}"
           f"&resolution=D&from={start_ts}&to={end_ts}&token={FINNHUB_KEY}")
    d = fetch(url)
    if d and d.get('s') == 'ok' and 't' in d:
        for i, ts in enumerate(d['t']):
            day = date.fromtimestamp(ts)
            if day not in rows_etf: rows_etf[day] = {}
            rows_etf[day][sym] = round(d['c'][i], 2)
    time.sleep(0.2)

rows = []
for day in sorted(rows_etf):
    r = rows_etf[day]
    rows.append([to_excel_date(day), r.get('SPY'), r.get('QQQ'),
                 r.get('GLD'), r.get('USO'), r.get('UUP')])
update_sheet(sh, rows, "Finnhub SPY/QQQ/GLD/USO/UUP")

# ════════════════════════════════════════════════════════════════
# GUARDAR y REPORTE
# ════════════════════════════════════════════════════════════════
print("\nGuardando workbooks...")
import os as _os
total_size = 0
for f in ARCHIVOS:
    _workbooks[f].save(BASE_DIR + f)
    sz = _os.path.getsize(BASE_DIR + f) / (1024*1024)
    total_size += sz
    print(f"  {f}: {sz:.1f} MB")

print(f"\n{'='*60}")
print(f"RESULTADO FINAL — {total_size:.1f} MB total ({len(ARCHIVOS)} archivos)")
print(f"{'='*60}")

print(f"\n✅ ACTUALIZADAS ({len(resultados['ok'])}):")
for s in resultados['ok']: print(f"   {s}")

if resultados['error']:
    print(f"\n⚠️  SIN DATOS DE API ({len(resultados['error'])}):")
    for s in resultados['error']: print(f"   {s}")

if resultados['manual']:
    print(f"\n📋 REQUIEREN ACTUALIZACIÓN MANUAL ({len(resultados['manual'])}):")
    for s in resultados['manual']: print(f"   {s}")
