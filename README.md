# Contexto do Projeto

## Visão geral
Este projeto aplica análise de sintomas baseada em IA a transcrições de **sessões de terapia em grupo** focadas em **transtornos aditivos**. É parte do meu **Trabalho de Conclusão de Curso (TCC)**, realizado na UFRGS.

## Avaliação de sintomas TDPM-20
A análise é fundamentada na escala **TDPM-20 (Transtorno Disregulatório Predostático da Mente — Transdiagnostic Dysregulation of the Predostatic Mind)**, uma ferramenta transdiagnóstica para avaliação de desregulação psicopatológica em indivíduos com transtornos aditivos. Integra dimensões emocionais, cognitivas, comportamentais e psicofisiológicas, aplicável em contextos clínicos e de pesquisa.

O TDPM-20 foi desenvolvido a partir do framework **DREXI3** (pela pesquisadora Patrícia Furtado Martins), iniciado pelo grupo de estudos do **Centro de Pesquisa de Álcool e Drogas (CPAD)** do **Hospital de Clínicas de Porto Alegre**, coordenado pelo **Dr. Felix Kessler**.

### Regras de pontuação
- Cada dimensão possui **2 itens**, exceto *Espectro Ansiedade/Fobia/Pânico*, que possui **3 itens** — totalizando **41 itens**.
- Todos os itens são pontuados em uma **escala de 0 a 4** (0 = ausente; 4 = grave).
- **Regra de desempate (sensibilidade clínica):** Em caso de dúvida entre duas pontuações possíveis (ex.: 1 vs. 2), atribuir sempre a **pontuação mais alta** para evitar subestimar a gravidade.
- O **escore da dimensão** é a **média dos seus itens** (intervalo 0–4).

### Etapas da avaliação
1. **Identificação** dos sintomas relevantes em cada dimensão.
2. **Pontuação** por item e cálculo da média dimensional, possibilitando a visualização de um perfil dimensional.
3. **Síntese clínica** destacando as **3 dimensões prioritárias** para intervenção, incluindo notas de impacto funcional, possíveis gatilhos e estratégias de manejo acordadas.

### As 20 dimensões do TDPM-20
| Desregulação | # | Dimensão | Itens (Critérios de Avaliação) |
|---|---|---|---|
| **Neurofisiológica** | 1 | Desregulação do Apetite | • Mudanças marcantes no apetite (comer demais/perder a fome)<br>• Alteração do comportamento alimentar para um padrão pouco saudável |
| | 2 | Desregulação do Sono | • Dificuldade para iniciar/manter o sono ou despertar (insônia)<br>• Alteração do ciclo sono-vigília ou sonolência diurna |
| | 3 | Desregulação da Energia / Ânimo | • Baixa ou alta energia/disposição para atividades usuais<br>• Oscilações de ânimo que afetam produtividade/engajamento |
| | 4 | Desregulação da Libido | • Alteração do desejo sexual (aumento/diminuição)<br>• Dificuldades de desempenho/satisfação sexual |
| | 5 | Dor / Sintomas Somáticos | • Dores/desconfortos corporais frequentes ou crônicos<br>• Sintomas físicos (tensão, cefaleia, GI) associados a estresse |
| **Neuropsicológica** | 6 | Alteração da Consciência | • Sensação de "desligamento", confusão ou despersonalização<br>• Flutuações do estado de alerta que atrapalham atividades |
| | 7 | Desregulação da Orientação | • Episódios de desorientação (tempo, lugar, pessoas)<br>• Necessidade de ajuda/pistas para se situar |
| | 8 | Memória / Comunicação | • Esquecimentos de curto, médio e longo prazo<br>• Alterações perceptíveis da evocação da linguagem |
| | 9 | Desregulação da Atenção | • Distraibilidade<br>• Dificuldade de manter foco até concluir tarefas |
| | 10 | Alteração da Sensopercepção | • Percepções incomuns (sons/imagens/sensações) não compartilhadas<br>• Hiper/hipossensibilidade sensorial que causa desconforto |
| **Busca** | 11 | Desregulação da Volição | • Baixa volição percebida de forma subjetiva<br>• Alta volição (ex: fissura/craving) |
| | 12 | Impulsividade | • Ações impulsivas/precipitadas (motoras)<br>• Decisões sem ponderar consequências (decisional) |
| | 13 | Conexão Social | • Evitação/isolamento social, sensação de desconexão<br>• Dificuldade de manter vínculos/reciprocidade nas relações |
| | 14 | Compulsão | • Comportamentos/pensamentos repetitivos difíceis de controlar<br>• Tempo gasto com rituais/checagens que interferem no dia a dia |
| | 15 | Restrição / Purgação | • Restrição alimentar rígida ou compensações (jejum, exercício)<br>• Episódios de purgação ou culpa intensa após comer |
| **Alarme** | 16 | Espectro Ansiedade / Fobia / Pânico | • Ansiedade/tensão excessivas em situações cotidianas<br>• Evitação de lugares/situações por medo ou antecipação ansiosa (fobia)<br>• Ataques de pânico (taquicardia, falta de ar, tremor, medo de perder o controle) |
| | 17 | Espectro Irritabilidade / Raiva | • Irritabilidade/baixa tolerância; Explosões de raiva<br>• Rancor/ressentimento mantidos após conflitos |
| | 18 | Espectro Desconfiança / Agressividade | • Tendência a interpretar intenções alheias como hostis<br>• Respostas duras/ameaçadoras/agressivas em desacordos |
| | 19 | Espectro Tristeza / Depressão | • Humor deprimido, anedonia, vazio, desesperança, desvalorização<br>• Ruminação negativista; Autoestima/autoimagem rebaixada |
| | 20 | Espectro Euforia / Mania | • Períodos de humor elevado/eufórico; Aceleração do pensamento<br>• Comportamentos expansivos e pensamentos grandiosos |

## Dados
- **Fonte:** Transcrições de sessões de terapia em grupo realizadas via plataforma de vídeo online
- **Idioma:** Português Brasileiro (PT-BR)
- **Formato:** `.docx`
- **Origem da transcrição:** Transcrição automática pela ferramenta de IA da plataforma

### Estrutura da transcrição
- **Cabeçalho:** Data + horário da reunião (UTC) + rótulo "Transcrição"
- **Timestamps:** Aparecem como quebras de seção a cada ~1 minuto (ex.: `00:00:00`, `00:01:23`), **não** por fala individual
- **Rótulos de locutor:** `Terapeuta:` e `Paciente1:` a `Paciente5:` (anonimização numérica já aplicada na origem)
- **Anonimização no texto:** Nomes reais substituídos por tokens como `Fulano1`, `Fulano2`
- **Tamanho do grupo:** Até 5 pacientes + 1 terapeuta por sessão

## Stack tecnológico
- **Linguagem:** Python 3.11+
- **Framework Web:** Flask 3 + Werkzeug
- **IA/LLM:** OpenAI API (`openai>=1.0.0`)
- **Leitura de Documentos:** `python-docx` (ingestão de transcrições `.docx`)
- **Armazenamento:** SQLite (com modo WAL e imposição de chaves estrangeiras)
- **Gerenciador de Pacotes:** `uv`
- **Testes:** `pytest`

## Estrutura do código-fonte

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
│   ├── therapy_groups.py        # Gestão de grupos terapêuticos e análise de redes sociais (dinâmicas de grupo)
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

## Documentação adicional
- [`docs/db_architecture.md`](docs/db_architecture.md) — Esquema do banco de dados e arquitetura de armazenamento
- [`docs/transcript_analysis_pipeline.md`](docs/transcript_analysis_pipeline.md) — Pipeline de análise de transcrições (fluxo, fases e diagrama de sequência)
- [`docs/design_system.md`](docs/design_system.md) — Sistema de design da interface web

## Orientação / instituição
- **Instituição:** UFRGS
- **Curso:** Engenharia de Computação
- **Orientadora:** Dra. Erika Fernandes Cota
