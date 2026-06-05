# Painel de Sugestões de Intervenção Terapêutica (Revisado)

Esta versão incorpora as ponderações sobre a participação do terapeuta na rede, o cálculo cumulativo e individualizado do risco de abandono, a detecção de subgrupos baseada na agregação temporal do grafo, alertas para sintomas de gravidade moderada persistente (nota 2) e a **extração inteligente de tópicos e temas das minutas das sessões**.

---

## 1. Ajustes Metodológicos de Rede e Coesão

### A. Inclusão do Terapeuta no Grafo de Interações
Para evitar falsos alertas de isolamento (quando um paciente interage muito com o terapeuta, mas pouco com os pares), o nó do **Terapeuta** é incluído na rede.
* **Mapeamento de Arestas Adicionais:**
  * `Paciente` $\to$ `Terapeuta`: Resposta a indagações diretas, busca por validação profissional ou relato direcionado.
  * `Terapeuta` $\to$ `Paciente`: Pergunta focada, validação clínica ou intervenção de suporte.
* **Nova Regra de Isolamento na Sessão:**
  * **Isolamento Horizontal (Par-a-Par):** O paciente interage apenas com o terapeuta.
  * **Isolamento Absoluto:** O paciente não interage com outros pacientes nem com o terapeuta (ausência total de arestas de entrada/saída).

### B. Prevenção de Abandono (Dropout) Cumulativo
O risco de evasão deixa de ser atrelado à coesão geral do grupo e passa a ser calculado por uma **Métrica de Desengajamento Individual Acumulado**, ponderando:
$$\text{Risco de Abandono} = f(\text{Presença Histórica}, \text{Isolamento Médio Acumulado}, \text{Tendência de Queda})$$

1. **Frequência Histórica:** Taxa de presença do paciente (sessões comparecidas / sessões totais da coorte).
2. **Isolamento Médio Acumulado:** Média temporal do tempo de fala ou volume de interações (horizontal e vertical) do paciente nas últimas $N$ sessões.
3. **Tendência:** Redução consecutiva no volume de fala/interações nas últimas 3 sessões.

### C. Detecção Histórica de Subgrupos (Cliques)
A identificação de subgrupos ou panelas que segregam o grupo é feita pela **agregação cumulativa das arestas da rede** ao longo de todas as sessões da coorte.
* **Como funciona:** Redes densamente conectadas entre si ao longo do tempo com raras conexões para nós externos revelam subgrupos consolidados, sugerindo ao terapeuta a necessidade de misturar ativamente os integrantes.

---

## 2. Matriz de Gatilhos e Ações Recomendadas (Atualizada)

### Ações Individuais (Baseadas em TDPM-20 e Sequenciamento de Pontuações)

| Tipo de Alerta | Gatilho Clínico | Ação Prática no Painel | Estratégia Clínica Recomendada | Exemplo no Painel |
| :--- | :--- | :--- | :--- | :--- |
| **Sintoma Agudo Crítico (Nota 4)** | `score = 4` em qualquer item por **≥ 2 sessões seguidas**. | **Intervenção Urgente / Encaminhamento** | Contato extra-sessão imediato. Avaliar necessidade de consulta psiquiátrica individualizada ou ajuste medicamentoso. | 🚨 **Crise Persistente (Paciente1):** Pontuação máxima em *Ataques de Pânico (16.3)* pela 2ª sessão consecutiva. **Ação:** Recomenda-se contato individual de suporte nas próximas 24h. |
| **Sofrimento Crônico Severo (Nota 3)** | `score = 3` em um mesmo item por **≥ 3 sessões seguidas**. | **Discussão de Barreira Terapêutica** | Dedicar 10 min da sessão individual/início do grupo para investigar barreiras na evolução desse sintoma específico. | ⚠️ **Sintoma Severo Crônico (Paciente3):** Escore 3 em *Ruminação e Autocrítica (19.2)* por 3 sessões seguidas. **Ação:** Abordar técnicas cognitivo-comportamentais focadas em ruminação no próximo encontro. |
| **Alerta Moderado Persistente (Nota 2)** | `score = 2` em um mesmo item por **≥ 4 sessões seguidas**. | **Psicoeducação e Manejo de Crônicos** | Paciente estagnado em sofrimento moderado. Focar em estratégias de aceitação, regulação emocional ou higiene comportamental para o sintoma específico. | 📉 **Alerta de Estagnação (Paciente5):** Sintoma de *Dificuldade para Iniciar/Manter o Sono (2.1)* persistente com nota 2 há 4 sessões. **Ação:** Oferecer diário de sono ou focar em higiene do sono. |
| **Deterioração Gradual** | Subida sucessiva de notas em 3 sessões (ex: $1 \to 2 \to 3$). | **Sondagem de Novos Estressores** | Investigar se novos eventos estressores ocorreram na rotina do paciente para justificar a piora gradativa. | 📈 **Piora Gradual (Paciente2):** Sintoma de *Irritabilidade e explosões de raiva (17.1)* subindo consecutivamente. **Ação:** Indagar sobre novos estressores no trabalho/família. |

---

### Ações Relacionais e Coesão (Baseadas nos Grafos Acumulados e Individuais)

| Tipo de Alerta | Gatilho Clínico | Ação Prática no Painel | Estratégia Clínica Recomendada | Exemplo no Painel |
| :--- | :--- | :--- | :--- | :--- |
| **Isolamento Absoluto na Sessão** | Paciente com zero conexões com pares e com o terapeuta na sessão atual. | **Resgate Emergencial de Presença** | O terapeuta deve iniciar o próximo encontro incluindo o paciente em um tema simples/acolhedor. | 🔇 **Paciente4 Isolado:** Nenhuma interação registrada na sessão 5. **Ação:** Fazer pergunta aberta direta a ele logo no início da próxima sessão para reinseri-lo. |
| **Monopólio Conversacional** | Paciente que ocupa > 40% das interações da sessão (par-a-par ou com o terapeuta). | **Acolher e Desviar** | Validar a fala do paciente e transitar suavemente a palavra para outro membro. | ⚖️ **Paciente2 Centralizador:** Dominou a maior parte da sessão conversando com o terapeuta. **Ação:** "Paciente2, excelente ponto. Paciente3, como você lida com isso na sua rotina?" |
| **Diálogo Exclusivo (Tutor/Terapeuta)** | Paciente com interações abundantes com o terapeuta, mas **zero conexões** com outros pacientes. | **Estimular Conexão Horizontal** | Incentivar o paciente a compartilhar sua vivência diretamente com outro membro, reduzindo a dependência da figura do terapeuta. | 🗣️ **Diálogo Vertical (Paciente5):** Conversou apenas com o terapeuta. **Ação:** Pedir que ele comente sobre o relato de outro membro ("Paciente5, o que você sugeriria para o Paciente1 sobre o manejo de gatilhos?"). |
| **Subgrupos Consolidados** | Agrupamento recorrente de interações exclusivas entre membros A-B (≥ 3 sessões). | **Dinâmica de Mistura conversacional** | Interromper o isolamento entre subgrupos mudando a disposição física (se presencial) ou direcionando debates cruzados. | 🧩 **Subgrupo Identificado (Histórico):** Conexões concentradas entre *Paciente1* e *Paciente3*. **Ação:** Direcionar perguntas que cruzem as falas de *Paciente1* e *Paciente2*. |
| **Risco de Abandono (Individual)** | Frequência de presença < 70% combinada com Isolamento Médio nas últimas sessões. | **Intervenção Preventiva de Dropout** | Enviar mensagem individual ou realizar ligação curta de acolhimento focada em fortalecer a aliança terapêutica. | 🚨 **Risco Alto de Abandono (Paciente4):** Presença de 60% e isolamento absoluto nas últimas duas sessões que compareceu. **Ação:** Realizar contato extra-sessão focado em retenção. |

---

## 3. Extração e Análise de Tópicos das Minutas

Podemos extrair dados altamente acionáveis das minutas (`group_clinical_progress_note`) sob duas perspectivas: **individual (por sessão)** e **histórica (longitudinal)**.

### A. Análise Individual (Por Sessão)
* **Correlação Tema-Sintoma:** Cruzar os temas transversais detectados na minuta da sessão com os picos de sintomas (TDPM-20) individuais.
  * *Exemplo:* Se o tema transversal foi "conflitos familiares" e as notas de *Irritabilidade (17.1)* e *Ansiedade (16.1)* subiram na mesma sessão para determinados pacientes, o painel infere e aponta que **estressores familiares** são os principais gatilhos ativos para esses indivíduos.
* **Mapeamento de Técnicas Clínicas Utilizadas:** Registrar quais intervenções foram aplicadas pelo terapeuta (ex: reestruturação cognitiva, psicoeducação, treino de assertividade) na sessão para auditar ou guiar o planejamento das próximas sessões.

### B. Análise Histórica (Evolução Longitudinal)
* **Estagnação Temática:** Se um mesmo tema transversal (ex: "manejo de fissura" ou "luto") aparece como tema principal em $\ge 4$ sessões seguidas, o painel alerta sobre **estagnação terapêutica** do grupo.
  * *Ação:* Sugerir ao terapeuta alterar a abordagem (ex: trazer uma técnica de aceitação e compromisso ou mudar o formato da dinâmica).
* **Sazonalidade e Padrões Calendários:** Rastrear a recorrência de temas em períodos específicos (ex: temas de "fim de semana", "festas de fim de ano", "férias").
  * *Ação:* O painel pode alertar antecipadamente: *"Historicamente, o tema 'fissura em fins de semana' surge a cada 4 semanas. Sugere-se antecipar estratégias de prevenção de recaída neste encontro."*
* **Trajetórias de Engajamento por Tema (Afinidade de Pacientes):** Identificar se certos pacientes se engajam (ou se calam) dependendo do tema da sessão.
  * *Exemplo:* *Paciente3* gera muitas conexões (edges) quando o tema é "Família", mas entra em isolamento absoluto quando o tema é "Carreira/Trabalho".
  * *Ação:* Alertar o terapeuta sobre a sensibilidade ou desinteresse do paciente a certos temas, permitindo uma moderação direcionada.
* **Indicador de Maturação do Grupo:** Mapear a evolução dos temas gerais ao longo do tempo (ex: transição de "Apresentação/Vinculação" nas sessões 1-3, para "Enfrentamento/Conflitos" nas sessões 4-8, e "Prevenção de Recaída/Planos Futuros" nas sessões 9+).

---

## 4. Fluxo de Trabalho Recomendado no Painel (Roteiro Clínico)

Com essas novas métricas agregadas, o painel do terapeuta gera um **Roteiro Clínico Automatizado** antes de cada sessão:

1. **Revisão da Sessão Anterior:** O painel mostra quem ficou isolado ou quem dominou o espaço na última sessão.
2. **Alertas de Sintomas em Destaque:** Lista os pacientes com sequências preocupantes (ex: quatro notas 2 consecutivas em insônia, ou deteriorações $1 \to 2 \to 3$).
3. **Sugestão de Abertura Temática:** *"Esta sessão deve abordar o tema X (antecipando o padrão de fim de ano). Paciente4 costuma se isolar neste tema; sugere-se trazê-lo ativamente para a discussão logo no início."*
