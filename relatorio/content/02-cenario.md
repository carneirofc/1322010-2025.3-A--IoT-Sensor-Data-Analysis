# Cenário e dados

## Hipóteses sobre o sensor

O enunciado não detalha o sensor, então foram adotadas as hipóteses abaixo:

- **Grandeza:** com uma leitura por segundo, o sensor não envia a forma de
  onda da vibração, que exigiria amostragem em kHz [@randall2011]. Ele envia
  um valor agregado: a velocidade de vibração RMS em mm/s, grandeza usada pela
  ISO 20816-3 [@iso20816-3].
- **Faixa de medição:** de 0 a 50 mm/s. Acima de 50 mm/s, o sensor satura e
  envia o código 65,5 mm/s. Valores negativos são impossíveis.
- **Transporte:** MQTT com QoS 1, que retransmite mensagens sem confirmação e
  por isso pode gerar duplicatas [@ufjf2026unidade3].
- **Sensor auxiliar:** a corrente do motor é medida no mesmo equipamento e
  indica em que regime a máquina está operando.

## Dados usados na demonstração

Como a atividade não fornece dados, foram geradas oito horas de leituras
sintéticas (28 800 instantes) com o pacote Python `analise/vibracao`. Os
dados reproduzem cada característica do enunciado e incluem dois eventos
reais, para verificar se o tratamento os preserva (Tabela 1). Como os
problemas foram inseridos de propósito, é possível conferir o resultado de
cada etapa.

: Problemas e eventos inseridos nos dados sintéticos.

| Característica | Como foi simulada | Quantidade |
|--------------------------|------------------------------------------------|----------------------:|
| Regimes de operação | Parada, vazio, carga e carga alta | 11 trechos |
| Ruído | Variação aleatória em todas as leituras | todas |
| Valores ausentes | Perdas isoladas (30 delas chegam como registro com valor vazio) e 4 quedas de conexão (30 a 60 s) | 575 (2,0%) |
| Picos falsos | Picos de 1 ou 2 leituras, de 18 a 45 mm/s | 33 picos (36 leituras) |
| Saturação | Leituras isoladas no fundo de escala (65,5 mm/s), sem reação da corrente | 4 |
| Valores negativos | Leituras de $-1$ mm/s | 3 |
| Duplicatas | Mensagens repetidas, fora de ordem | 180 |
| Variação no horário | Desvio de até 0,2 s no horário de cada leitura | todas |
| Impacto real | Choque de 4 s, também visto na corrente | 1 |
| Falha real | Vibração elevada por 150 s, também vista na corrente | 1 |

Fonte: Elaborado pelo autor (2026).

A Figura 1 mostra os dados brutos. Os picos falsos dominam o gráfico, enquanto
a falha real, menor, quase não aparece. A corrente do motor mostra os regimes
de operação e também reage aos dois eventos reais.

![Vibração bruta e corrente do motor nas oito horas simuladas, com os regimes de operação sombreados.](fig01-visao-geral.png){width=100%}

Fonte: Elaborado pelo autor (2026).
