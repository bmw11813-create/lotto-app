# -*- coding: utf-8 -*-
"""
7전략 매칭 백테스트
- 각 회차 r 마다 "직전 20회"만으로 엔진을 돌려(미래정보 차단) 전략별 줄을 생성
- 그 줄을 r회 실제 당첨번호 6개와 대조해 적중 개수를 집계
- 대조군 2종을 함께 돌려 "전략이 필터 이상의 무엇을 더하는가"를 분리

대조군
  RND  : 아무 조건 없는 무작위 6/45          (이론 평균 0.8000개, 3개↑ 2.3834%)
  FILT : isValid(110~160) 만 통과한 무작위 줄 (전략 고정번호 없음)

실행:
  python strategy_backtest.py v8     # V8 셔플(실제 앱 동작)
  python strategy_backtest.py fair   # 공정 셔플
  python strategy_backtest.py ctrl   # 대조군 + 분배회피(T, 셔플과 무관)
  python strategy_backtest.py report # 결과 합쳐 표 출력
"""
import json, math, os, random, sys
from collections import defaultdict
import strategy_prob as sp

N_LINE   = 150   # 회차당 전략별 생성 줄 수 (풀 기반 6전략 + 대조군)
N_LINE_T = 20    # 분배회피(T)는 1줄당 후보 1500개라 별도
POOL6    = ["X", "Y", "Z", "W", "V", "U"]

# ── 이론값 (초기하분포) ────────────────────────────────────────
def C(n, k):
    return math.comb(n, k)

def theory():
    tot = C(45, 6)
    p = {k: C(6, k) * C(39, 6 - k) / tot for k in range(7)}
    mean = sum(k * p[k] for k in range(7))
    return mean, sum(p[k] for k in range(3, 7)) * 100, p

# ── 집계 그릇 ─────────────────────────────────────────────────
class Acc:
    __slots__ = ("n", "hits", "dist", "per_round", "fail")
    def __init__(self):
        self.n = 0; self.hits = 0; self.fail = 0
        self.dist = [0] * 7
        self.per_round = []          # (줄수, 적중합, 3개↑개수) 회차별 → 군집표준오차용

    def add_round(self, hit_list, fail):
        self.fail += fail
        if not hit_list:
            return
        s = sum(hit_list)
        g3 = sum(1 for h in hit_list if h >= 3)
        self.n += len(hit_list); self.hits += s
        for h in hit_list:
            self.dist[h] += 1
        self.per_round.append((len(hit_list), s, g3))

    def to_json(self):
        return {"n": self.n, "hits": self.hits, "fail": self.fail,
                "dist": self.dist, "per_round": self.per_round}

# ── 대조군 생성기 ─────────────────────────────────────────────
def gen_rnd(rnd):
    return rnd.sample(range(1, 46), 6)

def gen_filt(rnd):
    for _ in range(300):
        a = sorted(rnd.sample(range(1, 46), 6))
        if sp.is_valid(a, 110, 160):
            return a
    return None

# ── 백테스트 ──────────────────────────────────────────────────
def run(mode, hist):
    rnd = random.Random(20260804 + {"v8": 1, "fair": 2, "ctrl": 3}[mode])
    shuffle = sp.v8_random_sort if mode == "v8" else sp.fair_shuffle

    if mode == "ctrl":
        keys = ["T", "RND", "FILT"]
    else:
        keys = POOL6
    acc = {k: Acc() for k in keys}

    total = len(hist) - 20
    for i, end in enumerate(range(20, len(hist))):
        train  = hist[end - 20:end]          # 직전 20회 (미래정보 없음)
        target = set(hist[end]["nums"])      # 맞혀야 할 회차
        eng = sp.compute_engine(train)
        S, P = sp.build_strategies(eng), sp.build_pools(eng)

        for k in keys:
            nl = N_LINE_T if k == "T" else N_LINE
            hl, fail = [], 0
            for _ in range(nl):
                if k == "RND":
                    line = gen_rnd(rnd)
                elif k == "FILT":
                    line = gen_filt(rnd)
                else:
                    line = sp.gen_line(k, S, P, rnd, shuffle)
                if line is None:
                    fail += 1
                else:
                    hl.append(len(target.intersection(line)))
            acc[k].add_round(hl, fail)

        if i % 200 == 0:
            print(f"  [{mode}] {i}/{total} (…{hist[end]['round']}회)", flush=True)

    out = {k: acc[k].to_json() for k in keys}
    out["_meta"] = {"mode": mode, "rounds": total,
                    "from": hist[20]["round"], "to": hist[-1]["round"]}
    json.dump(out, open(f"bt_{mode}.json", "w", encoding="utf-8"))
    print(f"  [{mode}] 완료 → bt_{mode}.json")

# ── 리포트 ────────────────────────────────────────────────────
def cluster_se(per_round, kind):
    """회차 단위 군집 표준오차 (같은 회차 줄들은 고정번호를 공유 → 상관 있음)"""
    m = len(per_round)
    if m < 2:
        return 0.0
    if kind == "mean":
        vals = [s / n for n, s, _ in per_round]
    else:
        vals = [100.0 * g / n for n, _, g in per_round]
    mu = sum(vals) / m
    var = sum((v - mu) ** 2 for v in vals) / (m - 1)
    return math.sqrt(var / m)

NAME = {**{k: f"{sp.STRAT_META[k]['emoji']} {sp.STRAT_META[k]['name']}({k})" for k in sp.ORDER},
        "RND": "⚪ 무작위 6/45 (대조군)", "FILT": "⚪ 필터만 통과 (대조군)"}

def report():
    th_mean, th_g3, th_p = theory()
    data = {}
    meta = None
    for mode in ("v8", "fair", "ctrl"):
        f = f"bt_{mode}.json"
        if not os.path.exists(f):
            print(f"!! {f} 없음 — python strategy_backtest.py {mode} 먼저 실행"); return
        d = json.load(open(f, encoding="utf-8"))
        meta = meta or d["_meta"]
        for k, v in d.items():
            if k != "_meta":
                data[(mode, k)] = v

    print("=" * 96)
    print(f"매칭 백테스트 결과 — {meta['from']}~{meta['to']}회 ({meta['rounds']}개 회차, 각 회차 직전 20회만 사용)")
    print("=" * 96)
    print(f"이론값(무작위 6/45): 평균 적중 {th_mean:.4f}개 · 3개↑ {th_g3:.4f}%")
    print(f"검증 줄 수: 전략당 {N_LINE}줄×{meta['rounds']}회차 = {N_LINE*meta['rounds']:,}줄 "
          f"(분배회피 {N_LINE_T}줄×{meta['rounds']}회차 = {N_LINE_T*meta['rounds']:,}줄)")

    def block(title, rows):
        print("\n" + title)
        print(f"{'전략':<24}{'줄 수':>10}{'평균적중':>10}{'±SE':>7}{'이론대비':>9}"
              f"{'3개↑%':>8}{'±SE':>7}{'4개↑%':>8}{'5개↑%':>8}{'6개':>6}")
        print("-" * 96)
        for mode, k in rows:
            v = data[(mode, k)]
            n = v["n"]; d = v["dist"]
            mean = v["hits"] / n
            g3 = 100.0 * sum(d[3:]) / n
            g4 = 100.0 * sum(d[4:]) / n
            g5 = 100.0 * sum(d[5:]) / n
            se_m = cluster_se(v["per_round"], "mean")
            se_g = cluster_se(v["per_round"], "g3")
            print(f"{NAME[k]:<24}{n:>10,}{mean:>10.4f}{se_m:>7.4f}{mean-th_mean:>+9.4f}"
                  f"{g3:>8.3f}{se_g:>7.3f}{g4:>8.4f}{g5:>8.4f}{d[6]:>6}")

    block("【A】 V8 셔플 = 실제 앱 동작", [("v8", k) for k in POOL6] + [("ctrl", "T")])
    block("【B】 공정 셔플로 바꿨을 때", [("fair", k) for k in POOL6] + [("ctrl", "T")])
    block("【C】 대조군", [("ctrl", "RND"), ("ctrl", "FILT")])

    print("\n【D】 V8 vs 공정 셔플 차이 (평균 적중 개수)")
    print(f"{'전략':<24}{'V8':>10}{'공정':>10}{'차이':>10}{'유의성':>12}")
    print("-" * 66)
    for k in POOL6:
        a, b = data[("v8", k)], data[("fair", k)]
        ma, mb = a["hits"] / a["n"], b["hits"] / b["n"]
        sa, sb = cluster_se(a["per_round"], "mean"), cluster_se(b["per_round"], "mean")
        se = math.sqrt(sa ** 2 + sb ** 2)
        z = (ma - mb) / se if se else 0
        print(f"{NAME[k]:<24}{ma:>10.4f}{mb:>10.4f}{ma-mb:>+10.4f}{('z=%+.2f' % z):>12}")

    print("\n【E】 적중 개수 분포 (V8 기준, %) — 이론값과 비교")
    print(f"{'전략':<24}" + "".join(f"{f'{i}개':>9}" for i in range(7)))
    print("-" * 90)
    print(f"{'이론(무작위)':<24}" + "".join(f"{100*th_p[i]:>9.4f}" for i in range(7)))
    for mode, k in [("v8", x) for x in POOL6] + [("ctrl", "T"), ("ctrl", "RND"), ("ctrl", "FILT")]:
        v = data[(mode, k)]
        n = v["n"]
        print(f"{NAME[k]:<24}" + "".join(f"{100*v['dist'][i]/n:>9.4f}" for i in range(7)))

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "report"
    if what == "report":
        report()
    else:
        run(what, sp.load_history())
