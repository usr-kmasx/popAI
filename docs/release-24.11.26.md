# popAI V24.11.26 — notas da versão

Data: 24 de novembro de 2026. Tag Git: `24.11.26`.
Continuação de [23.11.26](release-23.11.26.md).

## Corrector e Enhancer

Os quatro modos (Simple, More details, Creative e Dramatic) passam a executar
duas etapas independentes no mesmo processo do Qwen3.5-4B GGUF Q8_0 com Vulkan.

- **Corrector:** interpreta o texto original, corrige sua estrutura e traduz
  para inglês americano, preservando os detalhes e as restrições do usuário,
  sem acrescentar elementos artísticos. Temperatura 0,1; orçamento de reasoning
  de 512 tokens.
- **Enhancer:** recebe somente a descrição corrigida e aplica o modo escolhido,
  com as temperaturas anteriores e orçamento de reasoning de 192 tokens.

Não há histórico compartilhado nem recarregamento dos pesos entre as etapas.
A entrada permanece intacta até o resultado final validado. Undo restaura
o texto original; erros, cancelamento e desconexão preservam a entrada e
liberam o processo de inferência sob demanda.

## Novo mascote

O novo mascote substitui a apresentação anterior por dois olhos animados.
Na tela inicial, os olhos ficam maiores e centralizados; durante a geração
da imagem, deslocam-se para o canto e diminuem de tamanho. Permanecem no
canto enquanto a imagem estiver presente e retornam ao centro com New.

- Pupilas acompanham o cursor e alternam entre formas redondas e horizontais.
- Expressões em repouso e piscadas aleatórias, ocasionalmente duplas.
- O olho esquerdo representa o Corrector com uma linha pulsante; o direito
  representa o Enhancer com duas ondas animadas.
- Aprimorar o prompt não desloca o mascote quando a tela inicial está vazia.
- Durante a geração de imagens, os olhos tremem e se acalmam conforme o
  progresso real de amostragem, decodificação, ampliação e finalização.
  O ciclo de tremor foi ajustado para 600 ms.
- Preferências de movimento reduzido são respeitadas.

## Popup de processamento

Os eventos NDJSON distinguem as etapas, os deltas de reasoning emitidos
pelo modelo local, as respostas intermediárias e o resultado final.
A popup abre somente ao receber texto e permite minimizar e restaurar
a visualização pelo olho ativo. Cada resposta concluída permanece visível
por três segundos sem atrasar a inferência. Erros e cancelamentos fecham
a popup imediatamente. Os textos intermediários não são gravados no
histórico do navegador nem substituem a entrada.

## Instalação e compatibilidade

O instalador, os três conjuntos de modelos de imagem e seus presets
permanecem os mesmos da V23.11.26. Nenhum novo peso é necessário.
Para atualizar uma instalação existente, obtenha a nova versão do
repositório e reinicie o servidor quando não houver trabalho em execução.

## Verificação

- Suíte Python: 54 testes aprovados.
- Suíte JavaScript: 21 testes aprovados.
- Validação de sintaxe e revisão do diff.
- Testes cobrem roteamento entre Corrector e Enhancer, preservação da entrada,
  erros, cancelamento, progresso, popup, minimização e tempo de leitura.

Os testes automatizados usam respostas controladas e não geram imagens na GPU.
Não constituem garantia de qualidade artística ou compatibilidade universal.
