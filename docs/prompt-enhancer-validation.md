# Melhorador de prompt — validação em 2026-11-18

> **Registro histórico de 18/11/2026.** Esta validação ocorreu antes da inclusão
> do modo Cinematic Art. Veja o adendo ao final e as
> [notas da versão 21.11.26](release-21.11.26.md). Para as mudanças atuais,
> consulte também a [versão 21-1.11.26](release-21-1.11.26.md).

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

## Atualização — modo Cinematic Art (21/11/2026)

O melhorador agora oferece quatro modos: **Simple**, **More details**,
**Creative** e **Cinematic Art**. Este último está definido no novo arquivo
`prompt-enhancer-cinematic.txt`, reutiliza o modelo local LFM3 1.7B e usa
**temperatura 0.4**, sem alterar o contexto ou a arquitetura de execução.

A instrução Cinematic Art pede uma descrição única em inglês, com estética de
ilustração anime semirrealista e direção de arte cinematográfica; preserva
personagens, objetos, quantidades, ações, poses, enquadramento e restrições
da cena, evitando forçar elementos góticos, escuros ou sobrenaturais onde
não se encaixam. O texto integral fica no arquivo de prompt correspondente.

Na interface, a seleção do modo aparece no menu do ícone de aprimorar prompt.
A opção **Undo** fica no final do menu quando existe uma versão anterior do
texto para restaurar. Desfazer não inicia novo aprimoramento nem altera
a configuração de temperatura.

Os testes `tests/test_prompt_enhancer.py` cobrem a presença e a seleção do
novo modo (4 casos). A suíte Python atual do projeto inclui 27 testes e
a suíte de interface 13. Essas verificações de software não são uma avaliação
empírica de qualidade artística ou de fidelidade do LFM3 em todos os prompts.
Veja as [notas da versão 21.11.26](release-21.11.26.md).

## Atualização — Cinematic Art em 21-1.11.26 (21/11/2026)

Este adendo substitui **somente a descrição do comportamento atual** do modo
Cinematic Art, sem reescrever os registros de testes históricos acima.
O prompt interno agora está no texto atualizado de
`prompt-enhancer-cinematic.txt`: reforça a preservação literal dos
elementos informados, proíbe personagens ou letreiros adicionais e pede
decisões específicas de ponto focal, ângulo, iluminação, paleta e profundidade.
Para pedidos de edição, exige alteração restrita ao elemento solicitado.

A temperatura exclusiva do modo Cinematic Art foi reduzida de **0.4 para 0.3**
em `prompt_enhancer.py`; os outros modos e o contexto de 2048 tokens
permanecem inalterados. Cada pedido ao `/v1/chat/completions` usa uma
lista nova com uma mensagem `system` e uma `user`. O uso de
`cache_prompt=True` economiza processamento de prefixos, mas não mantém
histórico de conversa. Desfazer e aprimorar de novo o mesmo texto cria
outra requisição independente.

Validação nesta versão: 27 testes Python e 13 testes Node aprovados,
incluindo verificação da temperatura 0.3 e da instrução de manter o
restante da imagem inalterado durante edições. Não foram feitos testes
comparativos de fidelidade visual com geração de imagem.
Veja as [notas da versão 21-1.11.26](release-21-1.11.26.md).
