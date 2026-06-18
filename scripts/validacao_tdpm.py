#!/usr/bin/env python3
"""
Validacao da avaliacao TDPM-20 via LLM contra a avaliacao de um clinico
(sessao 16/03/2026). Analise exploratoria/preliminar (N=1 sessao, 4 pacientes).

Niveis de analise:
  1. Deteccao    - presenca/ausencia de sintoma por celula (paciente x item)
  2. Intensidade - concordancia da nota 0-4 (kappa ponderado, MAE)
  3. Dimensional - media por dimensao (0-4, unidade de analise do TDPM-20):
                   MAE sobre as 80 celulas (20 dims x 4 pacientes) + top-3
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
import csv, json, sqlite3, re, os
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from sklearn.metrics import precision_recall_fscore_support, confusion_matrix

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
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=prec, recall=rec, f1=f1,
                specificity=tn / (tn + fp) if tn + fp else np.nan)


def codetected(ref_s, test_s):
    pairs = []
    for p in PATIENTS:
        for code in set(ref_s[p]) & set(test_s[p]):
            pairs.append((p, code, ref_s[p][code], test_s[p][code]))
    return pairs


def dim_means(scores, p):
    """media 0-4 por dimensao (ausente=0), sobre TODOS os itens da dimensao.

    Esta e a unidade de analise prescrita pelo TDPM-20: o escore de cada
    dimensao e a media dos seus itens (2, exceto Ansiedade/Fobia/Panico, 3),
    nao a soma. Somar enviesaria a dimensao de 3 itens para cima.
    """
    sums = defaultdict(float)
    for code in ITEM_CODES:
        sums[code.split(".")[0]] += scores[p].get(code, 0)
    return {d: sums[d] / int(DIM_NITEMS[d]) for d in DIMS}


def to_dim_series(scores):
    """vetor denso de medias por dimensao indexado por (paciente, dimensao)."""
    idx = pd.MultiIndex.from_product([PATIENTS, list(DIMS)], names=["paciente", "dim"])
    mm  = {p: dim_means(scores, p) for p in PATIENTS}
    return pd.Series({(p, d): mm[p][d] for p, d in idx}, index=idx, name="dimmean")


def top3(scores, p):
    """tres dimensoes prioritarias, ordenadas pela media por dimensao (0-4)."""
    means = dim_means(scores, p)
    return sorted((d for d in means if means[d] > 0),
                  key=lambda d: (-means[d], int(d)))[:3]


def jaccard_p(ref_s, test_s, p):
    """concordancia de CONJUNTO do top-3 de um paciente: |A inter B| / |A uniao B|.
    Ignora a ordem. Retorna None se o clinico nao tem top-3 (sem gabarito)."""
    A, B = set(top3(ref_s, p)), set(top3(test_s, p))
    if not A:
        return None
    return len(A & B) / len(A | B)


def order_p(ref_s, test_s, p):
    """acerto de ordem do top-3 de um paciente (0-1); None sem gabarito clinico.
    Peso 3/2/1 pela posicao no top-3 do clinico. Cada dimensao tambem listada pelo
    modelo rende seu peso descontado pela distancia de posicao (cheio se mesma
    posicao, menor conforme a posicao se afasta), normalizado pelo maximo alcancavel."""
    ref, test = top3(ref_s, p), top3(test_s, p)
    if not ref:
        return None
    pos_t = {d: j for j, d in enumerate(test)}
    num = den = 0.0
    for i, d in enumerate(ref):
        w = 3 - i                                  # 3, 2, 1
        den += w
        if d in pos_t:
            num += w * (1 - abs(i - pos_t[d]) / 3)
    return num / den if den else 0.0


def _mean_top3(fn, ref_s, test_s):
    """media por paciente de uma metrica de top-3, excluindo os sem gabarito clinico."""
    vals = [v for p in PATIENTS if (v := fn(ref_s, test_s, p)) is not None]
    return float(np.mean(vals)) if vals else np.nan


def jaccard_top3(ref_s, test_s):
    return _mean_top3(jaccard_p, ref_s, test_s)


def weighted_rank_top3(ref_s, test_s):
    return _mean_top3(order_p, ref_s, test_s)


def metrics_row(ref_s, test_s):
    ref, test = to_series(ref_s), to_series(test_s)
    m = detection(ref, test)
    pairs = codetected(ref_s, test_s)
    n3 = sum(len(set(top3(ref_s, p)) & set(top3(test_s, p))) for p in PATIENTS)
    # concordancia no nivel da media por dimensao (80 celulas: 20 dims x 4 pacientes).
    # O MAE sobre todas as celulas e dominado por dimensoes ausentes em ambos (0 vs 0),
    # entao reporta-se tambem o MAE restrito as dimensoes ATIVAS (>0 em algum avaliador),
    # analogo a 'co-detectados' no nivel de item -- esse e o sinal honesto de gravidade.
    rd, td  = to_dim_series(ref_s), to_dim_series(test_s)
    dif_dim = (rd - td).abs()
    ativa   = (rd > 0) | (td > 0)
    return dict(
        **m,
        n_codet=len(pairs),
        exata=sum(1 for *_, a, b in pairs if a == b),
        dentro1=sum(1 for *_, a, b in pairs if abs(a - b) <= 1),
        mae_codet=np.mean([abs(a - b) for *_, a, b in pairs]) if pairs else np.nan,
        # vies = erro com sinal (modelo - clinico): >0 superestima, <0 subestima
        bias_codet=np.mean([b - a for *_, a, b in pairs]) if pairs else np.nan,
        top3_overlap=n3,
        mae_dim=float(dif_dim.mean()),
        dim_dentro1=int((dif_dim <= 1).sum()),
        dim_corr=float(rd.corr(td)),
        n_dim_ativa=int(ativa.sum()),
        mae_dim_ativa=float(dif_dim[ativa].mean()) if ativa.any() else np.nan,
        bias_dim_ativa=float((td - rd)[ativa].mean()) if ativa.any() else np.nan,
        top3_jaccard=jaccard_top3(ref_s, test_s),
        top3_ordem=weighted_rank_top3(ref_s, test_s),
    )


def reprodutibilidade(series_list):
    """concordancia entre execucoes do mesmo modelo (temperatura 0)."""
    sers = [to_series(s) for s in series_list]
    return dict(identical=all(sers[0].equals(s) for s in sers[1:]))


# ----------------------------------------------------------- figuras
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
                  [f"P{p[-1]} · {code} {ITEMS[code][:24]}" for p, code in rows], fontsize=7)
    for i in range(len(rows)):
        for j in range(len(raters)):
            v = data[i, j]
            ax.text(j, i, int(v), ha="center", va="center", fontsize=8,
                    color="white" if v >= 3 else ("#b0b0b0" if v == 0 else "black"))
    ax.set_title("Notas por avaliador (0 = ausente)", fontsize=10)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


# ----------------------------------------------------------- tabelas LaTeX
def write_table(df, fname, caption, label, fonte="Fonte: o autor.",
                pre="", column_format=None, tabularx=False, nota=None):
    # pre: comandos antes do tabular (ex.: \footnotesize, \tabcolsep) para caber na margem
    # column_format: especificacao de colunas (ex.: colunas X de tabularx que quebram linha)
    # tabularx: troca o ambiente tabular por tabularx{\textwidth} (texto longo que precisa quebrar)
    # nota: legenda explicativa abaixo da tabela (ex.: de-para de abreviacoes), antes da Fonte
    kw = {"column_format": column_format} if column_format else {}
    inner = df.to_latex(index=False, escape=False, **kw)  # permite $\kappa$, $\times$
    if tabularx:
        inner = inner.replace("\\begin{tabular}", "\\begin{tabularx}{\\textwidth}", 1)
        inner = inner.replace("\\end{tabular}", "\\end{tabularx}", 1)
    nota_tex = f"\\legend{{\\footnotesize {nota}}}\n" if nota else ""
    tex = (f"\\begin{{table}}[htbp]\n\\centering\n"
           f"\\caption{{{caption}}}\n\\label{{{label}}}\n{pre}{inner}"
           f"\\legend{{{fonte}}}\n{nota_tex}\\end{{table}}\n")
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
rows.sort(key=lambda r: r["m"]["f1"], reverse=True)   # melhor F1 de deteccao primeiro
best  = rows[0]
worst = rows[-1]

# reprodutibilidade entre as 3 execucoes (ordem igual a 'rows' p/ cross-ref)
repro = {r["nome"]: reprodutibilidade(runs[r["nome"]]) for r in rows}

hr("RANKING vs. CLINICO (execucao 1, ordenado por F1 de deteccao)")
print(f"{'modelo':18} {'recall':>7} {'F1':>5} {'MAE':>6} {'MAEdimA':>8} {'top3':>5} | {'identicas':>9}")
for r in rows:
    m = r["m"]; rp = repro[r["nome"]]
    mae  = f"{m['mae_codet']:.2f}" if m["n_codet"] else "---"
    maed = f"{m['mae_dim_ativa']:.2f}" if m["n_dim_ativa"] else "---"
    print(f"{r['nome']:18} {m['recall']:7.2f} {m['f1']:5.2f} {mae:>6} {maed:>8} "
          f"{m['top3_overlap']:5} | {('sim' if rp['identical'] else 'nao'):>9}")
print(f"\nMelhor F1: {best['nome']} (F1={best['m']['f1']:.2f})")

bestser = runs[best["nome"]][0]

# ---- figuras ----
hr("GERANDO FIGURAS")
os.makedirs(FIG_DIR, exist_ok=True)
fig_confusao([{"short": best["nome"],  "m": best["m"]},
              {"short": worst["nome"], "m": worst["m"]}],
             os.path.join(FIG_DIR, "fig_matriz_confusao.pdf"))
# heatmap compara o clinico com o melhor e o pior modelo (por F1)
heat = [("Clínico", clinico), (best["nome"], runs[best["nome"]][0]),
        (worst["nome"], runs[worst["nome"]][0])]
fig_heatmap(heat, os.path.join(FIG_DIR, "fig_notas_por_avaliador.pdf"))
for f in ("fig_matriz_confusao.pdf", "fig_notas_por_avaliador.pdf"):
    print("  escrito:", os.path.join("figuras", f))

# ---- tabelas ----
hr("GERANDO TABELAS LATEX")
os.makedirs(TAB_DIR, exist_ok=True)

det = pd.DataFrame([{
    "Modelo": r["nome"], "VP": r["m"]["tp"], "FP": r["m"]["fp"], "FN": r["m"]["fn"],
    "VN": r["m"]["tn"], "Precisão": f"{r['m']['precision']:.2f}",
    "Recall": f"{r['m']['recall']:.2f}", "F1": f"{r['m']['f1']:.2f}",
} for r in rows])
write_table(det, "tab_deteccao.tex",
            "Métricas de detecção de sintomas por modelo, contra o clínico (execução 1)",
            "tab:deteccao", pre="\\footnotesize\n\\setlength{\\tabcolsep}{4pt}\n")

# nivel de item (intensidade) e nivel de dimensao ficam em tabelas separadas,
# espelhando as subsecoes de resultados
inten = pd.DataFrame([{
    "Modelo": r["nome"],
    "N co-det.": r["m"]["n_codet"], "Exata": f"{r['m']['exata']}/{r['m']['n_codet']}",
    "Dentro de 1": f"{r['m']['dentro1']}/{r['m']['n_codet']}",
    "MAE co-det.": f"{r['m']['mae_codet']:.2f}" if r["m"]["n_codet"] else "---",
    "Viés co-det.": f"{r['m']['bias_codet']:+.2f}" if r["m"]["n_codet"] else "---",
} for r in rows])
write_table(inten, "tab_intensidade.tex",
            "Concordância de intensidade (escala 0--4) por modelo, contra o clínico",
            "tab:intensidade",
            pre="\\footnotesize\n\\setlength{\\tabcolsep}{4pt}\n")

dimt = pd.DataFrame([{
    "Modelo": r["nome"],
    "N dim. ativa": r["m"]["n_dim_ativa"],
    "MAE dim. ativa": f"{r['m']['mae_dim_ativa']:.2f}" if r["m"]["n_dim_ativa"] else "---",
    "Viés dim. ativa": f"{r['m']['bias_dim_ativa']:+.2f}" if r["m"]["n_dim_ativa"] else "---",
    "Jaccard top-3": f"{r['m']['top3_jaccard']:.2f}",
    "Ordem top-3": f"{r['m']['top3_ordem']:.2f}",
} for r in rows])
write_table(dimt, "tab_dimensional.tex",
            "Concordância no nível dimensional (média por dimensão, 0--4) por modelo, contra o clínico",
            "tab:dimensional",
            pre="\\footnotesize\n\\setlength{\\tabcolsep}{4pt}\n")

# comparacao das medias por dimensao: clinico vs. melhor e pior modelo (por F1),
# so nas dimensoes ativas em algum dos tres avaliadores
_X = ">{\\raggedright\\arraybackslash}X"
worstser  = runs[worst["nome"]][0]
dim_rater = [("Clínico", clinico), (best["nome"], bestser), (worst["nome"], worstser)]
dimcmp = []
for p in PATIENTS:
    mm = {lbl: dim_means(sc, p) for lbl, sc in dim_rater}
    for d in DIMS:
        vals = [mm[lbl][d] for lbl, _ in dim_rater]
        if any(v > 0 for v in vals):
            dimcmp.append({"Pac.": f"P{p[-1]}", "Dim.": d, "Dimensão": DIMS[d],
                           "Clínico": f"{vals[0]:.1f}", best["nome"]: f"{vals[1]:.1f}",
                           worst["nome"]: f"{vals[2]:.1f}"})
write_table(pd.DataFrame(dimcmp), "tab_dim_comparacao.tex",
            "Média por dimensão (0 a 4), recorte de dimensões ativas",
            "tab:dim-comparacao",
            pre="\\footnotesize\n\\setlength{\\tabcolsep}{4pt}\n",
            column_format=f"l l {_X} r r r", tabularx=True)

# detalhe ilustrativo no modelo de melhor concordancia
det_pairs = []
for p, code, a, b in sorted(codetected(clinico, bestser)):
    det_pairs.append({"Paciente": p, "Item": code, "Sintoma": ITEMS[code],
                      "Clínico": a, "LLM": b, "Dif.": abs(a-b)})
write_table(pd.DataFrame(det_pairs), "tab_codetectados.tex",
            f"Itens pontuados simultaneamente por clínico e {best['nome']}",
            "tab:codetectados")

t3 = []
usadas = set()  # dimensoes que aparecem na tabela, para a nota de de-para
fmt  = lambda L: ", ".join(L) or "---"          # so o numero da dimensao; nome vai na nota
cell = lambda v: f"{v:.2f}" if v is not None else "---"  # None = sem gabarito clinico
for p in PATIENTS:
    rc, rm = top3(clinico, p), top3(bestser, p)
    usadas |= set(rc) | set(rm)
    t3.append({"Paciente": p, "Clínico": fmt(rc), "LLM": fmt(rm),
               "$J_p$": cell(jaccard_p(clinico, bestser, p)),
               "$O_p$": cell(order_p(clinico, bestser, p))})
nota_dims = "Dimensões: " + ", ".join(
    f"{d}~{DIMS[d]}" for d in sorted(usadas, key=int)) + "."
write_table(pd.DataFrame(t3), "tab_top3.tex",
            f"Três dimensões prioritárias (top-3) por paciente: clínico e {best['nome']}",
            "tab:top3",
            pre="\\small\n", column_format="l l l r r", nota=nota_dims)

print("\nOK. Saidas em:", MONO)
