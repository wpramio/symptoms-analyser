# Estrutura do código-fonte

```
src/symptoms_analyser/
├── __init__.py
├── app.py                       # Roteamento principal do Flask
├── utils.py                     # Funções auxiliares globais do projeto, configuração de ambiente e LLM
│
├── controllers/                 # CONTROLLERS DE ROTEAMENTO E WEB API
│   ├── __init__.py
│   ├── admin.py                 # Lógica de telemetria e métricas administrativas
│   ├── evaluations.py           # Funções de consulta e alinhamento para avaliações TDPM-20
│   ├── interventions.py         # Ações clínicas heurísticas e cálculos de métricas do dashboard
│   ├── revisions.py             # Criação e validação de avaliações TDPM-20 revisadas por humanos
│   ├── therapy_sessions.py      # Criação/gerenciamento de sessões e estatísticas de tempo de fala da conversa
│   └── transcript_upload.py     # Gatilhos assíncronos de upload de transcrição e gerenciamento de arquivos
│
├── db/                          # CAMADA DE BANCO DE DADOS E ORM
│   ├── __init__.py              # Exportações unificadas de banco de dados e interface de transação
│   ├── connection.py            # Fábrica de contexto de conexão SQLite com WAL e chaves estrangeiras
│   ├── orm.py                   # Funções auxiliares centralizadas de transação SQL e criação de entidades
│   └── schema.sql               # Definições de esquema de banco de dados e migrações SQL DDL
│
└── pipeline/                    # PIPELINE CLÍNICO PRINCIPAL
    ├── __init__.py
    ├── llm_analysis.py          # FASE 2: Análise de LLM (avaliação de sintomas TDPM-20 e síntese)
    ├── orchestrator.py          # Orquestrador do Pipeline: Gerenciador de fluxo assíncrono
    └── preprocessing.py         # FASE 1: Pré-processamento (extração de texto e anonimização local)
```
