"""
update_seed_from_apis.py — Parchea data/seed.json directamente desde APIs públicas.

Fuentes: FRED, BCB (Brasil), BCRA, argentinadatos.com, datos.gob.ar

Uso:
  python3 scripts/update_seed_from_apis.py          # solo actualiza seed.json
  python3 scripts/update_seed_from_apis.py --deploy  # actualiza + npx vercel --prod --yes
"""
import json, sys, time, subprocess
from datetime import date, datetime
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

ROOT      = Path(__file__).parent.parent
SEED_PATH = ROOT / "data" / "seed.json"
FRED_KEY  = "e4fb63601eef13d8e1d74ee8ffb95888"
DEPLOY    = "--deploy" in sys.argv

MESES = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
         7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}

def lbl(year, month):
    return f"{MESES[month]} {str(year)[-2:]}"

def lbl_q(year, quarter):
    return f"Q{quarter} {str(year)[-2:]}"

def fetch(url, headers=None, retries=2):
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
    return None

def fred(series_id, units="lin", limit=36, freq=None):
    # sort_order=desc + reverse → últimos N registros en orden ascendente
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_KEY}&file_type=json"
           f"&sort_order=desc&limit={limit}&units={units}")
    if freq:
        url += f"&frequency={freq}"
    d = fetch(url)
    if not d or "observations" not in d:
        return []
    rows = [(o["date"], float(o["value"])) for o in d["observations"]
            if o["value"] not in (".", "")]
    return list(reversed(rows))

def bcb(series_id, start="01/01/2023"):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados?formato=json&dataInicial={start}"
    d = fetch(url)
    if not isinstance(d, list):
        return []
    return [(r["data"], float(r["valor"])) for r in d if "data" in r and "valor" in r]

def bcra(variable_id, start="2023-01-01"):
    url = f"https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/{variable_id}?desde={start}"
    d = fetch(url, headers={"Accept": "application/json"})
    if not d or "results" not in d:
        return []
    rows = []
    for r in d["results"]:
        for det in r.get("detalle", []):
            rows.append((det["fecha"], float(det["valor"])))
    return rows

def argdata(endpoint):
    return fetch(f"https://api.argentinadatos.com/v1/{endpoint}")

def datosgob(series_id, limit=36):
    # sort=desc → más recientes primero; luego revertir para orden cronológico
    url = f"https://apis.datos.gob.ar/series/api/series/?ids={series_id}&limit={limit}&sort=desc"
    d = fetch(url)
    if not d or "data" not in d:
        return []
    rows = [(row[0], row[1]) for row in d["data"] if row[1] is not None]
    return list(reversed(rows))

def monthly_avg(weekly_rows):
    """Agrega serie semanal a mensual (promedio)."""
    buckets = defaultdict(list)
    for date_str, val in weekly_rows:
        y, m = int(date_str[:4]), int(date_str[5:7])
        buckets[(y, m)].append(val)
    result = {}
    for (y, m) in sorted(buckets):
        result[(y, m)] = round(sum(buckets[(y, m)]) / len(buckets[(y, m)]), 1)
    return result

def mompct(rows, decimals=1):
    """Calcula variación MoM desde serie de niveles."""
    result = []
    prev = None
    for date_str, val in rows:
        if prev is not None and prev != 0:
            pct = round((val / prev - 1) * 100, decimals)
            result.append((date_str, pct))
        prev = val
    return result

def parse_date(s):
    """Convierte 'YYYY-MM-DD' a (year, month)."""
    return int(s[:4]), int(s[5:7])

def parse_quarter(s):
    """Convierte 'YYYY-MM-DD' a (year, quarter)."""
    y, m = parse_date(s)
    return y, (m - 1) // 3 + 1

def trim(pairs_l_v, keep=24):
    """Mantiene los últimos N puntos."""
    labels, values = zip(*pairs_l_v) if pairs_l_v else ([], [])
    return list(labels[-keep:]), list(values[-keep:])

def series_lv(rows, key_fn, val_fn=None, keep=24, decimals=1):
    """Convierte lista (date_str, val) a (labels, values) con keep últimos."""
    out = []
    for date_str, val in rows:
        label = key_fn(date_str)
        value = round(val_fn(val) if val_fn else val, decimals)
        out.append((label, value))
    if not out:
        return [], []
    labels, values = zip(*out)
    return list(labels[-keep:]), list(values[-keep:])

ok_count = 0
fail_count = 0

def update(seed_path_keys, new_l, new_v, name):
    global ok_count, fail_count
    if not new_v:
        print(f"  ⚠  {name}: sin datos de API, se mantiene el valor anterior")
        fail_count += 1
        return
    # Navegar el dict anidado
    obj = D
    for k in seed_path_keys[:-1]:
        obj = obj[k]
    last_key = seed_path_keys[-1]
    existing = obj[last_key]
    if isinstance(existing, dict):
        obj[last_key] = {"l": new_l, "v": new_v}
    else:
        # flat list (cpiCore, cpiMoM, etc.)
        obj[last_key] = new_v
    print(f"  ✓  {name}: {len(new_v)} puntos, último={new_v[-1]} ({new_l[-1] if new_l else '?'})")
    ok_count += 1

# ─────────────────────────────────────────────────────────────
print("=" * 60)
print(f"update_seed_from_apis.py — {date.today()}")
print("=" * 60)

with open(SEED_PATH) as f:
    D = json.load(f)

# ══════════════════════════════════════════════════════════════
# 1. EE.UU. (FRED)
# ══════════════════════════════════════════════════════════════
print("\n[FRED] EE.UU. ...")

# GDP real QoQ SAAR
rows = fred("A191RL1Q225SBEA", units="lin", limit=12)
if rows:
    pairs = [(lbl_q(*parse_quarter(d)), round(v, 1)) for d, v in rows]
    l, v = trim(pairs, keep=8)
    update(["us", "gdp"], l, v, "GDP QoQ SAAR")

# CPI YoY y MoM
cpi_yoy = fred("CPIAUCSL", units="pc1", limit=30)
if cpi_yoy:
    pairs = [(lbl(*parse_date(d)), round(v, 2)) for d, v in cpi_yoy]
    l, v = trim(pairs, keep=24)
    update(["us", "cpi"], l, v, "CPI YoY")

cpi_mom = fred("CPIAUCSL", units="pch", limit=30)
if cpi_mom:
    _, v = trim([(lbl(*parse_date(d)), round(v, 2)) for d, v in cpi_mom], keep=24)
    update(["us", "cpiMoM"], [], v, "CPI MoM")

# Core CPI YoY
core_cpi = fred("CPILFESL", units="pc1", limit=30)
if core_cpi:
    _, v = trim([(lbl(*parse_date(d)), round(v, 2)) for d, v in core_cpi], keep=24)
    update(["us", "cpiCore"], [], v, "Core CPI YoY")

# PCE YoY y MoM
pce_yoy = fred("PCEPI", units="pc1", limit=30)
if pce_yoy:
    pairs = [(lbl(*parse_date(d)), round(v, 2)) for d, v in pce_yoy]
    l, v = trim(pairs, keep=24)
    update(["us", "pce"], l, v, "PCE YoY")

pce_mom = fred("PCEPI", units="pch", limit=30)
if pce_mom:
    _, v = trim([(lbl(*parse_date(d)), round(v, 2)) for d, v in pce_mom], keep=24)
    update(["us", "pceMoM"], [], v, "PCE MoM")

core_pce = fred("PCEPILFE", units="pc1", limit=30)
if core_pce:
    _, v = trim([(lbl(*parse_date(d)), round(v, 2)) for d, v in core_pce], keep=24)
    update(["us", "pceCore"], [], v, "Core PCE YoY")

# PPI Final Demand YoY y MoM
ppi_yoy = fred("PPIFIS", units="pc1", limit=30)
if ppi_yoy:
    pairs = [(lbl(*parse_date(d)), round(v, 2)) for d, v in ppi_yoy]
    l, v = trim(pairs, keep=24)
    update(["us", "ppi"], l, v, "PPI YoY")

ppi_mom = fred("PPIFIS", units="pch", limit=30)
if ppi_mom:
    _, v = trim([(lbl(*parse_date(d)), round(v, 2)) for d, v in ppi_mom], keep=24)
    update(["us", "ppiMoM"], [], v, "PPI MoM")

core_ppi = fred("WPSFD4131", units="pc1", limit=30)
if core_ppi:
    _, v = trim([(lbl(*parse_date(d)), round(v, 2)) for d, v in core_ppi], keep=24)
    update(["us", "ppiCore"], [], v, "Core PPI YoY")

# Desempleo
ur = fred("UNRATE", units="lin", limit=30)
if ur:
    pairs = [(lbl(*parse_date(d)), round(v, 1)) for d, v in ur]
    l, v = trim(pairs, keep=24)
    update(["us", "ur"], l, v, "Desempleo EEUU")

# NFP (cambio mensual en miles)
nfp = fred("PAYEMS", units="chg", limit=30)
if nfp:
    pairs = [(lbl(*parse_date(d)), int(v)) for d, v in nfp]
    l, v = trim(pairs, keep=24)
    update(["us", "nfp"], l, v, "NFP")

# Fed Funds (promedio mensual efectivo)
fed = fred("FEDFUNDS", units="lin", limit=30)
if fed:
    pairs = [(lbl(*parse_date(d)), round(v, 2)) for d, v in fed]
    l, v = trim(pairs, keep=24)
    update(["us", "fed"], l, v, "Fed Funds")

# Initial Claims (semanal → mensual promedio)
claims_w = fred("ICSA", units="lin", limit=104)
if claims_w:
    monthly = monthly_avg(claims_w)
    pairs = [(lbl(y, m), round(v / 1000, 0)) for (y, m), v in monthly.items()]
    l, v = trim(pairs, keep=24)
    v = [int(x) for x in v]
    update(["us", "claims"], l, v, "Initial Claims")

# Balanza comercial (millones USD → dividir por 1000 para consistencia con seed en ~USD bn)
trade = fred("BOPGSTB", units="lin", limit=24)
if trade:
    pairs = [(lbl(*parse_date(d)), round(v / 1000, 1)) for d, v in trade]
    l, v = trim(pairs, keep=18)
    update(["us", "trade"], l, v, "Trade Balance EEUU")

# ══════════════════════════════════════════════════════════════
# 2. BRASIL (BCB)
# ══════════════════════════════════════════════════════════════
print("\n[BCB] Brasil ...")
time.sleep(0.3)

# IPCA YoY
ipca_yoy = bcb("13522", start="01/01/2023")
if ipca_yoy:
    pairs = []
    for date_str, val in ipca_yoy:
        d_obj = datetime.strptime(date_str, "%d/%m/%Y")
        pairs.append((lbl(d_obj.year, d_obj.month), round(val, 2)))
    l, v = trim(pairs, keep=24)
    update(["br", "cpi"], l, v, "IPCA YoY Brasil")

# IPCA MoM
ipca_mom = bcb("433", start="01/01/2023")
if ipca_mom:
    pairs = []
    for date_str, val in ipca_mom:
        d_obj = datetime.strptime(date_str, "%d/%m/%Y")
        pairs.append((lbl(d_obj.year, d_obj.month), round(val, 2)))
    _, v = trim(pairs, keep=24)
    update(["br", "cpiMoM"], [], v, "IPCA MoM Brasil")

# SELIC
selic_rows = bcb("432", start="01/01/2024")
if selic_rows:
    monthly = {}
    for date_str, val in selic_rows:
        d_obj = datetime.strptime(date_str, "%d/%m/%Y")
        monthly[(d_obj.year, d_obj.month)] = round(val, 2)
    pairs = [(lbl(y, m), v) for (y, m), v in sorted(monthly.items())]
    l, v = trim(pairs, keep=24)
    update(["br", "selic"], l, v, "SELIC")

# Desempleo PNAD
ur_br = bcb("24369", start="01/01/2023")
if ur_br:
    pairs = []
    for date_str, val in ur_br:
        d_obj = datetime.strptime(date_str, "%d/%m/%Y")
        pairs.append((lbl(d_obj.year, d_obj.month), round(val, 1)))
    l, v = trim(pairs, keep=24)
    update(["br", "ur"], l, v, "Desempleo PNAD Brasil")

# PIB QoQ (BCB 22099 = PIB YoY; se mantiene como está)
# La serie 22099 es YoY, no QoQ — no la reemplazamos para no romper el dashboard

# Balanza Comercial Brasil
trade_br = bcb("22704", start="01/01/2023")
if trade_br:
    pairs = []
    for date_str, val in trade_br:
        d_obj = datetime.strptime(date_str, "%d/%m/%Y")
        pairs.append((lbl(d_obj.year, d_obj.month), int(val)))
    l, v = trim(pairs, keep=24)
    update(["br", "trade"], l, v, "Balanza Comercial Brasil")

# ══════════════════════════════════════════════════════════════
# 3. ARGENTINA
# ══════════════════════════════════════════════════════════════
print("\n[ARG] Argentina ...")
time.sleep(0.3)

# IPC General MoM (argentinadatos)
ipc_raw = argdata("finanzas/indices/inflacion")
if isinstance(ipc_raw, list) and ipc_raw:
    pairs = []
    yoy_acc = []
    for r in ipc_raw:
        d_obj = datetime.strptime(r["fecha"][:10], "%Y-%m-%d")
        pairs.append((lbl(d_obj.year, d_obj.month), round(r["valor"], 2)))
        yoy_acc.append(r["valor"] / 100 + 1)

    l, v = trim(pairs, keep=24)
    update(["arg", "ipc"], l, v, "IPC MoM ARG")

    # IPC YoY: acumular 12 meses
    if len(yoy_acc) >= 12:
        yoy_pairs = []
        for i in range(11, len(yoy_acc)):
            prod = 1.0
            for j in range(i - 11, i + 1):
                prod *= yoy_acc[j]
            yoy_pairs.append((pairs[i][0], round((prod - 1) * 100, 1)))
        l_yoy, v_yoy = trim(yoy_pairs, keep=24)
        update(["arg", "ipcYoY"], l_yoy, v_yoy, "IPC YoY ARG")

# EMAE YoY (datos.gob.ar — ya viene como fracción, * 100)
emae_yoy = datosgob("143.3_ICE_SERVIA_2004_A_25", limit=36)
if emae_yoy:
    l, v = trim([(d, round(val * 100, 1)) for d, val in emae_yoy], keep=24)
    update(["arg", "emae"], l, v, "EMAE YoY")

# EMAE nivel desest (para calcular MoM)
emae_lev = datosgob("143.3_NO_PR_2004_A_21", limit=40)
if len(emae_lev) >= 2:
    mom = mompct(emae_lev)
    l, v = trim([(d, val) for d, val in mom], keep=24)
    update(["arg", "emaeDesest"], l, v, "EMAE Desest MoM")

# IPI MoM -- DESHABILITADO 10/09/2026 a pedido de Pedro: esta serie (datos.gob.ar) daba valores
# que no coinciden con los oficiales de INDEC que se cargan a mano desde el PDF cada mes (ver
# memoria ipi_minero_update.md). No pisar D.arg.ipi -- se actualiza solo manualmente.
# ipi_lev = datosgob("453.1_SERIE_ORIGNAL_0_0_14_46", limit=40)
# if len(ipi_lev) >= 2:
#     mom = mompct(ipi_lev)
#     l, v = trim([(d, val) for d, val in mom], keep=24)
#     update(["arg", "ipi"], l, v, "IPI MoM")

# ISAC MoM -- DESHABILITADO 10/09/2026, mismo motivo que IPI (ver arriba).
# isac_lev = datosgob("33.2_ISAC_NIVELRAL_0_M_18_63", limit=40)
# if len(isac_lev) >= 2:
#     mom = mompct(isac_lev)
#     l, v = trim([(d, val) for d, val in mom], keep=24)
#     update(["arg", "isac"], l, v, "ISAC MoM")

# IPI Minero YoY -- DESHABILITADO 10/09/2026, mismo motivo que IPI (ver arriba).
# ipi_min_lev = datosgob("453.1_TOTAL_0_0_14_96", limit=48)
# if len(ipi_min_lev) >= 13:
#     yoy = []
#     for i in range(12, len(ipi_min_lev)):
#         d, val = ipi_min_lev[i]
#         _, prev = ipi_min_lev[i - 12]
#         if prev and prev != 0:
#             yoy.append((d, round((val / prev - 1) * 100, 1)))
#     if yoy:
#         l, v = trim(yoy, keep=24)
#         update(["arg", "ipiMinero"], l, v, "IPI Minero YoY")

# BCRA: Reservas, Base Monetaria, M2, Crédito Privado
# Variable 1: Reservas internacionales (millones USD)
res = bcra(1, start="2023-01-01")
if res:
    monthly = {}
    for date_str, val in res:
        y, m = int(date_str[:4]), int(date_str[5:7])
        monthly[(y, m)] = round(val, 0)
    pairs = [(lbl(y, m), int(v)) for (y, m), v in sorted(monthly.items())]
    l, v = trim(pairs, keep=36)
    update(["arg", "reservasLargo"], l, v, "Reservas Brutas BCRA")

# Variable 15: Base monetaria (millones ARS)
base = bcra(15, start="2023-01-01")
if base:
    monthly = {}
    for date_str, val in base:
        y, m = int(date_str[:4]), int(date_str[5:7])
        monthly[(y, m)] = round(val, 0)
    pairs = [(lbl(y, m), int(v)) for (y, m), v in sorted(monthly.items())]
    l, v = trim(pairs, keep=36)
    update(["arg", "baseMonLargo"], l, v, "Base Monetaria BCRA")

# Variable 25: M2 Privado YoY
m2 = bcra(25, start="2024-01-01")
if m2:
    monthly = {}
    for date_str, val in m2:
        y, m = int(date_str[:4]), int(date_str[5:7])
        monthly[(y, m)] = round(val, 1)
    pairs = [(lbl(y, m), v) for (y, m), v in sorted(monthly.items())]
    l, v = trim(pairs, keep=24)
    update(["arg", "m2"], l, v, "M2 Privado YoY")

# Variable 26: Crédito privado (préstamos en ARS, millones)
# Calculamos YoY desde el nivel
cred_lev = bcra(26, start="2023-01-01")
if len(cred_lev) >= 13:
    monthly = {}
    for date_str, val in cred_lev:
        y, m = int(date_str[:4]), int(date_str[5:7])
        monthly[(y, m)] = val
    sorted_months = sorted(monthly.items())
    if len(sorted_months) >= 13:
        yoy = []
        for i in range(12, len(sorted_months)):
            (y, m), val = sorted_months[i]
            _, prev = sorted_months[i - 12]
            if prev and prev != 0:
                yoy.append((lbl(y, m), round((val / prev - 1) * 100, 1)))
        if yoy:
            l, v = trim(yoy, keep=24)
            update(["arg", "credito"], l, v, "Crédito Privado YoY")

# ══════════════════════════════════════════════════════════════
# GUARDAR
# ══════════════════════════════════════════════════════════════
D["_meta"]["updated"] = str(date.today())
D["_meta"]["source"] = "Amberes Consultora — generado con update_seed_from_apis.py"

with open(SEED_PATH, "w", encoding="utf-8") as f:
    json.dump(D, f, ensure_ascii=False, indent=2)

size = SEED_PATH.stat().st_size / 1024
print(f"\n{'='*60}")
print(f"seed.json actualizado: {size:.1f} KB")
print(f"Series OK: {ok_count}   Sin datos: {fail_count}")
print(f"{'='*60}")

# ══════════════════════════════════════════════════════════════
# DEPLOY (opcional)
# ══════════════════════════════════════════════════════════════
if DEPLOY:
    print("\n[Vercel] Deployando ...")
    result = subprocess.run(
        ["npx", "vercel", "--prod", "--yes"],
        cwd=ROOT,
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print("✓ Deploy exitoso")
        for line in result.stdout.splitlines()[-3:]:
            print(" ", line)
    else:
        print("✗ Error en deploy:")
        print(result.stderr[-500:])
else:
    print("\nPróximo paso: python3 scripts/update_seed_from_apis.py --deploy")
    print("  o: npx vercel --prod --yes")
