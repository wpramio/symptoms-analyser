# Symptoms Analyser — Plan

## Transcript Handling Strategy

### Option A — Analyze as-is
**Pros:** No preprocessing bias, reflects real-world conditions, simpler pipeline.
**Cons:** Split sentences will likely cause the LLM to miss context and score dimensions incorrectly. Noise tokens (`Да`, `Yrym`) could confuse the model. Results would be hard to validate.

**Verdict:** ❌ Risky for quality. Acceptable only as a *baseline* to compare against cleaned versions.

---

### Option B — Manual sanitization + synthetic expansion
**Pros:** Clean, controlled data. Synthetic set gives volume.
**Cons:** Manual work is slow and introduces **your own interpretation bias** into the transcripts. Synthetic data from a non-clinician may not reflect real psychopathological patterns accurately. Hard to justify academically without a clinician co-authoring the synthetic data.

**Verdict:** ⚠️ High effort, high bias risk. Not ideal unless a clinician validates each synthetic transcript.

---

### Option C — Automated sanitization + LLM-based synthetic generation from originals
**Pros:** Maximally reproducible, academically justifiable, preserves real speech patterns, scalable. The synthetic data inherits real linguistic and emotional texture from actual sessions.
**Cons:** You must validate that the sanitization didn't distort meaning. Synthetic generation must be carefully prompted and documented.

**Verdict:** ✅ Best option. This is also publishable as a **methodology contribution** in itself.

---

### Option D — Automated sanitization only, no synthetic data
**Pros:** Simpler than C, still academically rigorous if the sanitization pipeline is well-documented. Works if your real dataset is large enough.
**Cons:** Dataset may be too small for robust analysis.

**Verdict:** ✅ Good if dataset size is sufficient. Can be combined with C.

---

## Recommendation

**Go with C + D combined:**

1. **Automated sanitization pipeline** on all real transcripts (documented, reproducible)
2. **Use sanitized real transcripts** as the primary analysis dataset
3. **Generate synthetic transcripts** via LLM prompted with sanitized originals + TDPM-20 dimension profiles, validated by the therapist/supervisor
4. Use synthetic set for **testing and prompt tuning only**, keeping real transcripts for final evaluation

---

## On Academic Documentation of the Sanitization Pipeline

Automating sanitization and documenting it thoroughly is not just good practice — in a TCC/academic context it is **mandatory** for:

- **Reproducibility** — another researcher must be able to replicate your pipeline
- **Validity** — you must show the cleaning didn't distort clinical meaning
- **Ethics** — transformations on sensitive health data must be traceable

The sanitization pipeline itself could be a **standalone contribution** of the paper, described in a *"Materials and Methods"* section covering:

| Step | What to document |
|---|---|
| Split sentence reconstruction | Algorithm/heuristic used, edge cases |
| Noise token removal | Regex rules, token blacklist |
| Backchannel handling | Kept, stripped, or labeled separately |
| Anonymization verification | Confirm no real names leaked through |
| Validation | % of sentences affected, before/after examples |

---

## AI-based Sanitization

### Why AI over rule-based approaches
Rule-based approaches (regex, heuristics) are brittle for this problem because:
- Split sentences require **understanding context** to know which fragments belong together
- Noise tokens like `Yrym` vs `Uhum` require **judgment**, not just pattern matching
- Backchannels are sometimes meaningful (e.g., a patient saying `"Sim."` as genuine agreement vs. filler)

An LLM handles all three naturally, as it understands PT-BR conversational context.

### AI Sanitization Steps

| Step | LLM Task |
|---|---|
| **Sentence reconstruction** | Merge split turns from the same speaker based on conversational flow |
| **Noise removal** | Identify and remove hallucinated tokens (Cyrillic, garbled words) |
| **Backchannel labeling** | Classify short responses as `[filler]` or `[meaningful]` |
| **Anonymization check** | Flag any possible real names that slipped through |
| **Output normalization** | Produce clean, structured transcript in a consistent format |

### Academic Justification Requirements
Fully justifiable **if:**
- A **fixed, documented model version** is used (e.g., `gpt-4o-2024-08-06`)
- The sanitization **prompt is published** in the appendix
- **Before/after examples** are included in the methodology section
- A **human reviewer** (ideally the therapist) spot-checks a sample of sanitized transcripts
- An **agreement metric** between AI-sanitized and human-reviewed versions is reported

### Pipeline
```
Raw .docx
  → [Step 1] text extraction (python-docx)
  → [Step 2] AI sanitization prompt (LLM API)
  → [Step 3] structured clean transcript (plain text / JSON)
  → [Step 4] human spot-check sample
  → [Step 5] final dataset
  → [Step 6] TDPM-20 analysis prompt (LLM API)
  → [Step 7] output (scores + report)
```

---

## Pipeline Architecture

### Why API over UI
The pipeline sends transcripts to an LLM via **API** (not a web UI), because:
- `.docx` files cannot be sent directly to most LLM APIs — text must be extracted first
- API usage is **reproducible and scriptable**, unlike manual UI uploads
- The exact text sent to the model can be **logged**, which is required for academic validity

### Technology Stack

| Component | Tool |
|---|---|
| `.docx` text extraction | `python-docx` |
| LLM API calls | `openai` Python SDK (or equivalent) |
| Transcript storage | Plain `.txt` or `.json` per session |
| Orchestration | Python script |
| Logging | JSON log per session (raw input, prompt, raw output, sanitization log) |

### Step-by-step

#### Step 1 — Text Extraction
- Use `python-docx` to read the `.docx` file and extract paragraphs
- Preserve speaker label formatting (`Bold: text` → `Speaker: text`)
- Preserve timestamp markers
- Output: plain text string

#### Step 2 — AI Sanitization
- Send extracted text to LLM using the sanitization prompt (`prompts/sanitization.md`)
- Use a **fixed, pinned model version** and log it per run
- Output: sanitized transcript + sanitization log

#### Step 3 — Human Spot-check
- For a sample of sessions, the therapist or supervisor reviews the sanitized transcript against the original
- Agreement is measured and reported in the methodology

#### Step 4 — TDPM-20 Analysis
- Send sanitized transcript to LLM using the analysis prompt
- Output: TDPM-20 dimension scores per session (and optionally per speaker)

#### Step 5 — Output & Reporting
- Store results as structured JSON
- Generate human-readable report per session

---

## Design Decisions

### Timestamps — Keep as-is
Timestamps in the raw transcript have **minute-level precision** (e.g., `00:04:09`), not per-utterance. Despite the low granularity, they are kept in the sanitized transcript because:
- They preserve **session progression** — it is possible to observe whether a dimension appears early or late in the session, which may carry clinical relevance (e.g., anxiety escalating over time)
- They act as natural **chunk boundaries** for splitting long transcripts if needed for LLM context window management
- They are useful for **longitudinal tracking** within a session, even approximately
- Discarding them would lose traceability without meaningful gain

The original timestamp values are preserved verbatim — no conversion to block indices.

### LLM Model Choice
Models can be run via cloud APIs or locally, depending on the stage of work and available hardware:

**Cloud APIs:**
- **Development/testing:** `Gemini 3 Flash` (Google) — free tier, strong PT-BR quality, OpenAI-compatible API. Note that free tiers have strict rate limits, making concurrent execution impractical.
- **Final/academic runs:** `GPT-4o` or `GPT-4.1 mini` (OpenAI) — well-documented, strictly pinnable model versions, which is required for reproducibility.

**Local Execution (Recommended for users with a dedicated GPU):**
Since the project uses the `openai` Python SDK and `.env` configuration, it is 100% ready to run local, OpenAI-compatible servers (e.g., via **Ollama** or **LM Studio**) without code changes. This bypasses rate limits entirely and allows for fast, concurrent processing.

For a system with at least 6GB of VRAM (e.g., RTX 2060), you can fit a 4-bit quantized 7B-9B parameter model entirely in GPU memory, yielding 30-50+ tokens per second:
- **Llama 3 (8B) / Mistral (7B):** Highly capable models that understand PT-BR exceptionally well, especially when the system prompt is in English.
- **Qwen 2 (7B) / Gemma 2 (9B):** Exceptionally strong at multilingual tasks.
- **Dedicated PT-BR Fine-tunes:** e.g., Bode or Maritaca AI models.

#### Privacy & Ethics
Cloud-based APIs receive the transcript content externally. Before using any cloud API, confirm:
- Ethics committee approval covers external data processing
- UFRGS / CPAD data handling policies permit it
- Transcripts are sufficiently anonymized prior to transmission

This decision must be **explicitly documented** in the paper's methodology section.

### Chunking Strategy

#### Why chunking is necessary
A full session transcript (~1300 lines, ~73KB) exceeds the practical **output token limit** of current LLMs. Even models with large context windows have a much smaller output limit — in early testing, a single-call attempt was silently truncated at ~2621 completion tokens, sanitizing only ~8% of the transcript. Splitting by timestamp blocks (one ~1 minute block per call) keeps each output well within limits.

#### Tradeoffs of `--chunks-per-call N`

API call latency is dominated by a fixed overhead per call (network round trip, prompt processing — typically ~2s), not by input size. Output generation scales with completion tokens but is fast. This means **fewer calls = much faster overall**, even if each individual call takes slightly longer:

| `--chunks-per-call` | Calls (67-block session) | Est. total time | Quality risk |
|---|---|---|---|
| 1 | 67 | ~167s | Lowest — may miss cross-boundary sentence splits |
| 4 | 17 | ~68s | Low |
| **6** | **12** | **~54s** | **Low — recommended sweet spot** |
| 10 | 7 | ~38s | Moderate — model attention may dilute |
| 15 | 5 | ~30s | Higher |

The output token budget per call is `max_tokens=8192`, and each ~1 min block produces ~300 completion tokens on average, giving a theoretical ceiling of ~27 chunks per call (⌊8192/300⌋≈27) — but 6 provides good headroom and covers ~6 minutes of session per call, a coherent conversational segment.

**Recommendation:** Use `--chunks-per-call 6` as the default. Use `--chunks-per-call 1` only when traceability is the priority (e.g., debugging or final academic runs where per-block attribution matters).

## Synthetic Data Generation Pipeline

To rigorously evaluate the accuracy and resilience of the TDPM analysis pipeline (`tdpm_analyse_llm.py`), the architecture includes a pipeline for generating synthetic, realistic therapy transcripts based on the real sanitized transcripts. This serves as a ground-truth dataset.

### Design Decisions
The following key design decisions were established for the synthetic generation pipeline:

1. **Controlled Symptom Injection:**
   The generation of synthetic transcripts follows a controlled approach. Specific TDPM symptoms (e.g., `16.1`, `16.3`) are explicitly passed to the generator (e.g., via CLI arguments) to be injected into specific patient utterances. This deterministic approach ensures that the ground-truth dataset is known, measurable, and highly specific to the tests being run. 
   *(Alternative Considered: Randomized Symptom Injection was rejected because it lacks traceability, makes it difficult to isolate and test specific edge cases or dimensions, and complicates the creation of a rigorous, reproducible ground-truth dataset.)*

2. **Full Chunk Rewriting:**
   Instead of modifying only specific, isolated utterances, the LLM is instructed to rewrite the entire transcript chunk. This ensures that the conversation flows naturally, maintaining clinical realism, coherent contextual responses from other patients/therapists, and logical continuity, which is crucial for testing the LLM's true contextual reasoning capabilities.
   *(Alternative Considered: Targeted Utterance Replacement — altering only the specific sentence of a patient — was rejected because it often leads to disjointed conversations. For example, if a patient's statement is heavily altered to show a symptom, the therapist's subsequent response in the original transcript might no longer make logical sense, breaking the realism of the session.)*

### Dataset Generation Strategy

When generating the synthetic ground-truth dataset, the approach is to focus on a **Representative Subset** rather than attempting 100% ontology coverage by brute-forcing all 40 TDPM items into the limited set of available real transcripts. 

This strategy was chosen to mitigate two major risks:
1. **Contextual Mismatch (The "Frankenstein" Effect):** Forcefully injecting symptoms that do not align with the original topic of the conversation (e.g., injecting "grandiosity" into a discussion deeply focused on grief) results in highly artificial and disjointed dialogue. If the analysis script fails on these chunks, it is impossible to determine if the failure was due to the analyzer's shortcomings or the poor quality of the synthetic text.
2. **Lack of Diversity (Overfitting):** Repeatedly generating dozens of synthetic transcripts from the exact same base conversations risks overfitting the analysis pipeline to specific therapist styles, patient personas, and sentence structures, rather than proving the architecture's generalizability.

By selecting 5 to 10 diverse dimensions (e.g., Anxiety, Sleep, Psychosis, Impulsivity) and carefully matching them to appropriate conversational contexts within the real transcripts, the resulting dataset provides a rigorous, realistic, and methodologically sound validation of the pipeline's capabilities.

### From-Scratch Generation with Style References

To further expand the synthetic dataset while completely avoiding the constraints of the 2 base transcripts, the pipeline supports generating entire 30-minute therapy sessions from scratch. 

To ensure these entirely fabricated sessions remain clinically and linguistically authentic, the architecture employs a **Few-Shot Style Reference Injection**:
1. The generation script (`generate_from_scratch.py`) extracts a random ~4-minute chunk from one of the real sanitized transcripts.
2. This chunk is explicitly passed to the LLM as a `[STYLE_REFERENCE]`.
3. The LLM is instructed to strictly mimic the vocabulary, slang, sentence structure, and conversational pacing found in the reference, while inventing a completely new narrative designed to showcase the requested TDPM symptoms.

This approach guarantees full control over symptom injection while preserving the deep linguistic texture of the real therapy groups, preventing the synthetic data from sounding generic or artificial.
