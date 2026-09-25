# Análise técnica e estatística

## Situação encontrada

1. A tabela `concursos` era apenas um cache: havia 1 resultado em `data/app.db`
   e 4 em `dist/data/app.db`. Portanto o sistema não analisava todos os sorteios.
2. O gerador classificava combinações por equilíbrio par/ímpar e distribuição
   numérica. Isso não era uma simulação Monte Carlo de probabilidades e não
   demonstrava maior chance de prêmio. A frequência histórica nem era passada
   pelos fluxos de geração.
3. `main.py` tratava o retorno `(payload, fonte)` como um dicionário e falhava na
   conferência do último resultado.
4. A API aceitava mais de seis dezenas e descartava as excedentes, sem garantir
   seis dezenas distintas no intervalo 1–60. Usava várias fontes de terceiros
   com falhas silenciosas e longa espera acumulada.
5. O banco dependia da pasta de execução. Abrir por um atalho podia criar outro
   banco e fazer parecer que os jogos haviam desaparecido.
6. Operações de rede e geração bloqueavam o loop da interface Tkinter.
7. O interpretador de IDs podia converter `-9` ou texto arbitrário com um número
   em ID válido para exclusão.
8. Não havia testes automatizados, documentação de uso ou distinção clara entre
   análise retrospectiva e previsão.

## Mudanças

- Aplicativo nativo com consultas por intervalo, estatísticas, jogos salvos,
  conferência histórica, geração, probabilidades e avaliação comparativa.
- SQLite local com caminho estável, validação na entrada e consultas parametrizadas.
- Histórico obtido diretamente da CAIXA por número do concurso, com identificação
  validada, atualização incremental, cancelamento e indicação de falhas/lacunas.
- Fotografia dos 3.061 concursos oficiais até 22/09/2026 embutida no executável,
  sem bilhetes pessoais; novas consultas continuam disponíveis no aplicativo.
- Rede e simulação fora da thread da interface. A fila entrega resultados para
  atualização dos componentes na thread principal.
- Sugestões sem duplicatas, possibilidade de excluir jogos salvos e estratégia
  de diversificação de subconjuntos, sem alegação de superioridade preditiva.
- Estatísticas das 60 dezenas, inclusive as que não ocorreram na amostra, com
  percentual teórico de referência de 10% por sorteio.
- Avaliação cronológica reproduzível contra baseline aleatória do mesmo número
  de apostas, com resultados descritivos.

## Probabilidades e limites

A distribuição exata dos acertos de uma aposta simples segue:

`P(X = k) = C(6, k) × C(54, 6 − k) / C(60, 6)`.

A soma das probabilidades para k de 0 a 6 é 1. Os testes verificam essa identidade,
as faixas premiadas e a contagem de jogos distintos na cobertura da sena.

Não existe fundamento para transformar atraso, frequência, soma ou paridade de
um jogo específico em aumento de chance numa loteria independente e uniforme.
Uma classe de padrões pode conter mais combinações que outra; isso não torna
cada combinação dentro dessa classe mais provável.

Com dados completos podemos descrever padrões, investigar qualidade dos registros
e medir resultados históricos. Para alegar viés no sorteio seria necessário um
estudo independente, tratamento de múltiplas comparações e validação prospectiva.
O sistema não faz essa alegação. Também não calcula retorno esperado nem recomenda
valores financeiros de apostas.

## Consultas e desempenho

O número do concurso é chave primária: leitura individual e filtros por intervalo
usam esse índice. O volume de alguns milhares de concursos e 60 dezenas permite
calcular estatísticas em memória sem infraestrutura externa. As conexões SQLite
são curtas; a sincronização persiste resultados validados para permitir retomada.

Guardar as seis dezenas como texto canônico mantém compatibilidade com os bancos
existentes. Uma tabela de ocorrências normalizada só se torna necessária se o
produto passar a consultar milhões de bilhetes ou várias modalidades.

## Próximas evoluções possíveis

- Vincular apostas efetivamente realizadas a concursos e distinguir essas apostas
  de sugestões e conferências retrospectivas.
- Backup/restauração com seleção explícita de múltiplos bancos legados.
- Apostas de 7 a 20 dezenas e cálculo de cobertura da união de combinações.
- Avaliação prospectiva registrada antes de cada sorteio e intervalos de incerteza.

Esses itens ampliam o produto; não constituem promessa de prever resultados.
