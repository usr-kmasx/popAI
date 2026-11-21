# popAI 21.11.26 — notas da versão

Data: 21 de novembro de 2026. Tag de lançamento: `21.11.26`.

Esta versão consolida as mudanças na interface e no editor de referências feitas
após o lançamento `20.11.26`. O aplicativo permanece local no Linux, com o
gerador Vulkan, ampliação Real-ESRGAN e o melhorador de prompts LFM3 executado
na CPU. Nenhum modelo de imagem foi substituído nesta atualização.

## O que mudou

### Editor de desenho integrado

- Ícone de caneta dentro do campo de prompt, logo à direita do botão **+**.
- Disponível com **FLUX.2 Klein 4B** e **FLUX 3 Image Klein**. Fica oculto com
  **Z-Image Turbo**, que não usa referências na implementação atual.
- Janela modal de desenho, sem abrir outra aba, com tela de **960 × 720 (4:3)**
  e moldura da cor do tema `#222824`. A tela é 4:3 **fixa nesta versão**;
  a proporção de saída selecionada para o wallpaper não redimensiona o sketch.
- Pincel, borracha, entrada de texto, seleção e movimento individual, controle
  de espessura, paleta e cor personalizada, desfazer/refazer.
- Formas: retângulo, elipse, **linha reta contínua** e **seta com ponta**.
  Formas, textos e traços novos podem ser selecionados e redimensionados por
  alças nos cantos, incluindo após salvar e reabrir.
- A confirmação produz um PNG de referência e usa o mesmo endpoint
  `POST /api/reference` das imagens enviadas pelo botão **+**.

### Miniaturas e referências

- Clicar em uma referência desenhada pelo app reabre seu editor.
- Após editar, confirmar **substitui a referência na mesma posição**, sem
  acrescentar outra miniatura e sem alterar a ordem das demais referências.
- Elementos editáveis são mantidos no `sessionStorage` da aba, junto com a
  identificação do PNG. Permanecem após **F5** na mesma sessão, desde que a
  referência temporária ainda esteja disponível no servidor.
- Desenhos salvos em versões anteriores, sem dados vetoriais/objetos, podem
  ser reabertos como um **fundo PNG achatado**. É possível acrescentar novos
  objetos, mas não selecionar separadamente os traços antigos.
- Clicar em uma imagem comum enviada pelo botão **+** abre uma visualização
  ampliada em um diálogo. Fechá-la não modifica a referência.
- O limite é de **10 imagens de referência** para os modelos Klein. O botão
  de criar um desenho novo fica indisponível quando esse limite é atingido;
  editar uma referência existente não consome uma posição adicional.

### Prompt e controles de interface

- Novo modo **Cinematic Art**, instruído pelo arquivo
  `prompt-enhancer-cinematic.txt`. Usa o mesmo LFM3 1.7B local do melhorador
  e temperatura `0.4`; a saída pedida é um único parágrafo em inglês,
  preservando elementos e restrições da descrição original.
- Menu do melhorador de prompt com **Simple**, **More details**, **Creative**
  e **Cinematic Art**. **Undo** aparece por último quando há um texto anterior
  que pode ser restaurado.
- O campo de prompt **não se esconde mais automaticamente após 5 segundos**.
  **Hide prompt** foi colocado no menu aberto ao passar o mouse sobre a
  engrenagem; passar o mouse ou clicar na mensagem de status abaixo do campo
  volta a exibi-lo.
- **New** e o botão de gerar ao seu lado permanecem visíveis sem exigir hover.
  **New** limpa apenas o resultado e sorteia nova seed; não elimina o prompt
  nem as referências. A geração usa a mesma seed da página até que uma nova
  seja criada ou a página seja recarregada.

## Implementação e segurança

- Arquivos do editor integrado: `web/sketch.html`, `web/sketch.css`,
  `web/sketch.js`. A interface principal está em `web/index.html`,
  `web/style.css` e `web/app.js`.
- `server.py` serve os três recursos adicionais e permite
  `frame-ancestors 'self'` **somente** para `/sketch.html`. As demais
  páginas mantêm a política anterior de enquadramento.
- A interface e o editor trocam mensagens com `postMessage` após verificação
  de origem; a submissão é validada quanto a tipo e tamanho do PNG e formato
  do estado editável antes do upload.
- Os dados editáveis são **locais à sessão do navegador**. Não substituem
  um formato de projeto persistente ou um arquivo vetorial salvo em disco.
  As imagens temporárias de referências e os resultados são eliminados no
  encerramento do servidor; para conservar uma imagem gerada, use Download.
- `prototypes/sketch.html` e `prototypes/draw-pen.svg` registram a proposta
  independente de interface. **O editor oficial é o de `web/`**; o protótipo
  independente não deve ser usado como referência para as funções mais novas.

## Testes e alcance da validação

Verificações executadas no projeto, sem iniciar uma geração real na GPU:

| Verificação | Resultado |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 27 testes aprovados |
| `node --test tests/frontend.test.cjs` | 13 testes aprovados |
| `node --check web/app.js` e `node --check web/sketch.js` | Sintaxe aprovada |
| Testes do editor independente no Chromium headless | Aprovados |
| Teste integrado no Chromium headless, servidor local isolado | Aprovado |
| `git diff --check` | Sem erros |

O teste integrado verificou criação e edição do desenho, carregamento por miniatura,
substituição sem duplicação, restauração após recarregar, recuperação do PNG antigo
como fundo, preview ampliado de imagem comum, linha e seta (seleção, movimento,
redimensionamento, desfazer/refazer) e comunicação com a API local. Os testes
não medem qualidade da imagem gerada nem desempenho da GPU.

Para repetir a integração opcionalmente, execute em **dois terminais** no
diretório do projeto, com a porta 7863 livre:

Terminal A:
```bash
python3 prototypes/test-sketch-server.py
```

Terminal B:
```bash
node prototypes/test-sketch-integration.mjs
```

Encerre o servidor isolado do terminal A com Ctrl+C ao terminar. O teste usa
um gerenciador fictício (sem carregar pesos) e o Chromium em modo headless.

O teste do editor independente usa um servidor estático separado em 7861:
```bash
python3 -m http.server 7861 --bind 127.0.0.1 --directory prototypes
```
Em outro terminal, execute `node prototypes/test-sketch.mjs`.

## Histórico e documentos relacionados

- [README principal](../README.md): instalação, modelos, execução e uso atual.
- [Referências e edição](reference-editing.md): implementação inicial e adendo
  com os recursos atuais.
- [Validação do melhorador de prompt](prompt-enhancer-validation.md): testes
  históricos do LFM3 e extensão Cinematic Art.
- [Fluxo de ampliação](upscale-pipeline.md): arquitetura do pipeline de geração.
- Os arquivos `docs/superpowers/` e demais registros datados descrevem
  decisões históricas; não são a descrição normativa da versão atual.
