import copy
import unittest
from collections import Counter
from fractions import Fraction
from itertools import combinations
from unittest.mock import patch

from megasena.stats import (
    TOTAL_COMBINACOES, analisar_historico, backtest_cronologico, cobertura_sena,
    gerar_jogos_sugeridos, prob_acertar_sena, probabilidades_jogo_simples, score_jogo,
)


def historico_sintetico(quantidade=12):
    return [
        {"numero": i + 1, "data_apuracao": None,
         "dezenas": [((i * 6 + j) % 60) + 1 for j in range(6)]}
        for i in range(quantidade)
    ]


class ProbabilidadeTests(unittest.TestCase):
    def test_probabilidades_exatas_com_numerador_auditavel(self):
        probabilidades = probabilidades_jogo_simples()
        self.assertEqual(TOTAL_COMBINACOES, 50063860)
        for nome, favoraveis in [("sena", 1), ("quina", 324), ("quadra", 21465)]:
            with self.subTest(nome=nome):
                prob = probabilidades[nome]
                self.assertEqual(prob["favoraveis"], favoraveis)
                self.assertEqual(prob["total"], 50063860)
                self.assertEqual(prob["probabilidade"], float(Fraction(favoraveis, 50063860)))
                self.assertEqual(prob["um_em"], 50063860 / favoraveis)
        self.assertEqual(prob_acertar_sena(), probabilidades["sena"]["probabilidade"])

    def test_cobertura_remove_duplicatas_ordenadas_diferentemente(self):
        jogo = [1, 2, 3, 4, 5, 6]
        self.assertEqual(cobertura_sena([jogo, list(reversed(jogo))]), 1 / TOTAL_COMBINACOES)
        self.assertEqual(cobertura_sena([jogo, [1, 2, 3, 4, 5, 7]]), 2 / TOTAL_COMBINACOES)
        self.assertEqual(cobertura_sena([]), 0.0)


class GeradorTests(unittest.TestCase):
    def test_reproduzivel_distinto_e_valido_nas_duas_estrategias(self):
        for estrategia in ["aleatoria", "diversificada"]:
            with self.subTest(estrategia=estrategia):
                jogos = gerar_jogos_sugeridos(30, 2000, seed=42, estrategia=estrategia)
                self.assertEqual(jogos, gerar_jogos_sugeridos(30, 2000, seed=42, estrategia=estrategia))
                self.assertEqual(len({tuple(jogo) for jogo in jogos}), 30)
                for jogo in jogos:
                    self.assertEqual(jogo, sorted(set(jogo)))
                    self.assertEqual(len(jogo), 6)
                    self.assertTrue(all(1 <= dezena <= 60 for dezena in jogo))

    def test_exclusoes_e_duplicatas_forcadas(self):
        salvo, primeiro, segundo = [1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12], [13, 14, 15, 16, 17, 18]
        with patch("megasena.stats.random.Random") as random_mock:
            random_mock.return_value.sample.side_effect = [salvo, primeiro, primeiro, segundo]
            jogos = gerar_jogos_sugeridos(2, seed=1, estrategia="aleatoria", excluir=[salvo])
        self.assertEqual(jogos, [primeiro, segundo])

    def test_frequencia_nao_vira_peso_preditivo(self):
        sem_peso = gerar_jogos_sugeridos(5, 100, seed=10)
        com_peso = gerar_jogos_sugeridos(5, 100, freq=Counter({1: 100000}), seed=10)
        self.assertEqual(sem_peso, com_peso)

    def test_diversificacao_reduz_reuso_de_pares_neste_cenario(self):
        def repeticoes(jogos):
            pares = Counter(par for jogo in jogos for par in combinations(jogo, 2))
            return sum(n - 1 for n in pares.values())
        aleatorios = gerar_jogos_sugeridos(30, 3000, seed=123, estrategia="aleatoria")
        diversos = gerar_jogos_sugeridos(30, 3000, seed=123, estrategia="diversificada")
        self.assertLess(repeticoes(diversos), repeticoes(aleatorios))

    def test_limites_invalidos(self):
        casos = [
            {"n_sugestoes": 0}, {"n_sugestoes": -1}, {"n_sugestoes": 1001},
            {"n_sugestoes": True}, {"n_sugestoes": 1.5}, {"amostras": 0},
            {"amostras": 100001}, {"n_sugestoes": 10, "amostras": 9},
            {"estrategia": "previsao"}, {"excluir": [[1, 2, 3, 4, 5, 5]]},
        ]
        for kwargs in casos:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                gerar_jogos_sugeridos(**kwargs)

    def test_score_legado_valida_entrada(self):
        self.assertIsInstance(score_jogo([1, 2, 3, 4, 5, 6]), float)
        with self.assertRaises(ValueError):
            score_jogo([1, 2, 3, 4, 5, 5])


class HistoricoTests(unittest.TestCase):
    def test_frequencias_incluem_todas_dezenas_com_esperado_dez_por_cento(self):
        estatisticas = analisar_historico(historico_sintetico(10))
        self.assertEqual(estatisticas["total_concursos"], 10)
        self.assertEqual(len(estatisticas["frequencias"]), 60)
        self.assertTrue(estatisticas["completo_ate_ultimo"])
        self.assertEqual(estatisticas["concursos_faltantes"], 0)
        for freq in estatisticas["frequencias"]:
            self.assertEqual(freq["ocorrencias"], 1)
            self.assertEqual(freq["percentual"], 10)
            self.assertEqual(freq["percentual_esperado"], 10)
            self.assertFalse(freq["nunca_observada"])

    def test_atraso_paridade_soma_e_pares(self):
        historico = [
            {"numero": 3, "dezenas": [1, 2, 3, 4, 5, 6]},
            {"numero": 1, "dezenas": [1, 2, 3, 4, 5, 6]},
            {"numero": 2, "dezenas": [2, 4, 6, 8, 10, 12]},
        ]
        copia = copy.deepcopy(historico)
        resultado = analisar_historico(historico)
        self.assertEqual(historico, copia)
        frequencias = {item["dezena"]: item for item in resultado["frequencias"]}
        self.assertEqual(frequencias[1]["atraso"], 0)
        self.assertEqual(frequencias[8]["atraso"], 1)
        self.assertEqual(frequencias[60]["atraso"], 3)
        self.assertTrue(frequencias[60]["nunca_observada"])
        self.assertEqual(resultado["distribuicao_pares"][3], 2)
        self.assertEqual(resultado["distribuicao_pares"][6], 1)
        self.assertEqual(resultado["soma"], {"min": 21, "max": 42, "media": 28, "esperada": 183})
        self.assertEqual(resultado["pares_frequentes"][0], {"dezenas": [2, 4], "ocorrencias": 3})

    def test_historico_com_lacunas_fica_sinalizado(self):
        historico = historico_sintetico(5)[1:]
        historico.pop(1)
        resultado = analisar_historico(historico)
        self.assertEqual(resultado["concursos_faltantes"], 2)
        self.assertFalse(resultado["completo_ate_ultimo"])

    def test_historico_vazio_tem_estatisticas_definidas(self):
        resultado = analisar_historico([])
        self.assertEqual(resultado["total_concursos"], 0)
        self.assertEqual(resultado["pares_frequentes"], [])
        self.assertIsNone(resultado["soma"]["media"])
        self.assertTrue(all(freq["percentual"] == 0 for freq in resultado["frequencias"]))
        self.assertFalse(resultado["completo_ate_ultimo"])

    def test_concurso_duplicado_nao_pode_inflar_estatisticas(self):
        historico = historico_sintetico(1)
        with self.assertRaises(ValueError):
            analisar_historico(historico * 2)


class BacktestTests(unittest.TestCase):
    def test_ordem_limite_reprodutibilidade_e_orcamento_igual(self):
        historico = historico_sintetico()
        argumentos = dict(n_jogos=4, treino_minimo=3, max_concursos=5, seed=123, amostras=40)
        resultado = backtest_cronologico(list(reversed(historico)), **argumentos)
        self.assertEqual(resultado, backtest_cronologico(historico, **argumentos))
        self.assertEqual(resultado["avaliados"], 5)
        self.assertEqual([d["numero"] for d in resultado["detalhes"]], [8, 9, 10, 11, 12])
        self.assertEqual(resultado["sugeridos"]["apostas_avaliadas"], 20)
        self.assertEqual(resultado["aleatorios"]["apostas_avaliadas"], 20)
        self.assertEqual(sum(resultado["sugeridos"]["distribuicao_acertos"].values()), 20)

    def test_treino_nunca_recebe_resultado_atual_nem_futuro(self):
        historico = historico_sintetico(6)
        with patch("megasena.stats.gerar_jogos_sugeridos", wraps=gerar_jogos_sugeridos) as gerar:
            resultado = backtest_cronologico(historico, n_jogos=2, treino_minimo=2, max_concursos=3, amostras=20)
        self.assertEqual(gerar.call_count, 6)
        for rodada, indice in enumerate(range(3, 6)):
            kwargs_treino = gerar.call_args_list[rodada * 2].kwargs
            kwargs_baseline = gerar.call_args_list[rodada * 2 + 1].kwargs
            esperado = Counter(n for concurso in historico[:indice] for n in concurso["dezenas"])
            self.assertEqual(kwargs_treino["freq"], esperado)
            self.assertEqual(sum(kwargs_treino["freq"].values()), indice * 6)
            for dezena in historico[indice]["dezenas"]:
                self.assertEqual(kwargs_treino["freq"][dezena], 0)
            self.assertNotIn("freq", kwargs_baseline)
            self.assertEqual(kwargs_treino["n_sugestoes"], kwargs_baseline["n_sugestoes"])
            self.assertEqual(resultado["detalhes"][rodada]["treino_ate"], indice)

    def test_dados_futuros_nao_mudam_apostas_anteriores(self):
        historico = historico_sintetico(6)
        alterado = copy.deepcopy(historico)
        alterado[-1]["dezenas"] = [1, 2, 3, 4, 5, 6]
        capturas = []
        for dados in (historico, alterado):
            with patch("megasena.stats.gerar_jogos_sugeridos", wraps=gerar_jogos_sugeridos) as gerar:
                backtest_cronologico(dados, n_jogos=2, treino_minimo=2, max_concursos=4, amostras=20)
            capturas.append(gerar.call_args_list)
        self.assertEqual(capturas[0], capturas[1])

    def test_limites_e_amostra_insuficiente(self):
        casos = [
            {"treino_minimo": 0}, {"treino_minimo": 12}, {"n_jogos": 0},
            {"n_jogos": 201}, {"max_concursos": 501}, {"max_concursos": 0},
            {"amostras": 1}, {"estrategia": "previsao"},
        ]
        for kwargs in casos:
            parametros = {"treino_minimo": 2, **kwargs}
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                backtest_cronologico(historico_sintetico(), **parametros)


if __name__ == "__main__":
    unittest.main()
