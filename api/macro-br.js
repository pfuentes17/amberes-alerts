// FRED SELIC (IRSTCI01BRM156N) devuelve promedios diarios — imprecisos vs tasa de decisión.
// FRED GDP (NAEXKP01BRQ657S) devuelve QoQ en escala decimal tiny — inutilizable.
// Fuentes BCB: IPCA YoY (13522), IPCA MoM (433), Desempleo PNAD (24369) — funcionan bien.

async function bcb(s, n = 20) {
  try {
    const r = await fetch(
      `https://api.bcb.gov.br/dados/serie/bcdata.sgs.${s}/dados/ultimos/${n}?formato=json`,
      { signal: AbortSignal.timeout(12000), headers: { 'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0' } }
    );
    return r.ok ? r.json() : null;
  } catch { return null; }
}

const MES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const fmtB = s => { const p = s.split('/'); return MES[parseInt(p[1]) - 1] + ' ' + p[2].slice(2); };

module.exports = async function(req, res) {
  try {
    const [ipcaY, ipcaM, ur] = await Promise.all([
      bcb(13522, 20), // IPCA acum. 12 meses (YoY)
      bcb(433, 20),   // IPCA mensal (MoM)
      bcb(24369, 12)  // Desempleo PNAD contínua
    ]);

    const out = { ok: true };
    if (ipcaY) out.cpi  = { l: ipcaY.map(o => fmtB(o.data)), v: ipcaY.map(o => parseFloat(o.valor)) };
    if (ipcaM) out.cpiMoM = ipcaM.map(o => parseFloat(o.valor));
    if (ur)    out.ur   = { l: ur.map(o => fmtB(o.data)),    v: ur.map(o => parseFloat(o.valor)) };

    res.setHeader('Cache-Control', 'public,max-age=3600');
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.status(200).json(out);
  } catch(e) {
    res.status(502).json({ ok: false, error: e.message });
  }
};
