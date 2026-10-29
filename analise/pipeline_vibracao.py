# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "pandas>=2.2", "scipy>=1.13", "matplotlib>=3.9"]
# ///
"""Pipeline de pré-processamento para o sensor de vibração (Atividade da Unidade 3).

Gera um conjunto sintético com as características do enunciado (1 amostra/s,
~2% de ausências, picos extremos, ruído de alta frequência e diferentes regimes
de operação), aplica o pipeline proposto no relatório e salva:

  relatorio/figures/*.png        figuras de dados do relatório (os diagramas, Figuras 2 e 3,
                                 vêm de relatorio/diagramas/*.dot e são gerados pelo build)
  analise/saida/serie_tratada.csv.gz   série com valor bruto, tratado e flags
  analise/saida/auditoria.json         parâmetros, hashes, contagens por etapa e eventos
  analise/saida/entrada_*.csv.gz       entradas brutas (vibração e corrente), como recebidas

Uso:  uv run analise/pipeline_vibracao.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "relatorio" / "figures"
OUT = ROOT / "analise" / "saida"

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
VIB_NIVEL = {"parada": 0.25, "vazio": 1.6, "carga": 3.8, "alta": 5.6}
CORRENTE_NIVEL = {"parada": 0.0, "vazio": 7.5, "carga": 16.0, "alta": 23.0}
AGENDA = [
    ("parada", 1800), ("vazio", 1500), ("carga", 5400), ("alta", 3600),
    ("vazio", 900), ("parada", 1200), ("vazio", 600), ("carga", 6000),
    ("alta", 4200), ("vazio", 1200), ("parada", 2400),
]
EVENTO_REAL = (23000, 150)  # início (s) e duração (s) da falha simulada
IMPACTO_REAL = (10000, 4)  # choque mecânico curto, também visto na corrente

# Paleta (categórica em ordem fixa; vermelho reservado para "descartado").
C_BRUTO = "#9a9890"
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
C_ERRO = "#e34948"
REGIME_FUNDO = {"parada": "#f1f0ec", "vazio": "#e4eef9", "carga": "#cfe1f5", "alta": "#b5d1f0"}
# Nomes dos regimes nas figuras (os mesmos usados no texto do relatório).
REGIME_NOME = {"parada": "parada", "vazio": "vazio", "carga": "carga", "alta": "carga alta"}
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


# ---------------------------------------------------------------------------
# Dados sintéticos
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Intervalos [ini, fim) onde mask é verdadeiro."""
    m = np.concatenate([[False], mask, [False]]).astype(int)
    d = np.diff(m)
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def pipeline(bruto: pd.DataFrame, corrente: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    log: dict = {"linhas_recebidas": len(bruto)}

    # Etapa 2 — estrutura: duplicatas, ordenação, grade temporal regular.
    chave = ["device_id", "measurement_id", "timestamp"]
    # Retransmissão QoS 1 repete a mesma mensagem: fica a primeira recebida.
    # Repetições com valor diferente não deveriam existir; são contadas.
    rep = bruto[bruto.duplicated(chave, keep=False)]
    log["duplicados_com_valor_diferente"] = int(rep.groupby(chave)["value"].nunique(dropna=False).gt(1).sum())
    df = bruto.drop_duplicates(subset=chave)
    log["duplicados_removidos"] = len(bruto) - len(df)
    df = df.sort_values("timestamp")
    df["t"] = df["timestamp"].dt.round("1s")
    # Jitter: duas leituras arredondadas para o mesmo segundo. A segunda vai
    # para o segundo vizinho (do lado do horário original) se ele estiver vazio;
    # senão, fica a primeira e a colisão é contada.
    colide = df.duplicated(subset=["device_id", "measurement_id", "t"])
    ocupados = set(df.loc[~colide, "t"])
    movidas = 0
    for i in df.index[colide]:
        viz = df.at[i, "t"] + pd.Timedelta(seconds=1 if df.at[i, "timestamp"] >= df.at[i, "t"] else -1)
        if viz not in ocupados:
            df.at[i, "t"] = viz
            ocupados.add(viz)
            movidas += 1
    colisoes = df.duplicated(subset=["device_id", "measurement_id", "t"]).sum()
    df = df.drop_duplicates(subset=["device_id", "measurement_id", "t"])
    log["leituras_movidas_para_segundo_vizinho"] = movidas
    log["colisoes_apos_arredondar"] = int(colisoes)
    grade = pd.date_range(START, periods=len(corrente), freq="1s")
    s = df.set_index("t")["value"].reindex(grade)
    out = pd.DataFrame({"valor_bruto": s})
    out.index.name = "timestamp"
    out["corrente_A"] = corrente.set_index("timestamp")["corrente_A"].reindex(grade).to_numpy()
    flags = np.zeros(len(out), np.int32)
    ausente = out["valor_bruto"].isna().to_numpy()
    flags[ausente] |= FLAGS["AUSENTE_ORIGINAL"]
    log["ausentes_na_grade"] = int(ausente.sum())
    log["taxa_ausencia"] = float(ausente.mean())

    # Etapa 3 — validade: valores negativos e sensor travado são erro.
    x = out["valor_bruto"].to_numpy().copy()
    lo, hi = PARAMS["faixa_fisica_mm_s"]
    fora = ~np.isnan(x) & (x < lo)
    flags[fora] |= FLAGS["FORA_DA_FAIXA"]
    x[fora] = np.nan
    log["fora_da_faixa"] = int(fora.sum())
    # Saturação: o valor real é maior ou igual ao fundo de escala (dado
    # censurado, não erro). Fica como 50 mm/s, marcado, e a Etapa 4 decide se
    # é pico falso ou evento, pelo mesmo teste de duração e corrente.
    sat = ~np.isnan(x) & (x > hi)
    flags[sat] |= FLAGS["SATURADO"]
    x[sat] = hi
    log["saturadas"] = int(sat.sum())
    w = PARAMS["flatline_janela_s"]
    travado = (pd.Series(x).rolling(w, min_periods=w).std() < 1e-6).to_numpy()
    flags[travado] |= FLAGS["FLATLINE"]
    x[travado] = np.nan
    log["flatline"] = int(travado.sum())

    # Etapa 1 — regimes de operação a partir da corrente do motor.
    i_suave = out["corrente_A"].rolling(PARAMS["regime_suavizacao_s"], center=True, min_periods=1).median()
    lim = PARAMS["regime_corrente_limiares_A"]
    reg_idx = np.digitize(i_suave.to_numpy(), lim)
    # Sequências curtas (< 60 s) são absorvidas pelo regime anterior.
    seg =np.cumsum(np.r_[0, reg_idx[1:] != reg_idx[:-1]])
    for sid in np.unique(seg):
        idx = np.flatnonzero(seg == sid)
        if idx.size < 60 and idx[0] > 0:
            reg_idx[idx] = reg_idx[idx[0] - 1]
    seg = np.cumsum(np.r_[0, reg_idx[1:] != reg_idx[:-1]])
    out["regime"] = np.array(REGIMES)[reg_idx]
    out["segmento"] = seg
    margem = PARAMS["transiente_margem_s"]
    trans = np.zeros(len(out), bool)
    for b in np.flatnonzero(np.diff(seg)) + 1:
        trans[max(0, b - margem // 3):b + margem] = True
    flags[trans] |= FLAGS["TRANSIENTE_REGIME"]
    log["segmentos"] = int(seg.max() + 1)

    # Etapa 4 — outliers: baseline robusta por segmento + desvio robusto
    # (1,4826 × MAD) fixo por regime.
    xs = pd.Series(x, index=out.index)
    janela = PARAMS["outlier_janela_baseline_s"]
    base = xs.groupby(seg).transform(lambda v: v.rolling(janela, center=True, min_periods=10).median())
    resid = xs - base
    estavel = ~trans
    mad = {r: 1.4826 * np.nanmedian(np.abs(resid[(out["regime"] == r).to_numpy() & estavel]))
           for r in REGIMES}
    escala = out["regime"].map(mad).to_numpy()
    escala = np.maximum(escala, 0.05)  # piso: regime "parada" quase sem variação
    z = (resid / escala).to_numpy()
    zk = PARAMS["outlier_z_robusto"]
    cand = np.nan_to_num(np.abs(z)) > zk

    ci = out["corrente_A"]
    base_i = ci.groupby(seg).transform(lambda v: v.rolling(janela, center=True, min_periods=10).median())
    mad_i = 1.4826 * np.nanmedian(np.abs((ci - base_i)[estavel & (out["regime"] != "parada").to_numpy()]))
    z_i = ((ci - base_i) / mad_i).to_numpy()

    # Candidatos separados por até `agrupar` s formam um único episódio.
    agrupar = PARAMS["outlier_agrupamento_s"]
    unido = cand.copy()
    for a, b in runs(~cand):
        if 0 < a and b < len(cand) and b - a <= agrupar:
            unido[a:b] = True
    eventos, artefatos, em_transiente = [], 0, 0
    for a, b in runs(unido):
        dur = b - a
        z_cor = float(np.nanmedian(np.abs(z_i[a:b][cand[a:b]])))
        corroborado = z_cor > PARAMS["corroboracao_z_corrente"]
        if dur <= PARAMS["artefato_duracao_max_s"] and not corroborado:
            m = np.arange(a, b)[cand[a:b]]
            flags[m] |= FLAGS["ARTEFATO_PICO"]
            x[m] = np.nan
            artefatos += int(m.size)
        elif trans[a:b].any():
            # Partida/parada: o desvio vem da mudança de regime, não de falha.
            em_transiente += 1
        else:
            # Estende a marcação às bordas de subida/descida do evento.
            a2, b2 = max(0, a - 30), min(len(x), b + 30)
            flags[a2:b2] |= FLAGS["EVENTO_CANDIDATO"]
            eventos.append({
                "inicio": str(out.index[a]), "duracao_s": int(dur),
                "pico_mm_s": round(float(np.nanmax(x[a:b])), 2),
                "z_vibracao_max": round(float(np.nanmax(np.abs(z[a:b]))), 1),
                "z_corrente_mediano": round(z_cor, 1),
                "decisao": "preservado (persistente e corroborado pela corrente)",
            })
    log["amostras_artefato"] = artefatos
    sat_removidas = int((((flags & FLAGS["SATURADO"]) > 0) & ((flags & FLAGS["ARTEFATO_PICO"]) > 0)).sum())
    log["saturadas_removidas_como_pico_falso"] = sat_removidas
    log["picos_falsos_removidos"] = artefatos - sat_removidas
    log["candidatos_em_transiente"] = em_transiente
    log["eventos_preservados"] = eventos
    log["desvio_robusto_por_regime_mm_s"] = {k: round(float(v), 3) for k, v in mad.items()}

    # Etapa 5 — dados faltantes: interpolação linear só em lacunas curtas,
    # dentro do mesmo segmento e do mesmo conjunto (treino/validação/teste);
    # lacunas longas permanecem marcadas.
    nan = np.isnan(x)
    gmax = PARAMS["gap_interpolavel_max_s"]
    interp = pd.Series(x).groupby(seg).transform(lambda v: v.interpolate(limit_area="inside")).to_numpy()
    n = len(x)
    conj = np.searchsorted([int(0.70 * n), int(0.85 * n)], np.arange(n), side="right")
    lacunas = {"curtas": 0, "longas": 0, "amostras_imputadas": 0, "amostras_lacuna_longa": 0}
    for a, b in runs(nan):
        mesmo_seg = a > 0 and b < n and seg[a - 1] == seg[b] and conj[a - 1] == conj[b]
        if b - a <= gmax and mesmo_seg:
            x[a:b] = interp[a:b]
            flags[a:b] |= FLAGS["IMPUTADO_LINEAR"]
            lacunas["curtas"] += 1
            lacunas["amostras_imputadas"] += int(b - a)
        else:
            flags[a:b] |= FLAGS["LACUNA_LONGA"]
            lacunas["longas"] += 1
            lacunas["amostras_lacuna_longa"] += int(b - a)
    log["lacunas"] = lacunas
    out["valor_tratado"] = x

    # Mecanismo de ausência: taxa por regime (MCAR esperado ≈ uniforme).
    log["taxa_ausencia_por_regime"] = {
        r: round(float(ausente[(out["regime"] == r).to_numpy()].mean()), 4) for r in REGIMES}

    # Etapa 6 — filtragem (Savitzky–Golay por trecho contínuo do segmento).
    filt = np.full_like(x, np.nan)
    wl, po = PARAMS["savgol_janela_s"], PARAMS["savgol_ordem"]
    ok = ~np.isnan(x)
    for a, b in runs(ok):
        # Não atravessa fronteiras de segmento.
        cortes = [a] + [k for k in range(a + 1, b) if seg[k] != seg[k - 1]] + [b]
        for c0, c1 in zip(cortes[:-1], cortes[1:]):
            filt[c0:c1] = savgol_filter(x[c0:c1], wl, po) if c1 - c0 >= wl else x[c0:c1]
    out["valor_sg"] = filt
    # Janelas marcadas como evento não são suavizadas: o pico é a informação.
    protegido = (flags & FLAGS["EVENTO_CANDIDATO"]) > 0
    out["valor_filtrado"] = np.where(protegido, x, filt)

    out["flags"] = flags
    out["flags_txt"] = [
        "|".join(k for k, v in FLAGS.items() if f & v) for f in flags]
    out["z_robusto"] = np.round(z, 2)
    return out, log


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


def escalonar(out: pd.DataFrame) -> dict:
    """Etapa 7 — divisão cronológica 70/15/15 e escala robusta por regime (fit só no treino)."""
    n = len(out)
    a, b = int(0.70 * n), int(0.85 * n)
    conj = np.array(["treino"] * a + ["validacao"] * (b - a) + ["teste"] * (n - b))
    x = out["valor_filtrado"]
    treino = out.iloc[:a]
    # Saturadas valem "pelo menos 50 mm/s": não entram no ajuste como valor exato.
    exato = ((treino["flags"] & FLAGS["SATURADO"]) == 0).to_numpy()
    par = {}
    for r in REGIMES:
        v = x.iloc[:a][(treino["regime"] == r).to_numpy() & exato].dropna()
        q1, med, q3 = np.percentile(v, [25, 50, 75])
        par[r] = {"mediana": round(float(med), 3), "iqr": round(float(q3 - q1), 3)}
    med = out["regime"].map({k: v["mediana"] for k, v in par.items()})
    iqr = out["regime"].map({k: max(v["iqr"], 0.05) for k, v in par.items()})
    out["valor_escalonado"] = (x - med) / iqr
    out["conjunto"] = conj

    # Contra-exemplo: Min-Max ajustado no conjunto completo com picos espúrios.
    bruto = out["valor_bruto"].where(out["valor_bruto"].between(*PARAMS["faixa_fisica_mm_s"]))
    mm = (bruto - bruto.min()) / (bruto.max() - bruto.min())
    return {
        "parametros_por_regime_treino": par,
        "minmax_bruto_p99": round(float(mm.quantile(0.99)), 3),
        "minmax_bruto_max_valido": round(float(bruto.max()), 2),
        "escalonado_evento_max": round(float(out["valor_escalonado"].iloc[EVENTO_REAL[0]:sum(EVENTO_REAL)].max()), 1),
        "evento_no_conjunto": str(conj[EVENTO_REAL[0]]),
    }


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


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------
def sombrear_regimes(ax, out: pd.DataFrame) -> None:
    for sid, g in out.groupby("segmento"):
        ax.axvspan(g.index[0], g.index[-1], color=REGIME_FUNDO[g["regime"].iloc[0]], lw=0, zorder=0)


def fmt_tempo(ax, fmt="%H:%M", maxticks=6) -> None:
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=maxticks))
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))


def fig_visao_geral(out: pd.DataFrame) -> None:
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
    fig.savefig(FIG / "fig01-visao-geral.png")
    plt.close(fig)


def fig_outliers(out: pd.DataFrame) -> None:
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
    fig.savefig(FIG / "fig04-outliers.png")
    plt.close(fig)


def fig_lacunas(out: pd.DataFrame) -> None:
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
    fig.savefig(FIG / "fig06-lacunas.png")
    plt.close(fig)


def fig_filtros(out: pd.DataFrame, cands: dict) -> None:
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
    fig.savefig(FIG / "fig07-filtros.png")
    plt.close(fig)


def fig_lacuna_evento(series: dict) -> None:
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
    fig.savefig(FIG / "fig05-lacuna-evento.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    bruto, corrente, gabarito, verdade = gerar_dados(rng)
    out, log = pipeline(bruto, corrente)
    tab_filtros, cands = comparar_filtros(out)
    log["escalonamento"] = escalonar(out)
    tab_detectores = comparar_detectores(out, verdade)
    tab_imputacao = comparar_imputacao(out)
    log["lacuna_sobre_evento"], serie_lacuna = lacuna_sobre_evento(out)
    tab_escalas = comparar_escalas(out, log["escalonamento"]["parametros_por_regime_treino"])

    # Etapa 8 — validação: estatísticas por regime antes e depois.
    estat = []
    for r in REGIMES:
        m = (out["regime"] == r) & ((out["flags"] & (FLAGS["TRANSIENTE_REGIME"] | FLAGS["SATURADO"])) == 0)
        b = out.loc[m, "valor_bruto"].where(lambda v: v.between(0, 50))
        t = out.loc[m, "valor_tratado"]
        f = out.loc[m, "valor_filtrado"]
        estat.append({
            "regime": r, "n": int(m.sum()),
            "media_bruto": round(b.mean(), 3), "media_tratado": round(t.mean(), 3),
            "dp_bruto": round(b.std(), 3), "dp_tratado": round(t.std(), 3), "dp_filtrado": round(f.std(), 3),
            "p99_bruto": round(b.quantile(0.99), 2), "p99_tratado": round(t.quantile(0.99), 2),
        })
    log["validacao_por_regime"] = estat
    log["filtros"] = tab_filtros.to_dict(orient="records")
    log["detectores"] = tab_detectores.to_dict(orient="records")
    log["imputacao_erro_medio_mm_s"] = tab_imputacao.to_dict(orient="records")
    log["escalas"] = tab_escalas.to_dict(orient="records")
    log["gabarito_sintetico"] = gabarito

    out.to_csv(OUT / "serie_tratada.csv.gz", float_format="%.4f")
    # Entradas brutas guardadas como chegaram; o hash é do CSV sem compressão
    # (o gzip grava a data do arquivo, o que mudaria o hash a cada execução).
    entradas = {}
    for nome, tab in [("entrada_vibracao.csv.gz", bruto), ("entrada_corrente.csv.gz", corrente)]:
        tab.to_csv(OUT / nome, index=False)
        entradas[nome] = hashlib.sha256(tab.to_csv(index=False).encode()).hexdigest()
    params_txt = json.dumps(PARAMS, sort_keys=True)
    auditoria = {
        "pipeline_versao": "1.1.1",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fonte": {"device_id": DEVICE, "measurement_id": MEASUREMENT, "seed": SEED,
                  "entradas_sha256": entradas},
        "parametros": PARAMS,
        "parametros_sha256": hashlib.sha256(params_txt.encode()).hexdigest(),
        "flags": FLAGS,
        "contagens": log,
    }
    (OUT / "auditoria.json").write_text(json.dumps(auditoria, indent=2, ensure_ascii=False, default=str))

    fig_visao_geral(out)
    fig_outliers(out)
    fig_lacunas(out)
    fig_filtros(out, cands)
    fig_lacuna_evento(serie_lacuna)

    print(json.dumps(auditoria, indent=2, ensure_ascii=False, default=str))
    for tab in (tab_filtros, tab_detectores, tab_imputacao, tab_escalas):
        print(tab.to_string(index=False))


if __name__ == "__main__":
    main()
