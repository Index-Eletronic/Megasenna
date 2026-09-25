from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path


def caminho_banco() -> Path:
    """O executável mantém os dados fora da pasta temporária do PyInstaller."""
    if getattr(sys, "frozen", False):
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return local / "Megasenna" / "app.db"
    return Path(__file__).resolve().parent.parent / "data" / "app.db"


DB_PATH = caminho_banco()


class _Connection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH, timeout=15, factory=_Connection)


def _bancos_legados() -> list[Path]:
    pasta_exe = Path(sys.executable).resolve().parent
    candidatos = [pasta_exe / "data" / "app.db", Path.cwd() / "data" / "app.db"]
    if pasta_exe.name.lower() == "dist":
        candidatos.append(pasta_exe.parent / "data" / "app.db")
    if pasta_exe.parent.name.lower() == "dist":
        candidatos.extend([pasta_exe.parent / "data" / "app.db",
                           pasta_exe.parent.parent / "data" / "app.db"])
    destino = Path(DB_PATH).resolve()
    return list(dict.fromkeys(p.resolve() for p in candidatos if p.is_file() and p.resolve() != destino))


def _migrar_banco_legado() -> None:
    """Une bancos legados numa cópia; nunca altera origens nem substitui o destino."""
    destino = Path(DB_PATH)
    if not getattr(sys, "frozen", False) or destino.exists():
        return
    candidatos = _bancos_legados()
    if not candidatos:
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(f".migracao-{uuid.uuid4().hex}.db")
    try:
        with sqlite3.connect(candidatos[0].as_uri() + "?mode=ro", uri=True, factory=_Connection) as origem:
            with sqlite3.connect(temporario, factory=_Connection) as copia:
                origem.backup(copia)
                if copia.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("O banco legado não passou na verificação de integridade.")
        _unir_bancos_legados(temporario, candidatos[1:])
        try:
            # O link falha se outro processo já criou o destino; nunca sobrescreve.
            os.link(temporario, destino)
        except FileExistsError:
            pass
    finally:
        temporario.unlink(missing_ok=True)


def _unir_bancos_legados(destino: Path, outras_origens: list[Path]) -> None:
    with sqlite3.connect(destino, factory=_Connection) as con:
        existentes = set(con.execute("SELECT id, criado_em, dezenas FROM jogos").fetchall())
        origens = []
        for caminho in outras_origens:
            with sqlite3.connect(caminho.as_uri() + "?mode=ro", uri=True, factory=_Connection) as origem:
                origens.append((origem.execute("SELECT id, criado_em, dezenas FROM jogos").fetchall(),
                                origem.execute("SELECT numero, data_apuracao, dezenas FROM concursos").fetchall()))
        ids = {row[0] for row in existentes}
        proximo = max(ids | {row[0] for jogos, _ in origens for row in jogos}, default=0) + 1
        for jogos, concursos in origens:
            for row in jogos:
                if row in existentes:
                    continue
                jogo_id, criado, dezenas = row
                if jogo_id in ids:
                    jogo_id = proximo
                    proximo += 1
                con.execute("INSERT INTO jogos (id, criado_em, dezenas) VALUES (?, ?, ?)", (jogo_id, criado, dezenas))
                ids.add(jogo_id)
                existentes.add(row)
            for row in concursos:
                numero, data, dezenas = row
                existente = con.execute("SELECT numero, data_apuracao, dezenas FROM concursos WHERE numero = ?", (numero,)).fetchone()
                if existente and _concurso_dict(existente) != _concurso_dict(row):
                    raise RuntimeError(f"Bancos legados têm resultados diferentes para o concurso {numero}. As origens foram preservadas.")
                if not existente:
                    _concurso_dict(row)
                    con.execute("INSERT INTO concursos (numero, data_apuracao, dezenas) VALUES (?, ?, ?)", row)


def init_db() -> None:
    _migrar_banco_legado()
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS jogos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, criado_em TEXT NOT NULL, dezenas TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS concursos (
            numero INTEGER PRIMARY KEY, data_apuracao TEXT, dezenas TEXT NOT NULL)""")
    # O pacote inclui somente resultados públicos. Nunca embutir o banco de jogos.
    base_recursos = getattr(sys, "_MEIPASS", None)
    seed = Path(base_recursos) / "assets" / "concursos.json" if base_recursos else None
    if seed is not None and seed.is_file():
        with connect() as con:
            total = con.execute("SELECT COUNT(*) FROM concursos").fetchone()[0]
        if total < 3061:
            try:
                importar_historico(seed)
            except ValueError:
                # Deixe a interface abrir para que a sincronização repare linhas
                # corrompidas. Conflitos entre dois resultados válidos continuam
                # explícitos para evitar substituir o banco em silêncio.
                if not resumo_historico()["invalidos"]:
                    raise


def _numero_positivo(numero: int) -> int:
    if isinstance(numero, bool) or not isinstance(numero, int) or numero < 1:
        raise ValueError("O número deve ser um inteiro positivo.")
    return numero


def _dezenas_validas(dezenas: list[int]) -> list[int]:
    if not isinstance(dezenas, (list, tuple)) or len(dezenas) != 6:
        raise ValueError("Informe exatamente seis dezenas.")
    if any(isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 60 for n in dezenas):
        raise ValueError("As dezenas devem ser inteiros de 1 a 60.")
    if len(set(dezenas)) != 6:
        raise ValueError("As seis dezenas devem ser distintas.")
    return sorted(dezenas)


def _data_valida(data: str | None) -> str | None:
    if data is None:
        return None
    if not isinstance(data, str):
        raise ValueError("A data do concurso deve ser um texto.")
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(data, formato).strftime("%d/%m/%Y")
        except ValueError:
            continue
    raise ValueError("Data do concurso inválida; use DD/MM/AAAA ou AAAA-MM-DD.")


def _dezenas_texto(dezenas: list[int]) -> str:
    return ",".join(f"{n:02d}" for n in _dezenas_validas(dezenas))


def salvar_jogo(dezenas: list[int]) -> int:
    texto = _dezenas_texto(dezenas)
    with connect() as con:
        cur = con.execute("INSERT INTO jogos (criado_em, dezenas) VALUES (?, ?)",
                          (datetime.now().isoformat(timespec="seconds"), texto))
        return int(cur.lastrowid)


def listar_jogos() -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT id, criado_em, dezenas FROM jogos ORDER BY id DESC").fetchall()
    return [{"id": i, "criado_em": data, "dezenas": _dezenas_validas([int(n) for n in texto.split(",")])}
            for i, data, texto in rows]


def excluir_jogo(jogo_id: int) -> bool:
    with connect() as con:
        return con.execute("DELETE FROM jogos WHERE id = ?", (_numero_positivo(jogo_id),)).rowcount > 0


def excluir_todos_jogos() -> int:
    with connect() as con:
        return con.execute("DELETE FROM jogos").rowcount


def salvar_concurso(numero: int, data_apuracao: str | None, dezenas: list[int]) -> None:
    valores = (_numero_positivo(numero), _data_valida(data_apuracao), _dezenas_texto(dezenas))
    with connect() as con:
        con.execute("""INSERT INTO concursos (numero, data_apuracao, dezenas) VALUES (?, ?, ?)
            ON CONFLICT(numero) DO UPDATE SET
            data_apuracao = excluded.data_apuracao, dezenas = excluded.dezenas""", valores)


def _concurso_dict(row) -> dict:
    numero, data, texto = row
    return {"numero": _numero_positivo(numero), "data_apuracao": _data_valida(data),
            "dezenas": _dezenas_validas([int(n) for n in texto.split(",")])}


def listar_concursos(inicio: int | None = None, fim: int | None = None) -> list[dict]:
    filtros, parametros = [], []
    for valor, operador in ((inicio, ">="), (fim, "<=")):
        if valor is not None:
            filtros.append(f"numero {operador} ?")
            parametros.append(_numero_positivo(valor))
    if inicio is not None and fim is not None and inicio > fim:
        raise ValueError("O concurso inicial não pode ser maior que o final.")
    where = " WHERE " + " AND ".join(filtros) if filtros else ""
    with connect() as con:
        rows = con.execute("SELECT numero, data_apuracao, dezenas FROM concursos" + where + " ORDER BY numero", parametros).fetchall()
    return [_concurso_dict(row) for row in rows]


def obter_concurso(numero: int) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT numero, data_apuracao, dezenas FROM concursos WHERE numero = ?", (_numero_positivo(numero),)).fetchone()
    return _concurso_dict(row) if row else None


def ler_ultimo_concurso_salvo() -> dict | None:
    with connect() as con:
        row = con.execute("SELECT numero, data_apuracao, dezenas FROM concursos ORDER BY numero DESC LIMIT 1").fetchone()
    return _concurso_dict(row) if row else None


def resumo_historico() -> dict:
    """Lacunas começam no concurso 1. Somente uma sync confirma o último oficial."""
    with connect() as con:
        rows = con.execute("SELECT numero, data_apuracao, dezenas FROM concursos ORDER BY numero").fetchall()
    validos, invalidos = [], []
    for row in rows:
        try:
            validos.append(_concurso_dict(row)["numero"])
        except (ValueError, TypeError, AttributeError):
            invalidos.append(row[0])
    presentes = set(validos)
    maior_registro = max((row[0] for row in rows if row[0] > 0), default=0)
    return {"total": len(validos), "primeiro": min(validos, default=None),
            "ultimo": max(validos, default=None),
            "lacunas": [n for n in range(1, maior_registro + 1) if n not in presentes],
            "invalidos": invalidos}


def exportar_historico(caminho: str | Path) -> int:
    concursos = listar_concursos()
    Path(caminho).write_text(json.dumps({"formato": "megasenna-historico-v1", "concursos": concursos}, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(concursos)


def importar_historico(caminho: str | Path) -> int:
    """Valida tudo antes de gravar. Conflitos não alteram dados já existentes."""
    payload = json.loads(Path(caminho).read_text(encoding="utf-8-sig"))
    registros = payload.get("concursos") if isinstance(payload, dict) else payload
    if not isinstance(registros, list):
        raise ValueError("O arquivo precisa conter uma lista de concursos.")
    valores, vistos = [], set()
    for registro in registros:
        if not isinstance(registro, dict):
            raise ValueError("Registro de concurso inválido.")
        numero = _numero_positivo(registro.get("numero"))
        data = _data_valida(registro.get("data_apuracao"))
        if data is None:
            raise ValueError(f"O concurso {numero} não tem data de apuração.")
        texto = _dezenas_texto(registro.get("dezenas"))
        if numero in vistos:
            raise ValueError(f"Concurso {numero} repetido no arquivo.")
        vistos.add(numero)
        valores.append((numero, data, texto))
    with connect() as con:
        inseridos = 0
        for numero, data, texto in valores:
            existente = con.execute("SELECT numero, data_apuracao, dezenas FROM concursos WHERE numero = ?", (numero,)).fetchone()
            esperado = {"numero": numero, "data_apuracao": data, "dezenas": [int(n) for n in texto.split(",")]}
            if existente:
                if _concurso_dict(existente) != esperado:
                    raise ValueError(f"O concurso {numero} conflita com o banco local. Nenhum registro foi importado.")
                continue
            con.execute("INSERT INTO concursos (numero, data_apuracao, dezenas) VALUES (?, ?, ?)", (numero, data, texto))
            inseridos += 1
    return inseridos
