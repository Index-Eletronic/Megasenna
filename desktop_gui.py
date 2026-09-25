"""Aplicativo local: Tk só é acessado pela thread principal."""
from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from megasena import storage
from megasena.compare import normalize_jogo
from megasena.stats import (
    analisar_historico, backtest_cronologico, conferir_historico,
    cobertura_sena, gerar_jogos_sugeridos, probabilidades_jogo_simples,
)
from megasena.sync import sincronizar_historico


def dezenas_texto(nums):
    return "  ".join(f"{n:02d}" for n in nums)


def ler_dezenas(text):
    return normalize_jogo([int(n) for n in text.replace(",", " ").split()])


class MegaSenaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Megasenna · Histórico e análise local")
        self.root.geometry("1160x800")
        self.root.minsize(940, 680)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.suggestions = []
        self.closed = False
        storage.init_db()
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f4f6f8")
        style.configure("TLabel", background="#f4f6f8", foreground="#17332c", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
        style.configure("Sub.TLabel", foreground="#50635e")
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook.Tab", padding=(18, 9))
        shell = ttk.Frame(root, padding=20)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Megasenna", style="Title.TLabel").pack(anchor="w")
        ttk.Label(shell, text="Histórico verificável. Estatísticas descritivas. Jogos distintos.", style="Sub.TLabel").pack(anchor="w", pady=(2, 12))
        top = ttk.Frame(shell)
        top.pack(fill="x", pady=(0, 8))
        self.sync_button = ttk.Button(top, text="Atualizar histórico CAIXA", command=self.sync_history)
        self.sync_button.pack(side="left")
        self.cancel_button = ttk.Button(top, text="Cancelar atualização", command=self.cancel.set, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self.summary = tk.StringVar()
        ttk.Label(top, textvariable=self.summary).pack(side="left", padx=8)
        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True)
        self._history_tab()
        self._stats_tab()
        self._games_tab()
        self._validation_tab()
        self.progress = ttk.Progressbar(shell, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 5))
        self.status = tk.StringVar(value="Pronto. As consultas locais funcionam sem internet.")
        ttk.Label(shell, textvariable=self.status, wraplength=1080).pack(anchor="w")
        ttk.Label(shell, text=f"Banco local: {storage.DB_PATH}", style="Sub.TLabel", wraplength=1080).pack(anchor="w", pady=(3, 0))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.root.after(100, self.poll)

    def tab(self, name):
        frame = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(frame, text=name)
        return frame

    def table(self, parent, columns, headings, widths, height=12):
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True, pady=8)
        tree = ttk.Treeview(holder, columns=columns, show="headings", height=height)
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, anchor="center")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

    def _history_tab(self):
        frame = self.tab("Concursos")
        ttk.Label(frame, text="A atualização busca os concursos ausentes desde o nº 1 e pode ser retomada após interrupções.", wraplength=1000).pack(anchor="w")
        filters = ttk.Frame(frame)
        filters.pack(fill="x", pady=(10, 0))
        ttk.Label(filters, text="Do concurso").pack(side="left")
        self.first = ttk.Entry(filters, width=9)
        self.first.pack(side="left", padx=8)
        ttk.Label(filters, text="até").pack(side="left")
        self.last = ttk.Entry(filters, width=9)
        self.last.pack(side="left", padx=8)
        ttk.Button(filters, text="Consultar", command=lambda: self.safe(self.refresh_history)).pack(side="left")
        ttk.Button(filters, text="Exportar histórico JSON", command=self.export_history).pack(side="left", padx=8)
        ttk.Button(filters, text="Importar JSON", command=self.import_history).pack(side="left")
        self.history_table = self.table(frame, ("number", "date", "numbers"), ("Concurso", "Data", "Dezenas sorteadas"), (130, 180, 500))
        self.history_note = tk.StringVar()
        ttk.Label(frame, textvariable=self.history_note, wraplength=1000).pack(anchor="w")

    def _stats_tab(self):
        frame = self.tab("Estatísticas")
        ttk.Label(frame, text="Cada dezena tem chance de 10% de aparecer em um sorteio justo. Frequência e atraso descrevem o passado; não preveem o próximo resultado.", wraplength=1000).pack(anchor="w")
        self.stats_table = self.table(frame, ("number", "count", "percent", "delay"), ("Dezena", "Ocorrências", "% dos concursos locais", "Concursos locais sem aparecer"), (110, 150, 220, 300))
        self.stats_note = tk.StringVar()
        ttk.Label(frame, textvariable=self.stats_note, wraplength=1000).pack(anchor="w")

    def _games_tab(self):
        frame = self.tab("Meus jogos e sugestões")
        line = ttk.Frame(frame)
        line.pack(fill="x")
        ttk.Label(line, text="6 dezenas:").pack(side="left")
        self.game_entry = ttk.Entry(line, width=27)
        self.game_entry.pack(side="left", padx=8)
        ttk.Button(line, text="Salvar jogo", command=lambda: self.safe(self.add_game)).pack(side="left")
        ttk.Button(line, text="Conferir selecionado no histórico", command=lambda: self.safe(self.check_game)).pack(side="left", padx=8)
        ttk.Button(line, text="Excluir", command=lambda: self.safe(self.delete_game)).pack(side="left")
        self.games_table = self.table(frame, ("id", "numbers", "created"), ("ID", "Dezenas", "Salvo em"), (70, 400, 210), height=5)
        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        ttk.Label(controls, text="Sugestões:").pack(side="left")
        self.quantity = ttk.Spinbox(controls, from_=1, to=200, width=5)
        self.quantity.set("10")
        self.quantity.pack(side="left", padx=6)
        self.strategy = ttk.Combobox(controls, values=("diversificada", "aleatoria"), state="readonly", width=15)
        self.strategy.set("diversificada")
        self.strategy.pack(side="left", padx=6)
        ttk.Button(controls, text="Gerar", command=lambda: self.safe(self.generate)).pack(side="left", padx=6)
        ttk.Button(controls, text="Salvar sugestões", command=lambda: self.safe(self.save_suggestions)).pack(side="left", padx=6)
        ttk.Button(controls, text="Exportar jogos JSON", command=self.export_games).pack(side="left", padx=6)
        self.game_output = scrolledtext.ScrolledText(frame, height=9, font=("Consolas", 10), wrap="word", state="disabled")
        self.game_output.pack(fill="both", expand=True, pady=8)
        self.coverage = tk.StringVar()
        ttk.Label(frame, textvariable=self.coverage, wraplength=1000).pack(anchor="w")

    def _validation_tab(self):
        frame = self.tab("Probabilidades e avaliação")
        odds = probabilidades_jogo_simples()
        text = "Aposta simples de 6 dezenas — probabilidades exatas por concurso\n\n"
        for name in ("sena", "quina", "quadra"):
            item = odds[name]
            text += f"{name.capitalize()}: 1 em {item['um_em']:,.2f}  ({item['probabilidade']*100:.8f}%)\n"
        text += "\nJogos diferentes ampliam a cobertura da sena proporcionalmente à quantidade.\nDiversificação reduz repetição de grupos entre jogos; não torna uma combinação mais provável."
        ttk.Label(frame, text=text, justify="left", wraplength=1000).pack(anchor="w")
        ttk.Separator(frame).pack(fill="x", pady=14)
        ttk.Label(frame, text="Avaliação cronológica: 10 jogos por concurso, comparados com 10 jogos aleatórios.\nUsa até os 100 últimos concursos locais após ao menos 30 de histórico anterior; semente 42.", wraplength=1000).pack(anchor="w")
        ttk.Button(frame, text="Executar avaliação histórica", command=lambda: self.safe(self.backtest)).pack(anchor="w", pady=8)
        self.backtest_output = scrolledtext.ScrolledText(frame, height=12, font=("Consolas", 10), wrap="word", state="disabled")
        self.backtest_output.pack(fill="both", expand=True)
        self.write(self.backtest_output, "A avaliação é retrospectiva e descritiva. Não comprova capacidade de prever sorteios futuros.\nSomente concursos anteriores a cada resultado podem compor o treino.")

    @staticmethod
    def write(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.configure(state="disabled")

    def safe(self, action):
        try:
            action()
        except Exception as exc:
            messagebox.showerror("Não foi possível concluir", str(exc), parent=self.root)

    def refresh(self):
        summary = storage.resumo_historico()
        self.summary.set(f"{summary['total']} concursos locais · maior nº {summary['ultimo'] or '—'}")
        if summary['invalidos']:
            self.history_table.delete(*self.history_table.get_children())
            self.stats_table.delete(*self.stats_table.get_children())
            self.history_note.set(f"Há {len(summary['invalidos'])} resultado(s) inválido(s) no banco. Clique em Atualizar histórico CAIXA para reparar os registros.")
            self.stats_note.set("As estatísticas ficarão disponíveis após reparar o histórico.")
            self.refresh_games()
            return
        try:
            self.refresh_history()
        except ValueError:
            self.first.delete(0, "end")
            self.last.delete(0, "end")
            self.refresh_history()
        self.refresh_stats()
        self.refresh_games()

    def refresh_history(self):
        start = int(self.first.get()) if self.first.get().strip() else None
        end = int(self.last.get()) if self.last.get().strip() else None
        draws = storage.listar_concursos(inicio=start, fim=end)
        self.history_table.delete(*self.history_table.get_children())
        for draw in reversed(draws):
            self.history_table.insert("", "end", values=(draw['numero'], draw['data_apuracao'], dezenas_texto(draw['dezenas'])))
        summary = storage.resumo_historico()
        missing = summary['lacunas']
        if missing:
            note = f"Base incompleta: {len(missing)} concursos ausentes até o nº {summary['ultimo']}. Atualize o histórico."
        elif not summary['total']:
            note = "Base vazia. Use Atualizar histórico CAIXA para obter os resultados oficiais."
        else:
            note = f"Sequência local sem lacunas do nº 1 ao {summary['ultimo']}. Atualize para verificar novos concursos."
        self.history_note.set(f"{len(draws)} resultados nesta consulta. {note}")

    def refresh_stats(self):
        draws = storage.listar_concursos()
        self.stats_table.delete(*self.stats_table.get_children())
        if not draws:
            self.stats_note.set("Atualize o histórico para calcular as estatísticas.")
            return
        result = analisar_historico(draws)
        for row in result['frequencias']:
            delay = f">= {row['atraso']}" if row.get('nunca_observada') else row['atraso']
            self.stats_table.insert("", "end", values=(f"{row['dezena']:02d}", row['ocorrencias'], f"{row['percentual']:.2f}%", delay))
        pairs = "; ".join(f"{dezenas_texto(p['dezenas'])}: {p['ocorrencias']}" for p in result['pares_frequentes'][:5])
        parity = ", ".join(f"{k} pares: {v}" for k, v in result['distribuicao_pares'].items())
        self.stats_note.set(f"Base: {result['total_concursos']} concursos locais. Soma média: {result['soma']['media']:.1f}.\nDistribuição: {parity}.\nPares mais frequentes: {pairs}. Atraso conta apenas registros disponíveis; lacunas limitam a análise.")

    def refresh_games(self):
        games = storage.listar_jogos()
        self.games_table.delete(*self.games_table.get_children())
        for game in games:
            self.games_table.insert("", "end", iid=str(game['id']), values=(game['id'], dezenas_texto(game['dezenas']), game['criado_em']))
        unique = len({tuple(g['dezenas']) for g in games})
        probability = cobertura_sena([g['dezenas'] for g in games])
        self.coverage.set(f"{len(games)} registros · {unique} jogos distintos · cobertura da sena: {probability*100:.8f}% por concurso se todos forem apostados.")

    def add_game(self):
        nums = ler_dezenas(self.game_entry.get())
        if tuple(nums) in {tuple(g['dezenas']) for g in storage.listar_jogos()}:
            raise ValueError("Este jogo já está salvo. Uma cópia não amplia a cobertura.")
        storage.salvar_jogo(nums)
        self.game_entry.delete(0, "end")
        self.refresh_games()
        self.status.set("Jogo salvo no banco local.")

    def delete_game(self):
        selection = self.games_table.selection()
        if not selection:
            raise ValueError("Selecione um jogo para excluir.")
        game_id = int(selection[0])
        if messagebox.askyesno("Excluir jogo", f"Excluir o jogo {game_id} do banco local?", parent=self.root):
            storage.excluir_jogo(game_id)
            self.refresh_games()
            self.status.set(f"Jogo {game_id} excluído.")

    def check_game(self):
        selection = self.games_table.selection()
        if not selection:
            raise ValueError("Selecione um jogo salvo na tabela.")
        game = next(g for g in storage.listar_jogos() if str(g['id']) == selection[0])
        draws = storage.listar_concursos()
        if not draws:
            raise ValueError("Atualize o histórico antes de conferir.")
        results = conferir_historico(game['dezenas'], draws)
        counts = {n: sum(r['acertos_qtd'] == n for r in results) for n in range(7)}
        lines = [f"Jogo {game['id']}: {dezenas_texto(game['dezenas'])}", f"Conferência retrospectiva em {len(results)} concursos locais (não representa apostas realizadas).", " | ".join(f"{n} acertos: {counts[n]}" for n in range(7)), "", "Maiores acertos (até 30 resultados):"]
        for result in sorted(results, key=lambda r: (r['acertos_qtd'], r['numero']), reverse=True)[:30]:
            lines.append(f"Concurso {result['numero']} · {result['data_apuracao']} · {result['acertos_qtd']} acertos: {dezenas_texto(result['acertos'])}")
        self.write(self.game_output, "\n".join(lines))

    def start_job(self, work, success, label, cancellable=False):
        if self.busy:
            raise ValueError("Aguarde a operação em andamento terminar.")
        self.busy = True
        self.cancel.clear()
        self.sync_button.configure(state="disabled")
        self.cancel_button.configure(state="normal" if cancellable else "disabled")
        self.status.set(label)
        self.progress.configure(value=0, maximum=100)

        def run():
            try:
                result = work()
                self.events.put(("done", (success, result)))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    self.progress.configure(maximum=max(1, value['total'] or 1), value=value['processados'])
                    if value['total'] is None:
                        self.status.set("Consultando último concurso na CAIXA…")
                    else:
                        self.status.set(f"Atualizando histórico: {value['processados']}/{value['total']} · concurso {value['numero']} · {value['status']}")
                else:
                    self.busy = False
                    self.sync_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    if kind == "error":
                        self.status.set(f"Operação não concluída: {value}")
                        messagebox.showerror("Operação não concluída", value, parent=self.root)
                    else:
                        callback, result = value
                        self.safe(lambda: callback(result))
        except queue.Empty:
            pass
        if not self.closed:
            self.root.after(100, self.poll)

    def sync_history(self):
        def work():
            return sincronizar_historico(progresso=lambda p: self.events.put(("progress", p)), cancelar=self.cancel)

        def done(result):
            self.refresh()
            self.progress.configure(maximum=1, value=1 if result['completo'] else 0)
            if result['completo']:
                self.status.set(f"Histórico completo até o concurso {result['ultimo_oficial']}. {result['baixados']} resultados atualizados.")
            else:
                self.status.set(f"Atualização {result['status']}. Dados recebidos foram preservados. {len(result['falhas'])} falhas; execute novamente para retomar.")

        self.safe(lambda: self.start_job(work, done, "Consultando último concurso na CAIXA…", cancellable=True))

    def generate(self):
        count = int(self.quantity.get())
        if not 1 <= count <= 200:
            raise ValueError("Escolha de 1 a 200 sugestões.")
        strategy = self.strategy.get()
        excluded = [g['dezenas'] for g in storage.listar_jogos()]

        def done(games):
            self.suggestions = games
            probability = cobertura_sena(games)
            lines = [f"{len(games)} sugestões · estratégia {strategy}", f"Cobertura da sena deste conjunto: {probability*100:.8f}% (1 em {1/probability:,.2f}).", "Nenhuma combinação individual é mais provável. Jogos salvos foram excluídos.", ""]
            lines += [f"{i:03d}   {dezenas_texto(game)}" for i, game in enumerate(games, 1)]
            self.write(self.game_output, "\n".join(lines))
            self.status.set("Sugestões prontas. Use Salvar sugestões para registrar o conjunto.")

        self.start_job(lambda: gerar_jogos_sugeridos(n_sugestoes=count, estrategia=strategy, excluir=excluded), done, "Gerando jogos distintos…")

    def save_suggestions(self):
        if not self.suggestions:
            raise ValueError("Gere sugestões antes de salvar.")
        existing = {tuple(g['dezenas']) for g in storage.listar_jogos()}
        saved = 0
        for game in self.suggestions:
            if tuple(game) not in existing:
                storage.salvar_jogo(game)
                existing.add(tuple(game))
                saved += 1
        self.refresh_games()
        self.status.set(f"{saved} novos jogos salvos; jogos já existentes foram ignorados.")

    def backtest(self):
        draws = storage.listar_concursos()
        if len(draws) <= 30:
            raise ValueError("São necessários ao menos 31 concursos locais para esta avaliação.")

        def done(result):
            lines = [f"Concursos avaliados: {result['avaliados']} · jogos por concurso: {result['n_jogos']} · semente: {result['seed']}", "Resultados por bilhete (mesmo número de jogos nas duas estratégias):", ""]
            for key, label in (("sugeridos", "Diversificada"), ("aleatorios", "Aleatória")):
                row = result[key]
                lines.append(f"{label}: média {row['media_acertos']:.3f} acertos; melhor {row['melhor_acerto']}; quadras {row['quadras']}, quinas {row['quinas']}, senas {row['senas']}.")
            lines += ["", str(result['aviso']), "Lacunas no histórico reduzem o conjunto disponível para avaliação."]
            self.write(self.backtest_output, "\n".join(lines))
            self.status.set("Avaliação concluída com comparação aleatória do mesmo tamanho.")

        self.start_job(lambda: backtest_cronologico(draws), done, "Avaliando estratégias em ordem cronológica…")

    def export_json(self, filename, data):
        path = filedialog.asksaveasfilename(parent=self.root, initialfile=filename, defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.status.set(f"Exportado para {path}")

    def export_games(self):
        self.safe(lambda: self.export_json("meus-jogos.json", storage.listar_jogos()))

    def export_history(self):
        self.safe(lambda: self.export_json("historico-megasena.json", storage.listar_concursos()))

    def import_history(self):
        if self.busy:
            self.status.set("Aguarde a operação em andamento antes de importar.")
            return
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("Histórico JSON", "*.json")])
        if path:
            def done(total):
                self.refresh()
                self.status.set(f"{total} concursos importados. Registros existentes foram preservados.")
            self.safe(lambda: self.start_job(lambda: storage.importar_historico(path), done, "Validando histórico JSON…"))

    def close(self):
        self.closed = True
        self.cancel.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        MegaSenaApp(root)
    except Exception as exc:
        root.withdraw()
        messagebox.showerror("Erro ao iniciar Megasenna", str(exc), parent=root)
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
