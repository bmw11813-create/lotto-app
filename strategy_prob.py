# -*- coding: utf-8 -*-
"""
로또 앱 7전략 "번호별 추출 확률" 계산기
- index.html 의 computeEngine / buildStrategies / buildPools / isValid /
  popularityScore / generateAntiPopularLine / generateLine 을 1:1 재현
- 몬테카를로로 각 전략이 1~45번을 뽑을 확률(%)을 실측

특이사항:
  앱은 셔플에 JS 의 `.sort(() => Math.random() - 0.5)` 를 사용한다.
  이는 균등 셔플이 아니며 V8 의 정렬 알고리즘(배열 길이<64 → 이진삽입정렬)에
  따라 편향된다. 이 스크립트는 V8 동작을 그대로 재현한 모드(v8)와
  공정한 Fisher-Yates 모드(fair)를 모두 계산해 편향 크기를 비교한다.

실행: python strategy_prob.py
"""
import json, os, random, urllib.request, urllib.parse
from collections import defaultdict

CACHE = "lotto_history.json"
N_SIM = 100000      # 풀 기반 6전략(X,Y,Z,W,V,U) 시뮬레이션 줄 수
N_SIM_T = 6000     # 분배회피(T)는 1줄당 후보 1500개 생성이라 별도(적게)

# ────────────────────────────────────────────────────────────────
# 0. 당첨번호 수집
# ────────────────────────────────────────────────────────────────
def load_history():
    """전체 회차 당첨번호. dhlottery 직접 호출은 차단되므로 공개 미러 사용."""
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    url = "https://smok95.github.io/lotto/results/all.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    hist = [{"round": r["draw_no"], "nums": sorted(r["numbers"]),
             "bonus": r["bonus_no"], "date": r["date"][:10]} for r in raw]
    hist.sort(key=lambda r: r["round"])
    json.dump(hist, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return hist

# ────────────────────────────────────────────────────────────────
# 1. computeEngine  (index.html 130~205행)
# ────────────────────────────────────────────────────────────────
def compute_engine(history):
    h = sorted(history, key=lambda r: -r["round"])[:20]   # 최신 20회
    recent = list(reversed(h))                             # 오래된→최신

    freq = {n: 0 for n in range(1, 46)}
    for r in h:
        for n in r["nums"]:
            freq[n] += 1

    last_seen = {n: 999 for n in range(1, 46)}
    for idx, r in enumerate(recent):
        ago = len(recent) - 1 - idx
        for n in r["nums"]:
            if ago < last_seen[n]:
                last_seen[n] = ago

    # Y 미출현폭탄: 0회 → 없으면 1회
    y_pool = [n for n in range(1, 46) if freq[n] == 0]
    if not y_pool:
        y_pool = [n for n in range(1, 46) if freq[n] == 1]
    Y_fixed = y_pool[:3]

    # X 보너스추적: 최근 4회 보너스 중 중복제거 후 3개
    seen, X_fixed = set(), []
    for r in h[:4]:
        b = r["bonus"]
        if b and b not in seen:
            seen.add(b); X_fixed.append(b)
    X_fixed = X_fixed[:3]

    # W 이월수: 직전 회차 본번호 6개
    W_fixed = list(h[0]["nums"])

    # Z 휴식회귀: 빈도4+ 이면서 최근 4회+ 안 나온 번호 (빈도 내림차순, 동점은 번호 오름차순)
    strong_rested = sorted([n for n in range(1, 46) if freq[n] >= 4 and last_seen[n] >= 4],
                           key=lambda n: -freq[n])
    Z_fixed = strong_rested[:3] if strong_rested else list(Y_fixed)
    Z_fallback = not strong_rested

    # 풀
    sorted_by_freq = sorted(range(1, 46), key=lambda n: -freq[n])   # 안정정렬=동점 번호오름차순
    strong_pool = [n for n in sorted_by_freq if freq[n] >= 4][:12]
    once_pool = [n for n in range(1, 46) if freq[n] <= 1]
    mid_pool = [n for n in range(1, 46) if freq[n] in (2, 3)]

    # V 최약끝수
    digit_count = {d: 0 for d in range(10)}
    for r in h:
        for n in r["nums"]:
            digit_count[n % 10] += 1
    weakest_digit = sorted(range(10), key=lambda d: digit_count[d])[0]
    V_fixed = [n for n in range(1, 46) if n % 10 == weakest_digit]

    # U 합계정밀
    sums = [sum(r["nums"]) for r in h]
    avg_sum = round(sum(sums) / len(sums))
    # JS Math.round 는 .5 를 위로 올림 → 파이썬 round(뱅커스)와 다를 수 있어 보정
    raw = sum(sums) / len(sums)
    avg_sum = int(raw + 0.5) if raw >= 0 else -int(-raw + 0.5)

    return {
        "rounds": len(h), "lastRound": h[0]["round"], "firstRound": recent[0]["round"],
        "freq": freq, "lastSeen": last_seen,
        "X_fixed": X_fixed, "Y_fixed": Y_fixed, "Z_fixed": Z_fixed, "Z_fallback": Z_fallback,
        "W_fixed": W_fixed, "V_fixed": V_fixed, "weakestDigit": weakest_digit,
        "digitCount": digit_count,
        "U_sumMin": max(90, avg_sum - 13), "U_sumMax": min(190, avg_sum + 13), "avgSum": avg_sum,
        "pools": {
            "미출현": [n for n in y_pool if freq[n] == 0],
            "일회": once_pool, "강세": strong_pool, "중간": mid_pool,
        },
        "recentBonuses": [r["bonus"] for r in h[:4]],
    }

STRAT_META = {
    "X": {"name": "보너스추적", "emoji": "🎯", "fixedMin": 1, "fixedMax": 2},
    "Y": {"name": "미출현폭탄", "emoji": "🚀", "fixedMin": 1, "fixedMax": 1},
    "Z": {"name": "휴식회귀",   "emoji": "🔄", "fixedMin": 1, "fixedMax": 1},
    "W": {"name": "이월수",     "emoji": "🔁", "fixedMin": 1, "fixedMax": 2},
    "V": {"name": "최약끝수",   "emoji": "✨", "fixedMin": 1, "fixedMax": 2},
    "U": {"name": "합계정밀",   "emoji": "🎲", "fixedMin": 0, "fixedMax": 0, "fixed": []},
    "T": {"name": "분배회피",   "emoji": "🤫", "special": "antipopular"},
}
ORDER = ["X", "Y", "Z", "W", "V", "U", "T"]

def build_strategies(eng):
    import copy
    s = copy.deepcopy(STRAT_META)
    s["X"]["fixed"] = eng["X_fixed"]
    s["Y"]["fixed"] = eng["Y_fixed"]
    s["Z"]["fixed"] = eng["Z_fixed"]
    s["W"]["fixed"] = eng["W_fixed"]
    s["V"]["fixed"] = eng["V_fixed"]
    s["U"]["sumMin"] = eng["U_sumMin"]; s["U"]["sumMax"] = eng["U_sumMax"]
    s["T"]["lastWin"] = eng["W_fixed"]
    return s

def build_pools(eng):
    P = eng["pools"]
    return {
        "미출현": P["미출현"] if P["미출현"] else P["일회"],
        "일회": P["일회"], "강세": P["강세"], "중간": P["중간"],
    }

# ────────────────────────────────────────────────────────────────
# 2. isValid / popularityScore  (index.html 230~285행)
# ────────────────────────────────────────────────────────────────
def is_valid(nums, sum_min=110, sum_max=160):
    if len(nums) != 6:
        return False
    s = sorted(nums)
    t = sum(s)
    if t < sum_min or t > sum_max:
        return False
    if not any(n <= 15 for n in s):  return False
    if not any(16 <= n <= 30 for n in s): return False
    if not any(n >= 31 for n in s): return False
    odd = sum(1 for n in s if n % 2 == 1)
    if odd < 2 or odd > 4:
        return False
    pairs = sum(1 for i in range(5) if s[i + 1] - s[i] == 1)
    if pairs > 1:
        return False
    return True

def popularity_score(arr, last_win):
    s = sorted(arr)
    p = 0
    t = sum(s)
    if t < 100:    p += 5
    elif t <= 119: p += 2
    elif t <= 180: p += 0
    elif t <= 200: p += 1
    else:          p += 3
    high_cnt = sum(1 for n in s if n >= 32)
    p += max(0, 2 - high_cnt) * 2
    run = max_run = 1
    for i in range(1, 6):
        if s[i] - s[i - 1] == 1:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
    if max_run >= 3:
        p += 2
    diffs = [s[i] - s[i - 1] for i in range(1, 6)]
    if all(d == diffs[0] for d in diffs):
        p += 5
    else:
        if any(diffs[i] == diffs[i+1] == diffs[i+2] == diffs[i+3] for i in range(len(diffs) - 3)):
            p += 2
    band = defaultdict(int)
    for n in s:
        band[n // 10] += 1
    if any(c >= 4 for c in band.values()):
        p += 2
    if last_win and len(set(s) & set(last_win)) >= 3:
        p += 3
    if s == list(range(1, 7)) or all(n % 5 == 0 for n in s):
        p += 10
    return p

# ────────────────────────────────────────────────────────────────
# 3. 셔플 — V8 재현판 vs 공정판
# ────────────────────────────────────────────────────────────────
def v8_random_sort(arr, rnd):
    """JS `arr.sort(() => Math.random() - 0.5)` 를 V8 TimSort 로 재현.
    길이<64 이면 minRunLength==n → 초기 run 탐색 후 전체 이진삽입정렬 1회."""
    n = len(arr)
    if n < 2:
        return list(arr)
    a = list(arr)
    cmp = lambda: rnd.random() - 0.5      # 비교 결과는 인자와 무관한 난수

    # CountAndMakeRun(0, n)
    run_len = 2
    is_desc = cmp() < 0
    for _ in range(2, n):
        order = cmp()
        if is_desc:
            if order >= 0: break
        else:
            if order < 0: break
        run_len += 1
    if is_desc:
        a[0:run_len] = a[0:run_len][::-1]

    if run_len >= n:
        return a

    # BinaryInsertionSort(low=0, start=run_len, high=n)
    start = run_len if run_len != 0 else 1
    for st in range(start, n):
        left, right = 0, st
        pivot = a[st]
        while left < right:
            mid = left + ((right - left) >> 1)
            if cmp() < 0:
                right = mid
            else:
                left = mid + 1
        a[left + 1:st + 1] = a[left:st]
        a[left] = pivot
    return a

def fair_shuffle(arr, rnd):
    a = list(arr)
    rnd.shuffle(a)
    return a

# ────────────────────────────────────────────────────────────────
# 4. generateLine  (index.html 287~340행)
# ────────────────────────────────────────────────────────────────
def gen_antipopular_line(cfg, rnd):
    CAND, pool, attempts = 1500, [], 0
    while len(pool) < CAND and attempts < 40000:
        attempts += 1
        arr = sorted(rnd.sample(range(1, 46), 6))
        if is_valid(arr, 120, 175):
            pool.append(arr)
    if not pool:
        return None
    scored = sorted(((popularity_score(a, cfg.get("lastWin")), a) for a in pool),
                    key=lambda x: x[0])          # 안정정렬 = JS sort 와 동일
    cut = max(1, len(scored) // 20)              # 하위 5%
    return scored[rnd.randrange(cut)][1]

def gen_line(key, STRATEGIES, POOLS, rnd, shuffle, trace=False):
    """trace=True 면 (완성된 줄, 그 줄에 실제로 투입된 고정번호 리스트) 를 반환."""
    cfg = STRATEGIES[key]
    if cfg.get("special") == "antipopular":
        line = gen_antipopular_line(cfg, rnd)
        return (line, []) if trace else line
    sum_min = cfg.get("sumMin") or 110
    sum_max = cfg.get("sumMax") or 160

    fill_pool = list(dict.fromkeys(POOLS["미출현"] + POOLS["일회"] + POOLS["강세"] + POOLS["중간"]))
    fixed = cfg.get("fixed") or []
    fmin, fmax = cfg["fixedMin"], cfg["fixedMax"]

    for _ in range(300):
        nums = []
        fixed_count = rnd.randrange(fmax - fmin + 1) + fmin
        shuf = shuffle(fixed, rnd)
        for i in range(min(fixed_count, len(shuf))):
            if shuf[i] not in nums:
                nums.append(shuf[i])
        used_fixed = list(nums)          # 이 줄에 실제로 투입된 고정번호
        fill = shuffle([n for n in fill_pool if n not in nums], rnd)
        for n in fill:
            if len(nums) >= 6: break
            nums.append(n)
        if len(nums) < 6:
            rest = shuffle([n for n in range(1, 46) if n not in nums], rnd)
            for n in rest:
                if len(nums) >= 6: break
                nums.append(n)
        arr = sorted(nums)
        if is_valid(arr, sum_min, sum_max):
            return (arr, used_fixed) if trace else arr
    return (None, []) if trace else None

# ────────────────────────────────────────────────────────────────
# 5. 시뮬레이션
# ────────────────────────────────────────────────────────────────
def simulate(eng, shuffle_mode="v8", seed=20260804):
    STRATEGIES, POOLS = build_strategies(eng), build_pools(eng)
    shuffle = v8_random_sort if shuffle_mode == "v8" else fair_shuffle
    rnd = random.Random(seed)
    probs, fails = {}, {}
    for key in ORDER:
        n_sim = N_SIM_T if key == "T" else N_SIM
        cnt = defaultdict(int); ok = 0
        for _ in range(n_sim):
            line = gen_line(key, STRATEGIES, POOLS, rnd, shuffle)
            if line is None:
                continue
            ok += 1
            for n in line:
                cnt[n] += 1
        probs[key] = {n: 100.0 * cnt[n] / ok for n in range(1, 46)}
        fails[key] = 100.0 * (n_sim - ok) / n_sim
    return probs, fails

# ────────────────────────────────────────────────────────────────
# 6. 출력
# ────────────────────────────────────────────────────────────────
def fmt_table(probs, eng):
    fixed_sets = {"X": set(eng["X_fixed"]), "Y": set(eng["Y_fixed"]), "Z": set(eng["Z_fixed"]),
                  "W": set(eng["W_fixed"]), "V": set(eng["V_fixed"]), "U": set(), "T": set()}
    fill_pool = set(build_pools(eng)["미출현"] + build_pools(eng)["일회"] +
                    build_pools(eng)["강세"] + build_pools(eng)["중간"])
    lines = []
    head = "| 번호 | " + " | ".join(f"{STRAT_META[k]['emoji']}{STRAT_META[k]['name']}({k})" for k in ORDER) + " | 평균 |"
    lines.append(head)
    lines.append("|" + "---|" * (len(ORDER) + 2))
    for n in range(1, 46):
        cells = []
        for k in ORDER:
            v = probs[k][n]
            mark = "*" if n in fixed_sets[k] else ""
            cells.append(f"{v:.1f}{mark}")
        avg = sum(probs[k][n] for k in ORDER) / len(ORDER)
        tag = "" if n in fill_pool else " ⛔"
        lines.append(f"| {n}{tag} | " + " | ".join(cells) + f" | {avg:.1f} |")
    return "\n".join(lines)

def main():
    hist = load_history()
    eng = compute_engine(hist)
    print(f"=== 엔진 기준: {eng['firstRound']}~{eng['lastRound']}회 ({eng['rounds']}회) ===")
    print(f"X 보너스추적 고정후보: {eng['X_fixed']}  (최근4회 보너스 {eng['recentBonuses']})")
    print(f"Y 미출현폭탄 고정후보: {eng['Y_fixed']}")
    print(f"Z 휴식회귀   고정후보: {eng['Z_fixed']} (fallback={eng['Z_fallback']})")
    print(f"W 이월수     고정후보: {eng['W_fixed']}")
    print(f"V 최약끝수   고정후보: {eng['V_fixed']} (끝수 {eng['weakestDigit']}, 출현 {eng['digitCount'][eng['weakestDigit']]}회)")
    print(f"U 합계정밀   합 범위 : {eng['U_sumMin']}~{eng['U_sumMax']} (평균 {eng['avgSum']})")
    P = eng["pools"]
    print(f"풀 → 미출현{P['미출현']} / 일회{P['일회']} / 강세{P['강세']} / 중간{P['중간']}")
    fill = list(dict.fromkeys(build_pools(eng)['미출현'] + P['일회'] + P['강세'] + P['중간']))
    print(f"FILL_POOL({len(fill)}개): {sorted(fill)}")
    print(f"제외된 번호: {sorted(set(range(1,46)) - set(fill))}")
    print(f"끝수별 출현: {eng['digitCount']}")
    print()

    for mode in ("v8", "fair"):
        probs, fails = simulate(eng, mode)
        print(f"\n########## 셔플모드 = {mode} ##########")
        print("생성실패율(%): " + ", ".join(f"{k}={fails[k]:.2f}" for k in ORDER))
        print(fmt_table(probs, eng))
        json.dump({k: probs[k] for k in ORDER},
                  open(f"prob_{mode}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
