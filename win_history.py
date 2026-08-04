# -*- coding: utf-8 -*-
"""
복구된 앱 백업(recovered_backup.json)의 저장 번호를 실제 당첨번호와 대조 → win_history.xlsx

1) 저장된 모든 줄을 실제 당첨번호와 대조 (회차·날짜·산 번호·당첨번호·적중 수·등수)
2) 3개 이상 적중 줄만 따로 추출
3) 각 줄의 전략 표시를 그 회차 시점의 전략 고정번호와 대조해 교차검증(역추적)

strategy_prob.py 로직 재사용. 실행: python win_history.py
"""
import json
import pandas as pd
import strategy_prob as sp

FIXKEY = {"X": "X_fixed", "Y": "Y_fixed", "Z": "Z_fixed", "W": "W_fixed", "V": "V_fixed"}
SNAME = {k: f"{sp.STRAT_META[k]['emoji']}{sp.STRAT_META[k]['name']}" for k in sp.ORDER}

def rank_of(m, bonus_hit):
    if m == 6: return "1등"
    if m == 5 and bonus_hit: return "2등"
    if m == 5: return "3등"
    if m == 4: return "4등"
    if m == 3: return "5등"
    return "—"

def main():
    hist = json.load(open("lotto_history.json", encoding="utf-8"))
    H = {r["round"]: r for r in hist}
    idx = {r["round"]: i for i, r in enumerate(hist)}
    backup = json.load(open("recovered_backup.json", encoding="utf-8"))

    rows, trace = [], []
    for rec in backup["rounds"]:
        rd = rec.get("round")
        act = H.get(rd)
        if not act:
            print(f"  ! {rd}회 실제 당첨번호 없음 — 건너뜀"); continue
        win, bn = set(act["nums"]), act["bonus"]

        # 그 회차 시점(직전 20회)의 전략 고정번호 재현
        i = idx[rd]
        eng = sp.compute_engine(hist[i - 20:i])
        fixed = {k: set(eng[FIXKEY[k]]) for k in FIXKEY}

        for g in rec.get("games", []):
            nums = g["numbers"]
            m = len(win & set(nums))
            bh = bn in nums
            rows.append({
                "회차": rd, "추첨일": act["date"], "저장일": rec.get("date", ""),
                "줄": g.get("id"), "표시된 전략": SNAME.get(g.get("strategy"), g.get("strategy") or "—"),
                "내가 산 6개 번호": ", ".join(f"{x:02d}" for x in nums),
                "당첨번호": ", ".join(f"{x:02d}" for x in act["nums"]), "보너스": bn,
                "적중 개수": m, "보너스 적중": "O" if bh else "",
                "등수": rank_of(m, bh),
                "맞은 번호": ", ".join(f"{x:02d}" for x in sorted(win & set(nums))) or "—",
            })
            hit = {k: sorted(fixed[k] & set(nums)) for k in FIXKEY if fixed[k] & set(nums)}
            trace.append({
                "회차": rd, "줄": g.get("id"),
                "표시된 전략": SNAME.get(g.get("strategy"), g.get("strategy") or "—"),
                "번호": ", ".join(f"{x:02d}" for x in nums),
                "고정번호가 들어있는 전략": ", ".join(f"{SNAME[k]}({','.join(map(str,v))})"
                                                for k, v in hit.items()) or "— 없음",
                "표시와 일치": "O" if g.get("strategy") in hit else
                              ("판정불가(고정번호 없는 전략)" if g.get("strategy") in ("U", "T") else "X"),
            })

    df = pd.DataFrame(rows)
    hi = df[df["적중 개수"] >= 3].reset_index(drop=True)
    tr = pd.DataFrame(trace)

    fixinfo = []
    for rd in sorted({r["회차"] for r in rows}):
        i = idx[rd]
        eng = sp.compute_engine(hist[i - 20:i])
        for k in sp.ORDER:
            fixinfo.append({"회차": rd, "전략": SNAME[k],
                            "그 시점 고정번호 후보": ", ".join(map(str, eng[FIXKEY[k]])) if k in FIXKEY else "— (없는 전략)"})

    with pd.ExcelWriter("win_history.xlsx", engine="openpyxl") as w:
        df.to_excel(w, sheet_name="전체대조", index=False)
        (hi if len(hi) else pd.DataFrame([{"결과": "3개 이상 적중한 줄이 없습니다"}])) \
            .to_excel(w, sheet_name="3개이상적중", index=False)
        tr.to_excel(w, sheet_name="전략역추적", index=False)
        pd.DataFrame(fixinfo).to_excel(w, sheet_name="회차별_전략고정번호", index=False)
    print("저장 → win_history.xlsx")

    pd.set_option("display.unicode.east_asian_width", True)
    print(f"\n■ 전체 대조 ({len(df)}줄)")
    print(df[["회차", "추첨일", "줄", "표시된 전략", "내가 산 6개 번호",
              "적중 개수", "맞은 번호", "등수"]].to_string(index=False))
    print(f"\n■ 3개 이상 적중: {len(hi)}건")
    if len(hi):
        print(hi.to_string(index=False))
    print(f"\n■ 적중 개수 분포")
    print(df["적중 개수"].value_counts().sort_index().to_string())
    print(f"\n■ 전략 표시 교차검증")
    print(tr[["줄", "표시된 전략", "고정번호가 들어있는 전략", "표시와 일치"]].to_string(index=False))
    return df, hi, tr

if __name__ == "__main__":
    main()
