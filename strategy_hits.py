# -*- coding: utf-8 -*-
"""
전략 고정번호 적중 목록
- 21~1235회 각 회차마다 직전 20회로 computeEngine 재현 → 전략별 고정번호 후보 산출
- 그 후보가 해당 회차 실제 당첨번호 6개에 들어 있던 경우만 뽑아 목록화
- 최신 회차부터 정렬, 한 회차에 여러 개 맞으면 각각 한 줄
- 한 번호를 여러 전략이 집었으면 전략을 모두 나열

실행: python strategy_hits.py   → strategy_hits.txt 저장 + 최신 30줄 출력
"""
import strategy_prob as sp

FIXKEY = {"X": "X_fixed", "Y": "Y_fixed", "Z": "Z_fixed", "W": "W_fixed", "V": "V_fixed"}
LABEL = {k: f"{sp.STRAT_META[k]['emoji']}{sp.STRAT_META[k]['name']}" for k in FIXKEY}
OUT = "strategy_hits.txt"

def main():
    hist = sp.load_history()
    rows = []                                  # (회차, 번호, [전략키...])
    per_strat = {k: 0 for k in FIXKEY}         # 전략별 적중 횟수(번호 단위)
    rounds_with_hit = 0

    for end in range(20, len(hist)):
        eng = sp.compute_engine(hist[end - 20:end])
        rec = hist[end]
        win = set(rec["nums"])

        by_num = {}                            # 번호 → 그 번호를 집은 전략들
        for k, fk in FIXKEY.items():
            for n in eng[fk]:
                if n in win:
                    by_num.setdefault(n, []).append(k)
                    per_strat[k] += 1
        if by_num:
            rounds_with_hit += 1
        for n in sorted(by_num):
            rows.append((rec["round"], rec["date"], n, by_num[n]))

    rows.sort(key=lambda r: (-r[0], r[2]))     # 최신 회차 → 번호 오름차순

    lines = []
    A = lines.append
    A("=" * 78)
    A("전략 고정번호 적중 목록 — 21~1235회 (맞은 것만)")
    A("=" * 78)
    A("각 회차 직전 20회 데이터로 고정번호 후보를 재현하고, 그 회차 실제 당첨번호와 대조")
    A("🎲합계정밀·🤫분배회피는 고정번호가 없는 전략이라 대상에서 제외")
    A("")
    A(f"{'회차':>6} | {'날짜':^10} | {'맞은 번호':>9} | 그 번호를 집은 전략")
    A("-" * 78)
    for rd, date, n, ks in rows:
        A(f"{rd:>6} | {date:^10} | {n:>9} | " + ", ".join(LABEL[k] for k in ks))

    A("")
    A("=" * 78)
    A("전략별 총 적중 횟수 요약")
    A("=" * 78)
    tot_cand = {}
    for end in range(20, len(hist)):
        eng = sp.compute_engine(hist[end - 20:end])
        for k, fk in FIXKEY.items():
            tot_cand[k] = tot_cand.get(k, 0) + len(eng[fk])
    A(f"{'전략':<14}{'적중 횟수':>10}{'총 후보 수':>12}{'적중률':>10}{'기대 13.33% 대비':>18}")
    A("-" * 66)
    for k in sorted(FIXKEY, key=lambda x: -per_strat[x]):
        rate = 100 * per_strat[k] / tot_cand[k]
        A(f"{LABEL[k]:<14}{per_strat[k]:>10,}{tot_cand[k]:>12,}{rate:>9.2f}%{rate-100*6/45:>+17.2f}%p")
    A("-" * 66)
    A(f"{'합계':<14}{sum(per_strat.values()):>10,}{sum(tot_cand.values()):>12,}"
      f"{100*sum(per_strat.values())/sum(tot_cand.values()):>9.2f}%"
      f"{100*sum(per_strat.values())/sum(tot_cand.values())-100*6/45:>+17.2f}%p")
    A("")
    A(f"목록 줄 수(회차·번호 조합): {len(rows):,}줄")
    A(f"적중이 1개 이상 있던 회차: {rounds_with_hit:,} / {len(hist)-20:,}회 "
      f"({100*rounds_with_hit/(len(hist)-20):.1f}%)")

    open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"저장 완료 → {OUT}  ({len(lines):,}줄)")
    return rows, lines

if __name__ == "__main__":
    main()
