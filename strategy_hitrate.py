# -*- coding: utf-8 -*-
"""
전략별 적중률 종합
  [1] 전략별 적중률 = 총 맞은 개수 ÷ 총 뽑은 개수   (bt_*.json 재사용)
  [2] 적중 개수 분포 (0개/1개/2개/3개↑)
  [3] "고정번호 후보"만 따로 뗀 적중률 + 초기하 정확검정
  [4] 앱이 실제로 줄에 투입한 고정번호의 적중률 (셔플 편향 포함)

실행: python strategy_hitrate.py [nsim]   nsim 생략 시 [4] 건너뜀
"""
import json, math, random, sys
import strategy_prob as sp

ORDER = sp.ORDER
NAME = {k: f"{sp.STRAT_META[k]['emoji']} {sp.STRAT_META[k]['name']}" for k in ORDER}
BASE = 6 / 45 * 100          # 13.3333% — 번호 1개가 당첨 6개에 들 확률

# ─────────────────────────────────────────────────────────────
# [1][2] 백테스트 결과 재사용
# ─────────────────────────────────────────────────────────────
def load_bt():
    D = {}
    for m in ("v8", "fair", "ctrl"):
        for k, v in json.load(open(f"bt_{m}.json", encoding="utf-8")).items():
            if k != "_meta":
                D[(m, k)] = v
    return D

def cl_se(per_round):
    """회차 군집 표준오차 (평균 적중개수 기준)"""
    vals = [s / n for n, s, _ in per_round]
    m = len(vals)
    mu = sum(vals) / m
    var = sum((v - mu) ** 2 for v in vals) / (m - 1)
    return math.sqrt(var / m)

def part1(D):
    rows = []
    for k in ORDER:
        src = "ctrl" if k == "T" else "v8"
        v = D[(src, k)]
        n, hits = v["n"], v["hits"]
        rows.append((NAME[k], 100 * hits / (n * 6), hits / n, cl_se(v["per_round"]), n, hits))
    rows.sort(key=lambda r: -r[1])

    print("=" * 78)
    print("【1】 전략별 적중률  =  총 맞은 개수 ÷ 총 뽑은 번호 개수")
    print("     (21~1235회 1,215개 회차 · 각 회차 직전 20회만 사용 · V8 셔플 = 실제 앱)")
    print("=" * 78)
    print(f"┌{'─'*16}┬{'─'*10}┬{'─'*15}┬{'─'*11}┬{'─'*17}┐")
    print(f"│{'전략':^14}│{'적중률%':^8}│{'평균 적중개수':^11}│{'±SE':^9}│{'총 맞음/총 뽑음':^15}│")
    print(f"├{'─'*16}┼{'─'*10}┼{'─'*15}┼{'─'*11}┼{'─'*17}┤")
    for nm, hr, mean, se, n, hits in rows:
        print(f"│ {nm:<13}│{hr:>8.3f}  │{mean:>11.4f}    │ ±{se:>7.4f} │{hits:>7,}/{n*6:>9,}│")
    print(f"├{'─'*16}┼{'─'*10}┼{'─'*15}┼{'─'*11}┼{'─'*17}┤")
    r = D[("ctrl", "RND")]
    print(f"│ {'⚪ 무작위 6/45':<13}│{100*r['hits']/(r['n']*6):>8.3f}  │{r['hits']/r['n']:>11.4f}    │ ±{cl_se(r['per_round']):>7.4f} │{r['hits']:>7,}/{r['n']*6:>9,}│")
    print(f"│ {'📐 이론값':<13}│{BASE:>8.3f}  │{0.8:>11.4f}    │{'—':^9}│{'—':^15}│")
    print(f"└{'─'*16}┴{'─'*10}┴{'─'*15}┴{'─'*11}┴{'─'*17}┘")
    print("\n  ※ 적중률% = 평균 적중개수 ÷ 6.  이론값 0.8개 ÷ 6 = 13.333%")

def part2(D):
    print("\n" + "=" * 78)
    print("【2】 적중 개수 분포 (%) — 한 줄이 몇 개 맞았나")
    print("=" * 78)
    print(f"{'전략':<16}{'0개':>9}{'1개':>9}{'2개':>9}{'3개↑':>9}{'  (3개↑=5등 이상 당첨)'}")
    print("-" * 78)
    th = [math.comb(6, i) * math.comb(39, 6 - i) / math.comb(45, 6) for i in range(7)]
    print(f"{'📐 이론값':<16}{100*th[0]:>9.3f}{100*th[1]:>9.3f}{100*th[2]:>9.3f}{100*sum(th[3:]):>9.3f}")
    for k in ORDER:
        v = D[("ctrl" if k == "T" else "v8", k)]
        n, d = v["n"], v["dist"]
        print(f"{NAME[k]:<16}{100*d[0]/n:>9.3f}{100*d[1]/n:>9.3f}{100*d[2]/n:>9.3f}{100*sum(d[3:])/n:>9.3f}")
    r = D[("ctrl", "RND")]
    print(f"{'⚪ 무작위 6/45':<16}" + "".join(f"{100*r['dist'][i]/r['n']:>9.3f}" for i in range(3))
          + f"{100*sum(r['dist'][3:])/r['n']:>9.3f}")

# ─────────────────────────────────────────────────────────────
# [3] 고정번호 "후보" 적중률 — 시뮬레이션 없이 정확 계산
# ─────────────────────────────────────────────────────────────
FIXKEY = {"X": "X_fixed", "Y": "Y_fixed", "Z": "Z_fixed", "W": "W_fixed", "V": "V_fixed"}

def part3(hist):
    print("\n" + "=" * 78)
    print("【3】 '고정번호 후보'만 뗀 적중률 — 전략이 콕 집은 번호는 잘 맞았나")
    print("=" * 78)
    stat = {k: {"m": 0, "h": 0, "var": 0.0, "rounds": 0, "any": 0} for k in FIXKEY}
    for end in range(20, len(hist)):
        eng = sp.compute_engine(hist[end - 20:end])
        win = set(hist[end]["nums"])
        for k, fk in FIXKEY.items():
            S = set(eng[fk])
            m = len(S)
            if m == 0:
                continue
            h = len(S & win)
            s = stat[k]
            s["m"] += m; s["h"] += h; s["rounds"] += 1
            s["any"] += 1 if h > 0 else 0
            # 초기하 분산: 당첨 6개가 45개 중 무작위일 때 |S∩당첨| 의 분산
            s["var"] += m * (6 / 45) * (39 / 45) * (45 - m) / 44

    print(f"{'전략':<16}{'후보수':>8}{'평균':>7}{'총후보':>8}{'맞음':>7}{'적중률%':>9}{'기대%':>8}{'z':>8}{'판정':>10}")
    print("-" * 82)
    zs = []
    for k in FIXKEY:
        s = stat[k]
        rate = 100 * s["h"] / s["m"]
        exp = s["m"] * 6 / 45
        z = (s["h"] - exp) / math.sqrt(s["var"])
        zs.append(z)
        verdict = "유의미" if abs(z) > 2.58 else "차이없음"
        print(f"{NAME[k]:<16}{s['rounds']:>8}{s['m']/s['rounds']:>7.2f}{s['m']:>8,}{s['h']:>7,}"
              f"{rate:>9.3f}{BASE:>8.3f}{z:>+8.2f}{verdict:>10}")
    print(f"{'🎲 합계정밀':<16}{'—':>8}{'0.00':>7}{'—':>8}{'—':>7}{'—':>9}{'—':>8}{'—':>8}{'후보없음':>10}")
    print(f"{'🤫 분배회피':<16}{'—':>8}{'0.00':>7}{'—':>8}{'—':>7}{'—':>9}{'—':>8}{'—':>8}{'후보없음':>10}")
    chi = sum(z * z for z in zs)
    print(f"\n  5개 전략 z 제곱합 = {chi:.2f} (자유도 5, 기대 5.0, 유의임계 11.07)"
          f" → {'이상 있음' if chi > 11.07 else '이론과 일치 (p>0.05)'}")
    print("  ※ z = ±2.58 이면 p=0.01. |z|>2.58 이어야 '우연이 아니다'라고 말할 수 있음")

    print(f"\n  [참고] 후보 중 최소 1개가 당첨된 회차 비율")
    for k in FIXKEY:
        s = stat[k]
        mavg = s["m"] / s["rounds"]
        exp_any = 100 * (1 - math.comb(39, 6) / math.comb(45, 6)) if False else None
        print(f"    {NAME[k]:<14} {100*s['any']/s['rounds']:>6.2f}%  (후보 평균 {mavg:.2f}개)")

# ─────────────────────────────────────────────────────────────
# [4] 앱이 실제 줄에 넣은 고정번호의 적중률
# ─────────────────────────────────────────────────────────────
def part4(hist, nsim):
    print("\n" + "=" * 78)
    print(f"【4】 앱이 실제로 줄에 투입한 고정번호의 적중률 (회차당 {nsim}줄)")
    print("=" * 78)
    res = {}
    for mode in ("v8", "fair"):
        shuffle = sp.v8_random_sort if mode == "v8" else sp.fair_shuffle
        rnd = random.Random(777)
        acc = {k: [0, 0] for k in FIXKEY}      # [투입번호수, 맞은수]
        for end in range(20, len(hist)):
            eng = sp.compute_engine(hist[end - 20:end])
            S, P = sp.build_strategies(eng), sp.build_pools(eng)
            win = set(hist[end]["nums"])
            for k in FIXKEY:
                for _ in range(nsim):
                    line, used = sp.gen_line(k, S, P, rnd, shuffle, trace=True)
                    if line is None:
                        continue
                    acc[k][0] += len(used)
                    acc[k][1] += len(set(used) & win)
        res[mode] = acc
        print(f"  [{mode}] 완료")
    print(f"\n{'전략':<16}{'V8 적중률%':>12}{'공정 적중률%':>14}{'기대%':>8}")
    print("-" * 52)
    for k in FIXKEY:
        a, b = res["v8"][k], res["fair"][k]
        print(f"{NAME[k]:<16}{100*a[1]/a[0]:>12.3f}{100*b[1]/b[0]:>14.3f}{BASE:>8.3f}")

if __name__ == "__main__":
    D = load_bt()
    hist = sp.load_history()
    part1(D)
    part2(D)
    part3(hist)
    if len(sys.argv) > 1:
        part4(hist, int(sys.argv[1]))
