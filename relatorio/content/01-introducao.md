# Introdução

Dados de sensores quase nunca chegam limpos. Falhas de comunicação,
interferência elétrica e retransmissões de mensagens geram lacunas, picos
falsos, ruído e registros duplicados. Se esses problemas não forem tratados,
qualquer análise feita depois herda os erros. Por outro lado, um tratamento
exagerado pode apagar justamente o evento que se queria detectar
[@ufjf2026unidade3].

A atividade da Unidade 3 descreve uma máquina industrial cujo sensor de
vibração apresenta:

- medições a cada segundo;
- cerca de 2% de valores ausentes;
- alguns picos extremamente elevados;
- ruído de alta frequência;
- diferentes períodos de operação da máquina.

A atividade pede uma sequência de pré-processamento que explique como tratar
os dados faltantes, como identificar *outliers*, que filtro usar, como saber
se um pico é falha real ou ruído, se é preciso normalizar ou padronizar e o
que guardar para permitir a auditoria do tratamento.

O objetivo deste relatório é propor essa sequência e mostrar que ela funciona.
Para isso, o pipeline foi implementado em Python e aplicado a dados sintéticos
com problemas conhecidos, de modo a conferir o que cada etapa remove, corrige
ou preserva.
