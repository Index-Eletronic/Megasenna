"""Smoke do desktop com Tk oculto, banco temporário e nenhuma consulta de rede."""
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
from uuid import uuid4

import desktop_gui
from megasena import storage


class DesktopTests(unittest.TestCase):
    def setUp(self):
        # Arquivo temporário no projeto: mkdir(mode=0700) do tempfile no Python
        # 3.13 pode gerar ACL incompatível com tokens restritos no Windows.
        test_directory = Path(__file__).resolve().parent
        self.database = test_directory / f".desktop-smoke-{uuid4().hex}.db"
        self.addCleanup(self.remove_database)
        self.db_patch = patch.object(storage, "DB_PATH", self.database)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.network_patch = patch("desktop_gui.sincronizar_historico", side_effect=AssertionError("O smoke não deve acessar a rede"))
        self.network = self.network_patch.start()
        self.addCleanup(self.network_patch.stop)
        self.error_patch = patch("desktop_gui.messagebox.showerror")
        self.errors = self.error_patch.start()
        self.addCleanup(self.error_patch.stop)
        self.confirm_patch = patch("desktop_gui.messagebox.askyesno", return_value=True)
        self.confirm_patch.start()
        self.addCleanup(self.confirm_patch.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.destroy_root)
        self.app = desktop_gui.MegaSenaApp(self.root)
        self.root.update_idletasks()

    def remove_database(self):
        for suffix in ("", "-journal", "-wal", "-shm"):
            path = Path(str(self.database) + suffix)
            self.assertEqual(path.resolve().parent, Path(__file__).resolve().parent)
            path.unlink(missing_ok=True)

    def destroy_root(self):
        if self.root.winfo_exists():
            for callback in self.root.tk.call("after", "info"):
                self.root.after_cancel(callback)
            self.root.destroy()

    def find_button(self, text):
        def visit(widget):
            if isinstance(widget, ttk.Button) and widget.cget("text") == text:
                return widget
            for child in widget.winfo_children():
                found = visit(child)
                if found is not None:
                    return found
            return None

        result = visit(self.root)
        self.assertIsNotNone(result, f"Botão não encontrado: {text}")
        return result

    def insert(self, entry, value):
        entry.delete(0, "end")
        entry.insert(0, value)

    def wait_for_job(self, timeout=8):
        deadline = time.monotonic() + timeout
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.app.busy, "O resultado do worker não foi entregue à interface")

    def populate_history(self):
        for numero in range(1, 36):
            nums = [1, 2, 3, 4, 5, 6] if numero % 7 == 0 else [7, 8, 9, 10, 11, 12]
            storage.salvar_concurso(numero, f"{1 + (numero - 1) % 28:02d}/01/2026", nums)
        self.app.refresh()

    def add_game(self, text="1 2 3 4 5 6"):
        self.insert(self.app.game_entry, text)
        self.find_button("Salvar jogo").invoke()

    def test_startup_builds_four_tabs_without_network_or_visible_window(self):
        names = [self.app.tabs.tab(tab, "text") for tab in self.app.tabs.tabs()]
        self.assertEqual(names, ["Concursos", "Estatísticas", "Meus jogos e sugestões", "Probabilidades e avaliação"])
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertEqual(self.app.history_table.get_children(), ())
        self.assertEqual(self.app.games_table.get_children(), ())
        self.assertIn("0 concursos locais", self.app.summary.get())
        self.assertTrue(storage.DB_PATH.is_file())
        self.network.assert_not_called()
        self.errors.assert_not_called()

    def test_history_filter_and_statistics_use_local_fixture(self):
        self.populate_history()
        self.insert(self.app.first, "11")
        self.insert(self.app.last, "15")
        self.find_button("Consultar").invoke()
        rows = [self.app.history_table.item(row, "values") for row in self.app.history_table.get_children()]
        self.assertEqual([int(row[0]) for row in rows], [15, 14, 13, 12, 11])
        self.assertIn("5 resultados nesta consulta", self.app.history_note.get())
        self.assertEqual(len(self.app.stats_table.get_children()), 60)
        self.assertIn("35 concursos locais", self.app.stats_note.get())
        self.network.assert_not_called()
        self.errors.assert_not_called()

    def test_save_game_rejects_same_combination_in_different_order(self):
        self.add_game("6, 5, 4, 3, 2, 1")
        self.assertEqual(storage.listar_jogos()[0]["dezenas"], [1, 2, 3, 4, 5, 6])
        self.add_game("1 2 3 4 5 6")
        self.assertEqual(len(storage.listar_jogos()), 1)
        self.assertEqual(len(self.app.games_table.get_children()), 1)
        self.errors.assert_called_once()
        self.assertIn("já está salvo", self.errors.call_args.args[1])
        self.assertIn("1 jogos distintos", self.app.coverage.get())

    def test_delete_game_requires_selection_and_confirmation(self):
        self.add_game()
        self.find_button("Excluir").invoke()
        self.assertEqual(len(storage.listar_jogos()), 1)
        self.assertIn("Selecione", self.errors.call_args.args[1])
        row = self.app.games_table.get_children()[0]
        self.app.games_table.selection_set(row)
        self.find_button("Excluir").invoke()
        self.assertEqual(storage.listar_jogos(), [])

    def test_invalid_history_keeps_application_open_for_repair(self):
        with storage.connect() as con:
            con.execute("INSERT INTO concursos VALUES (1, NULL, '1,1,1,1,1,1')")
        self.app.refresh()
        self.assertIn("resultado(s) inválido(s)", self.app.history_note.get())
        self.assertEqual(self.app.stats_table.get_children(), ())
        self.assertEqual(str(self.app.sync_button.cget("state")), "normal")

    def test_consulting_latest_progress_does_not_require_total(self):
        self.app.events.put(("progress", {"processados": 0, "total": None, "numero": None, "status": "consultando"}))
        self.app.poll()
        self.assertIn("Consultando último concurso", self.app.status.get())

    def test_async_generation_uses_worker_and_updates_tk_on_main_thread(self):
        self.add_game()
        self.app.quantity.set("4")
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        worker_threads = []
        callback_threads = []
        main_thread = threading.get_ident()
        generator = desktop_gui.gerar_jogos_sugeridos
        write = self.app.write

        def generate(**kwargs):
            worker_threads.append(threading.get_ident())
            started.set()
            try:
                if not release.wait(5):
                    raise RuntimeError("Worker não liberado pelo teste")
                return generator(seed=42, **kwargs)
            finally:
                finished.set()

        def write_result(widget, text):
            callback_threads.append(threading.get_ident())
            return write(widget, text)

        with patch("desktop_gui.gerar_jogos_sugeridos", side_effect=generate) as mocked, \
                patch.object(self.app, "write", side_effect=write_result):
            self.find_button("Gerar").invoke()
            try:
                self.assertTrue(started.wait(3))
                self.assertTrue(self.app.busy)
                self.root.update()
                self.assertEqual(callback_threads, [])
            finally:
                release.set()
            self.wait_for_job()
            self.assertTrue(finished.is_set())
        self.assertNotEqual(worker_threads, [main_thread])
        self.assertEqual(callback_threads, [main_thread])
        mocked.assert_called_once_with(n_sugestoes=4, estrategia="diversificada", excluir=[[1, 2, 3, 4, 5, 6]])
        self.assertEqual(len(self.app.suggestions), 4)
        self.assertEqual(len({tuple(game) for game in self.app.suggestions}), 4)
        self.assertNotIn([1, 2, 3, 4, 5, 6], self.app.suggestions)
        self.assertIn("Nenhuma combinação individual é mais provável", self.app.game_output.get("1.0", "end"))
        self.find_button("Salvar sugestões").invoke()
        self.assertEqual(len(storage.listar_jogos()), 5)
        self.find_button("Salvar sugestões").invoke()
        self.assertEqual(len(storage.listar_jogos()), 5)
        self.assertIn("0 novos jogos salvos", self.app.status.get())
        self.errors.assert_not_called()
        self.network.assert_not_called()

    def test_historical_check_counts_all_draws_and_limits_display_to_thirty(self):
        self.populate_history()
        self.add_game()
        self.app.games_table.selection_set(self.app.games_table.get_children()[0])
        self.find_button("Conferir selecionado no histórico").invoke()
        output = self.app.game_output.get("1.0", "end")
        self.assertIn("em 35 concursos locais", output)
        self.assertIn("0 acertos: 30", output)
        self.assertIn("6 acertos: 5", output)
        self.assertEqual(sum(line.startswith("Concurso ") for line in output.splitlines()), 30)
        self.errors.assert_not_called()
        self.network.assert_not_called()

    def test_chronological_evaluation_runs_from_local_draws(self):
        self.populate_history()
        self.find_button("Executar avaliação histórica").invoke()
        self.wait_for_job(timeout=20)
        output = self.app.backtest_output.get("1.0", "end")
        self.assertIn("Concursos avaliados: 5", output)
        self.assertIn("jogos por concurso: 10", output)
        self.assertIn("Diversificada:", output)
        self.assertIn("Aleatória:", output)
        self.assertIn("Avaliação concluída", self.app.status.get())
        self.errors.assert_not_called()
        self.network.assert_not_called()

    def test_worker_failure_is_presented_and_releases_busy_state(self):
        with patch("desktop_gui.gerar_jogos_sugeridos", side_effect=ValueError("falha simulada")):
            self.find_button("Gerar").invoke()
            self.wait_for_job()
        self.errors.assert_called_once()
        self.assertIn("falha simulada", self.errors.call_args.args[1])
        self.assertEqual(str(self.app.sync_button.cget("state")), "normal")
        self.assertEqual(str(self.app.cancel_button.cget("state")), "disabled")


if __name__ == "__main__":
    unittest.main()
