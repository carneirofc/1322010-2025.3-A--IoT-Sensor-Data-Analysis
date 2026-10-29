"""Gerador do conjunto sintético (vibração + corrente do motor)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from vibracao.config import (
    AGENDA,
    CORRENTE_NIVEL,
    DEVICE,
    EVENTO_REAL,
    IMPACTO_REAL,
    MEASUREMENT,
    SEED,
    START,
    VIB_NIVEL,
)


def gerar_dados(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    """Retorna (vibração bruta como chega da ingestão, corrente do motor, gabarito, verdade).

    `verdade` guarda os índices dos picos espúrios, usados para avaliar os detectores.
    """
    regime = np.concatenate([[r] * d for r, d in AGENDA])
    n = regime.size
    t = np.arange(n)

    def resposta_1a_ordem(alvo: np.ndarray, tau: float) -> np.ndarray:
        y = np.empty_like(alvo)
        y[0] = alvo[0]
        a = 1.0 / tau
        for i in range(1, alvo.size):
            y[i] = y[i - 1] + a * (alvo[i] - y[i - 1])
        return y

    vib = resposta_1a_ordem(np.array([VIB_NIVEL[r] for r in regime]), tau=20.0)
    cor = resposta_1a_ordem(np.array([CORRENTE_NIVEL[r] for r in regime]), tau=8.0)

    # Falha real: elevação sustentada da vibração acompanhada pela corrente.
    ini, dur = EVENTO_REAL
    forma = np.zeros(n)
    sub, desce = 20, 30
    forma[ini:ini + sub] = np.linspace(0, 1, sub)
    forma[ini + sub:ini + dur - desce] = 1.0
    forma[ini + dur - desce:ini + dur] = np.linspace(1, 0, desce)
    vib += 7.0 * forma
    cor += 3.5 * forma
    i0, d0 = IMPACTO_REAL
    vib[i0:i0 + d0] += np.array([6.0, 9.0, 8.0, 4.0])
    cor[i0:i0 + d0] += np.array([3.0, 4.5, 4.0, 2.0])

    # Deriva térmica lenta + ruído de alta frequência (heteroscedástico).
    vib *= 1 + 0.04 * np.sin(2 * np.pi * t / 7200)
    vib += rng.normal(0, 0.06 + 0.07 * vib)
    vib = np.clip(vib, 0.02, None)
    cor += rng.normal(0, 0.35, n) * (cor > 0.5)
    cor = np.clip(cor, 0, None)

    proibido = np.zeros(n, bool)
    proibido[ini - 30:ini + dur + 30] = True
    proibido[i0 - 30:i0 + d0 + 30] = True

    def sortear(k: int) -> np.ndarray:
        livres = np.flatnonzero(~proibido)
        idx = rng.choice(livres, k, replace=False)
        proibido[idx] = True
        return np.sort(idx)

    # Picos espúrios (interferência elétrica): 1 ou 2 amostras, sem reflexo na corrente.
    picos = sortear(30)
    vib[picos] = rng.uniform(18, 45, picos.size)
    picos2 = sortear(3)
    vib[picos2] = rng.uniform(20, 40, 3)
    vib[np.minimum(picos2 + 1, n - 1)] = rng.uniform(20, 40, 3)
    proibido[np.minimum(picos2 + 1, n - 1)] = True
    # Valores fisicamente impossíveis: saturação do ADC e leituras negativas.
    sat = sortear(4)
    vib[sat] = 65.535
    neg = sortear(3)
    vib[neg] = -1.0

    # Ausências: isoladas (perda de pacote) + rajadas (queda de enlace).
    rajadas = [(5200, 45), (11800, 60), (16900, 30), (26900, 40)]
    ausente = np.zeros(n, bool)
    for a, d in rajadas:
        ausente[a:a + d] = True
        proibido[a:a + d] = True
    isoladas = sortear(400)
    campo_vazio = isoladas[:30]  # chegam como registro com campo vazio
    ausente[isoladas[30:]] = True

    ts = START + pd.to_timedelta(t, unit="s") + pd.to_timedelta(rng.normal(0, 60, n).clip(-200, 200), unit="ms")
    valor = vib.copy()
    valor[campo_vazio] = np.nan
    bruto = pd.DataFrame({
        "device_id": DEVICE,
        "measurement_id": MEASUREMENT,
        "timestamp": ts,
        "value": valor,
    })[~ausente]

    # Retransmissões MQTT QoS 1: mesmos campos, chegam fora de ordem.
    dup = bruto.sample(180, random_state=SEED)
    bruto = pd.concat([bruto, dup])
    ordem = np.arange(len(bruto)) + rng.normal(0, 3, len(bruto))
    bruto = bruto.iloc[np.argsort(ordem)].reset_index(drop=True)

    corrente = pd.DataFrame({"timestamp": START + pd.to_timedelta(t, unit="s"), "corrente_A": cor})
    gabarito = {
        "picos_espurios": int(picos.size + 2 * picos2.size),
        "fora_da_faixa": int(sat.size + neg.size),
        "ausentes": int(ausente.sum() + campo_vazio.size),
        "duplicados": 180,
        "evento_real_inicio": str(START + pd.Timedelta(seconds=ini)),
    }
    verdade = {"picos": np.unique(np.concatenate([picos, picos2, np.minimum(picos2 + 1, n - 1)]))}
    return bruto, corrente, gabarito, verdade
