"""Linha de comando: gera os dados, roda o pipeline e grava saídas e figuras."""

from __future__ import annotations

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import numpy as np

from vibracao import figuras
from vibracao.comparacoes import (
    comparar_detectores,
    comparar_escalas,
    comparar_filtros,
    comparar_imputacao,
    lacuna_sobre_evento,
)
from vibracao.config import DEVICE, FLAGS, MEASUREMENT, PARAMS, SEED
from vibracao.dados import gerar_dados
from vibracao.pipeline import escalonar, pipeline, validar


def hash_codigo() -> str:
    """SHA-256 dos módulos do pacote (nome + conteúdo, em ordem alfabética)."""
    h = hashlib.sha256()
    for f in sorted(Path(__file__).parent.glob("*.py")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(prog="vibracao", description=__doc__)
    ap.add_argument("--figuras", type=Path, default=Path("relatorio/figures"),
                    help="pasta das figuras (padrão: %(default)s)")
    ap.add_argument("--saida", type=Path, default=Path("analise/saida"),
                    help="pasta dos dados e da auditoria (padrão: %(default)s)")
    args = ap.parse_args()
    fig_dir, saida = args.figuras, args.saida

    fig_dir.mkdir(parents=True, exist_ok=True)
    saida.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    bruto, corrente, gabarito, verdade = gerar_dados(rng)
    out, log = pipeline(bruto, corrente)
    tab_filtros, cands = comparar_filtros(out)
    log["escalonamento"] = escalonar(out)
    tab_detectores = comparar_detectores(out, verdade)
    tab_imputacao = comparar_imputacao(out)
    log["lacuna_sobre_evento"], serie_lacuna = lacuna_sobre_evento(out)
    tab_escalas = comparar_escalas(out, log["escalonamento"]["parametros_por_regime_treino"])

    log["validacao_por_regime"] = validar(out)
    log["filtros"] = tab_filtros.to_dict(orient="records")
    log["detectores"] = tab_detectores.to_dict(orient="records")
    log["imputacao_erro_medio_mm_s"] = tab_imputacao.to_dict(orient="records")
    log["escalas"] = tab_escalas.to_dict(orient="records")
    log["gabarito_sintetico"] = gabarito

    out.to_csv(saida / "serie_tratada.csv.gz", float_format="%.4f")
    # Entradas brutas guardadas como chegaram; o hash é do CSV sem compressão
    # (o gzip grava a data do arquivo, o que mudaria o hash a cada execução).
    entradas = {}
    for nome, tab in [("entrada_vibracao.csv.gz", bruto), ("entrada_corrente.csv.gz", corrente)]:
        tab.to_csv(saida / nome, index=False)
        entradas[nome] = hashlib.sha256(tab.to_csv(index=False).encode()).hexdigest()
    params_txt = json.dumps(PARAMS, sort_keys=True)
    auditoria = {
        "pipeline_versao": version("vibracao"),
        "codigo_sha256": hash_codigo(),
        "fonte": {"device_id": DEVICE, "measurement_id": MEASUREMENT, "seed": SEED,
                  "entradas_sha256": entradas},
        "parametros": PARAMS,
        "parametros_sha256": hashlib.sha256(params_txt.encode()).hexdigest(),
        "flags": FLAGS,
        "contagens": log,
    }
    (saida / "auditoria.json").write_text(json.dumps(auditoria, indent=2, ensure_ascii=False, default=str))

    figuras.fig_visao_geral(out, fig_dir)
    figuras.fig_outliers(out, fig_dir)
    figuras.fig_lacunas(out, fig_dir)
    figuras.fig_filtros(out, cands, fig_dir)
    figuras.fig_lacuna_evento(serie_lacuna, fig_dir)

    print(json.dumps(auditoria, indent=2, ensure_ascii=False, default=str))
    for tab in (tab_filtros, tab_detectores, tab_imputacao, tab_escalas):
        print(tab.to_string(index=False))
