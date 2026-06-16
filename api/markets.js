// /api/markets.js — Live market data via Yahoo Finance (single batch request)

const SYMBOLS_MAP = {
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

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=120');

  try {
    const syms = Object.values(SYMBOLS_MAP).join(',');
    const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(syms)}&fields=regularMarketPrice,regularMarketChangePercent,regularMarketPreviousClose,fiftyTwoWeekHigh,fiftyTwoWeekLow,fiftyDayAverage,regularMarketTime`;

    const yRes = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://finance.yahoo.com/',
        'Origin': 'https://finance.yahoo.com',
        'Accept-Language': 'en-US,en;q=0.9',
      }
    });

    if (!yRes.ok) {
      const txt = await yRes.text();
      throw new Error(`Yahoo HTTP ${yRes.status}: ${txt.slice(0, 200)}`);
    }

    const json = await yRes.json();
    const quotes = json?.quoteResponse?.result || [];

    // Build lookup by symbol
    const bySymbol = {};
    for (const q of quotes) {
      bySymbol[q.symbol] = q;
    }

    const parse = (sym) => {
      const q = bySymbol[sym];
      if (!q) return null;
      return {
        price:   q.regularMarketPrice,
        chgPct:  q.regularMarketChangePercent != null ? parseFloat(q.regularMarketChangePercent.toFixed(2)) : null,
        prev:    q.regularMarketPreviousClose,
        high52w: q.fiftyTwoWeekHigh,
        low52w:  q.fiftyTwoWeekLow,
        ma50:    q.fiftyDayAverage,
        ts:      q.regularMarketTime,
      };
    };

    const sp    = parse('^GSPC');
    const t10   = parse('^TNX');
    const t2    = parse('^IRX');
    const gold  = parse('GC=F');

    if (sp?.price && sp?.high52w) sp.pctFromHigh = parseFloat((((sp.price - sp.high52w) / sp.high52w) * 100).toFixed(1));
    if (gold?.price && gold?.high52w) gold.pctFromHigh = parseFloat((((gold.price - gold.high52w) / gold.high52w) * 100).toFixed(1));

    const data = {
      sp500:        sp,
      nasdaq:       parse('^IXIC'),
      vix:          parse('^VIX'),
      eurusd:       parse('EURUSD=X'),
      usdjpy:       parse('JPY=X'),
      cnhusd:       parse('CNH=X'),
      ust10y:       t10,
      ust2y:        t2,
      wti:          parse('CL=F'),
      brent:        parse('BZ=F'),
      gold:         gold,
      copper:       parse('HG=F'),
      dxy:          parse('DX-Y.NYB'),
      spread2y10y:  (t10?.price && t2?.price) ? parseInt(((t10.price - t2.price) * 100).toFixed(0)) : null,
    };

    res.status(200).json({ ok: true, data });

  } catch (err) {
    console.error('markets error:', err.message);
    res.status(500).json({ ok: false, error: err.message });
  }
}
