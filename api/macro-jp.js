const KEY = process.env.FRED_API_KEY, BASE = 'https://api.stlouisfed.org/fred/series/observations';

// FRED no tiene series recientes de JP CPI/PPI/Trade/BOJ útiles.
// Solo UR tiene serie funcional: LRUNTTTTJPM156S (hasta Mar 2026).
// GDP en FRED devuelve niveles en billones — inutilizable como % QoQ.
// El seed es la fuente de verdad para CPI, PPI, Trade, BOJ, GDP.

async function fred(id, n = 8) {
  try {
    const r = await fetch(`${BASE}?series_id=${id}&api_key=${KEY}&file_type=json&sort_order=desc&limit=${n}`, { signal: AbortSignal.timeout(9000) });
    if (!r.ok) return [];
    const j = await r.json();
    return (j.observations || []).reverse().filter(o => o.value !== '.');
  } catch { return []; }
}

const MES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const fmtM = d => { const x = new Date(d + 'T12:00:00Z'); return MES[x.getUTCMonth()] + ' ' + String(x.getUTCFullYear()).slice(2); };
const fmt = a => a.length ? { l: a.map(o => fmtM(o.date)), v: a.map(o => parseFloat(o.value)) } : null;

module.exports = async function(req, res) {
  try {
    const ur = await fred('LRUNTTTTJPM156S', 8);
    res.setHeader('Cache-Control', 'public,max-age=3600');
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.status(200).json({
      ok: true,
      cpi: null, cpiCore: null, ppi: null,
      ur: fmt(ur) || null,
      gdp: null, boj: null, trade: null
    });
  } catch(e) {
    res.status(502).json({ ok: false, error: e.message });
  }
};
