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
    atualizar_concurso as salvar_concurso,
    ler_ultimo_concurso_salvo,
)
from megasena.stats import gerar_jogos_sugeridos, prob_acertar_sena
from megasena import storage
from megasena.sync import sincronizar_historico
from megasena.portfolio import (
    analisar_carteira, otimizar_carteira, preco_centavos, linhas_cobertura,
    conferir_concurso, linhas_conferencia, importar_carteira,
)


def parse_nums(tokens):
    """
    Cadeado Mega-Sena:
      - aceita 6 dezenas
      - cada uma deve estar entre 1 e 60
      - não permite repetição
      - aceita: adicionar 1 2 3 4 5 6  |  adicionar 1,2,3,4,5,6
    """
    if not tokens:
        raise ValueError("Informe 6 dezenas. Ex: adicionar 5 12 23 34 45 60")

    tokens = " ".join(tokens).replace(",", " ").split()

    # converte e valida quantidade
    try:
        nums = [int(t) for t in tokens]
    except ValueError:
        raise ValueError("Use apenas números. Ex: adicionar 5 12 23 34 45 60")

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
        raise ValueError("ID inválido. Use: excluir 9 (ou excluir ID9)")
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
        self.suggestion_price_centavos = 600
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
        if storage.listar_apostas_concurso(numero):
            self._show_lines(linhas_conferencia(conferir_concurso(numero)))

    def _show_comparisons(self, result):
        concurso, comparacoes = result
        self._show_latest(concurso)
        for jogo, comparacao in sorted(comparacoes, key=lambda item: (-item[1]["acertos_qtd"], item[0]["id"])):
            self.println(f"\nJogo id={jogo['id']} | {jogo['dezenas']}")
            self.println(f"🎯 Acertos: {comparacao['acertos_qtd']} |-> {comparacao['acertos']}")
        self.println()

    def _show_suggestions(self, suggestions):
        self.last_suggestions = suggestions
        self.suggestion_price_centavos = 600
        self.println("🧠 Jogos distintos e diversificados (use 'salvar_sugestoes' para salvar):")
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
                lines.append(f"Campos da resposta: {list(payload.keys())}")
            preview = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            if len(preview) > 900:
                preview = preview[:900] + "\n... (cortado)"
            lines.extend(["Prévia da resposta:", preview])
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
        comandos = [
            ("ajuda", "mostra ajuda"),
            ("adicionar N1 N2 N3 N4 N5 N6", "salva um jogo com seis dezenas de 1 a 60"),
            ("listar", "lista jogos salvos"),
            ("excluir ID", "exclui um jogo (aceita: 9, ID9, id=9, #9)"),
            ("excluir_todos", "exclui todos os jogos, com confirmação"),
            ("ultimo", "mostra o último resultado e salva uma cópia local"),
            ("comparar", "confere todos os jogos, do maior acerto ao menor"),
            ("sugerir [N]", "gera de 1 a 200 jogos distintos (padrão: 10)"),
            ("salvar_sugestoes", "salva todas as sugestões geradas"),
            ("salvar_sugestoes 1 3 5", "salva apenas as sugestões indicadas"),
            ("salvar_sugestoes perguntar", "pergunta quantas sugestões salvar"),
            ("probabilidade", "mostra a probabilidade de acertar a sena"),
            ("limpar", "limpa a tela e mostra os comandos"),
            ("diagnostico", "mostra a resposta original e os campos da API"),
            ("vincular CONCURSO [IDs|sugestoes]", "vincula carteira ao concurso (padrão: todos os salvos)"),
            ("conferir CONCURSO", "confere a carteira vinculada, com mais acertos primeiro"),
            ("atualizar", "faz backup, atualiza histórico e confere carteiras vinculadas"),
            ("cobertura [sugestoes] [PRECO]", "cobertura exata e custo (padrão: salvos, R$ 6,00)"),
            ("otimizar quadra|quina [sugestoes] [PRECO]", "mesmo tamanho; alternativa nas sugestões"),
            ("backup", "salva uma cópia íntegra do banco local"),
            ("importar_carteira CAMINHO", "carrega jogos JSON nas sugestões para revisão"),
        ]
        for comando, descricao in comandos:
            self.println(f"  {comando:<29} -> {descricao}")
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
            self.println("⚠️ Nenhuma sugestão na memória. Rode: sugerir 10")
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
        aliases = {
            "ajuda": "help", "adicionar": "add", "listar": "list",
            "excluir": "del", "excluir_todos": "delall", "ultimo": "latest",
            "último": "latest", "comparar": "compare", "sugerir": "suggest",
            "salvar_sugestoes": "save_suggested", "salvar_sugestões": "save_suggested",
            "probabilidade": "prob", "limpar": "clear", "diagnostico": "debuglatest",
            "diagnóstico": "debuglatest",
        }
        cmd = aliases.get(cmd, cmd)

        if cmd == 'importar_carteira':
            if self._busy:
                raise ValueError('Aguarde a operação em andamento.')
            caminho = line.partition(' ')[2].strip().strip('"')
            if not caminho:
                raise ValueError('Use: importar_carteira CAMINHO DO JSON')
            self._show_suggestions(importar_carteira(caminho))
            return

        if cmd in ('vincular', 'conferir', 'atualizar', 'cobertura', 'otimizar', 'backup'):
            if self._busy:
                raise ValueError('Aguarde a operação em andamento.')
            if cmd == 'backup':
                if args:
                    raise ValueError('Use: backup')
                self.println(f'Backup salvo em {storage.criar_backup()}')
            elif cmd == 'vincular':
                if not args:
                    raise ValueError('Use: vincular CONCURSO [IDs dos jogos]')
                numero = int(args[0])
                if len(args) == 2 and args[1].lower() == 'sugestoes':
                    total = storage.vincular_carteira_concurso(numero, self.last_suggestions, getattr(self, 'suggestion_price_centavos', 600))
                else:
                    ids = [parse_id(i) for i in args[1:]] if len(args) > 1 else None
                    total = storage.vincular_jogos_concurso(numero, ids)
                self.println(f'{total} jogos vinculados ao concurso {numero}. O vínculo não confirma pagamento.')
                self._show_lines(linhas_conferencia(conferir_concurso(numero)))
            elif cmd == 'conferir':
                if len(args) != 1:
                    raise ValueError('Use: conferir CONCURSO')
                self._show_lines(linhas_conferencia(conferir_concurso(int(args[0]))))
            elif cmd == 'atualizar':
                if args:
                    raise ValueError('Use: atualizar')
                def work():
                    result = sincronizar_historico()
                    lines = [f"Atualização: {result['status']} · {result['baixados']} resultados · backup: {result['backup']}"]
                    for n in storage.concursos_vinculados():
                        lines += linhas_conferencia(conferir_concurso(n))
                    return lines
                self._run_background(work, self._show_lines, 'Atualizando histórico com backup automático…')
            elif cmd == 'cobertura':
                sugestoes = bool(args and args[0].lower() == 'sugestoes')
                valores = args[1:] if sugestoes else args
                if len(valores) > 1:
                    raise ValueError('Use: cobertura [sugestoes] [PRECO POR JOGO]')
                valor = preco_centavos(valores[0]) if valores else 600
                jogos = [j[:] for j in self.last_suggestions] if sugestoes else [j['dezenas'] for j in listar_jogos()]
                self._run_background(lambda: linhas_cobertura(analisar_carteira(jogos, valor)), self._show_lines,
                                     'Calculando a união exata de quadra ou mais e quina ou mais…')
            else:
                if not args or args[0].lower() not in ('quadra', 'quina'):
                    raise ValueError('Use: otimizar quadra|quina [sugestoes] [PRECO POR JOGO]')
                objetivo = args[0].lower()
                sugestoes = len(args) > 1 and args[1].lower() == 'sugestoes'
                valores = args[2:] if sugestoes else args[1:]
                if len(valores) > 1:
                    raise ValueError('Use: otimizar quadra|quina [sugestoes] [PRECO POR JOGO]')
                valor = preco_centavos(valores[0]) if valores else 600
                jogos = [j[:] for j in self.last_suggestions] if sugestoes else [j['dezenas'] for j in listar_jogos()]
                def done(result):
                    self.last_suggestions = result['jogos']
                    self._show_lines(['ANTES:'] + linhas_cobertura(result['antes']) + ['ALTERNATIVA:'] + linhas_cobertura(result['depois']))
                    self.println(f"Ganho: {result['ganho_resultados']} resultados na faixa escolhida. {result['aviso']}")
                    self._show_suggestions(result['jogos'])
                    self.suggestion_price_centavos = result['depois']['valor_centavos']
                    self.println('Jogos originais e vínculos preservados. Salvar sugestões adiciona jogos ao banco; não substitui a carteira.')
                self._run_background(lambda: otimizar_carteira(jogos, objetivo, valor), done,
                                     'Otimizando carteira com a mesma quantidade e custo…')
            return

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
                raise ValueError("Use: excluir ID  (ex: excluir 7)")
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
                self.println("Você ainda não tem jogos salvos. Use: adicionar ...")
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
                    raise ValueError("Use: sugerir N, com N inteiro de 1 a 200.") from None
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
                self.println("⚠️ Nenhuma sugestão na memória. Rode: sugerir 10")
                return

            if not args:
                indices = list(range(1, len(self.last_suggestions) + 1))
                self._save_suggestions_by_indices(indices)
                return

            if args[0].lower() in ("perguntar", "ask"):
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
                raise ValueError("Informe índices inteiros. Exemplo: salvar_sugestoes 1 3 5") from None
            self._save_suggestions_by_indices(indices)
            return

        if cmd == "prob":
            self.println(f"📌 Prob. de acertar a sena por jogo (6/60): {prob_acertar_sena():.10f} (1 em 50.063.860)")
            self.println("Cada combinação tem a mesma chance em um sorteio justo; repetir um jogo não aumenta a cobertura.")
            return

        if cmd == "debuglatest":
            self._run_background(self._debug_latest, self._show_lines, "🔎 Consultando dados da API…")
            return

        raise ValueError("Comando desconhecido. Digite 'ajuda' para ver os comandos.")


if __name__ == "__main__":
    root = tk.Tk()
    app = TerminalApp(root)
    root.mainloop()
