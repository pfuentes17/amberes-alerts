// /api/markets.js — Finnhub (primary) + Frankfurter FX + fallback

const FINNHUB_KEY = process.env.FINNHUB_KEY;

// Finnhub symbol map
const FINNHUB_SYMBOLS = {
  sp500:  'SPY',     // ETF proxy — Finnhub free tier: US stocks/ETFs
  nasdaq: 'QQQ',
  vix:    'VIXY',    // Volatility ETF proxy
  wti:    'USO',
  gold:   'GLD',
  copper: 'COPX',
  dxy:    'UUP',
};

// Forex symbols on Finnhub: OANDA:USD_JPY etc.
const FINNHUB_FX = {
  eurusd: 'OANDA:EUR_USD',
  usdjpy: 'OANDA:USD_JPY',
  cnhusd: 'OANDA:USD_CNH', // will invert
};

// UST yields via FRED (already configured)
const FRED_KEY = process.env.FRED_API_KEY;

async function fetchFinnhubQuote(symbol) {
  const r = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${FINNHUB_KEY}`, {
    signal: AbortSignal.timeout(5000)
  });
  if (!r.ok) throw new Error(`Finnhub ${symbol}: HTTP ${r.status}`);
  const d = await r.json();
  if (!d.c) throw new Error(`Finnhub ${symbol}: no data`);
  return { price: d.c, chgPct: d.dp ?? null, prev: d.pc, high52w: d['52w'] ? null : null };
}

async function fetchFinnhubForex(symbol) {
  const r = await fetch(`https://finnhub.io/api/v1/forex/rates?base=USD&token=${FINNHUB_KEY}`, {
    signal: AbortSignal.timeout(5000)
  });
  if (!r.ok) throw new Error(`Finnhub forex HTTP ${r.status}`);
  const d = await r.json();
  return d.quote || {};
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
  const r = await fetch(`https://api.stlouisfed.org/fred/series/observations?series_id=${series}&api_key=${FRED_KEY}&limit=1&sort_order=desc&file_type=json`, {
    signal: AbortSignal.timeout(5000)
  });
  if (!r.ok) return null;
  const d = await r.json();
  const val = d.observations?.[0]?.value;
  return val && val !== '.' ? parseFloat(val) : null;
}

// Fallback snapshot (today's values from briefing)
const FALLBACK = {"sp500":{"price":7511.35,"chgPct":-0.57,"high52w":7620.9,"low52w":5943.23},"nasdaq":{"price":21727.69,"chgPct":-0.82},"vix":{"price":16.2,"chgPct":-7.43},"eurusd":{"price":1.1594,"chgPct":0.31},"usdjpy":{"price":145.8,"chgPct":-0.48},"cnhusd":{"price":7.24,"chgPct":0.12},"ust10y":{"price":4.97,"chgPct":-0.30},"ust2y":{"price":4.03,"chgPct":-0.25},"wti":{"price":76.4,"chgPct":-2.6},"brent":{"price":80.1,"chgPct":-2.3},"gold":{"price":4300,"chgPct":0.9,"high52w":4430,"low52w":2280},"copper":{"price":4.82,"chgPct":-1.2},"dxy":{"price":101.4,"chgPct":-0.4},"spread2y10y":94,"_fallback":true};

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=300');

  try {
    // Parallel: Finnhub stocks + FX + FRED yields
    const [fxResult, t10Result, t2Result] = await Promise.allSettled([
      fetchFrankfurter(),
      fetchFred('DGS10'),
      fetchFred('DGS2'),
    ]);

    // Finnhub: fetch all stock/ETF quotes in parallel (60 req/min free tier)
    const stockResults = await Promise.allSettled(
      Object.entries(FINNHUB_SYMBOLS).map(([key, sym]) =>
        fetchFinnhubQuote(sym).then(q => ({ key, q }))
      )
    );

    const data = { ...FALLBACK, _fallback: false };

    // Apply Finnhub stock data
    let finnhubOk = 0;
    for (const r of stockResults) {
      if (r.status === 'fulfilled') {
        const { key, q } = r.value;
        data[key] = { ...data[key], ...q };
        finnhubOk++;
      }
    }

    // Apply Frankfurter FX (most reliable free FX source)
    if (fxResult.status === 'fulfilled') {
      const rates = fxResult.value.rates;
      if (rates?.EUR) {
        const price = parseFloat((1 / rates.EUR).toFixed(4));
        const prev = data.eurusd?.prev;
        data.eurusd = { price, chgPct: prev ? parseFloat((((price-prev)/prev)*100).toFixed(2)) : null, source: 'live' };
      }
      if (rates?.JPY) {
        data.usdjpy = { price: parseFloat(rates.JPY.toFixed(2)), chgPct: data.usdjpy?.chgPct ?? null, source: 'live' };
      }
      if (rates?.CNY) {
        data.cnhusd = { price: parseFloat(rates.CNY.toFixed(4)), chgPct: data.cnhusd?.chgPct ?? null, source: 'live' };
      }
    }

    // Apply FRED yields
    if (t10Result.status === 'fulfilled' && t10Result.value) {
      data.ust10y = { ...data.ust10y, price: t10Result.value, source: 'live' };
    }
    if (t2Result.status === 'fulfilled' && t2Result.value) {
      data.ust2y = { ...data.ust2y, price: t2Result.value, source: 'live' };
    }

    // Spread 2Y-10Y
    const t10 = data.ust10y?.price;
    const t2  = data.ust2y?.price;
    if (t10 && t2) data.spread2y10y = parseInt(((t10 - t2) * 100).toFixed(0));

    if (finnhubOk === 0 && fxResult.status !== 'fulfilled') {
      data._fallback = true;
    }

    res.status(200).json({ ok: true, data });

  } catch (err) {
    console.error('markets fatal:', err.message);
    res.status(200).json({ ok: true, data: { ...FALLBACK, _fallback: true } });
  }
}
