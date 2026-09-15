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
