# Symptoms Analyser — Project Context

## Overview
This project applies AI-based sentiment/symptom analysis to transcripts of **group therapy sessions** focused on **addiction disorder**. It is developed as a **Bachelor's Conclusion Paper (TCC)** at UFRGS.

## Analysis Framework
The analysis is grounded in the **TDPM-20 (Transdiagnostic Dysregulation of the Predostatic Mind — Transtorno Disregulatório Predostático da Mente)** scale, a transdiagnostic tool for psychopathological dysregulation assessment in individuals with addictive disorders. It integrates emotional, cognitive, behavioral, and psychophysiological dimensions, applicable in both clinical and research settings.

The TDPM-20 was developed from the **DREXI3** framework (by researcher Patrícia Furtado Martins), initiated by the study group of the **Centro de Pesquisa de Álcool e Drogas (CPAD)** at **Hospital de Clínicas de Porto Alegre**, led by **Dr. Felix Kessler**.

### Scoring Rules
- Each dimension has **2 items**, except *Espectro Ansiedade/Fobia/Pânico* which has **3 items** — totaling **41 items**.
- All items are scored on a **0–4 scale** (0 = absent; 4 = severe).
- **Tiebreaker rule (clinical sensitivity):** When in doubt between two possible scores (e.g., 1 vs. 2), always assign the **higher score** to avoid underestimating severity.
- The **dimension score** is the **mean of its items** (range 0–4).

### Application Steps
1. **Identification** of relevant symptoms in each dimension.
2. **Scoring** per item and calculation of the dimension mean, enabling a dimensional profile visualization.
3. **Clinical synthesis** highlighting the **top 3 priority dimensions** for intervention, including functional impact notes, likely triggers, and agreed management strategies.

### The 20 TDPM-20 Dimensions
| Category | # | Dimension | Items (Assessment Criteria) |
|---|---|---|---|
| **Neurophysiological** | 1 | Desregulação do Apetite | • Mudanças marcantes no apetite (comer demais/perder a fome)<br>• Alteração do comportamento alimentar para um padrão pouco saudável |
| | 2 | Desregulação do Sono | • Dificuldade para iniciar/manter o sono ou despertar (insônia)<br>• Alteração do ciclo sono-vigília ou sonolência diurna |
| | 3 | Desregulação da Energia / Ânimo | • Baixa ou alta energia/disposição para atividades usuais<br>• Oscilações de ânimo que afetam produtividade/engajamento |
| | 4 | Desregulação da Libido | • Alteração do desejo sexual (aumento/diminuição)<br>• Dificuldades de desempenho/satisfação sexual |
| | 5 | Dor / Sintomas Somáticos | • Dores/desconfortos corporais frequentes ou crônicos<br>• Sintomas físicos (tensão, cefaleia, GI) associados a estresse |
| **Neuropsychological** | 6 | Alteração da Consciência | • Sensação de "desligamento", confusão ou despersonalização<br>• Flutuações do estado de alerta que atrapalham atividades |
| | 7 | Desregulação da Orientação | • Episódios de desorientação (tempo, lugar, pessoas)<br>• Necessidade de ajuda/pistas para se situar |
| | 8 | Memória / Comunicação | • Esquecimentos de curto, médio e longo prazo<br>• Alterações perceptíveis da evocação da linguagem |
| | 9 | Desregulação da Atenção | • Distraibilidade<br>• Dificuldade de manter foco até concluir tarefas |
| | 10 | Alteração da Sensopercepção | • Percepções incomuns (sons/imagens/sensações) não compartilhadas<br>• Hiper/hipossensibilidade sensorial que causa desconforto |
| **Search (Busca)** | 11 | Desregulação da Volição | • Baixa volição percebida de forma subjetiva<br>• Alta volição (ex: fissura/craving) |
| | 12 | Impulsividade | • Ações impulsivas/precipitadas (motoras)<br>• Decisões sem ponderar consequências (decisional) |
| | 13 | Conexão Social | • Evitação/isolamento social, sensação de desconexão<br>• Dificuldade de manter vínculos/reciprocidade nas relações |
| | 14 | Compulsão | • Comportamentos/pensamentos repetitivos difíceis de controlar<br>• Tempo gasto com rituais/checagens que interferem no dia a dia |
| | 15 | Restrição / Purgação | • Restrição alimentar rígida ou compensações (jejum, exercício)<br>• Episódios de purgação ou culpa intensa após comer |
| **Alarm (Alarme)** | 16 | Espectro Ansiedade / Fobia / Pânico | • Ansiedade/tensão excessivas em situações cotidianas<br>• Evitação por medo/antecipação; Ataques de pânico |
| | 17 | Espectro Irritabilidade / Raiva | • Irritabilidade/baixa tolerância; Explosões de raiva<br>• Rancor/ressentimento mantidos após conflitos |
| | 18 | Espectro Desconfiança / Agressividade | • Tendência a interpretar intenções alheias como hostis<br>• Respostas duras/ameaçadoras/agressivas em desacordos |
| | 19 | Espectro Tristeza / Depressão | • Humor deprimido, anedonia, vazio, desesperança, desvalorização<br>• Ruminação negativista; Autoestima/autoimagem rebaixada |
| | 20 | Espectro Euforia / Mania | • Períodos de humor elevado/eufórico; Aceleração do pensamento<br>• Comportamentos expansivos e pensamentos grandiosos |

## Data
- **Source:** Transcripts of group therapy sessions conducted via **Google Meet**
- **Language:** Brazilian Portuguese (PT-BR)
- **Format:** `.docx`
- **Transcription origin:** Automatic transcription by Google Meet's AI tool — **known quality issues:**
  - **Split sentences:** A single utterance is frequently broken across multiple consecutive lines, sometimes misattributed to a different speaker label mid-sentence (e.g., `"...no final de"` / `"semana."` separated by another speaker's line)
  - **Noise tokens:** Transcription hallucinations such as Cyrillic characters (`Да`), garbled tokens (`Yrym`, `Yry`), and ambiguous short tokens (`M.`)
  - **Backchannel intercalation:** Short acknowledgments (`Aham`, `Uhum`, `Sim`, `Né?`) from other participants heavily interrupt the main speaker's turn
  - A **sentence reconstruction / preprocessing step** is required before analysis
- **Anonymization:** Speaker identities replaced with `Terapeuta`, `Paciente1`–`Paciente5`; names within speech replaced with tokens like `Fulano1`, `Fulano2`
- **Session count / dataset size:** *(e.g., X sessions, ~Y words per session)*

### Transcript Structure
- **Header:** Meeting date + time (UTC) + label "Transcrição"
- **Timestamps:** Appear as section breaks roughly every ~1 minute (e.g., `00:00:00`, `00:01:23`), **not** per utterance
- **Speaker labels:** `Terapeuta:` and `Paciente1:` through `Paciente5:` (numeric anonymization already applied at source)
- **In-text anonymization:** Real names replaced with tokens like `Fulano1`, `Fulano2`
- **Group size:** Up to 5 patients + 1 therapist observed per session

### Known Preprocessing Challenges
| Challenge | Decision Needed |
|---|---|
| **Sentence reconstruction** | Should split turns be merged before scoring? How to detect them? |
| **Noise filtering** | Auto-remove Cyrillic/garbled tokens, or flag for manual review? |
| **Unit of analysis** | Score per reconstructed speaker turn? Per timestamp block? Per full session? |
| **Therapist utterances** | Include in TDPM-20 scoring or analyze separately / exclude? |
| **Backchannels** | Strip short filler responses before analysis or keep for context? |

### Clean Verbatim Transcription
Clean verbatim transcription is a style of audio-to-text conversion that removes unnecessary speech elements, such as filler words (e.g., "um," "uh," "like"), stutters, false starts, and background sounds, to make the text highly readable while retaining the exact meaning of the original recording.
This is what we do in `preprocess.py` using LLM.

## Goals
- Automatically identify TDPM-20 dimensions present in therapy session transcripts
- Score intensity per dimension (mean of item scores, 0–4)
- *(Per speaker? Per session?)*
- *(Generate reports? Visualizations? Comparisons over time?)*

## Technical Stack
- **Language:** *(e.g., Python)*
- **AI/LLM:** *(e.g., OpenAI GPT-4, local model, LangChain, etc.)*
- **Frameworks/Libraries:** *(e.g., spaCy, HuggingFace, pandas)*
- **Storage:** *(e.g., JSON, SQLite, CSV)*

## Constraints & Considerations
- All data is in **PT-BR** — models/prompts must handle Brazilian Portuguese
- Ethical handling of sensitive mental health data required
- *(IRB / ethics committee approval? Mention if applicable)*
- *(Is this a retrospective analysis or real-time?)*

## Output Format
*(Describe expected output: e.g., JSON with dimension scores per utterance, summary report per session, etc.)*

## Supervisor / Institution
- **Institution:** UFRGS
- **Course:** Computer Engineering
- **Supervisor:** Dra. Erika Fernandes Cota