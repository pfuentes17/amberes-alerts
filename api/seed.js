// /api/seed.js — Sirve data/seed.json con cache de 1 hora
const path = require('path');
const fs = require('fs');

module.exports = function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=86400');
  res.setHeader('Content-Type', 'application/json');

  try {
    const file = path.join(__dirname, '..', 'data', 'seed.json');
    const seed = fs.readFileSync(file, 'utf8');
    res.status(200).send(seed);
  } catch (e) {
    res.status(500).json({ error: 'seed.json no encontrado', detail: e.message });
  }
};
