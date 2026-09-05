/* 실제 과거 회차로 병렬 3방식 대조 (v18)

   무엇을 하나
     lotto_history.json 의 실제 당첨번호로, 회차마다 **그 직전 데이터만** 써서
     세 방식(축3×2 / 축2×3 / 축1×6)이 몇 개나 맞혔는지 센다.
     ★ 미래 정보 차단 — N회차를 채점할 때 쓰는 재료는 N-1 회차까지다.

   왜 '같은 줄 수' 로도 보나
     방식마다 나오는 줄 수가 다르다(축 11개면 165 / 55 / 11).
     줄이 많으면 당연히 더 맞으므로, 앞에서 같은 줄 수만 잘라낸 기준도 함께 낸다.

   실행 (이 폴더에서):
     node backtest_par_modes.mjs                 # 최근 100회차
     node backtest_par_modes.mjs --rounds=300    # 최근 300회차
     node backtest_par_modes.mjs --base=30       # 순위 계산에 쓸 직전 회차 수
*/
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';

async function loadChromium() {
  try { return (await import('playwright')).chromium; } catch (_) {}
  /* 이 저장소는 공개다 — 개인 PC 경로를 적지 않는다.
     playwright 가 다른 폴더에 깔려 있으면 PW_DIR 로 알려준다.
       예) PW_DIR="D:/proj/node_modules/playwright/index.mjs" node verify_par_modes.mjs */
  const p = process.env.PW_DIR;
  if (!p || !existsSync(p)) {
    console.error('playwright 를 찾지 못했습니다.');
    console.error('  이 폴더에 설치: npm i -D playwright');
    console.error('  또는 PW_DIR 에 playwright/index.mjs 경로를 지정하세요.');
    process.exit(2);
  }
  return (await import(pathToFileURL(p).href)).chromium;
}

const chromium = await loadChromium();

const arg = (k, d) => {
  const a = process.argv.find(x => x.startsWith('--' + k + '='));
  return a ? Number(a.slice(k.length + 3)) : d;
};

const ROUNDS = arg('rounds', 100);      // 채점할 회차 수 (최근부터)
const BASE = arg('base', 20);           // 순위 계산에 쓸 직전 회차 수
const port = arg('port', 3071);

const HIST = JSON.parse(readFileSync('lotto_history.json', 'utf-8'))
  .filter(r => r && Array.isArray(r.nums) && r.nums.length === 6)
  .sort((a, b) => a.round - b.round);
console.log(`데이터 ${HIST.length}회차 (${HIST[0].round}~${HIST[HIST.length - 1].round})`);

const srv = spawn('python', ['-m', 'http.server', String(port), '--directory', '.', '--bind', '127.0.0.1'],
  { stdio: 'ignore' });
await new Promise(r => setTimeout(r, 1200));

const browser = await chromium.launch();
const page = await browser.newPage();
const errs = [];
page.on('pageerror', e => errs.push(String(e)));
await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 60; i++) {
  if (await page.evaluate(() => !!(window.__par && window.__par.computeEngine))) break;
  await page.waitForTimeout(500);
}

const targets = HIST.slice(-ROUNDS);
console.log(`채점 ${targets.length}회차 · 직전 ${BASE}회차 기준\n`);

const out = await page.evaluate(([hist, targets, base]) => {
  const P = window.__par;
  const byRound = {};
  hist.forEach(h => { byRound[h.round] = h; });
  const acc = {};
  P.PAR_MODES.forEach(m => {
    acc[m.key] = { label: m.label, short: m.short, lines: 0, rounds: 0,
                   full: [0, 0, 0, 0, 0, 0, 0], equal: [0, 0, 0, 0, 0, 0, 0],
                   fullGames: 0, equalGames: 0, best: 0 };
  });
  const rows = [];

  targets.forEach(t => {
    /* ★ 미래 정보 차단 — 이 회차보다 앞선 것만 */
    const prior = hist.filter(h => h.round < t.round).slice(-base);
    if (prior.length < 5) return;
    const eng = P.computeEngine(prior);
    const S = P.buildStrategies(eng);
    const built = P.buildRankings(eng, S);
    /* 📊 내 빈도 축은 '그 회차에 내가 저장한 줄' 이 있어야 한다 — 소급에는 없으므로 뺀다 */
    const ord = P.axisOrders(eng, built.ranks, null);
    const keys = P.axisKeys(ord);
    const n = P.parEqualN(keys);
    const row = { round: t.round, axes: keys.length, equalN: n, m: {} };

    P.PAR_MODES.forEach(md => {
      const lines = P.parallelCombos(ord, keys, md.m, md.per).map(l => l.numbers);
      const f = P.gradePool(lines, t.nums, t.bonus);
      const e = P.gradePoolTop(lines, n, t.nums, t.bonus);
      const a = acc[md.key];
      a.rounds++; a.lines += lines.length;
      a.fullGames += f.games; a.equalGames += e.games;
      for (let i = 0; i <= 6; i++) { a.full[i] += f.dist[i]; a.equal[i] += e.dist[i]; }
      if (f.best && f.best.hits > a.best) a.best = f.best.hits;
      row.m[md.key] = { lines: lines.length, fullBest: f.best ? f.best.hits : 0, equalHit3: e.hit3 };
    });
    rows.push(row);
  });
  return { acc, rows, modes: P.PAR_MODES.map(m => ({ key: m.key, short: m.short, label: m.label })) };
}, [HIST, targets, BASE]);

const pct = (a, b) => b ? (a / b * 100).toFixed(3) + '%' : '-';
const L = [];
const say = (s) => { L.push(s); console.log(s); };

say('══════ 병렬 3방식 실제 회차 대조 ══════');
say(`대상 ${out.rows.length}회차 · 직전 ${BASE}회차로 순위 계산 · 미래 정보 차단`);
say('');
say('[전체 줄 기준] — 방식마다 줄 수가 다르다');
say('방식   줄/회차   총줄수    3개    4개   5개  6개   3개이상비율');
out.modes.forEach(m => {
  const a = out.acc[m.key];
  const hit3 = a.full[3] + a.full[4] + a.full[5] + a.full[6];
  say(`${m.short.padEnd(6)} ${String(Math.round(a.lines / a.rounds)).padStart(6)} ${String(a.fullGames).padStart(8)} `
    + `${String(a.full[3]).padStart(6)} ${String(a.full[4]).padStart(5)} ${String(a.full[5]).padStart(4)} `
    + `${String(a.full[6]).padStart(3)}   ${pct(hit3, a.fullGames)}`);
});
say('');
say('[같은 줄 수 기준] — 공정 비교 (가장 적은 방식에 맞춰 앞에서 잘라냄)');
say('방식   총줄수    3개    4개   5개  6개   3개이상비율');
out.modes.forEach(m => {
  const a = out.acc[m.key];
  const hit3 = a.equal[3] + a.equal[4] + a.equal[5] + a.equal[6];
  say(`${m.short.padEnd(6)} ${String(a.equalGames).padStart(7)} `
    + `${String(a.equal[3]).padStart(6)} ${String(a.equal[4]).padStart(5)} ${String(a.equal[5]).padStart(4)} `
    + `${String(a.equal[6]).padStart(3)}   ${pct(hit3, a.equalGames)}`);
});
say('');
out.modes.forEach(m => say(`${m.short} 최고 적중: ${out.acc[m.key].best}개`));
say('');
say('※ 3개 이상 = 5등 이상. 로또 1줄이 3개 이상 맞을 확률은 약 2.24% 다.');
say('※ 📊 내 빈도 축은 소급 검증에 쓸 수 없어(그 회차에 저장한 줄이 없다) 제외했다.');

writeFileSync('backtest_par_modes.txt', L.join('\n') + '\n', 'utf-8');
console.log('\n→ backtest_par_modes.txt 저장');
if (errs.length) console.log('페이지 오류:', errs.slice(0, 3));

await browser.close();
srv.kill();
