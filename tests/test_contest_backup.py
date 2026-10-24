import json
from contextlib import closing
import shutil
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from uuid import uuid4

from megasena import storage, sync
from megasena.portfolio import conferir_concurso
from terminal_gui import TerminalApp


class ContestBackupTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(__file__).resolve().parent / f'.contest-test-{uuid4().hex}'
        self.base.mkdir()
        self.addCleanup(self.cleanup)
        troca = patch.object(storage, 'DB_PATH', self.base / 'app.db')
        troca.start()
        self.addCleanup(troca.stop)
        storage.init_db()

    def cleanup(self):
        assert self.base.resolve().parent == Path(__file__).resolve().parent
        shutil.rmtree(self.base)

    def test_binding_is_idempotent_preserves_snapshots_and_waits_for_result(self):
        primeiro = storage.salvar_jogo([1, 2, 3, 4, 5, 6])
        segundo = storage.salvar_jogo([10, 20, 30, 40, 50, 60])
        self.assertEqual(storage.vincular_jogos_concurso(100), 2)
        self.assertEqual(storage.vincular_jogos_concurso(100), 0)
        storage.excluir_jogo(primeiro)
        self.assertEqual(len(storage.listar_apostas_concurso(100)), 2)
        self.assertEqual(conferir_concurso(100)['status'], 'aguardando_resultado')
        self.assertEqual(conferir_concurso(101)['status'], 'sem_jogos')
        storage.salvar_concurso(100, '24/10/2026', [1, 2, 3, 4, 5, 6])
        r = conferir_concurso(100)
        self.assertEqual([a['acertos_qtd'] for a in r['resultados']], [6, 0])
        self.assertEqual(r['resultados'][0]['faixa'], 'Sena')
        storage.vincular_jogos_concurso(101, [segundo], 700)
        self.assertEqual(storage.concursos_vinculados(), [101, 100])
        self.assertEqual(storage.listar_apostas_concurso(101)[0]['valor_centavos'], 700)
        with self.assertRaises(ValueError):
            storage.vincular_jogos_concurso(102, [segundo, 999])
        self.assertEqual(storage.listar_apostas_concurso(102), [])

    def test_backup_includes_committed_wal_and_is_restorable(self):
        with storage.connect() as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.execute("INSERT INTO jogos (criado_em, dezenas) VALUES ('hoje', '1,2,3,4,5,6')")
            con.commit()
            arquivo = storage.criar_backup('teste')
            with closing(sqlite3.connect(arquivo)) as copia:
                self.assertEqual(copia.execute('PRAGMA quick_check').fetchone()[0], 'ok')
                self.assertEqual(copia.execute('SELECT COUNT(*) FROM jogos').fetchone()[0], 1)
        self.assertNotEqual(arquivo, storage.criar_backup('teste'))
        self.assertEqual(list(arquivo.parent.glob('*.parcial')), [])

    def test_sync_backup_precedes_first_write_and_failure_prevents_update(self):
        payload = {'numero': 1, 'dataApuracao': '24/10/2026', 'listaDezenas': [1, 2, 3, 4, 5, 6]}
        with patch.object(sync, 'fetch_latest_megasena', return_value=(payload, 'teste')):
            r = sync.sincronizar_historico()
            with closing(sqlite3.connect(r['backup'])) as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM concursos').fetchone()[0], 0)
            self.assertEqual(conferir_concurso(1)['status'], 'sem_jogos')
            with patch.object(sync, 'criar_backup', side_effect=OSError('sem espaço')), patch.object(sync, 'salvar_concurso') as salvar:
                with self.assertRaises(OSError):
                    sync.sincronizar_historico()
                salvar.assert_not_called()

    def test_sync_result_automatically_changes_bound_contest_from_pending_to_checked(self):
        storage.salvar_jogo([1, 2, 3, 4, 5, 60])
        storage.vincular_jogos_concurso(1)
        self.assertEqual(conferir_concurso(1)['status'], 'aguardando_resultado')
        payload = {'numero': 1, 'dataApuracao': '24/10/2026', 'listaDezenas': [1, 2, 3, 4, 5, 6]}
        with patch.object(sync, 'fetch_latest_megasena', return_value=(payload, 'teste')):
            sync.sincronizar_historico()
        self.assertEqual(conferir_concurso(1)['resultados'][0]['faixa'], 'Quina')

    def test_import_and_single_update_backup_original_data(self):
        file = self.base / 'import.json'
        file.write_text(json.dumps([{'numero': 1, 'data_apuracao': '24/10/2026', 'dezenas': [1, 2, 3, 4, 5, 6]}]))
        storage.importar_historico(file)
        storage.atualizar_concurso(1, '24/10/2026', [1, 2, 3, 4, 5, 60])
        arquivos = list((self.base / 'backups').glob('*resultado*.db'))
        self.assertEqual(len(arquivos), 1)
        with closing(sqlite3.connect(arquivos[0])) as con:
            self.assertEqual(con.execute('SELECT dezenas FROM concursos WHERE numero=1').fetchone()[0], '01,02,03,04,05,06')

    def test_terminal_import_optimize_bind_and_check_without_adding_originals(self):
        app = TerminalApp.__new__(TerminalApp)
        app._busy = False
        app.println = Mock()
        app.last_suggestions = []
        app._run_background = lambda work, done, status: done(work())
        carteira = self.base / 'carteira teste.json'
        carteira.write_text(json.dumps({'jogos': [[1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 7]]}))
        app.dispatch(f'importar_carteira "{carteira}"')
        app.dispatch('cobertura sugestoes 6,50')
        self.assertTrue(any('R$ 13,00' in c.args[0] for c in app.println.call_args_list if c.args))
        app.dispatch('otimizar quadra sugestoes 6,50')
        self.assertEqual(len(app.last_suggestions), 2)
        self.assertEqual(storage.listar_jogos(), [])
        app.dispatch('vincular 1 sugestoes')
        self.assertEqual(len(storage.listar_apostas_concurso(1)), 2)
        self.assertEqual(sum(j['valor_centavos'] for j in storage.listar_apostas_concurso(1)), 1300)
        payload = {'numero': 1, 'dataApuracao': '24/10/2026', 'listaDezenas': [1, 2, 3, 4, 5, 6]}
        with patch.object(sync, 'fetch_latest_megasena', return_value=(payload, 'teste')):
            app.dispatch('atualizar')
        app.dispatch('conferir 1')
        self.assertTrue(any('acertos' in c.args[0] and 'Jogo ' in c.args[0] for c in app.println.call_args_list if c.args))
