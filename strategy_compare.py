# -*- coding: utf-8 -*-
"""strategy_prob.py 결과(prob_v8.json / prob_fair.json) 비교 분석"""
import json
import strategy_prob as sp

ORDER = sp.ORDER
NAME = {k: sp.STRAT_META[k]["name"] for k in ORDER}
UNIF = 600 / 45  # 균등 시 기대확률 13.33%

v8 = {k: {int(n): v for n, v in d.items()} for k, d in json.load(open("prob_v8.json", encoding="utf-8")).items()}
fair = {k: {int(n): v for n, v in d.items()} for k, d in json.load(open("prob_fair.json", encoding="utf-8")).items()}

hist = sp.load_history()
eng = sp.compute_engine(hist)
P = sp.build_pools(eng)
FILL = list(dict.fromkeys(P["미출현"] + P["일회"] + P["강세"] + P["중간"]))
FIXED = {"X": eng["X_fixed"], "Y": eng["Y_fixed"], "Z": eng["Z_fixed"],
         "W": eng["W_fixed"], "V": eng["V_fixed"], "U": [], "T": []}

print("=" * 70)
print("A. 셔플 편향(V8 `.sort(()=>Math.random()-0.5)`) 이 확률을 얼마나 왜곡하나")
print("=" * 70)
print(f"{'전략':<12}{'평균오차(%p)':>14}{'최대오차(%p)':>14}  최대오차 번호")
for k in ORDER:
    d = {n: v8[k][n] - fair[k][n] for n in range(1, 46)}
    worst = max(d, key=lambda n: abs(d[n]))
    mad = sum(abs(x) for x in d.values()) / 45
    print(f"{NAME[k]:<12}{mad:>14.2f}{abs(d[worst]):>14.2f}  {worst}번 ({fair[k][worst]:.1f}% → {v8[k][worst]:.1f}%)")

print("\n[FILL_POOL 순서 vs 실제확률] — 앞자리에 있을수록 더 뽑힘")
print("순번  번호   U전략확률(v8)  (균등이면 13.3%)")
for i in list(range(6)) + [15, 25, 35, 44]:
    n = FILL[i]
    print(f"{i:>3}  {n:>3}   {v8['U'][n]:>10.1f}%")

print("\n" + "=" * 70)
print("B. 전략별 편향 — 확률이 몰리는 번호 (v8, 실제 앱 동작 기준)")
print("=" * 70)
for k in ORDER:
    top = sorted(range(1, 46), key=lambda n: -v8[k][n])[:6]
    bot = sorted(range(1, 46), key=lambda n: v8[k][n])[:4]
    vals = [v8[k][n] for n in range(1, 46)]
    hi = ", ".join(f"{n}({v8[k][n]:.0f}%)" for n in top)
    lo = ", ".join(f"{n}({v8[k][n]:.0f}%)" for n in bot)
    print(f"\n{sp.STRAT_META[k]['emoji']} {NAME[k]}({k})  고정후보={FIXED[k] or '없음'}")
    print(f"   최고: {hi}")
    print(f"   최저: {lo}")
    print(f"   최고/최저 배율 {max(vals)/min(vals):.1f}배 · 상위6개 합 {sum(sorted(vals)[-6:]):.0f}% / 전체 600%")

print("\n" + "=" * 70)
print("C. 모든 전략이 공통으로 자주 뽑는 번호 / 공통으로 버리는 번호")
print("=" * 70)
mn = {n: min(v8[k][n] for k in ORDER) for n in range(1, 46)}
mx = {n: max(v8[k][n] for k in ORDER) for n in range(1, 46)}
avg = {n: sum(v8[k][n] for k in ORDER) / 7 for n in range(1, 46)}
print("\n[공통 강세] 7전략 최소확률이 높은 번호 = 어느 전략을 골라도 잘 나옴")
for n in sorted(range(1, 46), key=lambda n: -mn[n])[:8]:
    print(f"  {n:>2}번  최소{mn[n]:>5.1f}%  평균{avg[n]:>5.1f}%  (freq={eng['freq'][n]}회)")
print("\n[공통 약세] 7전략 최대확률이 낮은 번호 = 어느 전략을 골라도 잘 안 나옴")
for n in sorted(range(1, 46), key=lambda n: mx[n])[:8]:
    print(f"  {n:>2}번  최대{mx[n]:>5.1f}%  평균{avg[n]:>5.1f}%  (freq={eng['freq'][n]}회)")
print("\n[전략 의존] 전략에 따라 확률이 가장 크게 갈리는 번호")
for n in sorted(range(1, 46), key=lambda n: -(mx[n] - mn[n]))[:8]:
    who = max(ORDER, key=lambda k: v8[k][n])
    print(f"  {n:>2}번  {mn[n]:>5.1f}% ~ {mx[n]:>5.1f}%  (최고={NAME[who]})")

print("\n" + "=" * 70)
print("D. 전략끼리 얼마나 겹치나 — 서로 다른 전략의 두 줄이 공유하는 번호 개수(기대값)")
print("=" * 70)
print("   (무작위 두 줄 = 0.80개 / 완전히 같은 전략끼리도 랜덤이므로 1.0 미만)")
hdr = "      " + "".join(f"{k:>7}" for k in ORDER)
print(hdr)
for a in ORDER:
    row = f"  {a}   "
    for b in ORDER:
        ov = sum(v8[a][n] * v8[b][n] for n in range(1, 46)) / 10000
        row += f"{ov:>7.2f}"
    print(row)

print("\n[전략쌍 차이 크기] 총변동거리 TVD (0=동일, 100=완전 다름)")
pairs = []
for i, a in enumerate(ORDER):
    for b in ORDER[i + 1:]:
        tvd = sum(abs(v8[a][n] - v8[b][n]) for n in range(1, 46)) / 2
        pairs.append((tvd, a, b))
pairs.sort()
print("  가장 비슷한 3쌍:", ", ".join(f"{NAME[a]}↔{NAME[b]} {t:.0f}" for t, a, b in pairs[:3]))
print("  가장 다른  3쌍:", ", ".join(f"{NAME[a]}↔{NAME[b]} {t:.0f}" for t, a, b in pairs[-3:]))

print("\n[균등(13.3%)에서 얼마나 벗어났나] — 값이 클수록 '특색 있는' 전략")
for k in ORDER:
    tvd = sum(abs(v8[k][n] - UNIF) for n in range(1, 46)) / 2
    print(f"  {NAME[k]:<10} {tvd:>5.0f}")

print("\n" + "=" * 70)
print("E. FILL_POOL 이 실제로 번호를 걸러내는가 (전체 회차 점검)")
print("=" * 70)
full, cut = 0, 0
worst = None
for end in range(20, len(hist) + 1):
    e = sp.compute_engine(hist[:end])
    p = sp.build_pools(e)
    f = set(p["미출현"] + p["일회"] + p["강세"] + p["중간"])
    if len(f) == 45:
        full += 1
    else:
        cut += 1
        if worst is None or len(f) < worst[1]:
            worst = (e["lastRound"], len(f))
tot = full + cut
print(f"  검사한 창(20회 단위) {tot}개 중 FILL_POOL 이 45개 전부인 경우: {full}개 ({100*full/tot:.1f}%)")
print(f"  번호가 실제로 걸러진 경우: {cut}개 ({100*cut/tot:.1f}%)  최소 풀 크기 {worst[1] if worst else '-'}개")
