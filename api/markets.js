// /api/markets.js — Live market data via Yahoo Finance v8/chart
// Fetches one symbol at a time in parallel, uses Referer header to bypass 401

const SYMBOLS = {
  sp500:   '^GSPC',
  nasdaq:  '^IXIC',
  vix:     '^VIX',
  eurusd:  'EURUSD=X',
  usdjpy:  'JPY=X',
  cnhusd:  'CNH=X',
  ust10y:  '^TNX',
  ust2y:   '^IRX',
  wti:     'CL=F',
  brent:   'BZ=F',
  gold:    'GC=F',
  copper:  'HG=F',
  dxy:     'DX-Y.NYB',
};

const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Referer': 'https://finance.yahoo.com',
  'Accept': 'application/json',
};

async function fetchChart(symbol) {
  const encoded = encodeURIComponent(symbol);
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encoded}?interval=1d&range=5d&includePrePost=false`;
  const res = await fetch(url, { headers: HEADERS });
  if (!res.ok) throw new Error(`${symbol}: HTTP ${res.status}`);
  const json = await res.json();
  const meta = json?.chart?.result?.[0]?.meta;
  if (!meta) throw new Error(`${symbol}: no meta`);
  return meta;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=120');

  try {
    const entries = Object.entries(SYMBOLS);
    const results = await Promise.allSettled(
      entries.map(([key, sym]) => fetchChart(sym).then(m => ({ key, m })))
    );

    const byKey = {};
    for (const r of results) {
      if (r.status === 'fulfilled') {
        const { key, m } = r.value;
        const prev = m.chartPreviousClose || m.previousClose;
        const price = m.regularMarketPrice;
        const chgPct = prev ? ((price - prev) / prev) * 100 : null;
        byKey[key] = {
          price,
          chgPct: chgPct ? parseFloat(chgPct.toFixed(2)) : null,
          prev,
          high52w: m.fiftyTwoWeekHigh,
          low52w:  m.fiftyTwoWeekLow,
          ts: m.regularMarketTime,
        };
      }
    }

    // Enrich sp500 with MA50 approx (unavailable in chart meta, skip or set null)
    if (byKey.sp500 && byKey.sp500.high52w) {
      byKey.sp500.pctFromHigh = parseFloat((((byKey.sp500.price - byKey.sp500.high52w) / byKey.sp500.high52w) * 100).toFixed(1));
    }
    if (byKey.gold && byKey.gold.high52w) {
      byKey.gold.pctFromHigh = parseFloat((((byKey.gold.price - byKey.gold.high52w) / byKey.gold.high52w) * 100).toFixed(1));
    }

    // Spread 2Y-10Y in bps
    const t10 = byKey.ust10y?.price;
    const t2  = byKey.ust2y?.price;
    byKey.spread2y10y = (t10 && t2) ? parseInt(((t10 - t2) * 100).toFixed(0)) : null;

    res.status(200).json({ ok: true, data: byKey });

  } catch (err) {
    console.error('markets.js error:', err.message);
    res.status(500).json({ ok: false, error: err.message });
  }
}
