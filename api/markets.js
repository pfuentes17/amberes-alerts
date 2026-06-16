// /api/markets.js — Multi-source: Yahoo Finance + Frankfurter FX fallback

const SYMBOLS = ['^GSPC','^IXIC','^VIX','EURUSD=X','JPY=X','CNH=X','^TNX','^IRX','CL=F','BZ=F','GC=F','HG=F','DX-Y.NYB'];
const KEY_MAP = {'^GSPC':'sp500','^IXIC':'nasdaq','^VIX':'vix','EURUSD=X':'eurusd','JPY=X':'usdjpy','CNH=X':'cnhusd','^TNX':'ust10y','^IRX':'ust2y','CL=F':'wti','BZ=F':'brent','GC=F':'gold','HG=F':'copper','DX-Y.NYB':'dxy'};

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

// Static fallback snapshot (updated when possible)
const FALLBACK = {"sp500":{"price":7511.35,"chgPct":-0.57,"high52w":7620.9,"low52w":5943.23},"nasdaq":{"price":21727.69,"chgPct":-0.82},"vix":{"price":16.2,"chgPct":-7.43},"eurusd":{"price":1.1594,"chgPct":0.31},"usdjpy":{"price":145.8,"chgPct":-0.48},"cnhusd":{"price":7.24,"chgPct":0.12},"ust10y":{"price":4.97,"chgPct":-0.30},"ust2y":{"price":4.03,"chgPct":-0.25},"wti":{"price":76.4,"chgPct":-2.6},"brent":{"price":80.1,"chgPct":-2.3},"gold":{"price":4300,"chgPct":0.9,"high52w":4430,"low52w":2280},"copper":{"price":4.82,"chgPct":-1.2},"dxy":{"price":101.4,"chgPct":-0.4},"spread2y10y":94,"_fallback":true};

async function fetchYahoo() {
  const syms = SYMBOLS.join(',');
  const url = `https://query2.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(syms)}&fields=regularMarketPrice,regularMarketChangePercent,regularMarketPreviousClose,fiftyTwoWeekHigh,fiftyTwoWeekLow,fiftyDayAverage`;
  const r = await fetch(url, {
    headers: { 'User-Agent': UA, 'Referer': 'https://finance.yahoo.com/', 'Accept': 'application/json', 'Accept-Language': 'en-US,en;q=0.9' },
    signal: AbortSignal.timeout(6000)
  });
  if (!r.ok) throw new Error(`Yahoo HTTP ${r.status}`);
  const json = await r.json();
  const quotes = json?.quoteResponse?.result;
  if (!quotes?.length) throw new Error('No quotes returned');
  return quotes;
}

async function fetchFX() {
  // Frankfurter: free FX API, ECB rates, no key needed
  const r = await fetch('https://api.frankfurter.app/latest?from=USD&to=EUR,JPY,CNY', {
    signal: AbortSignal.timeout(4000)
  });
  if (!r.ok) throw new Error('Frankfurter error');
  return r.json();
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  // 5-minute CDN cache → Yahoo Finance called at most once/5min
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=600');

  try {
    const [yahooResult, fxResult] = await Promise.allSettled([fetchYahoo(), fetchFX()]);

    let data = {};
    let usingFallback = false;

    if (yahooResult.status === 'fulfilled') {
      // Parse Yahoo quotes
      const bySymbol = {};
      for (const q of yahooResult.value) bySymbol[q.symbol] = q;

      for (const [sym, key] of Object.entries(KEY_MAP)) {
        const q = bySymbol[sym];
        if (!q) continue;
        const price = q.regularMarketPrice;
        const high52w = q.fiftyTwoWeekHigh;
        data[key] = {
          price,
          chgPct: q.regularMarketChangePercent != null ? parseFloat(q.regularMarketChangePercent.toFixed(2)) : null,
          prev:   q.regularMarketPreviousClose,
          high52w,
          low52w: q.fiftyTwoWeekLow,
          ma50:   q.fiftyDayAverage,
          pctFromHigh: (price && high52w) ? parseFloat((((price - high52w) / high52w) * 100).toFixed(1)) : null,
        };
      }
    } else {
      // Yahoo failed — use fallback data
      console.warn('Yahoo failed:', yahooResult.reason?.message);
      data = { ...FALLBACK };
      usingFallback = true;
    }

    // Override FX with Frankfurter if available (more reliable)
    if (fxResult.status === 'fulfilled') {
      const rates = fxResult.value.rates;
      if (rates?.EUR) {
        const prev = data.eurusd?.prev;
        const price = parseFloat((1 / rates.EUR).toFixed(4));
        data.eurusd = { price, chgPct: prev ? parseFloat((((price-prev)/prev)*100).toFixed(2)) : data.eurusd?.chgPct ?? null, prev, source: 'frankfurter' };
      }
      if (rates?.JPY) {
        const price = parseFloat(rates.JPY.toFixed(2));
        data.usdjpy = { price, chgPct: data.usdjpy?.chgPct ?? null, source: 'frankfurter' };
      }
    }

    // Compute spread
    const t10 = data.ust10y?.price;
    const t2  = data.ust2y?.price;
    if (t10 && t2) data.spread2y10y = parseInt(((t10 - t2) * 100).toFixed(0));

    if (usingFallback) data._fallback = true;

    res.status(200).json({ ok: true, data });

  } catch (err) {
    console.error('markets fatal:', err.message);
    res.status(200).json({ ok: true, data: FALLBACK });
  }
}
