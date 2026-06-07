const fs = require('fs');
const path = require('path');

module.exports = async function handler(req, res) {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'manual.json'), 'utf8'));
    res.setHeader('Cache-Control', 'public, max-age=1800');
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.status(200).json(data);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
};
