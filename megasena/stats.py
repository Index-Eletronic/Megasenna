from __future__ import annotations
import random
from collections import Counter

def score_jogo(nums: list[int], freq: Counter[int] | None = None) -> float:
    """
    Score heurístico:
    - equilíbrio par/ímpar (ideal ~3/3)
    - diversidade de faixas (1-20, 21-40, 41-60)
    - penaliza sequências longas e padrões muito 'óbvios'
    - opcional: usa freq histórica para evitar extremos (nem só "quentes", nem só "frias")
    """
    nums = sorted(nums)

    # par/ímpar
    pares = sum(1 for n in nums if n % 2 == 0)
    impares = 6 - pares
    score = 1.0 - (abs(pares - impares) / 6.0)  # máximo quando 3/3

    # faixas
    buckets = [
        sum(1 for n in nums if 1 <= n <= 20),
        sum(1 for n in nums if 21 <= n <= 40),
        sum(1 for n in nums if 41 <= n <= 60),
    ]
    # melhor quando espalha, evita 5-1-0 etc.
    score += 0.6 - (max(buckets) - min(buckets)) * 0.15

    # penaliza sequência (ex: 10,11,12)
    longest_run = 1
    run = 1
    for i in range(1, len(nums)):
        if nums[i] == nums[i-1] + 1:
            run += 1
            longest_run = max(longest_run, run)
        else:
            run = 1
    if longest_run >= 3:
        score -= 0.25 * (longest_run - 2)

    # penaliza “muito baixo” ou “muito alto” concentrado
    if sum(1 for n in nums if n <= 10) >= 4:
        score -= 0.25
    if sum(1 for n in nums if n >= 51) >= 4:
        score -= 0.25

    # opcional: frequência histórica (se fornecida)
    if freq:
        # puxa o jogo para o “meio” da distribuição (evita só quentes ou só frias)
        vals = [freq[n] for n in nums]
        avg = sum(vals) / len(vals)
        # penaliza se for muito extremo comparado à média global
        global_avg = sum(freq.values()) / len(freq) if len(freq) else avg
        score -= min(0.35, abs(avg - global_avg) / (global_avg + 1e-9) * 0.15)

    return score

def gerar_jogos_sugeridos(
    n_sugestoes: int = 10,
    amostras: int = 20000,
    freq: Counter[int] | None = None,
    seed: int | None = None
) -> list[list[int]]:
    """
    Gera muitos candidatos e escolhe os top-N pelo score.
    """
    rng = random.Random(seed)
    candidatos = []
    for _ in range(amostras):
        jogo = rng.sample(range(1, 61), 6)
        sc = score_jogo(jogo, freq=freq)
        candidatos.append((sc, sorted(jogo)))
    candidatos.sort(key=lambda x: x[0], reverse=True)

    # remove duplicados mantendo ordem
    vistos = set()
    out = []
    for _, jogo in candidatos:
        t = tuple(jogo)
        if t in vistos:
            continue
        vistos.add(t)
        out.append(jogo)
        if len(out) >= n_sugestoes:
            break
    return out

def prob_acertar_sena() -> float:
    # 1 / C(60,6) = 1 / 50.063.860
    # cálculo direto sem depender de libs
    from math import comb
    return 1.0 / comb(60, 6)