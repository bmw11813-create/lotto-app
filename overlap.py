# -*- coding: utf-8 -*-
"""
전략 간 '번호 겹침(중복)' 분석 → overlap.xlsx / overlap.html
순위의 높낮이는 무시하고, 각 전략이 잡는 번호 '집합'의 겹침만 센다.

기준 두 가지를 모두 출력
  ⓐ 고정번호 후보 : 전략이 직접 콕 집는 번호 (합계정밀·분배회피는 없음)
  ⓑ TOP10        : 추출확률 상위 10개 번호 (7전략 전부)

strategy_prob.py(전략 로직) · rank_tvec.py(분배회피) · final_all.py(HTML 헬퍼) 재활용
실행: python overlap.py
"""
import json, os
import numpy as np
import pandas as pd
import strategy_prob as sp
import rank_tvec as tv
from final_all import CSS, df_html, ball_html

ORDER = sp.ORDER
NAME = {k: f"{sp.STRAT_META[k]['emoji']}{sp.STRAT_META[k]['name']}" for k in ORDER}
SHORT = {"X": "보너스추적", "Y": "미출현폭탄", "Z": "휴식회귀", "W": "이월수",
         "V": "최약끝수", "U": "합계정밀", "T": "분배회피"}
FIXKEY = {"X": "X_fixed", "Y": "Y_fixed", "Z": "Z_fixed", "W": "W_fixed", "V": "V_fixed"}


def build_sets(eng, probs):
    """ⓐ 고정번호 후보 / ⓑ TOP10 집합"""
    a = {k: set(eng[FIXKEY[k]]) if k in FIXKEY else set() for k in ORDER}
    b = {k: set(int(i) + 1 for i in np.argsort(-probs[k], kind="stable")[:10]) for k in ORDER}
    return a, b


def overlap_table(sets):
    """번호별 겹침 수 + 걸린 전략 목록"""
    rows = []
    for n in range(1, 46):
        hit = [k for k in ORDER if n in sets[k]]
        rows.append({"번호": n, "겹침 수": len(hit),
                     "걸린 전략": ", ".join(SHORT[k] for k in hit) if hit else "—",
                     **{SHORT[k]: ("O" if n in sets[k] else "") for k in ORDER}})
    df = pd.DataFrame(rows).sort_values(["겹침 수", "번호"], ascending=[False, True])
    return df.reset_index(drop=True)


def dist_table(sets, df, label):
    tot = sum(len(sets[k]) for k in ORDER)
    exp = tot / 45.0
    rows = []
    for lo, hi, lab in [(0, 0, "0개 (어느 전략도 안 잡음)"), (1, 1, "1개 전략만"),
                        (2, 2, "2개 전략"), (3, 3, "3개 전략"), (4, 99, "4개 이상")]:
        sel = df[(df["겹침 수"] >= lo) & (df["겹침 수"] <= hi)]
        rows.append({"기준": label, "겹침 구간": lab, "번호 개수": len(sel),
                     "비율%": round(100 * len(sel) / 45, 1),
                     "해당 번호": ", ".join(str(x) for x in sorted(sel["번호"])) or "—"})
    return pd.DataFrame(rows), tot, exp


def pair_matrix(sets):
    rows = []
    for a in ORDER:
        r = {"전략": SHORT[a]}
        for b in ORDER:
            r[SHORT[b]] = len(sets[a] & sets[b])
        rows.append(r)
    return pd.DataFrame(rows)


def main():
    hist = sp.load_history()
    eng = sp.compute_engine(hist[-20:])
    tpool, tbase = tv.make_pool(200_000)

    # 추출확률: prob_v8.json(전략당 100,000줄) 재사용, 분배회피는 벡터화판
    pv = json.load(open("prob_v8.json", encoding="utf-8"))
    probs = {k: (tv.t_probs(tpool, tbase, eng["W_fixed"]) if k == "T"
                 else np.array([pv[k][str(n)] for n in range(1, 46)])) for k in ORDER}

    A, B = build_sets(eng, probs)
    dfA, dfB = overlap_table(A), overlap_table(B)
    distA, totA, expA = dist_table(A, dfA, "ⓐ 고정번호 후보")
    distB, totB, expB = dist_table(B, dfB, "ⓑ TOP10")
    pA, pB = pair_matrix(A), pair_matrix(B)

    setinfo = pd.DataFrame([{"전략": SHORT[k],
                             "ⓐ 고정번호 후보": ", ".join(map(str, sorted(A[k]))) or "— (없음)",
                             "ⓐ 개수": len(A[k]),
                             "ⓑ TOP10": ", ".join(map(str, sorted(B[k]))),
                             "ⓑ 개수": len(B[k])} for k in ORDER])

    # ── xlsx ──────────────────────────────────────────────
    with pd.ExcelWriter("overlap.xlsx", engine="openpyxl") as w:
        setinfo.to_excel(w, sheet_name="전략별_번호집합", index=False)
        dfA.to_excel(w, sheet_name="ⓐ고정번호_겹침", index=False)
        dfB.to_excel(w, sheet_name="ⓑTOP10_겹침", index=False)
        pd.concat([distA, distB]).to_excel(w, sheet_name="겹침분포_요약", index=False)
        pA.to_excel(w, sheet_name="ⓐ전략쌍_겹침", index=False)
        pB.to_excel(w, sheet_name="ⓑ전략쌍_겹침", index=False)
    print("저장 → overlap.xlsx")

    # ── html ──────────────────────────────────────────────
    H = [f"<style>{CSS}</style><div class='wrap'>",
         "<h1>🔗 전략 간 번호 겹침 분석</h1>",
         f"<div class='sub'>기준 {eng['firstRound']}~{eng['lastRound']}회 (최근 20회) · "
         f"다음 {eng['lastRound']+1}회 대상 · 순위 높낮이는 무시하고 집합의 겹침만 계산</div>"]

    H.append(df_html(setinfo, heat_cols=["ⓐ 개수"], title="전략별 대표 번호 집합",
                     note="합계정밀·분배회피는 고정번호가 없는 전략이라 ⓐ가 비어 있습니다."))

    H.append(df_html(dfA[["번호", "겹침 수", "걸린 전략"] + [SHORT[k] for k in ORDER]],
                     heat_cols=["겹침 수"], title="ⓐ 고정번호 후보 기준 — 번호별 겹침",
                     note=f"총 {totA}개 번호칸이 45개 번호에 분포 → 무작위라면 번호당 평균 {expA:.2f}개 전략."))
    H.append(df_html(distA, heat_cols=["번호 개수"], title="ⓐ 겹침 경우의 수 분포"))

    H.append(df_html(dfB[["번호", "겹침 수", "걸린 전략"] + [SHORT[k] for k in ORDER]],
                     heat_cols=["겹침 수"], title="ⓑ TOP10 기준 — 번호별 겹침",
                     note=f"총 {totB}개 번호칸이 45개 번호에 분포 → 무작위라면 번호당 평균 {expB:.2f}개 전략."))
    H.append(df_html(distB, heat_cols=["번호 개수"], title="ⓑ 겹침 경우의 수 분포"))

    top = dfB[dfB["겹침 수"] >= 4]["번호"].tolist()
    if top:
        H.append("<h2>여러 전략이 공통으로 잡은 번호 (TOP10 기준 4개 전략 이상)</h2>")
        H.append("<div class='card'>" + "".join(ball_html(int(n)) for n in sorted(top)) + "</div>")

    H.append(df_html(pA, heat_cols=[SHORT[k] for k in ORDER], title="ⓐ 전략쌍별 공유 번호 수",
                     note="대각선은 자기 집합 크기."))
    H.append(df_html(pB, heat_cols=[SHORT[k] for k in ORDER], title="ⓑ 전략쌍별 공유 번호 수 (TOP10 ∩ TOP10)"))
    H.append("</div>")
    open("overlap.html", "w", encoding="utf-8").write("\n".join(H))
    print("저장 → overlap.html")

    return setinfo, dfA, dfB, distA, distB, pB, expA, expB


if __name__ == "__main__":
    si, dA, dB, qA, qB, pB, eA, eB = main()
    pd.set_option("display.unicode.east_asian_width", True)
    print("\n■ 전략별 대표 번호 집합")
    print(si.to_string(index=False))
    print(f"\n■ ⓐ 고정번호 후보 기준 — 겹침 상위 (무작위 기대 {eA:.2f})")
    print(dA[dA["겹침 수"] > 0][["번호", "겹침 수", "걸린 전략"]].to_string(index=False))
    print("\n■ ⓐ 겹침 분포")
    print(qA[["겹침 구간", "번호 개수", "비율%", "해당 번호"]].to_string(index=False))
    print(f"\n■ ⓑ TOP10 기준 — 겹침 상위 15 (무작위 기대 {eB:.2f})")
    print(dB[["번호", "겹침 수", "걸린 전략"]].head(15).to_string(index=False))
    print("\n■ ⓑ 겹침 분포")
    print(qB[["겹침 구간", "번호 개수", "비율%", "해당 번호"]].to_string(index=False))
    print("\n■ ⓑ 전략쌍별 공유 번호 수 (TOP10 ∩ TOP10)")
    print(pB.to_string(index=False))
