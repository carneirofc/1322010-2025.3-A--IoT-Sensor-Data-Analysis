"""Figuras de dados do relatório (fig01, fig04 a fig07)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from vibracao.config import (
    EVENTO_REAL,
    FLAGS,
    IMPACTO_REAL,
    PARAMS,
    REGIME_NOME,
    REGIMES,
)
from vibracao.pipeline import runs

# Paleta (categórica em ordem fixa; vermelho reservado para "descartado").
C_BRUTO = "#9a9890"
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
C_ERRO = "#e34948"
REGIME_FUNDO = {"parada": "#f1f0ec", "vazio": "#e4eef9", "carga": "#cfe1f5", "alta": "#b5d1f0"}
INK, INK2 = "#0b0b0b", "#52514e"

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.edgecolor": INK2,
    "axes.labelcolor": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#e2e1dc",
    "grid.linewidth": 0.6,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "legend.frameon": False,
    "lines.linewidth": 1.0,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
})


def sombrear_regimes(ax, out: pd.DataFrame) -> None:
    for sid, g in out.groupby("segmento"):
        ax.axvspan(g.index[0], g.index[-1], color=REGIME_FUNDO[g["regime"].iloc[0]], lw=0, zorder=0)


def fmt_tempo(ax, fmt="%H:%M", maxticks=6) -> None:
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=maxticks))
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))


def fig_visao_geral(out: pd.DataFrame, destino: Path) -> None:
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 4.4), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    for ax in (a1, a2):
        sombrear_regimes(ax, out)
    a1.plot(out.index, out["valor_bruto"].clip(-2, 70), color=C1, lw=0.4)
    a1.axhline(PARAMS["faixa_fisica_mm_s"][1], color=C_ERRO, lw=0.8, ls="--")
    a1.text(out.index[150], 51.5, "fundo de escala (50 mm/s)", color=INK2, fontsize=7)
    a1.set_ylabel("Vibração RMS (mm/s)")
    a1.set_title("Vibração bruta (1 leitura/s)", loc="left", fontsize=9, color=INK)
    ini = out.index[EVENTO_REAL[0]]
    a1.annotate("falha real", (ini, 14), (ini - pd.Timedelta(minutes=95), 30), fontsize=7.5, color=INK,
                arrowprops={"arrowstyle": "->", "color": INK2, "lw": 0.8})
    a2.plot(out.index, out["corrente_A"], color=C2, lw=0.5)
    a2.set_ylabel("Corrente (A)")
    a2.set_title("Corrente do motor (sensor auxiliar)", loc="left", fontsize=9, color=INK)
    fmt_tempo(a2)
    handles = [plt.Rectangle((0, 0), 1, 1, color=REGIME_FUNDO[r]) for r in REGIMES]
    a1.legend(handles, [f"regime: {REGIME_NOME[r]}" for r in REGIMES], ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, 1.28), fontsize=7.5)
    fig.savefig(destino / "fig01-visao-geral.png")
    plt.close(fig)


def fig_outliers(out: pd.DataFrame, destino: Path) -> None:
    art = np.flatnonzero(out["flags"].to_numpy() & FLAGS["ARTEFATO_PICO"])
    # Artefato isolado longe de transientes, dentro do regime "alta".
    alta = out["regime"].to_numpy() == "alta"
    alvo = next(i for i in art if alta[i] and i > 10000)
    jan_a = slice(alvo - 120, alvo + 120)
    ini, dur = EVENTO_REAL
    jan_e = slice(ini - 200, ini + dur + 200)
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.8), sharey=True)
    for ax, jan, tit in [(axs[0], jan_a, "(a) Pico falso: 1 leitura, corrente estável"),
                         (axs[1], jan_e, "(b) Falha real: 150 s, corrente acompanha")]:
        o = out.iloc[jan]
        ax.plot(o.index, o["valor_bruto"], color=C_BRUTO, lw=0.7, label="bruto")
        ax.plot(o.index, o["valor_tratado"], color=C1, lw=1.0, label="tratado")
        m = (o["flags"] & FLAGS["ARTEFATO_PICO"]) > 0
        ax.scatter(o.index[m], o["valor_bruto"][m], s=22, marker="x", color=C_ERRO, zorder=5,
                   label="pico falso (removido)")
        e = (o["flags"] & FLAGS["EVENTO_CANDIDATO"]) > 0
        if e.any():
            ax.axvspan(o.index[e][0], o.index[e][-1], color="#fbdccb", zorder=0, label="evento preservado")
        ax.set_title(tit, loc="left", fontsize=8.5)
        fmt_tempo(ax, "%H:%M")
        ax2 = ax.inset_axes([0, -0.42, 1, 0.25], sharex=ax)
        ax2.plot(o.index, o["corrente_A"], color=C2, lw=0.8)
        ax2.tick_params(labelsize=6.5)
        ax2.grid(True)
        ax.tick_params(labelbottom=False)
        fmt_tempo(ax2, "%H:%M")
    axs[0].set_ylabel("Vibração RMS (mm/s)")
    axs[0].text(-0.13, -0.3, "Corrente\n(A)", transform=axs[0].transAxes, fontsize=7, ha="center", va="center")
    h1, l1 = axs[0].get_legend_handles_labels()
    h2, l2 = axs[1].get_legend_handles_labels()
    extra = [(h, l) for h, l in zip(h2, l2) if l not in l1]
    fig.legend(h1 + [h for h, _ in extra], l1 + [l for _, l in extra], ncol=4, fontsize=7,
               loc="upper center", bbox_to_anchor=(0.5, 1.06))
    fig.subplots_adjust(bottom=0.32, wspace=0.12)
    fig.savefig(destino / "fig04-outliers.png")
    plt.close(fig)


def fig_lacunas(out: pd.DataFrame, destino: Path) -> None:
    f = out["flags"].to_numpy()
    imp = np.flatnonzero(f & FLAGS["IMPUTADO_LINEAR"])
    carga = out["regime"].to_numpy() == "carga"
    # Uma lacuna curta de 2+ amostras no regime "carga".
    blocos = [(a, b) for a, b in runs((f & FLAGS["IMPUTADO_LINEAR"]) > 0) if b - a >= 2 and carga[a]]
    a, b = blocos[0] if blocos else (imp[0], imp[0] + 1)
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.5), sharey=False)
    for ax, (c, tit) in zip(axs, [((a + b) // 2, f"(a) Lacuna curta ({b - a} s): preenchida"),
                                   (11800 + 30, "(b) Lacuna longa (60 s): mantida e marcada")]):
        o = out.iloc[c - 45:c + 45]
        ax.plot(o.index, o["valor_bruto"].where(o["valor_bruto"] < 50), color=C_BRUTO, lw=0.8, marker="o",
                ms=2.2, label="bruto")
        m = (o["flags"] & FLAGS["IMPUTADO_LINEAR"]) > 0
        ax.scatter(o.index[m], o["valor_tratado"][m], s=26, color=C3, zorder=5, label="preenchido (linear)")
        ml = (o["flags"] & FLAGS["LACUNA_LONGA"]) > 0
        if ml.any():
            ax.axvspan(o.index[ml][0], o.index[ml][-1], color="#ececea", zorder=0, label="lacuna longa (ausente)")
        ax.set_title(tit, loc="left", fontsize=8.5)
        fmt_tempo(ax, "%H:%M:%S", maxticks=4)
        ax.tick_params(axis="x", labelsize=7)
        ax.legend(fontsize=7, loc="lower left")
    axs[0].set_ylabel("Vibração RMS (mm/s)")
    fig.savefig(destino / "fig06-lacunas.png")
    plt.close(fig)


def fig_filtros(out: pd.DataFrame, cands: dict, destino: Path) -> None:
    i0, d0 = IMPACTO_REAL
    ini, _ = EVENTO_REAL
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.0), gridspec_kw={"width_ratios": [1, 1.4]})
    cores = [C1, C2, C4, C3]
    for ax, jan, tit in [(axs[0], slice(i0 - 25, i0 + 30), "(a) Impacto real de 4 s"),
                         (axs[1], slice(ini - 60, ini + 90), "(b) Início da falha de 150 s")]:
        o = out.iloc[jan]
        ax.plot(o.index, o["valor_tratado"], color=C_BRUTO, lw=0.8, marker="o", ms=1.6,
                label="tratado (sem filtro)")
        for (nome, y), c in zip(list(cands.items())[:4], cores):
            ax.plot(o.index, y.iloc[jan], color=c, lw=1.3 if "Savitzky" in nome else 1.0, label=nome)
        ax.set_title(tit, loc="left", fontsize=8.5)
        fmt_tempo(ax, "%H:%M:%S", maxticks=4)
        ax.tick_params(axis="x", labelsize=7)
    axs[0].set_ylabel("Vibração RMS (mm/s)")
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, ncol=3, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, 1.1))
    fig.savefig(destino / "fig07-filtros.png")
    plt.close(fig)


def fig_lacuna_evento(series: dict, destino: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    a, b = series["lacuna"]
    ax.axvspan(a, b, color="#ececea", zorder=0, label="lacuna criada para o teste (60 s)")
    ax.plot(series["real"].index, series["real"], color=C_BRUTO, lw=0.8, label="valor real")
    ax.plot(series["linear"].index, series["linear"], color=C1, lw=1.6, label="preenchido por interpolação linear")
    ax.plot(series["locf"].index, series["locf"], color=C2, lw=1.6, label="preenchido com o último valor (LOCF)")
    ax.set_ylabel("Vibração RMS (mm/s)")
    fmt_tempo(ax, "%H:%M:%S", maxticks=5)
    ax.tick_params(axis="x", labelsize=7)
    ax.legend(fontsize=7, loc="upper left")
    fig.savefig(destino / "fig05-lacuna-evento.png")
    plt.close(fig)
