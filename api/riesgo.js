const fs = require('fs');
const path = require('path');

module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'public, max-age=300, s-maxage=300');
  try {
    const file = path.join(process.cwd(), 'data', 'riesgo.json');
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    res.status(200).json(data);
  } catch (e) {
    res.status(404).json({ error: 'No hay datos de riesgo disponibles aún.' });
  }
};
