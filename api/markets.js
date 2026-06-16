// /api/markets.js — Live market data via Yahoo Finance v8/chart

const SYMBOLS = {
  sp500:   '^GSPC',
  nasdaq:  '^IXIC',
  vix:     '^VIX',
  eurusd:  'EURUSD=X',
  usdjpy:  'JPY=X',
  cnhusd:  'CNH=X',
  ust10y:  '^TNX',
  ust2y:   '^IRX',
  wti:     'CL-F',
  brent:   'BZ-F',
  gold:    'GC-F',
  copper:  'HG-F',
  dxy:     'DX-Y.NYB',
};

// Yahoo Finance uses %3D for = in query params
const YF_SYMBOLS = {
  sp500:   '%5EGSPC',
  nasdaq:  '%5EIXIC',
  vix:     '%5EVIX',
  eurusd:  'EURUSD%3DX',
  usdjpy:  'JPY%3DX',
  cnhusd:  'CNH%3DX',
  ust10y:  '%5ETNX',
  ust2y:   '%5EIRX',
  wti:     'CL%3DF',
  brent:   'BZ%3DF',
  gold:    'GC%3DF',
  copper:  'HG%3DF',
  dxy:     'DX-Y.NYB',
};

const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Accept': 'application/json, text/plain, */*',
  'Accept-Language': 'en-US,en;q=0.9',
  'Referer': 'https://finance.yahoo.com/',
  'Origin': 'https://finance.yahoo.com',
};

async function fetchOne(key, encodedSym) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodedSym}?interval=1d&range=5d`;
  const res = await fetch(url, { headers: HEADERS });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status} for ${key}: ${text.slice(0, 100)}`);
  }
  const json = await res.json();
  const meta = json?.chart?.result?.[0]?.meta;
  if (!meta) throw new Error(`No meta for ${key}`);
  return { key, meta };
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=120');

  const entries = Object.entries(YF_SYMBOLS);
  const results = await Promise.allSettled(
    entries.map(([key, sym]) => fetchOne(key, sym))
  );

  const errors = [];
  const byKey = {};

  for (const r of results) {
    if (r.status === 'fulfilled') {
      const { key, meta: m } = r.value;
      const prev = m.chartPreviousClose ?? m.previousClose ?? null;
      const price = m.regularMarketPrice;
      const chgPct = prev ? parseFloat((((price - prev) / prev) * 100).toFixed(2)) : null;
      byKey[key] = {
        price,
        chgPct,
        prev,
        high52w: m.fiftyTwoWeekHigh ?? null,
        low52w:  m.fiftyTwoWeekLow  ?? null,
        ts: m.regularMarketTime ?? null,
      };
      if (byKey[key].high52w) {
        byKey[key].pctFromHigh = parseFloat((((price - byKey[key].high52w) / byKey[key].high52w) * 100).toFixed(1));
      }
    } else {
      errors.push(r.reason?.message || String(r.reason));
    }
  }

  // Spread 2Y-10Y in bps
  const t10 = byKey.ust10y?.price;
  const t2  = byKey.ust2y?.price;
  byKey.spread2y10y = (t10 && t2) ? parseInt(((t10 - t2) * 100).toFixed(0)) : null;

  res.status(200).json({ ok: true, data: byKey, errors: errors.length ? errors : undefined });
}
