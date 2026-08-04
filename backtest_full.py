# -*- coding: utf-8 -*-
"""
로또 전략 백테스트 (전체 회차 자동 수집판)
- index.html 의 computeEngine / generateLine 고정번호 로직을 그대로 재현
- dhlottery 공식 API에서 1회~최신회차 당첨번호를 받아옴
- 각 회차 직전 20회로 전략 타깃을 만들고, 실제 당첨번호와의 적중을 랜덤 기대치와 비교

실행:  pip install requests  →  python backtest_full.py
"""
import math, json, time, os
import urllib.request

CACHE = "lotto_history.json"   # 받아온 당첨번호를 저장(재실행 시 재사용)

def fetch_round(no):
    url = f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={no}"
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8"))
        if d.get("returnValue") == "success":
            nums = sorted([d[f"drwtNo{i}"] for i in range(1,7)])
            return {"round": d["drwNo"], "nums": nums, "bonus": d["bnusNo"]}
    except Exception:
        return None
    return None

def load_history():
    data = {}
    if os.path.exists(CACHE):
        for r in json.load(open(CACHE, encoding="utf-8")):
            data[r["round"]] = r
    no = (max(data)+1) if data else 1
    print(f"{no}회부터 최신 회차까지 수집 중...")
    miss = 0
    while True:
        if no in data:
            no += 1; continue
        r = fetch_round(no)
        if r is None:
            miss += 1
            if miss >= 3: break      # 아직 추첨 안 된 회차 = 끝
            no += 1; continue
        miss = 0
        data[no] = r
        if no % 50 == 0: print(f"  ...{no}회")
        no += 1
        time.sleep(0.05)
    json.dump(list(data.values()), open(CACHE,"w",encoding="utf-8"), ensure_ascii=False)
    return data

def compute_engine(history):
    h = sorted(history, key=lambda r: r["round"], reverse=True)[:20]
    recent = list(reversed(h))
    freq = {i:0 for i in range(1,46)}
    for r in h:
        for n in r["nums"]: freq[n]+=1
    last = {i:999 for i in range(1,46)}
    for idx,r in enumerate(recent):
        ago = len(recent)-1-idx
        for n in r["nums"]:
            if ago < last[n]: last[n]=ago
    yPool = [n for n in freq if freq[n]==0] or [n for n in freq if freq[n]==1]
    Y = sorted(yPool)[:3]
    rb = [r["bonus"] for r in h[:4] if r["bonus"]]
    X = []
    for b in rb:
        if b not in X: X.append(b)
    X = X[:3]
    W = list(h[0]["nums"])
    sr = sorted([n for n in freq if freq[n]>=4 and last[n]>=4], key=lambda n:-freq[n])
    Z = sr[:3] if sr else list(Y)
    dc = {d:0 for d in range(10)}
    for r in h:
        for n in r["nums"]: dc[n%10]+=1
    wd = sorted(range(10), key=lambda d:dc[d])[0]
    V = [n for n in range(1,46) if n%10==wd]
    return {"X":X,"Y":Y,"Z":Z,"W":W,"V":V}

NAMES = {"X":"보너스추적","Y":"미출현폭탄","Z":"휴식회귀","W":"이월수","V":"최약끝수"}

def main():
    data = load_history()
    rs = sorted(data.keys())
    targets = [r for r in rs if r-20 >= rs[0]]   # 직전 20회가 있는 회차만
    keys = ["X","Y","Z","W","V"]
    hit = {k:0 for k in keys}; setsz = {k:0 for k in keys}; n = 0
    for R in targets:
        hist = [data[r] for r in rs if R-20 <= r < R]
        if len(hist) < 20: continue
        eng = compute_engine(hist); win = set(data[R]["nums"]); n += 1
        for k in keys:
            s = set(eng[k]); hit[k]+=len(win&s); setsz[k]+=len(s)
    print("\n" + "="*76)
    print(f"백테스트: {targets[0]}~{targets[-1]}회 중 {n}개 회차  (검증 슬롯 {n*6}개)")
    print("="*76)
    print(f"\n{'전략':<10}{'타깃평균':>8}{'실제적중':>8}{'실제%':>8}{'랜덤기대%':>9}{'차이':>7}{'유의성z':>9}")
    for k in keys:
        avgset = setsz[k]/n; actual = hit[k]/(n*6); rand = avgset/45
        N=n*6; mu=N*rand; sd=math.sqrt(N*rand*(1-rand))
        z=(hit[k]-mu)/sd if sd>0 else 0
        print(f"{NAMES[k]:<10}{avgset:>8.1f}{hit[k]:>8}{actual*100:>7.1f}%{rand*100:>8.1f}%{(actual-rand)*100:>+6.1f}%{z:>9.2f}")
    print("\n|z|<2 → 랜덤과 구별 불가(우연). 표본이 커질수록 모든 전략이 0(랜덤)으로 수렴합니다.")

if __name__ == "__main__":
    main()
