"""Comparações citadas no relatório (detectores, preenchimento, filtros, escalas)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from vibracao.config import (
    EVENTO_REAL,
    FLAGS,
    IMPACTO_REAL,
    PARAMS,
    REGIME_NOME,
    REGIMES,
    SEED,
)


def comparar_filtros(out: pd.DataFrame) -> pd.DataFrame:
    """Redução de ruído em regime estável vs. preservação do pico do evento."""
    x = out["valor_tratado"]
    w = PARAMS["savgol_janela_s"]
    cands = {
        f"Média móvel ({w} s)": x.rolling(w, center=True, min_periods=1).mean(),
        f"Mediana móvel ({w} s)": x.rolling(w, center=True, min_periods=1).median(),
        "Suavização exponencial (α = 0,2)": x.ewm(alpha=0.2).mean(),
        f"Savitzky–Golay ({w} s, ordem 2)": out["valor_sg"],
        "Savitzky–Golay + proteção de eventos": out["valor_filtrado"],
    }
    ini, dur = EVENTO_REAL
    trecho = slice(16000, 17800)  # regime "carga" estável
    resid_bruto = (x - x.rolling(121, center=True).median()).iloc[trecho].std()
    linhas = []
    for nome, y in cands.items():
        resid = (y - x.rolling(121, center=True).median()).iloc[trecho].std()
        # Atraso: instante em que a saída cruza metade do degrau do evento.
        nivel0 = x.iloc[ini - 60:ini].median()
        nivel1 = x.iloc[ini + 40:ini + 100].median()
        meio = nivel0 + 0.5 * (nivel1 - nivel0)
        cruza = lambda s: int(np.argmax(s.iloc[ini - 10:ini + 60].to_numpy() > meio))
        i0, d0 = IMPACTO_REAL
        nivel = x.iloc[i0 - 60:i0].median()
        imp = slice(i0 - 5, i0 + d0 + 5)
        linhas.append({
            "Filtro": nome,
            "Redução do ruído (%)": round(100 * (1 - resid / resid_bruto), 1),
            "Amplitude do impacto preservada (%)": round(
                100 * (y.iloc[imp].max() - nivel) / (x.iloc[imp].max() - nivel), 1),
            "Atraso na subida da falha (s)": cruza(y) - cruza(x),
        })
    return pd.DataFrame(linhas), cands


def comparar_detectores(out: pd.DataFrame, verdade: dict) -> pd.DataFrame:
    """Etapa 4 — o que cada detector marca, comparado com o gabarito sintético."""
    x = out["valor_bruto"].where(out["valor_bruto"].between(*PARAMS["faixa_fisica_mm_s"])).to_numpy()
    valido = ~np.isnan(x)
    pico = np.zeros(len(x), bool)
    pico[verdade["picos"]] = True
    pico &= valido
    evento = np.zeros(len(x), bool)
    for a, d in (IMPACTO_REAL, EVENTO_REAL):
        evento[a:a + d] = True
    normal = valido & ~pico & ~evento
    q1, q3 = np.nanpercentile(x, [25, 75])
    metodos = {
        "Escore z global (|z| > 3)": np.abs((x - np.nanmean(x)) / np.nanstd(x)) > 3,
        "Regra do IQR global": (x < q1 - 1.5 * (q3 - q1)) | (x > q3 + 1.5 * (q3 - q1)),
        "Hampel por regime (|z| > 6)": np.abs(np.nan_to_num(out["z_robusto"].to_numpy())) > PARAMS["outlier_z_robusto"],
        "Hampel + corroboração (proposto)": (out["flags"].to_numpy() & FLAGS["ARTEFATO_PICO"]) > 0,
    }
    return pd.DataFrame([{
        "Método": nome,
        "Picos falsos encontrados": f"{int((m & pico).sum())} de {int(pico.sum())}",
        "Leituras normais marcadas": int((m & normal).sum()),
        "Leituras de eventos reais marcadas": f"{int((m & evento).sum())} de {int((evento & valido).sum())}",
    } for nome, m in metodos.items()])


def comparar_imputacao(out: pd.DataFrame) -> pd.DataFrame:
    """Etapa 5 — erro de cada método ao preencher lacunas criadas em trechos com valor conhecido."""
    rng = np.random.default_rng(SEED + 1)
    x = out["valor_tratado"].to_numpy()
    limpo = out["flags"].to_numpy() == 0
    reg = out["regime"].to_numpy()
    seg = out["segmento"].to_numpy()
    media_global = np.nanmean(x[limpo])
    media_reg = {r: np.nanmean(x[limpo & (reg == r)]) for r in REGIMES}
    ctx, n_amostras = 30, 300
    linhas = []
    for L in (1, 5, 30, 60):
        erros: dict[str, list[float]] = {}
        while len(erros.get("Linear", [])) < n_amostras:
            s = int(rng.integers(ctx, len(x) - L - ctx))
            j = slice(s - ctx, s + L + ctx)
            if not limpo[j].all() or seg[j].min() != seg[j].max() or reg[s] == "parada":
                continue
            w = pd.Series(x[j].copy())
            real = w.iloc[ctx:ctx + L].to_numpy().copy()
            w.iloc[ctx:ctx + L] = np.nan
            preds = {
                "Média geral": np.full(L, media_global),
                "Média do regime": np.full(L, media_reg[reg[s]]),
                "Último valor (LOCF)": w.ffill().iloc[ctx:ctx + L].to_numpy(),
                "Linear": w.interpolate().iloc[ctx:ctx + L].to_numpy(),
                "Spline cúbica": w.interpolate(method="cubicspline").iloc[ctx:ctx + L].to_numpy(),
            }
            for nome, p in preds.items():
                erros.setdefault(nome, []).append(float(np.mean(np.abs(p - real))))
        linhas.append({"Lacuna (s)": L, **{k: round(float(np.mean(v)), 2) for k, v in erros.items()}})
    return pd.DataFrame(linhas)


def lacuna_sobre_evento(out: pd.DataFrame) -> tuple[dict, dict]:
    """Etapa 5 — o que a imputação inventaria se uma queda de 60 s cobrisse o início da falha."""
    ini, _ = EVENTO_REAL
    a, b = ini - 20, ini + 40
    x = out["valor_tratado"]
    y = x.copy()
    y.iloc[a:b] = np.nan
    series = {"real": x.iloc[a - 60:b + 60], "linear": y.interpolate().iloc[a - 1:b + 1],
              "locf": y.ffill().iloc[a - 1:b + 1], "lacuna": (out.index[a], out.index[b - 1])}
    resumo = {
        "lacuna_s": b - a,
        "media_real_mm_s": round(float(x.iloc[a:b].mean()), 2),
        "media_linear_mm_s": round(float(series["linear"].iloc[1:-1].mean()), 2),
        "media_locf_mm_s": round(float(series["locf"].iloc[1:-1].mean()), 2),
    }
    return resumo, series


def comparar_escalas(out: pd.DataFrame, par: dict) -> pd.DataFrame:
    """Etapa 7 — a mesma leitura em mm/s e em três escalas diferentes."""
    bruto = out["valor_bruto"].where(out["valor_bruto"].between(*PARAMS["faixa_fisica_mm_s"]))
    mn, mx, mu, sd = bruto.min(), bruto.max(), bruto.mean(), bruto.std()
    limpo = out["flags"] == 0
    ini, dur = EVENTO_REAL
    leituras = [(f"Típica em {REGIME_NOME[r]}", r, float(out.loc[limpo & (out["regime"] == r), "valor_tratado"].median()))
                for r in ["vazio", "carga", "alta"]]
    leituras.append(("Pico da falha real", "alta", float(out["valor_tratado"].iloc[ini:ini + dur].max())))
    return pd.DataFrame([{
        "Leitura": nome,
        "mm/s": round(v, 2),
        "Min-Max geral": round((v - mn) / (mx - mn), 2),
        "Escore z geral": round((v - mu) / sd, 2),
        "Robusta por regime": round((v - par[r]["mediana"]) / max(par[r]["iqr"], 0.05), 2),
    } for nome, r, v in leituras])
