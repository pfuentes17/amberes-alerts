// /api/markets.js — Live market data via Yahoo Finance
// Called by index.html on page load

const SYMBOLS = {
  // Equities
  sp500:   '^GSPC',
  nasdaq:  '^IXIC',
  dow:     '^DJI',
  // Volatility
  vix:     '^VIX',
  // FX
  eurusd:  'EURUSD=X',
  usdjpy:  'JPY=X',
  cnhusd:  'CNH=X',
  // Rates (Yahoo: % already)
  ust10y:  '^TNX',
  ust2y:   '^IRX',
  // Commodities
  wti:     'CL=F',
  brent:   'BZ=F',
  gold:    'GC=F',
  copper:  'HG=F',
  // Dollar index
  dxy:     'DX-Y.NYB',
};

async function fetchQuotes(symbols) {
  const joined = Object.values(symbols).join(',');
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${joined}&fields=regularMarketPrice,regularMarketChangePercent,regularMarketPreviousClose,fiftyTwoWeekHigh,fiftyTwoWeekLow,fiftyDayAverage,regularMarketTime`;

  const res = await fetch(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0',
      'Accept': 'application/json',
    }
  });

  if (!res.ok) throw new Error(`Yahoo Finance error: ${res.status}`);
  const data = await res.json();
  return data.quoteResponse?.result || [];
}

export default async function handler(req, res) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=120'); // cache 1 min

  try {
    const quotes = await fetchQuotes(SYMBOLS);

    // Build lookup by symbol
    const bySymbol = {};
    for (const q of quotes) {
      bySymbol[q.symbol] = q;
    }

    const get = (sym) => {
      const q = bySymbol[sym];
      if (!q) return null;
      return {
        price: q.regularMarketPrice,
        chgPct: q.regularMarketChangePercent,
        prev: q.regularMarketPreviousClose,
        high52w: q.fiftyTwoWeekHigh,
        low52w: q.fiftyTwoWeekLow,
        ma50: q.fiftyDayAverage,
        ts: q.regularMarketTime,
      };
    };

    const sp    = get('^GSPC');
    const nq    = get('^IXIC');
    const vix   = get('^VIX');
    const eur   = get('EURUSD=X');
    const jpy   = get('JPY=X');
    const cnh   = get('CNH=X');
    const t10   = get('^TNX');
    const t2    = get('^IRX');
    const wti   = get('CL=F');
    const brent = get('BZ=F');
    const gold  = get('GC=F');
    const copper= get('HG=F');
    const dxy   = get('DX-Y.NYB');

    // Spread 2Y-10Y in bps
    const spread = (t10 && t2) ? ((t10.price - t2.price) * 100).toFixed(0) : null;

    // vs 52w high (%)
    const pctFromHigh = (q) => q && q.high52w ? (((q.price - q.high52w) / q.high52w) * 100).toFixed(1) : null;

    const payload = {
      ts: Date.now(),
      sp500:  { ...sp,  pctFromHigh: pctFromHigh(sp),  ma50dist: sp && sp.ma50 ? (((sp.price - sp.ma50) / sp.ma50)*100).toFixed(1) : null },
      nasdaq: { ...nq,  pctFromHigh: pctFromHigh(nq) },
      vix:    { ...vix },
      dxy:    { ...dxy },
      eurusd: { ...eur },
      usdjpy: { ...jpy },
      cnhusd: { ...cnh },
      ust10y: { ...t10 },
      ust2y:  { ...t2 },
      spread2y10y: spread,
      wti:    { ...wti },
      brent:  { ...brent },
      gold:   { ...gold, pctFromHigh: pctFromHigh(gold) },
      copper: { ...copper },
    };

    res.status(200).json({ ok: true, data: payload });

  } catch (err) {
    console.error('markets.js error:', err.message);
    res.status(500).json({ ok: false, error: err.message });
  }
}
