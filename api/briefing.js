// /api/briefing.js — Sirve data/briefing.json con headers correctos
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const data = require('../data/briefing.json');

export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=7200');
  res.status(200).json({ ok: true, data });
}
