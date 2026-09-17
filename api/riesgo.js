const fs = require('fs');
const path = require('path');

module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'public, max-age=300, s-maxage=300');
  try {
    const isHistory = req.query && req.query.history === '1';
    const file = path.join(process.cwd(), 'data', isHistory ? 'riesgo_history.json' : 'riesgo.json');
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    res.status(200).json(data);
  } catch (e) {
    res.status(isHistory ? 200 : 404).json(isHistory ? [] : { error: 'No hay datos de riesgo disponibles aún.' });
  }
};
