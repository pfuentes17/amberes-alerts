// /api/markets.js — Yahoo Finance con cookie+crumb para evitar 401/429

const SYMBOLS = ['^GSPC','^IXIC','^VIX','EURUSD=X','JPY=X','CNH=X','^TNX','^IRX','CL=F','BZ=F','GC=F','HG=F','DX-Y.NYB'];
const KEY_MAP = {'^GSPC':'sp500','^IXIC':'nasdaq','^VIX':'vix','EURUSD=X':'eurusd','JPY=X':'usdjpy','CNH=X':'cnhusd','^TNX':'ust10y','^IRX':'ust2y','CL=F':'wti','BZ=F':'brent','GC=F':'gold','HG=F':'copper','DX-Y.NYB':'dxy'};

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

async function getCrumb() {
  // Step 1: get cookies from Yahoo Finance
  const r1 = await fetch('https://finance.yahoo.com/', {
    headers: { 'User-Agent': UA, 'Accept': 'text/html', 'Accept-Language': 'en-US,en;q=0.9' },
    redirect: 'follow'
  });
  const cookies = (r1.headers.get('set-cookie') || '').split(',').map(c => c.split(';')[0].trim()).filter(Boolean).join('; ');

  // Step 2: get crumb
  const r2 = await fetch('https://query1.finance.yahoo.com/v1/test/getcrumb', {
    headers: { 'User-Agent': UA, 'Cookie': cookies }
  });
  const crumb = await r2.text();
  return { crumb: crumb.trim(), cookies };
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=120');

  try {
    const { crumb, cookies } = await getCrumb();

    const syms = SYMBOLS.join(',');
    const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(syms)}&crumb=${encodeURIComponent(crumb)}&fields=regularMarketPrice,regularMarketChangePercent,regularMarketPreviousClose,fiftyTwoWeekHigh,fiftyTwoWeekLow,fiftyDayAverage`;

    const qRes = await fetch(url, {
      headers: { 'User-Agent': UA, 'Cookie': cookies, 'Accept': 'application/json', 'Referer': 'https://finance.yahoo.com/' }
    });

    if (!qRes.ok) {
      const txt = await qRes.text();
      throw new Error(`Yahoo quote HTTP ${qRes.status}: ${txt.slice(0,200)}`);
    }

    const json = await qRes.json();
    const quotes = json?.quoteResponse?.result || [];

    const bySymbol = {};
    for (const q of quotes) bySymbol[q.symbol] = q;

    const parse = (sym) => {
      const q = bySymbol[sym];
      if (!q) return null;
      const price = q.regularMarketPrice;
      const high52w = q.fiftyTwoWeekHigh;
      return {
        price,
        chgPct: q.regularMarketChangePercent != null ? parseFloat(q.regularMarketChangePercent.toFixed(2)) : null,
        prev:   q.regularMarketPreviousClose,
        high52w,
        low52w: q.fiftyTwoWeekLow,
        ma50:   q.fiftyDayAverage,
        pctFromHigh: (price && high52w) ? parseFloat((((price - high52w) / high52w) * 100).toFixed(1)) : null,
      };
    };

    const data = {};
    for (const [sym, key] of Object.entries(KEY_MAP)) data[key] = parse(sym);

    const t10 = data.ust10y?.price;
    const t2  = data.ust2y?.price;
    data.spread2y10y = (t10 && t2) ? parseInt(((t10 - t2) * 100).toFixed(0)) : null;

    res.status(200).json({ ok: true, data });

  } catch (err) {
    console.error('markets error:', err.message);
    res.status(500).json({ ok: false, error: err.message });
  }
}
