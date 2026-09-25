"""Estatísticas descritivas e cobertura de apostas simples da Mega-Sena.

Em sorteios uniformes e independentes, todas as combinações de seis dezenas
têm a mesma probabilidade. Frequência, atraso e score não preveem o sorteio.
"""
from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable, Mapping
from itertools import combinations
from math import comb

from .compare import conferir_historico, normalizar_historico, normalize_jogo

TOTAL_COMBINACOES = comb(60, 6)
AVISO_ESTATISTICO = (
    "Todas as combinações de 6 dezenas têm a mesma chance em sorteios justos e "
    "independentes. Frequências e atrasos descrevem o passado; não aumentam a "
    "chance futura. Diversificação organiza a cobertura entre apostas."
)


def _limite_inteiro(valor: int, nome: str, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
        raise ValueError(f"{nome} deve ser inteiro entre {minimo} e {maximo}.")
    return valor


def score_jogo(nums: list[int], freq: Counter[int] | None = None) -> float:
    """Índice de equilíbrio visual legado, sem interpretação de probabilidade.

    Mantido para compatibilidade. O gerador não usa este índice para classificar
    chances nem favorece números historicamente frequentes.
    """
    nums = normalize_jogo(nums)
    pares = sum(n % 2 == 0 for n in nums)
    score = 1.0 - abs(2 * pares - 6) / 6.0
    faixas = [sum(inicio <= n <= inicio + 19 for n in nums) for inicio in (1, 21, 41)]
    score += 0.6 - (max(faixas) - min(faixas)) * 0.15
    sequencia = maior = 1
    for anterior, atual in zip(nums, nums[1:]):
        sequencia = sequencia + 1 if atual == anterior + 1 else 1
        maior = max(maior, sequencia)
    if maior >= 3:
        score -= 0.25 * (maior - 2)
    if sum(n <= 10 for n in nums) >= 4:
        score -= 0.25
    if sum(n >= 51 for n in nums) >= 4:
        score -= 0.25
    if freq:
        valores = [freq.get(n, 0) for n in nums]
        media_global = sum(freq.get(n, 0) for n in range(1, 61)) / 60
        score -= min(0.35, abs(sum(valores) / 6 - media_global) / (media_global + 1e-9) * 0.15)
    return score


def gerar_jogos_sugeridos(
    n_sugestoes: int = 10,
    amostras: int = 20000,
    freq: Counter[int] | None = None,
    seed: int | None = None,
    *,
    estrategia: str = "diversificada",
    excluir: Iterable[Iterable[int]] | None = None,
) -> list[list[int]]:
    """Gera apostas distintas, aleatórias ou com menos sobreposição.

    Na estratégia diversificada, amostras é o orçamento total de candidatos,
    repartido entre as apostas. A escolha minimiza, nesta ordem, reutilização
    de trincas, de pares e de dezenas nas apostas deste lote. Não é previsão
    nem garantia de cobertura ótima de quadras/quinas. freq é aceito por
    compatibilidade; não é usado como peso preditivo. excluir evita apostas
    inteiras já salvas, não exclui combinações porque saíram no passado.
    """
    _limite_inteiro(n_sugestoes, "Quantidade de sugestões", 1, 1000)
    _limite_inteiro(amostras, "Quantidade de amostras", 1, 100000)
    if estrategia not in {"aleatoria", "diversificada"}:
        raise ValueError("Estratégia deve ser 'aleatoria' ou 'diversificada'.")
    if estrategia == "diversificada" and amostras < n_sugestoes:
        raise ValueError("Amostras deve ser pelo menos a quantidade de sugestões.")
    vistos = {tuple(normalize_jogo(jogo)) for jogo in (() if excluir is None else excluir)}
    if TOTAL_COMBINACOES - len(vistos) < n_sugestoes:
        raise ValueError("Não há combinações disponíveis suficientes.")
    rng = random.Random(seed)
    uso_dezenas: Counter = Counter()
    uso_pares: Counter = Counter()
    uso_trincas: Counter = Counter()
    jogos = []
    orcamento, resto = divmod(amostras, n_sugestoes)
    for indice in range(n_sugestoes):
        quantidade = orcamento + (indice < resto) if estrategia == "diversificada" else 1
        melhor = None
        melhor_custo = None
        for _ in range(quantidade):
            # Limite explícito evita laço sem fim com exclusões quase exaustivas.
            for _tentativa in range(10000):
                candidato = tuple(sorted(rng.sample(range(1, 61), 6)))
                if candidato not in vistos:
                    break
            else:
                raise ValueError("Não foi possível obter apostas livres; reduza as exclusões.")
            if estrategia == "aleatoria":
                melhor = candidato
                break
            custo = (
                sum(uso_trincas[trinca] for trinca in combinations(candidato, 3)),
                sum(uso_pares[par] for par in combinations(candidato, 2)),
                sum(uso_dezenas[dezena] for dezena in candidato),
            )
            if melhor_custo is None or custo < melhor_custo:
                melhor, melhor_custo = candidato, custo
            # Zero é o mínimo global e dispensa candidatos adicionais.
            if custo == (0, 0, 0):
                break
        assert melhor is not None
        vistos.add(melhor)
        uso_dezenas.update(melhor)
        uso_pares.update(combinations(melhor, 2))
        uso_trincas.update(combinations(melhor, 3))
        jogos.append(list(melhor))
    return jogos


def prob_acertar_sena() -> float:
    return 1.0 / TOTAL_COMBINACOES


def probabilidades_jogo_simples() -> dict:
    """Hipergeométrica exata: prêmios com exatamente 6, 5 ou 4 acertos.

    A fração exata está em favoraveis/total; probabilidade e um_em são decimais.
    """
    resultado = {}
    for nome, acertos in (("sena", 6), ("quina", 5), ("quadra", 4)):
        favoraveis = comb(6, acertos) * comb(54, 6 - acertos)
        resultado[nome] = {
            "favoraveis": favoraveis,
            "total": TOTAL_COMBINACOES,
            "probabilidade": favoraveis / TOTAL_COMBINACOES,
            "um_em": TOTAL_COMBINACOES / favoraveis,
        }
    return resultado


def cobertura_sena(jogos: Iterable[Iterable[int]]) -> float:
    """Chance exata de uma sena, com este conjunto, em um único sorteio.

    Cada aposta distinta cobre um resultado; duplicatas não somam cobertura.
    Não multiplicar probabilidades de quadra/quina assim: seus eventos podem
    se sobrepor entre apostas.
    """
    distintos = {tuple(normalize_jogo(jogo)) for jogo in jogos}
    return len(distintos) / TOTAL_COMBINACOES


def analisar_historico(concursos: Iterable[Mapping], top_pares: int = 20) -> dict:
    """Analisa todos os registros fornecidos, sem recorte por recência.

    O atraso é medido em registros observados desde a última ocorrência, não em
    calendário. Para dezenas ausentes em toda a amostra, é um limite inferior.
    Completude refere-se ao concurso 1 até o último número presente, sem
    confirmar que o último concurso oficial já foi importado.
    """
    _limite_inteiro(top_pares, "Quantidade de pares", 0, 1770)
    historico = normalizar_historico(concursos)
    quantidade = len(historico)
    frequencias: Counter = Counter()
    pares_frequentes: Counter = Counter()
    distribuicao_pares: Counter = Counter()
    ultima_ocorrencia = {}
    somas = []
    for indice, concurso in enumerate(historico):
        dezenas = concurso["dezenas"]
        frequencias.update(dezenas)
        pares_frequentes.update(combinations(dezenas, 2))
        distribuicao_pares[sum(n % 2 == 0 for n in dezenas)] += 1
        somas.append(sum(dezenas))
        for dezena in dezenas:
            ultima_ocorrencia[dezena] = indice
    ultimo = historico[-1]["numero"] if historico else None
    faltantes = ultimo - quantidade if ultimo else 0
    return {
        "total_concursos": quantidade,
        "primeiro_concurso": historico[0]["numero"] if historico else None,
        "ultimo_concurso": ultimo,
        "completo_ate_ultimo": bool(historico) and faltantes == 0,
        "concursos_faltantes": faltantes,
        "frequencias": [
            {
                "dezena": dezena,
                "ocorrencias": frequencias[dezena],
                "percentual": 100 * frequencias[dezena] / quantidade if quantidade else 0.0,
                "percentual_esperado": 10.0,
                "ocorrencias_esperadas": quantidade / 10,
                "atraso": quantidade - 1 - ultima_ocorrencia.get(dezena, -1),
                "nunca_observada": dezena not in ultima_ocorrencia,
            }
            for dezena in range(1, 61)
        ],
        "distribuicao_pares": {pares: distribuicao_pares[pares] for pares in range(7)},
        "soma": {
            "min": min(somas) if somas else None,
            "max": max(somas) if somas else None,
            "media": sum(somas) / quantidade if quantidade else None,
            "esperada": 183.0,
        },
        "pares_frequentes": [
            {"dezenas": list(par), "ocorrencias": contagem}
            for par, contagem in sorted(pares_frequentes.items(), key=lambda item: (-item[1], item[0]))[:top_pares]
        ],
        "aviso": AVISO_ESTATISTICO,
        "nota_atraso": "Atraso em concursos observados; para nunca observadas, limite inferior da amostra.",
    }


def _resumo_acertos(contagem: Counter) -> dict:
    total = sum(contagem.values())
    return {
        "distribuicao_acertos": {acertos: contagem[acertos] for acertos in range(7)},
        "quadras": contagem[4],
        "quinas": contagem[5],
        "senas": contagem[6],
        "melhor_acerto": max((acertos for acertos, n in contagem.items() if n), default=0),
        "media_acertos": sum(acertos * n for acertos, n in contagem.items()) / total if total else 0.0,
        "apostas_avaliadas": total,
    }


def backtest_cronologico(
    concursos: Iterable[Mapping],
    n_jogos: int = 10,
    treino_minimo: int = 30,
    max_concursos: int = 100,
    seed: int | None = 42,
    estrategia: str = "diversificada",
    amostras: int = 500,
) -> dict:
    """Compara carteiras simuladas com base aleatória de mesmo orçamento.

    Avalia no máximo os últimos max_concursos após o treino mínimo. Cada
    decisão só recebe concursos anteriores, incluindo todos os anteriores ao
    recorte avaliado. Sementes separadas e fixas tornam a auditoria reproduzível.
    Não escolhe a melhor semente nem ajusta parâmetros aos resultados de teste.
    Não estima lucro nem valida vantagem preditiva.
    """
    _limite_inteiro(n_jogos, "Jogos por concurso", 1, 200)
    _limite_inteiro(treino_minimo, "Treino mínimo", 1, 100000)
    _limite_inteiro(max_concursos, "Concursos de teste", 1, 500)
    _limite_inteiro(amostras, "Quantidade de amostras", n_jogos, 10000)
    if estrategia not in {"aleatoria", "diversificada"}:
        raise ValueError("Estratégia deve ser 'aleatoria' ou 'diversificada'.")
    historico = normalizar_historico(concursos)
    if len(historico) <= treino_minimo:
        raise ValueError("Histórico insuficiente: é preciso haver concursos após o treino mínimo.")
    inicio = max(treino_minimo, len(historico) - max_concursos)
    rng = random.Random(seed)
    sugeridos: Counter = Counter()
    aleatorios: Counter = Counter()
    frequencias_treino = Counter(n for c in historico[:inicio] for n in c["dezenas"])
    detalhes = []
    for indice in range(inicio, len(historico)):
        concurso = historico[indice]
        seed_sugeridos, seed_aleatorios = rng.getrandbits(64), rng.getrandbits(64)
        jogos = gerar_jogos_sugeridos(
            n_sugestoes=n_jogos, amostras=amostras,
            freq=frequencias_treino.copy(), seed=seed_sugeridos, estrategia=estrategia,
        )
        referencia = gerar_jogos_sugeridos(
            n_sugestoes=n_jogos, amostras=n_jogos, seed=seed_aleatorios, estrategia="aleatoria",
        )
        resultado = set(concurso["dezenas"])
        acertos_sugeridos = [len(set(jogo) & resultado) for jogo in jogos]
        acertos_aleatorios = [len(set(jogo) & resultado) for jogo in referencia]
        sugeridos.update(acertos_sugeridos)
        aleatorios.update(acertos_aleatorios)
        detalhes.append({
            "numero": concurso["numero"],
            "treino_ate": historico[indice - 1]["numero"],
            "treino_concursos": indice,
            "seed_sugeridos": seed_sugeridos,
            "seed_aleatorios": seed_aleatorios,
            "melhor_sugerido": max(acertos_sugeridos),
            "melhor_aleatorio": max(acertos_aleatorios),
        })
        # O resultado avaliado só entra no treino da próxima rodada.
        frequencias_treino.update(concurso["dezenas"])
    return {
        "avaliados": len(detalhes),
        "treino_minimo": treino_minimo,
        "n_jogos": n_jogos,
        "estrategia": estrategia,
        "seed": seed,
        "amostras": amostras,
        "sugeridos": _resumo_acertos(sugeridos),
        "aleatorios": _resumo_acertos(aleatorios),
        "detalhes": detalhes,
        "aviso": "Comparação descritiva em amostra finita; diferenças podem ocorrer ao acaso. " + AVISO_ESTATISTICO,
    }
