# -*- coding: utf-8 -*-
"""
종합 추천 생성기 — final_all.xlsx / final_all.html 생성
strategy_prob.py(전략 로직) · rank_tvec.py(분배회피 벡터화) 재활용

1부  이번 주 종합점수      : 17개 케이스에서 각 번호가 얼마나 선호되는지 → 종합점수 순위표
2부  최종 추천 5줄         : 종합점수 상위 번호로 유효조합 생성 (2줄 일반 + 3줄 분배회피)
3부  백테스트              : 과거 회차에서 종합점수 상위 번호가 실제로 잘 맞았는지 z검정

부가) strategy_hits.txt / strategy_rank.txt → .xlsx 변환

점수 규칙 (모든 케이스 공통)
  케이스별 선호도 r(n) ≥ 0 을 정의하고  점수(n) = 10 × r(n) / r의 평균
  → 평균적인 번호는 케이스당 10점. 17케이스 합계 평균 = 170점.

실행: python final_all.py
"""
import json, math, os, random, re
import numpy as np
import pandas as pd
import strategy_prob as sp
import rank_tvec as tv

SEED = 20260804
POOL_N = 1_000_000          # 조합 케이스용 마스터풀
T_POOL = 200_000            # 분배회피용 마스터풀
BT_ROUNDS = 300             # 3부 백테스트 회차 수(최신부터)
BT_SIM = 1000               # 3부 회차당 전략 시뮬 줄 수
NOW_SIM = 20000             # 1부 전략 TOP10 산출용 시뮬 줄 수(prob_v8.json 있으면 그걸 사용)
ORDER = sp.ORDER
SNAME = {k: f"{sp.STRAT_META[k]['emoji']}{sp.STRAT_META[k]['name']}" for k in ORDER}

# ══════════════════════════════════════════════════════════════
# 마스터풀 & 케이스 정의
# ══════════════════════════════════════════════════════════════
def make_pool(n, seed, batch=100_000):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range((n + batch - 1) // batch):
        r = np.sort(rng.random((batch, 45)).argsort(1)[:, :6] + 1, axis=1)
        out.append(r.astype(np.int8))
    return np.vstack(out)[:n]

def pts(r):
    """선호도 벡터 → 점수 (평균 10점)"""
    r = np.asarray(r, float)
    return 10.0 * r / r.mean()

def freq_pct(pool, mask):
    sel = pool[mask]
    if len(sel) == 0:
        return np.full(45, 6 / 45 * 100)
    return np.bincount(sel.ravel().astype(int), minlength=46)[1:46] / len(sel) * 100.0

def static_cases(pool):
    """회차와 무관한 조합 케이스 12개"""
    s = pool.sum(1).astype(int)
    odd = (pool % 2 == 1).sum(1)
    low = (pool <= 22).sum(1)
    b1 = (pool <= 15).sum(1); b2 = ((pool >= 16) & (pool <= 30)).sum(1); b3 = (pool >= 31).sum(1)
    C = {}
    for lo, hi in [(100, 120), (121, 140), (141, 160), (161, 180)]:
        C[f"합계 {lo}-{hi}"] = pts(freq_pct(pool, (s >= lo) & (s <= hi)))
    C["홀짝 3:3"] = pts(freq_pct(pool, odd == 3))
    C["홀짝 4:2"] = pts(freq_pct(pool, odd == 4))
    C["홀짝 2:4"] = pts(freq_pct(pool, odd == 2))
    C["고저 3:3"] = pts(freq_pct(pool, low == 3))
    C["고저 4:2"] = pts(freq_pct(pool, low == 4))
    C["고저 2:4"] = pts(freq_pct(pool, low == 2))
    C["3구간 2:2:2"] = pts(freq_pct(pool, (b1 == 2) & (b2 == 2) & (b3 == 2)))
    C["3구간 3:2:1"] = pts(freq_pct(pool, (b1 == 3) & (b2 == 2) & (b3 == 1)))
    return C

def cold_gaps(hist, end):
    """번호별 '몇 회 전에 마지막으로 나왔나' (end 직전까지만 사용)"""
    gap = {}
    for back, rec in enumerate(reversed(hist[:end])):
        for n in rec["nums"]:
            gap.setdefault(n, back)
        if len(gap) == 45:
            break
    return np.array([gap.get(n, 100) for n in range(1, 46)], float)

def strategy_top10(eng, rnd, nsim, pool_t, base_t, prob_override=None):
    """7전략 각각의 TOP10 번호 집합"""
    S, P = sp.build_strategies(eng), sp.build_pools(eng)
    tops, probs = {}, {}
    for k in ORDER:
        if prob_override and k in prob_override:
            p = prob_override[k]
        elif k == "T":
            p = tv.t_probs(pool_t, base_t, eng["W_fixed"])
        else:
            cnt = np.zeros(45); ok = 0
            for _ in range(nsim):
                line = sp.gen_line(k, S, P, rnd, sp.v8_random_sort)
                if line is None:
                    continue
                ok += 1
                for x in line:
                    cnt[x - 1] += 1
            p = cnt / max(ok, 1) * 100
        probs[k] = p
        tops[k] = set(int(i) + 1 for i in np.argsort(-p, kind="stable")[:10])
    return tops, probs

def dynamic_cases(eng, hist, end, tops):
    """회차마다 달라지는 데이터 기반 케이스 5개"""
    C = {}
    cons = np.array([sum(1 for k in ORDER if n in tops[k]) for n in range(1, 46)], float)
    C["전략합의 TOP10"] = pts(1 + cons)
    C["핫넘버(최근20회)"] = pts(1 + np.array([eng["freq"][n] for n in range(1, 46)], float))
    C["콜드넘버(장기미출현)"] = pts(1 + np.minimum(cold_gaps(hist, end), 60) / 10.0)
    carry = set(eng["W_fixed"])
    C["이월수(직전회차)"] = pts(np.array([3.0 if n in carry else 1.0 for n in range(1, 46)]))
    dc = eng["digitCount"]
    C["끝수다양성"] = pts(np.array([1.0 / (1 + dc[n % 10]) for n in range(1, 46)]))
    return C, cons

# ══════════════════════════════════════════════════════════════
# 2부 — 추천 줄 생성
# ══════════════════════════════════════════════════════════════
def band_ok(a):
    return any(x <= 15 for x in a) and any(16 <= x <= 30 for x in a) and any(x >= 31 for x in a)

def make_line(score, rnd, top_k=22, anti=False, tries=20000):
    cand = list(np.argsort(-score, kind="stable")[:top_k] + 1)
    w = np.array([score[n - 1] for n in cand], float)
    w = w / w.sum()
    best = None
    for _ in range(tries):
        pick = sorted(int(x) for x in np.random.default_rng(rnd.randrange(1 << 30))
                      .choice(cand, size=6, replace=False, p=w))
        t = sum(pick)
        if not (110 <= t <= 160) or not band_ok(pick):
            continue
        if anti:
            if sum(1 for x in pick if x >= 32) < 3:
                continue
            ps = sp.popularity_score(pick, None)
            if best is None or ps < best[0]:
                best = (ps, pick)
            if best[0] <= 0:
                break
        else:
            return pick, sum(score[n - 1] for n in pick) / 6
    if best:
        return best[1], sum(score[n - 1] for n in best[1]) / 6
    return None, 0.0

# ══════════════════════════════════════════════════════════════
# 출력 헬퍼
# ══════════════════════════════════════════════════════════════
def heat(v, lo, hi, c0=(232, 245, 233), c1=(27, 94, 32)):
    if hi <= lo or v != v:
        return "#ffffff", "#000000"
    t = max(0.0, min(1.0, (v - lo) / (hi - lo)))
    rgb = tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    fg = "#ffffff" if t > 0.55 else "#111111"
    return "#%02x%02x%02x" % rgb, fg

def df_html(df, heat_cols=(), title="", note=""):
    h = [f'<h2>{title}</h2>'] if title else []
    if note:
        h.append(f'<p class="note">{note}</p>')
    h.append('<div class="tw"><table>')
    h.append("<thead><tr>" + "".join(f"<th>{c}</th>" for c in df.columns) + "</tr></thead><tbody>")
    ranges = {c: (df[c].min(), df[c].max()) for c in heat_cols if c in df.columns}
    for _, row in df.iterrows():
        tds = []
        for c in df.columns:
            v = row[c]
            if c in ranges:
                bg, fg = heat(v, *ranges[c])
                tds.append(f'<td style="background:{bg};color:{fg};font-weight:600">'
                           f'{v:.1f}</td>' if isinstance(v, float) else
                           f'<td style="background:{bg};color:{fg};font-weight:600">{v}</td>')
            else:
                tds.append(f"<td>{v:.2f}</td>" if isinstance(v, float) else f"<td>{v}</td>")
        h.append("<tr>" + "".join(tds) + "</tr>")
    h.append("</tbody></table></div>")
    return "\n".join(h)

CSS = """
body{font-family:'Malgun Gothic','Segoe UI',sans-serif;margin:0;padding:24px;background:#f6f7f9;color:#1a1a1a}
.wrap{max-width:1280px;margin:0 auto}
h1{font-size:26px;margin:0 0 6px}h2{font-size:19px;margin:30px 0 10px;padding-left:10px;border-left:5px solid #047857}
h3{font-size:15px;margin:18px 0 8px;color:#374151}
.sub{color:#6b7280;font-size:13px;margin-bottom:18px}
.note{color:#6b7280;font-size:12.5px;margin:4px 0 10px;line-height:1.6}
.tw{overflow-x:auto;background:#fff;border:1px solid #e5e7eb;border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:13px}
th{background:#111827;color:#fff;padding:8px 10px;text-align:center;white-space:nowrap;position:sticky;top:0}
td{padding:6px 10px;text-align:center;border-top:1px solid #f0f0f0;white-space:nowrap}
tbody tr:hover td{background:#fffbe6!important;color:#111!important}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 18px;margin:12px 0}
.ball{display:inline-block;width:34px;height:34px;line-height:34px;border-radius:50%;color:#fff;
 font-weight:700;text-align:center;margin:2px 3px;font-size:14px}
.b1{background:#fbc400}.b2{background:#69c8f2}.b3{background:#ff7272}.b4{background:#aaa}.b5{background:#b0d840}
.tag{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11.5px;font-weight:700;margin-left:6px}
.t-anti{background:#fee2e2;color:#991b1b}.t-norm{background:#dbeafe;color:#1e40af}
.warn{background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;padding:14px 16px;margin:16px 0;font-size:13px;line-height:1.7}
.ok{color:#047857;font-weight:700}.no{color:#b91c1c;font-weight:700}
"""

def ball_html(n):
    c = "b1" if n <= 10 else "b2" if n <= 20 else "b3" if n <= 30 else "b4" if n <= 40 else "b5"
    return f'<span class="ball {c}">{n}</span>'

# ══════════════════════════════════════════════════════════════
def main():
    rnd = random.Random(SEED)
    hist = sp.load_history()
    print("마스터풀 생성 중…", flush=True)
    pool = make_pool(POOL_N, SEED)
    tpool, tbase = tv.make_pool(T_POOL)
    STATIC = static_cases(pool)
    print(f"  조합풀 {len(pool):,} / 분배회피풀 {len(tpool):,}", flush=True)

    # ─── 1부 ────────────────────────────────────────────────
    eng = sp.compute_engine(hist[-20:])
    override = None
    if os.path.exists("prob_v8.json"):
        pv = json.load(open("prob_v8.json", encoding="utf-8"))
        override = {k: np.array([pv[k][str(n)] for n in range(1, 46)]) for k in ORDER if k != "T"}
        print("  prob_v8.json 재사용(전략당 100,000줄)", flush=True)
    tops, probs = strategy_top10(eng, rnd, NOW_SIM, tpool, tbase, override)
    DYN, consensus = dynamic_cases(eng, hist, len(hist), tops)
    CASES = {**DYN, **STATIC}
    score = np.sum([CASES[c] for c in CASES], axis=0)

    df1 = pd.DataFrame({"번호": range(1, 46), "종합점수": score,
                        "전략합의(0~7)": consensus.astype(int)})
    for c in CASES:
        df1[c] = CASES[c]
    df1 = df1.sort_values("종합점수", ascending=False).reset_index(drop=True)
    df1.insert(0, "순위", range(1, 46))
    df1["종합점수"] = df1["종합점수"].round(1)
    for c in CASES:
        df1[c] = df1[c].round(1)

    # ─── 2부 ────────────────────────────────────────────────
    lines = []
    seen = set()
    for i in range(5):
        anti = i >= 2                       # 3~5번째 줄은 분배회피
        for _ in range(60):
            ln, avg = make_line(score, rnd, anti=anti)
            if ln and tuple(ln) not in seen:
                seen.add(tuple(ln)); break
        if ln:
            lines.append({"줄": i + 1, "유형": "분배회피" if anti else "종합점수",
                          "번호": " · ".join(f"{x:02d}" for x in ln), "_nums": ln,
                          "합계": sum(ln), "32이상": sum(1 for x in ln if x >= 32),
                          "홀수": sum(1 for x in ln if x % 2 == 1),
                          "대중성점수": sp.popularity_score(ln, eng["W_fixed"]),
                          "평균종합점수": round(avg, 1)})
    df2 = pd.DataFrame([{k: v for k, v in d.items() if k != "_nums"} for d in lines])

    # ─── 3부 백테스트 ───────────────────────────────────────
    print(f"3부 백테스트 {BT_ROUNDS}회차 시작…", flush=True)
    rnd2 = random.Random(999)
    ends = list(range(len(hist) - BT_ROUNDS, len(hist)))
    st = {kk: {"o": 0, "e": 0.0, "v": 0.0} for kk in ("TOP6", "TOP10", "BOT10")}
    rank_sum, rank_n, rank_pr = 0.0, 0, []
    for i, end in enumerate(ends):
        e = sp.compute_engine(hist[end - 20:end])
        tp, _ = strategy_top10(e, rnd2, BT_SIM, tpool, tbase)
        dyn, _ = dynamic_cases(e, hist, end, tp)
        sc = np.sum([dyn[c] for c in dyn] + [STATIC[c] for c in STATIC], axis=0)
        order = np.argsort(-sc, kind="stable") + 1
        win = set(hist[end]["nums"])
        for kk, sel in (("TOP6", set(map(int, order[:6]))),
                        ("TOP10", set(map(int, order[:10]))),
                        ("BOT10", set(map(int, order[-10:])))):
            m = len(sel)
            st[kk]["o"] += len(sel & win)
            st[kk]["e"] += 6 * m / 45
            st[kk]["v"] += m * (6 / 45) * (39 / 45) * (45 - m) / 44
        rr = {int(n): r + 1 for r, n in enumerate(order)}
        wr = [rr[n] for n in hist[end]["nums"]]
        rank_sum += sum(wr); rank_n += 6; rank_pr.append(sum(wr) / 6)
        if i % 50 == 0:
            print(f"  {i}/{len(ends)} (…{hist[end]['round']}회)", flush=True)

    rows3 = []
    for kk, lab in (("TOP6", "종합점수 1~6위"), ("TOP10", "종합점수 1~10위"), ("BOT10", "종합점수 36~45위")):
        a = st[kk]
        n_slots = a["e"] * 45 / 6                      # 총 (회차×번호) 슬롯 수
        rate = 100 * a["o"] / n_slots
        z = (a["o"] - a["e"]) / math.sqrt(a["v"])
        rows3.append({"구간": lab, "적중 횟수": a["o"], "기대 횟수": round(a["e"], 1),
                      "적중률%": round(rate, 3), "무작위 기대%": round(100 * 6 / 45, 3),
                      "z": round(z, 2), "판정": "예측력 있음" if abs(z) > 2.58 else "예측력 없음"})
    mu = sum(rank_pr) / len(rank_pr)
    se = math.sqrt(sum((x - mu) ** 2 for x in rank_pr) / (len(rank_pr) - 1) / len(rank_pr))
    zr = (rank_sum / rank_n - 23.0) / se
    rows3.append({"구간": "당첨번호 평균순위", "적중 횟수": "—", "기대 횟수": "—",
                  "적중률%": round(rank_sum / rank_n, 2), "무작위 기대%": 23.0,
                  "z": round(zr, 2), "판정": "예측력 있음" if abs(zr) > 2.58 else "예측력 없음"})
    df3 = pd.DataFrame(rows3)

    # ─── 저장: xlsx ─────────────────────────────────────────
    desc = pd.DataFrame({
        "케이스": list(CASES.keys()),
        "종류": ["데이터기반"] * len(DYN) + ["조합구조"] * len(STATIC),
        "설명": ["7전략 각각의 TOP10 에 몇 번 포함되는가",
                "최근 20회 출현 횟수가 많을수록 높음",
                "마지막 출현 이후 경과 회차가 클수록 높음",
                f"직전 {eng['lastRound']}회 당첨번호 6개에 가중 3배",
                "최근 20회에서 적게 나온 끝자리일수록 높음"] +
               [f"그 조건을 만족하는 조합들에서 번호가 등장하는 비율" for _ in STATIC],
        "점수 최소": [round(CASES[c].min(), 1) for c in CASES],
        "점수 최대": [round(CASES[c].max(), 1) for c in CASES],
        "변별력(최대-최소)": [round(CASES[c].max() - CASES[c].min(), 1) for c in CASES],
    })
    with pd.ExcelWriter("final_all.xlsx", engine="openpyxl") as w:
        df1.to_excel(w, sheet_name="1부_종합점수", index=False)
        desc.to_excel(w, sheet_name="1부_케이스설명", index=False)
        df2.to_excel(w, sheet_name="2부_추천5줄", index=False)
        df3.to_excel(w, sheet_name="3부_백테스트", index=False)
    print("저장 → final_all.xlsx")

    # ─── 저장: html ─────────────────────────────────────────
    H = [f"<style>{CSS}</style><div class='wrap'>"]
    H.append(f"<h1>🎰 종합 추천 생성기</h1>")
    H.append(f"<div class='sub'>기준 {eng['firstRound']}~{eng['lastRound']}회 (최근 20회) · "
             f"다음 {eng['lastRound']+1}회 대상 · 조합풀 {POOL_N:,}개 · "
             f"각 회차는 직전 20회만 사용(미래정보 차단)</div>")
    H.append("<div class='warn'>⚠️ <b>먼저 읽어주세요.</b> 3부 백테스트 결과, 이 종합점수는 "
             "실제 당첨번호를 무작위보다 잘 맞히지 <b>못합니다</b>. 아래 표는 "
             "'앱이 어떤 기준으로 번호를 고르는가'를 보여주는 것이지 당첨 확률을 높이지 않습니다. "
             "로또는 무작위 추첨입니다. (도박문제 상담 1336)</div>")

    H.append(df_html(df1[["순위", "번호", "종합점수", "전략합의(0~7)"] + list(CASES.keys())],
                     heat_cols=["종합점수"] + list(CASES.keys()),
                     title="1부 · 번호별 종합점수 순위표",
                     note="케이스별 점수는 '평균 번호 = 10점' 기준. 17케이스 합계 평균 170점. "
                          "색이 진할수록 그 케이스에서 선호되는 번호."))
    H.append(df_html(desc, heat_cols=["변별력(최대-최소)"], title="1부 · 케이스 정의와 변별력",
                     note="변별력이 0에 가까운 케이스는 번호를 사실상 구분하지 못합니다."))

    H.append("<h2>2부 · 최종 추천 5줄</h2>")
    for d in lines:
        tag = ('<span class="tag t-anti">분배회피</span>' if d["유형"] == "분배회피"
               else '<span class="tag t-norm">종합점수</span>')
        H.append(f"<div class='card'><b>{d['줄']}줄</b>{tag}<br>"
                 + "".join(ball_html(x) for x in d["_nums"])
                 + f"<div class='note'>합계 {d['합계']} · 32이상 {d['32이상']}개 · 홀수 {d['홀수']}개 · "
                   f"대중성점수 {d['대중성점수']}(낮을수록 당첨금 나눌 인원 적음) · "
                   f"평균 종합점수 {d['평균종합점수']}</div></div>")
    H.append("<p class='note'>모든 줄은 합계 110~160 및 1-15/16-30/31-45 세 구간을 모두 포함하는 "
             "유효조합입니다. 분배회피 줄은 32번 이상을 3개 이상 넣어 당첨 시 분배 인원을 줄입니다.</p>")

    H.append(df_html(df3, heat_cols=[], title=f"3부 · 백테스트 (최근 {BT_ROUNDS}회차)",
                     note=f"각 회차마다 직전 20회만으로 종합점수를 다시 계산해 실제 당첨번호와 대조. "
                          f"|z| &gt; 2.58 이어야 '우연이 아니다'라고 말할 수 있습니다."))
    verdict = "모든 구간에서 예측력이 확인되지 않았습니다" if all(abs(r["z"]) <= 2.58 for r in rows3) \
              else "일부 구간에서 유의한 차이가 나타났습니다 — 재검증 필요"
    H.append(f"<div class='warn'><b>3부 결론:</b> {verdict}. "
             f"종합점수 상위 10개 번호의 적중률은 {rows3[1]['적중률%']}% 로 무작위 기대치 13.333% 와 "
             f"통계적으로 구분되지 않으며, 실제 당첨번호의 평균 순위도 {rows3[3]['적중률%']}위로 "
             f"무작위 기준선 23위와 같습니다.</div>")
    H.append("</div>")
    open("final_all.html", "w", encoding="utf-8").write("\n".join(H))
    print("저장 → final_all.html")

    convert_existing()
    return df1, df2, df3


# ══════════════════════════════════════════════════════════════
# 기존 txt → xlsx 변환
# ══════════════════════════════════════════════════════════════
def convert_existing():
    if os.path.exists("strategy_hits.txt"):
        rows, summ = [], []
        for ln in open("strategy_hits.txt", encoding="utf-8"):
            m = re.match(r"^\s*(\d+)\s*\|\s*([\d-]+)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*$", ln)
            if m:
                rows.append({"회차": int(m.group(1)), "날짜": m.group(2),
                             "맞은 번호": int(m.group(3)), "집은 전략": m.group(4),
                             "전략 수": len(m.group(4).split(","))})
            m2 = re.match(r"^([^\s\d].*?)\s{2,}([\d,]+)\s+([\d,]+)\s+([\d.]+)%\s+([+\-][\d.]+)%p", ln)
            if m2:
                summ.append({"전략": m2.group(1).strip(), "적중 횟수": int(m2.group(2).replace(",", "")),
                             "총 후보 수": int(m2.group(3).replace(",", "")),
                             "적중률%": float(m2.group(4)), "기대 대비%p": float(m2.group(5))})
        with pd.ExcelWriter("strategy_hits.xlsx", engine="openpyxl") as w:
            pd.DataFrame(rows).to_excel(w, sheet_name="적중목록", index=False)
            if summ:
                pd.DataFrame(summ).to_excel(w, sheet_name="전략별요약", index=False)
        print(f"저장 → strategy_hits.xlsx ({len(rows):,}행)")

    if os.path.exists("strategy_rank.txt"):
        cols = ["보너스", "미출현", "휴식", "이월", "끝수", "합계", "분배"]
        rows = []
        for ln in open("strategy_rank.txt", encoding="utf-8"):
            m = re.match(r"^\s*(\d+)\s*\|\s*([\d-]+)\s*\|\s*(\d+)\s*\|((?:\s+\d+){7})\s*$", ln)
            if m:
                v = [int(x) for x in m.group(4).split()]
                rows.append({"회차": int(m.group(1)), "날짜": m.group(2), "당첨번호": int(m.group(3)),
                             **{c: v[i] for i, c in enumerate(cols)},
                             "7전략 평균순위": round(sum(v) / 7, 2)})
        df = pd.DataFrame(rows)
        summ = pd.DataFrame([{"전략": c, "당첨번호 평균순위": round(df[c].mean(), 2),
                              "무작위 기준": 23.0,
                              "차이": round(df[c].mean() - 23, 2)} for c in cols])
        with pd.ExcelWriter("strategy_rank.xlsx", engine="openpyxl") as w:
            df.to_excel(w, sheet_name="회차별순위", index=False)
            summ.to_excel(w, sheet_name="전략별평균", index=False)
        print(f"저장 → strategy_rank.xlsx ({len(df):,}행)")


if __name__ == "__main__":
    main()
