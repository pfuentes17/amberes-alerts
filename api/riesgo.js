const fs = require('fs');
const path = require('path');

// /api/riesgo               → data/riesgo.json          (pestaña Riesgo de cartera.html)
// /api/riesgo?history=1     → data/riesgo_history.json
// /api/riesgo?cartera=1     → data/cartera.json         (pestaña Composición, update_cartera.py) — 26/11/2026
// /api/riesgo?cartera=hist  → data/cartera_history.json
// /api/riesgo?cartera=gestion → data/gestion.json      (pestaña Gestión, update_gestion.py) — 27/11/2026
// /api/riesgo?indice=fng      → data/fng.json          (indices.html, Miedo y Codicia, update_fng.py) — 27/11/2026
// (se reutiliza esta función porque el plan Hobby de Vercel permite máx. 12 funciones)
module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'public, max-age=300, s-maxage=300');
  const q = req.query || {};
  const isHistory = q.history === '1' || q.cartera === 'hist';
  const base = q.indice === 'fng' ? 'fng' : q.cartera === 'gestion' ? 'gestion' : q.cartera ? 'cartera' : 'riesgo';
  try {
    const file = path.join(process.cwd(), 'data', base + (isHistory ? '_history' : '') + '.json');
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    res.status(200).json(data);
  } catch (e) {
    res.status(isHistory ? 200 : 404).json(isHistory ? [] : { error: 'No hay datos disponibles aún.' });
  }
};
