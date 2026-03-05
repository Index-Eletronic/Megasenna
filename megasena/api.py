from __future__ import annotations
import requests

class MegaSenaAPIError(RuntimeError):
    pass

# Fontes (tentaremos em ordem)
LOTTOLOOKUP_BASE = "https://lottolookup.com.br/api"

# Essas bases alternativas são comuns para a API estilo heroku (às vezes uma cai e outra fica)
FALLBACK_BASES = [
    "https://loteriascaixa-api.herokuapp.com",
    "https://loterias-gutotech.herokuapp.com",
    "https://loterias-caixa-gov.herokuapp.com",
]

# Caminhos possíveis (variam por projeto)
FALLBACK_PATHS = [
    "/api/mega-sena/latest",
    "/api/megasena/latest",
    "/api/mega-sena",
    "/api/megasena",
]

def _get_json(url: str, timeout: int) -> object:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()

def _as_dict(payload: object) -> dict:
    """Algumas APIs retornam lista; pegamos o primeiro item."""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list) and payload:
        if isinstance(payload[0], dict):
            return payload[0]
    raise MegaSenaAPIError(f"Payload inesperado: {type(payload)}")

def _normalize_payload(d: dict) -> dict:
    """
    Normaliza casos comuns:
    - { "megasena": { ... } }
    - { "mega-sena": { ... } }
    """
    for key in ("megasena", "mega-sena", "mega_sena"):
        if key in d and isinstance(d[key], dict):
            return d[key]
    return d

def dezenas_do_resultado(payload: dict) -> list[int]:
    """
    Suporta:
    - listaDezenas: ['08','11',...]
    - dezenas: ['08','11',...]
    - dezenasSorteadasOrdemSorteio (algumas variações)
    - numeros (outras variações)
    """
    payload = _normalize_payload(payload)

    candidates = [
        payload.get("listaDezenas"),
        payload.get("dezenas"),
        payload.get("dezenasSorteadasOrdemSorteio"),
        payload.get("numeros"),
        payload.get("sorteio"),  # raríssimo, mas deixamos
    ]

    for arr in candidates:
        if isinstance(arr, list) and len(arr) >= 6:
            try:
                return sorted(int(str(x).strip()) for x in arr[:6])
            except ValueError:
                # se vier tipo "08" ok, se vier "08;" não ok
                pass

    raise MegaSenaAPIError(
        f"Payload não contém dezenas em chaves conhecidas. Chaves recebidas: {list(payload.keys())}"
    )

def concurso_numero(payload: dict):
    payload = _normalize_payload(payload)
    return payload.get("numero") or payload.get("concurso") or payload.get("numeroDoConcurso") or payload.get("numero_concurso")

def concurso_data(payload: dict):
    payload = _normalize_payload(payload)
    return payload.get("dataApuracao") or payload.get("data") or payload.get("dataPorExtenso") or payload.get("data_concurso")

def fetch_latest_megasena(timeout: int = 15) -> tuple[dict, str]:
    """
    Retorna (payload_dict, fonte).
    Tenta:
      1) LottoLookup: /megasena (geralmente lista) e / (geralmente dict)
      2) Fallbacks (várias bases + vários paths)
    """

    # 1A) LottoLookup /megasena (normalmente lista com os últimos concursos)
    try:
        data = _get_json(f"{LOTTOLOOKUP_BASE}/megasena", timeout)
        d = _normalize_payload(_as_dict(data))
        _ = dezenas_do_resultado(d)  # valida
        return d, "lottolookup:/megasena"
    except Exception:
        pass

    # 1B) LottoLookup /api (às vezes retorna dict com várias loterias)
    try:
        data = _get_json(f"{LOTTOLOOKUP_BASE}", timeout)
        d = _normalize_payload(_as_dict(data))
        _ = dezenas_do_resultado(d)  # valida
        return d, "lottolookup:/api"
    except Exception:
        pass

    # 2) Fallbacks (tenta múltiplas bases e caminhos)
    last_err = None
    for base in FALLBACK_BASES:
        for path in FALLBACK_PATHS:
            url = f"{base}{path}"
            try:
                data = _get_json(url, timeout)
                d = _normalize_payload(_as_dict(data))
                _ = dezenas_do_resultado(d)  # valida
                return d, f"fallback:{url}"
            except Exception as e:
                last_err = e
                continue

    raise MegaSenaAPIError(f"Falha ao buscar resultado em todas as fontes. Detalhe: {last_err}")