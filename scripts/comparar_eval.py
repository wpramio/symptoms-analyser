#!/usr/bin/env python3
"""
Comparador ad-hoc de uma (ou mais) avaliacao TDPM-20 do LLM contra o clinico.

Complementa o scripts/validacao_tdpm.py: aquele e o harness fechado que compara
os modelos do TCC (eval ids fixos, 3 runs cada) e gera as tabelas/figuras LaTeX.
Este aqui e leve, recebe eval_id(s) pela linha de comando e imprime a comparacao
na hora -- util para iterar no prompt sem editar nada nem regenerar artefatos.

Mesma metodologia do harness, para os numeros baterem:
  - linha "Trecho de exemplo" do CSV do clinico e descartada
  - itens em branco = ausente (0); pacientes 1-4 considerados (outros ignorados)
  - dedup de itens repetidos pela maior nota (regra de desempate do TDPM-20)
  - escore de dimensao = media dos itens da dimensao (2, ou 3 para a 16), ausente=0
  - MAE dimensional reportado so nas dimensoes ATIVAS (>0 em algum avaliador)

Uso (a partir da raiz do repo):
  uv run python scripts/comparar_eval.py 44              # um eval vs clinico
  uv run python scripts/comparar_eval.py 1 6 17 43 44    # varios, lado a lado (A/B)
  uv run python scripts/comparar_eval.py 44 --detalhe    # tabela item a item do eval
"""
import argparse
import csv
import json
import os
import re
import sqlite3
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB   = os.path.join(ROOT, "data", "sqlite.db")
ONTO = os.path.join(ROOT, "data", "tdpm_ontology.json")
CSV  = os.path.join(ROOT, "data", "avaliacao_tdpm_terapeuta.csv")

PATIENTS = ["Paciente1", "Paciente2", "Paciente3", "Paciente4"]

_onto = json.load(open(ONTO))
ITEMS = _onto["TDPM_ITEMS"]        # "19.1" -> nome
DIMS  = _onto["TDPM_DIMENSIONS"]   # "19"   -> nome
ITEM_CODES = sorted(ITEMS, key=lambda c: tuple(int(x) for x in c.split(".")))
DIM_NITEMS = defaultdict(int)
for c in ITEM_CODES:
    DIM_NITEMS[c.split(".")[0]] += 1


# --------------------------------------------------------------- carga
def load_clinico():
    scores = {p: {} for p in PATIENTS}
    for r in csv.DictReader(open(CSV)):
        if "exemplo" in r["Trecho(s) da transcrição"].strip().lower():
            continue
        pac  = r["Paciente"].strip()
        code = r["Sintoma"].split(":")[0].strip()
        sc   = int(re.match(r"\s*(\d)", r["Escore (1 a 4)"]).group(1))
        if pac in scores:
            scores[pac][code] = max(scores[pac].get(code, 0), sc)
    return scores


def load_llm(con, eval_id):
    pid = {r["id"]: r["pseudonym"] for r in con.execute("SELECT id,pseudonym FROM patients")}
    scores = {p: {} for p in PATIENTS}
    njust = ntot = 0
    for r in con.execute("SELECT patient_id,item_code,score,justification "
                         "FROM patient_item_scores WHERE evaluation_id=?", (eval_id,)):
        pac = pid.get(r["patient_id"])
        if pac in scores:
            ntot += 1
            if r["justification"]:
                njust += 1
            scores[pac][r["item_code"]] = max(scores[pac].get(r["item_code"], 0), r["score"])
    return scores, njust, ntot


def eval_meta(con, eval_id):
    r = con.execute("SELECT model,status FROM evaluation_telemetry WHERE evaluation_id=?",
                    (eval_id,)).fetchone()
    return (r["model"], r["status"]) if r else ("?", "?")


# --------------------------------------------------------------- metricas
def detection(clin, test):
    tp = fp = fn = tn = 0
    for p in PATIENTS:
        for code in ITEM_CODES:
            ref = clin[p].get(code, 0) > 0
            tst = test[p].get(code, 0) > 0
            tp += ref and tst
            fp += (not ref) and tst
            fn += ref and (not tst)
            tn += (not ref) and (not tst)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec  = tp / (tp + fn) if tp + fn else 0.0
    f1   = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=prec, recall=rec, f1=f1)


def codetected(clin, test):
    """itens que clinico E modelo pontuaram: (pac, code, nota_clin, nota_llm)."""
    out = []
    for p in PATIENTS:
        for code in set(clin[p]) & set(test[p]):
            out.append((p, code, clin[p][code], test[p][code]))
    return out


def dim_means(scores):
    """media 0-4 por (paciente, dimensao), ausente=0, sobre todos os itens da dim."""
    out = {}
    for p in PATIENTS:
        sums = defaultdict(float)
        for code in ITEM_CODES:
            sums[code.split(".")[0]] += scores[p].get(code, 0)
        out[p] = {d: sums[d] / DIM_NITEMS[d] for d in DIMS}
    return out


def dim_mae_ativa(clin, test):
    cd, td = dim_means(clin), dim_means(test)
    difs = []
    for p in PATIENTS:
        for d in DIMS:
            a, b = cd[p][d], td[p][d]
            if a > 0 or b > 0:
                difs.append(abs(a - b))
    return (sum(difs) / len(difs) if difs else float("nan")), len(difs)


def metrics(clin, test):
    det = detection(clin, test)
    pairs = codetected(clin, test)
    exata = sum(1 for *_, a, b in pairs if a == b)
    mae_c = sum(abs(a - b) for *_, a, b in pairs) / len(pairs) if pairs else float("nan")
    bias  = sum(b - a for *_, a, b in pairs) / len(pairs) if pairs else float("nan")
    mae_d, ndim = dim_mae_ativa(clin, test)
    nitens = sum(len(test[p]) for p in PATIENTS)
    return dict(nitens=nitens, codet=len(pairs), exata=exata, mae_codet=mae_c,
                bias_codet=bias, mae_dim=mae_d, ndim=ndim, **det)


# --------------------------------------------------------------- saida
def fnum(v, nd=2):
    return f"{v:.{nd}f}" if v == v else "---"   # NaN -> ---


def tabela_resumo(con, clin, eval_ids):
    nclin = sum(len(clin[p]) for p in PATIENTS)
    print(f"\nClinico (referencia): {nclin} itens marcados\n")
    hdr = (f"{'eval':>5} {'modelo':<26} {'nit':>4} {'rec':>5} {'prec':>5} {'F1':>5} "
           f"{'exato':>9} {'MAEcod':>7} {'MAEdim':>7} {'just%':>6}")
    print(hdr)
    print("-" * len(hdr))
    for eid in eval_ids:
        test, njust, ntot = load_llm(con, eid)
        model, status = eval_meta(con, eid)
        m = metrics(clin, test)
        just = f"{100*njust/ntot:.0f}" if ntot else "0"
        exato = f"{m['exata']}/{m['codet']}"
        mark = "" if status == "success" else f" [{status}]"
        print(f"{eid:>5} {model.split('/')[-1][:26]:<26} {m['nitens']:>4} "
              f"{m['recall']:>5.2f} {m['precision']:>5.2f} {m['f1']:>5.2f} "
              f"{exato:>9} {fnum(m['mae_codet']):>7} {fnum(m['mae_dim']):>7} {just:>5}%{mark}")
    print("\nrec/prec/F1 = deteccao (presenca por celula paciente x item).")
    print("MAEcod = erro medio nos itens co-detectados; MAEdim = idem por dimensao ativa.")
    print("Escala 0-4. N=1 sessao: leitura exploratoria, nao validacao.")


def detalhe(con, clin, eval_id):
    test, njust, ntot = load_llm(con, eval_id)
    model, _ = eval_meta(con, eval_id)
    print(f"\nDetalhe eval {eval_id} ({model}) vs clinico  [just: {njust}/{ntot}]\n")
    print(f"{'Pac':<10}{'Item':<6}{'Clin':>5}{'LLM':>5}   nota")
    keys = sorted(
        {(p, c) for p in PATIENTS for c in set(clin[p]) | set(test[p])},
        key=lambda k: (k[0], tuple(int(x) for x in k[1].split("."))),
    )
    for p, c in keys:
        a = clin[p].get(c)
        b = test[p].get(c)
        if a is None:
            nota = "so LLM (clinico nao marcou)"
        elif b is None:
            nota = "** SO CLINICO (LLM perdeu) **"
        elif a == b:
            nota = "exato"
        else:
            nota = f"difere (delta {abs(a-b)})"
        print(f"{p:<10}{c:<6}{(a if a is not None else '-'):>5}{(b if b is not None else '-'):>5}   {nota}")


def main():
    ap = argparse.ArgumentParser(description="Compara eval(s) TDPM-20 do LLM contra o clinico.")
    ap.add_argument("eval_ids", nargs="+", type=int, help="um ou mais evaluation_id")
    ap.add_argument("--detalhe", action="store_true",
                    help="imprime a tabela item a item de cada eval (alem do resumo)")
    args = ap.parse_args()

    if not os.path.exists(DB):
        ap.error(f"banco nao encontrado em {DB}")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    clin = load_clinico()

    tabela_resumo(con, clin, args.eval_ids)
    if args.detalhe:
        for eid in args.eval_ids:
            detalhe(con, clin, eid)
    con.close()


if __name__ == "__main__":
    main()
