# Megasenna

Aplicativo Windows com banco SQLite local para consultar concursos da Mega-Sena,
analisar o histórico, conferir jogos e gerar conjuntos de apostas simples distintas.
O executável funciona sem Python instalado. Consultas e estatísticas funcionam
offline após baixar os resultados; a atualização usa a fonte oficial da CAIXA.

## Abrir

Execute `dist/Megasenna/Megasenna.exe`. Mantenha a pasta `Megasenna` completa
ao mover o aplicativo. A nova interface possui quatro abas:

- **Concursos:** atualização retomável desde o concurso 1, indicação de lacunas,
  busca por intervalo e exportação JSON.
- **Estatísticas:** frequência de todas as 60 dezenas, percentual de concursos,
  atraso observado, pares/ímpares, somas e pares frequentes.
- **Meus jogos e sugestões:** salvar jogos, conferir contra todo o histórico local,
  gerar conjuntos aleatórios ou diversificados, evitar duplicações e exportar.
- **Probabilidades e avaliação:** probabilidades exatas e avaliação cronológica
  comparada com apostas aleatórias de mesmo tamanho.

O executável já inclui os 3.061 concursos oficiais consultados em 24/09/2026,
em arquivo sem jogos pessoais. Use **Atualizar histórico CAIXA** para consultar
concursos posteriores ou completar a base. A atualização pode ser cancelada;
os resultados já confirmados ficam salvos e a próxima execução busca os ausentes.
Uma sequência local sem lacunas só está atualizada até o último concurso que contém.
Falhas de internet ou indisponibilidade da CAIXA não são tratadas como base completa.

## O que as sugestões significam

Em um sorteio justo, cada combinação de seis dezenas tem a mesma chance:

`P(sena) = 1 / C(60, 6) = 1 / 50.063.860`.

Dezenas frequentes ou atrasadas não ficam mais prováveis no próximo sorteio.
O gerador diversificado reduz a repetição de pares e trincas entre os jogos do
conjunto; essa é uma propriedade de cobertura, sem promessa de vantagem preditiva.
O aleatório permite comparar a estratégia sem filtros históricos.

Para `m` jogos simples **distintos** no mesmo concurso, a chance exata de sena é
`m / 50.063.860`. Dez jogos diferentes, por exemplo, cobrem 1 em 5.006.386.
Repetir o mesmo jogo não aumenta a chance de ele ser sorteado.
As probabilidades de quadra e quina do conjunto não podem ser somadas como se os
bilhetes fossem independentes; a interface apresenta essas probabilidades apenas
para uma aposta simples.

O teste retrospectivo compara quantidades iguais de jogos, em ordem cronológica,
sem usar o resultado avaliado para montar as sugestões. Uma diferença observada
em uma amostra não demonstra previsão ou vantagem futura. A avaliação disponível
é descritiva, não um teste de significância nem uma estimativa de retorno financeiro.

Fonte: [regras e probabilidades da CAIXA](https://loterias.caixa.gov.br/Paginas/mega-sena.aspx).

## Banco local e privacidade

- Código-fonte: `data/app.db`, relativo ao projeto, independente da pasta do terminal.
- Executável: `%LOCALAPPDATA%/Megasenna/app.db`.
- Os bancos antigos são preservados. A migração inicial utiliza o banco legado
  encontrado próximo ao executável; confira o caminho mostrado no rodapé.
- Jogos pessoais ficam no computador. A rede é usada para ler resultados públicos.
- Faça backup do arquivo `app.db` com o aplicativo fechado. Exportações JSON
  facilitam a inspeção e o transporte dos registros.

O repositório original já versionava bancos e binários; o `.gitignore` evita novos
artefatos locais, mas não remove os arquivos que já estavam versionados.

## Executar pelo código

Recomendado: Python 3.13 no Windows, com Tcl/Tk habilitado no instalador.
O aplicativo não exige bibliotecas externas em tempo de execução.

```powershell
py -3.13 desktop_gui.py
```

A interface de comandos anterior continua em `terminal_gui.py`; a entrada de
console em `main.py` também permanece disponível.

## Testar e gerar o executável

```powershell
py -3.13 -m pip install -r requirements-build.txt
py -3.13 -m unittest discover -s tests -v
./build.ps1
```

Saída: `dist/Megasenna/Megasenna.exe`. O executável antigo `dist/Megasena.exe` não é substituído.
O banco com jogos pessoais não é embutido no programa. O PyInstaller empacota o
Python e o Tkinter; não há servidor, conta online ou serviço de banco a instalar.

Veja [ANALISE.md](ANALISE.md) para os problemas encontrados e os critérios usados.
