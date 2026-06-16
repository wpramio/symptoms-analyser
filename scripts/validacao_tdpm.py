#!/usr/bin/env python3
"""
Validacao da avaliacao TDPM-20 via LLM contra a avaliacao de um clinico
(sessao 16/03/2026). Analise exploratoria/preliminar (N=1 sessao, 4 pacientes).

Niveis de analise:
  1. Deteccao    - presenca/ausencia de sintoma por celula (paciente x item)
  2. Intensidade - concordancia da nota 0-4 (kappa ponderado, MAE)
  3. Dimensional - agregacao para as 20 dimensoes + sobreposicao das top-3
  4. Reprodutibilidade - 3 execucoes por modelo a temperatura 0

Decisoes metodologicas (combinadas):
  - linha "Trecho de exemplo" do CSV do clinico e descartada
  - itens em branco = ausente (0); Paciente3 incluido como ausente
  - escala 1-4 para presenca; 0 = ausencia implicita
  - dedup de itens repetidos pela maior nota (regra de desempate do TDPM-20)
  - vs-clinico usa a execucao 1 de cada modelo; pacientes alem de 1-4 sao ignorados

Metricas via scikit-learn. Rode a partir da raiz do repo:
  uv run python scripts/validacao_tdpm.py
"""
import csv, json, sqlite3, re, os, itertools
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
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

# modelo (nome de exibicao) -> (slug OpenRouter, [eval run1, run2, run3])
MODELOS = [
    ("Gemma 4 31B",       "google/gemma-4-31b-it:free",  [1,  6,  17]),
    ("Gemini 3.5 Flash",  "google/gemini-3.5-flash",     [7,  8,  10]),
    ("Gemini 2.5 Pro",    "google/gemini-2.5-pro",       [40, 41, 42]),
    ("Claude Haiku 4.5",  "anthropic/claude-haiku-4.5",  [11, 12, 13]),
    ("Claude Sonnet 4.6", "anthropic/claude-sonnet-4.6", [14, 15, 16]),
    ("Claude Opus 4.8",   "anthropic/claude-opus-4.8",   [37, 38, 39]),
    ("GPT-5.4 nano",      "openai/gpt-5.4-nano",         [18, 19, 20]),
    ("GPT-5.4 mini",      "openai/gpt-5.4-mini",         [21, 22, 23]),
    ("GPT-5.4",           "openai/gpt-5.4",              [24, 25, 26]),
    ("GPT-5.5",           "openai/gpt-5.5",              [34, 35, 36]),
]
PROV_COLOR = {"google": "#5B8FF9", "anthropic": "#9270CA", "openai": "#61C0BF"}
def provider(slug): return slug.split("/")[0]

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


def reprodutibilidade(series_list):
    """concordancia entre execucoes do mesmo modelo (temperatura 0)."""
    sers = [to_series(s) for s in series_list]
    identical = all(sers[0].equals(s) for s in sers[1:])
    if identical:
        return dict(identical=True, kmean=1.0, kmin=1.0)
    ks = [cohen_kappa_score(a, b, weights="quadratic", labels=[0,1,2,3,4])
          for a, b in itertools.combinations(sers, 2)]
    return dict(identical=False, kmean=float(np.mean(ks)), kmin=float(min(ks)))


# ----------------------------------------------------------- figuras
def fig_kappa(rows, path):
    """barras horizontais: kappa ponderado vs. clinico, um por modelo, ordenado."""
    rs = sorted(rows, key=lambda r: r["m"]["kappa_quad"])   # asc => melhor no topo
    labels = [r["nome"] for r in rs]
    vals   = [r["m"]["kappa_quad"] for r in rs]
    colors = [PROV_COLOR[r["prov"]] for r in rs]
    fig, ax = plt.subplots(figsize=(7, 5))
    bands = [(0,.2,"sofrível"),(.2,.4,"razoável"),(.4,.6,"moderada"),
             (.6,.8,"substancial"),(.8,1,"quase perfeita")]
    greys = ["#f7f7f7","#ededed","#e2e2e2","#d6d6d6","#cacaca"]
    for (lo,hi,name), g in zip(bands, greys):
        ax.axvspan(lo, hi, color=g, zorder=0)
        ax.text((lo+hi)/2, len(labels)-0.35, name, ha="center", va="top",
                fontsize=6.5, color="#888")
    bars = ax.barh(labels, vals, color=colors, zorder=3, height=0.62)
    for b, v in zip(bars, vals):
        ax.text(v+0.012, b.get_y()+b.get_height()/2, f"{v:.2f}", va="center", fontsize=8)
    ax.set_xlim(0, 1); ax.set_xlabel("Kappa de Cohen ponderado (quadrático) vs. clínico")
    ax.set_title("Concordância com o clínico por modelo (sessão 16/03/2026)")
    leg = [Patch(color=PROV_COLOR[p], label=p) for p in ("google","anthropic","openai")]
    ax.legend(handles=leg, fontsize=7, loc="lower right", title="Provedor", title_fontsize=7)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def fig_confusao(comps, path):
    fig, axes = plt.subplots(1, len(comps), figsize=(4*len(comps), 3.6))
    if len(comps) == 1: axes = [axes]
    for ax, c in zip(axes, comps):
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
    data = np.array([[rt[1][p].get(code, 0) for rt in raters] for (p, code) in rows])
    fig, ax = plt.subplots(figsize=(1.1*len(raters)+2.5, 0.42*len(rows)+1))
    cmap = ListedColormap(["#ffffff", "#fee5d9", "#fcae91", "#fb6a4a", "#cb181d"])
    ax.imshow(data, cmap=cmap, vmin=0, vmax=4, aspect="auto")
    ax.set_xticks(range(len(raters)), [r[0] for r in raters], fontsize=8, rotation=20, ha="right")
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
def write_table(df, fname, caption, label, fonte="Fonte: o autor.",
                pre="", column_format=None, tabularx=False):
    # pre: comandos antes do tabular (ex.: \footnotesize, \tabcolsep) para caber na margem
    # column_format: especificacao de colunas (ex.: colunas X de tabularx que quebram linha)
    # tabularx: troca o ambiente tabular por tabularx{\textwidth} (texto longo que precisa quebrar)
    kw = {"column_format": column_format} if column_format else {}
    inner = df.to_latex(index=False, escape=False, **kw)  # permite $\kappa$, $\times$
    if tabularx:
        inner = inner.replace("\\begin{tabular}", "\\begin{tabularx}{\\textwidth}", 1)
        inner = inner.replace("\\end{tabular}", "\\end{tabularx}", 1)
    tex = (f"\\begin{{table}}[htbp]\n\\centering\n"
           f"\\caption{{{caption}}}\n\\label{{{label}}}\n{pre}{inner}"
           f"\\legend{{{fonte}}}\n\\end{{table}}\n")
    open(os.path.join(TAB_DIR, fname), "w").write(tex)
    print("  escrito:", os.path.join("tabelas", fname))


def hr(t=""): print("\n" + "=" * 72 + (f"\n{t}" if t else ""))


# ----------------------------------------------------------- main
clinico = load_clinico()
runs = {nome: [load_llm(e) for e in evals] for nome, slug, evals in MODELOS}

# validade externa: execucao 1 de cada modelo vs. clinico
rows = [dict(nome=nome, slug=slug, prov=provider(slug),
             m=metrics_row(clinico, runs[nome][0]))
        for nome, slug, evals in MODELOS]
rows.sort(key=lambda r: r["m"]["kappa_quad"], reverse=True)   # melhor concordancia primeiro
best  = rows[0]
worst = rows[-1]

# reprodutibilidade entre as 3 execucoes (ordem igual a 'rows' p/ cross-ref)
repro = {r["nome"]: reprodutibilidade(runs[r["nome"]]) for r in rows}

hr("RANKING vs. CLINICO (execucao 1, ordenado por kappa pond. quad.)")
print(f"{'modelo':18} {'kquad':>6} {'recall':>7} {'F1':>5} {'top3':>5} | "
      f"{'identicas':>9} {'kmin':>5}")
for r in rows:
    m = r["m"]; rp = repro[r["nome"]]
    print(f"{r['nome']:18} {m['kappa_quad']:6.2f} {m['recall']:7.2f} {m['f1']:5.2f} "
          f"{m['top3_overlap']:5} | {('sim' if rp['identical'] else 'nao'):>9} {rp['kmin']:5.2f}")
print(f"\nMelhor concordancia: {best['nome']} (kquad={best['m']['kappa_quad']:.2f})")

bestser = runs[best["nome"]][0]

# ---- figuras ----
hr("GERANDO FIGURAS")
os.makedirs(FIG_DIR, exist_ok=True)
fig_kappa(rows, os.path.join(FIG_DIR, "fig_kappa_comparacoes.pdf"))
fig_confusao([{"short": best["nome"],  "m": best["m"]},
              {"short": worst["nome"], "m": worst["m"]}],
             os.path.join(FIG_DIR, "fig_matriz_confusao.pdf"))
heat = [("Clínico", clinico), (best["nome"], bestser)]
for base in ("Gemma 4 31B", "Gemini 3.5 Flash"):
    if base != best["nome"]:
        heat.append((base, runs[base][0]))
fig_heatmap(heat, os.path.join(FIG_DIR, "fig_notas_por_avaliador.pdf"))
for f in ("fig_kappa_comparacoes.pdf", "fig_matriz_confusao.pdf", "fig_notas_por_avaliador.pdf"):
    print("  escrito:", os.path.join("figuras", f))

# ---- tabelas ----
hr("GERANDO TABELAS LATEX")
os.makedirs(TAB_DIR, exist_ok=True)

det = pd.DataFrame([{
    "Modelo": r["nome"], "VP": r["m"]["tp"], "FP": r["m"]["fp"], "FN": r["m"]["fn"],
    "VN": r["m"]["tn"], "Precisão": f"{r['m']['precision']:.2f}",
    "Recall": f"{r['m']['recall']:.2f}", "F1": f"{r['m']['f1']:.2f}",
    "$\\kappa$ bin.": f"{r['m']['kappa']:.2f}", "PABAK": f"{r['m']['pabak']:.2f}",
} for r in rows])
write_table(det, "tab_deteccao.tex",
            "Métricas de detecção de sintomas por modelo, contra o clínico (execução 1)",
            "tab:deteccao", pre="\\footnotesize\n\\setlength{\\tabcolsep}{4pt}\n")

inten = pd.DataFrame([{
    "Modelo": r["nome"], "$\\kappa$ pond. (quad.)": f"{r['m']['kappa_quad']:.2f}",
    "$\\kappa$ pond. (lin.)": f"{r['m']['kappa_lin']:.2f}",
    "N co-det.": r["m"]["n_codet"], "Exata": f"{r['m']['exata']}/{r['m']['n_codet']}",
    "Dentro de 1": f"{r['m']['dentro1']}/{r['m']['n_codet']}",
    "MAE co-det.": f"{r['m']['mae_codet']:.2f}" if r["m"]["n_codet"] else "---",
    "Top-3 (sobrep.)": r["m"]["top3_overlap"],
} for r in rows])
write_table(inten, "tab_intensidade.tex",
            "Concordância de intensidade (escala 0--4) e dimensional por modelo, contra o clínico",
            "tab:intensidade",
            pre="\\footnotesize\n\\setlength{\\tabcolsep}{4pt}\n")

rep = pd.DataFrame([{
    "Modelo": r["nome"],
    "Execuções idênticas": "sim" if repro[r["nome"]]["identical"] else "não",
    "$\\kappa$ pond. médio": f"{repro[r['nome']]['kmean']:.2f}",
    "$\\kappa$ pond. mínimo": f"{repro[r['nome']]['kmin']:.2f}",
} for r in rows])
write_table(rep, "tab_reprodutibilidade.tex",
            "Reprodutibilidade entre as três execuções de cada modelo (temperatura 0)",
            "tab:reprodutibilidade")

# detalhe ilustrativo no modelo de melhor concordancia
det_pairs = []
for p, code, a, b in sorted(codetected(clinico, bestser)):
    det_pairs.append({"Paciente": p, "Item": code, "Sintoma": ITEMS[code],
                      "Clínico": a, best["nome"]: b, "Dif.": abs(a-b)})
write_table(pd.DataFrame(det_pairs), "tab_codetectados.tex",
            f"Itens pontuados simultaneamente por clínico e {best['nome']}",
            "tab:codetectados")

t3 = []
for p in PATIENTS:
    fmt = lambda L: ", ".join(f"{d} ({DIMS[d]})" for d in L) or "---"
    t3.append({"Paciente": p, "Clínico": fmt(top3(clinico, p)),
               best["nome"]: fmt(top3(bestser, p))})
_X = ">{\\raggedright\\arraybackslash}X"
write_table(pd.DataFrame(t3), "tab_top3.tex",
            f"Três dimensões prioritárias (top-3) por paciente: clínico e {best['nome']}",
            "tab:top3",
            pre="\\small\n", column_format=f"l {_X} {_X}", tabularx=True)

print("\nOK. Saidas em:", MONO)
