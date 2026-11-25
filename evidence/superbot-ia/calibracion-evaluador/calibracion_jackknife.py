"""Calibración sintética del intervalo t con jackknife por bloques: tamaño del error según bloques y reparto."""

import math

import numpy as np

g = np.random.default_rng(3)
T975 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365}


def datos(K, n, e, icc, colas, reparto):
    s, c = np.zeros((2, K)), np.zeros((2, K))
    comun = g.normal(0, 7 * math.sqrt(icc), K)
    for j in range(2):
        if reparto == "igual":
            p = np.full(K, 1 / K)
        elif reparto == "desigual":
            p = g.dirichlet(np.full(K, 1.5))
        else:  # un bloque concentra la mitad de los casos de un grupo
            p = np.full(K, 0.5 / (K - 1))
            p[j] = 0.5
        b = g.choice(K, n, p=p)
        u = g.normal(0, 7 * math.sqrt(icc), K)
        z = g.normal(0, 1, n) if not colas else g.standard_t(4, n) / math.sqrt(2)
        x = comun[b] + u[b] + z * 7 * math.sqrt(max(0, 1 - 2 * icc)) + (e if j == 0 else 0)
        s[j], c[j] = np.bincount(b, x, K), np.bincount(b, minlength=K)
    return s, c


def est(s, c):
    return s[0].sum() / c[0].sum() - s[1].sum() / c[1].sum()


def intervalo(s, c):
    vale = c.sum(0) > 0
    s, c = s[:, vale], c[:, vale]
    K = s.shape[1]
    if K < 3:
        return None
    fuera = list(range(K))
    if any((np.delete(c, k, 1).sum(1) == 0).any() for k in fuera):
        return None
    t = est(s, c)
    m = np.array([est(np.delete(s, k, 1), np.delete(c, k, 1)) for k in fuera])
    se = math.sqrt((K - 1) / K * ((m - t) ** 2).sum())
    return t - T975[K - 1] * se, t + T975[K - 1] * se


def corre(K, e, icc, colas, reparto, n=50, sims=3000):
    r = [0, 0, 0, 0]
    for _ in range(sims):
        ic = intervalo(*datos(K, n, e, icc, colas, reparto))
        r[3 if ic is None else 0 if ic[0] > 0 else 1 if ic[1] <= 0 else 2] += 1
    return [round(100 * x / sims, 1) for x in r]


print("K reparto icc colas efecto n -> APORTA / NO APORTA / INCONCLUSO / no calculable (%)")
for K in (3, 4, 5, 6, 7):
    for reparto in ("igual", "desigual", "concentrado"):
        for icc, colas in ((0, 0), (0.1, 1), (0.3, 0)):
            print(K, reparto, icc, colas, 0, 50, corre(K, 0, icc, colas, reparto))
for K in (4, 5, 6, 7):
    for e in (2, 4, 6):
        print(K, "igual", 0, 0, e, 50, corre(K, e, 0, 0, "igual"))
print(6, "igual", 0, 0, 0, 30, corre(6, 0, 0, 0, "igual", n=30))


def datos2(K, ga, gd, solape, icc, n=50):
    s, c = np.zeros((2, K)), np.zeros((2, K))
    for j, G in enumerate((ga, gd)):
        b = np.array(G)[g.integers(0, len(G), n)]
        e = g.normal(0, 1, K + 1)
        u = (e[1:] * math.sqrt(1 - solape) + e[:-1] * math.sqrt(solape)) * 7 * math.sqrt(icc)
        x = u[b] + g.normal(0, 7 * math.sqrt(1 - icc), n)
        s[j], c[j] = np.bincount(b, x, K), np.bincount(b, minlength=K)
    return s, c


def c2(*a, sims=4000):
    r = [0, 0, 0, 0]
    for _ in range(sims):
        ic = intervalo(*datos2(*a))
        r[3 if ic is None else 0 if ic[0] > 0 else 1 if ic[1] <= 0 else 2] += 1
    return [round(100 * x / sims, 1) for x in r]


for K, ga, gd in (
    (4, (0, 1), (2, 3)),
    (4, (0, 1, 2, 3), (0, 1)),
    (4, (0, 1, 2, 3), (0, 1, 2)),
    (4, (0, 1, 2, 3), (0, 1, 2, 3)),
    (6, tuple(range(6)), (0, 1)),
    (6, tuple(range(6)), (0, 1, 2)),
    (6, tuple(range(6)), (0, 1, 2, 3)),
    (6, (0, 1, 2), (3, 4, 5)),
    (6, (0, 1, 2, 3), (2, 3, 4, 5)),
    (7, tuple(range(7)), (0, 1, 2)),
    (7, tuple(range(7)), (0, 1, 2, 3)),
):
    print(K, ga, gd, "icc0", c2(K, ga, gd, 0, 0), "icc.2", c2(K, ga, gd, 0, 0.2))
for K in (4, 6, 7):
    print(
        "solape",
        K,
        [c2(K, tuple(range(K)), tuple(range(K)), sol, icc) for sol, icc in ((0.2, 0.2), (0.5, 0.2), (0.5, 0.4))],
    )
