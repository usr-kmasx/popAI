# Correções locais — 2026-11-17

> **Histórico.** Os modelos e comandos deste registro refletem 17/11/2026.
> O conjunto atual e a versão 21-1.11.26 estão descritos no
> [README](../README.md) e nas [notas do lançamento](release-21-1.11.26.md).

Autorizado: remover DreamShaper e concluir a simplificação e correções discutidas.
Modelos oficiais: Z-Image Turbo Q8 e Klein 4B Q8. Pesos continuam no SSD externo;
não copiar 16,5 GB para a partição com pouco espaço. Não instalar no sistema.

1. Remover somente DreamShaper: concluído, 2.132.625.894 bytes liberados.
2. Limitar conjuntos/componentes aos dois oficiais; personalizado altera parâmetros.
3. Reutilizar motor em alterações de parâmetros que não afetam o carregamento.
4. Gravar configurações juntas ao Salvar; descarregar/cancelar continua imediato.
5. Distinguir falhas de memória, driver e componentes com instrução pertinente.
6. Usuário ajustou: PNGs novos somente temporários durante a sessão; apenas o download
   pelo botão cria a cópia permanente no destino do navegador. Preservar PNGs antigos.
   Recuperação de etapas finais disponível enquanto os temporários existirem.
   Conter arraste para não perder a imagem e manter enquadramento no resize.

Verificação: suíte existente e verificações diretas, sem geração real nem novos
scripts de teste. Não alterar outros projetos nem criar commits no Git da pasta pai.

Resultado: itens 1–6 implementados. Verificados diretamente: apenas dois conjuntos;
nenhuma recarga ao mudar passos/CFG/resolução/tile; recarga ao mudar mmap; consulta
de pastas sem gravar; preview/referências temporários, nenhum PNG novo em outputs,
recuperação de ampliação sem gerar novamente, limpeza ao encerrar e rollback em
ENOSPC. Falhas VRAM/RAM/driver/componente diferenciadas.
Revisão independente encontrou seleção antiga da GPU de ampliação em cache; corrigida
com renovação da política do ampliador preservando o gerador e verificação direta.
Sem geração em GPU, sem instalação no sistema, sem transferência dos pesos externos.

Verificação final: 17 testes de backend e 6 de interface passaram.
A política anterior de retenção de intermediários foi substituída: PNGs novos
ficam somente no diretório temporário e são removidos ao encerrar o servidor;
somente o download explícito cria a cópia permanente. Arquivos antigos preservados.
