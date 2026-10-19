// Independent research implementation. No Quandora code or private datasets.
export function parseCSV(text) {
  const rows = text.trim().replace(/^\uFEFF/, '').split(/\r?\n/).map(s => s.split(',').map(x => x.trim()));
  if (rows.shift()?.join(',').toLowerCase() !== 'date,symbol,close') throw Error('CSV header must be date,symbol,close');
  if (rows.length > 100000) throw Error('Maximum 100,000 rows per import.');
  const seen = new Set(); const byDate = new Map();
  for (const [date, symbol, raw, ...extra] of rows) {
    const price = Number(raw);
    if (extra.length || !/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0,10)!==date || !/^[A-Za-z0-9._-]{1,20}$/.test(symbol) || !Number.isFinite(price) || price <= 0) throw Error('Invalid row. Use an ISO date, a symbol, and a positive close.');
    const key = date + ':' + symbol;
    if (seen.has(key)) throw Error('Duplicate date/symbol: ' + key);
    seen.add(key); if (!byDate.has(date)) byDate.set(date, {}); byDate.get(date)[symbol] = price;
  }
  const dates = [...byDate.keys()].sort(); const symbols = [...new Set(rows.map(r=>r[1]))].sort();
  if (dates.length < 5 || symbols.length < 2 || symbols.length > 100) throw Error('Need at least 5 dates and 2–100 assets.');
  for (const date of dates) if (Object.keys(byDate.get(date)).length !== symbols.length) throw Error('Every date must contain every asset. Missing prices on ' + date);
  for (let i=1;i<dates.length;i++) if ((Date.parse(dates[i])-Date.parse(dates[i-1]))/86400000 !== 1) throw Error('This version requires consecutive daily bars, including weekends.');
  return {dates, symbols, prices: dates.map(d=>symbols.map(s=>byDate.get(d)[s]))};
}
export function sampleData(periods=400) {
  let seed=9127; const random=()=>{seed=(seed*16807)%2147483647;return seed/2147483647;};
  const symbols=['BTC','ETH','SOL','BNB','LINK','AVAX']; let prices=[42000,2200,95,310,15,35];
  const rows=['date,symbol,close'];
  for(let i=0;i<periods;i++) {const date=new Date(Date.UTC(2025,0,1+i)).toISOString().slice(0,10);prices=prices.map((p,j)=>p*Math.exp((random()-.49)*.055 + Math.sin(i/27+j)*.002));symbols.forEach((s,j)=>rows.push(`${date},${s},${prices[j].toFixed(6)}`));}
  return rows.join('\n');
}
export function validateConfig(data, config) {
  const {capital,lookback,feeBps,slippageBps,selection,mode}=config;
  if (!Number.isFinite(capital)||capital<100||capital>1e9) throw Error('Capital must be between $100 and $1 billion.');
  if (!Number.isInteger(lookback)||lookback<1||lookback>=data.dates.length-1) throw Error('Lookback must leave at least two evaluation bars.');
  if (!Number.isInteger(selection)||selection<1||selection>Math.floor(data.symbols.length/2)) throw Error('Assets per side must be between 1 and half the universe.');
  if (![feeBps,slippageBps].every(x=>Number.isFinite(x)&&x>=0&&x<=500)) throw Error('Costs must be 0–500 basis points.');
  if (!['momentum','reversal'].includes(mode)) throw Error('Unknown signal.');
}
export function targetWeights(data,config,index) {
  const rank=data.symbols.map((symbol,j)=>({j,symbol,score:data.prices[index][j]/data.prices[index-config.lookback][j]-1})).sort((a,b)=>b.score-a.score||a.symbol.localeCompare(b.symbol));
  if(config.mode==='reversal') rank.reverse();
  const weights=Array(data.symbols.length).fill(0);
  rank.slice(0,config.selection).forEach(x=>weights[x.j]=.5/config.selection);
  rank.slice(-config.selection).forEach(x=>weights[x.j]=-.5/config.selection);
  return weights;
}
export function createReplay(data,config) {
  validateConfig(data,config);
  return {index:config.lookback,equity:config.capital,quantities:Array(data.symbols.length).fill(0),curve:[{date:data.dates[config.lookback],equity:config.capital}],fills:[],status:'ready',config:{...config}};
}
export function advanceReplay(data,run) {
  if (run.status==='stopped'||run.status==='complete') throw Error('Replay is terminal. Create a new run.');
  if(run.index>=data.dates.length-1) {run.status='complete';return run;}
  const i=run.index, c=run.config, weights=targetWeights(data,c,i), current=data.prices[i], next=data.prices[i+1];
  let cost=0;const equityBefore=run.equity;
  const quantities=weights.map((w,j)=>w*equityBefore/current[j]);
  quantities.forEach((qty,j)=>{const delta=qty-run.quantities[j],notional=Math.abs(delta*current[j]);if(notional>1e-8){const fee=notional*(c.feeBps+c.slippageBps)/10000;cost+=fee;run.fills.push({date:data.dates[i],symbol:data.symbols[j],side:delta>0?'Buy':'Sell',quantity:Math.abs(delta),price:current[j],cost:fee});}});
  const pnl=quantities.reduce((sum,q,j)=>sum+q*(next[j]-current[j]),0);
  run.equity=equityBefore-cost+pnl;run.quantities=quantities;run.index++;run.curve.push({date:data.dates[run.index],equity:run.equity});
  run.status=run.equity<=0?'stopped':run.index===data.dates.length-1?'complete':'running';
  return run;
}
export function metrics(curve,capital) {
  let peak=capital,drawdown=0;const returns=[];
  curve.forEach((p,i)=>{peak=Math.max(peak,p.equity);drawdown=Math.max(drawdown,1-p.equity/peak);if(i) returns.push(p.equity/curve[i-1].equity-1);});
  const mean=returns.reduce((a,b)=>a+b,0)/(returns.length||1),variance=returns.reduce((a,b)=>a+(b-mean)**2,0)/Math.max(1,returns.length-1);
  return {totalReturn:curve.at(-1).equity/capital-1,maxDrawdown:drawdown,sharpe:variance>0?mean/Math.sqrt(variance)*Math.sqrt(365):null,bars:returns.length};
}
export function backtest(data,config) {
  const run=createReplay(data,config);
  while(!['complete','stopped'].includes(run.status)) advanceReplay(data,run);
  return {...run,metrics:metrics(run.curve,config.capital)};
}
