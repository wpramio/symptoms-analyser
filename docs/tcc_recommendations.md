# TCC Recommendations: Symptoms Analyser

For a **Computer Engineering (Engenharia de Computação)** Bachelor's Conclusion Paper (TCC) at **UFRGS**, your thesis must balance the clinical application context with **deep technical rigor**. A simple system demonstration is insufficient; you need to highlight the engineering challenges, architectural choices, algorithmic complexity (graph theory & heuristics), and quantitative validation.

Below is a recommended structure and the most critical topics you should cover in your TCC monograph.

---

## 1. Thesis Structure Overview

| Chapter | Purpose | Computer Engineering Focus |
| :--- | :--- | :--- |
| **1. Introduction** | Contextualize the problem, objectives, and contributions. | Why automated clinical tools are needed; the problem of transcription noise and cognitive overload. |
| **2. Theoretical Foundation** | Establish the scientific basis. | Clinical framework (TDPM-20), LLM-based information extraction, Graph Theory/Social Network Analysis (SNA). |
| **3. System Architecture & Design** | Describe how the system is designed. | Anonymization engines (LGPD), processing pipelines, DB schema design, frontend-backend decoupling. |
| **4. Algorithms & Heuristics** | Detail the custom logic and math. | Sentence reconstruction, Graph metrics (cliques, components), Clinical Decision Support System (CDSS) rules. |
| **5. Evaluation & Results** | Prove that the system works. | LLM accuracy vs. Human clinicians (Gold Standard), latency/cost analysis, utility assessment. |
| **6. Conclusion & Future Work** | Summarize findings and future paths. | Limitations of current LLMs, scale issues, and edge-computing/local deployment. |

---

## 2. Core Topics & How to Frame Them

### Theme A: Natural Language Processing (NLP) & Data Engineering
As a Computer Engineering student, you should frame the transcript ingestion not just as "calling an API," but as an **unstructured data processing pipeline**.
*   **The Transcription Quality Problem:** Document the challenges of automated speech-to-text (STT) outputs from platforms like Google Meet (split sentences, backchannel interruptions, hallucinated tokens like Cyrillic characters).
*   **Transcript Reconstruction Pipeline:** Detail the state-machine/LLM approach to cleaning and reconstruct speaker turns (Clean Verbatim Transcription).
*   **Entity Extraction & Semantic Grounding:** Explain how you map raw Portuguese text into the **TDPM-20 clinical ontology** (41 items, 0–4 scale). Focus on:
    *   *Prompt engineering patterns:* Few-shot learning, JSON schema enforcement, and structured output parsing.
    *   *Fault Tolerance:* Explain the retry loop for LLM JSON failures (handling malformed outputs, API timeouts, or rate limits).

### Theme B: Graph Theory & Social Network Analysis (SNA)
This is a highly valued topic for Computer Engineering examiners because it involves data structures and mathematical modeling.
*   **Group Cohesion Modeling:** Representing group therapy as a directed network graph $G = (V, E)$, where:
    *   $V$ (Vertices): Patients and the Therapist.
    *   $E$ (Edges): Conversational interactions/support links extracted from the synthesis.
*   **Graph Metrics & Algorithms:** Explain the algorithms used to compute:
    *   *Conversational Monopoly (Airtime percentage):* Word count distributions and node dominance.
    *   *Absolute Isolation vs. Vertical Dialogue:* Identifying components or nodes with zero horizontal edges (edges to other patients) vs. only vertical edges (edges to the therapist).
    *   *Cliques and Subgroups:* Finding persistent reciprocal edges over a longitudinal sliding window (e.g., last 3 sessions).
    *   *Cytoscape.js Integration:* Explain client-side visualization optimizations, edge layout calculations, and dynamic node filtering.

### Theme C: Clinical Decision Support System (CDSS) & Heuristics
You are not just storing data; you are building a system that actively reasons to support clinical decisions.
*   **Rule Engine / Heuristic Implementation:** Document the mathematical rules governing the alerts:
    *   *Individual Heuristics:* Consecutive high scores (e.g., $Score = 4$ for $\ge 2$ sessions; $Score = 3$ for $\ge 3$ sessions) and monotonic deterioration trends ($Score_t > Score_{t-1} > Score_{t-2}$).
    *   *Relational Heuristics:* Attendance rate $< 70\%$ coupled with average horizontal interactions $< 1.5$ per session to flag **cumulative dropout risk**.
    *   *Thematic Heuristics:* Semantic keyword search overlap in progress notes across consecutive sessions to flag **thematic stagnation**.
*   **Software Design Patterns:** Highlight the decoupling of heuristic calculations (`_run_heuristics_calculations` in `interventions.py`) from route-handling, making the evaluation engine reusable and testable.

### Theme D: System Architecture & Privacy (LGPD)
*   **Architectural Overview:** Present a diagram (e.g., C4 model or block diagram) showing the separation of concerns:
    *   Ingestion Engine $\rightarrow$ Anonymizer $\rightarrow$ Processing Pipeline $\rightarrow$ DB (SQLite/PostgreSQL) $\rightarrow$ Analytics Backend $\rightarrow$ Interactive Dashboard.
*   **Anonymization & Security:** Because this handles highly sensitive mental health data, focus on LGPD (Brazilian General Data Protection Law) compliance:
    *   *Pseudonymization mapping:* How the system translates real names to persistent pseudonyms (`Paciente1`, `Paciente2`) to track longitudinal progress while preventing identity leakage.
    *   *Data minimization:* Retaining only anonymized text in the database.

---

## 3. The Validation Strategy (Crucial for TCC)

The TCC committee will scrutinize how you evaluated your solution. You must include a dedicated **Results** section showing:

1.  **Symptom Extraction Accuracy (LLM vs. Human):**
    *   Compare the TDPM-20 dimension averages generated by the LLM against evaluations done manually by professional clinicians (your "Gold Standard").
    *   Calculate metrics: Mean Absolute Error (MAE) of dimension scores, and Cohen's Kappa / F1-Score for symptom occurrence detection.
2.  **Performance & Resource Trade-offs:**
    *   Measure the processing latency (in seconds) and token cost (in USD/BRL) for different LLMs (e.g., comparing a high-end model like GPT-4o with a faster, cheaper model like GPT-3.5/Gemini Flash or a local llama-based open-source model).
3.  **Heuristics Utility:**
    *   Present a case study showing how the system successfully raised a "Dropout Risk" alert or "Therapeutic Stagnation" alert, and how a clinician would act upon it.
