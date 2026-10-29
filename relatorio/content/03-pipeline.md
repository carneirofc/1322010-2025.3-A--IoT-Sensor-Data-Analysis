# Pipeline de pré-processamento

## Visão geral

O pipeline tem oito etapas (Figura 2). Elas seguem a sequência proposta na
Unidade 3 [@ufjf2026unidade3], com uma mudança de ordem: os *outliers* são
tratados antes dos dados faltantes. Se as lacunas fossem preenchidas antes, a
interpolação usaria os picos falsos como referência e espalharia o erro para
as leituras vizinhas.

Três regras valem para todas as etapas:

1. **O dado bruto nunca é alterado.** Cada etapa grava o resultado em uma nova
   coluna, e o valor original continua disponível.
2. **Marcar antes de apagar.** Toda decisão sobre uma leitura (inválida, pico
   falso, preenchida, evento) fica registrada em uma marcação (*flag*) daquela
   leitura.
3. **O conhecimento físico vem antes da estatística.** Um valor impossível é
   erro. Um valor possível, mesmo raro, pode ser um evento real.

![Etapas do pipeline de pré-processamento proposto.](fig02-pipeline.png){width=100%}

Fonte: Elaborado pelo autor (2026).

## Etapa 1 — Conhecer os dados

Antes de tratar os dados, registram-se as características do sensor: grandeza
(vibração RMS), unidade (mm/s), frequência (1 leitura/s) e faixa de medição
(0 a 50 mm/s). Esses valores definem os parâmetros das próximas etapas.

Também é preciso conhecer os regimes de operação. A vibração normal muda
com a carga da máquina: 5,6 mm/s é normal em carga alta, mas anormal com a
máquina em vazio (Figura 1). Por isso, os regimes foram identificados pela
corrente do motor, com limites de 2, 12 e 20 A. Para que oscilações rápidas
da corrente não criem regimes falsos, a corrente é suavizada por uma mediana
móvel de 15 s, e uma mudança de regime só é aceita se durar pelo menos 60 s.
Todas as estatísticas das etapas seguintes são calculadas separadamente para
cada regime. Os 20 s antes
e os 60 s depois de cada troca de regime são marcados como transição.

## Etapa 2 — Verificar a estrutura

Esta etapa corrige a forma dos dados, sem julgar os valores:

- **Duplicatas:** registros com o mesmo dispositivo, medição e horário são
  removidos, e fica o primeiro recebido. Como o QoS 1 reenvia a mesma
  mensagem, as cópias devem ter o mesmo valor; se o valor for diferente, o
  caso é contado no registro de auditoria para investigação. As 180
  duplicatas foram eliminadas, todas com valor igual ao original.
- **Ordem:** as leituras são ordenadas pelo horário do sensor.
- **Grade de 1 s:** os horários são arredondados para o segundo, e cada
  segundo sem leitura passa a aparecer como ausente. Foram encontradas 575
  ausências (2,0%), igual ao valor do enunciado.
- **Variação no horário:** se o relógio do sensor varia muito, duas leituras
  podem ser arredondadas para o mesmo segundo e deixar o segundo vizinho
  vazio, o que criaria uma lacuna falsa. Nesse caso, a segunda leitura é
  movida para o segundo vizinho do lado do seu horário original: o segundo
  seguinte, se o horário foi arredondado para baixo, ou o anterior, se foi
  arredondado para cima. Se esse segundo já estiver ocupado, fica a primeira
  leitura e a colisão é contada. Nos dados sintéticos, a variação foi de até
  0,2 s e não houve colisões.

## Etapa 3 — Verificar a validade

Esta etapa separa o que é erro do que é apenas um valor fora do comum:

- **Valores negativos:** são impossíveis para uma vibração RMS e foram
  transformados em ausentes. Foram 3 leituras.
- **Sensor travado:** o mesmo valor repetido por 60 s com a máquina ligada.
  Não houve casos nos dados sintéticos, mas a regra fica ativa.
- **Saturação:** uma leitura no fundo de escala (o código 65,5 mm/s) não é
  necessariamente um erro. Ela pode indicar uma vibração real acima do que o
  sensor consegue medir, ou seja, um valor de pelo menos 50 mm/s. Por isso, a
  leitura não é apagada: ela é marcada como saturada, registrada como
  50 mm/s e segue para a Etapa 4, que aplica o mesmo teste de duração e
  corrente usado nos picos. As 4 saturações dos dados sintéticos duraram 1 s
  cada e não tiveram reação da corrente, então foram removidas como picos
  falsos. Se uma saturação for mantida como evento, o valor de 50 mm/s é só um
  limite inferior. Por isso, leituras marcadas como saturadas não entram em
  médias, percentis ou no ajuste de escala como se fossem valores exatos.

Valores altos, mas possíveis, não são removidos nesta etapa, porque podem
ser justamente a falha que se quer detectar.

## Etapa 4 — Identificar *outliers* e separar falha de ruído

### Como identificar

Média e desvio-padrão são distorcidos pelos próprios picos. Por isso,
usou-se o filtro de Hampel, que compara cada leitura com a mediana dos seus
vizinhos e mede a distância usando o desvio absoluto mediano (MAD), uma
medida de dispersão que não é afetada pelos picos [@hampel1974; @pearson2016].
Multiplicado por 1,4826, o MAD fica na mesma escala do desvio-padrão quando o
ruído é normal. Esse produto é chamado aqui de desvio robusto:

$$
z = \frac{\text{leitura} - \text{mediana móvel}}{\text{desvio robusto do regime}},
\qquad \text{desvio robusto} = 1{,}4826 \times \text{MAD}
$$

Foi usada uma variante do filtro. No filtro de Hampel clássico, o MAD é
calculado na mesma janela móvel da mediana [@pearson2016]. Aqui, o desvio
robusto é fixo para cada regime e calculado nos trechos de operação estável,
porque a variação normal cresce com a carga: 0,18 mm/s em vazio, 0,32 mm/s em
carga e 0,48 mm/s em carga alta. Com a escala fixa, ela não aumenta durante
uma falha, e a falha continua com $|z|$ alto. Uma leitura é considerada suspeita
quando $|z| > 6$.

Esse desvio foi estimado com as oito horas inteiras, antes da divisão em
treino e teste da Etapa 7. Aqui isso é aceitável, porque ele só mede o nível
de ruído do sensor em cada regime e não é usado como entrada de modelo. Em
produção, ele seria estimado com um histórico anterior e mantido fixo, como os
parâmetros de escala da Etapa 7.

A mediana móvel é centrada e usa uma janela de 5 minutos (301 leituras). Ela
só começa a acompanhar um evento que dure mais que metade da janela, cerca de
2,5 minutos. A falha simulada, de 150 s, está perto desse limite. Falhas mais
longas e degradações lentas são discutidas na Seção 4.2.

### Falha real ou ruído?

Um pico pode ser interferência elétrica ou uma falha mecânica de verdade.
Nenhum critério isolado resolve a dúvida, então cada episódio suspeito é
avaliado com os critérios da Tabela 2.

: Critérios para separar pico falso de falha real.

| Critério | Pico falso | Falha real |
|-------------------------|-----------------------------------|-----------------------------------|
| Duração | 1 a 3 leituras | Vários segundos |
| Outros sensores | Corrente do motor estável | Corrente do motor reage junto |
| Momento | Partida, parada ou troca de regime | Operação estável |
| Forma | Salto e volta imediata | Subida e descida graduais |
| Repetição | Coincide com partida de outras máquinas | Volta a acontecer ou piora com os dias |

Fonte: Elaborado pelo autor, com base em @ufjf2026unidade3.

Os três primeiros critérios foram automatizados na sequência de perguntas da
Figura 3. Para a corrente, calcula-se um escore $z$ da mesma forma que para a
vibração, com mediana móvel de 5 minutos e o desvio robusto da corrente em
operação estável. Considera-se que a corrente reage quando a mediana de $|z|$ da
corrente durante o episódio passa de 3. Leituras suspeitas separadas por até
5 s formam um único episódio.

A ordem das perguntas importa. O teste de duração e corrente vem antes do
teste de troca de regime, porque é justamente nas partidas e trocas de regime
que os picos falsos são mais comuns (Tabela 2). Assim, um pico curto e sem
reação da corrente é removido mesmo dentro de uma transição; nos dados
sintéticos, um pico falso e uma saturação caíram em trocas de regime e foram
removidos. Um episódio mais longo ou com reação da corrente, dentro de uma
transição, fica como indeterminado: é mantido e marcado, mas não é tratado
como evento, porque o desvio pode vir da própria mudança de carga. Nos dados
sintéticos, 7 episódios (48 leituras) ficaram como indeterminados. Os outros dois critérios da
Tabela 2 ajudam a investigar os episódios marcados como evento, junto com a
equipe de manutenção.

![Sequência de decisão aplicada a cada leitura.](fig03-decisao.png){width=95%}

Fonte: Elaborado pelo autor (2026).

A Figura 4 mostra o resultado em dois casos. Foram removidas 36 leituras como
picos falsos, exatamente as 36 leituras dos 33 picos inseridos, além das 4
saturações sem reação da corrente. Os dois eventos reais foram preservados. O impacto de 4 s mostra por que a duração sozinha não basta: ele
é curto como um pico falso, mas a corrente também reage.

![Classificação de picos: (a) pico falso removido; (b) falha real preservada. Abaixo de cada painel, a corrente do motor.](fig04-outliers.png){width=100%}

Fonte: Elaborado pelo autor (2026).

### Comparação com métodos mais simples

Para ver se essa regra é necessária, ela foi comparada com três detectores
mais simples. Os dois primeiros são os métodos estatísticos citados na
Unidade 3, calculados sobre a série inteira; o terceiro é o filtro de Hampel
sem a etapa de corroboração. A Tabela 3 mostra o que cada um marcaria para
remoção. A comparação usa só as leituras dentro da faixa de medição: os
3 valores negativos e as 4 saturações ficam de fora, porque já são tratados
na Etapa 3.

: O que cada detector marcaria para remoção.

| Detector | Leituras de picos falsos encontradas | Leituras normais marcadas | Leituras de eventos reais marcadas |
|------------------------------------|------------:|------------:|------------:|
| Escore z global ($|z| > 3$) | 36 de 36 | 0 | 120 de 154 |
| Regra do IQR global | 36 de 36 | 0 | 121 de 154 |
| Hampel por regime ($|z| > 6$) | 36 de 36 | 48 | 129 de 154 |
| Hampel + corroboração (proposto) | 36 de 36 | 0 | 0 de 154 |

Fonte: Elaborado pelo autor (2026).

Todos encontram os picos falsos, porque eles são muito altos. A diferença
está no que mais seria apagado. O escore z e a regra do IQR removeriam a
maior parte da falha real, já que ela também é um valor raro. O filtro de
Hampel sozinho ainda marcaria 48 leituras normais, todas em trocas de regime;
na regra completa, elas são os 7 episódios indeterminados e não são
removidas. Só a regra completa remove os picos falsos sem tocar nos eventos.

## Etapa 5 — Tratar os dados faltantes

### Por que os dados estão faltando?

Antes de preencher uma lacuna, é preciso entender por que ela existe
[@little2019]. Se a perda é aleatória, como um pacote perdido na rede,
preencher é seguro. Se o sensor para de enviar justamente quando a vibração
sobe, a lacuna é um sinal de problema, e preenchê-la esconderia a falha
[@ufjf2026unidade3]. Nos dados sintéticos, a taxa de ausência foi parecida em
todos os regimes (entre 1,5% e 2,4%) e não aumentou com a vibração, o que
indica perdas aleatórias de comunicação.

### Qual método usar?

Depois das etapas 3 e 4, as lacunas somam 618 leituras: as 575 ausências
originais, os 3 valores negativos, as 4 saturações e as 36 leituras de picos
falsos removidas. Para escolher
o método de preenchimento, foram criadas lacunas artificiais em trechos onde
o valor real é conhecido. Cada método preencheu 300 lacunas de cada tamanho,
e o erro foi medido (Tabela 4).

: Erro médio ao preencher lacunas de operação normal (mm/s).

| Lacuna | Média geral | Média do regime | Último valor (LOCF) | Linear | Spline cúbica |
|---------|-------:|-------:|-------:|-------:|-------:|
| 1 s | 1,26 | 0,30 | 0,42 | 0,34 | 0,40 |
| 5 s | 1,31 | 0,29 | 0,41 | 0,35 | 0,68 |
| 30 s | 1,28 | 0,30 | 0,39 | 0,36 | 2,44 |
| 60 s | 1,25 | 0,30 | 0,41 | 0,37 | 4,92 |

Fonte: Elaborado pelo autor (2026).

A média geral erra de três a quatro vezes mais que a média do regime, o
último valor e a interpolação linear, porque ignora o regime da máquina. A
spline cúbica funciona em lacunas de 1 s, mas oscila cada vez mais em lacunas
longas, como alerta a Unidade 3; a partir de 30 s, erra mais até que a média
geral. A média do regime e
a interpolação linear erram pouco, perto do próprio nível de ruído do
sensor.

A média do regime erra um pouco menos aqui porque, nos dados sintéticos, a
vibração é quase constante dentro de cada regime. Ela supõe, porém, que nada
mudou durante a lacuna. A Figura 5 mostra o que acontece quando essa
suposição falha. Os dados sintéticos não têm uma queda de conexão durante a
falha; por isso, para este teste, foi criada artificialmente uma lacuna de
60 s sobre o início da falha real. A interpolação linear desenha uma subida
que começa cerca de 20 s antes da falha verdadeira, e o último valor (LOCF)
esconde a falha até o fim da lacuna.

![Preenchimento de uma lacuna de 60\ s criada artificialmente sobre o início da falha real.](fig05-lacuna-evento.png){width=100%}

Fonte: Elaborado pelo autor (2026).

### Regra adotada

Com base nesses resultados, o tratamento depende do tamanho da lacuna
(Figura 6):

- **Lacunas de até 5 s:** preenchidas por interpolação linear. Em 5 s a
  máquina não tem tempo de mudar de estado, e a reta acompanha mudanças
  locais, como o início de um evento, melhor que uma média fixa. Foram 434
  lacunas curtas (442 leituras).
- **Lacunas maiores que 5 s:** não são preenchidas. Ficam marcadas como
  ausentes, porque não há como saber o que aconteceu durante a lacuna
  (Figura 5). Foram as 4 quedas de conexão (176 leituras).

A interpolação nunca atravessa uma troca de regime nem as fronteiras entre os
conjuntos de treino, validação e teste (Etapa 7).

![Tratamento de lacunas: (a) lacuna curta preenchida; (b) queda de conexão de 60\ s mantida como ausente.](fig06-lacunas.png){width=100%}

Fonte: Elaborado pelo autor (2026).

## Etapa 6 — Filtrar o ruído

O ruído de alta frequência é a variação rápida das leituras em torno do valor
verdadeiro. Ele vem de interferência elétrica, da resolução do sensor e de
vibrações do ambiente [@ufjf2026unidade3]. Filtrar ajuda a enxergar a
tendência, mas todo filtro tem um custo: quanto mais reduz o ruído, mais ele
achata eventos curtos. Quatro filtros foram comparados: média móvel, mediana
móvel e Savitzky–Golay, com janela de 11 s (polinômio de ordem 2 no caso do
Savitzky–Golay), e suavização exponencial com $\alpha = 0{,}2$. Foram medidos
três itens (Tabela 5 e Figura 7):

- **Ruído removido:** quanto o desvio-padrão do resíduo diminui depois do
  filtro, em 30 minutos de operação estável em carga. O resíduo é a diferença
  entre a leitura e uma mediana móvel de 2 minutos, que representa o nível
  verdadeiro.
- **Altura do impacto preservada:** quanto da altura do impacto real de 4 s
  sobra depois do filtro.
- **Atraso no início da falha:** quantos segundos a mais o filtro leva para
  cruzar a metade da subida da falha.

: Comparação de filtros com janela de 11\ s.

| Filtro | Ruído removido | Altura do impacto preservada | Atraso no início da falha |
|------------------------------------------|------------:|------------:|------------:|
| Média móvel | 72% | 27% | 1 s |
| Mediana móvel | 65% | 6% | 0 s |
| Suavização exponencial | 68% | 41% | 5 s |
| Savitzky–Golay | 56% | 56% | 0 s |
| Savitzky–Golay sem suavizar eventos | 56% | 100% | 0 s |

Fonte: Elaborado pelo autor (2026).

![Resposta dos filtros (a) ao impacto real de 4\ s e (b) ao início da falha de 150\ s.](fig07-filtros.png){width=100%}

Fonte: Elaborado pelo autor (2026).

A média e a mediana móveis removem mais ruído, mas quase apagam o impacto. A
mediana é ótima contra picos isolados, mas por isso mesmo ignora um evento
real de poucos segundos. A suavização exponencial é simples e usa pouca
memória, mas atrasa a detecção da falha. O filtro de Savitzky–Golay
[@savitzky1964] ajusta uma curva em cada janela e preserva melhor a altura dos
picos.

A escolha foi o filtro de Savitzky–Golay, sem suavizar os trechos marcados
como evento. Além disso, o pipeline gera duas séries:

- **série tratada, sem filtro:** usada para alarmes, porque mantém a altura
  real dos picos. Na nuvem, ela é o resultado das Etapas 2 a 5. No *gateway*,
  em tempo real, os alarmes usam uma versão simplificada da Etapa 4
  (Seção 3.11), para não disparar nos picos falsos;
- **série filtrada:** usada para gráficos de tendência, painéis e como
  entrada de modelos (Etapa 7).

Dois cuidados na leitura da Tabela 5. Primeiro, os 100% da última linha
dependem da Etapa 4: o trecho só deixa de ser suavizado porque já foi marcado
como evento. Um evento que a Etapa 4 não detectar será suavizado como o resto
da série, e a altura preservada volta a ser de 56%. Segundo, a média, a
mediana e o Savitzky–Golay são centrados: para calcular o valor de um
instante, usam 5 s de leituras futuras. O atraso de 0 s vale para o
processamento em lote. Em tempo real, esses filtros só entregam o valor 5 s
depois, enquanto a suavização exponencial usa apenas leituras passadas. Como a
série filtrada serve só para gráficos e painéis, e os alarmes usam a série sem
filtro, esse atraso não prejudica a detecção.

## Etapa 7 — Normalizar ou padronizar?

Depende do uso dos dados [@ufjf2026unidade3]:

- **Alarmes e painéis:** não é necessário. Os limites de vibração da
  ISO 20816-3 são dados em mm/s, e o operador precisa ler a unidade física
  [@iso20816-3].
- **Modelos de aprendizado de máquina:** é necessário padronizar quando o
  modelo é sensível à escala, como KNN, SVM ou redes neurais. Modelos
  baseados em árvores de decisão dispensam essa etapa.

A Tabela 6 mostra como algumas leituras ficam em três escalas diferentes.

: A mesma leitura em três escalas.

| Leitura | mm/s | Min-Max geral | Escore z geral | Robusta por regime |
|----------------------------|-------:|-------:|-------:|-------:|
| Típica em vazio | 1,60 | 0,04 | $-0{,}78$ | $-0{,}09$ |
| Típica em carga | 3,77 | 0,09 | 0,17 | $-0{,}02$ |
| Típica em carga alta | 5,68 | 0,13 | 1,01 | 0,12 |
| Pico da falha real | 15,78 | 0,36 | 5,42 | 29,15 |

Fonte: Elaborado pelo autor (2026).

Na normalização Min-Max, calculada sobre as leituras dentro da faixa de
medição (sem os valores negativos e sem as saturações), o maior valor é um
pico falso de 43,6 mm/s. Com isso, todas as leituras ficam espremidas perto de zero, e até
a falha real vale só 0,36. No escore z geral, uma leitura normal em carga alta
parece um desvio (1,01), só porque esse regime vibra mais que a média. Na
padronização robusta por regime, que subtrai a mediana e divide pelo
intervalo interquartil (IQR) de cada regime, toda leitura normal fica perto
de zero, e a falha se destaca com 29,15.

A mediana e o IQR dessa escala são calculados sobre a série filtrada da
Etapa 6, que é a entrada dos modelos. Como o filtro reduz o ruído, o IQR fica
menor que o da série sem filtro: em carga alta, 0,35 mm/s, contra 0,63 mm/s
sem filtro, valor próximo do esperado para ruído normal com o desvio robusto
da Etapa 4 ($1{,}349 \times 0{,}48 \approx 0{,}65$). A falha não é suavizada e
por isso se destaca mais na escala da série filtrada; com o IQR da série sem
filtro, ela valeria cerca de 16.

Para evitar vazamento de dados [@kaufman2012], a divisão entre treino,
validação e teste segue a ordem do tempo (70%, 15% e 15%), e a mediana e o
IQR são calculados apenas no treino. Embaralhar as leituras antes de dividir
colocaria segundos vizinhos, quase iguais, no treino e no teste, e o modelo
pareceria melhor do que é.

## Etapa 8 — Validar o resultado

A última etapa verifica se os dados tratados ainda representam a máquina
[@ufjf2026unidade3]. A Tabela 7 compara os dados antes e depois do tratamento,
fora das trocas de regime. DP é o desvio-padrão, e P99 é o valor abaixo do qual
estão 99% das leituras.

: Vibração antes e depois do tratamento (mm/s).

| Regime | Média antes | Média depois | DP antes | DP depois | P99 antes | P99 depois |
|------------|-------:|-------:|-------:|-------:|-------:|-------:|
| Parada | 0,27 | 0,25 | 0,71 | 0,08 | 0,43 | 0,43 |
| Vazio | 1,64 | 1,60 | 1,12 | 0,18 | 2,05 | 2,04 |
| Carga | 3,81 | 3,78 | 1,05 | 0,34 | 4,60 | 4,57 |
| Carga alta | 5,85 | 5,81 | 1,45 | 1,04 | 12,90 | 12,64 |

Fonte: Elaborado pelo autor (2026).

A média quase não mudou, então o tratamento não deslocou o nível de operação.
O desvio-padrão caiu bastante porque os picos falsos foram removidos. Em carga
alta ele caiu menos, porque os eventos reais continuam nos dados. O P99 de
carga alta também continua em cerca de 12,6 mm/s pelo mesmo motivo: se ele
tivesse caído para perto de 6 mm/s, o tratamento teria apagado a falha. Por
fim, os resultados conferem com o que foi inserido: 180 duplicatas, 3 valores
negativos, 4 saturações, 36 leituras de picos falsos e 2 eventos preservados.

Com dados reais não existe gabarito. Nesse caso, a validação equivalente é
revisar com a equipe de manutenção os eventos encontrados, comparando-os com
as ordens de serviço e com o registro de operação da máquina.

## Auditoria do tratamento

Para que qualquer valor tratado possa ser explicado e refeito, o pipeline
guarda as informações da Tabela 8.

: Informações guardadas para auditoria.

| O que guardar | Para que serve |
|----------------------------------------------|----------------------------------------|
| Dado bruto, sem alteração | Refazer o tratamento desde a origem |
| Valores bruto, tratado e filtrado de cada leitura | Comparar cada transformação |
| *Flag* de cada leitura (ausente, inválida, saturada, pico falso, evento, preenchida, lacuna longa, transição) | Saber o que foi feito em cada ponto |
| Regime e escore $z$ de cada leitura | Explicar por que um ponto foi classificado |
| Parâmetros, com código de verificação (*hash*) e versão do script | Provar qual configuração gerou o resultado |
| *Hash* dos arquivos de entrada e semente do gerador sintético | Confirmar que o tratamento partiu dos mesmos dados |
| Parâmetros de escala calculados no treino | Aplicar a mesma escala aos dados novos |
| Contagens de cada etapa e lista de eventos | Acompanhar a qualidade e investigar eventos |

Fonte: Elaborado pelo autor (2026).

O script grava essas informações em quatro arquivos: as entradas brutas, como
foram recebidas (`entrada_vibracao.csv.gz` e `entrada_corrente.csv.gz`);
`serie_tratada.csv.gz`, com uma linha por segundo; e `auditoria.json`, com os
parâmetros, os *hashes* SHA-256 das entradas e do código, a semente do gerador
sintético (1322010), as contagens e os eventos. Com a mesma semente, o script
gera exatamente os mesmos dados, e os *hashes* confirmam isso. Por exemplo, o impacto real fica registrado assim no arquivo de
auditoria:

```text
{ "inicio": "2026-10-20 08:46:40", "duracao_s": 4,
  "pico_mm_s": 14.89, "z_vibracao_max": 19.2,
  "z_corrente_mediano": 9.8,
  "decisao": "preservado (persistente e corroborado pela corrente)" }
```

Com esse registro, qualquer pessoa consegue saber quando o evento aconteceu,
qual foi a sua intensidade e por que ele não foi removido. As contagens
também servem para acompanhar o sensor ao longo do tempo. Se a quantidade de
picos falsos dobrar de uma semana para outra, por exemplo, pode haver um
problema de cabo ou de aterramento.

## Onde executar cada etapa

Em um sistema IoT, o tratamento pode ser dividido entre o próprio sensor (a
borda), o *gateway* da fábrica e a nuvem [@shi2016]. Etapas simples e
urgentes ficam perto do sensor; etapas que precisam de histórico ficam na
nuvem (Tabela 9).

: Onde executar cada etapa do pipeline.

| Local | Etapas | Motivo |
|----------------|--------------------------------------------|--------------------------------------------|
| Sensor (borda) | Cálculo do valor RMS; marcação de valores negativos e saturados (Etapa 3) | Processa o sinal bruto em kHz; marca as leituras suspeitas, mas envia todas, sem descartar |
| *Gateway* | Duplicatas e grade de 1 s (Etapa 2); versão simplificada da Etapa 4; alarmes | Resposta rápida, mesmo sem conexão com a nuvem |
| Nuvem | Regimes, *outliers*, lacunas, filtragem, escala e validação (Etapas 1, 4 a 8), com o histórico completo; auditoria | Precisam de minutos ou horas de histórico e de outros sensores |

Fonte: Elaborado pelo autor, com base em @shi2016.

A versão simplificada da Etapa 4 no *gateway* evita que os alarmes disparem
nos picos falsos. Ela usa só leituras passadas: a mediana dos últimos
5 minutos e o desvio robusto de cada regime, calculado na nuvem e enviado ao
*gateway*. Uma leitura acima do limite gera alarme imediato se a corrente do
motor também reagir, sem cruzar um limite de regime. Se a corrente não reagir,
o alarme espera 4 s e só dispara se a vibração continuar alta, porque um pico
falso dura até 3 s.

As trocas de regime exigem uma regra própria. Na passagem de vazio para
carga, a vibração sobe de cerca de 1,6 para 3,8 mm/s, o que dá $|z| \approx 12$
contra o desvio robusto de vazio, e a corrente também muda. Sem essa regra,
toda troca de regime dispararia o alarme. Por isso, quando a corrente cruza um
limite de regime, o *gateway* passa a comparar a vibração com a mediana e o
desvio robusto do novo regime, já calculados pela nuvem, durante os 60 s da
janela de transição, e nessa janela a mudança da corrente não conta como
confirmação de falha. A nuvem refaz depois a Etapa 4 completa, com a janela
centrada, e é esse resultado que fica registrado na auditoria.
