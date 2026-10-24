"""Cobertura exata da união dos resultados premiados de uma carteira."""
from __future__ import annotations

import random
import json
from pathlib import Path
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from itertools import combinations
from math import comb

from .compare import normalize_jogo, comparar_jogo

TOTAL = comb(60, 6)
LIMITE = 200


def importar_carteira(caminho):
    payload = json.loads(Path(caminho).read_text(encoding='utf-8-sig'))
    registros = payload.get('jogos') if isinstance(payload, dict) else payload
    if not isinstance(registros, list) or not registros:
        raise ValueError('O JSON deve conter uma lista de jogos ou o campo jogos.')
    jogos = [r.get('dezenas') if isinstance(r, dict) else r for r in registros]
    return _carteira(jogos)


def preco_centavos(texto):
    try:
        valor = Decimal(str(texto).replace(',', '.'))
        if not valor.is_finite() or valor <= 0 or valor != valor.quantize(Decimal('.01')):
            raise ValueError
        return int(valor * 100)
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError('Informe um preço positivo com até duas casas decimais.') from None


def _carteira(jogos):
    jogos = [normalize_jogo(j) for j in jogos]
    if len(jogos) > LIMITE:
        raise ValueError(f'O cálculo exato aceita até {LIMITE} jogos por carteira.')
    return jogos


def _mascara(jogo):
    return sum(1 << (n - 1) for n in jogo)


def _vizinhos(jogo, minimo):
    dentro = [1 << (n - 1) for n in jogo]
    fora = [1 << (n - 1) for n in range(1, 61) if n not in jogo]
    for acertos in range(minimo, 7):
        for parte in combinations(dentro, acertos):
            base = sum(parte)
            for complemento in combinations(fora, 6 - acertos):
                yield base | sum(complemento)


def cobertura_uniao(jogos, minimo):
    """Conta resultados distintos com ao menos uma aposta com >= minimo acertos.

    Componentes sem eventos em comum são somados. Dentro de cada componente,
    cada sorteio é representado por um inteiro de 60 bits e contado uma vez.
    """
    if minimo not in (4, 5, 6):
        raise ValueError('O mínimo de acertos deve ser 4, 5 ou 6.')
    jogos = list(dict.fromkeys(tuple(j) for j in _carteira(jogos)))
    if minimo == 6:
        return len(jogos)
    masks = [_mascara(j) for j in jogos]
    pendentes = set(range(len(jogos)))
    total = 0
    por_jogo = sum(comb(6, k) * comb(54, 6-k) for k in range(minimo, 7))
    while pendentes:
        componente = [pendentes.pop()]
        for i in componente:
            vizinhos = {j for j in pendentes if (masks[i] & masks[j]).bit_count() >= 2 * minimo - 6}
            componente.extend(vizinhos)
            pendentes.difference_update(vizinhos)
        if len(componente) == 1:
            total += por_jogo
        else:
            resultados = set()
            for i in componente:
                resultados.update(_vizinhos(jogos[i], minimo))
            total += len(resultados)
    return total


def analisar_carteira(jogos, valor_centavos=600):
    jogos = _carteira(jogos)
    if isinstance(valor_centavos, bool) or not isinstance(valor_centavos, int) or valor_centavos <= 0:
        raise ValueError('Preço em centavos deve ser um inteiro positivo.')
    unicos = list(dict.fromkeys(tuple(j) for j in jogos))
    faixas = {}
    for nome, minimo in [('quadra_ou_mais', 4), ('quina_ou_mais', 5), ('sena', 6)]:
        favoraveis = cobertura_uniao(unicos, minimo)
        faixas[nome] = {'favoraveis': favoraveis, 'total': TOTAL,
                       'probabilidade': favoraveis / TOTAL,
                       'um_em': TOTAL / favoraveis if favoraveis else None}
    return {'registros': len(jogos), 'distintos': len(unicos),
            'duplicados': len(jogos) - len(unicos), 'valor_centavos': valor_centavos,
            'custo_centavos': len(jogos) * valor_centavos, 'faixas': faixas}


@lru_cache(maxsize=None)
def _intersecao(comuns, minimo):
    # Interseção exata dos eventos de dois bilhetes, pelas quatro regiões.
    total = 0
    for x in range(comuns + 1):
        for y in range(7 - comuns):
            for z in range(7 - comuns):
                fora = 6 - x - y - z
                if x+y >= minimo and x+z >= minimo and 0 <= fora <= 48+comuns:
                    total += comb(comuns, x) * comb(6-comuns, y) * comb(6-comuns, z) * comb(48+comuns, fora)
    return total


def otimizar_carteira(jogos, objetivo='quadra', valor_centavos=600, seed=42, candidatos=150):
    """Busca heurística; aceita a alternativa só após conferir sua união exata.

    Mantém quantidade e preço. Não altera os jogos de entrada nem garante ótimo
    global. Minimizar interseções aos pares é apenas a etapa de busca.
    """
    jogos = _carteira(jogos)
    if not jogos:
        raise ValueError('Adicione jogos à carteira antes de otimizar.')
    if objetivo not in ('quadra', 'quina'):
        raise ValueError('Escolha quadra ou quina.')
    if isinstance(candidatos, bool) or not isinstance(candidatos, int) or not 1 <= candidatos <= 1000:
        raise ValueError('Candidatos deve ser inteiro de 1 a 1000.')
    minimo = 4 if objetivo == 'quadra' else 5
    antes = analisar_carteira(jogos, valor_centavos)
    rng = random.Random(seed)
    alternativa = [j[:] for j in jogos]
    masks = [_mascara(j) for j in alternativa]
    # Busca local preserva os outros jogos ao testar cada substituição.
    for _ in range(2):
        mudou = False
        for indice in range(len(alternativa)):
            outros = masks[:indice] + masks[indice+1:]
            def custo(j):
                mask = _mascara(j)
                return sum(_intersecao((mask & m).bit_count(), minimo) for m in outros)
            original = alternativa[indice]
            if custo(original) == 0:
                continue
            opcoes = [original] + [rng.sample(range(1, 61), 6) for _ in range(candidatos)]
            novo = min((j for j in opcoes if _mascara(j) not in outros), key=custo)
            if custo(novo) < custo(original):
                alternativa[indice] = sorted(novo)
                masks[indice] = _mascara(novo)
                mudou = True
        if not mudou:
            break
    depois = analisar_carteira(alternativa, valor_centavos)
    chave = 'quadra_ou_mais' if minimo == 4 else 'quina_ou_mais'
    ganho = depois['faixas'][chave]['favoraveis'] - antes['faixas'][chave]['favoraveis']
    if ganho <= 0:
        alternativa, depois, ganho = [j[:] for j in jogos], antes, 0
    return {'jogos': alternativa, 'antes': antes, 'depois': depois, 'objetivo': objetivo,
            'ganho_resultados': ganho, 'seed': seed,
            'aviso': 'Busca heurística com cobertura final exata; não garante o ótimo global nem prevê sorteios.'}


def linhas_cobertura(analise):
    custo = f"{analise['custo_centavos'] / 100:.2f}".replace('.', ',')
    linhas = [f"{analise['registros']} jogos · {analise['distintos']} distintos · {analise['duplicados']} duplicados",
              f"Custo por concurso: R$ {custo} ({analise.get('origem_custo', 'preço unitário configurado')})."]
    for chave, nome in [('quadra_ou_mais', 'Quadra ou mais'), ('quina_ou_mais', 'Quina ou mais'), ('sena', 'Sena')]:
        f = analise['faixas'][chave]
        chance = f"1 em {f['um_em']:,.2f}" if f['um_em'] else 'sem cobertura'
        linhas.append(f"{nome}: {f['probabilidade']*100:.8f}% · {chance} · {f['favoraveis']}/{TOTAL} resultados")
    linhas += ['Probabilidade de ao menos um jogo atingir a faixa no mesmo concurso; eventos não são somados entre si.',
               'As chances pressupõem todos os jogos apostados. Não representam compra ou prêmio confirmado.']
    return linhas


def conferir_concurso(numero):
    from . import storage
    apostas = storage.listar_apostas_concurso(numero)
    concurso = storage.obter_concurso(numero)
    resultados = []
    if concurso:
        for aposta in apostas:
            r = comparar_jogo(aposta['dezenas'], concurso['dezenas'])
            resultados.append({**aposta, **r, 'faixa': {4: 'Quadra', 5: 'Quina', 6: 'Sena'}.get(r['acertos_qtd'], 'Sem faixa de prêmio')})
    resultados.sort(key=lambda r: (-r['acertos_qtd'], r['id']))
    return {'numero': numero, 'concurso': concurso, 'apostas': apostas, 'resultados': resultados,
            'status': 'sem_jogos' if not apostas else ('conferido' if concurso else 'aguardando_resultado')}


def linhas_conferencia(relatorio):
    linhas = [f"Concurso {relatorio['numero']} · {len(relatorio['apostas'])} jogos vinculados"]
    if relatorio['status'] == 'sem_jogos':
        return linhas + ['Nenhum jogo vinculado a este concurso. Use vincular antes de conferir.']
    if not relatorio['concurso']:
        return linhas + ['Aguardando resultado local. Atualize o histórico CAIXA.']
    linhas += [f"Resultado: {relatorio['concurso']['dezenas']}", 'Conferência dos jogos vinculados; não comprova pagamento nem direito ao prêmio.']
    linhas += [f"Jogo {r['id']} · {r['dezenas']} · {r['acertos_qtd']} acertos {r['acertos']} · {r['faixa']}" for r in relatorio['resultados']]
    return linhas
