from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/app.db")


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS jogos (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          criado_em TEXT NOT NULL,
          dezenas TEXT NOT NULL
        );
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS concursos (
          numero INTEGER PRIMARY KEY,
          data_apuracao TEXT,
          dezenas TEXT NOT NULL
        );
        """)


def salvar_jogo(dezenas: list[int]) -> int:
    dezenas_txt = ",".join(f"{n:02d}" for n in sorted(dezenas))
    with connect() as con:
        cur = con.execute(
            "INSERT INTO jogos (criado_em, dezenas) VALUES (?, ?)",
            (datetime.now().isoformat(timespec="seconds"), dezenas_txt),
        )
        return int(cur.lastrowid)


def listar_jogos() -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT id, criado_em, dezenas FROM jogos ORDER BY id DESC").fetchall()
    out = []
    for _id, criado_em, dezenas in rows:
        nums = [int(x) for x in dezenas.split(",")]
        out.append({"id": _id, "criado_em": criado_em, "dezenas": nums})
    return out


def excluir_jogo(jogo_id: int) -> bool:
    with connect() as con:
        cur = con.execute("DELETE FROM jogos WHERE id = ?", (int(jogo_id),))
        return cur.rowcount > 0


def excluir_todos_jogos() -> int:
    with connect() as con:
        cur = con.execute("DELETE FROM jogos")
        return cur.rowcount


# ----------------------------
# CACHE DO ÚLTIMO CONCURSO
# ----------------------------

def salvar_concurso(numero: int | None, data_apuracao: str | None, dezenas: list[int]) -> None:
    """
    Salva (ou atualiza) um concurso no cache.
    Se numero for None, não salva.
    """
    if numero is None:
        return
    dezenas_txt = ",".join(f"{n:02d}" for n in sorted(dezenas))
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO concursos (numero, data_apuracao, dezenas) VALUES (?, ?, ?)",
            (int(numero), data_apuracao, dezenas_txt),
        )


def ler_ultimo_concurso_salvo() -> dict | None:
    """
    Retorna o concurso com maior 'numero' salvo no banco, ou None.
    """
    with connect() as con:
        row = con.execute(
            "SELECT numero, data_apuracao, dezenas FROM concursos ORDER BY numero DESC LIMIT 1"
        ).fetchone()

    if not row:
        return None

    numero, data_apuracao, dezenas_txt = row
    dezenas = [int(x) for x in dezenas_txt.split(",")]
    return {"numero": numero, "data_apuracao": data_apuracao, "dezenas": dezenas}