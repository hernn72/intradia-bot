import numpy as np

g = np.random.default_rng(2)
T975 = {3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160}


def datos(K, n, e, icc, esc):
    s = np.zeros((2, K))
    c = np.zeros((2, K))
    com = g.normal(0, 7 * np.sqrt(icc), K)  # choque común a ambos grupos
    for j in range(2):
        b = g.integers(0, K, n)
        u = g.normal(0, 7 * np.sqrt(icc), K)
        z = g.normal(0, 1, n) if esc == 0 else (g.standard_t(4, n) / np.sqrt(2))
        x = com[b] + u[b] + z * 7 * np.sqrt(max(0, 1 - 2 * icc)) + (e if j == 0 else 0)
        s[j] = np.bincount(b, x, K)
        c[j] = np.bincount(b, minlength=K)
    return s, c


def est(s, c):
    return s[0].sum() / c[0].sum() - s[1].sum() / c[1].sum()


def perc(s, c, B=1000):
    K = s.shape[1]
    ix = g.integers(0, K, (B, K))
    S = s[:, ix].sum(2)
    C = c[:, ix].sum(2)
    ok = (C > 0).all(0)
    d = np.sort(S[0][ok] / C[0][ok] - S[1][ok] / C[1][ok])
    m = len(d)
    return d[int(0.025 * m)], d[int(np.ceil(0.975 * m)) - 1]


def jack(s, c):
    K = s.shape[1]
    t = est(s, c)
    m = np.array([est(np.delete(s, k, 1), np.delete(c, k, 1)) for k in range(K)])
    se = np.sqrt((K - 1) / K * ((m - t) ** 2).sum())
    q = T975[K - 1]
    return t - q * se, t + q * se


def corre(f, K, e, icc, esc=0, sims=1500):
    r = [0, 0, 0]
    for _ in range(sims):
        lo, hi = f(*datos(K, 50, e, icc, esc))
        r[0 if lo > 0 else 1 if hi <= 0 else 2] += 1
    return [round(100 * x / sims, 1) for x in r]


print("metodo K icc colas efecto -> APORTA/NO/INCONCLUSO")
for nom, f in (("percentil", perc), ("jackknife-t", jack)):
    for K in (6, 7):
        for icc, esc in ((0, 0), (0.1, 0), (0.1, 1)):
            print(nom, K, icc, esc, 0, corre(f, K, 0, icc, esc))
    for e in (2, 4, 6):
        print(nom, 6, 0, 0, e, corre(f, 6, e, 0))
    print(nom, 12, 0.1, 0, 0, corre(f, 12, 0, 0.1))
