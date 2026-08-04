# -*- coding: utf-8 -*-
"""
전략별 번호 순위 분석 → strategy_rank.txt

[1] 전략별 1~45번 추출확률 순위표
[2] 지금 앱이 뽑은 줄(전략당 5줄)의 번호가 [1]에서 몇 위인지
[3] 과거 각 회차의 실제 당첨번호가 그 시점 전략 순위에서 몇 위였는지 + 요약

모두 strategy_prob.py 로직 재사용. 각 회차는 직전 20회만 사용(미래정보 차단).
분배회피(T)는 rank_tvec.py 의 벡터화판 사용(원본과 exact 검증 완료).

실행: python strategy_rank.py
"""
import json, math, random
import numpy as np
import strategy_prob as sp
import rank_tvec as tv

ORDER = sp.ORDER                       # X Y Z W V U T
NAME  = {k: f"{sp.STRAT_META[k]['emoji']}{sp.STRAT_META[k]['name']}" for k in ORDER}
SHORT = {"X": "보너스", "Y": "미출현", "Z": "휴식", "W": "이월", "V": "끝수", "U": "합계", "T": "분배"}
N_RANK = 1500                          # [3] 회차별 순위 추정 시뮬 줄 수
T_POOL = 200000
OUT = "strategy_rank.txt"
L = []
def A(s=""): L.append(s)

# ── 확률 → 순위 (동점은 평균순위) ────────────────────────────
def to_ranks(p):
    order = np.argsort(-p, kind="stable")
    r = np.empty(45)
    i = 0
    while i < 45:
        j = i
        while j + 1 < 45 and p[order[j + 1]] == p[order[i]]:
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        for t in range(i, j + 1):
            r[order[t]] = avg
        i = j + 1
    return r                            # r[n-1] = n번의 순위

def sim_probs(key, S, P, rnd, n):
    cnt = np.zeros(45)
    ok = 0
    for _ in range(n):
        line = sp.gen_line(key, S, P, rnd, sp.v8_random_sort)
        if line is None:
            continue
        ok += 1
        for x in line:
            cnt[x - 1] += 1
    return cnt / max(ok, 1) * 100.0

# ══════════════════════════════════════════════════════════════
def main():
    hist = sp.load_history()
    pool, base = tv.make_pool(T_POOL)
    eng = sp.compute_engine(hist[-20:])
    S, P = sp.build_strategies(eng), sp.build_pools(eng)
    FIX = {"X": set(eng["X_fixed"]), "Y": set(eng["Y_fixed"]), "Z": set(eng["Z_fixed"]),
           "W": set(eng["W_fixed"]), "V": set(eng["V_fixed"]), "U": set(), "T": set()}

    # ─── [1] 현재 순위표 (prob_v8.json = 100,000줄 시뮬 재사용) ───
    pv = json.load(open("prob_v8.json", encoding="utf-8"))
    prob_now = {}
    for k in ORDER:
        prob_now[k] = (tv.t_probs(pool, base, eng["W_fixed"]) if k == "T"
                       else np.array([pv[k][str(n)] for n in range(1, 46)]))
    rank_now = {k: to_ranks(prob_now[k]) for k in ORDER}

    A("=" * 84)
    A(f"전략별 번호 순위 분석 — 기준 {eng['firstRound']}~{eng['lastRound']}회 (다음 회차 {eng['lastRound']+1}회 대상)")
    A("=" * 84)
    A("모든 계산은 strategy_prob.py 로직 재사용 / 각 회차는 직전 20회만 사용(미래정보 차단)")
    A(f"[1][2] 확률: 전략당 100,000줄 시뮬 (분배회피는 마스터풀 {T_POOL:,}개 기반)")
    A(f"[3] 확률: 회차당 {N_RANK:,}줄 시뮬 × 1,215회차")
    A("")
    A("━" * 84)
    A("[1] 전략별 숫자 순위표 — 1~45번을 추출확률 높은 순으로")
    A("━" * 84)
    for k in ORDER:
        p, r = prob_now[k], rank_now[k]
        spread = p.max() - p.min()
        flat = " ← 확률 평평 (고정번호 없음, 사실상 순위 무의미)" if k in ("U", "T") else ""
        A("")
        A(f"◆ {NAME[k]}  최고 {p.max():.1f}% / 최저 {p.min():.1f}% / 격차 {spread:.1f}%p{flat}")
        if FIX[k]:
            A(f"   고정번호 후보: {sorted(FIX[k])}")
        A(f"   {'순위':>4} {'번호':>4} {'확률%':>7}    {'순위':>4} {'번호':>4} {'확률%':>7}    "
          f"{'순위':>4} {'번호':>4} {'확률%':>7}")
        idx = np.argsort(-p, kind="stable")
        rows = 15
        for i in range(rows):
            cells = []
            for c in range(3):
                j = i + c * rows
                if j < 45:
                    n = int(idx[j]) + 1
                    star = "*" if n in FIX[k] else " "
                    cells.append(f"   {r[n-1]:>4.0f} {n:>4}{star}{p[n-1]:>6.1f}")
                else:
                    cells.append(" " * 20)
            A("  " + "   ".join(cells))
    A("")
    A("  * = 그 전략의 고정번호 후보")

    # ─── [2] 지금 뽑은 줄의 순위 ───────────────────────────────
    A("")
    A("━" * 84)
    A(f"[2] 지금 앱이 뽑은 번호의 순위 — 전략당 5줄 ({eng['lastRound']+1}회용)")
    A("━" * 84)
    rnd = random.Random(20260804)
    avg_pick = {}
    for k in ORDER:
        A("")
        A(f"◆ {NAME[k]}")
        allr = []
        for i in range(5):
            line = sp.gen_line(k, S, P, rnd, sp.v8_random_sort)
            if line is None:
                A(f"   {i+1}줄: 생성 실패"); continue
            rs = [rank_now[k][n - 1] for n in line]
            allr += rs
            body = "  ".join(f"{n:>2}({r:.0f}위)" for n, r in zip(line, rs))
            A(f"   {i+1}줄: {body}   평균 {sum(rs)/6:.1f}위")
        avg_pick[k] = sum(allr) / len(allr) if allr else float("nan")
        A(f"   → 5줄 30개 번호의 평균 순위: {avg_pick[k]:.1f}위 (45개 중 무작위면 23.0위)")
    A("")
    A(f"  {'전략':<12}{'뽑은 번호 평균순위':>20}")
    A("  " + "-" * 32)
    for k in sorted(ORDER, key=lambda x: avg_pick[x]):
        A(f"  {NAME[k]:<12}{avg_pick[k]:>18.1f}위")
    A("  ※ 전략이 자기가 높게 평가한 번호를 뽑으므로 23위보다 위인 게 당연함(자기충족)")

    # ─── [3] 과거 회차 당첨번호의 순위 ─────────────────────────
    print("[3] 회차별 순위 계산 시작…", flush=True)
    rnd2 = random.Random(555)
    rows = []
    acc = {k: {"sum": 0.0, "n": 0, "rmean": [],
               "t5o": 0, "t5e": 0.0, "t5v": 0.0,
               "t10o": 0, "t10e": 0.0, "t10v": 0.0} for k in ORDER}

    for step, end in enumerate(range(20, len(hist))):
        e = sp.compute_engine(hist[end - 20:end])
        s2, p2 = sp.build_strategies(e), sp.build_pools(e)
        rec = hist[end]
        win = rec["nums"]
        rk = {}
        for k in ORDER:
            pr = (tv.t_probs(pool, base, e["W_fixed"]) if k == "T"
                  else sim_probs(k, s2, p2, rnd2, N_RANK))
            rk[k] = to_ranks(pr)
            a = acc[k]
            wr = [rk[k][n - 1] for n in win]
            a["sum"] += sum(wr); a["n"] += 6; a["rmean"].append(sum(wr) / 6)
            for TOP, so, se, sv in (("t5", "t5o", "t5e", "t5v"), ("t10", "t10o", "t10e", "t10v")):
                cut = 5 if TOP == "t5" else 10
                tops = {i + 1 for i in range(45) if rk[k][i] <= cut}
                m = len(tops)
                a[so] += len(tops.intersection(win))
                a[se] += 6 * m / 45
                a[sv] += m * (6 / 45) * (39 / 45) * (45 - m) / 44
        for n in win:
            rows.append((rec["round"], rec["date"], n, [rk[k][n - 1] for k in ORDER]))
        if step % 100 == 0:
            print(f"  {step}/{len(hist)-20} (…{rec['round']}회)", flush=True)

    rows.sort(key=lambda r: (-r[0], r[2]))
    A("")
    A("━" * 84)
    A("[3] 회차별 실제 당첨번호의 순위 — 그 시점(직전 20회) 전략 순위에서 몇 위였나")
    A("━" * 84)
    A(f"{'회차':>6} | {'날짜':^10} | {'번호':>4} |" + "".join(f"{SHORT[k]:>7}" for k in ORDER))
    A("-" * 84)
    for rd, date, n, rs in rows:
        A(f"{rd:>6} | {date:^10} | {n:>4} |" + "".join(f"{x:>7.0f}" for x in rs))

    # ─── [3] 요약 ──────────────────────────────────────────────
    A("")
    A("━" * 84)
    A("[3] 요약 — 실제 당첨번호들의 평균 순위 (45개 중 23.0위 = 예측력 없음)")
    A("━" * 84)
    A(f"{'전략':<12}{'평균순위':>10}{'±SE':>8}{'23과 차이':>11}{'z':>8}{'판정':>12}")
    A("-" * 63)
    zs = []
    for k in sorted(ORDER, key=lambda x: acc[x]["sum"] / acc[x]["n"]):
        a = acc[k]
        m = a["sum"] / a["n"]
        v = a["rmean"]
        mu = sum(v) / len(v)
        se = math.sqrt(sum((x - mu) ** 2 for x in v) / (len(v) - 1) / len(v))
        z = (m - 23.0) / se
        zs.append(z)
        A(f"{NAME[k]:<12}{m:>10.2f}{se:>8.3f}{m-23:>+11.2f}{z:>+8.2f}"
          f"{('예측력 있음' if abs(z) > 2.58 else '예측력 없음'):>12}")
    chi = sum(z * z for z in zs)
    A("")
    A(f"  7전략 z 제곱합 = {chi:.2f} (자유도 7, 기대 7.0, 유의임계 18.48) → "
      f"{'이상 있음' if chi > 18.48 else '전부 무작위와 구분 불가 (p>0.05)'}")
    A("  ※ |z| > 2.58 (p<0.01) 이어야 '우연이 아니다'라고 말할 수 있음")

    A("")
    A("  [보강] 순위 상위권 적중률 — 시뮬 잡음에 강한 지표")
    A(f"  {'전략':<12}{'TOP5 적중':>11}{'기대':>9}{'z':>8}   {'TOP10 적중':>11}{'기대':>9}{'z':>8}")
    A("  " + "-" * 74)
    for k in ORDER:
        a = acc[k]
        z5 = (a["t5o"] - a["t5e"]) / math.sqrt(a["t5v"])
        z10 = (a["t10o"] - a["t10e"]) / math.sqrt(a["t10v"])
        A(f"  {NAME[k]:<12}{a['t5o']:>11,}{a['t5e']:>9,.0f}{z5:>+8.2f}   "
          f"{a['t10o']:>11,}{a['t10e']:>9,.0f}{z10:>+8.2f}")
    A("  ※ 전략이 1~5위로 꼽은 번호가 실제로 당첨된 횟수 vs 무작위 기대치")

    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"저장 완료 → {OUT} ({len(L):,}줄)")

if __name__ == "__main__":
    main()
