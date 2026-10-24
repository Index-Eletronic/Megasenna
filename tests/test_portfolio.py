import copy
from itertools import combinations
from math import comb
import unittest

from megasena.portfolio import (
    analisar_carteira, cobertura_uniao, otimizar_carteira, preco_centavos,
    _intersecao,
)


class PortfolioTests(unittest.TestCase):
    def test_single_ticket_events_include_higher_tiers(self):
        r = analisar_carteira([[1, 2, 3, 4, 5, 6]])
        self.assertEqual(r['faixas']['quadra_ou_mais']['favoraveis'], 21790)
        self.assertEqual(r['faixas']['quina_ou_mais']['favoraveis'], 325)
        self.assertEqual(r['faixas']['sena']['favoraveis'], 1)

    def test_original_25_ticket_portfolio_can_reach_exact_upper_bound(self):
        from pathlib import Path
        from megasena.portfolio import importar_carteira
        jogos = importar_carteira(Path(__file__).resolve().parent.parent / 'assets/carteira-25-2026-09-25.json')
        r = otimizar_carteira(jogos)
        self.assertEqual(r['antes']['faixas']['quadra_ou_mais']['favoraveis'], 544714)
        self.assertEqual(r['depois']['faixas']['quadra_ou_mais']['favoraveis'], 25*21790)
        self.assertEqual(r['ganho_resultados'], 36)
        self.assertEqual(r['depois']['custo_centavos'], 15000)

    def test_duplicates_cost_money_but_do_not_add_coverage(self):
        a = [1, 2, 3, 4, 5, 6]
        r = analisar_carteira([a, list(reversed(a))], 650)
        self.assertEqual((r['registros'], r['distintos'], r['duplicados']), (2, 1, 1))
        self.assertEqual(r['custo_centavos'], 1300)
        self.assertEqual(r['faixas'], analisar_carteira([a])['faixas'])

    def test_disjoint_events_and_pair_overlap(self):
        a = [1, 2, 3, 4, 5, 6]
        self.assertEqual(cobertura_uniao([a, [7, 8, 9, 10, 11, 12]], 4), 2*21790)
        self.assertEqual(cobertura_uniao([a, [1, 2, 7, 8, 9, 10]], 4), 2*21790-36)
        self.assertEqual(cobertura_uniao([a, [1, 2, 3, 4, 7, 8]], 5), 2*325-4)
        self.assertEqual(_intersecao(2, 4), 36)
        self.assertEqual(_intersecao(4, 5), 4)

    def test_triple_overlap_matches_independent_weighted_enumeration(self):
        jogos = [{1, 2, 3, 4, 5, 6}, {1, 2, 3, 4, 5, 7}, {1, 2, 3, 4, 7, 8}]
        universo = set.union(*jogos)
        for minimo in (4, 5, 6):
            expected = 0
            for k in range(7):
                for subset in combinations(universo, k):
                    if any(len(set(subset) & j) >= minimo for j in jogos):
                        expected += comb(60-len(universo), 6-k)
            self.assertEqual(cobertura_uniao([list(j) for j in jogos], minimo), expected)

    def test_optimizer_preserves_count_cost_input_and_never_reduces_target(self):
        jogos = [[1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 7], [1, 2, 3, 4, 5, 8]]
        original = copy.deepcopy(jogos)
        for alvo, chave in [('quadra', 'quadra_ou_mais'), ('quina', 'quina_ou_mais')]:
            r = otimizar_carteira(jogos, alvo, 650, candidatos=10)
            self.assertEqual(jogos, original)
            self.assertEqual(len(r['jogos']), 3)
            self.assertEqual(r['antes']['custo_centavos'], r['depois']['custo_centavos'])
            self.assertGreater(r['ganho_resultados'], 0)
            self.assertGreater(r['depois']['faixas'][chave]['favoraveis'], r['antes']['faixas'][chave]['favoraveis'])
            self.assertEqual(r, otimizar_carteira(jogos, alvo, 650, candidatos=10))

    def test_optimal_disjoint_baseline_is_kept_and_duplicates_can_be_removed(self):
        jogos = [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]
        r = otimizar_carteira(jogos, candidatos=2)
        self.assertEqual(r['ganho_resultados'], 0)
        self.assertEqual(r['jogos'], jogos)
        r = otimizar_carteira([jogos[0], jogos[0]], candidatos=2)
        self.assertEqual(r['depois']['distintos'], 2)
        self.assertEqual(r['antes']['custo_centavos'], r['depois']['custo_centavos'])

    def test_empty_limits_invalid_prices_and_tiers(self):
        self.assertEqual(analisar_carteira([])['faixas']['quadra_ou_mais']['favoraveis'], 0)
        for valor in ('NaN', 'Infinity', '-1', '0', '6.001', 'texto'):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                preco_centavos(valor)
        self.assertEqual(preco_centavos('6,50'), 650)
        with self.assertRaises(ValueError):
            analisar_carteira([[1, 2, 3, 4, 5, 6]] * 201)
        with self.assertRaises(ValueError):
            cobertura_uniao([[1, 2, 3, 4, 5, 6]], 3)
        with self.assertRaises(ValueError):
            otimizar_carteira([])
