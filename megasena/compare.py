from __future__ import annotations

def normalize_jogo(nums: list[int]) -> list[int]:
    nums = [int(n) for n in nums]
    if len(nums) != 6:
        raise ValueError("Jogo da Mega-Sena precisa ter exatamente 6 dezenas.")
    if any(n < 1 or n > 60 for n in nums):
        raise ValueError("Dezenas devem estar entre 1 e 60.")
    if len(set(nums)) != 6:
        raise ValueError("Não pode repetir dezena no mesmo jogo.")
    return sorted(nums)

def comparar_jogo(jogo: list[int], resultado: list[int]) -> dict:
    j = set(normalize_jogo(jogo))
    r = set(resultado)
    acertos = sorted(j & r)
    return {
        "acertos_qtd": len(acertos),
        "acertos": acertos,
        "faltantes": sorted(j - r),
    }