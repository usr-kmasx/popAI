# popAI 21-1.11.26 — notas da versão

Data: 21 de novembro de 2026. Tag de lançamento: `21-1.11.26`.

Atualização incremental da versão [21.11.26](release-21.11.26.md).
Esta versão muda somente o texto e a temperatura do modo **Cinematic Art**,
a localização do controle **Hide** e as verificações/documentação associadas.
Não troca os modelos de geração de imagem, o backend Vulkan, o ampliador ou
os recursos de referência e desenho.

## Melhorador de prompt — Cinematic Art

- O conteúdo de `prompt-enhancer-cinematic.txt` foi substituído pelo novo
  prompt interno fornecido para o modo Cinematic Art. Ele mantém a estética
  cinematográfica de ilustração anime semirrealista e arte digital de fantasia,
  mas enfatiza a preservação dos personagens, objetos, quantidades, poses,
  ações, cenário, enquadramento e restrições informadas.
- A direção de arte deve escolher, para a cena específica, um ponto focal,
  enquadramento e sensação de lente, iluminação coerente, paleta de cores
  e camadas de primeiro plano, plano intermediário e fundo. Detalhes extras
  devem se limitar aos materiais presentes na cena.
- Em edição com imagem de referência, o prompt instrui modificar somente
  o elemento solicitado e manter o restante inalterado. Para descrições
  curtas, pede cerca de 150–220 palavras; para descrições detalhadas, mantém
  tamanho próximo ao original; para edições simples, uma ou duas frases.
  A saída permanece um único parágrafo em inglês.
- A temperatura do modo `cinematic` passou de **0.4 para 0.3** em
  `prompt_enhancer.py`. Os modos **Simple**, **More details** e **Creative**
  mantêm seus prompts e parâmetros. O modelo continua sendo o LFM3 1.7B
  local na CPU, com contexto de 2048 tokens.
- Cada clique em melhorar envia uma requisição independente, com mensagens
  `system` e `user`, sem histórico de chat. **Undo** restaura o texto
  anterior; melhorar novamente após desfazer usa esse texto restaurado.
  O cache de prompt não cria uma sessão conversacional. Reduzir a temperatura
  não garante fidelidade perfeita e não altera a seed de imagens.

## Interface — Hide ao lado de New

- O botão **Hide** fica na faixa inferior à direita, ao lado do botão
  **Gerar** (seta) e de **New**, e apenas esconde o input do prompt.
- Foi removido o submenu que aparecia no hover da engrenagem.
  Clicar na engrenagem continua abrindo **Settings**.
- Passar o mouse ou clicar na mensagem de status abaixo do input continua
  reabrindo o campo, com o comportamento de animação existente. O app
  não volta a esconder o campo automaticamente.
- O CSS reserva espaço para os três botões inferiores.
- **New** não foi alterado: sorteia uma seed nova e limpa o resultado
  exibido, preservando prompt e referências. Gerar sem usar **New**
  continua reutilizando a seed atual da página, mesmo após alterar o texto.

## Arquivos atualizados

- `prompt-enhancer-cinematic.txt` e `prompt_enhancer.py`.
- `web/index.html`, `web/app.js`, `web/style.css`.
- `tests/test_prompt_enhancer.py` e `tests/frontend.test.cjs`.
- `README.md` e documentação em `docs/`.

## Validação

Testes executados no código local, sem carregar modelos de imagem na GPU:

| Verificação | Resultado |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 27 aprovados |
| `node --test tests/frontend.test.cjs` | 13 aprovados |
| `node --check web/app.js` e `node --check web/sketch.js` | Sem erros de sintaxe |
| `git diff --check` | Sem erros |

Os testes cobrem o modo Cinematic Art, a temperatura configurada, o
restauro de texto de edição, a posição e o funcionamento de **Hide**, a
remoção do hover da engrenagem e a reabertura pelo status. Não houve
avaliação empírica da qualidade visual ou da fidelidade das imagens geradas.

## Histórico

- [Versão anterior 21.11.26](release-21.11.26.md): editor de desenho,
  referências e controles existentes.
- [Registro de validação do melhorador](prompt-enhancer-validation.md):
  configuração inicial, modo Cinematic Art e adendo desta atualização.
- [README](../README.md): instruções de instalação e uso atuais.
