/* v18 실측 — 병렬 조합 3방식 (축3×2 / 축2×3 / 축1×6) + 대조

   핵심 방어선
     ① 어느 방식이든 한 줄은 **정확히 6개** · 중복 없음
     ② 축 수만 다르고 축마다 뽑는 개수가 방식대로다
     ③ 줄 수 = C(축수, m) 그대로
     ④ ★ 기존 방식(축3×2) 결과가 **한 줄도 바뀌지 않는다** (parallelAll 호환)
     ⑤ 같은 데이터면 몇 번을 돌려도 결과가 같다(결정적)
     ⑥ 겹치면 다음 순위로 밀어 6개를 채우고 * 로 표시한다
     ⑦ 세 방식을 **같은 줄 수**로 잘라 공정 비교한다

   실행: node verify_par_modes.mjs [--port=3051]
*/
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { existsSync } from 'node:fs';

/* 이 폴더에는 node_modules 가 없다. playwright 가 깔린 곳에서 불러온다.
   PW_DIR 환경변수로 덮어쓸 수 있고, 없으면 공간픽 폴더를 본다. */
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

const port = Number((process.argv.find(a => a.startsWith('--port=')) || '--port=3051').slice(7));
/* 이 폴더를 그대로 띄운다. **이 폴더에서 실행할 것**
   (cd lotto-app-git && node verify_par_modes.mjs) */
const srv = spawn('python', ['-m', 'http.server', String(port), '--directory', '.', '--bind', '127.0.0.1'],
  { stdio: 'ignore' });
await new Promise(r => setTimeout(r, 1200));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 420, height: 1000 } });
const pageErrors = [];
page.on('pageerror', e => pageErrors.push(String(e)));
await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'domcontentloaded' });
/* Babel 이 브라우저에서 컴파일을 끝낼 때까지 기다린다 — 고정 시간으로 재면 느린 날 실패한다 */
for (let i = 0; i < 60; i++) {
  if (await page.evaluate(() => !!(window.__par && window.__par.PAR_MODES))) break;
  await page.waitForTimeout(500);
}

const checks = [];
const ok = (l, c) => checks.push([l, !!c]);

/* 화면이 실제로 떴는지 — 여기서 실패하면 문법 오류다 */
const booted = await page.evaluate(() => {
  const root = document.getElementById('root') || document.body;
  return { html: (root.innerHTML || '').length, errs: 0 };
});
ok('앱이 정상으로 렌더된다 (root ' + booted.html + '자)', booted.html > 500);
ok('문법 오류 없음 (pageerror ' + pageErrors.length + ')', pageErrors.length === 0);
if (pageErrors.length) console.log(pageErrors.slice(0, 3));

/* 순위표(ord)를 만들어 계산부를 직접 두드린다.
   실데이터가 없어도 되도록 축마다 서로 다른 결정적 순서를 만든다. */
const R = await page.evaluate(() => {
  const KEYS = ['T', 'A', 'B', 'C', 'D'];   // T = 분배회피(섞기 대상)
  const ALL = Array.from({ length: 45 }, (_, i) => i + 1);
  const ord = {};
  KEYS.forEach((k, i) => {           // 축마다 시작점을 달리해 겹침도 생기게 한다
    ord[k] = ALL.slice(i).concat(ALL.slice(0, i));
  });
  const P = window.__par;
  const COMBO = P.PAR_MODES.filter(m => !m.mix);      // 조합 방식만
  const out = { modes: COMBO.map(m => ({ key: m.key, m: m.m, per: m.per })), runs: {} };
  COMBO.forEach(md => {
    const lines = P.parallelCombos(ord, KEYS, md.m, md.per);
    out.runs[md.key] = {
      count: lines.length,
      first: lines[0] ? { numbers: lines[0].numbers, parts: lines[0].parts.map(p => p.nums.length), label: lines[0].label } : null,
      allSix: lines.every(l => l.numbers.length === 6),
      noDup: lines.every(l => new Set(l.numbers).size === 6),
      sorted: lines.every(l => l.numbers.every((n, i, a) => i === 0 || a[i - 1] < n)),
      perOk: lines.every(l => l.parts.length === md.m && l.parts.every(p => p.nums.length === md.per)),
    };
  });
  /* ④ 기존 호출부 호환 */
  const legacy = P.parallelAll(ord, KEYS).map(l => l.numbers.join(','));
  const viaNew = P.parallelCombos(ord, KEYS, 3, 2).map(l => l.numbers.join(','));
  out.legacySame = JSON.stringify(legacy) === JSON.stringify(viaNew);
  out.legacyCount = legacy.length;
  /* ⑤ 결정적 */
  const again = P.parallelCombos(ord, KEYS, 2, 3).map(l => l.numbers.join(','));
  const again2 = P.parallelCombos(ord, KEYS, 2, 3).map(l => l.numbers.join(','));
  out.deterministic = JSON.stringify(again) === JSON.stringify(again2);
  /* ⑥ 대체(*) — 축 A·B 는 1칸 차이라 반드시 겹친다 */
  const two = P.parallelCombos(ord, ['A', 'B'], 2, 3);
  out.subst = two[0] ? { substituted: two[0].substituted, label: two[0].label } : null;
  /* ⑦ 공정 비교 */
  out.equalN = P.parEqualN(KEYS);
  out.cmp = P.parCompareModes(ord, KEYS, [1, 2, 3, 4, 5, 6], 7)
    .map(c => ({ key: c.key, lines: c.lines, fullGames: c.full.games, equalGames: c.equal.games }));
  /* 🆕 v21 — 분배회피 섞기 */
  const mixAll = P.popMixAll(ord, KEYS);
  out.mix = {
    count: mixAll.length,
    expect: (KEYS.length - 1) * P.POPMIX_RATIOS.length,
    allSix: mixAll.every(l => l.numbers.length === 6),
    noDup: mixAll.every(l => new Set(l.numbers).size === 6),
    usesT: mixAll.every(l => l.parts[0].k === P.POPMIX_KEY),
    ratios: [...new Set(mixAll.map(l => l.mix.join(':')))].sort(),
    splitOk: mixAll.every(l => l.parts[0].nums.length + l.parts[1].nums.length === 6
      && l.parts[0].nums.length === l.mix[0]),
    labelled: mixAll.every(l => /분배\d\+/.test(l.label)),
    deterministic: JSON.stringify(mixAll.map(l => l.numbers))
      === JSON.stringify(P.popMixAll(ord, KEYS).map(l => l.numbers)),
  };
  out.mixOne = (() => {
    const l = P.popMixLine('A', ord, [4, 2]);
    return l ? { t: l.parts[0].nums.length, o: l.parts[1].nums.length, six: l.numbers.length } : null;
  })();

  /* 🆕 v19 — 방식 겹쳐 고르기(합치기) */
  const uni = P.parallelUnion(ord, KEYS, ['a3x2', 'b2x3', 'c1x6']);
  const sigs = uni.map(l => l.numbers.join(','));
  out.union = {
    count: uni.length,
    dupSkipped: uni.dupSkipped,
    unique: new Set(sigs).size,
    allSix: uni.every(l => l.numbers.length === 6),
    tagged: uni.every(l => !!l.mode),
    order: [...new Set(uni.map(l => l.mode))],
    rawSum: P.parUnionCount(KEYS, ['a3x2', 'b2x3', 'c1x6']),
  };
  /* 하나만 켠 경우 — 조합 규칙은 그대로이고 **같은 번호 줄만** 빠진다 */
  const one = P.parallelUnion(ord, KEYS, ['b2x3']);
  const raw = P.parallelCombos(ord, KEYS, 2, 3).map(l => l.numbers.join(','));
  out.unionOne = {
    count: one.length, raw: raw.length,
    unique: new Set(raw).size,
    matchesUnique: one.length === new Set(raw).size,
    subset: one.every(l => raw.indexOf(l.numbers.join(',')) >= 0),
  };
  const uni2 = P.parallelUnion(ord, KEYS, ['a3x2', 'b2x3', 'c1x6']).map(l => l.numbers.join(','));
  out.unionDeterministic = JSON.stringify(sigs) === JSON.stringify(uni2);
  /* 🆕 v20 — 중복 축 진단 · 커버 · 무작위 대조군 */
  const dupOrd = { A: ALL.slice(), B: ALL.slice(), C: ALL.slice().reverse() };
  out.v20 = {
    overlapSame: P.axisOverlap(dupOrd, ['A', 'B'], 6)[0].same,          // 완전 동일 → 6
    overlapDiff: P.axisOverlap(dupOrd, ['A', 'C'], 6)[0].same,          // 정반대 → 0
    dupPairs: P.axisDupPairs(dupOrd, ['A', 'B', 'C']).map(d => d.a + d.b),
    warn: P.AXIS_DUP_WARN,
    cover6: P.coverCount([{ numbers: [1, 2, 3, 4, 5, 6] }]),
    cover9: P.coverCount([{ numbers: [1, 2, 3, 4, 5, 6] }, { numbers: [4, 5, 6, 7, 8, 9] }]),
    pickN: P.coverPick(P.parallelCombos(ord, KEYS, 3, 2), 3).length,
    pickGrows: (() => {
      const src = P.parallelCombos(ord, KEYS, 3, 2);
      const a = P.coverCount(P.coverPick(src, 2));
      const b = P.coverCount(src.slice(0, 2));
      return a >= b;                                    // 커버 우선이 앞에서 자른 것보다 못하지 않다
    })(),
    randSame: JSON.stringify(P.randomLines(5, 42)) === JSON.stringify(P.randomLines(5, 42)),
    randDiff: JSON.stringify(P.randomLines(5, 42)) !== JSON.stringify(P.randomLines(5, 43)),
    randShape: P.randomLines(20, 7).every(l => l.length === 6 && new Set(l).size === 6
      && l.every(n => n >= 1 && n <= 45) && l.every((n, i, arr) => i === 0 || arr[i - 1] < n)),
  };
  /* 🆕 v22 — 6축 통합 */
  const o12 = { T: ALL.slice(), U: ALL.slice(), V: ALL.slice().reverse(),
                X: ALL.slice(), COLD: ALL.slice(), Y: ALL.slice(), Z: ALL.slice(),
                HOT: ALL.slice(), MY: ALL.slice(), W: ALL.slice(),
                C: ALL.slice(), R: ALL.slice() };
  const o6 = P.axisOrders6(o12);
  const k6 = P.axisKeys6(o6);
  out.six = {
    keys: k6,
    count: k6.length,
    groups: P.AXIS6.map(g => g.k),
    allFull: k6.every(k => o6[k].length === 45 && new Set(o6[k]).size === 45),
    /* U(정순) + V(역순)은 모든 번호의 평균 자리가 같아진다 → 완전 동점 → 번호순 */
    tieOrder: o6.G_NUM ? o6.G_NUM.slice(0, 3).join(',') : null,
    /* 실제로 순서를 바꾸는 경우 — 45를 U 에서 맨 앞으로 올리면 평균이 당겨진다 */
    reorder: (() => {
      const u = [45].concat(ALL.filter(n => n !== 45));   // 45가 1등
      const v = ALL.slice();                              // 45가 꼴등
      const m = P.mergeOrders({ U: u, V: v }, ['U', 'V']);
      return { pos45: m.indexOf(45), pos1: m.indexOf(1), len: m.length };
    })(),
    /* 재료가 하나면 그대로 */
    popSame: JSON.stringify(o6.G_POP) === JSON.stringify(o12.T),
    /* 재료가 없으면 빠진다 */
    dropped: P.axisKeys6(P.axisOrders6({ T: ALL.slice() })),
    mixKey: P.popmixKeyOf(o6),
    mixKey12: P.popmixKeyOf(o12),
  };
  out.nck = [P.nCk(5, 3), P.nCk(5, 2), P.nCk(5, 1), P.nCk(11, 3), P.nCk(11, 2), P.nCk(11, 1)];
  return out;
});

ok('② 조합 방식 3종이 정의돼 있다 (실제 ' + R.modes.map(m => m.m + '×' + m.per).join(' / ') + ')',
  JSON.stringify(R.modes.map(m => [m.m, m.per])) === JSON.stringify([[3, 2], [2, 3], [1, 6]]));
ok('nCk 계산 정상 (실제 ' + R.nck.join(',') + ')',
  JSON.stringify(R.nck) === JSON.stringify([10, 10, 5, 165, 55, 11]));

for (const md of R.modes) {
  const r = R.runs[md.key];
  ok('① ' + md.m + '×' + md.per + ' — 모든 줄이 6개', r.allSix);
  ok('① ' + md.m + '×' + md.per + ' — 중복 번호 없음', r.noDup);
  ok('② ' + md.m + '×' + md.per + ' — 축 ' + md.m + '개 · 축마다 ' + md.per + '개', r.perOk);
  ok('③ ' + md.m + '×' + md.per + ' — 줄 수 C(5,' + md.m + ')=' + R.nck[[3, 2, 1].indexOf(md.m)] + ' (실제 ' + r.count + ')',
    r.count === [10, 10, 5][[3, 2, 1].indexOf(md.m)]);
  ok('  ' + md.m + '×' + md.per + ' — 번호가 오름차순으로 정렬된다', r.sorted);
}

ok('★ ④ 기존 방식(축3×2) 결과가 한 줄도 바뀌지 않는다 (' + R.legacyCount + '줄 동일)', R.legacySame);
ok('⑤ 같은 데이터면 결과가 같다(결정적)', R.deterministic);
ok('⑥ 겹치면 다음 순위로 밀고 * 로 표시 (실제 ' + (R.subst && R.subst.label) + ')',
  R.subst && R.subst.substituted === true && /\*/.test(R.subst.label));

ok('⑦ 공정 비교용 줄 수 = 가장 적은 방식에 맞춘다 (실제 ' + R.equalN + ')', R.equalN === 5);
ok('★ ⑦ 방식들을 같은 줄 수(5)로 잘라 채점한다 — 줄이 그보다 적으면 있는 만큼 (실제 '
   + R.cmp.map(c => c.equalGames + '/' + c.lines).join(' ') + ')',
  R.cmp.length === 5 && R.cmp.every(c => c.equalGames === Math.min(5, c.lines)));
ok('⑦ 조합 방식 줄 수는 그대로 (실제 ' + R.cmp.map(c => c.fullGames).join(',') + ')',
  JSON.stringify(R.cmp.slice(0, 3).map(c => c.fullGames)) === JSON.stringify([10, 10, 5]));

/* 화면에 방식 버튼이 실제로 있는가 */
const ui = await page.evaluate(() => {
  const txt = document.body.innerText || '';
  return { has3x2: /3×2/.test(txt), has2x3: /2×3/.test(txt), has1x6: /1×6/.test(txt) };
});
ok('화면에 방식 버튼 3개가 보인다 (3×2 / 2×3 / 1×6)', ui.has3x2 && ui.has2x3 && ui.has1x6);

/* ── 🆕 v19 방식 겹쳐 고르기 ─────────────────────────────── */
ok('⑧ 셋을 켜면 줄이 합쳐진다 (합계 ' + R.union.rawSum + ' → 중복 제거 후 ' + R.union.count + ')',
  R.union.count > 0 && R.union.count <= R.union.rawSum);
ok('★ ⑧ 번호가 같은 줄은 한 번만 남는다 (겹쳐서 뺀 줄 ' + R.union.dupSkipped + ')',
  R.union.unique === R.union.count && R.union.count + R.union.dupSkipped === R.union.rawSum);
ok('⑧ 합친 뒤에도 모든 줄이 6개', R.union.allSix);
ok('⑧ 줄마다 어느 방식에서 나왔는지 표시된다', R.union.tagged);
ok('⑧ 방식 순서가 고정이다 (실제 ' + R.union.order.join('→') + ')',
  JSON.stringify(R.union.order) === JSON.stringify(['a3x2', 'b2x3', 'c1x6']));
ok('⑧ 하나만 켜면 그 방식 줄에서 겹치는 것만 빠진다 ('
   + R.unionOne.raw + '줄 → 고유 ' + R.unionOne.unique + '줄)',
  R.unionOne.matchesUnique && R.unionOne.subset);
ok('⑧ 같은 데이터면 합친 결과도 매번 같다', R.unionDeterministic);

const ui2 = await page.evaluate(() => {
  const cmp = window.__par.parCompareModes;
  const ALL = Array.from({ length: 45 }, (_, i) => i + 1);
  const KEYS = ['A', 'B', 'C', 'D', 'E'];
  const ord = {}; KEYS.forEach((k, i) => { ord[k] = ALL.slice(i).concat(ALL.slice(0, i)); });
  return cmp(ord, KEYS, [1, 2, 3, 4, 5, 6], 7).map(c => ({ key: c.key, lines: c.lines }));
});
ok('⑧ 대조표에 「합침」 줄이 추가된다 (실제 ' + ui2.map(c => c.key).join(',') + ')',
  ui2.length === 5 && ui2[4].key === 'all' && ui2[4].lines > 0);

/* ── 🆕 v21 분배회피 섞기 ────────────────────────────────── */
const M = R.mix;
ok('⑫ 상대 축 × 비율 3가지만큼 나온다 (기대 ' + M.expect + ' · 실제 ' + M.count + ')',
  M.count > 0 && M.count <= M.expect);
ok('⑫ 모든 줄이 6개 · 중복 없음', M.allSix && M.noDup);
ok('★ ⑫ 항상 분배회피 축이 먼저 들어간다', M.usesT);
ok('★ ⑫ 4:2 · 3:3 · 2:4 가 모두 쓰인다 (실제 ' + M.ratios.join(' ') + ')',
  JSON.stringify(M.ratios) === JSON.stringify(['2:4', '3:3', '4:2']));
ok('⑫ 비율대로 나눠 담는다 (분배회피 개수 = 비율 앞자리)', M.splitOk);
ok('⑫ 어느 비율로 만든 줄인지 표시된다', M.labelled);
ok('⑫ 같은 데이터면 결과가 같다', M.deterministic);
/* ── 🆕 v22 6축 통합 ─────────────────────────────────────── */
const S6 = R.six;
ok('★ ⑬ 12축이 6축으로 묶인다 (실제 ' + S6.count + '개 · ' + S6.keys.join(' ') + ')',
  S6.count === 6 && JSON.stringify(S6.keys) === JSON.stringify(S6.groups));
ok('⑬ 묶은 뒤에도 1~45 가 빠짐없이 한 번씩', S6.allFull);
ok('⑬ 재료가 하나뿐인 묶음은 원본 그대로 (분배회피)', S6.popSame);
ok('⑬ 정순+역순은 모든 번호가 동점 → 번호순 (실제 ' + S6.tieOrder + ')',
  S6.tieOrder === '1,2,3');
ok('★ ⑬ 순위 평균이 실제로 순서를 바꾼다 — 한쪽 1등·한쪽 꼴등인 45가 중간으로 (실제 '
   + S6.reorder.pos45 + '번째 · 1번은 ' + S6.reorder.pos1 + '번째)',
  S6.reorder.len === 45 && S6.reorder.pos45 > 0 && S6.reorder.pos45 < 44
  && S6.reorder.pos45 > S6.reorder.pos1);
ok('⑬ 재료가 없는 묶음은 빠진다 (실제 ' + JSON.stringify(S6.dropped) + ')',
  JSON.stringify(S6.dropped) === JSON.stringify(['G_POP']));
ok('⑬ 분배섞기가 6축에서는 G_POP 을 쓴다 (실제 ' + S6.mixKey + ' / 12축 ' + S6.mixKey12 + ')',
  S6.mixKey === 'G_POP' && S6.mixKey12 === 'T');

ok('⑫ 4:2 는 분배회피 4 + 상대 2 (실제 ' + (R.mixOne && R.mixOne.t) + '+' + (R.mixOne && R.mixOne.o) + ')',
  R.mixOne && R.mixOne.t === 4 && R.mixOne.o === 2 && R.mixOne.six === 6);

/* ── 🆕 v20 중복 축 진단 · 커버 · 무작위 대조군 ─────────── */
const V = R.v20;
ok('⑨ 똑같은 축 두 개는 겹침 6/6 (실제 ' + V.overlapSame + ')', V.overlapSame === 6);
ok('⑨ 정반대 축은 겹침 0/6 (실제 ' + V.overlapDiff + ')', V.overlapDiff === 0);
ok('★ ⑨ 겹침 ' + V.warn + ' 이상만 중복으로 잡는다 (실제 ' + JSON.stringify(V.dupPairs) + ')',
  V.dupPairs.length === 1 && V.dupPairs[0] === 'AB');
ok('⑩ 커버 세기 — 한 줄 6개 (실제 ' + V.cover6 + ')', V.cover6 === 6);
ok('⑩ 커버 세기 — 겹치는 줄은 한 번만 (4,5,6 중복 → 9)', V.cover9 === 9);
ok('⑩ 커버 우선 선별이 앞에서 자른 것보다 좁지 않다', V.pickGrows);
ok('⑩ 요청한 줄 수만큼 고른다 (실제 ' + V.pickN + ')', V.pickN === 3);
ok('★ ⑪ 무작위 대조군은 씨앗이 같으면 같다(다시 봐도 같은 기준)', V.randSame);
ok('⑪ 씨앗이 다르면 다르다', V.randDiff);
ok('⑪ 무작위 줄도 1~45 · 6개 · 중복 없음 · 오름차순', V.randShape);

console.log('── v18 병렬 3방식 실측 ──');
checks.forEach(([l, c]) => console.log(' ' + (c ? 'PASS' : 'FAIL') + ' ' + l));
const pass = checks.filter(c => c[1]).length;
console.log('\n' + pass + '/' + checks.length + (pass === checks.length ? ' PASS' : ' — 실패 있음'));

await browser.close();
srv.kill();
process.exit(pass === checks.length ? 0 : 1);
