# Discussão

## Erros comuns evitados

A Unidade 3 lista seis erros frequentes no pré-processamento de dados de
sensores [@ufjf2026unidade3]. A Tabela 10 mostra como o pipeline evita cada
um deles e onde isso foi verificado.

: Erros comuns e como o pipeline os evita.

| Erro comum | Como o pipeline evita | Onde |
|------------------------------|---------------------------------------------|----------------------|
| Apagar todos os *outliers* | Só remove picos curtos sem reação da corrente; eventos são preservados | Etapa 4, Tabela 3 |
| Preencher todos os faltantes com a média | Interpolação linear só em lacunas de até 5 s; a média geral errou de três a quatro vezes mais | Etapa 5, Tabela 4 |
| Filtrar demais | Savitzky–Golay sem suavizar eventos; alarmes usam a série sem filtro | Etapa 6, Tabela 5 |
| Normalizar sem olhar a distribuição | Min-Max descartado por causa dos picos; escala robusta por regime | Etapa 7, Tabela 6 |
| Calcular parâmetros com treino e teste juntos | Divisão pela ordem do tempo; escala ajustada só no treino (o desvio robusto da Etapa 4 usa a série inteira, mas só mede o ruído do sensor) | Etapa 7 |
| Ignorar o significado físico | Faixa física do sensor, regimes de operação e corrente do motor | Etapas 1 e 3 |

Fonte: Elaborado pelo autor, com base em @ufjf2026unidade3.

## Limitações

- **Dados sintéticos.** Os problemas foram simulados de forma simples. Em
  dados reais, picos de interferência podem durar mais ou coincidir com
  variações da corrente, e os limites usados ($|z| > 6$ para a vibração, $|z| > 3$ para a
  corrente, 3 s e 5 s) precisam
  ser ajustados com a ajuda da equipe de manutenção.
- **Dependência da corrente do motor.** A identificação dos regimes e a
  confirmação de eventos usam a corrente. Se esse sensor também falhar, os
  episódios suspeitos devem ser preservados como indeterminados, nunca
  removidos.
- **Regime definido pela corrente.** Uma falha que aumente a corrente além de
  um limite por mais de 60 s, por exemplo de 16 para 21 A em carga, seria
  tratada como troca de regime. O episódio seria mantido, mas marcado só como
  transição, e não como evento. Isso pode ser evitado com histerese (limites
  diferentes para subir e para descer de regime), com uma duração mínima maior
  ou com o estado de operação informado pelo controlador da máquina.
- **Eventos longos e degradação lenta.** A mediana móvel de 5 minutos passa a
  acompanhar um evento que dure mais de cerca de 2,5 minutos, e a parte final
  dele deixa de parecer anormal. Uma degradação gradual, ao longo de horas ou
  dias, também não é detectada por esse método, porque a mediana sobe junto.
  Para esses casos, é preciso acompanhar a tendência do nível de vibração de
  cada regime, por exemplo a mediana diária, e compará-la com os limites da
  ISO 20816-3 [@iso20816-3].
- **Uma leitura por segundo.** O valor RMS mostra que a vibração mudou, mas
  não a causa mecânica da falha. Para isso seria preciso analisar o sinal
  completo, amostrado em kHz, com análise de frequências [@randall2011].
- **Ausência ligada à falha.** Os dados sintéticos não simularam um sensor que
  para de enviar durante a falha; esse caso só foi testado com a lacuna criada
  artificialmente da Figura 5. Em produção, uma queda de conexão durante um
  evento deve gerar alerta, e não preenchimento.
