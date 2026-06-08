const nodemailer = require('nodemailer');
const path = require('path');
const fs = require('fs');

const SITE_URL = 'https://macroargy-eight.vercel.app/macro.html';

const RECIPIENTS = [
  'pedrof@grupoamberes.com.ar',
  'soledad@grupoamberes.com.ar',
  'angelesgf@grupoamberes.com.ar',
  'Jheredia@grupoamberes.com.ar',
  'nicolas_lop@hotmail.com',
];

const CATEGORY_LABELS = {
  inflation: 'Inflación',
  labor:     'Mercado laboral',
  activity:  'Actividad económica',
  monetary:  'Política monetaria',
  trade:     'Comercio exterior',
  fiscal:    'Fiscal',
};

const CATEGORY_COLORS = {
  inflation: '#e53e3e',
  labor:     '#38a169',
  activity:  '#3182ce',
  monetary:  '#805ad5',
  trade:     '#dd6b20',
  fiscal:    '#d69e2e',
};

function getWeekRange(date, offset = 0) {
  const d = new Date(date);
  const day = d.getUTCDay();
  const monday = new Date(d);
  monday.setUTCDate(d.getUTCDate() - (day === 0 ? 6 : day - 1) + offset * 7);
  monday.setUTCHours(0, 0, 0, 0);
  const friday = new Date(monday);
  friday.setUTCDate(monday.getUTCDate() + 4);
  friday.setUTCHours(23, 59, 59, 999);
  return { monday, friday };
}

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T12:00:00Z');
  const days = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
  const months = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
  return `${days[d.getUTCDay()]} ${d.getUTCDate()} ${months[d.getUTCMonth()]}`;
}

function buildEmailHtml(releases, weekLabel, weekRange, isFriday) {
  const byDay = {};
  releases.forEach(r => { if (!byDay[r.date]) byDay[r.date] = []; byDay[r.date].push(r); });

  const MONTHS = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const DAYS   = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'];

  function fmtLong(dateStr) {
    const d = new Date(dateStr + 'T12:00:00Z');
    return `${DAYS[d.getUTCDay()]} ${d.getUTCDate()} de ${MONTHS[d.getUTCMonth()]}`;
  }
  function fmtShort(dateStr) {
    const d = new Date(dateStr + 'T12:00:00Z');
    return `${d.getUTCDate()} de ${MONTHS[d.getUTCMonth()]}`;
  }

  const mondayFmt = fmtShort(weekRange.monday.toISOString().slice(0,10));
  const fridayFmt = fmtShort(weekRange.friday.toISOString().slice(0,10));
  const year = weekRange.monday.getUTCFullYear();

  const dayBlocks = Object.keys(byDay).sort().map(date => {
    const items = byDay[date].map(r => `
      <table style="width:100%;border-collapse:collapse;margin-bottom:2px">
        <tr>
          <td style="vertical-align:top;padding:14px 0 14px 20px;border-left:4px solid #00e880;width:100%">
            <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#00A99D;font-family:'Lato',Arial,sans-serif;font-weight:700;margin-bottom:5px">${r.flag}&nbsp; ${CATEGORY_LABELS[r.category] || r.category}</div>
            <div style="font-size:15px;color:#1e1e22;font-family:'Lato',Arial,sans-serif;font-weight:700;line-height:1.3;margin-bottom:4px">${r.indicator}</div>
            <div style="font-size:12px;color:#606060;font-family:'Lato',Arial,sans-serif;line-height:1.5">${r.detail}</div>
          </td>
        </tr>
      </table>`).join('<div style="height:10px"></div>');

    return `
      <div style="margin-bottom:28px">
        <div style="font-size:10px;letter-spacing:2.5px;text-transform:uppercase;color:#1e1e22;font-family:'Lato',Arial,sans-serif;font-weight:700;padding-bottom:10px;border-bottom:2px solid #1e1e22;margin-bottom:14px">${fmtLong(date)}</div>
        ${items}
      </div>`;
  }).join('');

  const greeting = isFriday
    ? `Te acercamos las publicaciones macroeconómicas relevantes programadas para la <strong>próxima semana</strong> (${mondayFmt} – ${fridayFmt} de ${year}).`
    : `Te acercamos las publicaciones macroeconómicas relevantes programadas para <strong>esta semana</strong> (${mondayFmt} – ${fridayFmt} de ${year}).`;

  const emptyMsg = `<p style="font-size:14px;color:#606060;text-align:center;padding:30px 0;font-style:italic;font-family:'Lato',Arial,sans-serif">No se registran publicaciones macroeconómicas relevantes para este período.</p>`;

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Lato:wght@300;400;700&display=swap" rel="stylesheet">
<title>Amberes — Calendario Macro</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:'Lato',Arial,sans-serif">
<div style="max-width:600px;margin:0 auto">

  <!-- Header -->
  <div style="background:#1e1e22;padding:32px 40px 24px">
    <table style="width:100%;border-collapse:collapse">
      <tr>
        <td style="vertical-align:middle">
          <img src="https://grupoamberes.com.ar/frontend/img/logo.svg" alt="Amberes" height="32" style="display:block;filter:brightness(0) invert(1)" onerror="this.style.display='none'">
        </td>
        <td style="vertical-align:middle;text-align:right">
        </td>
      </tr>
    </table>
  </div>

  <!-- Green rule -->
  <div style="background:#00e880;height:4px;font-size:0"></div>

  <!-- Title band -->
  <div style="background:#1e1e22;padding:28px 40px 32px">
    <div style="font-size:9px;letter-spacing:3px;text-transform:uppercase;color:#00e880;font-family:'Lato',Arial,sans-serif;font-weight:700;margin-bottom:10px">Actualización Semanal · ${year}</div>
    <div style="font-size:28px;color:#ffffff;font-family:'Lato',Arial,sans-serif;font-weight:300;line-height:1.25;margin-bottom:10px">Calendario de Publicaciones<br><strong style="font-weight:700">Macroeconómicas</strong></div>
    <div style="font-size:11px;color:rgba(255,255,255,.45);font-family:'Lato',Arial,sans-serif;letter-spacing:1px">${mondayFmt.toUpperCase()} — ${fridayFmt.toUpperCase()} &nbsp;·&nbsp; ${releases.length} PUBLICACION${releases.length !== 1 ? 'ES' : ''}</div>
  </div>

  <!-- Body -->
  <div style="background:#ffffff;padding:36px 40px">

    <!-- Intro -->
    <p style="font-size:14px;color:#333;line-height:1.75;margin:0 0 30px;font-family:'Lato',Arial,sans-serif;font-weight:300">
      ${greeting}
    </p>

    <div style="height:1px;background:#e4e4e4;margin-bottom:28px"></div>

    <!-- Events -->
    ${releases.length === 0 ? emptyMsg : dayBlocks}

    <div style="height:1px;background:#e4e4e4;margin:8px 0 28px"></div>

    <!-- CTA -->
    <table style="width:100%;border-collapse:collapse">
      <tr>
        <td style="vertical-align:middle">
          <div style="font-size:12px;color:#606060;font-family:'Lato',Arial,sans-serif">Accedé al dashboard con datos en tiempo real</div>
        </td>
        <td style="vertical-align:middle;text-align:right;white-space:nowrap;padding-left:16px">
          <a href="${SITE_URL}" style="display:inline-block;background:#00e880;color:#1e1e22;font-family:'Lato',Arial,sans-serif;font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;text-decoration:none;padding:10px 22px;border-radius:2px">Ver Dashboard</a>
        </td>
      </tr>
    </table>

  </div>

  <!-- Footer -->
  <div style="background:#1e1e22;padding:24px 40px;border-top:4px solid #00e880">
    <div style="font-size:10px;color:rgba(255,255,255,.3);font-family:'Lato',Arial,sans-serif;margin-bottom:6px"><a href="https://grupoamberes.com.ar" style="color:#00e880;text-decoration:none">grupoamberes.com.ar</a></div>
    <div style="font-size:10px;color:rgba(255,255,255,.25);font-family:'Lato',Arial,sans-serif;line-height:1.7">
      Reporte automático · Lunes y viernes · 9:00 hs (Argentina)<br>
      Fuentes: BLS · BEA · Fed · Eurostat · BCE · INDEC · BCB · NBS · IBGE
    </div>
  </div>

</div>
</body>
</html>`;
}

module.exports = async function handler(req, res) {
  try {
    const day = req.query?.day || 'monday';
    const isFriday = day === 'friday';

    // Read calendar from bundled file
    const cal = JSON.parse(fs.readFileSync(path.join(__dirname, 'release-calendar.json'), 'utf8'));

    const now = new Date();
    const offset = isFriday ? 1 : 0;
    const weekLabel = isFriday ? 'Próxima semana' : 'Esta semana';
    const { monday, friday } = getWeekRange(now, offset);

    const releases = cal.releases.filter(r => {
      const d = new Date(r.date + 'T12:00:00Z');
      return d >= monday && d <= friday;
    });

    const html = buildEmailHtml(releases, weekLabel, { monday, friday }, isFriday);
    const mondayStr = monday.toISOString().slice(0,10);
    const fridayStr = friday.toISOString().slice(0,10);
    const subject = isFriday
      ? `📅 Próxima semana: ${releases.length} publicaciones macro (${mondayStr.slice(5).replace('-','/')} – ${fridayStr.slice(5).replace('-','/')})`
      : `📊 Esta semana: ${releases.length} publicaciones macro (${mondayStr.slice(5).replace('-','/')} – ${fridayStr.slice(5).replace('-','/')})`;

    const transporter = nodemailer.createTransport({
      service: 'gmail',
      auth: {
        user: process.env.GMAIL_USER,
        pass: process.env.GMAIL_APP_PASSWORD,
      },
    });

    await transporter.sendMail({
      from: `"Amberes Dashboard" <${process.env.GMAIL_USER}>`,
      to: RECIPIENTS.join(', '),
      subject,
      html,
    });

    res.status(200).json({ ok: true, sent: RECIPIENTS.length, releases: releases.length });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
};
