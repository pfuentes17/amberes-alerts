// /api/briefing.js — Sirve el briefing.json con headers correctos
import { readFileSync } from 'fs';
import { join } from 'path';

export default function handler(req, res) {
  const raw = readFileSync(join(process.cwd(), 'data', 'briefing.json'), 'utf8');
  const data = JSON.parse(raw);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=7200');
  res.status(200).json({ ok: true, data });
}
