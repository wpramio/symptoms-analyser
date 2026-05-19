# Cost Estimation for TDPM-20 Analysis Pipeline

This document provides a cost estimation across several LLM providers and models for processing clinical sessions. The pipeline consists of two main steps: **Preprocess** (sanitization/speaker diarization) and **Analysis** (TDPM-20 rating).

## Token Usage Estimation

The estimates are based on the existing execution logs (`output/preprocess.log.json` and `output/tdpm_analysis.log.json`).

Average raw text sizes per session:

- `session_2026_03_16.raw.txt`: ~17,000 - 18,500 tokens
- `session_2026_03_23.raw.txt`: ~15,500 - 17,000 tokens

### 1. Preprocess Step
Based on the successful runs (e.g., `gemini-2.5-flash`, `gemini-3-flash-preview`):
*   **Average Prompt Tokens:** ~30,000 tokens per session
*   **Average Completion Tokens:** ~10,000 tokens per session

### 2. Analysis Step
Based on the full-session runs (e.g., `google/gemma-4-31b-it:free`):
*   **Average Prompt Tokens:** ~35,000 tokens per session
*   **Average Completion Tokens:** ~1,500 tokens per session

### Total per Session
*   **Total Input Tokens:** ~65,000 tokens
*   **Total Output Tokens:** ~11,500 tokens

---

## Cost Estimation by Provider

The prices below are estimated per **1 Million (1M) tokens** (in USD).

### Pricing Sources and Freshness
* **Freshness / Date of Estimate:** May 17, 2026.
* **Sources:**
  * **Google (Gemini):** [Google AI Studio Pricing](https://ai.google.dev/pricing) with "flex" tier
  * **OpenAI (GPT-5.4 / GPT-5.5):** [OpenAI API Pricing](https://openai.com/api/pricing/)
  * **Anthropic (Claude Haiku / Sonnet / Opus):** [Anthropic API Pricing](https://www.anthropic.com/pricing)

| Provider | Model | Input Price (/1M) | Output Price (/1M) | Cost per Session | Cost for 100 Sessions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Google** | Gemini 2.5 Flash          | $0.15  | $1.25  | **$0.008** | **$0.83** |
| **Google** | Gemini 2.5 Pro            | $0.625 | $5.00  | **$0.070** | **$6.99** |
| **Google** | Gemini 3.1 Flash-Lite     | $0.125 | $0.25  | **$0.013** | **$1.31** |
| **Google** | Gemini 3.1 Pro Preview    | $1.00  | $6.00  | **$0.070** | **$6.99** |
| **OpenAI** | GPT-5.4 nano              | $0.10  | $0.625 | **$0.024** | **$2.44** |
| **OpenAI** | GPT-5.4 mini              | $0.375 | $2.25  | **$0.016** | **$1.66** |
| **OpenAI** | GPT-5.4                   | $1.25  | $7.50  | **$0.151** | **$15.09** |
| **OpenAI** | GPT-5.5                   | $2.50  | $15.00 | **$0.375** | **$37.53** |
| **Anthropic** | Claude Haiku 4.5       | $1.00  | $5.00  | **$0.083** | **$8.25** |
| **Anthropic** | Claude Sonnet 4.6      | $3.00  | $15.00 | **$0.368** | **$36.75** |
| **Anthropic** | Claude Opus 4.6        | $5.00  | $25.00 | **$0.625** | **$62.50** |
| **Local / Open Weights** | Gemma 4 (Local via Ollama) | $0.00 | $0.00 | **$0.00** | **$0.00** * |

*\* Local models incur hardware and electricity costs rather than direct API fees.*

### Calculation Details per Session

**1. Google Gemini Flash (e.g. 2.5 / 3)**
*   Input: 65k * ($0.075 / 1M) = $0.0048
*   Output: 11.5k * ($0.30 / 1M) = $0.0034
*   **Total: $0.0082**

**2. Google Gemini Pro**
*   Input: 65k * ($1.25 / 1M) = $0.0813
*   Output: 11.5k * ($5.00 / 1M) = $0.0575
*   **Total: $0.1388**

**3. OpenAI GPT-4o-mini**
*   Input: 65k * ($0.15 / 1M) = $0.0097
*   Output: 11.5k * ($0.60 / 1M) = $0.0069
*   **Total: $0.0166**

**4. OpenAI GPT-4o**
*   Input: 65k * ($2.50 / 1M) = $0.1625
*   Output: 11.5k * ($10.00 / 1M) = $0.1150
*   **Total: $0.2775**

**5. Anthropic Claude 3.5 Sonnet**
*   Input: 65k * ($3.00 / 1M) = $0.1950
*   Output: 11.5k * ($15.00 / 1M) = $0.1725
*   **Total: $0.3675**

---

## Recommendations

1. **Production at Scale (Cost-Efficient):** Use **Gemini Flash** or **GPT-4o-mini**. They offer incredibly low costs (less than 2 cents per session) while maintaining enough reasoning capability for sanitization and standard TDPM-20 analysis.
2. **High-Accuracy Analysis:** For the actual TDPM-20 rating (where complex clinical reasoning is required), you might consider using **Gemini Pro**, **GPT-4o**, or **Claude 3.5 Sonnet**. If you use a hybrid approach (e.g., Flash for preprocess, Sonnet for analysis), the cost would be:
   *   Preprocess (Flash): 30k * $0.075/1M + 10k * $0.30/1M = ~$0.005
   *   Analysis (Sonnet): 35k * $3.00/1M + 1.5k * $15.00/1M = ~$0.127
   *   **Total Hybrid Cost:** ~$0.132 per session.
3. **Privacy / Zero API Cost:** Using **Gemma 4** locally via Ollama is ideal for strict privacy compliance and avoiding API costs entirely, provided your hardware can support the 26B/31B parameter models efficiently.
