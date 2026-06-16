// /api/briefing.js — Sirve data/briefing.json (CommonJS-compatible)
const path = require('path');
const fs = require('fs');

module.exports = function handler(req, res) {
  try {
    const file = path.join(process.cwd(), 'data', 'briefing.json');
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=7200');
    res.status(200).json({ ok: true, data });
  } catch(e) {
    res.status(500).json({ ok: false, error: e.message });
  }
};
