const KEY = process.env.FRED_API_KEY, BASE = 'https://api.stlouisfed.org/fred/series/observations';

// FRED no tiene series recientes de JP CPI/PPI/Trade/BOJ útiles.
// Solo UR tiene serie funcional: LRUNTTTTJPM156S (OECD, desestacionalizada; llega al mes anterior al último publicado).
// GDP en FRED devuelve niveles en billones — inutilizable como % QoQ.
// El seed es la fuente de verdad para CPI, PPI, Trade, BOJ, GDP.

// Reintenta (FRED devuelve 5xx/timeout intermitente desde Vercel); si agota reintentos lanza el error
// para que el endpoint lo informe en vez de devolver null en silencio.
async function fred(id, n = 10, retries = 3) {
  let lastErr;
  for (let i = 0; i < retries; i++) {
    try {
      if (!KEY) throw new Error('FRED_API_KEY ausente');
      const r = await fetch(`${BASE}?series_id=${id}&api_key=${KEY}&file_type=json&sort_order=desc&limit=${n}`, { signal: AbortSignal.timeout(10000) });
      if (!r.ok) throw new Error(`FRED ${id}: ${r.status}`);
      const j = await r.json();
      return (j.observations || []).reverse().filter(o => o.value !== '.');
    } catch (e) {
      lastErr = e;
      if (i < retries - 1) await new Promise(res => setTimeout(res, 500 * (i + 1)));
    }
  }
  throw lastErr;
}

const MES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const fmtM = d => { const x = new Date(d + 'T12:00:00Z'); return MES[x.getUTCMonth()] + ' ' + String(x.getUTCFullYear()).slice(2); };
const fmt = a => a.length ? { l: a.map(o => fmtM(o.date)), v: a.map(o => parseFloat(o.value)) } : null;

module.exports = async function(req, res) {
  try {
    let ur = [], urError = null;
    try { ur = await fred('LRUNTTTTJPM156S', 10); } catch (e) { urError = e.message; }
    res.setHeader('Cache-Control', 'public,max-age=3600');
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.status(200).json({
      ok: true,
      cpi: null, cpiCore: null, ppi: null,
      ur: fmt(ur) || null,
      gdp: null, boj: null, trade: null,
      ...(urError ? { urError } : {})
    });
  } catch(e) {
    res.status(502).json({ ok: false, error: e.message });
  }
};
