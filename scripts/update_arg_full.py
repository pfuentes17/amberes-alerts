"""
Extrae TODAS las series argentinas disponibles en /Users/pedrofuentes/Documents/Series/
y actualiza data/seed.json con las series nuevas y extendidas.
"""
import json, os
from datetime import datetime
from collections import defaultdict
from openpyxl import load_workbook

SERIES_DIR = '/Users/pedrofuentes/Documents/Series'
SEED_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'seed.json')
MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

def fmt_mes(fecha):
    if isinstance(fecha, str): return fecha
    return f"{MESES[fecha.month-1]} {str(fecha.year)[2:]}"

def fmt_q(s):
    # "2025 III" → "Q3 25", "2025 I" → "Q1 25"
    rom = {"I":1, "II":2, "III":3, "IV":4}
    try:
        parts = str(s).strip().split()
        yr = parts[0][-2:]
        n = rom.get(parts[1], 0)
        return f"Q{n} {yr}" if n else None
    except: return None

def clean(v):
    if v is None or str(v) in ('#DIV/0!','#REF!','#VALUE!','#N/A','#NAME?','///'): return None
    try: return float(v)
    except: return None

def r1(v, dec=1):
    v = clean(v)
    return None if v is None else round(v, dec)

def pct(v, dec=1):
    v = clean(v)
    if v is None: return None
    # si viene como decimal (0.038 = 3.8%), convertir
    if abs(v) < 5: return round(v * 100, dec)
    return round(v, dec)

def monthly_agg(rows, fecha_col=0, val_col=1, agg='last'):
    """Agrega serie diaria a mensual."""
    monthly = {}
    counts = defaultdict(list)
    for r in rows:
        if r[fecha_col] is None: continue
        v = clean(r[val_col])
        if v is None: continue
        try:
            fd = r[fecha_col]
            key = (fd.year, fd.month)
            counts[key].append(v)
        except: continue
    result = {}
    for k in sorted(counts.keys()):
        vals = counts[k]
        if agg == 'last': result[k] = vals[-1]
        elif agg == 'avg': result[k] = round(sum(vals)/len(vals), 1)
    return result

# ── Cargar seed actual ──
with open(SEED_PATH) as f:
    D = json.load(f)
if 'arg' not in D: D['arg'] = {}
A = D['arg']

print("=" * 60)
print("Extrayendo series argentinas de Series.xlsx ...")
print("=" * 60)

wb = load_workbook(f'{SERIES_DIR}/Series.xlsx', read_only=True, data_only=True)

# ── 1. BALANZA COMERCIAL ARGENTINA (expo + impo) ──
ws = wb['Balanza Comercial Argentina']
rows = list(ws.iter_rows(values_only=True))
bc_l, bc_expo, bc_impo, bc_saldo = [], [], [], []
for r in rows:
    if r[1] is None or not hasattr(r[1], 'year'): continue
    expo = clean(r[2])
    impo = clean(r[10]) if len(r) > 10 else None
    if expo is None: continue
    lbl = fmt_mes(r[1])
    bc_l.append(lbl)
    bc_expo.append(int(round(expo)))
    bc_impo.append(int(round(impo)) if impo is not None else None)
    if impo is not None:
        bc_saldo.append(int(round(expo - impo)))
    else:
        bc_saldo.append(None)
# Tomar últimos 60 meses
n = 60
A['balanzaComercial'] = {
    'l': bc_l[-n:], 'expo': bc_expo[-n:],
    'impo': bc_impo[-n:], 'saldo': bc_saldo[-n:]
}
print(f"  balanzaComercial: {len(bc_l[-n:])} períodos | {bc_l[-n]} → {bc_l[-1]}")

# ── 2. IPI (Producción Industrial) ──
ws = wb['IPI']
rows = list(ws.iter_rows(values_only=True))
ipi_l, ipi_v, ipi_idx = [], [], []
for r in rows:
    if r[0] is None or not hasattr(r[0], 'year'): continue
    yoy = clean(r[2])
    idx = clean(r[1])
    if idx is None: continue
    lbl = fmt_mes(r[0])
    ipi_l.append(lbl)
    # YoY puede ser decimal o % directo
    if yoy is not None:
        yoy_pct = pct(yoy) if abs(yoy) < 2 else round(yoy, 1)
        ipi_v.append(yoy_pct)
    else:
        ipi_v.append(None)
    ipi_idx.append(round(idx, 1))
n = 48
A['ipi'] = {'l': ipi_l[-n:], 'v': ipi_v[-n:], 'idx': ipi_idx[-n:]}
last_valid = [(l,v) for l,v in zip(ipi_l, ipi_v) if v is not None]
print(f"  ipi: {len(ipi_l[-n:])} períodos | último YoY válido: {last_valid[-1] if last_valid else 'N/A'}")

# ── 3. ISAC (Construcción) ──
ws = wb['ISAC']
rows = list(ws.iter_rows(values_only=True))
isac_l, isac_v, isac_idx = [], [], []
for r in rows:
    if r[0] is None or not hasattr(r[0], 'year'): continue
    yoy = clean(r[2])
    idx = clean(r[1])
    if idx is None: continue
    lbl = fmt_mes(r[0])
    isac_l.append(lbl)
    isac_v.append(pct(yoy) if (yoy is not None and abs(yoy) < 2) else (round(yoy, 1) if yoy is not None else None))
    isac_idx.append(round(idx, 1))
n = 48
A['isac'] = {'l': isac_l[-n:], 'v': isac_v[-n:], 'idx': isac_idx[-n:]}
last_valid_isac = [(l,v) for l,v in zip(isac_l, isac_v) if v is not None]
print(f"  isac: {len(isac_l[-n:])} períodos | último YoY válido: {last_valid_isac[-1] if last_valid_isac else 'N/A'}")

# ── 4. ICC (Índice de Costos de Construcción) ──
ws = wb['ICC']
rows_icc = []
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i > 500: break
    rows_icc.append(row)
icc_l, icc_yoy, icc_mom = [], [], []
for r in rows_icc:
    if r[0] is None or not hasattr(r[0], 'year'): continue
    yoy = clean(r[2])
    mom = clean(r[3])
    if yoy is None and mom is None: continue
    lbl = fmt_mes(r[0])
    icc_l.append(lbl)
    icc_yoy.append(pct(yoy) if (yoy is not None and abs(yoy) < 2) else (round(yoy, 1) if yoy is not None else None))
    icc_mom.append(pct(mom) if (mom is not None and abs(mom) < 2) else (round(mom, 1) if mom is not None else None))
n = 48
A['icc'] = {'l': icc_l[-n:], 'v': icc_yoy[-n:], 'mom': icc_mom[-n:]}
print(f"  icc: {len(icc_l[-n:])} períodos | último: {icc_l[-1] if icc_l else 'N/A'}")

# ── 5. PBI Argentina ──
ws = wb['PBI']
rows = list(ws.iter_rows(values_only=True))
pbi_l, pbi_yoy, pbi_qoq = [], [], []
for r in rows:
    if r[0] is None or 'Trimestre' in str(r[0]): continue
    lbl = fmt_q(r[0])
    if not lbl: continue
    yoy = clean(r[3])
    qoq = clean(r[2])
    pbi_l.append(lbl)
    pbi_yoy.append(round(yoy * 100, 1) if (yoy is not None and abs(yoy) < 1) else (round(yoy, 1) if yoy is not None else None))
    pbi_qoq.append(round(qoq * 100, 1) if (qoq is not None and abs(qoq) < 1) else (round(qoq, 1) if qoq is not None else None))
n = 24
A['pbi'] = {'l': pbi_l[-n:], 'yoy': pbi_yoy[-n:], 'qoq': pbi_qoq[-n:]}
print(f"  pbi: {len(pbi_l[-n:])} trimestres | {pbi_l[-n]} → {pbi_l[-1]} | YoY último: {pbi_yoy[-1]}")

# ── 6. SALARIOS ──
ws = wb['Salarios']
sal_l, sal_priv_nom, sal_pub_nom, sal_priv_real, sal_ipc_mom = [], [], [], [], []
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i > 600: break
    r = row
    if r[0] is None or not hasattr(r[0], 'year'): continue
    # col E = privado nominal index, col F = privado real, col H = público nominal, col B = IPC MoM
    priv = clean(r[4])   # col E: priv nominal
    priv_r = clean(r[5]) # col F: priv real
    pub = clean(r[7])    # col H: pub nominal
    ipc_m = clean(r[1])  # col B: IPC (index or MoM)
    if priv is None: continue
    sal_l.append(fmt_mes(r[0]))
    sal_priv_nom.append(round(priv, 1))
    sal_priv_real.append(round(priv_r, 1) if priv_r else None)
    sal_pub_nom.append(round(pub, 1) if pub else None)
    # col C = IPC MoM %
    ipc_mom_v = clean(r[2])
    sal_ipc_mom.append(pct(ipc_mom_v) if (ipc_mom_v is not None and abs(ipc_mom_v) < 2) else (round(ipc_mom_v,1) if ipc_mom_v else None))
n = 48
A['salarios'] = {
    'l': sal_l[-n:], 'privNom': sal_priv_nom[-n:],
    'privReal': sal_priv_real[-n:], 'pubNom': sal_pub_nom[-n:]
}
print(f"  salarios: {len(sal_l[-n:])} períodos | {sal_l[-n]} → {sal_l[-1]}")

# ── 7. POBREZA ──
ws = wb['Pobreza']
rows = list(ws.iter_rows(values_only=True))
pob_l, pob_personas, pob_hogares, pob_indigencia = [], [], [], []
for r in rows:
    if r[0] is None or 'Fecha' in str(r[0]): continue
    lbl = str(r[0]).strip()
    if not lbl or lbl == 'None': continue
    pers = clean(r[4])  # personas pobres %
    hog = clean(r[1])   # hogares pobres %
    indig = clean(r[5]) # indigencia personas %
    if pers is None: continue
    # convertir label "2025 I" → "Q1 25"
    qlab = fmt_q(lbl) or lbl
    pob_l.append(qlab)
    pob_personas.append(round(float(pers), 1))
    pob_hogares.append(round(float(hog), 1) if hog else None)
    pob_indigencia.append(round(float(indig), 1) if indig else None)
A['pobreza'] = {'l': pob_l, 'personas': pob_personas, 'hogares': pob_hogares, 'indigencia': pob_indigencia}
print(f"  pobreza: {len(pob_l)} semestres | {pob_l[0]} → {pob_l[-1]} | último: {pob_personas[-1]}%")

# ── 8. CBA-CBT (canasta básica) ──
ws = wb['CBA-CBT']
rows = list(ws.iter_rows(values_only=True))
cbt_l, cbt_cba, cbt_cbt = [], [], []
for r in rows:
    if r[0] is None or not hasattr(r[0], 'year'): continue
    cba = clean(r[1])
    cbt = clean(r[5])
    if cbt is None: continue
    cbt_l.append(fmt_mes(r[0]))
    cbt_cba.append(int(round(cba)) if cba else None)
    cbt_cbt.append(int(round(cbt)))
n = 48
A['cbt'] = {'l': cbt_l[-n:], 'cba': cbt_cba[-n:], 'cbt': cbt_cbt[-n:]}
print(f"  cbt: {len(cbt_l[-n:])} períodos | último: {cbt_l[-1]} | CBT={cbt_cbt[-1]} ARS")

# ── 9. LIQUIDACIÓN AGRO ──
ws = wb['Liq. Agro']
rows = list(ws.iter_rows(values_only=True))
liq_l, liq_v = [], []
for r in rows:
    if r[1] is None or not hasattr(r[1], 'year'): continue
    v = clean(r[2])
    if v is None: continue
    liq_l.append(fmt_mes(r[1]))
    liq_v.append(int(round(v)))
n = 48
A['liqAgro'] = {'l': liq_l[-n:], 'v': liq_v[-n:]}
print(f"  liqAgro: {len(liq_l[-n:])} períodos | {liq_l[-n]} → {liq_l[-1]} | último: {liq_v[-1]} MM USD")

# ── 10. BALANCE CAMBIARIO BCRA ──
ws = wb['Balance Cambiario BCRA']
rows = list(ws.iter_rows(values_only=True))
bc_cc_l, bc_cc, bc_bienes, bc_serv = [], [], [], []
for r in rows:
    if r[0] is None or not hasattr(r[0], 'year'): continue
    cc = clean(r[1])
    bienes = clean(r[2])
    serv = clean(r[3])
    if cc is None: continue
    bc_cc_l.append(fmt_mes(r[0]))
    bc_cc.append(int(round(cc)))
    bc_bienes.append(int(round(bienes)) if bienes else None)
    bc_serv.append(int(round(serv)) if serv else None)
n = min(36, len(bc_cc_l))
A['balanceCambiario'] = {
    'l': bc_cc_l[-n:], 'cc': bc_cc[-n:],
    'bienes': bc_bienes[-n:], 'servicios': bc_serv[-n:]
}
print(f"  balanceCambiario: {len(bc_cc_l)} períodos | {bc_cc_l[0] if bc_cc_l else 'N/A'} → {bc_cc_l[-1] if bc_cc_l else 'N/A'}")

# ── 11. IPC LARGO (2000-2024) ──
ws = wb['IPC 2000-2024']
rows = list(ws.iter_rows(values_only=True))
ipc_largo_l, ipc_largo_v = [], []
for r in rows:
    if r[0] is None or not hasattr(r[0], 'year'): continue
    v = clean(r[1])  # col B = MoM%
    if v is None: continue
    ipc_largo_l.append(fmt_mes(r[0]))
    ipc_largo_v.append(pct(v) if abs(v) < 2 else round(v, 1))
A['ipcLargo'] = {'l': ipc_largo_l, 'v': ipc_largo_v}
print(f"  ipcLargo: {len(ipc_largo_l)} períodos | {ipc_largo_l[0]} → {ipc_largo_l[-1]}")

# ── 12. RIESGO PAÍS (mensual promedio desde diario) ──
ws = wb['Riesgo Pais']
rows_rp = []
for row in ws.iter_rows(values_only=True):
    rows_rp.append(row)
rp_monthly = monthly_agg(rows_rp, fecha_col=0, val_col=1, agg='avg')
rp_l = [f"{MESES[k[1]-1]} {str(k[0])[2:]}" for k in sorted(rp_monthly.keys())]
rp_v = [round(rp_monthly[k]) for k in sorted(rp_monthly.keys())]
n = 60
A['riesgoPais'] = {'l': rp_l[-n:], 'v': rp_v[-n:]}
print(f"  riesgoPais: {len(rp_l[-n:])} períodos | {rp_l[-n]} → {rp_l[-1]} | último: {rp_v[-1]}")

# ── 13. MERVAL USD (mensual promedio) ──
ws = wb['MERVAL USD']
rows_m = []
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i > 15000: break
    rows_m.append(row)
merval_monthly = monthly_agg(rows_m, fecha_col=0, val_col=1, agg='avg')
mv_l = [f"{MESES[k[1]-1]} {str(k[0])[2:]}" for k in sorted(merval_monthly.keys())]
mv_v = [round(merval_monthly[k], 0) for k in sorted(merval_monthly.keys())]
n = min(36, len(mv_l))
A['mervalUSD'] = {'l': mv_l[-n:], 'v': mv_v[-n:]}
print(f"  mervalUSD: {len(mv_l)} períodos | {mv_l[0] if mv_l else 'N/A'} → {mv_l[-1] if mv_l else 'N/A'} | último: {mv_v[-1] if mv_v else 'N/A'}")

# ── 14. RESERVAS (mensual último día) ──
ws = wb['Reservas Internacionales']
rows_res = []
for row in ws.iter_rows(values_only=True):
    rows_res.append(row)
res_monthly = monthly_agg(rows_res, fecha_col=0, val_col=1, agg='last')
res_netas = monthly_agg(rows_res, fecha_col=0, val_col=4, agg='last')
res_l = [f"{MESES[k[1]-1]} {str(k[0])[2:]}" for k in sorted(res_monthly.keys())]
res_v = [round(res_monthly[k]) for k in sorted(res_monthly.keys())]
res_n = [round(res_netas.get(k, 0)) for k in sorted(res_monthly.keys())]
n = 60
A['reservasBrutas'] = {'l': res_l[-n:], 'v': res_v[-n:], 'netas': res_n[-n:]}
print(f"  reservasBrutas: {len(res_l[-n:])} períodos | {res_l[-n]} → {res_l[-1]} | último brutas: {res_v[-1]} MM USD")

# ── 15. DÓLAR (mensual promedio) ──
ws = wb['Dolar']
rows_d = list(ws.iter_rows(values_only=True))
dol_oficial = monthly_agg(rows_d, fecha_col=0, val_col=1, agg='avg')
dol_ccl = monthly_agg(rows_d, fecha_col=0, val_col=4, agg='avg')
dol_l = [f"{MESES[k[1]-1]} {str(k[0])[2:]}" for k in sorted(dol_oficial.keys())]
dol_of = [round(dol_oficial[k]) for k in sorted(dol_oficial.keys())]
dol_cc = [round(dol_ccl.get(k, 0)) for k in sorted(dol_oficial.keys())]
n = min(24, len(dol_l))
A['dolar'] = {'l': dol_l[-n:], 'oficial': dol_of[-n:], 'ccl': dol_cc[-n:]}
print(f"  dolar: {len(dol_l)} períodos | {dol_l[0] if dol_l else 'N/A'} → {dol_l[-1] if dol_l else 'N/A'} | último oficial: {dol_of[-1] if dol_of else 'N/A'}")

wb.close()

# ── También tomar Balanza Comercial con Importaciones de IPIs y Economia Real ──
print("\nExtrayendo de Economia Real.xlsx ...")
wb2 = load_workbook(f'{SERIES_DIR}/Economia Real.xlsx', read_only=True, data_only=True)

# Despacho cemento
if 'Despacho cemento' in wb2.sheetnames:
    ws = wb2['Despacho cemento']
    rows = list(ws.iter_rows(values_only=True))
    cem_l, cem_v, cem_yoy = [], [], []
    for r in rows:
        if r[1] is None or not hasattr(r[1], 'year'): continue
        v = clean(r[2])
        yoy = clean(r[3])
        if v is None: continue
        cem_l.append(fmt_mes(r[1]))
        cem_v.append(int(round(v/1000)) if v else None)  # en miles ton
        cem_yoy.append(pct(yoy) if (yoy and abs(yoy) < 2) else (round(yoy*100,1) if yoy else None))
    n = 48
    A['cemento'] = {'l': cem_l[-n:], 'v': cem_v[-n:], 'yoy': cem_yoy[-n:]}
    print(f"  cemento: {len(cem_l[-n:])} períodos | {cem_l[-n]} → {cem_l[-1]}")

# Produccion automotor
if 'Produccion automotor' in wb2.sheetnames:
    ws = wb2['Produccion automotor']
    rows = list(ws.iter_rows(values_only=True))
    auto_l, auto_prod, auto_expo = [], [], []
    for r in rows:
        if r[1] is None or not hasattr(r[1], 'year'): continue
        prod = clean(r[2])
        expo = clean(r[7]) if len(r) > 7 else None
        if prod is None: continue
        auto_l.append(fmt_mes(r[1]))
        auto_prod.append(int(round(prod)))
        auto_expo.append(int(round(expo)) if expo else None)
    n = 48
    if auto_l:
        A['autos'] = {'l': auto_l[-n:], 'prod': auto_prod[-n:], 'expo': auto_expo[-n:]}
        last_valid_auto = [(l,v) for l,v in zip(auto_l, auto_prod) if v and v > 0]
        print(f"  autos: {len(auto_l[-n:])} períodos | último válido: {last_valid_auto[-1] if last_valid_auto else 'N/A'}")

wb2.close()

# ── Actualizar metadata ──
D['_meta'] = {
    'updated': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
    'source': 'xlsx_update_arg_full.py'
}

# ── Guardar ──
with open(SEED_PATH, 'w') as f:
    json.dump(D, f, ensure_ascii=False, separators=(',', ':'))

# Verificar JSON válido
with open(SEED_PATH) as f:
    json.load(f)

size = os.path.getsize(SEED_PATH) / 1024
print(f"\n✓ seed.json actualizado ({size:.1f} KB)")
print(f"✓ Nuevas claves en arg: balanzaComercial, ipi, isac, icc, pbi, salarios, pobreza, cbt, liqAgro, balanceCambiario, ipcLargo, riesgoPais, mervalUSD, reservasBrutas, dolar, cemento, autos")
