# Megasenna

Aplicativo Windows com banco SQLite local para consultar concursos da Mega-Sena,
analisar o histórico, conferir jogos e gerar conjuntos de apostas simples distintas.
O executável funciona sem Python instalado. Consultas e estatísticas funcionam
offline após baixar os resultados; a atualização usa a fonte oficial da CAIXA.

## Abrir

Execute `dist/Megasenna/Megasenna.exe`. Mantenha a pasta `Megasenna` completa
ao mover o aplicativo. A interface possui cinco abas:

- **Concursos:** atualização retomável desde o concurso 1, indicação de lacunas,
  busca por intervalo e exportação JSON.
- **Estatísticas:** frequência de todas as 60 dezenas, percentual de concursos,
  atraso observado, pares/ímpares, somas e pares frequentes.
- **Meus jogos e sugestões:** salvar jogos, conferir contra todo o histórico local,
  gerar conjuntos aleatórios ou diversificados, evitar duplicações e exportar.
- **Carteira e concursos:** vincular jogos a concursos, conferir automaticamente,
  calcular cobertura e custo e revisar alternativas otimizadas para quadra ou quina.
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
para uma aposta simples na aba de probabilidades. A aba Carteira e concursos
calcula a união exata dos eventos do conjunto para quatro ou mais e cinco ou
mais acertos, incluindo as faixas superiores.

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

### Comandos do terminal

Execute `py -3.13 terminal_gui.py`. A ajuda e os comandos são em português:

```text
ajuda
adicionar 5 12 23 34 45 60
listar
excluir ID
excluir_todos
ultimo
comparar
sugerir 10
salvar_sugestoes
salvar_sugestoes 1 3 5
salvar_sugestoes perguntar
probabilidade
limpar
diagnostico
```

`comparar` confere todos os jogos contra o último resultado disponível e os
apresenta do maior número de acertos para o menor, incluindo jogos sem acertos.
Em empates, o menor ID aparece primeiro. A opção 2 de `main.py` usa a mesma
ordenação. `listar` continua mostrando os jogos salvos sem consultar resultados.
Os comandos antigos em inglês continuam aceitos por compatibilidade.

### Carteira, conferência por concurso e backup

Na aba **Carteira e concursos**, escolha a origem da análise: Jogos salvos,
Sugestões ou Concurso informado. O botão **Importar carteira JSON** carrega uma
carteira nas sugestões sem modificar jogos salvos. A distribuição inclui as
carteiras original e alternativa em `dist/carteiras/`.

1. Informe o concurso e o preço por jogo (referência inicial: R$ 6,00, editável).
2. Use **Calcular cobertura e custo** para ver registros, jogos distintos,
   duplicações, custo e chances de ao menos um bilhete com quadra ou mais,
   quina ou mais e sena. Em Concurso informado o custo usa os valores registrados.
3. Escolha quadra ou quina e use **Otimizar mesma quantidade**. A busca reduz
   sobreposições entre os eventos, valida a união exata e mantém a original se
   não encontrar ganho na faixa escolhida. Quantidade e preço permanecem iguais.
   A chance de sena só aumenta se havia jogos repetidos e eles forem substituídos
   por combinações distintas.
4. Revise os resultados antes/depois e exporte a alternativa JSON. Ela também
   fica nas Sugestões; os originais não são substituídos. A busca é heurística,
   sem garantia geral de ótimo global. Pode alterar a cobertura da outra faixa.
5. Com a origem desejada selecionada, use **Vincular carteira escolhida** para
   adicionar cópias das dezenas ao concurso. Vínculos existentes são mantidos;
   jogos iguais naquele concurso são ignorados. O vínculo não confirma pagamento.
6. A conferência mostra os jogos vinculados em ordem decrescente de acertos,
   destacando quadra, quina e sena. Sem resultado local fica aguardando. Após
   atualizar o histórico, as carteiras são conferidas com os resultados novos.
   A última carteira vinculada também é conferida ao abrir o programa.

O cálculo exato aceita até **200 registros** e roda em segundo plano. Cada
resultado de seis dezenas é contado apenas uma vez, mesmo que vários jogos
atinjam a faixa. Quadra ou mais e quina ou mais são eventos sobrepostos e não
devem ser somados. Jogos duplicados continuam custando, mas não ampliam cobertura.

Os snapshots do SQLite ficam em **`backups/` ao lado do banco local**, antes
de atualizar resultados, importar histórico, vincular carteiras ou migrar o
esquema. Uma falha no backup interrompe a atualização. **Backup agora** permite
criar uma cópia manual. As cópias são verificadas com `quick_check` e preservam
dados confirmados ainda no WAL. Para restaurar, feche o programa, preserve o
banco atual e substitua `app.db` por uma cópia escolhida. Os backups contêm jogos
pessoais. Não são apagados automaticamente.

O `build.ps1` também salva o banco e a distribuição anterior em
`build/backups/` antes de substituir os executáveis (o banco usa a pasta de
backups ao lado do próprio arquivo).

No terminal, os mesmos recursos estão disponíveis:

```text
importar_carteira dist/carteiras/carteira-25-2026-09-25.json
cobertura sugestoes 6,00
otimizar quadra sugestoes 6,00
vincular 3063 sugestoes
atualizar
conferir 3063
backup
```

Troque o número do exemplo pelo concurso desejado. `vincular CONCURSO` usa todos
os jogos salvos; `vincular CONCURSO 1 3` usa apenas os IDs indicados.
`cobertura` e `otimizar quina` usam os jogos salvos quando `sugestoes` é omitido.
Vincular sugestões otimizadas preserva o preço usado na otimização.

## Testar e gerar o executável

```powershell
py -3.13 -m pip install -r requirements-build.txt
py -3.13 -m unittest discover -s tests -v
./build.ps1
```

Saídas: `dist/Megasenna/Megasenna.exe` (interface de abas) e
`dist/Megasena.exe` (terminal com comandos em português). O terminal anterior
é substituído pela versão atualizada. Se existir `.venv-build`, o script usa
esse ambiente; caso contrário, usa o comando `python`.
O banco com jogos pessoais não é embutido no programa. O PyInstaller empacota o
Python e o Tkinter; não há servidor, conta online ou serviço de banco a instalar.

Veja [ANALISE.md](ANALISE.md) para os problemas encontrados e os critérios usados.

## Carrinho de 25 apostas no portal CAIXA

Para preencher automaticamente, uma a uma, as 25 apostas da carteira preparada,
consulte [AUTOMACAO_CARRINHO.md](AUTOMACAO_CARRINHO.md). A automação em Python abre
o navegador visível, confere cada jogo no carrinho e para antes do pagamento.

Para usar o navegador já aberto e clicar por coordenadas com PyAutoGUI, consulte
[AUTOMACAO_PYAUTOGUI.md](AUTOMACAO_PYAUTOGUI.md). Esse modo calibra o volante na
tela com cinco pontos iniciais e captura **Colocar no Carrinho** após marcar as
seis dezenas, com o botão ativo. Confere visualmente as dezenas e espera o
volante ficar vazio após o clique. Se houver jogo pendente, confira-o no carrinho
antes de retomar. Esse modo não lê o painel de apostas nem confirma o registro
da aposta no site.
