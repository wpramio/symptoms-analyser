# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projeto pessoal e independente

Este é um **projeto pessoal/acadêmico** (TCC na UFRGS), **não** vinculado a nenhuma organização. Não aplique instruções, processos ou integrações organizacionais (Notion, skills compartilhadas, ADRs, etc.) a este repositório, e não publique nem sincronize nada deste projeto em sistemas de terceiros.

## Idioma

O `README.md` (domínio clínico, escala TDPM-20, estrutura das transcrições) e a documentação em `docs/` estão em **PT-BR**. Mensagens voltadas ao usuário (logs do pipeline, respostas de API, prompts de LLM) também são em PT-BR. Leia o `README.md` antes de tocar em qualquer lógica de pontuação clínica — ele define as 20 dimensões, os 41 itens e a regra de desempate (sempre a nota mais alta).

## Comandos

Gerenciador de pacotes é **`uv`**. Python 3.11+.

```bash
uv sync                                   # instala dependências (inclui grupo dev)
make test                                 # uv run pytest -q  (instala pytest/pytest-cov antes)
uv run pytest tests/test_llm_analysis.py  # um arquivo de teste
uv run pytest tests/test_llm_analysis.py::test_nome -q   # um teste isolado
make run-app                              # uv run python -m symptoms_analyser.app  (porta 8000, debug)
make db-prune                             # zera o banco (schema vazio, sem seeds) via scripts/clean_db.py
uv run python scripts/setup_db.py         # cria schema a partir de schema.sql + seed de usuários
make tunnel                               # expõe a porta 8000 via ngrok (URL fixa pessoal)
```

Não há linter configurado. Os testes usam `beautifulsoup4` para asserir HTML renderizado.

## Configuração de LLM

Lida de `.env` em `utils.py`. O cliente é o SDK `openai`, mas a base URL é configurável — o **default é Gemini** (`gemini-2.5-flash-preview-04-17` via endpoint OpenAI-compat do Google):

- `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` (cai para `GEMINI_API_KEY`/`OPENAI_API_KEY`).

Todas as chamadas usam `temperature=0` e `response_format={"type": "json_object"}`. `call_model` em `llm_analysis.py` tem retry com backoff para 429 (parseia `retryDelay` da mensagem de erro).

## Arquitetura

Aplicação **Flask monolítica** (servidor único, SQLite, processamento assíncrono via threads). Fluxo geral: rota → controller → camada ORM.

### Camadas

- **`app.py`** — registra TODAS as rotas (páginas Jinja + API JSON) e filtros Jinja. Cada rota é um wrapper fino que chama um controller. Único arquivo de roteamento; não há blueprints.
- **`controllers/`** — lógica de negócio por domínio (therapy_groups, therapy_sessions, evaluations, interventions, revisions, admin, transcript_upload). Controllers **não** abrem conexões diretamente para escrita do pipeline; usam `db/orm.py`.
- **`db/`** — `connection.py` expõe `get_db()` (context manager, conexão curta por request); `orm.py` tem as funções de transação (re-exportadas por `db/__init__.py`, importado como `import symptoms_analyser.db as orm`); `schema.sql` é a fonte única do schema (10 tabelas: users, therapy_groups, patients, therapy_sessions, therapy_session_patients, transcripts, tdpm_evaluations, evaluation_telemetry, patient_item_scores, session_clinical_analyses).
- **`pipeline/`** — `preprocessing.py` (Fase 1: extrai `.docx`/`.txt`, anonimização local nome→pseudônimo), `llm_analysis.py` (Fase 2: avaliação TDPM-20 via `evaluate_symptoms_with_tdpm` + análise clínica qualitativa via `generate_clinical_analysis`), `orchestrator.py` (encadeia as fases).
- **`prompts/*.md`** — prompts de sistema lidos em runtime (`tdpm_evaluation.md`, `clinical_analysis.md`). `data/tdpm_ontology.json` mapeia códigos de dimensão/item para nomes; carregado no import de `llm_analysis.py`.

### Pipeline assíncrono (importante)

Upload (`controllers/transcript_upload.py`) salva o arquivo, cria um `task_id` (UUID) num dict **`tasks` em memória** e dispara `process_transcript_pipeline` numa `threading.Thread`. O frontend faz polling em `/api/status/<task_id>`. Consequências:

- O estado das tasks é volátil — some quando o servidor reinicia.
- Com `debug=True` o reloader do Flask roda dois processos; threads de background podem se comportar de forma inesperada ao salvar.

### Dois padrões de conexão SQLite — não misturar

1. **Por request (controllers de leitura):** `with get_db() as conn:` — conexão curta, fecha sozinha.
2. **Pipeline:** o orchestrator abre **uma conexão WAL de vida longa** e a passa explicitamente como `db_conn=` para cada função do ORM, mantendo tudo na mesma transação/conexão durante o processamento. Funções do ORM aceitam `db_conn` opcional e caem para `get_db()` quando ausente. Ao adicionar steps ao pipeline, **propague o `db_conn`** — não abra uma nova conexão.

Todas as conexões aplicam `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`.

### Pontuação TDPM-20

A transcrição é dividida em chunks por timestamp (`split_into_chunks`) e reagrupada em lotes (`merge_chunks`, `blocks_per_call=100` por padrão). Cada chunk vai ao LLM separadamente; `aggregate_chunk_results` consolida pegando o **maior score por item** entre os chunks e calculando a média por dimensão (divisor = número de itens da dimensão na ontologia, não só os pontuados). As `top3` dimensões guiam a análise clínica qualitativa. Resultados viram registros relacionais via `orm.create_patient_item_score` (com citações/evidências e timestamp extraído).

## Convenções e armadilhas

- **Pseudônimos de paciente** seguem o formato `PacienteN` (validado por regex `^Paciente\d+$` nas rotas admin). Pacientes são "self-healing": `find_or_create_patient` cria sob demanda durante a análise.
- **Usuário atual hardcoded:** `inject_current_user` em `app.py` busca `users.id = 2` — não há autenticação ainda (ver TODO no código).
- `app.secret_key` está hardcoded no `app.py`.
- Schema só muda em `schema.sql`; depois rode `setup_db.py`. Não há framework de migração: para bancos já existentes, escreva um script one-off de migração (padrão: ALTER + backup `.bak`, ex. `scripts/migrate_clinical_analysis_rename.py`), ou recrie do zero com `make db-prune`. SQLite não faz ALTER de CHECK constraint — edite a DDL via `PRAGMA writable_schema` (ver o script citado).
- Scripts em `scripts/` são utilitários one-off de migração/backfill (`migrate_files_to_db.py`, `migrate_groups.py`, `backfill_clinical_analyses.py`, `migrate_clinical_analysis_rename.py`); inserem o project root no `sys.path` manualmente.
