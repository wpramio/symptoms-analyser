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
| # | Dimension |
|---|-----------|
| 1 | Espectro Ansiedade / Fobia / Pânico |
| 2 | Espectro Raiva / Irritabilidade |
| 3 | Espectro Desconfiança / Agressividade |
| 4 | Espectro Tristeza / Depressão |
| 5 | Espectro Euforia / Mania |
| 6 | Desregulação da Volição |
| 7 | Desregulação da Conexão Social |
| 8 | Impulsividade Decisional / Motora |
| 9 | Compulsão |
| 10 | Restrição / Purgação |
| 11 | Desregulação do Sono |
| 12 | Desregulação da Libido |
| 13 | Desregulação do Apetite |
| 14 | Desregulação da Energia |
| 15 | Desregulação da Orientação |
| 16 | Desregulação da Atenção |
| 17 | Desregulação da Memória / Comunicação |
| 18 | Alteração da Consciência |
| 19 | Alteração da Sensopercepção |
| 20 | Dor / Sintomas Somáticos |

## Data
- **Source:** Transcripts of group therapy sessions conducted via **Google Meet**
- **Language:** Brazilian Portuguese (PT-BR)
- **Format:** `.docx` (primary), `.pdf` available for reference
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