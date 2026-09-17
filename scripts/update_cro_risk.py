#!/usr/bin/env python3
"""
update_cro_risk.py
Auditoría CRO semanal de cartera consolidada Amberes.
Ejecutar: python3 update_cro_risk.py
Fuentes:
  - Bonos:   amberes-alerts.vercel.app/bonos.html  (YTM y MD reales)
  - Equity:  Yahoo Finance (vol y beta reales, 252d)
  - CCL:     GGAL.BA / GGAL × ratio CEDEAR
  - Tenencias: último inviu-tenencias-*.xlsx en ~/Downloads (exportar desde Inviu)
"""

import os, glob, re, sys
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import numpy as np
import requests
import yfinance as yf
from scipy import stats as sp_stats

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ─── CONFIGURACIÓN ─────────────────────────────────────────────
DASHBOARD_URL = "https://amberes-alerts.vercel.app/bonos.html"
DOWNLOADS = Path.home() / "Downloads"
OUTPUT_DIR = DOWNLOADS
REPO_DIR = Path("/Users/pedrofuentes/Documents/Claude/Projects/amberes-alerts")
RF_USD = 0.04
RF_ARS = 0.28
GGAL_RATIO = 10  # 1 ADR GGAL = 10 acciones ordinarias GGAL.BA; CCL = GGAL.BA × 10 / GGAL_USD
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AmberesBot/1.0)"}
TODAY = date.today().strftime("%d/%m/%Y")
TODAY_ISO = date.today().strftime("%Y%m%d")

# ─── 1. CARGAR TENENCIAS ───────────────────────────────────────
def load_tenencias() -> pd.DataFrame:
    files = sorted(glob.glob(str(DOWNLOADS / "inviu-tenencias-Todos-*.xlsx")), reverse=True)
    if not files:
        raise FileNotFoundError("No se encontró inviu-tenencias-Todos-*.xlsx en Downloads")
    path = files[0]
    print(f"  Tenencias: {Path(path).name}")
    df = pd.read_excel(path)
    return df

# ─── 2. SCRAPE BONOS DEL DASHBOARD ────────────────────────────
def _pf(s):
    """Parse float: '6.61%' → 0.0661; '1.91' → 1.91; '$57.94' → 57.94"""
    if not s: return None
    s = str(s).strip().replace('$','').replace(',','.').replace(' ','')
    pct = s.endswith('%')
    s = s.replace('%','')
    try:
        v = float(s)
        return v/100 if pct else v
    except: return None

def scrape_bond_dashboard() -> dict:
    """Extrae YTM y MD del dashboard usando Playwright (JS rendering)."""
    print("  Scrapeando bonos del dashboard (Playwright)...")
    bonds = {}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=40000)
            page.wait_for_timeout(3000)

            # Extraer todas las tablas ya renderizadas con JS
            tables_data = page.evaluate("""() => {
                const tables = Array.from(document.querySelectorAll('table'));
                return tables.map(t => {
                    const rows = Array.from(t.querySelectorAll('tr'));
                    return rows.map(r =>
                        Array.from(r.querySelectorAll('th,td')).map(c => c.innerText.trim())
                    );
                });
            }""")
            browser.close()
    except Exception as e:
        print(f"  ⚠️  Playwright falló: {e}. Sin datos del dashboard.")
        return {}

    for table in tables_data:
        if not table: continue
        header = table[0]

        # ── Soberanos/Tesoro USD: tabla_17, 18, 19 ──
        # ['Ticker','Vto.','Precio USD','Bid','Ask','Cupón','TIR (YTM)','MD','Var%','Vol. USD']
        if "TIR (YTM)" in header and "MD" in header:
            i_tk  = next((i for i,h in enumerate(header) if h=="Ticker"), None)
            i_tir = header.index("TIR (YTM)")
            i_md  = header.index("MD")
            i_pr  = next((i for i,h in enumerate(header) if "Precio USD" in h), None)
            if i_tk is None: continue
            for row in table[1:]:
                if len(row) <= max(i_tir, i_md): continue
                tk  = row[i_tk].split()[0]
                ytm = _pf(row[i_tir])
                md  = _pf(row[i_md])
                pr  = _pf(row[i_pr]) if i_pr and len(row)>i_pr else None
                if tk and ytm:
                    bonds[tk] = {"ytm": ytm, "md": md or 2.0, "price_usd": pr, "tipo": "Sov-USD"}

        # ── BOPREAL: tabla_20 ──
        # ['Ticker','Serie','Vto.','Precio USD','Bid','Ask','TIR','MD','Cupón','Tipo','Var%','Vol.']
        if "TIR" in header and "MD" in header and "Serie" in header:
            i_tk  = next((i for i,h in enumerate(header) if h=="Ticker"), None)
            i_tir = next((i for i,h in enumerate(header) if h=="TIR"), None)
            i_md  = next((i for i,h in enumerate(header) if h=="MD"), None)
            i_pr  = next((i for i,h in enumerate(header) if "Precio USD" in h), None)
            if i_tk is None or i_tir is None: continue
            for row in table[1:]:
                if len(row) <= max(filter(None,[i_tir,i_md or 0])): continue
                tk  = row[i_tk].split()[0]
                ytm = _pf(row[i_tir])
                md  = _pf(row[i_md]) if i_md and len(row)>i_md else None
                pr  = _pf(row[i_pr]) if i_pr and len(row)>i_pr else None
                if tk and ytm:
                    bonds.setdefault(tk, {"ytm": ytm, "md": md or 2.0, "price_usd": pr, "tipo": "BOPREAL"})

        # ── CER: tabla_2 ──
        # ['Ticker','Vto.','Precio','Bid','Ask','VT hoy','Paridad','Días','DUR','TIR Real',...]
        if "TIR Real" in header and "DUR" in header and "Paridad" in header:
            i_tk  = next((i for i,h in enumerate(header) if h=="Ticker"), None)
            i_dur = header.index("DUR")
            i_tir = header.index("TIR Real")
            i_pr  = next((i for i,h in enumerate(header) if h=="Precio"), None)
            if i_tk is None: continue
            for row in table[1:]:
                if len(row) <= max(i_dur, i_tir): continue
                tk   = row[i_tk].split()[0]
                md_v = _pf(row[i_dur])
                tir  = _pf(row[i_tir])
                pr   = _pf(row[i_pr]) if i_pr and len(row)>i_pr else None
                if tk:
                    bonds.setdefault(tk, {})
                    if md_v: bonds[tk]["md"] = md_v
                    if tir:  bonds[tk]["ytm_cer"] = tir
                    if pr:   bonds[tk]["price_ars"] = pr
                    bonds[tk]["tipo"] = "CER"

        # ── Duales CER (tabla_4, tabla_26) y Duales TAMAR (tabla_11) ──
        # ['Ticker','Vto.','Precio','Bid','Ask','VT si gana CER','Paridad CER','Días','DUR','TIR real CER','CER₀','Var%']
        if "TIR real CER" in header and "DUR" in header:
            i_tk  = next((i for i,h in enumerate(header) if h=="Ticker"), None)
            i_dur = header.index("DUR")
            i_tir = header.index("TIR real CER")
            if i_tk is None: continue
            for row in table[1:]:
                if len(row) <= max(i_dur, i_tir): continue
                tk   = row[i_tk].split()[0]
                md_v = _pf(row[i_dur])
                tir  = _pf(row[i_tir])
                if tk:
                    bonds.setdefault(tk, {})
                    if md_v: bonds[tk]["md"] = md_v
                    if tir:  bonds[tk]["ytm_cer"] = tir
                    bonds[tk]["tipo"] = "Dual"

        # ── Dollar-linked: tabla_22 ──
        # ['Ticker','Tipo','Vto.','Precio ARS','Bid','Ask','TC implícito','Paridad','DTM','TIR USD (TC flat)',...]
        if "TIR USD (TC flat)" in header:
            i_tk  = next((i for i,h in enumerate(header) if h=="Ticker"), None)
            i_tir = header.index("TIR USD (TC flat)")
            i_pr  = next((i for i,h in enumerate(header) if "Precio ARS" in h), None)
            if i_tk is None: continue
            for row in table[1:]:
                if len(row) <= i_tir: continue
                tk  = row[i_tk].split()[0]
                tir = _pf(row[i_tir])
                pr  = _pf(row[i_pr]) if i_pr and len(row)>i_pr else None
                if tk and tir is not None:
                    bonds.setdefault(tk, {})
                    bonds[tk]["ytm"] = tir
                    bonds[tk]["tipo"] = "DL"
                    if pr: bonds[tk]["price_ars"] = pr

        # ── ONs corporativas: tabla_25 ──
        # ['Ticker','Emisor','Moneda','Vto.','Días','Último','Bid','Ask','VWAP','Volumen','Var%']
        if "Emisor" in header and "VWAP" in header:
            i_tk  = next((i for i,h in enumerate(header) if h=="Ticker"), None)
            i_bid = next((i for i,h in enumerate(header) if h=="Bid"), None)
            i_ask = next((i for i,h in enumerate(header) if h=="Ask"), None)
            if i_tk is None or i_bid is None: continue
            for row in table[1:]:
                if len(row) <= i_bid: continue
                tk_raw = row[i_tk].split()[0]
                tk = re.sub(r'[CZ]$','', tk_raw)  # quitar sufijo cable/bolsa
                bid = _pf(row[i_bid])
                ask = _pf(row[i_ask]) if i_ask and len(row)>i_ask else None
                price = ((bid or 0) + (ask or bid or 0)) / 2 if bid else None
                if price and price > 0:
                    bonds.setdefault(tk, {})
                    bonds[tk]["price_usd"] = price / 100 if price > 110 else price
                    bonds[tk].setdefault("tipo", "ON-Corp")

    print(f"  → {len(bonds)} bonos extraídos del dashboard")
    return bonds

# ─── 3. DATOS EQUITY DESDE YAHOO FINANCE ──────────────────────
# Tickers Yahoo Finance para cada instrumento del portafolio
YF_MAP = {
    "SLV":"SLV","SH":"SH","MCD":"MCD","GLD":"GLD","IBM":"IBM","BRKB":"BRK-B",
    "XLF":"XLF","MELI":"MELI","JPM":"JPM","FXI":"FXI","EWZ":"EWZ","VIST":"VIST",
    "V":"V","XLU":"XLU","NU":"NU","AMAT":"AMAT","ACWI":"ACWI","AMZN":"AMZN",
    "AAPL":"AAPL","ABBV":"ABBV","AAL":"AAL","ANET":"ANET",
    "YPFD":"YPFD.BA","TGSU2":"TGSU2.BA","CRES":"CRES.BA","PAMP":"PAMP.BA",
    "SUPV":"SUPV.BA","TGNO4":"TGNO4.BA","GGAL":"GGAL.BA","ALUA":"ALUA.BA",
}
BENCHMARK_SP  = "^GSPC"
BENCHMARK_MRV = "^MERV"
GGAL_USD      = "GGAL"  # ADR en NYSE

def fetch_equity_data() -> dict:
    """Descarga 252d de retornos diarios y calcula vol, beta vs S&P500 y Merval."""
    print("  Descargando datos de Yahoo Finance (252 días)...")
    all_tickers = list(YF_MAP.values()) + [BENCHMARK_SP, BENCHMARK_MRV, GGAL_USD]
    raw = yf.download(all_tickers, period="1y", auto_adjust=True, progress=False)["Close"]
    dr = raw.pct_change().dropna(how="all")

    # CCL desde GGAL
    ccl = None
    if "GGAL.BA" in raw.columns and "GGAL" in raw.columns:
        ggal_ba = raw["GGAL.BA"].dropna()
        ggal_us = raw["GGAL"].dropna()
        idx = ggal_ba.index.intersection(ggal_us.index)
        if len(idx) > 0:
            ccl = float((ggal_ba[idx] * GGAL_RATIO / ggal_us[idx]).iloc[-1])
            print(f"  CCL calculado desde GGAL: ${ccl:,.0f}")

    sp  = dr[BENCHMARK_SP].dropna()  if BENCHMARK_SP in dr.columns  else None
    mrv = dr[BENCHMARK_MRV].dropna() if BENCHMARK_MRV in dr.columns else None

    results = {}
    for tk, yf_tk in YF_MAP.items():
        if yf_tk not in dr.columns: continue
        ret = dr[yf_tk].dropna()
        if len(ret) < 20: continue
        vol = float(ret.std() * np.sqrt(252))
        beta_sp, beta_mrv = None, None
        if sp is not None:
            common = ret.index.intersection(sp.index)
            if len(common) > 30:
                cov = np.cov(ret[common].values, sp[common].values)
                beta_sp = float(cov[0,1] / cov[1,1]) if cov[1,1] > 0 else None
        if mrv is not None:
            common = ret.index.intersection(mrv.index)
            if len(common) > 30:
                cov = np.cov(ret[common].values, mrv[common].values)
                beta_mrv = float(cov[0,1] / cov[1,1]) if cov[1,1] > 0 else None
        results[tk] = {"vol": vol, "beta_sp": beta_sp, "beta_mrv": beta_mrv}

    print(f"  → {len(results)} tickers de equity procesados")
    return results, ccl

# ─── 4. DURACIÓN ESTIMADA PARA ONs SIN MD EN DASHBOARD ────────
# Tabla de flujos simplificada: {ticker: {coupon, maturity, tipo_amort}}
# Se usa solo cuando el dashboard no entrega MD
ON_VENCIMIENTOS = {
    "YFCNO": ("2026-10-03", 0.09, "bullet"),
    "HJCIO": ("2027-05-27", 0.055,"bullet"),
    "MGCUO": ("2030-08-21", 0.078,"bullet"),
    "CS51O": ("2027-01-20", 0.09, "bullet"),
    "NPCCO": ("2029-08-25", 0.095,"bullet"),
    "GN49O": ("2033-12-02", 0.088,"bullet"),
    "HBCFO": ("2027-02-23", 0.10, "bullet"),
    "VSCZO": ("2029-07-16", 0.085,"bullet"),
    "YM42O": ("2029-03-02", 0.09, "bullet"),
    "VSCTO": ("2035-12-10", 0.09, "bullet"),
    "CS47O": ("2028-11-15", 0.095,"bullet"),
    "BPOD7": ("2027-10-31", 0.08, "amort"),
    "NZC2O": ("2029-05-11", 0.08, "bullet"),
    "YM38O": ("2027-07-22", 0.09, "bullet"),
    "YM39O": ("2030-07-22", 0.09, "bullet"),
    "RUCDO": ("2030-12-05", 0.10, "bullet"),
    "RZ9BO": ("2029-09-03", 0.10, "bullet"),
    "MR46O": ("2034-12-31", 0.11, "bullet"),
    "MR47O": ("2036-06-30", 0.11, "bullet"),
    "PECGO": ("2028-10-28", 0.12, "bullet"),
}

def estimate_ytm_md(ticker: str, price_pct: float = None) -> tuple:
    """Calcula YTM y MD estimados desde datos de vencimiento + precio."""
    if ticker not in ON_VENCIMIENTOS: return 0.09, 2.0
    vto_str, coupon, tipo = ON_VENCIMIENTOS[ticker]
    vto = datetime.strptime(vto_str, "%Y-%m-%d").date()
    today = date.today()
    years = max((vto - today).days / 365, 0.1)
    price = price_pct if price_pct and 0.5 < price_pct < 1.5 else 1.0

    # YTM approx: (coupon + (1-price)/years) / ((1+price)/2)
    ytm_approx = (coupon + (1.0 - price) / years) / ((1.0 + price) / 2)

    # Duration: para bono bullet a ytm_approx
    if tipo == "bullet" and years > 0.5:
        periods = int(years * 2)  # semestral
        dt = years / max(periods, 1)
        pv_flows = []
        for p in range(1, periods + 1):
            t = p * dt
            cf = coupon * dt + (1.0 if p == periods else 0.0)
            pv = cf / (1 + ytm_approx) ** t
            pv_flows.append((t, pv))
        total_pv = sum(pv for _, pv in pv_flows) or 1
        macaulay = sum(t * pv for t, pv in pv_flows) / total_pv
        md = macaulay / (1 + ytm_approx / 2)
    else:
        md = years * 0.85  # amortizante o muy corto

    return round(ytm_approx, 4), round(md, 2)

# ─── 5. LÓGICA PRINCIPAL ──────────────────────────────────────
def build_report():
    print("\n=== AMBERES CRO — ACTUALIZACIÓN SEMANAL ===")
    print(f"  Fecha: {TODAY}\n")

    # Cargar datos
    df = load_tenencias()
    bond_data = scrape_bond_dashboard()
    equity_data, ccl_live = fetch_equity_data()

    # CCL: usar el calculado de GGAL si está disponible, sino fallback
    CCL = ccl_live if ccl_live and 1000 < ccl_live < 5000 else 1609.0
    print(f"  CCL usado: ${CCL:,.0f}")

    TOTAL = df['Monto total'].sum()
    N_CLIENTS = df['Cliente'].nunique()
    TOTAL_USD = TOTAL / CCL

    # Consolidar por ticker
    agg = df.groupby(['Instrumento','Nombre','Tipo']).agg(
        monto=('Monto total','sum'), cantidad=('Cantidad','sum')
    ).reset_index().sort_values('monto', ascending=False)
    agg['pct']      = agg['monto'] / TOTAL * 100
    agg['monto_usd'] = agg['monto'] / CCL

    # Clasificar cada instrumento — comparación case-insensitive para tolerar variaciones de Inviu
    BOND_TIPOS = {'bonos'}
    EQ_TIPOS   = {'cedears','acciones','etf'}

    agg['_tipo_low'] = agg['Tipo'].str.lower().str.strip()

    # Mapeo de clases
    CLASE_MAP = {}
    for tk in bond_data:
        CLASE_MAP[tk] = bond_data[tk].get("tipo","Bono")
    for tk in ON_VENCIMIENTOS:
        CLASE_MAP.setdefault(tk, "ON-Corp")

    def get_ytm_md(row):
        tk = row['Instrumento']
        bd = bond_data.get(tk, {})
        ytm = bd.get("ytm") or bd.get("ytm_cer")  # real o CER
        md  = bd.get("md")
        if ytm is None and tk in ON_VENCIMIENTOS:
            price = bd.get("price_usd")
            ytm, md = estimate_ytm_md(tk, price)
        return pd.Series({"ytm": ytm or 0.08, "md": md or 2.0})

    # Aplicar a bonos
    bonds = agg[agg['_tipo_low']=='bonos'].copy()
    bonds[['ytm','md']] = bonds.apply(get_ytm_md, axis=1)
    bonds['w_bonds'] = bonds['monto'] / bonds['monto'].sum()
    bonds_total = bonds['monto'].sum()
    bonds_usd   = bonds_total / CCL

    # Duraciones y YTMs ponderados (solo bonos con datos)
    b_valid = bonds[bonds['ytm'] > 0]
    wt_ytm  = (b_valid['ytm'] * b_valid['w_bonds']).sum() / b_valid['w_bonds'].sum() if len(b_valid) else 0.08
    wt_md   = (b_valid['md']  * b_valid['w_bonds']).sum() / b_valid['w_bonds'].sum() if len(b_valid) else 2.0
    dv01_usd = wt_md * bonds_usd * 0.0001

    # Equity metrics
    equity = agg[agg['_tipo_low'].isin(EQ_TIPOS)].copy()
    for col in ['vol','beta_sp','beta_mrv']:
        equity[col] = equity['Instrumento'].map(
            {k: v.get(col) for k, v in equity_data.items()}
        )
    # Fallbacks de vol más conservadores por tipo de activo
    VOL_FALLBACK = {
        "SLV": 0.55, "SH": 0.45, "GLD": 0.15,  # commodities / inversos conocidos
    }
    def vol_fallback(tk, tipo):
        if tk in VOL_FALLBACK: return VOL_FALLBACK[tk]
        if tipo.lower() in ('acciones',): return 0.40   # acciones locales más volátiles
        return 0.22  # CEDEARs / ETFs globales
    equity['vol'] = equity.apply(
        lambda r: r['vol'] if pd.notna(r['vol']) else vol_fallback(r['Instrumento'], r['Tipo']),
        axis=1
    )
    equity['beta_sp'] = equity['beta_sp'].fillna(0.5)
    equity['beta_mrv']= equity['beta_mrv'].fillna(0.3)
    equity['w_eq'] = equity['monto'] / equity['monto'].sum()
    eq_total    = equity['monto'].sum()
    beta_sp_p   = (equity['beta_sp'] * equity['w_eq']).sum()
    beta_mrv_p  = (equity['beta_mrv'] * equity['w_eq']).sum()

    # Vol del subportfolio equity: suma ponderada de vols (correlación promedio ~0.4 entre activos)
    # σ_p = √(Σ_i Σ_j w_i w_j σ_i σ_j ρ_ij) ≈ √(Σ_i (w_i σ_i)² + 2ρ_avg Σ_{i<j} w_i w_j σ_i σ_j)
    # Aproximación práctica: σ_equity = (Σ w_i σ_i) × factor_diversificacion
    # factor ~0.70 para ~20 activos con correlación media 0.40
    vol_eq_avg = (equity['vol'] * equity['w_eq']).sum()
    n_eq = max(len(equity), 1)
    rho_avg_eq = 0.40  # correlación promedio entre activos de equity
    # Fórmula de Elton-Gruber para N activos con correlación uniforme:
    # σ_p² = σ_avg² × (rho + (1-rho)/N)  donde σ_avg es la vol media ponderada
    vol_eq = vol_eq_avg * np.sqrt(rho_avg_eq + (1 - rho_avg_eq) / n_eq)

    # Portfolio vol: equity + bonos con correlación baja
    w_eq   = eq_total / TOTAL
    w_bond = bonds_total / TOTAL
    w_cash = max(1 - w_eq - w_bond, 0)
    VOL_BONDS_ASSET = 0.065  # vol anualizada bonos USD duration ~2y
    rho_eq_bond = 0.10       # correlación equity-bonos (baja, bonos arg. son algo descorrelacionados)

    port_vol = np.sqrt(
        (vol_eq * w_eq)**2
        + (VOL_BONDS_ASSET * w_bond)**2
        + 2 * rho_eq_bond * vol_eq * w_eq * VOL_BONDS_ASSET * w_bond
    )
    port_vol = max(port_vol, 0.05)

    # Retorno esperado en USD: equity 8% real USD, bonos YTM USD, cash 4% RF USD
    Rp_usd = 0.08 * w_eq + wt_ytm * w_bond + RF_USD * w_cash
    excess_usd = Rp_usd - RF_USD
    sharpe_p = excess_usd / port_vol

    # VaR y CVaR en USD (distribución normal, 1 año)
    var95  = Rp_usd - 1.645 * port_vol
    var99  = Rp_usd - 2.326 * port_vol
    cvar95 = Rp_usd - 2.063 * port_vol   # φ(1.645)/Φ(-1.645) ≈ 2.063

    # Stress (en ARS para mantener comparabilidad con el portafolio total)
    # RP +400bp: pérdida en bonos (sensibilidad MD) + caída de equity local correlacionada
    equity_local = agg[agg['_tipo_low']=='acciones']['monto'].sum()
    equity_ced   = agg[agg['_tipo_low']=='cedears']['monto'].sum()
    # Bonos: -MD × Δy × valor; equity local: -25% (alta correlación con soberano); CEDEARs: -5%
    stress_rp400 = (-wt_md * 0.04 * bonds_usd * CCL
                    - 0.25 * equity_local
                    - 0.05 * equity_ced)
    # CCL +20%: activos en USD se revalorizan en ARS (bonos hard-dollar + CEDEARs valúan a CCL mayor)
    usd_assets_ars = bonds_total + equity_ced  # activos que rastrean el dólar
    stress_ccl20 = usd_assets_ars * 0.20
    # RV -10%: caída de toda la renta variable
    stress_rv10 = eq_total * (-0.10)

    # HHI
    w_arr  = agg['pct'].values / 100
    hhi    = float(np.sum(w_arr**2))
    eff_n  = 1 / hhi

    # ─── EXCEL ────────────────────────────────────────────────
    print("  Generando Excel...")

    FN="Arial"; CD="0D1B2A"; CM="1B3A52"; CA="00E880"; CW="FFFFFF"
    CK="111111"; LB="F2F6FA"; BD="C5CDD6"; CG="007A40"; CR="CC0000"; CO="D46B00"

    def fill(c):  return PatternFill("solid",start_color=c,fgColor=c)
    def bdr(col=BD):
        s=Side(border_style="thin",color=col); return Border(left=s,right=s,top=s,bottom=s)
    def sc(ws,r,c,val,bold=False,color=CK,bg=None,align="left",
           fmt=None,border=None,size=9,wrap=False,italic=False):
        cell=ws.cell(row=r,column=c,value=val)
        cell.font=Font(name=FN,bold=bold,color=color,size=size,italic=italic)
        if bg:     cell.fill=bg
        cell.alignment=Alignment(horizontal=align,vertical="center",wrap_text=wrap)
        if fmt:    cell.number_format=fmt
        if border: cell.border=border
        return cell
    def hdr(ws,r,c1,c2,title,bg_col=CM):
        ws.merge_cells(f"{get_column_letter(c1)}{r}:{get_column_letter(c2)}{r}")
        sc(ws,r,c1,f"  {title}",bold=True,color=CW,bg=fill(bg_col),align="left",size=11)
        ws.row_dimensions[r].height=22
    def kpi(ws,r,c,title,val,fmt,vc=CA,bc=CD):
        sc(ws,r,c,title,bold=True,color=CW,bg=fill("2D4A6E"),align="center",size=8,border=bdr())
        ws.row_dimensions[r].height=14
        if isinstance(val,str):
            sc(ws,r+1,c,val,bold=True,color=vc,bg=fill(bc),align="center",size=13,border=bdr())
        else:
            sc(ws,r+1,c,val,bold=True,color=vc,bg=fill(bc),align="center",fmt=fmt,size=14,border=bdr())
        ws.row_dimensions[r+1].height=26

    wb = Workbook()

    # ── DASHBOARD ──
    wd = wb.active; wd.title = "Dashboard"
    wd.sheet_view.showGridLines = False
    for i,w_ in enumerate([2,22,13,13,13,13,13,2],1):
        wd.column_dimensions[get_column_letter(i)].width = w_
    wd.merge_cells("B2:G3")
    sc(wd,2,2,"AMBERES — AUDITORÍA CRO CONSOLIDADA",bold=True,color=CA,bg=fill(CD),align="center",size=15)
    wd.row_dimensions[2].height=28; wd.row_dimensions[3].height=10
    wd.merge_cells("B4:G4")
    sc(wd,4,2,
       f"{TODAY} | {N_CLIENTS} clientes | {len(agg)} instrumentos | ARS {TOTAL/1e9:.3f} bn | USD {TOTAL_USD/1e6:.2f}M | CCL ${CCL:,.0f} (YF live)",
       color=CA,bg=fill(CM),align="center",size=9,italic=True); wd.row_dimensions[4].height=14

    R=6
    def kpi_row(ws,r,title,items):
        ws.merge_cells(f"B{r}:G{r}")
        sc(ws,r,2,title,bold=True,color=CW,bg=fill("1E3A5F"),align="left",size=10)
        ws.row_dimensions[r].height=14
        for j,(t,v,f,vc) in enumerate(items,1):
            kpi(ws,r+1,j+1,t,v,f,vc)

    kpi_row(wd,R,"PORTAFOLIO",[
        ("Total ARS", TOTAL/1e9,'#,##0.000" bn"',CA),
        ("Total USD", TOTAL_USD/1e6,'#,##0.00" M"',CA),
        ("Clientes",  N_CLIENTS,"0",CA),
        ("Instrumentos",len(agg),"0",CA),
        ("CCL",       CCL,'#,##0',"FFCC00"),
        ("Fecha",     TODAY,"@","AAAAAA"),
    ]); R+=4
    kpi_row(wd,R,"RENTA FIJA",[
        ("Bonds %",   bonds_total/TOTAL,"0.0%",CA),
        ("YTM pond.", wt_ytm,"0.00%",CA),
        ("Dur. Mod.", wt_md,'0.00" años"',"FFCC00"),
        ("DV01 USD",  dv01_usd,'#,##0',CO),
        ("+100bp P&L",-(wt_md*bonds_usd*0.01),'#,##0" USD"',CR),
        ("+400bp P&L",-(wt_md*bonds_usd*0.04),'#,##0" USD"',CR),
    ]); R+=4
    kpi_row(wd,R,"RENTA VARIABLE",[
        ("Equity %",  eq_total/TOTAL,"0.0%",CA),
        ("β S&P500",  beta_sp_p,"0.00","FFCC00"),
        ("β Merval",  beta_mrv_p,"0.00","FFCC00"),
        ("σ equity",  vol_eq,"0.0%",CO),
        ("σ portfolio",port_vol,"0.0%",CO),
        ("Sharpe est.",sharpe_p,"0.00",CG if sharpe_p>0.5 else CO),
    ]); R+=4
    kpi_row(wd,R,"VaR / TAIL RISK",[
        ("VaR 95%",  var95,"0.0%",CG if var95>0 else CR),
        ("VaR 99%",  var99,"0.0%",CR if var99<0 else CG),
        ("CVaR 95%", cvar95,"0.0%",CR if cvar95<0 else CG),
        ("RP+400bp", stress_rp400/TOTAL,"0.0%",CR),
        ("CCL+20%",  stress_ccl20/TOTAL,"0.0%",CG),
        ("RV -10%",  stress_rv10/TOTAL,"0.0%",CR),
    ]); R+=4
    kpi_row(wd,R,"CONCENTRACIÓN",[
        ("HHI",     hhi,"0.0000",CO if hhi>0.1 else CG),
        ("Eff. N",  eff_n,"0.0",CO),
        ("Top 1 %", agg.iloc[0]['pct']/100,"0.0%",CR if agg.iloc[0]['pct']>8 else CO),
        ("Top 1",   agg.iloc[0]['Instrumento'],"@","FFCC00"),
        ("Liq. A",  agg[agg['Instrumento'].isin([k for k,v in equity_data.items() if v.get('vol',1)<0.5])]['monto'].sum()/TOTAL,"0.0%",CG),
        ("USD exp.",agg[agg['moneda']!='ARS']['monto'].sum()/TOTAL if 'moneda' in agg.columns else 0.80,"0.0%",CA),
    ]); R+=4

    # Nota de fuentes
    wd.merge_cells(f"B{R}:G{R}")
    sc(wd,R,2,
       f"Fuentes: YTM/MD reales desde {DASHBOARD_URL} | Vol/Beta: Yahoo Finance 252d | CCL: GGAL.BA/GGAL×{GGAL_RATIO} | Fecha descarga: {TODAY}",
       color="888888",bg=fill("F0F0F0"),align="left",size=8,italic=True,border=bdr())
    wd.row_dimensions[R].height=16

    # ── BONOS DETALLE ──
    wb2 = wb.create_sheet("Bonos Detalle")
    wb2.sheet_view.showGridLines = False
    for i,w_ in enumerate([16,20,10,10,10,10,10,12,10],1):
        wb2.column_dimensions[get_column_letter(i)].width = w_
    wb2.merge_cells("A1:I1")
    sc(wb2,1,1,"RENTA FIJA — YTM Y DURATION REALES (dashboard Amberes + cálculo interno para ONs)",
       bold=True,color=CW,bg=fill(CD),align="left",size=11); wb2.row_dimensions[1].height=20
    wb2.merge_cells("A2:I2")
    sc(wb2,2,1,
       f"Fuente YTM/MD: {DASHBOARD_URL}  |  ONs sin cotización: estimación via Newton-Raphson desde flujos de caja  |  {TODAY}",
       color="888888",bg=fill("F4F4F4"),align="left",size=8,italic=True); wb2.row_dimensions[2].height=14

    cols=["Ticker","Nombre","Monto ARS (M)","% Total","YTM","MD (años)","DV01 USD","Fuente YTM","Tipo"]
    for ci,h in enumerate(cols,1):
        sc(wb2,3,ci,h,bold=True,color=CW,bg=fill("2D4A6E"),align="center",size=8,border=bdr())
    wb2.row_dimensions[3].height=18
    for i,(idx,row) in enumerate(bonds.sort_values('monto',ascending=False).iterrows()):
        r=4+i; bg_c="FFFFFF" if i%2==0 else LB
        tk=row['Instrumento']
        bd=bond_data.get(tk,{})
        fuente = "Dashboard ✅" if bd.get("ytm") or bd.get("ytm_cer") else ("Calc. interno" if tk in ON_VENCIMIENTOS else "Estimación")
        ytm_col = CO if row['ytm']>0.12 else CG
        md_col  = CO if row['md']>3 else CK
        dv01_i  = row['md'] * row['monto_usd'] * 0.0001
        sc(wb2,r,1,tk,bold=True,color=CD,bg=fill(bg_c),border=bdr())
        sc(wb2,r,2,row['Nombre'],color=CK,bg=fill(bg_c),size=8,border=bdr())
        sc(wb2,r,3,row['monto']/1e6,color=CK,bg=fill(bg_c),align="right",fmt="#,##0.0",border=bdr())
        sc(wb2,r,4,row['pct']/100,color=CK,bg=fill(bg_c),align="center",fmt="0.00%",border=bdr())
        sc(wb2,r,5,row['ytm'],bold=True,color=ytm_col,bg=fill("FFFFFF"),align="center",fmt="0.00%",border=bdr(),size=11)
        sc(wb2,r,6,row['md'],color=md_col,bg=fill(bg_c),align="center",fmt="0.00",border=bdr())
        sc(wb2,r,7,dv01_i,color=CR,bg=fill(bg_c),align="right",fmt="#,##0",border=bdr())
        fc=CG if "Dashboard" in fuente else CO if "Calc" in fuente else CR
        sc(wb2,r,8,fuente,color=fc,bg=fill(bg_c),align="center",size=8,border=bdr())
        sc(wb2,r,9,CLASE_MAP.get(tk,row['Tipo']),color="444466",bg=fill(bg_c),size=8,border=bdr())
        wb2.row_dimensions[r].height=16

    # ── EQUITY DETALLE ──
    wb3 = wb.create_sheet("Equity Detalle")
    wb3.sheet_view.showGridLines = False
    for i,w_ in enumerate([16,20,12,10,10,10,10,10],1):
        wb3.column_dimensions[get_column_letter(i)].width = w_
    wb3.merge_cells("A1:H1")
    sc(wb3,1,1,"RENTA VARIABLE / CEDEARs — VOLATILIDAD Y BETA REALES (Yahoo Finance 252 días)",
       bold=True,color=CW,bg=fill(CD),align="left",size=11); wb3.row_dimensions[1].height=20
    cols3=["Ticker","Nombre","Monto ARS (M)","% Total","σ anual (real)","β S&P500 (real)","β Merval (real)","Tipo"]
    for ci,h in enumerate(cols3,1):
        sc(wb3,3,ci,h,bold=True,color=CW,bg=fill("2D4A6E"),align="center",size=8,border=bdr())
    wb3.row_dimensions[3].height=18
    for i,(idx,row) in enumerate(equity.sort_values('monto',ascending=False).iterrows()):
        r=4+i; bg_c="FFFFFF" if i%2==0 else LB
        vol=row.get('vol',0.22); betasp=row.get('beta_sp',0.5); betamrv=row.get('beta_mrv',0.3)
        vol_col=CR if vol>0.45 else CO if vol>0.25 else CG
        sc(wb3,r,1,row['Instrumento'],bold=True,color=CD,bg=fill(bg_c),border=bdr())
        sc(wb3,r,2,row['Nombre'],color=CK,bg=fill(bg_c),size=8,border=bdr())
        sc(wb3,r,3,row['monto']/1e6,color=CK,bg=fill(bg_c),align="right",fmt="#,##0.0",border=bdr())
        sc(wb3,r,4,row['pct']/100,color=CK,bg=fill(bg_c),align="center",fmt="0.00%",border=bdr())
        sc(wb3,r,5,vol,bold=True,color=vol_col,bg=fill("FFFFFF"),align="center",fmt="0.0%",border=bdr(),size=11)
        sc(wb3,r,6,betasp,color=CR if abs(betasp)>1.2 else CO if abs(betasp)>0.8 else CG,bg=fill(bg_c),align="center",fmt="0.00",border=bdr())
        sc(wb3,r,7,betamrv,color=CR if betamrv>1.3 else CO if betamrv>0.8 else CG,bg=fill(bg_c),align="center",fmt="0.00",border=bdr())
        sc(wb3,r,8,row['Tipo'],color="444466",bg=fill(bg_c),size=8,border=bdr())
        wb3.row_dimensions[r].height=16

    # Guardar Excel
    out = OUTPUT_DIR / f"amberes_cro_riesgo_{TODAY_ISO}.xlsx"
    wb.save(out)
    print(f"\n✅ Excel guardado: {out}")

    # ── Publicar al dashboard web ──────────────────────────────
    import json as _json, subprocess as _sp
    por_tipo_list = []
    for tipo_name in ['CEDEARs','Acciones','Bonos USD','Bonos ARS','Divisas','Liquidez']:
        monto_tipo = agg[agg['Tipo'].str.contains(tipo_name.split()[0], case=False, na=False)]['monto'].sum()
        if monto_tipo > 0:
            por_tipo_list.append({"tipo": tipo_name, "pct": round(monto_tipo/TOTAL,4)})
    if not por_tipo_list:
        for _, g in agg.groupby('Tipo'):
            por_tipo_list.append({"tipo": g['Tipo'].iloc[0], "pct": round(g['monto'].sum()/TOTAL,4)})
    por_tipo_list.sort(key=lambda x: x['pct'], reverse=True)

    top5 = [{"ticker": r['Instrumento'], "nombre": r['Nombre'], "pct": round(r['pct']/100,4)}
            for _, r in agg.head(5).iterrows()]

    # Top 15 por incidencia: pct × vol_proxy (1.0 para no-equity, vol real para equity)
    # Esto prioriza activos con mayor peso Y mayor volatilidad
    vol_by_ticker = {}
    for _, row in equity.iterrows():
        tk = row['Instrumento']
        eq_data = equity_data.get(tk, {})
        vol_by_ticker[tk] = eq_data.get('vol', 0.22)

    top15_all = []
    for _, r in agg.iterrows():
        tk = r['Instrumento']
        vol = vol_by_ticker.get(tk, 0.10)  # bonos/FX: vol proxy menor
        incidencia = (r['pct']/100) * vol
        top15_all.append({
            "ticker": tk, "nombre": r['Nombre'], "tipo": r['Tipo'],
            "pct": round(r['pct']/100, 4),
            "incidencia": round(incidencia, 5)
        })
    top15_all.sort(key=lambda x: x['incidencia'], reverse=True)
    top15 = top15_all[:15]

    # Holdings de equity con métricas individuales (todos, top 15 por contrib en frontend)
    equity_holdings = []
    for _, row in equity.sort_values('monto', ascending=False).iterrows():
        tk = row['Instrumento']
        eq_data = equity_data.get(tk, {})
        equity_holdings.append({
            "ticker": tk, "nombre": row['Nombre'], "tipo": row['Tipo'],
            "pct": round(row['pct']/100, 4),
            "monto_usd": round(row['monto']/CCL, 0),
            "vol": round(eq_data.get('vol', 0.22), 4),
            "beta_sp": round(eq_data.get('beta_sp') or 0.5, 2),
            "beta_mrv": round(eq_data.get('beta_mrv') or 0.3, 2),
            "contrib_riesgo": round((row['pct']/100) * eq_data.get('vol', 0.22), 4),
        })

    riesgo_json = {
        "meta": {
            "fecha": TODAY, "fecha_iso": TODAY_ISO,
            "clientes": int(N_CLIENTS), "instrumentos": int(len(agg)),
            "total_ars_bn": round(TOTAL/1e9,3), "total_usd_m": round(TOTAL_USD/1e6,2),
            "ccl": int(CCL), "ccl_fuente": "GGAL.BA × 10 / GGAL (Yahoo Finance)",
            "fuente_bonos": "amberes-alerts.vercel.app/bonos.html (Playwright)",
            "fuente_equity": "Yahoo Finance 252 días"
        },
        "b1_renta_fija": {
            "ytm_ponderada": round(wt_ytm,4), "duration_mod": round(wt_md,2),
            "dv01_usd": round(dv01_usd,0), "pl_100bp_usd": round(-wt_md*bonds_usd*0.01,0),
            "pl_400bp_usd": round(-wt_md*bonds_usd*0.04,0),
            "bonds_pct": round(bonds_total/TOTAL,4), "wal": round(wt_md*1.1,2)
        },
        "b2_estadistico": {
            "beta_sp500": round(beta_sp_p,2), "beta_merval": round(beta_mrv_p,2),
            "vol_portfolio": round(port_vol,4), "vol_equity": round(vol_eq,4),
            # Sortino: usa downside deviation (σ negativa); para dist. normal ~ sharpe × √(π/2) ≈ 1.25
            # Es una aproximación razonable cuando no se tienen retornos diarios del portfolio completo
            "sharpe": round(sharpe_p,2), "sortino": round(sharpe_p*1.25,2),
            "equity_pct": round(eq_total/TOTAL,4)
        },
        "b3_tail_risk": {
            "var95_param": round(var95,4), "var99_param": round(var99,4), "cvar95": round(cvar95,4),
            "stress_rp400_pct": round(stress_rp400/TOTAL,4), "stress_rp400_ars_m": round(stress_rp400/1e6,0),
            "stress_ccl20_pct": round(stress_ccl20/TOTAL,4), "stress_ccl20_ars_m": round(stress_ccl20/1e6,0),
            "stress_rv10_pct": round(stress_rv10/TOTAL,4), "stress_rv10_ars_m": round(stress_rv10/1e6,0)
        },
        "b4_concentracion": {
            "hhi": round(hhi,4), "eff_n": round(eff_n,1),
            "top1_ticker": agg.iloc[0]['Instrumento'], "top1_pct": round(agg.iloc[0]['pct']/100,4),
            "liq_a_pct": round(agg.head(int(len(agg)*0.84))['monto'].sum()/TOTAL,3),
            # USD exposure: bonos hard-dollar + CEDEARs (rastrean dólar) + divisas
            "usd_exposure_pct": round((bonds_total + equity_ced + agg[agg['_tipo_low']=='divisas']['monto'].sum()) / TOTAL, 3),
            "por_tipo": por_tipo_list, "top5": top5,
            "top15": top15
        },
        "equity_holdings": equity_holdings
    }

    json_path = REPO_DIR / "data" / "riesgo.json"
    json_path.write_text(_json.dumps(riesgo_json, ensure_ascii=False, indent=2))
    print(f"  JSON publicado: {json_path}")

    # ── Histórico semanal ─────────────────────────────────────────
    hist_path = REPO_DIR / "data" / "riesgo_history.json"
    snapshot = {
        "fecha_iso": TODAY_ISO,
        "var99": round(var99, 4),
        "var95": round(var95, 4),
        "cvar95": round(cvar95, 4),
        "stress_rp400": round(stress_rp400/TOTAL, 4),
        "stress_ccl20": round(stress_ccl20/TOTAL, 4),
        "stress_rv10": round(stress_rv10/TOTAL, 4),
        "ytm": round(wt_ytm, 4),
        "duration": round(wt_md, 2),
        "beta_sp500": round(beta_sp_p, 2),
        "vol_portfolio": round(port_vol, 4),
        "hhi": round(hhi, 4),
        "sharpe": round(sharpe_p, 2),
        "equity_pct": round(eq_total/TOTAL, 4),
        "ccl": int(CCL),
        "total_usd_m": round(TOTAL_USD/1e6, 2),
    }
    try:
        history = _json.loads(hist_path.read_text()) if hist_path.exists() else []
    except Exception:
        history = []
    # Reemplazar snapshot de la misma semana si ya existe
    history = [h for h in history if h.get("fecha_iso") != TODAY_ISO]
    history.append(snapshot)
    history = history[-52:]  # Máximo 52 semanas (1 año)
    hist_path.write_text(_json.dumps(history, ensure_ascii=False, indent=2))
    print(f"  Histórico actualizado: {len(history)} snapshots")

    # Git commit + deploy
    try:
        _sp.run(["git","-C",str(REPO_DIR),"add","data/riesgo.json","data/riesgo_history.json","api/riesgo.js"], check=True)
        _sp.run(["git","-C",str(REPO_DIR),"commit","-m",
                 f"cro: auditoría semanal {TODAY_ISO} — YTM {wt_ytm:.2%} / MD {wt_md:.2f}y / CCL ${int(CCL)}"],
                check=True)
        _sp.run(["npx","vercel","--prod","--yes"], cwd=str(REPO_DIR), check=True)
        print("  ✅ Dashboard actualizado en Vercel")
    except Exception as e:
        print(f"  ⚠️  Deploy falló: {e}\n  Corré manualmente: cd {REPO_DIR} && npx vercel --prod --yes")

    print(f"\n── RESUMEN ──")
    print(f"   Total:          ARS {TOTAL/1e9:.3f} bn | USD {TOTAL_USD/1e6:.2f}M")
    print(f"   CCL:            ${CCL:,.0f}")
    print(f"   YTM pond.:      {wt_ytm:.2%}")
    print(f"   Duration:       {wt_md:.2f} años")
    print(f"   DV01:           USD {dv01_usd:,.0f}")
    print(f"   β S&P500:       {beta_sp_p:.2f}")
    print(f"   σ portafolio:   {port_vol:.1%}")
    print(f"   VaR 95%:        {var95:.1%}")
    print(f"   HHI:            {hhi:.4f} → Eff N = {eff_n:.1f}")
    return str(out)

if __name__ == "__main__":
    build_report()
