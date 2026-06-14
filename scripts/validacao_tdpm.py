#!/usr/bin/env python3
"""
Validacao da avaliacao TDPM-20 via LLM contra a avaliacao de um clinico
(sessao 16/03/2026). Analise exploratoria/preliminar (N=1 sessao, 4 pacientes).

Niveis de analise:
  1. Deteccao    - presenca/ausencia de sintoma por celula (paciente x item)
  2. Intensidade - concordancia da nota 0-4 (kappa ponderado, MAE)
  3. Dimensional - agregacao para as 20 dimensoes + sobreposicao das top-3
  4. Confiabilidade - LLM vs LLM (inter-modelo e intra-modelo)

Decisoes metodologicas (combinadas):
  - linha "Trecho de exemplo" do CSV do clinico e descartada
  - itens em branco = ausente (0); Paciente3 incluido como ausente
  - escala 1-4 para presenca; 0 = ausencia implicita
  - dedup de itens repetidos pela maior nota (regra de desempate do TDPM-20)

Metricas via scikit-learn. Rode a partir da raiz do repo:
  uv run python scripts/validacao_tdpm.py
"""
import csv, json, sqlite3, re, os
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from sklearn.metrics import (cohen_kappa_score, precision_recall_fscore_support,
                             confusion_matrix)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB   = os.path.join(ROOT, "data", "sqlite.db")
ONTO = os.path.join(ROOT, "data", "tdpm_ontology.json")
CSV  = os.path.join(ROOT, "data", "avaliacao_tdpm_terapeuta.csv")

# saidas vao direto para o repo da monografia
MONO    = os.path.expanduser("~/projects/ufrgs/tcc-monografia")
FIG_DIR = os.path.join(MONO, "figuras")
TAB_DIR = os.path.join(MONO, "tabelas")

PATIENTS = ["Paciente1", "Paciente2", "Paciente3", "Paciente4"]

onto  = json.load(open(ONTO))
ITEMS = onto["TDPM_ITEMS"]          # "19.1" -> nome
DIMS  = onto["TDPM_DIMENSIONS"]     # "19"   -> nome
ITEM_CODES = sorted(ITEMS, key=lambda c: tuple(int(x) for x in c.split(".")))
DIM_NITEMS = pd.Series(ITEM_CODES).str.split(".").str[0].value_counts()  # itens por dim


# ----------------------------------------------------------- carga de dados
def load_clinico():
    scores = {p: {} for p in PATIENTS}
    for r in csv.DictReader(open(CSV)):
        if "exemplo" in r["Trecho(s) da transcrição"].strip().lower():
            continue
        pac  = r["Paciente"].strip()
        code = r["Sintoma"].split(":")[0].strip()
        sc   = int(re.match(r"\s*(\d)", r["Escore (1 a 4)"]).group(1))
        scores[pac][code] = max(scores[pac].get(code, 0), sc)
    return scores


def load_llm(eval_id):
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    pid = {r["id"]: r["pseudonym"] for r in con.execute("SELECT id,pseudonym FROM patients")}
    scores = {p: {} for p in PATIENTS}
    for r in con.execute("SELECT patient_id,item_code,score FROM patient_item_scores "
                         "WHERE evaluation_id=?", (eval_id,)):
        pac = pid[r["patient_id"]]
        if pac in scores:
            scores[pac][r["item_code"]] = max(scores[pac].get(r["item_code"], 0), r["score"])
    con.close()
    return scores


def to_series(scores):
    """vetor denso 0-4 indexado por (paciente, item), ausencia = 0."""
    idx = pd.MultiIndex.from_product([PATIENTS, ITEM_CODES], names=["paciente", "item"])
    return pd.Series({(p, c): scores[p].get(c, 0) for p, c in idx}, index=idx, name="score")


# ----------------------------------------------------------- metricas
def detection(ref, test):
    rb, tb = (ref > 0).astype(int), (test > 0).astype(int)
    tn, fp, fn, tp = confusion_matrix(rb, tb, labels=[0, 1]).ravel()
    prec, rec, f1, _ = precision_recall_fscore_support(
        rb, tb, average="binary", zero_division=0)
    n = len(ref); po = (tp + tn) / n
    kappa = cohen_kappa_score(rb, tb)
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=prec, recall=rec, f1=f1,
                specificity=tn / (tn + fp) if tn + fp else np.nan,
                agreement=po, kappa=kappa, pabak=2 * po - 1)


def codetected(ref_s, test_s):
    pairs = []
    for p in PATIENTS:
        for code in set(ref_s[p]) & set(test_s[p]):
            pairs.append((p, code, ref_s[p][code], test_s[p][code]))
    return pairs


def top3(scores, p):
    sums = defaultdict(int)
    for code, sc in scores[p].items():
        sums[code.split(".")[0]] += sc
    return sorted((d for d in sums if sums[d] > 0), key=lambda d: -sums[d])[:3]


# ----------------------------------------------------------- relatorio
def hr(t=""): print("\n" + "=" * 72 + (f"\n{t}" if t else ""))


def report_pair(name, ref_s, test_s, ref_label, test_label):
    hr(f"### {name}\n    ({ref_label} = referencia, {test_label} = teste)")
    ref, test = to_series(ref_s), to_series(test_s)

    m = detection(ref, test)
    print(f"\n[1] DETECCAO  ({len(PATIENTS)} pac x {len(ITEM_CODES)} itens = {len(ref)} celulas)")
    print(f"    VP={m['tp']} FP={m['fp']} FN={m['fn']} VN={m['tn']}")
    print(f"    Precisao={m['precision']:.2f} Recall={m['recall']:.2f} F1={m['f1']:.2f} "
          f"Especif.={m['specificity']:.2f}")
    print(f"    Concordancia={m['agreement']:.3f} Kappa(bin)={m['kappa']:.2f} PABAK={m['pabak']:.2f}")

    print("\n[2] INTENSIDADE (0-4)")
    wq = cohen_kappa_score(ref, test, weights="quadratic", labels=[0,1,2,3,4])
    wl = cohen_kappa_score(ref, test, weights="linear",    labels=[0,1,2,3,4])
    print(f"    Denso (ausencia=0): kappa pond. quad={wq:.2f} linear={wl:.2f} "
          f"MAE={np.mean(np.abs(ref - test)):.3f}")
    pairs = codetected(ref_s, test_s)
    print(f"    Co-detectados (ambos>0): N={len(pairs)}")
    for p, code, a, b in sorted(pairs):
        d = abs(a - b); flag = "" if d == 0 else f"  (dif {d})"
        print(f"      {p:10} {code:5} {ITEMS[code][:32]:32} ref={a} teste={b}{flag}")
    if pairs:
        ex = sum(1 for *_, a, b in pairs if a == b)
        w1 = sum(1 for *_, a, b in pairs if abs(a - b) <= 1)
        mae = np.mean([abs(a - b) for *_, a, b in pairs])
        print(f"      exata={ex}/{len(pairs)} dentro-de-1={w1}/{len(pairs)} MAE={mae:.2f}")

    print("\n[3] DIMENSIONAL - top-3 prioritarias por paciente")
    for p in PATIENTS:
        tr, tt = top3(ref_s, p), top3(test_s, p)
        inter = set(tr) & set(tt)
        fmt = lambda L: [f"{d}:{DIMS[d][:16]}" for d in L] or ["(nenhuma)"]
        print(f"    {p}: ref  ={fmt(tr)}")
        print(f"    {'':10} teste={fmt(tt)}  sobrep.={len(inter)}/{max(len(tr),len(tt)) or 1}")


def metrics_row(ref_s, test_s):
    ref, test = to_series(ref_s), to_series(test_s)
    m = detection(ref, test)
    pairs = codetected(ref_s, test_s)
    n3 = sum(len(set(top3(ref_s, p)) & set(top3(test_s, p))) for p in PATIENTS)
    return dict(
        **m,
        kappa_quad=cohen_kappa_score(ref, test, weights="quadratic", labels=[0,1,2,3,4]),
        kappa_lin =cohen_kappa_score(ref, test, weights="linear",    labels=[0,1,2,3,4]),
        n_codet=len(pairs),
        exata=sum(1 for *_, a, b in pairs if a == b),
        dentro1=sum(1 for *_, a, b in pairs if abs(a - b) <= 1),
        mae_codet=np.mean([abs(a - b) for *_, a, b in pairs]) if pairs else np.nan,
        top3_overlap=n3,
    )


# ----------------------------------------------------------- figuras
def fig_kappa(comps, path):
    labels = [c["short"] for c in comps]
    vals   = [c["m"]["kappa_quad"] for c in comps]
    colors = ["#5B8FF9" if c["kind"] == "externa" else "#9270CA" for c in comps]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bands = [(0,.2,"#f7f7f7","sofrível"),(.2,.4,"#eaeaea","razoável"),
             (.4,.6,"#dddddd","moderada"),(.6,.8,"#cfcfcf","substancial"),
             (.8,1,"#c2c2c2","quase perfeita")]
    for lo, hi, col, name in bands:
        ax.axhspan(lo, hi, color=col, zorder=0)
        ax.text(len(labels)-0.4, (lo+hi)/2, name, va="center", ha="right",
                fontsize=7, color="#777")
    bars = ax.bar(labels, vals, color=colors, zorder=3, width=0.6)
    for b, v in zip(bars, vals):
        ax.text(b.get_x()+b.get_width()/2, v+0.02, f"{v:.2f}", ha="center", fontsize=9)
    ax.set_ylim(0, 1); ax.set_ylabel("Kappa de Cohen ponderado (quadrático)")
    ax.set_title("Concordância por comparação (sessão 16/03/2026)")
    ax.margins(x=0.02)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def fig_confusao(comps_ext, path):
    fig, axes = plt.subplots(1, len(comps_ext), figsize=(4*len(comps_ext), 3.6))
    if len(comps_ext) == 1: axes = [axes]
    for ax, c in zip(axes, comps_ext):
        m = c["m"]; mat = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
        ax.imshow(mat, cmap="Blues", vmin=0, vmax=mat.max())
        for i in range(2):
            for j in range(2):
                ax.text(j, i, mat[i, j], ha="center", va="center",
                        color="white" if mat[i, j] > mat.max()/2 else "black", fontsize=13)
        ax.set_xticks([0,1], ["Ausente","Presente"]); ax.set_yticks([0,1], ["Ausente","Presente"])
        ax.set_xlabel("LLM"); ax.set_ylabel("Clínico (referência)")
        ax.set_title(c["short"].replace("\n", " "))
    fig.suptitle("Detecção de sintomas: matriz de confusão (paciente × item)")
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def fig_heatmap(raters, path):
    """raters: lista de (label, scores_dict). Linhas = itens pontuados por alguem."""
    rows = []
    for p in PATIENTS:
        codes = set().union(*[r[1][p].keys() for r in raters])
        for code in sorted(codes, key=lambda c: tuple(int(x) for x in c.split("."))):
            rows.append((p, code))
    data = np.array([[r[1][p].get(code, 0) for _, r in [(0, rr) for rr in raters]]
                     for (p, code) in rows]) if rows else np.zeros((0, len(raters)))
    data = np.array([[rt[1][p].get(code, 0) for rt in raters] for (p, code) in rows])
    fig, ax = plt.subplots(figsize=(5.5, 0.42*len(rows)+1))
    cmap = ListedColormap(["#ffffff", "#fee5d9", "#fcae91", "#fb6a4a", "#cb181d"])
    ax.imshow(data, cmap=cmap, vmin=0, vmax=4, aspect="auto")
    ax.set_xticks(range(len(raters)), [r[0] for r in raters])
    ax.set_yticks(range(len(rows)),
                  [f"{p[-1]}·{code} {ITEMS[code][:24]}" for p, code in rows], fontsize=7)
    for i in range(len(rows)):
        for j in range(len(raters)):
            v = data[i, j]
            ax.text(j, i, "" if v == 0 else int(v), ha="center", va="center",
                    fontsize=8, color="white" if v >= 3 else "black")
    ax.set_title("Notas por avaliador (0 = ausente)", fontsize=10)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


# ----------------------------------------------------------- tabelas LaTeX
def write_table(df, fname, caption, label, fonte="Fonte: elaborado pelo autor.",
                pre="", column_format=None, tabularx=False):
    # pre: comandos antes do tabular (ex.: \footnotesize, \tabcolsep) para caber na margem
    # column_format: especificacao de colunas (ex.: colunas X de tabularx que quebram linha)
    # tabularx: troca o ambiente tabular por tabularx{\textwidth} (texto longo que precisa quebrar)
    kw = {"column_format": column_format} if column_format else {}
    inner = df.to_latex(index=False, escape=False, **kw)  # permite $\kappa$, $\times$
    if tabularx:
        inner = inner.replace("\\begin{tabular}", "\\begin{tabularx}{\\textwidth}", 1)
        inner = inner.replace("\\end{tabular}", "\\end{tabularx}", 1)
    tex = (f"\\begin{{table}}[htb]\n\\centering\n"
           f"\\caption{{{caption}}}\n\\label{{{label}}}\n{pre}{inner}"
           f"\\legend{{{fonte}}}\n\\end{{table}}\n")
    open(os.path.join(TAB_DIR, fname), "w").write(tex)
    print("  escrito:", os.path.join("tabelas", fname))


# ----------------------------------------------------------- main
clinico = load_clinico()
gemma   = load_llm(1)   # gemma-4-31b-it   (eval 1 == eval 6)
gem1    = load_llm(7)   # gemini-3.5-flash (rodada 1)
gem2    = load_llm(8)   # gemini-3.5-flash (rodada 2)

hr("DADOS CARREGADOS (sessao 16/03/2026)")
print("\nClinico (apos limpeza):")
for p in PATIENTS: print(f"  {p}: {clinico[p]}")
print("\nGemma   :", {p: gemma[p] for p in PATIENTS})
print("Gemini1 :", {p: gem1[p] for p in PATIENTS})
print("Gemini2 :", {p: gem2[p] for p in PATIENTS})

report_pair("VALIDADE EXTERNA: Clinico vs Gemini 3.5 Flash", clinico, gem1, "clinico", "gemini")
report_pair("VALIDADE EXTERNA: Clinico vs Gemma 4-31b",      clinico, gemma, "clinico", "gemma")
report_pair("CONFIABILIDADE INTER-MODELO: Gemini vs Gemma",  gem1, gemma, "gemini", "gemma")
report_pair("CONFIABILIDADE INTRA-MODELO: Gemini r1 vs r2",  gem1, gem2,  "gemini-r1", "gemini-r2")

# estrutura de comparacoes
COMPS = [
    dict(short="Clínico ×\nGemini", kind="externa", m=metrics_row(clinico, gem1)),
    dict(short="Clínico ×\nGemma",  kind="externa", m=metrics_row(clinico, gemma)),
    dict(short="Gemini ×\nGemma",   kind="confiab", m=metrics_row(gem1, gemma)),
    dict(short="Gemini\nr1 × r2",   kind="confiab", m=metrics_row(gem1, gem2)),
]
NAMES = [r"Clínico $\times$ Gemini", r"Clínico $\times$ Gemma",
         r"Gemini $\times$ Gemma", r"Gemini r1 $\times$ r2"]

# ---- figuras ----
hr("GERANDO FIGURAS")
os.makedirs(FIG_DIR, exist_ok=True)
fig_kappa(COMPS, os.path.join(FIG_DIR, "fig_kappa_comparacoes.pdf"))
fig_confusao(COMPS[:2], os.path.join(FIG_DIR, "fig_matriz_confusao.pdf"))
fig_heatmap([("Clínico", clinico), ("Gemma", gemma), ("Gemini", gem1)],
            os.path.join(FIG_DIR, "fig_notas_por_avaliador.pdf"))
for f in ("fig_kappa_comparacoes.pdf", "fig_matriz_confusao.pdf", "fig_notas_por_avaliador.pdf"):
    print("  escrito:", os.path.join("figuras", f))

# ---- tabelas ----
hr("GERANDO TABELAS LATEX")
os.makedirs(TAB_DIR, exist_ok=True)

det = pd.DataFrame([{
    "Comparação": n, "VP": m["m"]["tp"], "FP": m["m"]["fp"], "FN": m["m"]["fn"],
    "VN": m["m"]["tn"], "Precisão": f"{m['m']['precision']:.2f}",
    "Recall": f"{m['m']['recall']:.2f}", "F1": f"{m['m']['f1']:.2f}",
    "$\\kappa$ bin.": f"{m['m']['kappa']:.2f}", "PABAK": f"{m['m']['pabak']:.2f}",
} for n, m in zip(NAMES, COMPS)])
write_table(det, "tab_deteccao.tex",
            "Métricas de detecção de sintomas (presença/ausência) por comparação.",
            "tab:deteccao")

inten = pd.DataFrame([{
    "Comparação": n, "$\\kappa$ pond. (quad.)": f"{m['m']['kappa_quad']:.2f}",
    "$\\kappa$ pond. (lin.)": f"{m['m']['kappa_lin']:.2f}",
    "N co-det.": m["m"]["n_codet"], "Exata": f"{m['m']['exata']}/{m['m']['n_codet']}",
    "Dentro de 1": f"{m['m']['dentro1']}/{m['m']['n_codet']}",
    "MAE co-det.": f"{m['m']['mae_codet']:.2f}",
    "Top-3 (sobrep.)": m["m"]["top3_overlap"],
} for n, m in zip(NAMES, COMPS)])
write_table(inten, "tab_intensidade.tex",
            "Concordância de intensidade (escala 0--4) e dimensional por comparação.",
            "tab:intensidade",
            pre="\\footnotesize\n\\setlength{\\tabcolsep}{4.5pt}\n")

# co-detectados clinico x gemini (detalhe ilustrativo)
det_pairs = []
for p, code, a, b in sorted(codetected(clinico, gem1)):
    det_pairs.append({"Paciente": p, "Item": code, "Sintoma": ITEMS[code],
                      "Clínico": a, "Gemini": b, "Dif.": abs(a-b)})
write_table(pd.DataFrame(det_pairs), "tab_codetectados.tex",
            "Itens pontuados por clínico e LLM (Gemini) simultaneamente.",
            "tab:codetectados")

# top-3 dimensional por paciente
t3 = []
for p in PATIENTS:
    fmt = lambda L: ", ".join(f"{d} ({DIMS[d]})" for d in L) or "---"
    t3.append({"Paciente": p, "Clínico": fmt(top3(clinico, p)),
               "Gemini": fmt(top3(gem1, p)), "Gemma": fmt(top3(gemma, p))})
_X = ">{\\raggedright\\arraybackslash}X"
write_table(pd.DataFrame(t3), "tab_top3.tex",
            "Três dimensões prioritárias (top-3) por paciente e avaliador.",
            "tab:top3",
            pre="\\small\n", column_format=f"l {_X} {_X} {_X}", tabularx=True)

print("\nOK. Saidas em:", MONO)
