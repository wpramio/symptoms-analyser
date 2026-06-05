De forma resumida, as ações sugeridas se dividem em três grandes pilares com base nos dados que você já possui no banco de dados (patient_item_scores e session_syntheses):

Ações Individuais (Foco em Sintomas - TDPM-20)

Ajuste de Plano Terapêutico: Diante de picos agudos de gravidade em sintomas específicos (ex: sono, impulsividade, ou humor deprimido), sugerir checagem individual no início da sessão ou extra-sessão.
Protocolos Específicos: Recomendar ativação comportamental para pacientes com sintomas estagnados de anedonia ou anomalias de evolução comportamental.
Ações Relacionais (Foco em Dinâmica - Grafo de Suporte Mútuo)

Estimular Conexão Ativa: Para pacientes identificados no grafo sem nenhuma conexão de entrada ou saída (isolamento na sessão), sugerir ao terapeuta criar pontes de fala direcionadas com outros membros.
Moderar Centralização: Auxiliar o terapeuta a balancear o tempo de fala de membros que monopolizam as interações ou discussões de confronto/validação.
Ações de Grupo e Risco (Foco em Evasão - Coesão)

Prevenção de Abandono (Dropout): Alertas preventivos com sugestões de contato direto para acolhimento de pacientes identificados em risco de evasão.
Dissolução de Subgrupos: Recomendar dinâmicas de segurança ou quebra-gelo em duplas mistas caso o modelo detecte a formação de subgrupos isolados (panelas) na análise de coesão.

## Ajustes com base nos tópicos extraídos das minutas
1. Análise Individual (Por Sessão)
Correlação Tema-Sintoma: Cruzar os temas da sessão com a evolução dos sintomas. Se o tema for "conflito familiar" e as notas de irritabilidade subirem, o sistema sugere que o estressor familiar está ativo para aqueles pacientes.
Mapeamento de Técnicas Clínicas: Rastrear quais abordagens e técnicas terapêuticas (CBT, aceitação, etc.) foram utilizadas pelo terapeuta para guiar o planejamento das próximas sessões.
2. Análise Histórica (Evolução Longitudinal)
Estagnação Temática: Se o mesmo tema (ex: "luto" ou "fissura") domina a conversa por $\ge 4$ sessões seguidas, o painel avisa sobre estagnação e sugere mudar a dinâmica.
Sazonalidade e Padrões Calendários: Identificar tópicos recorrentes em períodos específicos (ex: datas festivas, fins de semana) e alertar preventivamente o terapeuta.
Afinidade de Engajamento por Tema: Identificar se determinados pacientes se isolam ou se engajam de acordo com o tema da sessão (ex: Paciente A conversa bastante sobre "família", mas fica em isolamento no tema "carreira").
Maturação do Grupo: Mapear a progressão natural de tópicos ao longo do tempo (desde apresentação inicial até prevenção de recaída avançada).

# Auditoria de Intervenções Clínicas e Análise de Tópicos
## O que foi implementado do bloco acima

Este documento apresenta uma análise técnica detalhada do estado atual de implementação das intervenções sugeridas no painel clínico, divididas entre **Análise Individual (Por Sessão)** e **Análise Histórica (Evolução Longitudinal)**, cruzando as especificações teóricas de `docs/suggested_interventions.md` com o código-fonte real nos diretórios `src/symptoms_analyser/controllers/` e `src/symptoms_analyser/pipeline/`.

---

## 1. Análise Individual (Por Sessão)

### A. Correlação Tema-Sintoma
*Cruzar os temas da sessão com a evolução dos sintomas. Se o tema for "conflito familiar" e as notas de irritabilidade subirem, o sistema sugere que o estressor familiar está ativo para aqueles pacientes.*

* **Status:** ❌ **Não Implementado**
* **Detalhes do Código:**
  * No arquivo [interventions.py](file:///home/wpramio/projects/ufrgs/symptoms-analyser/src/symptoms_analyser/controllers/interventions.py#L183-L276), os alertas de sintomas individuais (como `Piora Gradual` ou `Crise Persistente`) baseiam-se em lógicas puramente numéricas do histórico do TDPM-20 de cada paciente.
  * O sistema sugere ações gerais para deterioração de sintomas (ex: para irritabilidade alta, recomenda *"sondar ativamente se novos eventos estressores familiares ou profissionais afetaram o paciente"*).
  * No entanto, **não há cruzamento de dados** entre os temas transversais detectados dinamicamente na sessão (da nota clínica da minuta ou da rede de interações) com as pontuações de sintomas do paciente na mesma sessão para inferir dinamicamente a ativação de um estressor específico.

### B. Mapeamento de Técnicas Clínicas
*Rastrear quais abordagens e técnicas terapêuticas (CBT, aceitação, etc.) foram utilizadas pelo terapeuta para guiar o planejamento das próximas sessões.*

* **Status:** ⚠️ **Parcialmente Mencionado (Qualitativo / Não Estruturado)**
* **Detalhes do Código:**
  * No arquivo de prompt do LLM [clinical_synthesis.md](file:///home/wpramio/projects/ufrgs/symptoms-analyser/prompts/clinical_synthesis.md#L15-L16), o modelo é instruído a incluir brevemente na minuta textual de progresso do grupo (`group_clinical_progress_note`) as intervenções e técnicas realizadas pelo terapeuta (ex: reestruturação cognitiva, psicoeducação).
  * Contudo, esse mapeamento é exclusivamente qualitativo e fica embutido no bloco de texto livre. Não há persistência estruturada no banco de dados (`schema.sql` não possui tabelas ou campos para técnicas), nem painel de planejamento ou lógicas que consumam e sugiram dinamicamente abordagens baseadas nas técnicas passadas.

---

## 2. Análise Histórica (Evolução Longitudinal)

### A. Estagnação Temática
*Se o mesmo tema (ex: "luto" ou "fissura") domina a conversa por $\ge 4$ sessões seguidas, o painel avisa sobre estagnação e sugere mudar a dinâmica.*

* **Status:** 🔄 **Parcialmente Implementado**
* **Detalhes do Código:**
  * No controller [interventions.py](file:///home/wpramio/projects/ufrgs/symptoms-analyser/src/symptoms_analyser/controllers/interventions.py#L454-L486) (`HEURISTIC 3: Extração de Tópicos`), o sistema analisa as últimas 3 ou 4 sessões da coorte (`recent_syntheses`).
  * Ele busca por substrings associadas a 7 temas mapeados de forma estática no dicionário `clinical_keywords` (`fissura`, `recaída`, `estressores familiares`, `ansiedade / pânico`, `estagnação no trabalho`, `insônia / sono`, `luto / perda`).
  * Se um termo é detectado no texto de todas as sessões analisadas nessa janela, ele gera o alerta `"Estagnação temática: <Tema>"` e recomenda propor dinâmicas focadas em aceitação e compromisso (ACT) ou quebras conversacionais.
  * **Limitação:** A detecção é baseada em *regex/keywords* estáticas simples dentro do texto da nota, e não por modelagem semântica ou extração estruturada de tópicos do LLM por sessão.

### B. Sazonalidade e Padrões Calendários
*Identificar tópicos recorrentes em períodos específicos (ex: datas festivas, fins de semana) e alertar preventivamente o terapeuta.*

* **Status:** ❌ **Não Implementado**
* **Detalhes do Código:**
  * Não há suporte para análise de calendários, finais de semana ou datas festivas nos arquivos de banco de dados ou controllers. O sistema analisa as datas das sessões de forma estritamente sequencial para ordenação temporal, sem inteligência sazonal.

### C. Afinidade de Engajamento por Tema
*Identificar se determinados pacientes se isolam ou se engajam de acordo com o tema da sessão (ex: Paciente A conversa bastante sobre "família", mas fica em isolamento no tema "carreira").*

* **Status:** ❌ **Não Implementado**
* **Detalhes do Código:**
  * Embora o sistema registre o engajamento conversacional (airtime e número de conexões/edges de rede) e os temas gerais das sessões, não há cruzamento longitudinal no banco de dados ou heurísticas relacionais que façam correlações paciente-tema para alertar sobre sensibilidade ou desinteresse específico.

### D. Maturação do Grupo
*Mapear a progressão natural de tópicos ao longo do tempo (desde apresentação inicial até prevenção de recaída avançada).*

* **Status:** ❌ **Não Implementado**
* **Detalhes do Código:**
  * Não existe lógica implementada no backend ou visualização no frontend que organize as sessões em fases de maturação grupal baseadas em trajetórias temáticas ao longo do tempo.
