# Conclusão

Este relatório propôs um pipeline de pré-processamento em oito etapas para o
sensor de vibração da atividade da Unidade 3. Aplicado a dados sintéticos com
problemas conhecidos, ele removeu todas as duplicatas, valores negativos e
picos falsos, inclusive as saturações sem reação da corrente, sem apagar os
dois eventos reais. A Tabela 11 resume as
respostas às perguntas da atividade.

: Respostas às perguntas da atividade.

| Pergunta | Resposta |
|------------------------------|------------------------------------------------------------|
| Como tratar os dados faltantes? | Verificar se a perda é aleatória; preencher por interpolação linear só as lacunas de até 5 s, dentro do mesmo regime; deixar as maiores marcadas como ausentes, porque podem esconder um evento (Etapa 5). |
| Como identificar *outliers*? | Primeiro, pelos limites físicos do sensor: valores negativos são erro, e saturações são testadas como possíveis eventos. Depois, pelo filtro de Hampel, com desvio robusto (1,4826 × MAD) fixo para cada regime. Um pico só é removido se durar até 3 s e a corrente do motor não reagir; caso contrário, é preservado como evento. Métodos globais apagariam a falha real (Etapas 3 e 4). |
| Que filtro usar? | Savitzky–Golay, sem suavizar os trechos de evento; alarmes usam a série sem filtro. A mediana móvel apagaria um impacto real de 4 s (Etapa 6). |
| Como saber se um pico é falha real ou ruído? | Pela duração, pela reação da corrente do motor, pelo momento da operação, pela forma do pico e pela repetição ao longo dos dias (Etapa 4). |
| É preciso normalizar ou padronizar? | Não para alarmes e painéis; sim para modelos de aprendizado de máquina, com padronização robusta por regime calculada só no treino (Etapa 7). |
| O que guardar para auditoria? | Dado bruto, valores de cada etapa, *flags* por leitura, parâmetros com versão, parâmetros de escala, *hashes* das entradas, semente do gerador, contagens por etapa e lista de eventos (Seção 3.10). |

Fonte: Elaborado pelo autor, com base em @ufjf2026unidade3.

Três escolhas foram decisivas para o resultado. A primeira é nunca alterar o
dado bruto e registrar cada decisão por leitura. A segunda é calcular as
estatísticas por regime de operação, porque a vibração normal muda com a
carga. A terceira é só remover um pico quando ele é curto e a corrente do
motor não confirma a falha.

As comparações feitas com os dados sintéticos mostram que essas escolhas têm
efeito real. O escore z e a regra do IQR encontraram todos os picos falsos,
mas apagariam até 121 das 154 leituras dos eventos reais; o filtro de Hampel
sem corroboração apagaria 129. Ao preencher lacunas, o erro da média geral foi
mais de três vezes o da interpolação linear.
E a mediana móvel, que reduz bem o ruído, apagou 94% da altura de um impacto
real. Em todos os casos, o método mais simples melhora a aparência dos dados,
mas perde justamente a informação que o monitoramento da máquina precisa.

Como próximos passos, sugere-se testar o pipeline com dados reais da máquina,
ajustar os limites com a equipe de manutenção e estender o tratamento ao sinal
de vibração completo, antes do cálculo do valor RMS.
