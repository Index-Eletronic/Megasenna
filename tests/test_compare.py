import unittest

from megasena.compare import comparar_jogo, conferir_historico, normalizar_historico, normalize_jogo


class CompareTests(unittest.TestCase):
    def test_normaliza_inteiros_e_texto_sem_modificar_entrada(self):
        entrada = ["60", "05", 4, 3, 2, 1]
        self.assertEqual(normalize_jogo(entrada), [1, 2, 3, 4, 5, 60])
        self.assertEqual(entrada[0], "60")

    def test_rejeita_dezenas_invalidas_sem_truncar(self):
        invalidos = [
            [1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 5], [0, 2, 3, 4, 5, 6],
            [1, 2, 3, 4, 5, 61], [1.9, 2, 3, 4, 5, 6],
            [True, 2, 3, 4, 5, 6], "123456", None,
        ]
        for entrada in invalidos:
            with self.subTest(entrada=entrada), self.assertRaises(ValueError):
                normalize_jogo(entrada)

    def test_compara_e_valida_resultado_tambem(self):
        self.assertEqual(comparar_jogo([1, 2, 3, 4, 5, 6], [4, 5, 6, 7, 8, 9]), {
            "acertos_qtd": 3, "acertos": [4, 5, 6], "faltantes": [1, 2, 3],
        })
        with self.assertRaises(ValueError):
            comparar_jogo([1, 2, 3, 4, 5, 6], [1, 1, 1, 1, 1, 1])

    def test_confere_todo_historico_em_ordem_decrescente(self):
        concursos = [
            {"numero": 2, "data_apuracao": "02/01/2020", "dezenas": [1, 2, 3, 4, 7, 8]},
            {"numero": 1, "data_apuracao": "01/01/2020", "dezenas": [1, 2, 3, 4, 5, 6]},
            {"numero": 3, "data_apuracao": "03/01/2020", "dezenas": [10, 20, 30, 40, 50, 60]},
        ]
        resultado = conferir_historico([1, 2, 3, 4, 5, 6], concursos)
        self.assertEqual([item["numero"] for item in resultado], [3, 2, 1])
        self.assertEqual([item["acertos_qtd"] for item in resultado], [0, 4, 6])
        self.assertEqual(resultado[1]["data_apuracao"], "02/01/2020")
        self.assertEqual([item["numero"] for item in concursos], [2, 1, 3])

    def test_historico_rejeita_duplicatas_e_numero_invalido(self):
        concurso = {"numero": 1, "dezenas": [1, 2, 3, 4, 5, 6]}
        with self.assertRaises(ValueError):
            normalizar_historico([concurso, concurso])
        for numero in [0, -1, True, 1.1, None]:
            with self.subTest(numero=numero), self.assertRaises(ValueError):
                normalizar_historico([{**concurso, "numero": numero}])

    def test_historico_vazio(self):
        self.assertEqual(conferir_historico([1, 2, 3, 4, 5, 6], []), [])


if __name__ == "__main__":
    unittest.main()
