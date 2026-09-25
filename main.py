from __future__ import annotations
import sqlite3

from megasena.api import (
    MegaSenaAPIError,
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
    salvar_concurso,
    ler_ultimo_concurso_salvo,
)
from megasena.stats import gerar_jogos_sugeridos, prob_acertar_sena

def parse_jogo(txt: str) -> list[int]:
    # aceita "01 02 03 04 05 06" ou "1,2,3,4,5,6"
    parts = txt.replace(",", " ").split()
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        raise ValueError("Use apenas números. Exemplo: 5 12 23 34 45 60") from None
    return normalize_jogo(nums)


def _main():
    init_db()

    print("🎟️  MegaSena Checker")
    print("1) Adicionar jogo")
    print("2) Comparar meus jogos com o último resultado")
    print("3) Sugerir jogos distintos e diversificados")
    print("4) Listar jogos salvos")
    op = input("Escolha: ").strip()

    if op == "1":
        txt = input("Digite 6 dezenas (ex: 5 12 23 34 45 60): ")
        jogo = parse_jogo(txt)
        jid = salvar_jogo(jogo)
        print(f"✅ Jogo salvo (id={jid}): {jogo}")

    elif op == "2":
        jogos = listar_jogos()
        if not jogos:
            print("Você ainda não tem jogos salvos. Use a opção 1.")
            return

        try:
            payload, fonte = fetch_latest_megasena()
            resultado = dezenas_do_resultado(payload)
            concurso = concurso_numero(payload)
            data = concurso_data(payload)
            salvar_concurso(concurso, data, resultado)
        except MegaSenaAPIError:
            cached = ler_ultimo_concurso_salvo()
            if not cached:
                raise
            concurso = cached["numero"]
            data = cached["data_apuracao"]
            resultado = cached["dezenas"]
            fonte = "cache local; resultado mais recente disponível, sem atualização online"
        print(f"📣 Concurso: {concurso} | Data: {data} | Dezenas: {resultado} | Fonte: {fonte}")

        for j in reversed(jogos):  # do mais antigo para o mais novo
            r = comparar_jogo(j["dezenas"], resultado)
            print(f"\nJogo id={j['id']} ({j['criado_em']}): {j['dezenas']}")
            print(f"🎯 Acertos: {r['acertos_qtd']} -> {r['acertos']}")

    elif op == "3":
        print(f"📌 Probabilidade de acertar a sena por jogo (6/60): {prob_acertar_sena():.10f} (1 em 50.063.860)")
        print("Cada combinação tem a mesma chance em um sorteio justo. O histórico não prevê o próximo resultado.")
        try:
            n = int(input("Quantas sugestões? (1 a 200, padrão 10) ").strip() or "10")
        except ValueError:
            raise ValueError("Informe uma quantidade inteira de 1 a 200.") from None
        if not 1 <= n <= 200:
            raise ValueError("Informe uma quantidade inteira de 1 a 200.")
        sugestoes = gerar_jogos_sugeridos(
            n_sugestoes=n,
            estrategia="diversificada",
            excluir=[j["dezenas"] for j in listar_jogos()],
        )
        print("\n🧠 Sugestões:")
        for i, s in enumerate(sugestoes, 1):
            print(f"{i:02d}) {s}")

    elif op == "4":
        jogos = listar_jogos()
        if not jogos:
            print("Sem jogos salvos.")
            return
        for j in jogos:
            print(f"id={j['id']} | {j['criado_em']} | {j['dezenas']}")

    else:
        print("Opção inválida.")


def main():
    try:
        _main()
    except (ValueError, MegaSenaAPIError, sqlite3.Error) as exc:
        print(f"❌ Não foi possível concluir: {exc}")
    except (EOFError, KeyboardInterrupt):
        print("\nOperação cancelada.")


if __name__ == "__main__":
    main()
