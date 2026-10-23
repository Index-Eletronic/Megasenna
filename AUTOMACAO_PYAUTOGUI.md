# Preencher os 25 jogos com PyAutoGUI

Execute [`preencher_carrinho_pyautogui.py`](preencher_carrinho_pyautogui.py).
Ele usa o **Chrome, Edge ou Firefox que você já abriu** e clica nas dezenas e em
**Colocar no Carrinho**. Não clica em **Ir para pagamento**. A carteira é a mesma
de [`assets/carteira-25-2026-09-25.json`](assets/carteira-25-2026-09-25.json).

## Preparação

1. Abra o [volante oficial da Mega-Sena](https://www.loteriasonline.caixa.gov.br/silce-web/#/mega-sena)
   em **um dos monitores**. Confirme a maioridade e entre na sua conta, se
   desejar. Deixe o navegador visível, com o volante inteiro e os botões
   **Limpar Volante** e **Colocar no Carrinho** na tela. Não mude zoom, tamanho
   da janela, resolução ou rolagem durante os cliques.
2. **Confira o carrinho antes do primeiro uso** e esvazie-o se quiser começar
   os 25 jogos do zero. O script não consulta o conteúdo do carrinho.
3. No terminal do PyCharm, instale as dependências no interpretador que você usa
   para executar o script (o caminho abaixo é o que você mostrou):

   ```powershell
   & "C:\Users\w11\Documents\GitHub\centro_controle_instalacao\.venv\Scripts\python.exe" -m pip install -r "C:\Users\w11\Documents\GitHub\Megasenna\requirements-pyautogui.txt"
   ```

Para só conferir a lista de jogos, sem mover o mouse:

```powershell
& "C:\Users\w11\Documents\GitHub\centro_controle_instalacao\.venv\Scripts\python.exe" "C:\Users\w11\Documents\GitHub\Megasenna\preencher_carrinho_pyautogui.py" --conferir
```

## Primeiro jogo e depois os 25

Recomendo testar **apenas o primeiro jogo**:

```powershell
& "C:\Users\w11\Documents\GitHub\centro_controle_instalacao\.venv\Scripts\python.exe" "C:\Users\w11\Documents\GitHub\Megasenna\preencher_carrinho_pyautogui.py" --ate-jogo 1
```

O programa pedirá quantas dezenas há na primeira linha. Nas imagens enviadas são
**22** (linhas 01–22, 23–44, 45–60). Em uma janela mais estreita podem ser **17**.
Em seguida, para cada um dos **cinco pontos iniciais**, feche a mensagem e mova o mouse ao
centro indicado; a posição será capturada após quatro segundos. Marque `01`, a
última dezena da primeira linha (`22` ou `17`), a primeira da última linha
(`45` ou `52`), `60` e **Limpar Volante**. A prévia também
mostra o centro calculado de `23` (ou `18`, se houver 17 colunas): ele serve para
conferir o início da segunda linha e **não precisa ser calibrado**. O mouse
passa pelos pontos da prévia sem clicar; use **Recalibrar** se algum estiver errado.

Depois de marcar as seis dezenas do primeiro jogo, o programa pede para apontar
o centro de **Colocar no Carrinho** já ativo. Confira a prévia antes do clique.
Essa posição é usada nos jogos seguintes enquanto a grade permanecer no mesmo
lugar. Se o painel lateral ou a janela mudar a grade, o programa pedirá nova
calibração, inclusive do botão ativo, antes de continuar.

Se antes apareceu “fora da tela principal” com `01` em X=2570, isso ocorreu
porque a versão anterior media apenas o monitor principal. Esta versão mede a
área de todos os monitores, pede a posição de `60` e verifica se a captura de
tela e o mouse usam a mesma escala do Windows. As coordenadas antigas podem
mudar; faça a calibração nova com o navegador já posicionado.

Depois do jogo 01, confira no site as seis dezenas, o concurso, o preço e o total.
Volte ao volante da Mega-Sena e execute sem `--ate-jogo` para continuar do 02
ao 25:

```powershell
& "C:\Users\w11\Documents\GitHub\centro_controle_instalacao\.venv\Scripts\python.exe" "C:\Users\w11\Documents\GitHub\Megasenna\preencher_carrinho_pyautogui.py"
```

Antes de cada inclusão, o programa limpa o volante, move o mouse visivelmente,
faz uma pausa entre cliques e confere por imagem **cada dezena selecionada**. Só
clica em **Colocar no Carrinho** se as seis dezenas corresponderem ao jogo. Depois,
espera o volante ficar vazio. Antes do jogo seguinte, verifica se o desenho da
grade continua no mesmo lugar e pede nova calibração se necessário. Se uma
seleção não corresponder ao jogo, interrompe a execução.
Ele **não usa o endereço da aba nem a área de transferência**. Também não lê o
painel **Apostas recentes**, o concurso, o preço ou o total. O volante vazio é
um sinal visual de avanço, **não uma confirmação de que o site registrou o jogo**.
Confira os 25 jogos na página completa do carrinho antes de qualquer pagamento.

## Interrupção e retomada

- Mova o mouse ao **canto superior esquerdo** para interromper imediatamente;
  o `FAILSAFE` do PyAutoGUI permanece ligado.
- O script usa as posições calibradas e capturas da tela. Não faça outra ação no
  computador durante a execução. Depois de qualquer interrupção, confira o
  carrinho antes de tentar novamente.
- O progresso fica em `data/progresso-carrinho-pyautogui.json`. Se o programa
  parar depois de clicar em **Colocar no Carrinho** sem ver o volante voltar ao
  estado vazio, **não repetirá esse jogo automaticamente**. Confira se ele
  entrou no carrinho. No erro relatado, o jogo 01 ficou pendente; depois de
  conferir que ele não entrou, a pendência local foi liberada para novo teste.
  Para começar de novo, primeiro esvazie o carrinho no site e depois execute com
  `--novo-carrinho`. O progresso local registra apenas o
  que a automação observou na tela; ele não comprova a aceitação pelo site.
- Coordenadas medidas de capturas enviadas por mensagem não são usadas para
  clicar: zoom, barra do navegador, escala do Windows e painel lateral mudam
  os pixels reais. O script ativa o modo de DPI por monitor antes de carregar
  o PyAutoGUI e verifica que a captura cobre toda a área dos monitores. Se a
  geometria não coincidir, ele para antes de clicar.

Os jogos são distintos e aumentam a cobertura conjunta; cada combinação
individual tem a mesma probabilidade de sair. O valor esperado para 25 jogos
simples é R$ 150,00, sujeito ao [preço oficial da CAIXA](https://loterias.caixa.gov.br/Paginas/Mega-Sena.aspx).
