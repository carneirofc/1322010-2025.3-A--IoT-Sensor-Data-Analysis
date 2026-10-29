"""Etapas 1 a 8 do pipeline de pré-processamento."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

from vibracao.config import EVENTO_REAL, FLAGS, PARAMS, REGIMES, START


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


def validar(out: pd.DataFrame) -> list[dict]:
    """Etapa 8 — validação: estatísticas por regime antes e depois."""
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
    return estat
