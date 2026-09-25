import io
from contextlib import redirect_stdout
from queue import Queue
from threading import Event, get_ident
import unittest
from unittest.mock import Mock, patch

import main
from terminal_gui import TerminalApp, parse_id, parse_nums


class CliTests(unittest.TestCase):
    def run_cli(self, answers):
        output = io.StringIO()
        with patch("builtins.input", side_effect=answers), patch("main.init_db"), redirect_stdout(output):
            main.main()
        return output.getvalue()

    def test_compare_unpacks_payload_and_uses_normalized_fields(self):
        payload = {"concurso": 3210, "data": "24/09/2026", "dezenas": ["01", "02", "03", "04", "05", "06"]}
        jogos = [{"id": 4, "criado_em": "2026-09-24", "dezenas": [1, 2, 3, 4, 5, 7]}]
        with patch("main.fetch_latest_megasena", return_value=(payload, "fonte-teste")), \
                patch("main.listar_jogos", return_value=jogos), patch("main.salvar_concurso") as save:
            output = self.run_cli(["2"])
        self.assertIn("Concurso: 3210", output)
        self.assertIn("24/09/2026", output)
        self.assertIn("Acertos: 5", output)
        self.assertIn("fonte-teste", output)
        save.assert_called_once_with(3210, "24/09/2026", [1, 2, 3, 4, 5, 6])

    def test_compare_uses_local_cache_if_api_unavailable(self):
        cached = {"numero": 3209, "data_apuracao": "22/09/2026", "dezenas": [1, 2, 3, 4, 5, 6]}
        jogos = [{"id": 1, "criado_em": "2026-09-24", "dezenas": [1, 2, 3, 4, 5, 6]}]
        with patch("main.fetch_latest_megasena", side_effect=main.MegaSenaAPIError("offline")), \
                patch("main.listar_jogos", return_value=jogos), \
                patch("main.ler_ultimo_concurso_salvo", return_value=cached):
            output = self.run_cli(["2"])
        self.assertIn("cache local", output)
        self.assertIn("Acertos: 6", output)

    def test_suggestions_exclude_saved_games(self):
        jogos = [{"dezenas": [1, 2, 3, 4, 5, 6]}]
        with patch("main.listar_jogos", return_value=jogos), \
                patch("main.gerar_jogos_sugeridos", return_value=[[7, 8, 9, 10, 11, 12]]) as generate:
            output = self.run_cli(["3", "1"])
        generate.assert_called_once_with(n_sugestoes=1, estrategia="diversificada", excluir=[[1, 2, 3, 4, 5, 6]])
        self.assertIn("mesma chance", output)

    def test_invalid_suggestion_quantity_has_friendly_message(self):
        for quantity in ("zero", "0", "-1", "201", "1.5"):
            with self.subTest(quantity=quantity), patch("main.gerar_jogos_sugeridos") as generate:
                output = self.run_cli(["3", quantity])
            self.assertIn("quantidade inteira de 1 a 200", output)
            generate.assert_not_called()

    def test_invalid_game_does_not_save(self):
        with patch("main.salvar_jogo") as save:
            output = self.run_cli(["1", "1 2 tres 4 5 6"])
        self.assertIn("Use apenas números", output)
        save.assert_not_called()


class TerminalTests(unittest.TestCase):
    def make_app(self):
        app = TerminalApp.__new__(TerminalApp)
        app.root = Mock()
        app.println = Mock()
        app._background_results = Queue()
        app._busy = False
        app._closed = False
        return app

    def test_worker_does_not_call_ui_until_queue_is_polled(self):
        app = self.make_app()
        main_thread = get_ident()
        release = Event()
        started = Event()
        finished = Event()
        worker_thread = []
        callback_thread = []

        def work():
            worker_thread.append(get_ident())
            started.set()
            self.assertTrue(release.wait(3))
            return "resultado"

        def show(result):
            callback_thread.append(get_ident())
            self.assertEqual(result, "resultado")

        original_put = app._background_results.put

        def put_result(result):
            original_put(result)
            finished.set()

        app._background_results.put = put_result
        app._run_background(work, show, "Consultando")
        self.assertTrue(started.wait(3))
        self.assertTrue(app._busy)
        self.assertFalse(callback_thread)
        app.root.assert_not_called()
        release.set()
        self.assertTrue(finished.wait(3))
        self.assertFalse(callback_thread)
        app._drain_background_results()
        self.assertNotEqual(worker_thread, [main_thread])
        self.assertEqual(callback_thread, [main_thread])
        self.assertFalse(app._busy)
        app.root.after.assert_called_once()

    def test_worker_error_is_reported_on_main_thread_and_allows_retry(self):
        app = self.make_app()
        callback = Mock()
        app._busy = True
        app._background_results.put((callback, None, RuntimeError("offline")))
        app._drain_background_results()
        callback.assert_not_called()
        self.assertFalse(app._busy)
        self.assertIn("offline", app.println.call_args.args[0])

    def test_delete_accepts_documented_ids_only(self):
        for text in ("9", "ID9", "id=9", "#9", "ID: 9"):
            self.assertEqual(parse_id(text), 9)
        for text in ("-9", "abc9", "9 10", "9.5", "0"):
            with self.assertRaises(ValueError):
                parse_id(text)

    def test_comma_and_space_separated_numbers(self):
        self.assertEqual(parse_nums(["1,", "2,", "3,", "4,", "5,", "6"]), [1, 2, 3, 4, 5, 6])


if __name__ == "__main__":
    unittest.main()
