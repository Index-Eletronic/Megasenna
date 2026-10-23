"""Protege a carteira carregada antes de qualquer clique no site de apostas."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from megasena.cart_automation import validate_tickets


CARTEIRA = Path(__file__).resolve().parents[1] / "assets" / "carteira-25-2026-09-25.json"


class CartTicketValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid_data = json.loads(CARTEIRA.read_text(encoding="utf-8"))

    def validate_temp(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jogos.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return validate_tickets(path)

    def test_carteira_real_tem_25_jogos_distintos_e_ordenados(self):
        tickets = validate_tickets(CARTEIRA)
        self.assertEqual(len(tickets), 25)
        self.assertEqual(tickets[0], (9, 21, 26, 39, 48, 56))
        self.assertEqual(tickets[-1], (15, 17, 30, 32, 36, 40))
        self.assertEqual(len(set(tickets)), 25)
        for ticket in tickets:
            self.assertIsInstance(ticket, tuple)
            self.assertEqual(len(ticket), 6)
            self.assertEqual(ticket, tuple(sorted(ticket)))
            self.assertTrue(all(type(number) is int and 1 <= number <= 60 for number in ticket))

    def test_rejeita_quantidade_diferente_de_25(self):
        for count in (0, 24, 26):
            with self.subTest(count=count):
                data = copy.deepcopy(self.valid_data)
                data["jogos"] = data["jogos"][:count]
                if count == 26:
                    data["jogos"].append([1, 2, 3, 4, 5, 6])
                with self.assertRaises(ValueError):
                    self.validate_temp(data)

    def test_rejeita_dezenas_fora_da_faixa_repetidas_ou_em_quantidade_errada(self):
        cases = {
            "zero": [0, 2, 3, 4, 5, 6],
            "acima_de_60": [1, 2, 3, 4, 5, 61],
            "repetida": [1, 2, 3, 4, 5, 5],
            "cinco_dezenas": [1, 2, 3, 4, 5],
            "sete_dezenas": [1, 2, 3, 4, 5, 6, 7],
            "texto": ["01", 2, 3, 4, 5, 6],
            "decimal": [1.0, 2, 3, 4, 5, 6],
            "booleano": [True, 2, 3, 4, 5, 6],
        }
        for name, invalid_ticket in cases.items():
            with self.subTest(name=name):
                data = copy.deepcopy(self.valid_data)
                data["jogos"][0] = invalid_ticket
                with self.assertRaises(ValueError):
                    self.validate_temp(data)

    def test_rejeita_aposta_repetida_mesmo_em_outra_ordem(self):
        data = copy.deepcopy(self.valid_data)
        data["jogos"][1] = list(reversed(data["jogos"][0]))
        with self.assertRaises(ValueError):
            self.validate_temp(data)

    def test_rejeita_estrutura_sem_lista_de_jogos(self):
        for data in ({}, {"jogos": "01 02 03 04 05 06"}, []):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.validate_temp(data)


if __name__ == "__main__":
    unittest.main()
