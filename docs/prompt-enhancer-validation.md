# Melhorador de prompt — validação em 2026-11-18

Modelo AtomicChat/LFM3-1.7B-Uncensored-GGUF, AD-Q4_K_M, SHA-256 e tamanho
conferidos: 1.132.208.000 bytes. Revisão e fontes fixadas em prompt-enhancer.json.
llama-server compilado para CPU x86-64/AVX2, sem CUDA ou Vulkan; executor e
bibliotecas locais ocupam cerca de 19 MiB. Licenças preservadas. Nenhuma instalação
no sistema e nenhum peso de imagem movido.

Configuração final: contexto 2048, -ngl 0, --device none, --reasoning off,
--parallel 1, --no-context-shift, 4 threads, localhost:8081 e chave interna.
O contexto foi reduzido de 4096 por solicitação do usuário durante a implementação.
Conferido diretamente no comando do processo real.

Testes reais, sem gerar imagens:

- Prompt de geração em português convertido em um parágrafo em inglês. Interface
  com contexto 4096: 14,30 s e 12,47 s. Contexto final 2048: 14,70 s, primeiro
  token em 4,68 s. A redução de contexto não acelerou significativamente esse caso.
- Instrução simples de edição com o prompt interno final: 7,40 s. Preservou rosto,
  roupa e composição, sem trazer objetos do exemplo de geração. O exemplo não
  é incluído nos pedidos de edição para evitar contaminação do contexto.
- Streaming observado no textarea; botão SVG, desfazer e cancelamento conferidos
  no navegador. Cancelamento e falhas restauram o texto original.
- Cancelamento explícito antes do primeiro token liberou o pedido do app em 0,001 s.
  O cálculo nativo já iniciado ainda conclui o lote corrente antes de ficar ocioso;
  o cancelamento não descarrega o modelo.
- Modelo permaneceu na RAM entre pedidos. RSS observado de aproximadamente
  1,7 GiB; CPU ociosa após estabilizar: zero ticks em uma janela de dois segundos.
  Essa medida não representa uma média entre computadores.
- Porta 8081 ocupada: outra instância informou o conflito sem adotar ou encerrar
  o processo existente. Acesso ao endpoint de modelo sem chave retornou 401.
- Encerramento do app durante uma melhoria real: motor e supervisor encerrados,
  estado temporário removido. Os testes usaram configurações isoladas; a data de
  modificação da configuração real é anterior ao início desta preparação.
  A pasta temporária de compilação foi removida; executor funciona com suas
  bibliotecas do projeto após essa remoção.
- 18 testes existentes de backend e 6 de interface passaram. Mais 3 verificações
  temporárias de interface passaram: streaming/desfazer sem gerar imagem, erro
  após texto parcial e encerramento incompleto restaurando o original. Nenhum
  arquivo adicional de teste foi criado.

Os registros em logs/prompt-enhancer-validation.json incluem uma tentativa
anterior ao ajuste do prompt, não representativa da saída final. Resultados com
2048 estão em logs/prompt-enhancer-2048-validation.json; a instrução de edição
final em logs/prompt-enhancer-edit-final-validation.json. Cancelamento e repouso
em logs/prompt-enhancer-cancel-validation.json. Captura da interface em
docs/prompt-enhancer.jpg.

Limites técnicos: a descrição e a saída compartilham o contexto de 2048 tokens;
não há meta fixa de palavras. A aplicação limita textos a 16.000 caracteres e
pedidos a 120 segundos para não deixar a interface presa. Não foram acrescentados
filtros de assunto ao app; não se promete ausência absoluta de recusas do modelo.
