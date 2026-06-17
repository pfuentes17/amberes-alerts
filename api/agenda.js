// /api/agenda.js — Genera la agenda de próximos eventos desde data/calendar.json
// Fuente única: si cambia el calendario, la agenda se actualiza sola.
const path = require('path');
const fs = require('fs');

const DOW = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
const MON = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

const LIMIT = 10; // cuántos eventos próximos mostrar

module.exports = function handler(req, res) {
  try {
    const file = path.join(__dirname, '..', 'data', 'calendar.json');
    const { events } = JSON.parse(fs.readFileSync(file, 'utf8'));

    // "Hoy" según la fecha de calendario en Argentina (UTC-3), no en UTC del servidor
    const todayStr = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Argentina/Buenos_Aires',
      year: 'numeric', month: '2-digit', day: '2-digit'
    }).format(new Date()); // -> "2026-06-16"
    const today = new Date(todayStr + 'T00:00:00Z');

    const upcoming = events
      .map(e => ({ ...e, _d: new Date(e.date + 'T00:00:00Z') }))
      .filter(e => e._d >= today)
      .sort((a, b) => a._d - b._d)
      .slice(0, LIMIT)
      .map(e => {
        const isToday = e._d.getTime() === today.getTime();
        let fecha;
        if (isToday) {
          fecha = 'Hoy';
        } else {
          fecha = `${DOW[e._d.getUTCDay()]} ${e._d.getUTCDate()} ${MON[e._d.getUTCMonth()]}`;
        }
        if (e.time) fecha += ` · ${e.time}`;
        if (e.star) fecha += ' ⭐';
        return { flag: e.flag, fecha, evento: e.evento, bold: !!e.star || isToday };
      });

    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=7200');
    res.status(200).json({ ok: true, data: upcoming });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
};
