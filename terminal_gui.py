# terminal_gui.py
import tkinter as tk
from tkinter import scrolledtext, messagebox
import json

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
    Aceita:
      add 1 2 3 4 5 6
      add 1,2,3,4,5,6
    """
    if not tokens:
        raise ValueError("Informe 6 dezenas. Ex: add 5 12 23 34 45 60")

    if len(tokens) == 1 and "," in tokens[0]:
        tokens = tokens[0].split(",")

    nums = [int(t) for t in tokens]
    return normalize_jogo(nums)


class TerminalApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MegaSena Terminal")
        self.root.geometry("980x560")

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
        self.cmd.bind("<Return>", lambda e: self.on_run())
        self.cmd.bind("<Up>", self.on_up)
        self.cmd.bind("<Down>", self.on_down)

        self.println("🎟️ MegaSena Terminal iniciado.")
        self.println("✅ Versão: TERMINAL_GUI_DEBUGLATEST_V1")
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

    def print_help(self):
        self.println()
        self.println("Comandos disponíveis:")
        self.println("  help                         -> mostra ajuda")
        self.println("  add N1 N2 N3 N4 N5 N6         -> salva um jogo")
        self.println("  list                         -> lista jogos salvos")
        self.println("  del ID                       -> exclui um jogo pelo id")
        self.println("  delall                       -> exclui TODOS os jogos do banco (com confirmação)")
        self.println("  latest                       -> mostra último resultado (e salva em cache)")
        self.println("  compare                      -> compara TODOS jogos com o último resultado (usa cache se offline)")
        self.println("  suggest [N]                  -> sugere N jogos (padrão 10)")
        self.println("  prob                         -> mostra prob. de acertar sena (6/60)")
        self.println("  clear / cls                  -> limpa a tela e mostra os comandos")
        self.println("  debuglatest                  -> 🔎 arma secreta: mostra payload bruto e chaves da API")
        self.println("Exemplos:")
        self.println("  add 5 12 23 34 45 60")
        self.println("  add 5,12,23,34,45,60")
        self.println("  del 7")
        self.println("  delall")
        self.println("  suggest 15")
        self.println("  debuglatest")
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
        """
        Retorna (numero, data, dezenas, fonte, from_cache_bool)
        """
        try:
            payload, fonte = fetch_latest_megasena()
            dezenas = dezenas_do_resultado(payload)
            numero = concurso_numero(payload)
            data = concurso_data(payload)
            # salva cache se tiver numero
            salvar_concurso(numero, data, dezenas)
            return numero, data, dezenas, fonte, False
        except Exception as e:
            cached = ler_ultimo_concurso_salvo()
            if cached:
                return cached["numero"], cached["data_apuracao"], cached["dezenas"], f"cache (erro API: {e})", True
            raise

    def dispatch(self, line: str):
        parts = line.split()
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
            for j in reversed(jogos):  # do mais antigo para o mais novo
                self.println(f"id={j['id']} | {j['criado_em']} | {j['dezenas']}")
            return

        if cmd in ("del", "delete", "rm", "remove"):
            if not args:
                raise ValueError("Use: del ID  (ex: del 7)")
            jid = int(args[0])
            ok = excluir_jogo(jid)
            if ok:
                self.println(f"🗑️ Jogo id={jid} excluído.")
            else:
                self.println(f"⚠️ Não encontrei jogo com id={jid}.")
            return

        if cmd in ("delall", "deleteall", "rmall", "clearall"):
            if not messagebox.askyesno("Confirmar", "Apagar TODOS os jogos do banco?"):
                self.println("Cancelado.")
                return
            qtd = excluir_todos_jogos()
            self.println(f"🧹 Removi {qtd} jogo(s).")
            return

        if cmd == "latest":
            numero, data, dezenas, fonte, from_cache = self._fetch_latest_or_cache()
            tag = "📦 cache" if from_cache else "🌐 online"
            self.println(f"📣 Último concurso: {numero} | Data: {data} | Dezenas: {dezenas}  ({tag}, fonte: {fonte})")
            return

        if cmd == "compare":
            jogos = listar_jogos()
            if not jogos:
                self.println("Você ainda não tem jogos salvos. Use: add ...")
                return

            numero, data, resultado, fonte, from_cache = self._fetch_latest_or_cache()
            tag = "📦 cache" if from_cache else "🌐 online"
            self.println(f"📣 Concurso {numero} ({data}) | {resultado}  ({tag}, fonte: {fonte})")

            for j in reversed(jogos):
                r = comparar_jogo(j["dezenas"], resultado)
                self.println(f"\nJogo id={j['id']} ({j['criado_em']}): {j['dezenas']}")
                self.println(f"🎯 Acertos: {r['acertos_qtd']} -> {r['acertos']}")
            self.println()
            return

        if cmd == "suggest":
            n = 10
            if args:
                n = int(args[0])
                if n < 1 or n > 200:
                    raise ValueError("N precisa estar entre 1 e 200.")

            self.println(f"📌 Prob. de acertar a sena (6/60): ~ {prob_acertar_sena():.10f} (≈ 1 em 50 milhões)")
            sugestoes = gerar_jogos_sugeridos(n_sugestoes=n, amostras=20000)
            self.println("🧠 Sugestões:")
            for i, s in enumerate(sugestoes, 1):
                self.println(f"{i:02d}) {s}")
            return

        if cmd == "prob":
            self.println(f"📌 Prob. de acertar a sena (6/60): ~ {prob_acertar_sena():.10f} (≈ 1 em 50 milhões)")
            return

        # 🔎 ARMA SECRETA
        if cmd == "debuglatest":
            self.println("🔎 Debug do último resultado (arma secreta ativada)")

            try:
                payload, fonte = fetch_latest_megasena()
                self.println(f"Fonte: {fonte}")

                # chaves
                if isinstance(payload, dict):
                    self.println(f"Chaves do payload: {list(payload.keys())}")
                else:
                    self.println(f"Tipo do payload: {type(payload)}")

                # preview do JSON
                try:
                    preview = json.dumps(payload, ensure_ascii=False, indent=2)
                except Exception:
                    preview = str(payload)

                if len(preview) > 900:
                    preview = preview[:900] + "\n... (cortado)"
                self.println("Payload (preview):")
                self.println(preview)

                # tenta extrair dezenas
                try:
                    dezenas = dezenas_do_resultado(payload)
                    numero = concurso_numero(payload)
                    data = concurso_data(payload)
                    self.println(f"✅ Extração OK -> Concurso: {numero} | Data: {data} | Dezenas: {dezenas}")
                except Exception as e:
                    self.println(f"❌ Falha ao extrair dezenas: {e}")

            except Exception as e:
                self.println(f"❌ Falha ao buscar online: {e}")
                cached = ler_ultimo_concurso_salvo()
                if cached:
                    self.println("📦 Cache encontrado no banco:")
                    self.println(
                        f"Concurso: {cached['numero']} | Data: {cached['data_apuracao']} | Dezenas: {cached['dezenas']}"
                    )
                else:
                    self.println("📦 Sem cache salvo.")
            return

        raise ValueError("Comando desconhecido. Digite 'help' para ver os comandos.")


if __name__ == "__main__":
    root = tk.Tk()
    app = TerminalApp(root)
    root.mainloop()