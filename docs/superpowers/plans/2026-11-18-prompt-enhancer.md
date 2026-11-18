# Melhorador de prompt — implementação

Decisão do usuário: AtomicChat/LFM3-1.7B-Uncensored-GGUF, variante Q4_K_M
disponível no repositório (AD-Q4_K_M), llama-server somente CPU, contexto 2048,
raciocínio desligado, porta 8081. Resultado escrito diretamente no input através
de botão SVG. Modelo inicia junto com o servidor e permanece na RAM.
Nenhuma instalação, pacote ou configuração no sistema; arquivos no projeto.

1. Consultar revisões/hashes; obter executor CPU compatível com LFM3 e pesos
   quantizados no projeto. Preservar licenças e registrar versão, tamanho e hash.
2. Serviço próprio com supervisão de processo, inicialização em segundo plano,
   localhost/autenticação, sem reutilizar serviço desconhecido na porta 8081,
   tempo limite e encerramento conjunto. Falha deste serviço não impede imagens.
3. API do app para status e reescrita em streaming. Instrução preserva idioma,
   intenção, estilo e restrições do usuário, acrescentando detalhes visuais úteis;
   referências implicam instruções de edição, sem inventar descrição da referência.
4. Botão SVG de melhoria junto ao input. Streaming direto no texto; sem gerar
   imagem automaticamente. Desativar envio/edição durante melhoria, preservar
   texto original em falha ou cancelamento, oferecer desfazer e cancelar.
5. Validar com modelo real na CPU, medir tempo/RAM, verificar porta ocupada,
   cancelamento/fechamento e falhas; executar regressão existente e conferir GUI.

Decisões locais: idioma original por padrão, pois não houve escolha de tradução;
sem filtros de assunto adicionados. Nenhuma promessa de ausência absoluta de
recusas do modelo. Não iniciar geração de imagem para testar reescrita.

Resultado: itens 1–5 concluídos. Contexto final 2048 conforme pedido posterior.
Revisão independente apontou cancelamento bloqueado na espera do primeiro token
e ausência de exclusão no retry da ampliação; ambos corrigidos. Verificações reais,
regressão e limites documentados em docs/prompt-enhancer-validation.md. Todo arquivo
permanente novo ficou no projeto; nenhuma instalação no sistema ou geração de imagem.
