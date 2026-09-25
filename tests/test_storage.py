import json
import os
import sqlite3
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from megasena import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(__file__).resolve().parent / f".storage-test-{uuid4().hex}"
        self.base.mkdir()
        self.addCleanup(self.clean_base)
        self.db_patch = patch.object(storage, "DB_PATH", self.base / "app.db")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        storage.init_db()

    def clean_base(self):
        assert self.base.resolve().parent == Path(__file__).resolve().parent
        shutil.rmtree(self.base)

    def test_jogos_validacao_e_persistencia(self):
        jogo = storage.salvar_jogo([60, 5, 4, 3, 2, 1])
        storage.init_db()
        self.assertEqual(storage.listar_jogos()[0]["dezenas"], [1, 2, 3, 4, 5, 60])
        for nums in ([1] * 6, [0, 2, 3, 4, 5, 6], [True, 2, 3, 4, 5, 6], [1.0, 2, 3, 4, 5, 6], [1, 2]):
            with self.subTest(nums=nums), self.assertRaises(ValueError):
                storage.salvar_jogo(nums)
        self.assertEqual(len(storage.listar_jogos()), 1)
        self.assertTrue(storage.excluir_jogo(jogo))
        self.assertFalse(storage.excluir_jogo(jogo))

    def test_consultas_lacunas_e_upsert(self):
        for numero in [5, 1, 3]:
            storage.salvar_concurso(numero, "2026-09-22", [1, 2, 3, 4, 5, 6])
        self.assertEqual([c["numero"] for c in storage.listar_concursos(2, 5)], [3, 5])
        self.assertEqual(storage.resumo_historico()["lacunas"], [2, 4])
        self.assertEqual(storage.obter_concurso(1)["data_apuracao"], "22/09/2026")
        self.assertIsNone(storage.obter_concurso(2))
        storage.salvar_concurso(5, "22/09/2026", [1, 2, 3, 4, 5, 60])
        self.assertEqual(storage.ler_ultimo_concurso_salvo()["dezenas"][-1], 60)
        self.assertEqual(storage.resumo_historico()["total"], 3)
        with self.assertRaises(ValueError):
            storage.listar_concursos(10, 1)
        for numero in (None, 0, -1, True, 1.0, "1"):
            with self.subTest(numero=numero), self.assertRaises(ValueError):
                storage.salvar_concurso(numero, None, [1, 2, 3, 4, 5, 6])

    def test_conexao_fecha_e_reverte_transacao(self):
        with self.assertRaises(RuntimeError):
            with storage.connect() as con:
                con.execute("INSERT INTO jogos (criado_em, dezenas) VALUES ('hoje', '1,2,3,4,5,6')")
                raise RuntimeError("teste")
        with self.assertRaises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")
        self.assertEqual(storage.listar_jogos(), [])

    def test_registro_corrompido_nao_conta_como_historico_valido(self):
        with storage.connect() as con:
            con.execute("INSERT INTO concursos VALUES (2, '22/09/2026', '1,1,1,1,1,1')")
        resumo = storage.resumo_historico()
        self.assertEqual(resumo["total"], 0)
        self.assertEqual(resumo["invalidos"], [2])
        self.assertEqual(resumo["lacunas"], [1, 2])
        with self.assertRaises(ValueError):
            storage.listar_concursos()

    def test_caminhos_independentes_do_diretorio_atual(self):
        esperado = Path(storage.__file__).resolve().parent.parent / "data" / "app.db"
        self.assertEqual(storage.caminho_banco(), esperado)
        with patch.object(storage.sys, "frozen", True, create=True), patch.dict(os.environ, {"LOCALAPPDATA": str(self.base)}):
            self.assertEqual(storage.caminho_banco(), self.base / "Megasenna" / "app.db")

    def test_migracao_une_legados_preserva_origens_e_destino_existente(self):
        storage.salvar_jogo([1, 2, 3, 4, 5, 6])
        storage.salvar_concurso(1, "11/03/1996", [4, 5, 30, 33, 41, 52])
        primeiro = storage.DB_PATH
        segundo = self.base / "outro.db"
        with patch.object(storage, "DB_PATH", segundo):
            storage.init_db()
            storage.salvar_jogo([7, 8, 9, 10, 11, 12])
            storage.salvar_concurso(2, "18/03/1996", [1, 2, 3, 4, 5, 6])
        destino = self.base / "migrado" / "app.db"
        originais = [primeiro.read_bytes(), segundo.read_bytes()]
        with patch.object(storage, "DB_PATH", destino), patch.object(storage.sys, "frozen", True, create=True), patch.object(storage, "_bancos_legados", return_value=[primeiro, segundo]) as bancos:
            storage.init_db()
            self.assertEqual(len(storage.listar_jogos()), 2)
            self.assertEqual(len({j["id"] for j in storage.listar_jogos()}), 2)
            self.assertEqual(storage.resumo_historico()["total"], 2)
            storage.init_db()
            self.assertEqual(bancos.call_count, 1)
        self.assertEqual(originais, [primeiro.read_bytes(), segundo.read_bytes()])

    def test_importacao_valida_tudo_e_rollback_em_conflito(self):
        caminho = self.base / "historico.json"
        storage.salvar_concurso(2, "22/09/2026", [1, 2, 3, 4, 5, 6])
        registros = [{"numero": 1, "data_apuracao": "22/09/2026", "dezenas": [1, 2, 3, 4, 5, 6]},
                     {"numero": 2, "data_apuracao": "22/09/2026", "dezenas": [1, 2, 3, 4, 5, 7]}]
        caminho.write_text(json.dumps({"concursos": registros}), encoding="utf-8")
        with self.assertRaises(ValueError):
            storage.importar_historico(caminho)
        self.assertIsNone(storage.obter_concurso(1))
        registros[1]["dezenas"][-1] = 6
        caminho.write_text(json.dumps(registros), encoding="utf-8")
        self.assertEqual(storage.importar_historico(caminho), 1)
        self.assertEqual(storage.importar_historico(caminho), 0)
        self.assertEqual(storage.exportar_historico(caminho), 2)
        self.assertEqual(storage.importar_historico(caminho), 0)

    def test_executavel_novo_carrega_apenas_historico_publico_embutido(self):
        recursos = Path(storage.__file__).resolve().parent.parent
        with patch.object(storage.sys, "frozen", True, create=True), \
             patch.object(storage.sys, "_MEIPASS", str(recursos), create=True), \
             patch.object(storage, "_bancos_legados", return_value=[]):
            storage.init_db()
            resumo = storage.resumo_historico()
            self.assertEqual((resumo["total"], resumo["primeiro"], resumo["ultimo"]), (3061, 1, 3061))
            self.assertEqual(resumo["lacunas"], [])
            self.assertEqual(storage.listar_jogos(), [])


if __name__ == "__main__":
    unittest.main()
