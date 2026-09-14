#!/usr/bin/env python3
"""
xlsx_to_json.py — Convierte amberes_data.xlsx → data/seed.json

Uso:
  python3 scripts/xlsx_to_json.py

El script lee el Excel, extrae las series de cada hoja y regenera
data/seed.json que usan los dashboards en producción.

Después de correrlo: npx vercel --prod --yes
"""
import json, os, sys
from pathlib import Path

try:
    from openpyxl import load_workbook
except ImportError:
    print("Error: openpyxl no instalado. Corré: pip3 install openpyxl")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
XLSX = Path("/Users/pedrofuentes/Library/CloudStorage/OneDrive-Personal/Documentos/amberes_data.xlsx")
OUT  = ROOT / "data" / "seed.json"

if not XLSX.exists():
    print(f"Error: no encontré {XLSX}")
    sys.exit(1)

wb = load_workbook(XLSX, data_only=True)

def get_sheet(name):
    if name not in wb.sheetnames:
        print(f"  ⚠ Hoja '{name}' no encontrada")
        return None
    return wb[name]

def parse_series(ws):
    """
    Lee bloques del formato:
      Fila N:   [LABEL]  (texto en col A)
      Fila N+1: [Período, p1, p2, p3, ...]
      Fila N+2: [Valor,   v1, v2, v3, ...]
      Fila N+3: vacía

    Devuelve dict: { label_text: {"l": [...], "v": [...]} }
    """
    results = {}
    r = 3  # start row (1-indexed), skip title row (1) and freeze row (2)
    max_r = ws.max_row
    while r <= max_r:
        label_cell = ws.cell(r, 1).value
        if label_cell and isinstance(label_cell, str) and label_cell.strip():
            # Fila de períodos
            periods = []
            c = 2
            while ws.cell(r+1, c).value is not None:
                periods.append(str(ws.cell(r+1, c).value))
                c += 1
            # Fila de valores
            values = []
            for i in range(len(periods)):
                v = ws.cell(r+2, i+2).value
                values.append(float(v) if v is not None else None)
            if periods and values:
                results[label_cell.strip()] = {"l": periods, "v": values}
            r += 4
        else:
            r += 1
    return results

def sv(series, key):
    """Extrae solo .v de una serie"""
    return series.get(key, {}).get("v", [])

def sl(series, key):
    """Extrae solo .l de una serie"""
    return series.get(key, {}).get("l", [])

print(f"Leyendo {XLSX.name}...")

# ── US ──────────────────────────────────────────────────
print("  US...")
ws_us = get_sheet("US")
s = parse_series(ws_us) if ws_us else {}

US_GDP_L = sl(s, "GDP — Crecimiento Trimestral SAAR (%)") or ["Q1 24","Q2 24","Q3 24","Q4 24","Q1 25","Q2 25","Q3 25","Q4 25","Q1 26"]
US_CPI_L = sl(s, "CPI YoY") or ["Jun 25","Jul 25","Ago 25","Sep 25","Oct 25","Nov 25","Dic 25","Ene 26","Feb 26","Mar 26","Abr 26","May 26"]
US_PCE_L = sl(s, "PCE YoY") or ["May 25","Jun 25","Jul 25","Ago 25","Sep 25","Oct 25","Nov 25","Dic 25","Ene 26","Feb 26","Mar 26","Abr 26","May 26"]

# ── Brasil ───────────────────────────────────────────────
print("  Brasil...")
ws_br = get_sheet("Brasil")
s_br = parse_series(ws_br) if ws_br else {}

# ── China ────────────────────────────────────────────────
print("  China...")
ws_cn = get_sheet("China")
s_cn = parse_series(ws_cn) if ws_cn else {}

# ── Eurozona ─────────────────────────────────────────────
print("  Eurozona...")
ws_eu = get_sheet("Eurozona")
s_eu = parse_series(ws_eu) if ws_eu else {}

# ── Japón ────────────────────────────────────────────────
print("  Japón...")
ws_jp = get_sheet("Japón")
s_jp = parse_series(ws_jp) if ws_jp else {}

# ── ARG: leer por hojas específicas ──────────────────────
print("  Argentina...")
ws_ipc  = get_sheet("ARG_IPC")
ws_act  = get_sheet("ARG_Actividad")
ws_com  = get_sheet("ARG_Comercio")
ws_bcra = get_sheet("ARG_BCRA")
ws_fisc = get_sheet("ARG_Fiscal")

s_ipc  = parse_series(ws_ipc)  if ws_ipc  else {}
s_act  = parse_series(ws_act)  if ws_act  else {}
s_bcra = parse_series(ws_bcra) if ws_bcra else {}
s_fisc = parse_series(ws_fisc) if ws_fisc else {}

# Helper: read a table (multi-row) from ws starting at a given row
def read_table_rows(ws, title_partial, col_count):
    """Find a table by partial title match and return rows as lists."""
    for r in range(1, ws.max_row+1):
        v = ws.cell(r, 1).value
        if v and title_partial.lower() in str(v).lower():
            rows = []
            r2 = r + 2  # skip title + header
            while r2 <= ws.max_row:
                row_label = ws.cell(r2, 1).value
                if not row_label:
                    break
                row_vals = [ws.cell(r2, c).value for c in range(2, col_count+2)]
                rows.append((str(row_label), row_vals))
                r2 += 1
            return rows
    return []

# ── BUILD SEED ──────────────────────────────────────────
D = {
  "us": {
    "gdp":  {"l": sl(s, "GDP — Crecimiento Trimestral SAAR (%)") or US_GDP_L,
              "v": sv(s, "GDP — Crecimiento Trimestral SAAR (%)") or [0.8,3.6,3.3,1.9,-0.6,3.8,4.4,0.5,2.1]},
    "cpi":  {"l": US_CPI_L, "v": sv(s, "CPI YoY") or [2.6,2.7,2.9,3.0,2.9,2.7,3.0,2.8,2.7,3.3,3.8,4.2]},
    "cpiCore": sv(s, "Core CPI YoY") or [2.6,2.7,2.8,2.8,2.7,2.7,2.8,2.9,2.7,2.7,2.8,2.9],
    "cpiMoM":  sv(s, "CPI MoM") or [0.3,0.2,0.4,0.3,0.2,0.1,0.2,0.2,0.2,0.9,0.6,0.5],
    "pce":  {"l": US_PCE_L, "v": sv(s, "PCE YoY") or [2.3,2.6,2.6,2.7,2.8,2.7,2.8,2.9,2.9,2.9,3.5,3.8,4.1]},
    "pceCore": sv(s, "Core PCE YoY") or [2.5,2.5,2.6,2.7,2.7,2.6,2.7,3.0,3.1,3.0,3.2,3.3,3.4],
    "pceMoM":  sv(s, "PCE MoM") or [0.1,0.2,0.2,0.2,0.2,0.2,0.2,0.3,0.2,0.2,0.4,0.4,0.4],
    "ppi":  {"l": US_PCE_L, "v": sv(s, "PPI YoY") or [2.6,2.4,3.2,2.7,3.0,2.8,3.1,3.1,2.4,4.0,6.9,9.8,6.5]},
    "ppiCore": sv(s, "Core PPI YoY") or [2.5,2.3,3.1,2.7,3.0,2.8,3.0,3.0,3.0,3.3,4.1,3.9,5.1],
    "ppiMoM":  sv(s, "PPI MoM") or [0.2,0.3,0.5,0.2,0.3,0.2,0.3,0.3,0.4,0.7,1.4,1.1,1.1],
    "ur":  {"l": US_PCE_L, "v": sv(s, "Desempleo (%)") or [4.2,4.1,4.3,4.3,4.4,4.4,4.5,4.4,4.3,4.4,4.3,4.3,4.3]},
    "nfp": {"l": US_PCE_L, "v": sv(s, "NFP (miles)") or [19,-13,72,-26,108,-173,56,-17,160,-156,214,179,172]},
    "trade":{"l": sl(s,"Balanza Comercial — EE.UU.") or ["Jul 25","Ago 25","Sep 25","Oct 25","Nov 25","Dic 25","Ene 26","Feb 26","Mar 26"],
              "v": sv(s,"Balanza Comercial — EE.UU.") or [-74,-56,-49,-31,-56,-73,-55,-58,-60]},
    "fed":  {"l": sl(s,"Fed Funds Rate") or ["Ene 22","Jun 22","Dic 22","Mar 23","Jun 23","Dic 23","Sep 24","Nov 24","Dic 24","Oct 25","Nov 25","Dic 25"],
              "v": sv(s,"Fed Funds Rate") or [0.25,1.5,4.25,4.75,5.25,5.5,5.0,4.75,4.5,4.25,4.0,3.75]},
    "claims":{"l": sl(s,"Jobless Claims") or ["Ene 25","Feb 25","Mar 25","Abr 25","May 25","Jun 25","Jul 25","Ago 25","Sep 25","Oct 25","Nov 25","Dic 25","Ene 26","Feb 26","Mar 26","Abr 26"],
               "v": sv(s,"Jobless Claims") or [217,228,224,227,235,240,238,245,250,242,237,226,220,218,225,210]}
  },
  "br": {
    "cpi":    {"l": sl(s_br,"IPCA YoY") or [], "v": sv(s_br,"IPCA YoY") or [4.76,4.87,4.83,4.56,5.06,5.48,5.53,5.32,5.35,5.23,5.13,5.17,4.68,4.46,4.26,4.44,3.81,4.14,4.39,4.72]},
    "cpiMoM": sv(s_br,"IPCA MoM") or [0.56,0.39,0.52,0.16,1.31,0.56,0.43,0.26,0.24,0.26,-0.11,0.48,0.09,0.18,0.33,0.33,0.70,0.88,0.67,0.58],
    "selic":  {"l": sl(s_br,"SELIC") or [], "v": sv(s_br,"SELIC") or [10.75,11.25,12.25,13.25,13.25,14.25,14.25,14.75,15.0,15.0,15.0,15.0,15.0,15.0,15.0,15.0,15.0,14.75,14.50]},
    "ur":     {"l": sl(s_br,"Desempleo PNAD") or [], "v": sv(s_br,"Desempleo PNAD") or [7.2,7.0,6.9,6.6,6.2,6.1,5.8,5.6,5.6,5.4,6.1,5.8]},
    "gdp":    {"l": sl(s_br,"PIB QoQ") or [], "v": sv(s_br,"PIB QoQ") or [1.47,2.04,2.48,2.99,1.8]},
    "trade":  {"l": sl(s_br,"Balanza Comercial") or [], "v": sv(s_br,"Balanza Comercial") or [7673,7613,6999,5691,6822,9633,6200,5800,7100]}
  },
  "cn": {
    "cpi":    {"l": sl(s_cn,"CPI YoY") or [], "v": sv(s_cn,"CPI YoY") or [-0.99,-0.70,-0.10,0.50,0.80,0.50,-0.70,-0.10,1.2,1.2]},
    "ppi":    {"l": sl(s_cn,"PPI YoY") or [], "v": sv(s_cn,"PPI YoY") or [-2.8,-2.5,-2.3,-2.5,-2.3,-2.1,-2.2,-2.4,2.8,3.9]},
    "pmiNbs": {"l": sl(s_cn,"PMI NBS Manufactura") or [], "v": sv(s_cn,"PMI NBS Manufactura") or [49.8,50.1,50.3,49.2,50.1,49.0,50.4,50.3,49.5]},
    "pmiSvc": {"l": sl(s_cn,"PMI NBS Servicios") or [], "v": sv(s_cn,"PMI NBS Servicios") or [50.3,50.8,51.5,52.2,52.5,50.4,50.1,49.4,49.8]},
    "pmiCai": {"l": sl(s_cn,"PMI Caixin Manufactura") or [], "v": sv(s_cn,"PMI Caixin Manufactura") or [49.3,50.3,51.5,50.5,50.9,50.8,52.1,52.2,51.8]},
    "ip":     {"l": sl(s_cn,"Prod. Industrial YoY") or [], "v": sv(s_cn,"Prod. Industrial YoY") or [4.5,5.4,5.3,5.4,6.2,1.8,6.3,7.7,4.1,4.5]},
    "ret":    {"l": sl(s_cn,"Ventas Minoristas YoY") or [], "v": sv(s_cn,"Ventas Minoristas YoY") or [2.1,3.2,4.8,3.0,3.7,3.1,4.0,4.6,5.1,-0.6]},
    "rate":   {"l": sl(s_cn,"Tasa LPR 1 año") or [], "v": sv(s_cn,"Tasa LPR 1 año") or [3.45,3.35,3.1,3.1,3.1,3.1,3.1,3.1,3.1,3.1]},
    "trade":  {"l": sl(s_cn,"Balanza Comercial") or [], "v": sv(s_cn,"Balanza Comercial") or [990,910,1048,982,1023,905,960,1020,980,880,920,970]}
  },
  "eu": {
    "cpi":     {"l": sl(s_eu,"HICP YoY") or [], "v": sv(s_eu,"HICP YoY") or [2.3,2.4,1.7,1.9,2.6,3.0]},
    "cpiCore": sv(s_eu,"Core HICP YoY") or [2.7,2.7,2.2,2.4,2.3,2.2],
    "ppi":     {"l": sl(s_eu,"PPI YoY") or [], "v": sv(s_eu,"PPI YoY") or [-3.2,-2.9,-1.8,-0.9,0.2,0.8]},
    "bce":     {"l": sl(s_eu,"BCE") or [], "v": sv(s_eu,"BCE") or [3.75,3.5,3.25,3.0,2.75,2.5,2.25,2.25,2.25,2.25,2.25,2.50]},
    "ur":      {"l": sl(s_eu,"Desempleo") or [], "v": sv(s_eu,"Desempleo") or [6.2,6.1,6.1,6.2,6.1]},
    "gdp":     {"l": sl(s_eu,"PIB QoQ") or [], "v": sv(s_eu,"PIB QoQ") or [0.3,0.3,0.4,0.2,0.4]},
    "trade":   {"l": [], "v": [4770,4696,5117,5071,6988,5567]}
  },
  "jp": {
    "cpi":     {"l": sl(s_jp,"CPI YoY") or [], "v": sv(s_jp,"CPI YoY") or [2.9,3.6,1.5,1.3,0.0,1.4]},
    "cpiCore": sv(s_jp,"Core CPI YoY") or [2.7,3.0,1.8,1.6,0.0,1.3],
    "ppi":     {"l": sl(s_jp,"PPI YoY") or [], "v": sv(s_jp,"PPI YoY") or [3.7,4.0,4.2,4.3,3.8,3.9]},
    "boj":     {"l": sl(s_jp,"BOJ") or [], "v": sv(s_jp,"BOJ") or [0.0,0.25,0.5,0.5,1.0]},
    "ur":      {"l": sl(s_jp,"Desempleo") or [], "v": sv(s_jp,"Desempleo") or [2.4,2.4,2.5,2.4,2.4,2.5]},
    "gdp":     {"l": sl(s_jp,"PIB QoQ") or [], "v": sv(s_jp,"PIB QoQ") or [-0.2,0.3,0.7,0.45]},
    "trade":   {"l": sl(s_jp,"Balanza Comercial") or [], "v": sv(s_jp,"Balanza Comercial") or [0.3,2.1,-2.7,1.1,0.6,-0.12]}
  },
  "arg": {
    "ipc":       {"l": sl(s_ipc,"IPC General MoM") or [], "v": sv(s_ipc,"IPC General MoM") or [1.5,1.6,1.9,1.9,2.1,2.3,2.5,2.8,2.9,2.9,3.4,2.6,2.1]},
    "nucleo":    sv(s_ipc,"IPC Núcleo MoM") or [1.4,1.5,1.7,1.8,1.9,2.0,2.3,2.6,2.6,3.1,3.2,2.3,1.9],
    "regulados": sv(s_ipc,"IPC Regulados MoM") or [1.0,2.0,2.4,2.2,2.1,2.9,3.5,3.4,2.4,4.3,5.1,4.7,2.4],
    "estacion":  sv(s_ipc,"IPC Estacionales MoM") or [5.8,-0.5,0.8,1.0,2.4,2.4,0.4,2.2,5.7,-1.3,1.0,0.0,2.1],
    "ipcYoY":   {"l": sl(s_ipc,"IPC General YoY") or [], "v": sv(s_ipc,"IPC General YoY") or [43.5,39.4,36.6,33.6,31.8,31.3,31.4,31.5,32.4,33.1,32.6,32.4,33.2]},
    "emae":     {"l": sl(s_act,"EMAE YoY") or [], "v": sv(s_act,"EMAE YoY") or [7.8,5.2,6.3,2.8,2.2,4.8,3.1,-0.3,3.3,1.5,-2.0,5.5]},
    "emaeDesest":{"l": sl(s_act,"EMAE Desestacionalizado MoM") or [], "v": sv(s_act,"EMAE Desestacionalizado MoM") or [0.2,1.1,-2.3,1.6,-0.1,-0.3,0.0,0.6,0.6,-0.4,0.0,1.9,-0.2,-2.7,3.5]},
    "ipi":      {"l": sl(s_act,"IPI MoM") or [], "v": sv(s_act,"IPI MoM") or [-0.1,-0.9,-1.1,0.4,2.4,-3.0,3.7,-2.1]},
    "isac":     {"l": sl(s_act,"ISAC MoM") or [], "v": sv(s_act,"ISAC MoM") or [1.2,0.0,-3.9,2.9,-0.1,-1.4,5.1,-4.0]},
    "ucii":     {"l": sl(s_act,"UCII") or [], "v": sv(s_act,"UCII") or [55.0,58.6,54.4,58.6,58.9,59.0,58.2,59.4,61.1,61.0,57.7,53.8,53.6,54.6,59.8,59.9]},
    "ipiMinero":{"l": sl(s_act,"IPI Minero YoY") or [], "v": sv(s_act,"IPI Minero YoY") or [0.2,6.8,7.8,4.0,2.0,4.1,2.2,5.0,5.5,3.4,10.8,9.5]},
    "tasa":     {"l": sl(s_bcra,"Tasa de Política Monetaria") or [], "v": sv(s_bcra,"Tasa de Política Monetaria") or [32.0,30.0,30.0,30.0,35.0,35.0,32.0,32.0,26.0,26.0,26.0,29.0,29.0]},
    "m2":       {"l": sl(s_bcra,"M2 Privado YoY") or [], "v": sv(s_bcra,"M2 Privado YoY") or [35.2,28.4,22.1,18.6,24.3,28.1,31.4,29.8]},
    "credito":  {"l": sl(s_bcra,"Crédito Privado YoY") or [], "v": sv(s_bcra,"Crédito Privado YoY") or [185.4,198.2,210.6,224.8,215.3,218.9,228.4,241.6]},
    "reservasLargo": {"l": sl(s_bcra,"Reservas Brutas — Serie Larga") or [], "v": sv(s_bcra,"Reservas Brutas — Serie Larga") or []},
    "baseMonLargo":  {"l": sl(s_bcra,"Base Monetaria — Serie Larga") or [], "v": sv(s_bcra,"Base Monetaria — Serie Larga") or []}
  },
  "_meta": {
    "updated": "2026-06-25",
    "source": "Amberes Consultora — generado con xlsx_to_json.py"
  }
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(D, f, ensure_ascii=False, indent=2)

print(f"\n✓ seed.json actualizado ({OUT.stat().st_size/1024:.1f} KB)")
print("  Siguiente paso: npx vercel --prod --yes")
