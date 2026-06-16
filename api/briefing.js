// /api/briefing.js — Sirve el briefing.json con headers correctos
import data from './briefing.json' assert { type: 'json' };

export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=7200');
  res.status(200).json({ ok: true, data });
}
