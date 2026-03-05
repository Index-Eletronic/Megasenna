from __future__ import annotations
from megasena.api import fetch_latest_megasena, dezenas_do_resultado
from megasena.compare import comparar_jogo, normalize_jogo
from megasena.storage import init_db, salvar_jogo, listar_jogos
from megasena.stats import gerar_jogos_sugeridos, prob_acertar_sena

def parse_jogo(txt: str) -> list[int]:
    # aceita "01 02 03 04 05 06" ou "1,2,3,4,5,6"
    parts = txt.replace(",", " ").split()
    nums = [int(p) for p in parts]
    return normalize_jogo(nums)

def main():
    init_db()

    print("🎟️  MegaSena Checker")
    print("1) Adicionar jogo")
    print("2) Comparar meus jogos com o último resultado")
    print("3) Sugerir novos jogos (heurístico + Monte Carlo)")
    print("4) Listar jogos salvos")
    op = input("Escolha: ").strip()

    if op == "1":
        txt = input("Digite 6 dezenas (ex: 5 12 23 34 45 60): ")
        jogo = parse_jogo(txt)
        jid = salvar_jogo(jogo)
        print(f"✅ Jogo salvo (id={jid}): {jogo}")

    elif op == "2":
        payload = fetch_latest_megasena()
        resultado = dezenas_do_resultado(payload)
        concurso = payload.get("numero")
        data = payload.get("dataApuracao")
        print(f"📣 Último concurso: {concurso} | Data: {data} | Dezenas: {resultado}")

        jogos = listar_jogos()
        if not jogos:
            print("Você ainda não tem jogos salvos. Use a opção 1.")
            return

        for j in reversed(jogos):  # do mais antigo para o mais novo
            r = comparar_jogo(j["dezenas"], resultado)
            print(f"\nJogo id={j['id']} ({j['criado_em']}): {j['dezenas']}")
            print(f"🎯 Acertos: {r['acertos_qtd']} -> {r['acertos']}")

    elif op == "3":
        print(f"📌 Probabilidade de acertar a sena (6/60): ~ {prob_acertar_sena():.10f} (≈ 1 em 50 milhões)")
        n = int(input("Quantas sugestões? (ex: 10) ").strip() or "10")
        sugestoes = gerar_jogos_sugeridos(n_sugestoes=n, amostras=20000)
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

if __name__ == "__main__":
    main()