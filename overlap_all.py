# -*- coding: utf-8 -*-
"""
전략 간 '번호 겹침' 통합 분석 → overlap_all.xlsx / overlap_all.html

[1] 전체 겹침    : ⓐ고정번호 후보 / ⓑTOP10 두 기준으로 번호별 겹침 수·전략명 + 겹침 분포
[2] TOP3 겹침    : 2개 이상 전략의 TOP3 에 동시에 든 번호 + 전략별 순위
[3] 같은 순위 겹침: 같은 번호가 2개 이상 전략에서 동일 순위를 받은 경우

※ 별표(*) = 셔플 편향으로 상위에 뜬 번호.
   판정 근거는 추측이 아니라 실측 — prob_v8.json(실제 앱 `.sort(()=>Math.random()-0.5)`)와
   prob_fair.json(공정 셔플)의 확률 차이가 +2.0%p 이상인 번호.

재활용: strategy_prob(전략 로직) · rank_tvec(분배회피) · strategy_rank(순위) · overlap/final_all(표·HTML)
실행: python overlap_all.py
"""
import json
import numpy as np
import pandas as pd
import strategy_prob as sp
import rank_tvec as tv
from strategy_rank import to_ranks
from overlap import build_sets, overlap_table, dist_table, pair_matrix, SHORT
from final_all import CSS, df_html, ball_html

ORDER = sp.ORDER
BIAS_CUT = 2.0        # %p — 이 이상이면 셔플 편향으로 상위에 뜬 것으로 표시
POOL_KEYS = [k for k in ORDER if k != "T"]     # 분배회피는 셔플을 쓰지 않음


def load_probs(eng, tpool, tbase):
    v8 = json.load(open("prob_v8.json", encoding="utf-8"))
    fair = json.load(open("prob_fair.json", encoding="utf-8"))
    tp = tv.t_probs(tpool, tbase, eng["W_fixed"])
    P = {k: (tp if k == "T" else np.array([v8[k][str(n)] for n in range(1, 46)])) for k in ORDER}
    F = {k: (tp if k == "T" else np.array([fair[k][str(n)] for n in range(1, 46)])) for k in ORDER}
    return P, F


def bias_info(P, F, eng):
    """번호별 셔플 편향 크기(%p) + FILL_POOL 순번(편향의 원인)"""
    gap = np.mean([P[k] - F[k] for k in POOL_KEYS], axis=0)
    pl = sp.build_pools(eng)
    fill = list(dict.fromkeys(pl["미출현"] + pl["일회"] + pl["강세"] + pl["중간"]))
    pos = {n: i for i, n in enumerate(fill)}
    return gap, pos


def star(n, gap):
    return "*" if gap[n - 1] >= BIAS_CUT else ""


def top3_overlap(ranks, gap):
    t3 = {k: [int(i) + 1 for i in np.argsort(ranks[k], kind="stable")[:3]] for k in ORDER}
    rows = []
    for n in range(1, 46):
        hit = [k for k in ORDER if n in t3[k]]
        if len(hit) >= 2:
            rows.append({"번호": f"{n}{star(n, gap)}", "_n": n, "걸린 전략 수": len(hit),
                         "걸린 전략": ", ".join(SHORT[k] for k in hit),
                         **{SHORT[k]: (f"{ranks[k][n-1]:.0f}위" if k in hit else "—") for k in ORDER}})
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values(["걸린 전략 수", "_n"], ascending=[False, True]).drop(columns="_n")
    return df.reset_index(drop=True), t3


def same_rank_overlap(ranks, gap, max_rank=45):
    rows = []
    for n in range(1, 46):
        by = {}
        for k in ORDER:
            by.setdefault(ranks[k][n - 1], []).append(k)
        for r, ks in sorted(by.items()):
            if len(ks) >= 2 and r <= max_rank:
                rows.append({"번호": f"{n}{star(n, gap)}", "_n": n, "공통 순위": f"{r:.0f}위",
                             "_r": r, "전략 수": len(ks),
                             "해당 전략들": ", ".join(SHORT[k] for k in ks)})
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values(["전략 수", "_r", "_n"], ascending=[False, True, True]).drop(columns=["_n", "_r"])
    return df.reset_index(drop=True)


def main():
    hist = sp.load_history()
    eng = sp.compute_engine(hist[-20:])
    tpool, tbase = tv.make_pool(200_000)
    P, F = load_probs(eng, tpool, tbase)
    gap, pos = bias_info(P, F, eng)
    ranks = {k: to_ranks(P[k]) for k in ORDER}

    # ── [1] 전체 겹침 ────────────────────────────────────
    A, B = build_sets(eng, P)
    dfA, dfB = overlap_table(A), overlap_table(B)
    for df in (dfA, dfB):
        df.insert(1, "편향*", [star(n, gap) for n in df["번호"]])
        df["편향 크기%p"] = [round(gap[n - 1], 2) for n in df["번호"]]
    distA, totA, expA = dist_table(A, dfA, "ⓐ 고정번호 후보")
    distB, totB, expB = dist_table(B, dfB, "ⓑ TOP10")
    pA, pB = pair_matrix(A), pair_matrix(B)

    setinfo = pd.DataFrame([{"전략": SHORT[k],
                             "ⓐ 고정번호 후보": ", ".join(map(str, sorted(A[k]))) or "— (없음)",
                             "ⓐ 개수": len(A[k]),
                             "ⓑ TOP10": ", ".join(map(str, sorted(B[k]))),
                             "TOP3": ", ".join(str(int(i) + 1) for i in np.argsort(ranks[k], kind="stable")[:3])}
                            for k in ORDER])

    # ── [2][3] ───────────────────────────────────────────
    df2, t3 = top3_overlap(ranks, gap)
    df3 = same_rank_overlap(ranks, gap)

    # 편향 상세
    bias = pd.DataFrame([{"번호": n, "FILL_POOL 순번": pos.get(n, "—"),
                          "V8 평균확률%": round(np.mean([P[k][n - 1] for k in POOL_KEYS]), 2),
                          "공정 평균확률%": round(np.mean([F[k][n - 1] for k in POOL_KEYS]), 2),
                          "편향 크기%p": round(gap[n - 1], 2),
                          "별표": star(n, gap)} for n in range(1, 46)]) \
        .sort_values("편향 크기%p", ascending=False).reset_index(drop=True)

    # 같은순위 겹침의 우연 기대치: 전략쌍마다 평균 1개 (순열 고정점)
    n_pairs = len(ORDER) * (len(ORDER) - 1) // 2
    obs_pairs = int(sum(int(r["전략 수"]) * (int(r["전략 수"]) - 1) // 2 for _, r in df3.iterrows())) if len(df3) else 0

    # ── xlsx ─────────────────────────────────────────────
    with pd.ExcelWriter("overlap_all.xlsx", engine="openpyxl") as w:
        setinfo.to_excel(w, sheet_name="전략별_번호집합", index=False)
        dfA.to_excel(w, sheet_name="1_ⓐ고정번호_겹침", index=False)
        dfB.to_excel(w, sheet_name="1_ⓑTOP10_겹침", index=False)
        pd.concat([distA, distB]).to_excel(w, sheet_name="1_겹침분포", index=False)
        pA.to_excel(w, sheet_name="1_ⓐ전략쌍", index=False)
        pB.to_excel(w, sheet_name="1_ⓑ전략쌍", index=False)
        (df2 if len(df2) else pd.DataFrame([{"결과": "2개 이상 전략의 TOP3에 동시에 든 번호 없음"}])) \
            .to_excel(w, sheet_name="2_TOP3겹침", index=False)
        (df3 if len(df3) else pd.DataFrame([{"결과": "동일 순위 겹침 없음"}])) \
            .to_excel(w, sheet_name="3_같은순위겹침", index=False)
        bias.to_excel(w, sheet_name="셔플편향_근거", index=False)
    print("저장 → overlap_all.xlsx")

    # ── html ─────────────────────────────────────────────
    H = [f"<style>{CSS}</style><div class='wrap'>",
         "<h1>🔗 전략 간 번호 겹침 통합 분석</h1>",
         f"<div class='sub'>기준 {eng['firstRound']}~{eng['lastRound']}회 (최근 20회) · "
         f"다음 {eng['lastRound']+1}회 대상 · 7전략 전부</div>",
         f"<div class='warn'>⭐ <b>별표(*) 기준</b> — 실제 앱의 셔플 "
         f"<code>.sort(()=&gt;Math.random()-0.5)</code>은 공정하지 않아 FILL_POOL 앞자리 번호를 "
         f"과대추출합니다. 별표는 추측이 아니라 <b>실측</b>으로, 같은 조건에서 공정 셔플 대비 "
         f"평균 확률이 <b>+{BIAS_CUT}%p 이상</b> 부풀려진 번호입니다. "
         f"이런 번호가 여러 전략 상위에 함께 뜨는 것은 전략들의 합의가 아니라 <b>버그의 공통 부작용</b>입니다.</div>"]

    st = bias[bias["별표"] == "*"]["번호"].tolist()
    if st:
        H.append("<div class='card'><b>별표 대상 번호</b><br>"
                 + "".join(ball_html(int(n)) for n in sorted(st))
                 + f"<div class='note'>{len(st)}개. 전부 FILL_POOL 앞순번(미출현·일회 풀)에 있는 번호입니다.</div></div>")

    H.append(df_html(setinfo, heat_cols=["ⓐ 개수"], title="전략별 대표 번호 집합"))

    H.append("<h2>[1] 전체 겹침</h2>")
    H.append(df_html(dfA[["번호", "편향*", "겹침 수", "걸린 전략"] + [SHORT[k] for k in ORDER]],
                     heat_cols=["겹침 수"], title="ⓐ 고정번호 후보 기준",
                     note=f"총 {totA}칸이 45개 번호에 분포 → 무작위라면 번호당 평균 {expA:.2f}개 전략."))
    H.append(df_html(distA, heat_cols=["번호 개수"], title="ⓐ 겹침 분포"))
    H.append(df_html(dfB[["번호", "편향*", "겹침 수", "걸린 전략"] + [SHORT[k] for k in ORDER]],
                     heat_cols=["겹침 수"], title="ⓑ TOP10 기준",
                     note=f"총 {totB}칸이 45개 번호에 분포 → 무작위라면 번호당 평균 {expB:.2f}개 전략."))
    H.append(df_html(distB, heat_cols=["번호 개수"], title="ⓑ 겹침 분포"))
    H.append(df_html(pB, heat_cols=[SHORT[k] for k in ORDER], title="전략쌍별 공유 번호 수 (TOP10 ∩ TOP10)"))

    H.append("<h2>[2] TOP3 겹침</h2>")
    if len(df2):
        H.append(df_html(df2, heat_cols=["걸린 전략 수"], title="",
                         note="2개 이상 전략의 TOP3에 동시에 든 번호."))
    else:
        H.append("<div class='card'>2개 이상 전략의 TOP3에 동시에 든 번호가 없습니다.</div>")

    H.append("<h2>[3] 같은 순위 겹침</h2>")
    if len(df3):
        H.append(df_html(df3, heat_cols=["전략 수"], title="",
                         note=f"관측 {obs_pairs}쌍 / 우연 기대 {n_pairs}쌍. "
                              f"전략쌍 하나당 '같은 순위인 번호'는 우연히도 평균 1개 생깁니다"
                              f"(순열의 고정점). 따라서 이 표는 의미 있는 합의가 아닙니다."))
    else:
        H.append("<div class='card'>동일 순위 겹침이 없습니다.</div>")

    H.append(df_html(bias.head(20), heat_cols=["편향 크기%p"], title="⭐ 별표 판정 근거 (편향 상위 20)",
                     note="FILL_POOL 순번이 앞일수록 편향이 큽니다 — 이것이 원인입니다."))
    H.append("</div>")
    open("overlap_all.html", "w", encoding="utf-8").write("\n".join(H))
    print("저장 → overlap_all.html")
    return setinfo, dfA, dfB, distA, distB, pB, df2, df3, bias, expA, expB, obs_pairs, n_pairs


if __name__ == "__main__":
    si, dA, dB, qA, qB, pB, d2, d3, bi, eA, eB, op, np_ = main()
    pd.set_option("display.unicode.east_asian_width", True)
    P = lambda t: print("\n" + "=" * 76 + f"\n{t}\n" + "=" * 76)

    P("전략별 대표 번호 집합")
    print(si.to_string(index=False))
    P(f"[1]ⓐ 고정번호 후보 겹침 (걸린 번호만 / 무작위 기대 {eA:.2f})")
    print(dA[dA["겹침 수"] > 0][["번호", "편향*", "겹침 수", "걸린 전략"]].to_string(index=False))
    print("\n▶ ⓐ 겹침 분포")
    print(qA[["겹침 구간", "번호 개수", "비율%", "해당 번호"]].to_string(index=False))
    P(f"[1]ⓑ TOP10 겹침 — 상위 16 (무작위 기대 {eB:.2f})")
    print(dB[["번호", "편향*", "겹침 수", "걸린 전략"]].head(16).to_string(index=False))
    print("\n▶ ⓑ 겹침 분포")
    print(qB[["겹침 구간", "번호 개수", "비율%", "해당 번호"]].to_string(index=False))
    P("[2] TOP3 겹침")
    print(d2.to_string(index=False) if len(d2) else "  해당 없음")
    P(f"[3] 같은 순위 겹침 (관측 {op}쌍 / 우연 기대 {np_}쌍)")
    print(d3.to_string(index=False) if len(d3) else "  해당 없음")
    P("⭐ 별표 판정 근거 — 셔플 편향 상위 10")
    print(bi.head(10).to_string(index=False))
