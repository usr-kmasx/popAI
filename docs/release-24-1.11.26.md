# popAI V24-1.11.26 — notas da versão

Data: 24 de novembro de 2026. Tag Git: `24-1.11.26`.
Continuação de [24.11.26](release-24.11.26.md).

## Editor de poses integrado

O editor de poses 2D passa a fazer parte do editor de desenho (lápis)
para os modelos que aceitam referências: FLUX.2 Klein 4B e Qwen Image 2.1.
O editor de desenho anterior permanece disponível, agora com a ferramenta Pose.

- Articulações manipuláveis com cinemática inversa ou rotação direta.
- Presets pesquisáveis por nome e categoria, espelhamento, espessura,
  rotação, visibilidade e ordenação de partes do corpo.
- Interface na paleta do popAI, com cantos retos, área de desenho ajustada
  à altura da janela e rolagem independente dos painéis laterais.
- Câmera 2D: Espaço + arrastar ou botão central + arrastar; roda do mouse
  para zoom; clique na porcentagem para restaurar a visão.
- Salvamento e abertura de projetos de pose em JSON, além de exportação
  em SVG e PNG.

## Composição e referências

A opção **Use in sketch** insere a pose como objeto PNG transparente
selecionável, mantendo sua proporção ao redimensionar. É possível mover,
excluir, desfazer, refazer e inserir várias poses no mesmo desenho.
O desenho pode ser reaberto pela miniatura da referência, preservando
seus objetos e posições. A pose inserida é rasterizada: as articulações
não são editáveis individualmente dentro do desenho.

O fluxo direto do editor de poses para a geração foi descartado em favor
de uma composição final no lápis. O usuário mantém as ferramentas de
desenho e pode adicionar objetos ao redor dos personagens.

## Instruções por referência

Na geração, a interface acrescenta ao pedido enviado ao modelo instruções
que identificam o número de cada referência criada pelo editor.
Desenhos com poses orientam a postura e composição; desenhos sem poses
orientam a disposição visual. Imagens importadas pelo botão + não recebem
instruções adicionais. O texto visível do usuário não é alterado.
Não há ControlNet, modelo adicional, nova dependência ou mudança no motor
de geração; trata-se de orientação por imagem e texto, não de controle
anatômico garantido.

## Validação

- Dois testes manuais de geração foram aprovados pelo usuário: as posturas
  foram reconhecidas sem reprodução literal do manequim.
- Testes de navegador validaram inserção, movimentação, redimensionamento,
  reabertura, câmera, layout e integração com a política de segurança do
  servidor.
- Suíte Python: 54 testes aprovados.
- Suíte JavaScript: 22 testes aprovados.

A fidelidade em todas as poses e modelos ainda não foi comprovada.
O instalador e os pesos existentes permanecem inalterados.
