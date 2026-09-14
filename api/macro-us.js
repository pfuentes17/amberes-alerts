const KEY = process.env.FRED_API_KEY;
const BASE = 'https://api.stlouisfed.org/fred/series/observations';

// Reintenta cada serie hasta 3 veces con backoff -- FRED devuelve 502/timeout de forma
// intermitente cuando se piden varias series en simultaneo desde Vercel. Cada intento tiene
// timeout propio de 10s (antes 8s, sin reintento -- una sola serie lenta tiraba abajo TODO
// el endpoint porque se usaba Promise.all).
async function fred(id, limit=14, retries=3){
  let lastErr;
  for(let attempt=0; attempt<retries; attempt++){
    try{
      const r=await fetch(`${BASE}?series_id=${id}&api_key=${KEY}&file_type=json&sort_order=desc&limit=${limit}`,{signal:AbortSignal.timeout(10000)});
      if(!r.ok) throw new Error(`FRED ${id}: ${r.status}`);
      const j=await r.json();
      return (j.observations||[]).reverse().filter(o=>o.value!=='.');
    }catch(e){
      lastErr = e;
      if(attempt < retries-1) await new Promise(res=>setTimeout(res, 500*(attempt+1)));
    }
  }
  throw lastErr;
}
function yoy(obs){const r=[];for(let i=12;i<obs.length;i++){const c=parseFloat(obs[i].value),p=parseFloat(obs[i-12].value);if(!isNaN(c)&&!isNaN(p)&&p)r.push({date:obs[i].date,value:((c/p-1)*100).toFixed(1)});}return r;}
function mom(obs){const r=[];for(let i=1;i<obs.length;i++){const c=parseFloat(obs[i].value),p=parseFloat(obs[i-1].value);if(!isNaN(c)&&!isNaN(p)&&p)r.push({date:obs[i].date,value:((c/p-1)*100).toFixed(2)});}return r;}
const MES=['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const fmtM=d=>{const x=new Date(d+'T12:00:00Z');return MES[x.getUTCMonth()]+' '+String(x.getUTCFullYear()).slice(2);};
const fmtQ=d=>{const x=new Date(d+'T12:00:00Z');return `Q${Math.floor(x.getUTCMonth()/3)+1} ${String(x.getUTCFullYear()).slice(2)}`;};
const last=(a,n=12)=>a.slice(-n);
const fmt=a=>({l:a.map(o=>fmtM(o.date)),v:a.map(o=>parseFloat(o.value))});

// Series a traer, agrupadas por como se combinan despues. Cada entrada corre en su propio
// Promise.allSettled -- si una serie falla (incluso despues de los reintentos), el resto
// de las series siguen entregandose normalmente en la respuesta.
const SERIES = {
  cpiL:  ()=>fred('CPIAUCSL',26),  cpiCL: ()=>fred('CPILFESL',26),
  pceL:  ()=>fred('PCEPI',26),     pceCL: ()=>fred('PCEPILFE',26),
  ppiL:  ()=>fred('PPIACO',26),    ppiCL: ()=>fred('PPICOR',26),
  gdp:   ()=>fred('A191RL1Q225SBEA',10),
  ur:    ()=>fred('UNRATE',12),
  nfp:   ()=>fred('PAYEMS',13),
  fed:   ()=>fred('FEDFUNDS',20),
  claims:()=>fred('IC4WSA',16),
  trade: ()=>fred('BOPGSTB',14),
};

module.exports=async function(req,res){
  const keys = Object.keys(SERIES);
  const settled = await Promise.allSettled(keys.map(k=>SERIES[k]()));
  const data = {};
  const errors = {};
  settled.forEach((s,i)=>{
    if(s.status==='fulfilled') data[keys[i]] = s.value;
    else errors[keys[i]] = s.reason?.message || String(s.reason);
  });

  const out = {ok:true};
  if(Object.keys(errors).length) out.partialErrors = errors;

  if(data.gdp) out.gdp = {l:data.gdp.map(o=>fmtQ(o.date)),v:data.gdp.map(o=>parseFloat(o.value))};
  if(data.cpiL){
    out.cpi = fmt(last(yoy(data.cpiL)));
    out.cpiMoM = last(mom(data.cpiL)).map(o=>parseFloat(o.value));
  }
  if(data.cpiCL) out.cpiCore = last(yoy(data.cpiCL)).map(o=>parseFloat(o.value));
  if(data.pceL){
    out.pce = fmt(last(yoy(data.pceL)));
    out.pceMoM = last(mom(data.pceL)).map(o=>parseFloat(o.value));
  }
  if(data.pceCL) out.pceCore = last(yoy(data.pceCL)).map(o=>parseFloat(o.value));
  if(data.ppiL){
    out.ppi = fmt(last(yoy(data.ppiL)));
    out.ppiMoM = last(mom(data.ppiL)).map(o=>parseFloat(o.value));
  }
  if(data.ppiCL) out.ppiCore = last(yoy(data.ppiCL)).map(o=>parseFloat(o.value));
  if(data.ur) out.ur = fmt(last(data.ur));
  if(data.nfp){
    const nfpChg=[];for(let i=1;i<data.nfp.length;i++)nfpChg.push({date:data.nfp[i].date,value:Math.round(parseFloat(data.nfp[i].value)-parseFloat(data.nfp[i-1].value))});
    out.nfp = {l:last(nfpChg).map(o=>fmtM(o.date)),v:last(nfpChg).map(o=>o.value)};
  }
  if(data.fed){
    const fedD=data.fed.filter((o,i)=>i===0||o.value!==data.fed[i-1].value);
    out.fed = {l:fedD.map(o=>fmtM(o.date)),v:fedD.map(o=>parseFloat(o.value))};
  }
  if(data.claims) out.claims = fmt(last(data.claims,16));
  if(data.trade) out.trade = {l:last(data.trade,12).map(o=>fmtM(o.date)),v:last(data.trade,12).map(o=>Math.round(parseFloat(o.value)/1000))};

  // Si TODAS las series fallaron no hay nada util que devolver -- ahi si es un error real.
  if(Object.keys(errors).length === keys.length){
    res.status(502).json({ok:false,error:'Todas las series de FRED fallaron',details:errors});
    return;
  }

  res.setHeader('Cache-Control','public,max-age=1800');res.setHeader('Access-Control-Allow-Origin','*');
  res.status(200).json(out);
};
