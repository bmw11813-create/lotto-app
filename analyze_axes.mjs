/* 축 진단 — 무엇이 겹치고 무엇이 낭비인지 실제 회차로 재본다

   왜 하나
     셋을 겹쳐 켜도 줄이 165 → 168개밖에 안 늘었다.
     축들이 서로 같은 번호를 내놓고 있다는 뜻이다. 그걸 숫자로 확인한다.

   보는 것
     ① 축끼리 TOP2·TOP6 가 얼마나 겹치나 (쌍별 평균 겹침 개수)
     ② 165줄이 실제로 45개 번호 중 몇 개나 덮나 (커버리지)
     ③ 같은 줄이 몇 개나 중복 생성되나
     ④ 축별 단독 적중률 — 어느 축이 실제로 쓸모 있나
     ⑤ 무작위 165줄과의 대조 (같은 조건 대조군)

   실행: node analyze_axes.mjs [--rounds=200] [--base=20]
*/
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';

async function loadChromium() {
  try { return (await import('playwright')).chromium; } catch (_) {}
  const p = process.env.PW_DIR;
  if (!p || !existsSync(p)) {
    console.error('playwright 를 찾지 못했습니다. npm i -D playwright 또는 PW_DIR 지정.');
    process.exit(2);
  }
  return (await import(pathToFileURL(p).href)).chromium;
}
const chromium = await loadChromium();

const arg = (k, d) => {
  const a = process.argv.find(x => x.startsWith('--' + k + '='));
  return a ? Number(a.slice(k.length + 3)) : d;
};
const ROUNDS = arg('rounds', 200), BASE = arg('base', 20), port = arg('port', 3091);

const HIST = JSON.parse(readFileSync('lotto_history.json', 'utf-8'))
  .filter(r => r && Array.isArray(r.nums) && r.nums.length === 6)
  .sort((a, b) => a.round - b.round);

const srv = spawn('python', ['-m', 'http.server', String(port), '--directory', '.', '--bind', '127.0.0.1'],
  { stdio: 'ignore' });
await new Promise(r => setTimeout(r, 1200));
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 60; i++) {
  if (await page.evaluate(() => !!(window.__par && window.__par.computeEngine))) break;
  await page.waitForTimeout(500);
}

const targets = HIST.slice(-ROUNDS);
const out = await page.evaluate(([hist, targets, base]) => {
  const P = window.__par;
  const pairTop2 = {}, pairTop6 = {}, axisHit = {}, axisSeen = {};
  let rounds = 0, coverSum = 0, dupSum = 0, rawSum = 0, uniqSum = 0;
  let randHit3 = 0, randGames = 0, parHit3 = 0, parGames = 0;
  let keysSeen = [];

  /* 결정적 난수 — 회차마다 같은 씨앗이라 다시 돌려도 같은 대조군이 나온다 */
  const rng = (seed) => () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;

  targets.forEach(t => {
    const prior = hist.filter(h => h.round < t.round).slice(-base);
    if (prior.length < 5) return;
    const eng = P.computeEngine(prior);
    const built = P.buildRankings(eng, P.buildStrategies(eng));
    const ord = P.axisOrders(eng, built.ranks, null);
    const keys = P.axisKeys(ord);
    if (!keysSeen.length) keysSeen = keys.slice();
    rounds++;

    /* ① 축끼리 겹침 */
    for (let a = 0; a < keys.length; a++) for (let b = a + 1; b < keys.length; b++) {
      const ka = keys[a], kb = keys[b], id = ka + '|' + kb;
      const t2a = ord[ka].slice(0, 2), t2b = ord[kb].slice(0, 2);
      const t6a = ord[ka].slice(0, 6), t6b = ord[kb].slice(0, 6);
      pairTop2[id] = (pairTop2[id] || 0) + t2a.filter(n => t2b.indexOf(n) >= 0).length;
      pairTop6[id] = (pairTop6[id] || 0) + t6a.filter(n => t6b.indexOf(n) >= 0).length;
    }

    /* ② ③ 165줄 커버리지·중복 */
    const lines = P.parallelCombos(ord, keys, 3, 2);
    const sigs = lines.map(l => l.numbers.join(','));
    const uniq = new Set(sigs).size;
    rawSum += lines.length; uniqSum += uniq; dupSum += lines.length - uniq;
    const used = new Set(); lines.forEach(l => l.numbers.forEach(n => used.add(n)));
    coverSum += used.size;
    const g = P.gradePool(lines.map(l => l.numbers), t.nums, t.bonus);
    parHit3 += g.hit3; parGames += g.games;

    /* ④ 축별 단독(TOP6) 적중 */
    keys.forEach(k => {
      const six = ord[k].slice(0, 6);
      const m = six.filter(n => t.nums.indexOf(n) >= 0).length;
      axisHit[k] = (axisHit[k] || 0) + (m >= 3 ? 1 : 0);
      axisSeen[k] = (axisSeen[k] || 0) + 1;
    });

    /* ⑤ 같은 줄 수의 무작위 대조군 */
    const r = rng(t.round * 7919);
    const rand = [];
    for (let i = 0; i < lines.length; i++) {
      const pool = Array.from({ length: 45 }, (_, x) => x + 1);
      for (let j = pool.length - 1; j > 0; j--) {
        const q = Math.floor(r() * (j + 1));
        const tmp = pool[j]; pool[j] = pool[q]; pool[q] = tmp;
      }
      rand.push(pool.slice(0, 6).sort((x, y) => x - y));
    }
    const rg = P.gradePool(rand, t.nums, t.bonus);
    randHit3 += rg.hit3; randGames += rg.games;
  });

  const meta = (k) => {
    const A = (window.__par.AXES || []);
    return k;
  };
  return {
    rounds, keys: keysSeen,
    pairTop2: Object.keys(pairTop2).map(id => ({ id, avg: pairTop2[id] / rounds })),
    pairTop6: Object.keys(pairTop6).map(id => ({ id, avg: pairTop6[id] / rounds })),
    cover: coverSum / rounds, raw: rawSum / rounds, uniq: uniqSum / rounds, dup: dupSum / rounds,
    axis: Object.keys(axisHit).map(k => ({ k, hit: axisHit[k], seen: axisSeen[k] })),
    par: { hit3: parHit3, games: parGames },
    rand: { hit3: randHit3, games: randGames },
  };
}, [HIST, targets, BASE]);

const L = [], say = s => { L.push(s); console.log(s); };
const pct = (a, b) => b ? (a / b * 100).toFixed(3) + '%' : '-';

say('══════ 축 진단 (최근 ' + out.rounds + '회차 · 직전 ' + BASE + '회차 기준) ══════');
say('쓸 수 있는 축 ' + out.keys.length + '개: ' + out.keys.join(' '));
say('');
say('① 축끼리 TOP2 겹침 — 2개 중 몇 개가 같은가 (1.0 이상이면 절반이 같다)');
out.pairTop2.sort((a, b) => b.avg - a.avg).slice(0, 12)
  .forEach(p => say('   ' + p.id.padEnd(14) + p.avg.toFixed(2)));
say('');
say('   TOP6 겹침 상위 (6개 중 몇 개가 같은가)');
out.pairTop6.sort((a, b) => b.avg - a.avg).slice(0, 12)
  .forEach(p => say('   ' + p.id.padEnd(14) + p.avg.toFixed(2)));
say('');
say('② 165줄이 덮는 번호: 평균 ' + out.cover.toFixed(1) + ' / 45개');
say('③ 165줄 중 번호가 같은 줄: 평균 ' + out.dup.toFixed(1) + '줄 (고유 ' + out.uniq.toFixed(1) + '줄)');
say('');
say('④ 축별 단독 TOP6 한 줄이 3개 이상 맞은 횟수 (' + out.rounds + '회차 중)');
out.axis.sort((a, b) => b.hit - a.hit)
  .forEach(a => say('   ' + a.k.padEnd(8) + a.hit + '회  ' + pct(a.hit, a.seen)));
say('');
say('⑤ 같은 줄 수 무작위 대조군');
say('   병렬 3×2 : ' + pct(out.par.hit3, out.par.games) + '  (' + out.par.hit3 + '/' + out.par.games + ')');
say('   무작위    : ' + pct(out.rand.hit3, out.rand.games) + '  (' + out.rand.hit3 + '/' + out.rand.games + ')');

writeFileSync('analyze_axes.txt', L.join('\n') + '\n', 'utf-8');
console.log('\n→ analyze_axes.txt 저장');
await browser.close();
srv.kill();
