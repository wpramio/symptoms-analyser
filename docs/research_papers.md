# Reference Research & Literature

This document outlines the theoretical frameworks and scientific publications that justify and guide the design of the **Symptoms Analyser** application, specifically the **TDPM-20 clinical ontology**, **LLM transcript scraping**, and **automated intervention suggestions**.

---

## 1. Foundational Clinical Framework (DREXI3 / ACERT / TDPM-20)

The transdiagnostic symptom ontology and the dynamic model of the group therapy dashboard (Alarm, Seek, and Balance modes) are based on the DREXI3/ACERT framework developed by researchers at the **Alcohol and Drugs Research Center (CPAD)** of the **Hospital de Clínicas de Porto Alegre (HCPA)**, Brazil.

*   **Proposing an integrative, dynamic and transdiagnostic model for addictions: dysregulation phenomena of the three main modes of the predostatic mind**
    *   *Journal:* Frontiers in Psychiatry (2024)
    *   *Significance:* Explains the core clinical model, defining how externalizing and internalizing symptoms dysregulate the Alarm, Seek, and Balance modes of the predostatic mind.
    *   *Access Link:* [Frontiers in Psychiatry Article](https://doi.org/10.3389/fpsyt.2023.1298002)

*   **Transdiagnostic Pharmacology of Addictions: Current Evidence and Future Perspectives**
    *   *Journal:* MDPI / Brain Sciences (2026)
    *   *Significance:* Expands on the 20 transdiagnostic dimensions (**TDPM-20**) for individualized patient mapping and treatment planning.
    *   *Access Link:* [MDPI Article](https://doi.org/10.3390/futurepharmacol6020019)

---

## 2. LLM-Based Symptom Extraction & Transcript Scraping

The transcript processing pipeline uses Large Language Models to identify symptoms, determine their severity (scores 1–4), and extract Portuguese dialogue snippets as clinical evidence.

*   **A Survey of Large Language Models in Psychotherapy: Current Landscape and Future Directions**
    *   *Publisher:* Association for Computational Linguistics (ACL Findings, 2025)
    *   *Significance:* Establishes a comprehensive taxonomy for LLMs in mental health assessment, diagnosis, and tracking symptom fluctuations.
    *   *Access Link:* [ACL Anthology Publication](https://aclanthology.org/2025.findings-acl.385/)
    *   *DOI:* [10.18653/v1/2025.findings-acl.385](https://doi.org/10.18653/v1/2025.findings-acl.385)

*   **Extracting Symptoms and their Status from Clinical Conversations**
    *   *Publisher:* Association for Computational Linguistics (ACL)
    *   *Significance:* Evaluates automated systems against human annotators for identifying symptoms and their status (present, absent, uncertain) in clinical conversations.
    *   *Access Link:* [ACL Anthology Publication](https://aclanthology.org/2020.acl-main.412/)
    *   *Direct PDF:* [Download PDF from ACL Anthology](https://aclanthology.org/2020.acl-main.412.pdf)

*   **Matching Human Performance in Identifying Symptoms**
    *   *Publisher:* Journal of Biomedical Informatics / PubMed
    *   *Significance:* Assesses LLMs on clinical transcript comprehension, showing that advanced zero-shot/few-shot models can achieve clinical-grade classification accuracy.
    *   *Access Link:* [PubMed Central / NIH Indexing](https://www.ncbi.nlm.nih.gov/pmc/)

*   **Toward Large Language Models as a Therapeutic Tool: Comparing Prompting Techniques to Improve GPT-Delivered Problem-Solving Therapy**
    *   *Significance:* Analyzes prompt engineering strategies for symptom identification and problem-solving therapy workflows.
    *   *Access Link:* [arXiv Preprint](https://arxiv.org/abs/2409.00112)

---

## 3. Automated Clinical Feedback & Intervention Suggestions

The heuristics that trigger intervention panels (e.g., resguiding dominant speakers, identifying group dropout risks, and proposing therapeutic exercises) leverage research in computerized supervision:

*   **LLM-as-a-Supervisor: Mistaken Therapeutic Behaviors Trigger Targeted Supervisory Feedback**
    *   *Significance:* Proposes a novel model for using LLMs to analyze transcripts, detect suboptimal therapist interventions, and suggest real-time clinical adjustments.
    *   *Access Link:* [arXiv Preprint](https://arxiv.org/abs/2508.06915)

*   **Large Language Models Could Change the Future of Behavioral Healthcare: A Proposal for Responsible Development and Evaluation**
    *   *Publisher:* Nature / Mental Health Science
    *   *Significance:* Formulates a clinical science framework for integrating LLMs responsibly as decision-support systems for behavioral intervention.
    *   *Access Link:* [Nature Article](https://doi.org/10.1038/s44184-024-00056-z)

*   **Automated Coding of Psychotherapy Sessions**
    *   *Source:* Lyssn.io Scientific Publications
    *   *Significance:* A collection of peer-reviewed papers validating the use of machine learning and LLMs to code therapist skills (active listening, empathy, validation) and patient engagement, proving its utility in clinical training and quality assurance.
    *   *Access Link:* [Lyssn.io Peer-Reviewed Science Index](https://www.lyssn.io/science/)

*   **Content Coding of Psychotherapy Transcripts Using Labeled Topic Models**
    *   *Significance:* Focuses on using topic modeling to parse conversations, map patient themes, and track progress over time.
    *   *Access Link:* [ResearchGate Publication Listing](https://www.researchgate.net/publication/221617260_Content_Coding_of_Psychotherapy_Transcripts_Using_Labeled_Topic_Models)
