# terminal_gui.py
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import json
import re
from queue import Empty, Queue
from threading import Thread

from megasena.api import (
    fetch_latest_megasena,
    dezenas_do_resultado,
    concurso_numero,
    concurso_data,
)
from megasena.compare import comparar_jogo, normalize_jogo
from megasena.storage import (
    init_db,
    salvar_jogo,
    listar_jogos,
    excluir_jogo,
    excluir_todos_jogos,
    salvar_concurso,
    ler_ultimo_concurso_salvo,
)
from megasena.stats import gerar_jogos_sugeridos, prob_acertar_sena


def parse_nums(tokens):
    """
    Cadeado Mega-Sena:
      - aceita 6 dezenas
      - cada uma deve estar entre 1 e 60
      - não permite repetição
      - aceita: add 1 2 3 4 5 6  |  add 1,2,3,4,5,6
    """
    if not tokens:
        raise ValueError("Informe 6 dezenas. Ex: add 5 12 23 34 45 60")

    tokens = " ".join(tokens).replace(",", " ").split()

    # converte e valida quantidade
    try:
        nums = [int(t) for t in tokens]
    except ValueError:
        raise ValueError("Use apenas números. Ex: add 5 12 23 34 45 60")

    if len(nums) != 6:
        raise ValueError(f"Você informou {len(nums)} dezena(s). A Mega-Sena exige exatamente 6.")

    # valida faixa 1..60
    fora = [n for n in nums if n < 1 or n > 60]
    if fora:
        raise ValueError(f"Dezenas inválidas (fora de 1..60): {sorted(set(fora))}")

    # valida repetição
    if len(set(nums)) != 6:
        repetidas = sorted([n for n in set(nums) if nums.count(n) > 1])
        raise ValueError(f"Dezenas repetidas não são permitidas: {repetidas}")

    # mantém o normalize_jogo como validação final/padrão do projeto
    return normalize_jogo(nums)


def parse_id(text: str) -> int:
    """
    Aceita: '9', 'ID9', 'id=9', '#9', 'ID: 9'...
    Retorna o número inteiro.
    """
    m = re.fullmatch(r"(?:id\s*[:=]?\s*|#\s*)?([1-9]\d*)", text.strip(), re.IGNORECASE)
    if not m:
        raise ValueError("ID inválido. Use: del 9 (ou del ID9)")
    return int(m.group(1))


class TerminalApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MegaSena Terminal")
        self.root.geometry("950x580")
        self.root.resizable(False, False)
        init_db()

        self.out = scrolledtext.ScrolledText(root, wrap=tk.WORD, height=24, font=("Consolas", 11))
        self.out.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 6))
        self.out.configure(state="disabled")

        bar = tk.Frame(root)
        bar.pack(fill=tk.X, padx=10, pady=(0, 10))

        tk.Label(bar, text="> ", font=("Consolas", 12)).pack(side=tk.LEFT)

        self.cmd = tk.Entry(bar, font=("Consolas", 12))
        self.cmd.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cmd.focus_set()

        tk.Button(bar, text="Executar", command=self.on_run).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(bar, text="Ajuda", command=self.print_help).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(bar, text="Limpar", command=self.clear_and_help).pack(side=tk.LEFT, padx=(8, 0))

        self.history = []
        self.hist_index = 0

        # guarda as últimas sugestões geradas (sessão)
        self.last_suggestions: list[list[int]] = []
        self._background_results = Queue()
        self._busy = False
        self._closed = False
        self._poll_id = self.root.after(100, self._drain_background_results)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.cmd.bind("<Return>", lambda e: self.on_run())
        self.cmd.bind("<Up>", self.on_up)
        self.cmd.bind("<Down>", self.on_down)

        self.println("🎟️ MegaSena Terminal iniciado.")
        self.println("✅ Banco local; consultas online em segundo plano.")
        self.print_help()

    def println(self, text=""):
        self.out.configure(state="normal")
        self.out.insert(tk.END, text + "\n")
        self.out.see(tk.END)
        self.out.configure(state="disabled")

    def clear_output(self):
        self.out.configure(state="normal")
        self.out.delete("1.0", tk.END)
        self.out.configure(state="disabled")

    def clear_and_help(self):
        self.clear_output()
        self.print_help()

    def _on_close(self):
        self._closed = True
        self.root.after_cancel(self._poll_id)
        self.root.destroy()

    def _run_background(self, work, on_success, status):
        """O worker só calcula; a fila entrega a resposta na thread do Tk."""
        if self._busy:
            self.println("⏳ Aguarde a consulta ou geração em andamento.")
            return
        self._busy = True
        self.println(status)

        def worker():
            try:
                result = work()
            except Exception as exc:
                self._background_results.put((on_success, None, exc))
            else:
                self._background_results.put((on_success, result, None))

        Thread(target=worker, daemon=True, name="megasena-terminal").start()

    def _drain_background_results(self):
        if self._closed:
            return
        try:
            on_success, result, error = self._background_results.get_nowait()
        except Empty:
            pass
        else:
            self._busy = False
            if error is not None:
                self.println(f"❌ Não foi possível concluir: {error}")
            else:
                try:
                    on_success(result)
                except Exception as exc:
                    self.println(f"❌ Não foi possível apresentar o resultado: {exc}")
        self._poll_id = self.root.after(100, self._drain_background_results)

    def _show_latest(self, result):
        numero, data, dezenas, fonte, from_cache = result
        tag = "📦 cache local, pode estar desatualizado" if from_cache else "🌐 online"
        self.println(f"📣 Concurso: {numero} ({data}) | Dezenas: {dezenas} ({tag}, fonte: {fonte})")

    def _show_comparisons(self, result):
        concurso, comparacoes = result
        self._show_latest(concurso)
        for jogo, comparacao in comparacoes:
            self.println(f"\nJogo id={jogo['id']} | {jogo['dezenas']}")
            self.println(f"🎯 Acertos: {comparacao['acertos_qtd']} |-> {comparacao['acertos']}")
        self.println()

    def _show_suggestions(self, suggestions):
        self.last_suggestions = suggestions
        self.println("🧠 Jogos distintos e diversificados (use 'save_suggested' para salvar):")
        for i, suggestion in enumerate(suggestions, 1):
            self.println(f"{i:02d}) {suggestion}")

    def _show_lines(self, lines):
        for line in lines:
            self.println(line)

    def _debug_latest(self):
        lines = []
        try:
            payload, fonte = fetch_latest_megasena()
            lines.append(f"Fonte: {fonte}")
            if isinstance(payload, dict):
                lines.append(f"Chaves do payload: {list(payload.keys())}")
            preview = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            if len(preview) > 900:
                preview = preview[:900] + "\n... (cortado)"
            lines.extend(["Payload (preview):", preview])
            try:
                dezenas = dezenas_do_resultado(payload)
                numero = concurso_numero(payload)
                data = concurso_data(payload)
                lines.append(f"✅ Extração OK -> Concurso: {numero} | Data: {data} | Dezenas: {dezenas}")
            except Exception as exc:
                lines.append(f"❌ Falha ao extrair dezenas: {exc}")
        except Exception as exc:
            lines.append(f"❌ Falha ao buscar online: {exc}")
            cached = ler_ultimo_concurso_salvo()
            if cached:
                lines.extend([
                    "📦 Cache encontrado no banco:",
                    f"Concurso: {cached['numero']} | Data: {cached['data_apuracao']} | Dezenas: {cached['dezenas']}",
                ])
            else:
                lines.append("📦 Sem cache salvo.")
        return lines

    def print_help(self):
        self.println()
        self.println("Comandos disponíveis:")
        self.println("  help                          -> mostra ajuda")
        self.println("  add N1 N2 N3 N4 N5 N6          -> salva um jogo (DEZENAS 1..60)")
        self.println("  list                          -> lista jogos salvos")
        self.println("  del ID                         -> exclui um jogo (aceita: 9, ID9, id=9, #9)")
        self.println("  delall                        -> exclui TODOS os jogos do banco (com confirmação)")
        self.println("  latest                        -> mostra último resultado (e salva em cache)")
        self.println("  compare                       -> compara TODOS jogos com o último resultado (usa cache se offline)")
        self.println("  suggest [N]                   -> gera N jogos distintos e diversificados (1..200, padrão 10)")
        self.println("  save_suggested                -> salva TODAS as sugestões geradas por 'suggest'")
        self.println("  save_suggested 1 3 5          -> salva só as sugestões pelos índices informados")
        self.println("  save_suggested ask            -> pergunta quantas salvar (no popup)")
        self.println("  prob                          -> mostra prob. de acertar sena (6/60)")
        self.println("  clear / cls                   -> limpa a tela e mostra os comandos")
        self.println("  debuglatest                   -> 🔎 mostra payload bruto e chaves da API")
        self.println("=~ " * 38)
        self.println()

    def on_up(self, event=None):
        if not self.history:
            return
        self.hist_index = max(0, self.hist_index - 1)
        self.cmd.delete(0, tk.END)
        self.cmd.insert(0, self.history[self.hist_index])

    def on_down(self, event=None):
        if not self.history:
            return
        self.hist_index = min(len(self.history), self.hist_index + 1)
        self.cmd.delete(0, tk.END)
        if self.hist_index < len(self.history):
            self.cmd.insert(0, self.history[self.hist_index])

    def on_run(self):
        line = self.cmd.get().strip()
        if not line:
            return
        self.history.append(line)
        self.hist_index = len(self.history)
        self.println(f"> {line}")
        self.cmd.delete(0, tk.END)
        try:
            self.dispatch(line)
        except Exception as e:
            self.println(f"❌ Erro: {e}")

    def _fetch_latest_or_cache(self):
        try:
            payload, fonte = fetch_latest_megasena()
            dezenas = dezenas_do_resultado(payload)
            numero = concurso_numero(payload)
            data = concurso_data(payload)
            salvar_concurso(numero, data, dezenas)
            return numero, data, dezenas, fonte, False
        except Exception as e:
            cached = ler_ultimo_concurso_salvo()
            if cached:
                return cached["numero"], cached["data_apuracao"], cached["dezenas"], f"cache (erro API: {e})", True
            raise

    def _save_suggestions_by_indices(self, indices: list[int]):
        if not self.last_suggestions:
            self.println("⚠️ Nenhuma sugestão na memória. Rode: suggest 10")
            return

        saved_ids = []
        for idx in indices:
            if idx < 1 or idx > len(self.last_suggestions):
                self.println(f"⚠️ Índice inválido: {idx} (válido 1..{len(self.last_suggestions)})")
                continue
            jogo = self.last_suggestions[idx - 1]
            jid = salvar_jogo(jogo)
            saved_ids.append(jid)

        if saved_ids:
            self.println(f"✅ Sugestões salvas! IDs criados: {saved_ids}")
        else:
            self.println("⚠️ Nada foi salvo.")

    def dispatch(self, line: str):
        parts = line.split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("help", "?"):
            self.print_help()
            return

        if cmd in ("clear", "cls"):
            self.clear_and_help()
            return

        if cmd == "add":
            jogo = parse_nums(args)
            jid = salvar_jogo(jogo)
            self.println(f"✅ Jogo salvo (id={jid}): {jogo}")
            return

        if cmd == "list":
            jogos = listar_jogos()
            if not jogos:
                self.println("Sem jogos salvos.")
                return
            for j in reversed(jogos):
                self.println(f"id={j['id']} |-> {j['dezenas']}")
            return

        if cmd in ("del", "delete", "rm", "remove"):
            if not args:
                raise ValueError("Use: del ID  (ex: del 7)")
            jid = parse_id(" ".join(args))
            ok = excluir_jogo(jid)
            self.println(f"🗑️ Jogo id={jid} excluído." if ok else f"⚠️ Não encontrei jogo com id={jid}.")
            return

        if cmd in ("delall", "deleteall", "rmall", "clearall"):
            if not messagebox.askyesno("Confirmar", "Apagar TODOS os jogos do banco?"):
                self.println("Cancelado.")
                return
            qtd = excluir_todos_jogos()
            self.println(f"🧹 Removi {qtd} jogo(s).")
            return

        if cmd == "latest":
            self._run_background(self._fetch_latest_or_cache, self._show_latest, "⏳ Consultando último resultado…")
            return

        if cmd == "compare":
            jogos = listar_jogos()
            if not jogos:
                self.println("Você ainda não tem jogos salvos. Use: add ...")
                return

            def compare():
                concurso = self._fetch_latest_or_cache()
                return concurso, [(j, comparar_jogo(j["dezenas"], concurso[2])) for j in reversed(jogos)]

            self._run_background(compare, self._show_comparisons, "⏳ Consultando resultado para comparar jogos…")
            return

        if cmd == "suggest":
            n = 10
            if args:
                try:
                    if len(args) != 1:
                        raise ValueError
                    n = int(args[0])
                except ValueError:
                    raise ValueError("Use: suggest N, com N inteiro de 1 a 200.") from None
                if n < 1 or n > 200:
                    raise ValueError("N precisa estar entre 1 e 200.")
            self.println(f"📌 Prob. de acertar a sena por jogo (6/60): {prob_acertar_sena():.10f} (1 em 50.063.860)")
            self.println("Cada combinação tem a mesma chance em um sorteio justo. O histórico não prevê o próximo resultado.")

            def suggest():
                return gerar_jogos_sugeridos(
                    n_sugestoes=n,
                    estrategia="diversificada",
                    excluir=[j["dezenas"] for j in listar_jogos()],
                )

            self._run_background(suggest, self._show_suggestions, "⏳ Gerando jogos distintos dos já salvos…")
            return

        if cmd == "save_suggested":
            if self._busy:
                self.println("⏳ Aguarde a consulta ou geração em andamento antes de salvar sugestões.")
                return
            if not self.last_suggestions:
                self.println("⚠️ Nenhuma sugestão na memória. Rode: suggest 10")
                return

            if not args:
                indices = list(range(1, len(self.last_suggestions) + 1))
                self._save_suggestions_by_indices(indices)
                return

            if args[0].lower() == "ask":
                q = simpledialog.askinteger(
                    "Salvar sugestões",
                    f"Quantas sugestões salvar? (1..{len(self.last_suggestions)})",
                    minvalue=1,
                    maxvalue=len(self.last_suggestions),
                )
                if q is None:
                    self.println("Cancelado.")
                    return
                indices = list(range(1, q + 1))
                self._save_suggestions_by_indices(indices)
                return

            try:
                indices = [int(x) for x in args]
            except ValueError:
                raise ValueError("Informe índices inteiros. Exemplo: save_suggested 1 3 5") from None
            self._save_suggestions_by_indices(indices)
            return

        if cmd == "prob":
            self.println(f"📌 Prob. de acertar a sena por jogo (6/60): {prob_acertar_sena():.10f} (1 em 50.063.860)")
            self.println("Cada combinação tem a mesma chance em um sorteio justo; repetir um jogo não aumenta a cobertura.")
            return

        if cmd == "debuglatest":
            self._run_background(self._debug_latest, self._show_lines, "🔎 Consultando dados da API…")
            return

        raise ValueError("Comando desconhecido. Digite 'help' para ver os comandos.")


if __name__ == "__main__":
    root = tk.Tk()
    app = TerminalApp(root)
    root.mainloop()
