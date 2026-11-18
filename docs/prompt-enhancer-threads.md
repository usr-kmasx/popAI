# Comparação de threads — 2026-11-18

Modelo LFM3 1.7B AD-Q4_K_M, CPU, contexto 2048. Cada configuração recebeu
aquecimento e duas execuções do mesmo prompt, saída fixa de 128 tokens,
amostragem determinística e cache de prompt desligado. Medições incluem prefill.
O cache e o comprimento variáveis do uso normal podem mudar esses tempos.

| Threads | Média total | Primeiro token | CPU média do processo |
| --- | --- | --- | --- |
| 2 | 25.50 s | 8.10 s | 196.1% |
| 4 | 22.84 s | 4.62 s | 387.6% |
| 6 | 19.75 s | 3.71 s | 564.0% |

6 threads reduziram o tempo em 13.5% contra 4, consumindo 45.5% mais
CPU simultânea. Percentuais de CPU somam o tempo dos processadores lógicos:
100% equivale à ocupação de um processador lógico, não do computador inteiro.
2 threads consumiram aproximadamente metade da CPU simultânea de 4, com
tempo total cerca de 12% maior e maior espera inicial. RSS ficou próximo de
1,70 GiB em todos os casos. Outros processos do computador permaneceram ativos;
estes resultados são específicos deste ambiente e não um teste de qualidade.

Recomendação: preservar 4 como equilíbrio. Se a prioridade for somente latência,
6 foram mais rápidos neste teste; 2 reduzem a disputa por CPU. Nenhuma configuração
do app foi alterada. Processos/portas/pastas de teste isolados foram encerrados
e removidos. Nenhuma imagem foi gerada e nada foi instalado.

Resultados brutos: logs/prompt-enhancer-threads-20261118.json.
