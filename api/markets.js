// /api/markets.js
// Sources:
//   - Finnhub (free US stocks): chgPct for S&P, NASDAQ, Gold, WTI proxies
//   - Frankfurter: live FX (EUR/USD, USD/JPY, CNH/USD)
//   - FRED: UST yields 10Y + 2Y (daily)
//   - Fallback snapshot: absolute price levels updated in briefing.json

const KEY = process.env.FINNHUB_KEY;
const FRED_KEY = process.env.FRED_API_KEY;

// ETF proxies — only chgPct is used; absolute prices come from fallback
const ETF_MAP = {
  sp500:  'SPY',
  nasdaq: 'QQQ',
  gold:   'GLD',
  wti:    'USO',
  dxy:    'UUP',
  copper: 'COPX',
};

// Static snapshot (absolute price levels from today's briefing)
// These get updated daily by the briefing agent
const BASELINE = {
  sp500:  { price:7511.35, high52w:7620.9, low52w:5943.23 },
  nasdaq: { price:21727.69 },
  vix:    { price:16.2, chgPct:-7.43 }, // VIX: no ETF proxy available on free
  eurusd: { price:1.1594 },
  usdjpy: { price:145.8 },
  cnhusd: { price:7.24 },
  ust10y: { price:4.97 },
  ust2y:  { price:4.03 },
  wti:    { price:76.4, low52w:55, high52w:97 },
  brent:  { price:80.1 },
  gold:   { price:4300, high52w:4430, low52w:2280 },
  copper: { price:4.82 },
  dxy:    { price:101.4 },
};

async function fetchFinnhub(symbol) {
  const r = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${KEY}`, {
    signal: AbortSignal.timeout(5000)
  });
  if (!r.ok) throw new Error(`Finnhub ${symbol} HTTP ${r.status}`);
  const d = await r.json();
  if (d.error || !d.dp == null) throw new Error(`Finnhub ${symbol}: ${d.error || 'no data'}`);
  return { chgPct: parseFloat(d.dp.toFixed(2)), prev: d.pc, current: d.c };
}

async function fetchFrankfurter() {
  const r = await fetch('https://api.frankfurter.app/latest?from=USD&to=EUR,JPY,CNY', {
    signal: AbortSignal.timeout(5000)
  });
  if (!r.ok) throw new Error('Frankfurter error');
  return r.json();
}

async function fetchFred(series) {
  if (!FRED_KEY) return null;
  const r = await fetch(
    `https://api.stlouisfed.org/fred/series/observations?series_id=${series}&api_key=${FRED_KEY}&limit=1&sort_order=desc&file_type=json`,
    { signal: AbortSignal.timeout(5000) }
  );
  if (!r.ok) return null;
  const d = await r.json();
  const val = d.observations?.[0]?.value;
  return val && val !== '.' ? parseFloat(val) : null;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=300');

  // Start with baseline prices
  const data = {};
  for (const [k, v] of Object.entries(BASELINE)) {
    data[k] = { ...v };
  }
  data._fallback = false;

  // Parallel fetches
  const [fxR, t10R, t2R] = await Promise.allSettled([
    fetchFrankfurter(),
    fetchFred('DGS10'),
    fetchFred('DGS2'),
  ]);

  const etfResults = await Promise.allSettled(
    Object.entries(ETF_MAP).map(([key, sym]) =>
      fetchFinnhub(sym).then(q => ({ key, q }))
    )
  );

  // Apply Finnhub ETF change%
  let finhubOk = 0;
  for (const r of etfResults) {
    if (r.status === 'fulfilled') {
      const { key, q } = r.value;
      data[key] = { ...data[key], chgPct: q.chgPct, _live: true };
      finhubOk++;
    }
  }

  // Apply live FX (Frankfurter)
  if (fxR.status === 'fulfilled') {
    const rates = fxR.value.rates;
    if (rates?.EUR) {
      const price = parseFloat((1 / rates.EUR).toFixed(4));
      const prev = price / (1 + (data.eurusd.chgPct || 0) / 100);
      data.eurusd = { price, chgPct: data.eurusd.chgPct ?? null, _live: true };
    }
    if (rates?.JPY) {
      data.usdjpy = { price: parseFloat(rates.JPY.toFixed(2)), chgPct: data.usdjpy.chgPct ?? null, _live: true };
    }
    if (rates?.CNY) {
      data.cnhusd = { price: parseFloat(rates.CNY.toFixed(4)), chgPct: data.cnhusd.chgPct ?? null, _live: true };
    }
  }

  // Apply FRED yields
  if (t10R.status === 'fulfilled' && t10R.value) {
    const price = t10R.value;
    const prev = data.ust10y.price;
    data.ust10y = { ...data.ust10y, price, chgPct: prev ? parseFloat((((price-prev)/prev)*100).toFixed(2)) : null, _live: true };
  }
  if (t2R.status === 'fulfilled' && t2R.value) {
    const price = t2R.value;
    const prev = data.ust2y.price;
    data.ust2y = { ...data.ust2y, price, chgPct: prev ? parseFloat((((price-prev)/prev)*100).toFixed(2)) : null, _live: true };
  }

  // Spread
  const t10 = data.ust10y?.price;
  const t2  = data.ust2y?.price;
  if (t10 && t2) data.spread2y10y = parseInt(((t10 - t2) * 100).toFixed(0));

  if (finhubOk === 0) data._fallback = true;

  res.status(200).json({ ok: true, data });
}
