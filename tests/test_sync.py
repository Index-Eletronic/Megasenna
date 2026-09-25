import shutil
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from megasena import storage, sync
from megasena.api import MegaSenaAPIError


def resultado(numero):
    return {"numero": numero, "dataApuracao": "22/09/2026", "listaDezenas": [1, 2, 3, 4, 5, 6]}, "caixa"


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(__file__).resolve().parent / f".sync-test-{uuid4().hex}"
        self.base.mkdir()
        self.addCleanup(self.clean_base)
        troca = patch.object(storage, "DB_PATH", self.base / "app.db")
        troca.start()
        self.addCleanup(troca.stop)
        storage.init_db()
        latest = patch.object(sync, "fetch_latest_megasena", return_value=resultado(4))
        latest.start()
        self.addCleanup(latest.stop)

    def clean_base(self):
        assert self.base.resolve().parent == Path(__file__).resolve().parent
        shutil.rmtree(self.base)

    def test_preenche_lacunas_e_pula_concursos_salvos(self):
        storage.salvar_concurso(2, "22/09/2026", [1, 2, 3, 4, 5, 6])
        eventos = []
        with patch.object(sync, "fetch_megasena_concurso", side_effect=lambda n, timeout: resultado(n)) as fetch:
            resumo = sync.sincronizar_historico(progresso=eventos.append)
            self.assertEqual([c.args[0] for c in fetch.call_args_list], [1, 3])
        self.assertTrue(resumo["completo"])
        self.assertEqual(resumo["total"], 4)
        self.assertEqual(resumo["baixados"], 3)
        self.assertEqual(eventos[-1]["processados"], eventos[-1]["total"])

    def test_falha_preserva_progresso_e_retomada(self):
        with patch.object(sync, "fetch_megasena_concurso", side_effect=[resultado(1), MegaSenaAPIError("offline")]):
            resumo = sync.sincronizar_historico()
        self.assertEqual(resumo["status"], "erro")
        self.assertFalse(resumo["completo"])
        self.assertEqual(resumo["lacunas"], [2, 3])
        with patch.object(sync, "fetch_megasena_concurso", side_effect=lambda n, timeout: resultado(n)) as fetch:
            retomada = sync.sincronizar_historico()
            self.assertEqual([c.args[0] for c in fetch.call_args_list], [2, 3])
        self.assertTrue(retomada["completo"])

    def test_cancelar_preserva_downloads_confirmados(self):
        cancelar = Event()
        def progresso(evento):
            if evento["processados"] == 1:
                cancelar.set()
        with patch.object(sync, "fetch_megasena_concurso", side_effect=lambda n, timeout: resultado(n)):
            resumo = sync.sincronizar_historico(progresso, cancelar)
        self.assertEqual(resumo["status"], "cancelado")
        self.assertFalse(resumo["completo"])
        self.assertEqual(resumo["total"], 2)
        self.assertEqual(resumo["lacunas"], [2, 3])

    def test_offline_nao_afirma_estar_atualizado(self):
        storage.salvar_concurso(1, "22/09/2026", [1, 2, 3, 4, 5, 6])
        with patch.object(sync, "fetch_latest_megasena", side_effect=MegaSenaAPIError("offline")):
            resumo = sync.sincronizar_historico()
        self.assertEqual(resumo["total"], 1)
        self.assertFalse(resumo["completo"])
        self.assertIsNone(resumo["ultimo_oficial"])

    def test_concurso_errado_nao_preenche_lacuna(self):
        with patch.object(sync, "fetch_megasena_concurso", return_value=resultado(99)):
            resumo = sync.sincronizar_historico()
        self.assertFalse(resumo["completo"])
        self.assertEqual(resumo["status"], "erro")
        self.assertIsNone(storage.obter_concurso(99))
        self.assertIsNone(storage.obter_concurso(1))

    def test_registro_corrompido_e_reparado(self):
        with storage.connect() as con:
            con.execute("INSERT INTO concursos VALUES (2, NULL, '1,1,1,1,1,1')")
        with patch.object(sync, "fetch_megasena_concurso", side_effect=lambda n, timeout: resultado(n)):
            resumo = sync.sincronizar_historico()
        self.assertTrue(resumo["completo"])
        self.assertEqual(resumo["invalidos"], [])


if __name__ == "__main__":
    unittest.main()
