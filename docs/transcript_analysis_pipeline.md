# Pipeline de análise de transcrição

Este documento descreve o fluxo de trabalho, o fluxo de dados e a arquitetura de modularidade do pipeline de processamento de transcrições do **Symptoms Analyser**.

---

## 1. Diagrama de sequência

O diagrama abaixo mapeia as etapas sequenciais executadas pelo orquestrador durante o processamento de uma transcrição:

```mermaid
sequenceDiagram
    autonumber
    participant Orch as Orquestrador do pipeline (orchestrator.py)
    participant Prep as Pré-processamento (preprocessing.py)
    participant LLM_Ana as Análise com LLM (llm_analysis.py)
    participant LLM as Provedor de LLM (API externa)
    participant ORM as Camada ORM (orm.py)
    participant DB as Banco de dados SQLite

    Note over Orch: process_transcript_pipeline(task_id, filepath, session_id, auto_fill)
    activate Orch

    Orch->>Prep: extract_text(file)
    activate Prep
    Prep-->>Orch: metadata, raw_text
    deactivate Prep

    Orch->>Prep: anonymize_text(raw_text)
    activate Prep
    Prep-->>Orch: anonymized_text, mappings
    deactivate Prep

    Orch->>Prep: create_transcript(file, session_id, raw_text, anonymized_text, metadata)
    activate Prep
    Prep->>ORM: create_transcript(session_id, filename, file_type, raw_text, anonymized_text)
    ORM->>DB: INSERT INTO transcripts (status='preprocessing')
    DB-->>ORM: transcript_id
    
    alt extract_metadata == True
        Prep->>Prep: Estima duração e analisa data de início
        Prep->>ORM: update_therapy_session(session_id, name, start_at, duration)
        ORM->>DB: UPDATE therapy_sessions
    end
    Prep-->>Orch: transcript_id
    deactivate Prep

    loop Para cada paciente detectado na anonimização
        Orch->>ORM: find_or_create_patient(pseudonym, real_name)
        ORM->>DB: INSERT OR IGNORE INTO patients
        Orch->>ORM: link_patient_to_session(session_id, pseudonym)
        ORM->>DB: INSERT OR IGNORE INTO therapy_session_patients
    end

    Orch->>ORM: update_transcript(transcript_id, status='preprocessed')
    ORM->>DB: UPDATE transcripts

    Orch->>LLM_Ana: evaluate_symptoms_with_tdpm(transcript_id)
    activate LLM_Ana
    LLM_Ana->>ORM: update_transcript(status='analyzing')
    ORM->>DB: UPDATE transcripts
    
    loop Para cada bloco de transcrição
        LLM_Ana->>LLM: Envia bloco com prompt (avaliação de sintomas)
        LLM-->>LLM_Ana: Retorna pontuações extraídas
    end

    LLM_Ana->>ORM: create_tdpm_evaluation(transcript_id, session_id, clinician)
    ORM->>DB: INSERT INTO tdpm_evaluations
    DB-->>ORM: evaluation_id
    
    LLM_Ana->>ORM: create_evaluation_telemetry(evaluation_id, metrics)
    loop Para cada pontuação (item de score por paciente)
        LLM_Ana->>ORM: create_patient_item_score(evaluation_id, score_details)
    end
    
    LLM_Ana->>ORM: update_transcript(transcript_id, status='completed')
    ORM->>DB: UPDATE transcripts
    deactivate LLM_Ana

    Orch->>LLM_Ana: generate_clinical_synthesis(transcript_id)
    activate LLM_Ana
    LLM_Ana->>LLM: Envia transcrição completa com prompt (síntese clínica)
    LLM-->>LLM_Ana: Retorna nota de progresso e mapeamento de interações
    LLM_Ana->>ORM: create_session_synthesis(transcript_id, group_progress_note, interactions_mapping)
    ORM->>DB: INSERT INTO session_syntheses
    deactivate LLM_Ana
    deactivate Orch
```

---

## 2. Arquitetura do pipeline

A orquestração do pipeline é projetada para rodar de forma assíncrona e desacoplada dos controladores HTTP (web).

### 2.1. Orquestração e fluxo de execução

1. **Gatilho e assincronismo**: Quando uma nova transcrição é recebida, o controlador `controllers/transcript_upload.py` delega o processamento ao orquestrador iniciando uma thread em segundo plano com a função `process_transcript_pipeline` (em `pipeline/orchestrator.py`). Isso permite que a requisição HTTP responda de imediato com um identificador de tarefa (`task_id`), evitando o bloqueio da interface do usuário.
2. **Monitoramento e polling**: Durante a execução, o orquestrador atualiza um dicionário global de tarefas em memória (`tasks`), registrando mensagens de log detalhadas e o status atual. O cliente consome esses dados via requisições de consulta periódica (*polling*) para atualizar a barra de progresso na interface.
3. **Conexão e concorrência no banco de dados**: Para garantir a integridade transacional no SQLite durante o processamento em segundo plano, o orquestrador gerencia conexões dedicadas configuradas explicitamente com o modo Write-Ahead Logging (WAL) ativo e tratamento robusto de travamentos.
4. **Sequenciamento de etapas**: O fluxo executa as etapas de forma sequencial, atualizando o status do registro a cada transição:
   * **Extração de texto**: Lê o arquivo de entrada físico (`.txt` ou `.docx`) e extrai o texto bruto e metadados básicos.
   * **Anonimização local**: Realiza a substituição de nomes próprios de pacientes por pseudônimos estruturados (ex: `Paciente1`), consultando registros existentes para manter a consistência e criando automaticamente novas relações de paciente/sessão.
   * **Criação do registro**: Salva a transcrição no banco de dados com o status `preprocessed` e, caso configurado, atualiza os metadados da sessão de terapia associada (como nome público estimado e duração).
   * **Avaliação clínica TDPM-20**: Divide a transcrição em blocos e envia-os de forma iterativa ao provedor de LLM para pontuar as dimensões clínicas.
   * **Síntese clínica**: Invoca o provedor de LLM para gerar uma análise qualitativa (nota de progresso do grupo) e o mapa de interações sociais da sessão.

O diagrama de blocos abaixo descreve como os componentes se relacionam e interagem com o banco de dados:

```mermaid
flowchart TD
    Upload[Formulário de upload de arquivo]

    UploadHandler[controller.transcript_upload]

    ThreadLinear[orchestrator.process_transcript_pipeline\n*Worker sequencial assíncrono*]

    subgraph Preprocessing [Pré-processamento]
        Extract[preprocessing.extract_text]
        Anon[preprocessing.anonymize_text]
        Create[preprocessing.create_transcript]
    end
    subgraph LLMAnalysis [Análise com LLM]
        TDPM[llm_analysis.evaluate_symptoms_with_tdpm]
        Synth[llm_analysis.generate_clinical_synthesis]
    end

    DB[(Banco de dados)]

    Upload --> UploadHandler
    UploadHandler --> ThreadLinear
    
    %% Fluxo atual (setas contínuas)
    ThreadLinear -->|Passo 1| Extract
    ThreadLinear -->|Passo 2| Anon
    ThreadLinear -->|Passo 3| Create
    ThreadLinear -->|Passo 4| TDPM
    ThreadLinear -->|Passo 5| Synth
    
    Anon -.->|Lê| DB
    Create -.->|Escreve| DB
    TDPM -.->|Lê/Escreve| DB
    Synth -.->|Lê/Escreve| DB
```

### 2.2. Máquina de estados do processamento

O progresso e o ciclo de vida do pipeline são gerenciados por meio de uma máquina de estados persistida na coluna `status` da tabela `transcripts`. Esse controle permite monitorar o progresso em tempo real e identificar pontos de falha:
*   **queued**: A transcrição foi recebida e aguarda o início do processamento.
*   **preprocessing**: O texto está sendo extraído e anonimizado localmente.
*   **preprocessed**: A etapa de pré-processamento foi concluída com sucesso e o arquivo está pronto para a análise clínica.
*   **analyzing**: O pipeline está executando a avaliação clínica TDPM-20 e a síntese por meio de chamadas à API de LLM.
*   **completed**: Todo o fluxo foi finalizado com sucesso e os resultados estão salvos.
*   **failed**: Ocorreu um erro em alguma das etapas (com o rastreamento salvo na coluna `error_message`).
