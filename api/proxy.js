// Proxy consolidado — reemplaza 9 funciones individuales de 1 sola
// Uso: /api/proxy?src=<key>
const SOURCES = {
  bonds:      'https://data912.com/live/arg_bonds',
  cedears:    'https://data912.com/live/arg_cedears',
  notes:      'https://data912.com/live/arg_notes',
  dolar:      'https://dolarapi.com/v1/dolares',
  bcra:       'https://rendimientos.co/api/bcra',
  lecaps:     'https://rendimientos.co/api/lecaps',
  soberanos:  'https://rendimientos.co/api/soberanos',
  'cer-index':    'https://rendimientos.co/api/cer',
  'cer-precios':  'https://rendimientos.co/api/cer-precios',
};

const BYMA_ON_URL = 'https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/negociable-obligations';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=60');

  const src = req.query.src;

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
