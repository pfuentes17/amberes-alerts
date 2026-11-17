// Proxy consolidado — reemplaza 9 funciones individuales de 1 sola
// Uso: /api/proxy?src=<key>
const SOURCES = {
  bonds:      'https://data912.com/live/arg_bonds',
  cedears:    'https://data912.com/live/arg_cedears',
  notes:      'https://data912.com/live/arg_notes',
  corp:       'https://data912.com/live/arg_corp',
  dolar:      'https://dolarapi.com/v1/dolares',
  bcra:       'https://rendimientos.co/api/bcra',
  lecaps:     'https://rendimientos.co/api/lecaps',
  soberanos:  'https://rendimientos.co/api/soberanos',
  'cer-precios':  'https://rendimientos.co/api/cer-precios',
};

const BYMA_ON_URL = 'https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/negociable-obligations';
// rendimientos.co/api/cer (usado antes para "cer-index") quedó pisado ~13 días desde
// principios de septiembre 2026 pese a etiquetarse "BCRA (T-10)" — se detectó porque el
// gráfico de la curva CER en bonos.html se veía "siempre igual" (índice congelado). Se
// reemplaza por la serie oficial del BCRA (id 30) directo, tomando el último valor publicado.
const BCRA_CER_URL = 'https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/30';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=60');

  const src = req.query.src;

  // CER oficial — BCRA directo (id 30), CER a T-10 hábiles (misma convención de prospecto
  // usada para el CER₀ de emisión de los bonos CER en bonos.html: el CER de la fecha D no
  // se conoce hasta 10 días hábiles después, así que se opera con el valor de D-10 hábiles).
  // No cuenta feriados (solo fin de semana) — mismo criterio ya usado y validado esta sesión.
  if (src === 'cer-index') {
    try {
      let cur = new Date();
      let count = 0;
      while (count < 10) {
        cur = new Date(cur.getTime() - 24 * 3600 * 1000);
        if (cur.getUTCDay() !== 0 && cur.getUTCDay() !== 6) count++;
      }
      const hasta = cur;
      const desde = new Date(hasta.getTime() - 10 * 24 * 3600 * 1000); // margen extra por feriados
      const fmt = d => d.toISOString().slice(0, 10);
      const url = `${BCRA_CER_URL}?desde=${fmt(desde)}&hasta=${fmt(hasta)}`;
      const r = await fetch(url, { signal: AbortSignal.timeout(9000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      const serie = data?.results?.[0]?.detalle || [];
      if (!serie.length) throw new Error('serie BCRA vacía');
      const ultimo = serie[0]; // la API devuelve orden descendente (más reciente primero)
      return res.status(200).json({ cer: ultimo.valor, fecha: ultimo.fecha, fuente: 'BCRA (id 30, T-10, directo)' });
    } catch (e) {
      return res.status(502).json({ error: e.message });
    }
  }

  // Serie CER diaria del BCRA (id 30) desde hace 40 días hasta lo último PUBLICADO, que llega por adelantado
  // hasta el 15 del mes siguiente (el CER de cada período 15→15 se define con el IPC de M-2). La usa el
  // breakeven de bonos.html para separar el CER ya conocido del que depende de IPC todavía no publicado.
  if (src === 'cer-serie') {
    try {
      const fmt = d => d.toISOString().slice(0, 10);
      const now = new Date();
      const desde = new Date(now.getTime() - 40 * 86400000), hasta = new Date(now.getTime() + 70 * 86400000);
      const r = await fetch(`${BCRA_CER_URL}?desde=${fmt(desde)}&hasta=${fmt(hasta)}&limit=1000`, { signal: AbortSignal.timeout(9000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      const serie = (data?.results?.[0]?.detalle || []).map(x => ({ fecha: x.fecha, valor: x.valor })).sort((a, b) => a.fecha < b.fecha ? -1 : 1);
      if (!serie.length) throw new Error('serie BCRA vacía');
      res.setHeader('Cache-Control', 's-maxage=3600');
      return res.status(200).json({ serie, ultimo: serie[serie.length - 1], fuente: 'BCRA (id 30)' });
    } catch (e) {
      return res.status(502).json({ error: e.message });
    }
  }

  // TAMAR bancos privados (BCRA id 136, TNA %), diaria desde abr-2026 — para acumular la pata TAMAR de los duales CER/TAMAR desde su emisión
  if (src === 'tamar-hist') {
    try {
      const fmt = d => d.toISOString().slice(0, 10);
      const r = await fetch(`https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/136?desde=2024-10-01&hasta=${fmt(new Date())}&limit=1000`, { signal: AbortSignal.timeout(9000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      const serie = (d?.results?.[0]?.detalle || []).map(x => ({ f: x.fecha, v: x.valor })).sort((a, b) => a.f.localeCompare(b.f));
      if (!serie.length) throw new Error('serie TAMAR vacía');
      res.setHeader('Cache-Control', 's-maxage=3600');
      return res.status(200).json({ serie, fuente: 'BCRA (id 136, TAMAR bancos privados TNA)' });
    } catch (e) {
      return res.status(502).json({ error: e.message });
    }
  }

  // Bandas cambiarias — BCRA directo (ids 1187 límite inferior / 1188 límite superior). El BCRA publica la serie
  // por adelantado (hasta fin del mes en curso), así el dashboard no depende de constantes hardcodeadas.
  if (src === 'banda') {
    try {
      const fmt = d => d.toISOString().slice(0, 10);
      const hoy = new Date();
      const desde = fmt(new Date(hoy.getTime() - 4 * 24 * 3600 * 1000));
      const hasta = fmt(new Date(hoy.getTime() + 150 * 24 * 3600 * 1000));
      const get = async id => {
        const r = await fetch(`https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/${id}?desde=${desde}&hasta=${hasta}&limit=400`, { signal: AbortSignal.timeout(9000) });
        if (!r.ok) throw new Error(`HTTP ${r.status} (id ${id})`);
        const d = await r.json();
        return Object.fromEntries((d?.results?.[0]?.detalle || []).map(x => [x.fecha, x.valor]));
      };
      const [lo, hi] = await Promise.all([get(1187), get(1188)]);
      const serie = Object.keys(hi).filter(f => f in lo).sort().map(f => ({ f, piso: lo[f], techo: hi[f] }));
      if (!serie.length) throw new Error('serie de bandas vacía');
      res.setHeader('Cache-Control', 's-maxage=3600');
      return res.status(200).json({ serie, fuente: 'BCRA (ids 1187/1188)' });
    } catch (e) {
      return res.status(502).json({ error: e.message });
    }
  }

  // Soberanos USD-MEP en la forma del viejo feed de Netlify (usado por confianza.html):
  // {data:[{symbol, price_usd, bid, ask, volume, pct_change}], source}. Fuente: data912, líneas "XXXD".
  if (src === 'soberanos-usd') {
    try {
      const SYMS = ['AL29','AL30','AL35','AL41','AE38','AO27','AO28','AO29','BPD7','GD29','GD30','GD35','GD38','GD41','GD46'];
      const r = await fetch(SOURCES.bonds, { signal: AbortSignal.timeout(9000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const by = Object.fromEntries((await r.json()).map(x => [x.symbol, x]));
      const data = SYMS.map(sym => {
        const x = by[sym + 'D'];
        return x && x.c ? { symbol: sym, price_usd: x.c, bid: x.px_bid, ask: x.px_ask, volume: x.v, pct_change: x.pct_change } : null;
      }).filter(Boolean);
      if (!data.length) throw new Error('sin datos');
      return res.status(200).json({ data, source: 'data912' });
    } catch (e) {
      return res.status(502).json({ error: e.message, data: [] });
    }
  }

  // BYMA ONs — POST especial
  if (src === 'byma-ons') {
    try {
      const r = await fetch(BYMA_ON_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Origin': 'https://open.bymadata.com.ar' },
        body: JSON.stringify({ page: 0, pageSize: 100 }),
        signal: AbortSignal.timeout(9000),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      return res.status(200).json(data);
    } catch (e) {
      return res.status(502).json({ error: e.message });
    }
  }

  const url = SOURCES[src];
  if (!url) return res.status(400).json({ error: `src inválido: ${src}` });
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(9000) });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    res.status(200).json(data);
  } catch (e) {
    res.status(502).json({ error: e.message });
  }
}
