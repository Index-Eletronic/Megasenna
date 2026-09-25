from __future__ import annotations

from collections.abc import Callable
from threading import Event

from .api import concurso_data, concurso_numero, dezenas_do_resultado, fetch_latest_megasena, fetch_megasena_concurso, MegaSenaAPIError
from .storage import init_db, resumo_historico, salvar_concurso


def sincronizar_historico(
    progresso: Callable[[dict], None] | None = None,
    cancelar: Event | None = None,
    timeout: int = 15,
) -> dict:
    """Baixa apenas concursos faltantes e confirma cada gravação individualmente.

    Para na primeira falha de rede; uma nova chamada retoma os faltantes.
    Cancelamento é observado entre requisições, limitadas pelo timeout informado.
    `completo` refere-se ao último oficial observado no início desta execução.
    O callback roda na mesma thread; GUIs devem encaminhá-lo a uma fila.
    """
    init_db()
    oficial = None
    baixados = 0
    falhas = []
    fonte = None

    def cancelado():
        return cancelar is not None and cancelar.is_set()

    def resultado(status: str):
        resumo = resumo_historico()
        faltantes = list(resumo["lacunas"])
        if oficial is not None:
            faltantes = [n for n in faltantes if n <= oficial]
            faltantes.extend(range((resumo["ultimo"] or 0) + 1, oficial + 1))
            faltantes = sorted(set(faltantes))
        resumo.update({"status": status, "ultimo_oficial": oficial, "baixados": baixados,
                       "falhas": falhas, "fonte": fonte, "lacunas": faltantes,
                       "completo": status == "concluido" and oficial is not None and
                       not faltantes and not resumo["invalidos"] and resumo["ultimo"] == oficial})
        return resumo

    if cancelado():
        return resultado("cancelado")
    if progresso:
        progresso({"processados": 0, "total": None, "numero": None, "status": "consultando"})
    try:
        payload, fonte = fetch_latest_megasena(timeout=timeout)
        oficial = concurso_numero(payload)
        if cancelado():
            return resultado("cancelado")
        resumo = resumo_historico()
        anteriores = set(resumo["lacunas"])
        if oficial > (resumo["ultimo"] or 0) or oficial in anteriores:
            baixados += 1
        salvar_concurso(oficial, concurso_data(payload), dezenas_do_resultado(payload))
    except MegaSenaAPIError as exc:
        falhas.append({"numero": None, "erro": str(exc)})
        return resultado("erro")
    resumo = resumo_historico()
    faltantes = [n for n in resumo["lacunas"] if n <= oficial]
    total = len(faltantes)
    if progresso:
        progresso({"processados": 0, "total": total, "numero": oficial, "status": "baixando"})
    for indice, numero in enumerate(faltantes, 1):
        if cancelado():
            return resultado("cancelado")
        try:
            payload, _ = fetch_megasena_concurso(numero, timeout=timeout)
            if cancelado():
                return resultado("cancelado")
            if concurso_numero(payload) != numero:
                raise MegaSenaAPIError(f"Resultado incorreto para o concurso {numero}.")
            salvar_concurso(numero, concurso_data(payload), dezenas_do_resultado(payload))
            baixados += 1
        except MegaSenaAPIError as exc:
            falhas.append({"numero": numero, "erro": str(exc)})
            return resultado("erro")
        if progresso:
            progresso({"processados": indice, "total": total, "numero": numero, "status": "baixando"})
    if cancelado():
        return resultado("cancelado")
    final = resultado("concluido")
    if not final["completo"]:
        final["status"] = "inconsistente"
        final["falhas"].append({"numero": None, "erro": "O banco contém registros inválidos ou posteriores ao último concurso oficial."})
    return final
