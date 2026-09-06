/* v24 실측 — ① 분배섞기 토스트 버그 ② 「병렬」 탭(번호·비용·당첨 비교)

   핵심 방어선
     ① ★ 6축에서도 분배섞기가 막히지 않는다 (v23 까지는 축을 켜도 항상 막혔다)
     ② 하단 탭이 6개다 · 「병렬」 탭이 열린다
     ③ 저장된 자동 생성 줄이 없으면 안내만 보여준다
     ④ 비용·당첨 비교표 — 자동 생성 / 무작위 / 실구매 3줄
     ⑤ 당첨번호가 없으면 들어간 돈만 보여주고 손익은 말하지 않는다
     ⑥ 번호 목록에 당첨 번호가 표시된다

   실행 (이 폴더에서): node verify_partab.mjs [--port=3151]
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

const port = Number((process.argv.find(a => a.startsWith('--port=')) || '--port=3151').slice(7));
const srv = spawn('python', ['-m', 'http.server', String(port), '--directory', '.', '--bind', '127.0.0.1'],
  { stdio: 'ignore' });
await new Promise(r => setTimeout(r, 1200));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 420, height: 1400 } });
const pageErrors = [];
page.on('pageerror', e => pageErrors.push(String(e)));
await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 60; i++) {
  if (await page.evaluate(() => !!(window.__par && window.__par.popmixKeyOf))) break;
  await page.waitForTimeout(500);
}

const checks = [];
const ok = (l, c) => checks.push([l, !!c]);

/* ── ① 분배섞기 축 키 ─────────────────────────────────────── */
const K = await page.evaluate(() => {
  const P = window.__par;
  const ALL = Array.from({ length: 45 }, (_, i) => i + 1);
  const o12 = { T: ALL.slice(), U: ALL.slice(), V: ALL.slice().reverse(), X: ALL.slice(),
                COLD: ALL.slice(), Y: ALL.slice(), Z: ALL.slice(), HOT: ALL.slice(),
                MY: ALL.slice(), W: ALL.slice(), C: ALL.slice(), R: ALL.slice() };
  const o6 = P.axisOrders6(o12);
  const k6 = P.axisKeys6(o6);
  return {
    key6: P.popmixKeyOf(o6), key12: P.popmixKeyOf(o12),
    in6: k6.indexOf(P.popmixKeyOf(o6)) >= 0,
    /* 옛 방식(항상 'T')으로 찾으면 6축에서는 못 찾는다 — 그게 버그였다 */
    oldWouldFail: k6.indexOf('T') < 0,
    mixLines: P.popMixAll(o6, k6).length,
  };
});
ok('★ ① 6축에서 분배회피 키를 제대로 찾는다 (실제 ' + K.key6 + ')', K.key6 === 'G_POP');
ok('① 12축에서는 종전대로 T', K.key12 === 'T');
ok('★ ① 켠 축 목록 안에 있다 → 더 이상 막히지 않는다', K.in6);
ok('① (버그 재현) 옛 방식으로 T 를 찾으면 6축에서는 없다', K.oldWouldFail);
ok('① 6축에서 분배섞기 줄이 실제로 만들어진다 (실제 ' + K.mixLines + '줄)', K.mixLines > 0);

/* ── ② 하단 탭 ───────────────────────────────────────────── */
const nav = await page.evaluate(() => {
  const labels = ['생성', '저장', '매칭', '병렬', '통계', '설정'];
  const btns = [...document.querySelectorAll('button')]
    .filter(b => labels.indexOf((b.textContent || '').trim()) >= 0);
  return { found: btns.map(b => b.textContent.trim()), count: btns.length };
});
ok('② 하단 탭이 6개다 (실제 ' + nav.found.join(' ') + ')',
  nav.count === 6 && nav.found.indexOf('병렬') >= 0);

/* ③ 저장분이 없을 때 */
await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').trim() === '병렬');
  if (b) b.click();
});
await page.waitForTimeout(500);
let body = await page.evaluate(() => document.body.innerText || '');
ok('③ 저장분이 없으면 안내를 보여준다', /자동 생성된 줄이 없습니다/.test(body));
ok('③ 어디서 만드는지 알려준다', /자동 전체 생성/.test(body));

/* ── ④⑤⑥ 저장분을 넣고 다시 ─────────────────────────────── */
await page.evaluate(() => {
  const key = Object.keys(localStorage).find(k => /round|saved|lotto/i.test(k));
  return key;
});
const seeded = await page.evaluate(() => {
  /* 앱이 쓰는 저장 함수를 통하지 않고, 화면 컴포넌트를 직접 만들어 검사한다 —
     저장소 구조에 의존하지 않기 위해서다. */
  const P = window.__par;
  const rec = {
    round: 1241, games: [{ id: 1, numbers: [1, 2, 3, 4, 5, 6] }],
    winNumbers: [3, 11, 15, 20, 33, 41], bonus: 7,
    par: { isPar: true, axes: 6, modeLabel: '3×2 + 분배섞기', unique: 3, dupSkipped: 2,
           combos: [[3, 11, 15, 20, 33, 41], [3, 11, 15, 22, 30, 44], [2, 9, 17, 33, 38, 44]],
           labels: ['분배4+빈도2', '수치3+합의3', '분배2+보너스4'] },
  };
  const pz = P.gradePool ? null : null;
  return {
    par: (function () { const f = window.poolPrize; return f ? f(rec.par.combos, rec.winNumbers, rec.bonus) : null; })(),
    rec,
  };
});
/* poolPrize 는 전역이 아니므로 __par 를 통해 노출됐는지 확인 */
const pp = await page.evaluate(() => {
  try { return typeof poolPrize === 'function' ? 'ok' : 'no'; } catch (e) { return 'scoped'; }
});
ok('④ 비용·당첨 계산기(poolPrize)가 만들어져 있다', pp === 'ok' || pp === 'scoped');

/* 화면 문구가 실제로 그려지는지 — 컴포넌트를 직접 렌더해 확인 */
const rendered = await page.evaluate(() => {
  const host = document.createElement('div');
  host.id = '__partab';
  document.body.appendChild(host);
  const rec = {
    round: 1241, games: [{ id: 1, numbers: [1, 2, 3, 4, 5, 6] }],
    winNumbers: [3, 11, 15, 20, 33, 41], bonus: 7,
    par: { isPar: true, axes: 6, modeLabel: '3×2 + 분배섞기', unique: 3, dupSkipped: 2,
           combos: [[3, 11, 15, 20, 33, 41], [3, 11, 15, 22, 30, 44], [2, 9, 17, 33, 38, 44]],
           labels: ['분배4+빈도2', '수치3+합의3', '분배2+보너스4'] },
  };
  try {
    const root = ReactDOM.createRoot(host);
    root.render(React.createElement(ParTab, {
      saved: [rec], round: 1241, dark: false,
      card: 'bg-white', textDim: 'text-slate-500',
    }));
  } catch (e) { return { err: String(e) }; }
  return { ok: true };
});
ok('④ 병렬 탭 컴포넌트가 오류 없이 그려진다', rendered.ok === true);
await page.waitForTimeout(600);

const txt = await page.evaluate(() => (document.getElementById('__partab') || {}).innerText || '');
ok('④ 비교표에 3줄이 있다 (자동 생성 · 무작위 · 실제 구매)',
  /자동 생성/.test(txt) && /무작위/.test(txt) && /실제 구매/.test(txt));
ok('④ 구매비용·당첨금·손익 칸이 있다',
  /구매비용/.test(txt) && /당첨금/.test(txt) && /손익/.test(txt));
ok('★ ④ 3줄 × 1,000원 = 3,000원이 찍힌다 (실제 ' + (/3,000원/.test(txt) ? 'O' : 'X') + ')',
  /3,000원/.test(txt));
ok('★ ④ 1등(6개 일치) 당첨금이 잡힌다', /1등/.test(txt));
ok('④ 만든 방식이 보인다 (3×2 + 분배섞기 · 겹쳐서 뺀 2줄)',
  /분배섞기/.test(txt) && /겹쳐서 뺀 2줄/.test(txt));
ok('④ 검증용이라는 사실을 밝힌다', /실제로 사지 않은 검증용/.test(txt));

/* ⑤ 당첨번호가 없을 때 */
const noWin = await page.evaluate(() => {
  /* ★ 같은 자리에 두 번 그리면 앞 화면이 남는다(React 루트 중복).
     새 자리를 만들어 깨끗하게 그린다. */
  const old = document.getElementById('__partab2');
  if (old) old.remove();
  const host = document.createElement('div');
  host.id = '__partab2';
  document.body.appendChild(host);
  const rec = {
    round: 1242, games: [],
    winNumbers: null, bonus: null,
    par: { isPar: true, axes: 6, modeLabel: '3×2', unique: 2, combos: [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]] },
  };
  const root = ReactDOM.createRoot(host);
  root.render(React.createElement(ParTab, {
    saved: [rec], round: 1242, dark: false, card: 'bg-white', textDim: 'text-slate-500',
  }));
  return true;
});
await page.waitForTimeout(600);
const txt2 = await page.evaluate(() => (document.getElementById('__partab2') || {}).innerText || '');
/* '손익' 이라는 낱말은 안내문에도 나온다("…손익이 채워집니다").
   봐야 할 것은 **손익 수치를 지어내지 않는가** — 비교표 자체가 안 그려져야 한다. */
ok('★ ⑤ 당첨번호가 없으면 비교표를 그리지 않는다(손익 수치 없음)',
  !/실제 구매/.test(txt2) && !/무작위/.test(txt2) && /당첨번호가 없습니다/.test(txt2));
ok('⑤ 대신 들어간 돈만 보여준다 (2줄 = 2,000원)', /2,000원/.test(txt2));
ok('⑤ 당첨번호를 넣으라고 안내한다', /당첨번호/.test(txt2));

/* ── ⑦ 덮어쓰기 경고 문구 ────────────────────────────────
   자동 전체 생성은 기존 병렬 줄을 **통째로 교체**한다(data.par = {...}).
   종전 문구 "다시 만들까요?" 는 추가인지 교체인지 알 수 없었다. */
const warn = await page.evaluate(() => {
  const src = [...document.querySelectorAll('script')]
    .map(x => x.textContent || '').join('');
  return {
    saysReplace: /통째로 교체됩니다/.test(src),
    saysDeleted: /지워지고 새로 만든/.test(src),
    saysBoth: /줄이 저장돼 있습니다/.test(src),
    oldGone: !/이미 있습니다\. 다시 만들까요/.test(src),
    /* 실제로 덮어쓰는 코드인지 — data.par 에 통째 대입 */
    overwrites: /data\.par = \{/.test(src),
  };
});
ok('★ ⑦ 확인 문구가 "통째로 교체" 라고 밝힌다', warn.saysReplace);
ok('⑦ 지워지는 줄 수와 새로 생기는 줄 수를 함께 말한다', warn.saysDeleted && warn.saysBoth);
ok('⑦ 애매하던 옛 문구는 없어졌다', warn.oldGone);
ok('⑦ (근거) 실제로 data.par 를 통째로 대입한다 = 덮어쓰기', warn.overwrites);

ok('pageerror 0건 (실제 ' + pageErrors.length + ')', pageErrors.length === 0);
if (pageErrors.length) console.log(pageErrors.slice(0, 5));

console.log('── v24 병렬 탭 · 토스트 버그 실측 ──');
checks.forEach(([l, c]) => console.log(' ' + (c ? 'PASS' : 'FAIL') + ' ' + l));
const pass = checks.filter(c => c[1]).length;
console.log('\n' + pass + '/' + checks.length + (pass === checks.length ? ' PASS' : ' — 실패 있음'));

await browser.close();
srv.kill();
process.exit(pass === checks.length ? 0 : 1);
