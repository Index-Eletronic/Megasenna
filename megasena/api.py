from __future__ import annotations

import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CAIXA_BASE = "https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena"


class MegaSenaAPIError(RuntimeError):
    pass


def _get_json(url: str, timeout: int) -> object:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "Megasenna/1.0"})
    with urlopen(req, timeout=timeout) as resposta:
        return json.loads(resposta.read().decode("utf-8-sig"))


def _normalize_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise MegaSenaAPIError("A CAIXA não retornou um objeto de resultado válido.")
    for key in ("megasena", "mega-sena", "mega_sena"):
        if key in payload and isinstance(payload[key], dict):
            return payload[key]
    return payload


def _inteiro(valor: object, campo: str) -> int:
    if isinstance(valor, bool):
        raise MegaSenaAPIError(f"{campo} inválido.")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().isascii() and valor.strip().isdigit():
        return int(valor.strip())
    raise MegaSenaAPIError(f"{campo} deve ser um número inteiro.")


def dezenas_do_resultado(payload: dict) -> list[int]:
    payload = _normalize_payload(payload)
    for chave in ("listaDezenas", "dezenas", "dezenasSorteadasOrdemSorteio", "numeros", "sorteio"):
        if chave not in payload or payload[chave] is None:
            continue
        valores = payload[chave]
        if not isinstance(valores, list) or len(valores) != 6:
            raise MegaSenaAPIError("O resultado deve conter exatamente seis dezenas.")
        dezenas = [_inteiro(n, "Dezena") for n in valores]
        if any(not 1 <= n <= 60 for n in dezenas) or len(set(dezenas)) != 6:
            raise MegaSenaAPIError("O resultado contém dezenas repetidas ou fora de 1 a 60.")
        return sorted(dezenas)
    raise MegaSenaAPIError("O resultado não contém as dezenas sorteadas.")


def concurso_numero(payload: dict) -> int:
    payload = _normalize_payload(payload)
    for chave in ("numero", "concurso", "numeroDoConcurso", "numero_concurso"):
        if chave in payload and payload[chave] is not None:
            numero = _inteiro(payload[chave], "Concurso")
            if numero < 1:
                raise MegaSenaAPIError("O número do concurso deve ser positivo.")
            return numero
    raise MegaSenaAPIError("O resultado não contém o número do concurso.")


def concurso_data(payload: dict) -> str:
    payload = _normalize_payload(payload)
    for chave in ("dataApuracao", "data", "data_apuracao", "data_concurso"):
        if chave in payload and payload[chave] is not None:
            valor = payload[chave]
            if isinstance(valor, str):
                for formato in ("%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(valor, formato).strftime("%d/%m/%Y")
                    except ValueError:
                        continue
            raise MegaSenaAPIError("O resultado contém uma data de apuração inválida.")
    raise MegaSenaAPIError("O resultado não contém a data de apuração.")


def _buscar(url: str, timeout: int, esperado: int | None = None) -> tuple[dict, str]:
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError("O tempo limite precisa ser positivo.")
    try:
        payload = _normalize_payload(_get_json(url, timeout))
        tipo = payload.get("tipoJogo")
        if tipo is not None and tipo != "MEGA_SENA":
            raise MegaSenaAPIError("A resposta não corresponde à Mega-Sena.")
        numero = concurso_numero(payload)
        concurso_data(payload)
        dezenas_do_resultado(payload)
        if esperado is not None and numero != esperado:
            raise MegaSenaAPIError(f"Foi solicitado o concurso {esperado}, mas a CAIXA retornou {numero}.")
        return payload, url
    except HTTPError as exc:
        raise MegaSenaAPIError(f"A CAIXA respondeu HTTP {exc.code}. Tente sincronizar novamente mais tarde.") from exc
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MegaSenaAPIError(f"Não foi possível consultar a CAIXA: {exc}") from exc


def fetch_latest_megasena(timeout: int = 15) -> tuple[dict, str]:
    return _buscar(CAIXA_BASE, timeout)


def fetch_megasena_concurso(numero: int, timeout: int = 15) -> tuple[dict, str]:
    if isinstance(numero, bool) or not isinstance(numero, int) or numero < 1:
        raise ValueError("O concurso deve ser um inteiro positivo.")
    return _buscar(f"{CAIXA_BASE}/{numero}", timeout, esperado=numero)
