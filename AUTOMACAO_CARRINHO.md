# Preencher os 25 jogos no carrinho da Mega-Sena

Esta automação usa o navegador visível para preencher, um por vez, os 25 jogos de
[`assets/carteira-25-2026-09-25.json`](assets/carteira-25-2026-09-25.json). Ela
confere as seis dezenas antes de cada clique e lê a aposta na página completa do
carrinho depois da inclusão. Não aciona **Ir para pagamento** nem registra a
compra; o carrinho deve ser conferido no site.

## Preparar no PyCharm (Windows)

1. Abra esta pasta como projeto no PyCharm. Crie um ambiente Python 3.13 e
   selecione `.venv/Scripts/python.exe` como interpretador do projeto:

   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements-automation.txt
   ```

2. Confira os jogos sem abrir o site:

   ```powershell
   .\.venv\Scripts\python.exe preencher_carrinho.py --conferir
   ```

3. Para preencher o carrinho, execute:

   ```powershell
   .\.venv\Scripts\python.exe preencher_carrinho.py
   ```

O Edge abre o [portal oficial da CAIXA](https://www.loteriasonline.caixa.gov.br/silce-web/#/mega-sena).
Confirme você mesmo a maioridade e, se desejar, entre na sua conta. Abra o
volante da Mega-Sena e pressione **Enter no terminal** quando as dezenas 01 a 60
estiverem visíveis. Se o portal não fizer uma sincronização de conta, confira o
carrinho aberto e digite **CONFERIDO** no terminal depois que ele carregar. O
script irá ler o carrinho atual, ignorar jogos desta
carteira que já estejam lá exatamente uma vez, preencher os demais e voltar ao
carrinho para conferir cada inclusão. Ao final, o navegador permanece aberto até
você pressionar Enter mais uma vez.

O perfil do navegador fica em `data/perfil-navegador-carrinho/`, ignorado pelo Git.
Ele pode reter a sessão de acesso, então use o projeto apenas no seu computador.
Também é possível trocar `--navegador msedge` por `--navegador chrome`.

## Conferências e limites

- Cada jogo deve ter seis dezenas distintas de 01 a 60; a carteira inteira deve
  conter 25 jogos distintos.
- Antes de cada inclusão, o script usa **Limpar Volante**, marca as seis dezenas,
  confirma a seleção exata, quantidade **6**, **Teimosinhas 0** e valor **R$ 6,00**.
- Depois do clique, ele exige a aposta na lista recente **e** sua linha no
  carrinho, com mesmo jogo, preço, teimosinha e concurso. Se o site mudar,
  ocorrer um alerta ou uma conferência falhar, ele para sem tentar outro clique.
- Em conta conectada, a leitura do carrinho espera a resposta de sincronização
  da CAIXA e confere que a tabela exibida corresponde à resposta. Sem essa
  requisição, pede uma conferência visual inicial para não tratar dados ainda
  carregando como carrinho vazio.
- A leitura do carrinho permite retomar após uma interrupção sem repetir jogos já
  encontrados lá. Se houver um mesmo jogo duplicado, com teimosinha, preço
  inesperado ou concursos diferentes, a execução para para conferência manual.
- Vinte e cinco apostas simples custam **R$ 150,00** por concurso segundo o
  [preço oficial atual](https://loterias.caixa.gov.br/Paginas/Mega-Sena.aspx).
  O portal pode impor limites dinâmicos ao carrinho. Verifique o total e o
  concurso mostrados antes de decidir sobre qualquer pagamento.

Os seletores foram conferidos no código público do portal em 23/10/2026. O fluxo
foi testado em uma página local que reproduz o volante e o carrinho. Uma sessão
real do usuário ainda precisa confirmar que o portal aceita a automação no
navegador visível; o acesso automatizado sem interface recebeu bloqueio do
serviço de proteção do site. O script não tenta contornar bloqueios nem desafios
de acesso.

As 25 apostas aumentam a cobertura do **conjunto** porque são diferentes e pouco
sobrepostas. Nenhuma combinação individual é mais provável de sair do que outra.
