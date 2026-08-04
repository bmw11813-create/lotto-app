# -*- coding: utf-8 -*-
"""분배회피(T) 확률분포의 벡터화 계산 + 원본 로직 대조검증

원본: 유효조합 1500개 생성 → 대중성점수 오름차순 → 하위 5%(75개)에서 1개 무작위
대체: 유효조합 마스터풀 M개를 미리 만들어 두고, 회차별로 lastWin 항만 갱신해
      하위 5%를 뽑아 번호별 등장빈도를 계산 (표본 크기만 키운 동일 분포)
근거: popularity_score 중 회차마다 달라지는 항은 '직전회차와 3개↑ 겹침 +3' 하나뿐
"""
import numpy as np
import strategy_prob as sp

def valid_mask(a, lo, hi):
    """sp.is_valid 의 벡터화판. a는 (M,6) 오름차순 정렬 배열."""
    t = a.sum(1)
    ok = (t >= lo) & (t <= hi)
    ok &= (a <= 15).any(1) & ((a >= 16) & (a <= 30)).any(1) & (a >= 31).any(1)
    odd = (a % 2 == 1).sum(1)
    ok &= (odd >= 2) & (odd <= 4)
    ok &= (np.diff(a, axis=1) == 1).sum(1) <= 1
    return ok

def base_score(a):
    """sp.popularity_score 에서 lastWin 항만 뺀 부분의 벡터화판."""
    M = a.shape[0]
    p = np.zeros(M, np.int16)
    t = a.sum(1)
    p += np.where(t < 100, 5, np.where(t <= 119, 2, np.where(t <= 180, 0, np.where(t <= 200, 1, 3)))).astype(np.int16)
    p += (np.maximum(0, 2 - (a >= 32).sum(1)) * 2).astype(np.int16)

    d1 = np.diff(a, axis=1) == 1                 # 연속런
    cur = np.ones(M, np.int16); mx = np.ones(M, np.int16)
    for i in range(5):
        cur = np.where(d1[:, i], cur + 1, 1).astype(np.int16)
        mx = np.maximum(mx, cur)
    p += np.where(mx >= 3, 2, 0).astype(np.int16)

    d = np.diff(a, axis=1)                       # 등차
    all_eq = (d[:, 0:1] == d).all(1)
    ar5 = np.zeros(M, bool)
    for i in range(2):                           # i+3 < 5  →  i = 0,1
        ar5 |= (d[:, i] == d[:, i+1]) & (d[:, i+1] == d[:, i+2]) & (d[:, i+2] == d[:, i+3])
    p += np.where(all_eq, 5, np.where(ar5, 2, 0)).astype(np.int16)

    b = a // 10                                  # 십의자리 4개 이상 몰림
    band = np.zeros(M, bool)
    for v in range(5):
        band |= (b == v).sum(1) >= 4
    p += np.where(band, 2, 0).astype(np.int16)

    seq = (a == np.arange(1, 7)).all(1)          # 유명 패턴
    m5 = (a % 5 == 0).all(1)
    p += np.where(seq | m5, 10, 0).astype(np.int16)
    return p

def make_pool(M, seed=4242, batch=100000):
    rng = np.random.default_rng(seed)
    out, got = [], 0
    while got < M:
        r = np.sort(rng.random((batch, 45)).argsort(1)[:, :6] + 1, axis=1).astype(np.int8)
        r = r[valid_mask(r.astype(np.int16), 120, 175)]
        out.append(r); got += len(r)
    pool = np.vstack(out)[:M].astype(np.int16)
    return pool, base_score(pool)

def t_probs(pool, base, last_win):
    """해당 회차의 T 전략 번호별 추출확률(%) 45개"""
    ind = np.zeros(46, bool); ind[list(last_win)] = True
    score = base + np.where(ind[pool].sum(1) >= 3, 3, 0).astype(np.int16)
    k = max(1, len(pool) // 20)                  # 하위 5%
    idx = np.argpartition(score, k)[:k]
    cnt = np.bincount(pool[idx].ravel(), minlength=46)[1:46]
    return cnt / k * 100.0

# ── 검증 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import random, collections
    rng = np.random.default_rng(1)
    a = np.sort(rng.random((4000, 45)).argsort(1)[:, :6] + 1, axis=1).astype(np.int16)

    v_vec = valid_mask(a, 120, 175)
    v_ref = np.array([sp.is_valid(list(map(int, r)), 120, 175) for r in a])
    print("is_valid 일치:", bool((v_vec == v_ref).all()), f"({v_ref.sum()}/4000 통과)")

    b_vec = base_score(a)
    b_ref = np.array([sp.popularity_score(list(map(int, r)), None) for r in a])
    print("base_score 일치:", bool((b_vec == b_ref).all()))

    lw = [3, 8, 9, 22, 28, 42]
    s_vec = base_score(a) + np.where(np.isin(a, lw).sum(1) >= 3, 3, 0)
    s_ref = np.array([sp.popularity_score(list(map(int, r)), lw) for r in a])
    print("lastWin 포함 점수 일치:", bool((s_vec == s_ref).all()))

    # 분포 대조: 원본 gen_antipopular_line 2000줄 vs 벡터화판
    pool, base = make_pool(200000)
    print(f"마스터풀 {len(pool):,}개 생성 완료")
    pv = t_probs(pool, base, lw)

    rnd = random.Random(9)
    cnt = collections.Counter()
    N = 2000
    for _ in range(N):
        cnt.update(sp.gen_antipopular_line({"lastWin": lw}, rnd))
    ref = np.array([100 * cnt[n] / N for n in range(1, 46)])
    diff = np.abs(pv - ref)
    print(f"원본 {N}줄 vs 벡터화판 — 최대차 {diff.max():.2f}%p, 평균차 {diff.mean():.2f}%p"
          f"  (원본 몬테카를로 오차 ±{100*(0.13*0.87/N)**0.5:.2f}%p)")
    order_v = np.argsort(-pv)[:10] + 1
    order_r = np.argsort(-ref)[:10] + 1
    print("상위10 (벡터화):", list(order_v))
    print("상위10 (원본)  :", list(order_r))
