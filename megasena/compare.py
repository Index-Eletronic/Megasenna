from __future__ import annotations

from collections.abc import Iterable, Mapping


def _inteiro(valor: object, nome: str) -> int:
    """Aceita inteiros e texto inteiro, sem truncar decimais ou aceitar booleanos."""
    if isinstance(valor, bool) or not isinstance(valor, (int, str)):
        raise ValueError(f"{nome} deve ser um número inteiro.")
    try:
        return int(valor)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{nome} deve ser um número inteiro.") from exc


def normalize_jogo(nums: Iterable[int]) -> list[int]:
    if isinstance(nums, (str, bytes)):
        raise ValueError("Informe uma lista com exatamente 6 dezenas.")
    try:
        dezenas = [_inteiro(n, "Dezena") for n in nums]
    except TypeError as exc:
        raise ValueError("Informe uma lista com exatamente 6 dezenas.") from exc
    if len(dezenas) != 6:
        raise ValueError("Jogo da Mega-Sena precisa ter exatamente 6 dezenas.")
    if any(n < 1 or n > 60 for n in dezenas):
        raise ValueError("Dezenas devem estar entre 1 e 60.")
    if len(set(dezenas)) != 6:
        raise ValueError("Não pode repetir dezena no mesmo jogo.")
    return sorted(dezenas)


def normalizar_historico(concursos: Iterable[Mapping]) -> list[dict]:
    """Valida e copia o histórico em ordem crescente. Lacunas são permitidas.

    Duplicatas são rejeitadas para não inflar os cálculos.
    """
    resultado = []
    vistos = set()
    for concurso in concursos:
        if not isinstance(concurso, Mapping) or "numero" not in concurso or "dezenas" not in concurso:
            raise ValueError("Cada concurso deve informar número e dezenas.")
        numero = _inteiro(concurso["numero"], "Número do concurso")
        if numero < 1:
            raise ValueError("Número do concurso deve ser positivo.")
        if numero in vistos:
            raise ValueError(f"Concurso duplicado no histórico: {numero}.")
        vistos.add(numero)
        resultado.append({
            "numero": numero,
            "data_apuracao": concurso.get("data_apuracao"),
            "dezenas": normalize_jogo(concurso["dezenas"]),
        })
    return sorted(resultado, key=lambda item: item["numero"])


def comparar_jogo(jogo: list[int], resultado: list[int]) -> dict:
    j = set(normalize_jogo(jogo))
    r = set(normalize_jogo(resultado))
    acertos = sorted(j & r)
    return {
        "acertos_qtd": len(acertos),
        "acertos": acertos,
        "faltantes": sorted(j - r),
    }


def conferir_historico(jogo: list[int], concursos: Iterable[Mapping]) -> list[dict]:
    """Confere todos os concursos informados, mais recentes antes.

    Acertos passados são comparação retrospectiva, não prêmios reais.
    """
    dezenas = normalize_jogo(jogo)
    return [
        {**concurso, **comparar_jogo(dezenas, concurso["dezenas"])}
        for concurso in reversed(normalizar_historico(concursos))
    ]
