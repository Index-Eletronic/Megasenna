import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from megasena import api


def resultado(numero=1):
    return {"numero": numero, "tipoJogo": "MEGA_SENA", "dataApuracao": "11/03/1996",
            "listaDezenas": ["04", "05", "30", "33", "41", "52"]}


class APITests(unittest.TestCase):
    def test_consulta_oficial_e_concurso(self):
        with patch.object(api, "_get_json", return_value=resultado()) as get:
            payload, fonte = api.fetch_latest_megasena()
            self.assertEqual(fonte, api.CAIXA_BASE)
            self.assertEqual(api.dezenas_do_resultado(payload), [4, 5, 30, 33, 41, 52])
            self.assertEqual(api.concurso_numero(payload), 1)
            api.fetch_megasena_concurso(1)
            get.assert_called_with(api.CAIXA_BASE + "/1", 15)

    def test_concurso_diferente_ou_outra_modalidade_rejeitados(self):
        for payload in (resultado(2), {**resultado(), "tipoJogo": "LOTOFACIL"}):
            with patch.object(api, "_get_json", return_value=payload), self.assertRaises(api.MegaSenaAPIError):
                api.fetch_megasena_concurso(1)

    def test_valores_nao_sao_truncados_ou_convertidos_silenciosamente(self):
        for dezenas in ([1, 2, 3, 4, 5, 6, 7], [1, 1, 3, 4, 5, 6], [0, 2, 3, 4, 5, 6],
                        [1, 2, 3, 4, 5, 61], [True, 2, 3, 4, 5, 6], [1.5, 2, 3, 4, 5, 6]):
            with self.subTest(dezenas=dezenas), self.assertRaises(api.MegaSenaAPIError):
                api.dezenas_do_resultado({"listaDezenas": dezenas})
        for numero in (0, -1, True, 1.2, None):
            with self.subTest(numero=numero), self.assertRaises(api.MegaSenaAPIError):
                api.concurso_numero({"numero": numero})

    def test_payload_e_data_invalidos(self):
        for payload in ([], {}, {**resultado(), "dataApuracao": "31/02/2026"}):
            with patch.object(api, "_get_json", return_value=payload), self.assertRaises(api.MegaSenaAPIError):
                api.fetch_latest_megasena()

    def test_falhas_de_rede_sao_explicitas(self):
        for erro in (TimeoutError("timeout"), URLError("offline"), HTTPError(api.CAIXA_BASE, 503, "indisponível", {}, None), json.JSONDecodeError("ruim", "x", 0)):
            with patch.object(api, "_get_json", side_effect=erro), self.assertRaises(api.MegaSenaAPIError):
                api.fetch_latest_megasena()

    def test_urllib_fecha_resposta(self):
        resposta = MagicMock()
        resposta.__enter__.return_value.read.return_value = json.dumps(resultado()).encode()
        with patch.object(api, "urlopen", return_value=resposta) as abrir:
            self.assertEqual(api.fetch_latest_megasena()[0]["numero"], 1)
            self.assertEqual(abrir.call_args.args[0].full_url, api.CAIXA_BASE)
            resposta.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
