/* v23 실측 — 생성 탭 전략 카드 9개 → 6개 통합

   v22 는 아래쪽 「병렬 조합」의 축만 줄였고 위쪽 전략 카드는 9개 그대로였다.
   여기서 화면에 실제로 6장이 뜨는지, 그 6개로 줄이 만들어지는지 본다.

   핵심 방어선
     ① 화면에 카드가 정확히 6장 뜬다 (9전략 버튼을 누르면 9장)
     ② 6전략이 순위 평균으로 합쳐진다 · 1~45 가 빠짐없이 한 번씩
     ③ 분배회피는 조합 단위 경로를 그대로 탄다(번호 순위가 아니다)
     ④ 6전략으로 줄이 실제로 만들어진다 · 6개 · 중복 없음
     ⑤ 같은 전략을 다시 눌러도 다른 줄이 나온다(순위를 이어받는다)
     ⑥ 9전략 원본 결과가 바뀌지 않는다

   실행 (이 폴더에서): node verify_strat6.mjs [--port=3141]
*/
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { existsSync } from 'node:fs';

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

const port = Number((process.argv.find(a => a.startsWith('--port=')) || '--port=3141').slice(7));
const srv = spawn('python', ['-m', 'http.server', String(port), '--directory', '.', '--bind', '127.0.0.1'],
  { stdio: 'ignore' });
await new Promise(r => setTimeout(r, 1200));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 420, height: 1200 } });
const pageErrors = [];
page.on('pageerror', e => pageErrors.push(String(e)));
await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 60; i++) {
  if (await page.evaluate(() => !!(window.__par && window.__par.STRAT6))) break;
  await page.waitForTimeout(500);
}

const checks = [];
const ok = (l, c) => checks.push([l, !!c]);

/* ── ① 화면 카드 수 ─────────────────────────────────────── */
const cards = () => page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')]
    .filter(b => /전략\s|MIX/.test(b.textContent || ''));
  return btns.map(b => (b.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 24));
});
let c6 = await cards();
ok('① 기본이 6전략이다 — 카드 ' + (c6.length - 1) + '장 + MIX (실제 ' + c6.length + ')',
  c6.length === 7 && c6.some(t => /MIX/.test(t)));
ok('① 통합 이름이 보인다 (수치규칙·미출현·합의)',
  c6.join(' ').indexOf('수치규칙') >= 0 && c6.join(' ').indexOf('미출현') >= 0);

await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').trim() === '9전략');
  if (b) b.click();
});
await page.waitForTimeout(400);
const c9 = await cards();
ok('① 9전략 버튼을 누르면 9장 + MIX (실제 ' + c9.length + ')', c9.length === 10);
await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').trim() === '6전략');
  if (b) b.click();
});
await page.waitForTimeout(400);
c6 = await cards();
ok('① 다시 6전략으로 돌아온다 (실제 ' + c6.length + ')', c6.length === 7);

/* ── ②③ 합치기 ─────────────────────────────────────────── */
const R = await page.evaluate(() => {
  const P = window.__par;
  const mk = (order) => order.map((n, i) => ({ n, rank: i + 1, reason: 'r' }));
  const ALL = Array.from({ length: 45 }, (_, i) => i + 1);
  const R9 = {
    T: mk(ALL), X: mk(ALL), W: mk(ALL),
    Y: mk(ALL), Z: mk(ALL.slice().reverse()),
    U: mk(ALL), V: mk([45].concat(ALL.filter(n => n !== 45))),
    C: mk(ALL), R: mk(ALL.slice().reverse()),
  };
  const R6 = P.buildRankings6(R9);
  const keys = Object.keys(R6);
  return {
    keys,
    order: P.DISPLAY_ORDER6,
    full: keys.every(k => R6[k] && R6[k].length === 45 && new Set(R6[k].map(r => r.n)).size === 45),
    ranked: keys.every(k => R6[k].every((r, i) => r.rank === i + 1)),
    /* U(정순) + V(45가 1등) → 45가 앞으로 당겨진다 */
    numPos45: R6.S_NUM.findIndex(r => r.n === 45),
    numPos45Raw: R9.U.findIndex(r => r.n === 45),
    /* 근거가 어느 전략에서 왔는지 남는다 */
    why: R6.S_NUM[0].reason,
    /* ③ 분배회피는 조합 단위 경로 */
    antiPop: P.isAntiPopStrat('S_POP') && P.isAntiPopStrat('T') && !P.isAntiPopStrat('S_NUM'),
    /* 단독 재료는 원본 그대로 */
    bonSame: JSON.stringify(R6.S_BON.map(r => r.n)) === JSON.stringify(R9.X.map(r => r.n)),
  };
});
ok('② 6전략이 만들어진다 (실제 ' + R.keys.length + '개 · ' + R.keys.join(' ') + ')',
  R.keys.length === 6 && JSON.stringify(R.keys.sort()) === JSON.stringify(R.order.slice().sort()));
ok('② 1~45 가 빠짐없이 한 번씩 · 순위가 1부터 매겨진다', R.full && R.ranked);
ok('★ ② 순위 평균으로 실제 순서가 바뀐다 (45번: 원본 ' + (R.numPos45Raw + 1) + '위 → 통합 ' + (R.numPos45 + 1) + '위)',
  R.numPos45 < R.numPos45Raw);
ok('② 어느 전략에서 몇 위였는지 근거가 남는다 (실제 ' + R.why + ')', /U\d+위\+V\d+위/.test(R.why));
ok('② 재료가 하나뿐이면 원본 그대로 (보너스추적)', R.bonSame);
ok('★ ③ 분배회피는 조합 단위 경로를 탄다', R.antiPop);

/* ── ④⑤⑥ 줄 생성 ──────────────────────────────────────── */
const G = await page.evaluate(() => {
  const P = window.__par;
  const ALL = Array.from({ length: 45 }, (_, i) => i + 1);
  const mk = (order) => order.map((n, i) => ({ n, rank: i + 1, reason: 'r' }));
  const R9 = { T: mk(ALL), X: mk(ALL), W: mk(ALL), Y: mk(ALL), Z: mk(ALL.slice().reverse()),
               U: mk(ALL), V: mk(ALL.slice().reverse()), C: mk(ALL), R: mk(ALL.slice().reverse()) };
  const R6 = P.buildRankings6(R9);
  const ANTI = [{ a: [2, 9, 17, 33, 38, 44], sc: 1 }, { a: [5, 12, 21, 35, 40, 45], sc: 2 }];
  const line1 = P.buildLine('S_NUM', 1, R6, ANTI);
  const line2 = P.buildLine('S_NUM', 2, R6, ANTI);
  const pop1 = P.buildLine('S_POP', 1, R6, ANTI);
  const pop2 = P.buildLine('S_POP', 2, R6, ANTI);
  const old1 = P.buildLine('U', 1, R9, ANTI);
  return {
    l1: line1 && line1.numbers, l2: line2 && line2.numbers,
    pop1: pop1 && pop1.numbers, pop2: pop2 && pop2.numbers,
    popReason: pop1 && pop1.reason,
    old1: old1 && old1.numbers,
  };
});
ok('④ 6전략으로 줄이 만들어진다 (실제 ' + JSON.stringify(G.l1) + ')',
  Array.isArray(G.l1) && G.l1.length === 6 && new Set(G.l1).size === 6);
ok('④ 번호가 오름차순', G.l1.every((n, i, a) => i === 0 || a[i - 1] < n));
ok('★ ⑤ 같은 전략을 또 눌러도 다른 줄 (1번 ' + JSON.stringify(G.l1) + ' / 2번 ' + JSON.stringify(G.l2) + ')',
  JSON.stringify(G.l1) !== JSON.stringify(G.l2));
ok('★ ③ 분배회피는 후보 조합을 그대로 쓴다 (실제 ' + JSON.stringify(G.pop1) + ')',
  JSON.stringify(G.pop1) === JSON.stringify([2, 9, 17, 33, 38, 44]));
ok('③ 분배회피 두 번째 줄은 다음 후보 (실제 ' + JSON.stringify(G.pop2) + ')',
  JSON.stringify(G.pop2) === JSON.stringify([5, 12, 21, 35, 40, 45]));
ok('③ 분배회피 근거에 대중성 점수가 남는다', /대중성 점수/.test(G.popReason || ''));
ok('★ ⑥ 9전략 원본 줄은 그대로 (U 1번 = ' + JSON.stringify(G.old1) + ')',
  JSON.stringify(G.old1) === JSON.stringify([1, 2, 3, 4, 5, 6]));

ok('pageerror 0건 (실제 ' + pageErrors.length + ')', pageErrors.length === 0);
if (pageErrors.length) console.log(pageErrors.slice(0, 5));

console.log('── v23 전략 6개 통합 실측 ──');
checks.forEach(([l, c]) => console.log(' ' + (c ? 'PASS' : 'FAIL') + ' ' + l));
const pass = checks.filter(c => c[1]).length;
console.log('\n' + pass + '/' + checks.length + (pass === checks.length ? ' PASS' : ' — 실패 있음'));

await browser.close();
srv.kill();
process.exit(pass === checks.length ? 0 : 1);
