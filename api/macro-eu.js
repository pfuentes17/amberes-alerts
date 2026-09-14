// FRED no tiene series recientes de EU (HICP, PPI, UR desactualizadas hasta 2022).
// BCE devuelve 1 solo punto. Seed de EU es la fuente de verdad — no sobreescribir.
// Mantener estructura para futuro si FRED actualiza series.
module.exports = async function(req, res) {
  res.setHeader('Cache-Control', 'public,max-age=3600');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.status(200).json({ ok: true, cpi: null, cpiCore: null, ppi: null, bce: null, ur: null, gdp: null });
};
