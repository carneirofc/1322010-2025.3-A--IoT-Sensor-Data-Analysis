# Análise de Dados de Dispositivos IoT e de Sensores — Unidade 3

Atividade da Unidade 3 (pré-processamento) da disciplina 1322010-2025.3-A, UFJF.
Propõe um pipeline de pré-processamento para um sensor de vibração industrial
(1 leitura/s, ausências, picos falsos, ruído e vários regimes de operação) e o
demonstra com dados sintéticos.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `analise/vibracao/` | Pacote Python: gerador sintético, pipeline (Etapas 1–8), comparações e figuras |
| `analise/saida/` | Saídas geradas: entradas brutas, série tratada e `auditoria.json` |
| `relatorio/` | Relatório técnico (Markdown → PDF/DOCX, ABNT); ver `relatorio/README.md` |

## Gerar os dados e as figuras

Requer [uv](https://docs.astral.sh/uv/). Na raiz do repositório:

```bash
uv run vibracao
```

O resultado é determinístico (semente fixa). Grava as figuras de dados em
`relatorio/figures/` e as saídas em `analise/saida/`; as pastas podem ser
trocadas com `--figuras` e `--saida`.

Também é possível instalar o comando:

```bash
uv tool install .
vibracao --help
```

## Gerar o relatório

```bash
make -C relatorio        # relatorio/build/relatorio.pdf e relatorio.docx
```

Usa `pandoc`, `lualatex` e Graphviz locais quando existem; senão, roda em um
contêiner (podman ou docker).

## Como citar

O relatório cita o pacote pela versão marcada com a *tag* `v1.2.0` (ABNT NBR 6023):

> CARNEIRO, Claudio Ferreira. **vibracao**: pacote Python de pré-processamento
> de dados de um sensor de vibração industrial. Versão 1.2.0. [S.l.]: GitHub,
> 2026. Disponível em:
> <https://github.com/carneirofc/1322010-2025.3-A--IoT-Sensor-Data-Analysis/tree/v1.2.0>.
> Acesso em: 29 out. 2026.

A entrada BibTeX está em `relatorio/bib/references.bib` (`carneiro2026vibracao`).
A versão do pacote (`pyproject.toml`), o campo `pipeline_versao` de
`analise/saida/auditoria.json` e a *tag* devem ser iguais.
