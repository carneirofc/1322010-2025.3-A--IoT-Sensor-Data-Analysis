"""Parâmetros do pipeline, flags e descrição do cenário sintético."""

import pandas as pd

SEED = 1322010
START = pd.Timestamp("2026-10-20 06:00:00")
DEVICE = "maq-07"
MEASUREMENT = "vib_rms_mm_s"

# Parâmetros do pipeline (registrados na auditoria).
PARAMS = {
    "faixa_fisica_mm_s": [0.0, 50.0],  # fundo de escala do sensor
    "flatline_janela_s": 60,
    "regime_corrente_limiares_A": [2.0, 12.0, 20.0],
    "regime_suavizacao_s": 15,
    "transiente_margem_s": 60,
    "outlier_janela_baseline_s": 301,
    "outlier_z_robusto": 6.0,
    "outlier_agrupamento_s": 5,
    "artefato_duracao_max_s": 3,
    "corroboracao_z_corrente": 3.0,
    "gap_interpolavel_max_s": 5,
    "savgol_janela_s": 11,
    "savgol_ordem": 2,
    "divisao_cronologica": [0.70, 0.15, 0.15],
}

# Flags por amostra (máscara de bits).
FLAGS = {
    "AUSENTE_ORIGINAL": 1,
    "FORA_DA_FAIXA": 2,
    "FLATLINE": 4,
    "ARTEFATO_PICO": 8,
    "EVENTO_CANDIDATO": 16,
    "IMPUTADO_LINEAR": 32,
    "LACUNA_LONGA": 64,
    "TRANSIENTE_REGIME": 128,
    "SATURADO": 256,
}

REGIMES = ["parada", "vazio", "carga", "alta"]
# Nomes dos regimes nas figuras e tabelas (os mesmos usados no texto do relatório).
REGIME_NOME = {"parada": "parada", "vazio": "vazio", "carga": "carga", "alta": "carga alta"}
VIB_NIVEL = {"parada": 0.25, "vazio": 1.6, "carga": 3.8, "alta": 5.6}
CORRENTE_NIVEL = {"parada": 0.0, "vazio": 7.5, "carga": 16.0, "alta": 23.0}
AGENDA = [
    ("parada", 1800), ("vazio", 1500), ("carga", 5400), ("alta", 3600),
    ("vazio", 900), ("parada", 1200), ("vazio", 600), ("carga", 6000),
    ("alta", 4200), ("vazio", 1200), ("parada", 2400),
]
EVENTO_REAL = (23000, 150)  # início (s) e duração (s) da falha simulada
IMPACTO_REAL = (10000, 4)  # choque mecânico curto, também visto na corrente
