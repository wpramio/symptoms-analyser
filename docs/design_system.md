# Design System & Component Style Guide

This document defines the unified, premium visual system for **Symptoms Analyser**. To maintain visual excellence and ensure all new pages seamlessly integrate with the existing theme, developers must follow these semantic classes and architectural patterns rather than writing custom inline CSS.

---

## 1. Core Visual Tokens (CSS Variables)
The visual system is built on centralized custom CSS properties defined in `/static/css/styles.css`. Always reference these variables for colors, borders, and curvatures:

*   **Primary Accent:** `var(--primary)` (#3b82f6 - glowing clinic blue) and `var(--primary-hover)` (#2563eb)
*   **Typography:** `var(--text-main)` (high-contrast title) and `var(--text-muted)` (soft slate subtitle)
*   **Containers:** `var(--card-bg)` (solid glass cards), `var(--border)` (refined dividers), and `var(--radius)` (8px borders radius)
*   **Depth:** `var(--shadow)` (subtle structural shadows)

---

## 2. Page Hierarchy & Grid Framework

Every new template page must extend `base.html` and wrap its visual body in a unified `.main-container` (or legacy `.dashboard-view` / `.calculator-view`) container:

```html
{% extends 'base.html' %}
{% set active_page = 'your_page_route_id' %}

{% block title %}Nome da Página - Symptoms Analyser{% endblock %}

{% block content %}
<div class="main-container">
    <!-- Page Header -->
    <div class="page-header">
        <h2>Título Principal da Página</h2>
        <p>Subtítulo ou descrição curta da funcionalidade desta interface.</p>
    </div>
    
    <!-- Your Component Grid / Body goes here -->
</div>
{% endblock %}
```

---

## 3. Structural Components

### A. The Responsive Cards Grid (`.dashboard-grid` + `.dashboard-card`)
Use this for KPI metrics, configuration parameters, or small summaries (legacy names: `.calc-grid` / `.calc-card`):

```html
<div class="dashboard-grid">
    <!-- Component Card -->
    <div class="dashboard-card">
        <h3>Título do Card</h3>
        <!-- Content (Inputs, statistics, graphs, list items) -->
    </div>
</div>
```

### B. Two-Column Split Grid (`.patients-split-grid`)
Use this when you need a wide primary workspace (e.g., data lists, graphs) alongside a narrow operational panel (e.g., insertion forms, parameter adjustments):

```html
<div class="patients-split-grid">
    <!-- Left Workspace (takes 2/3 space on large screens) -->
    <div class="calc-results">
        <h3>Lista de Dados</h3>
        <!-- Main component -->
    </div>

    <!-- Right Sidebar Panel (takes 1/3 space) -->
    <div class="calc-card">
        <h3>Painel de Ações</h3>
        <!-- Form or configurations -->
    </div>
</div>
```

---

## 4. Input & Control Elements (`.input-group`)

Always wrap forms, inputs, and selects in the `.input-group` container. They will automatically inherit rounded corners, focus glowing indicators, and professional slate margins:

```html
<div class="input-group">
    <label for="uniqueInputId">Identificador do Campo:</label>
    <input type="text" id="uniqueInputId" placeholder="Escreva a instrução..." required>
</div>

<div class="input-group">
    <label for="uniqueSelectId">Configuração Selecionável:</label>
    <select id="uniqueSelectId">
        <option value="val1">Opção 1</option>
        <option value="val2">Opção 2</option>
    </select>
</div>
```

---

## 5. Buttons & Triggers (`.btn` / `.btn-secondary`)

Do not style buttons manually. Use the global visual trigger classes:

*   **Primary Button (`.btn`):** Use for crucial actions (submissions, savings, analysis triggers).
*   **Secondary Button (`.btn-secondary`):** Use for secondary or destructive items (cancellations, resetting parameters).

```html
<!-- Primary glowing blue button -->
<button type="submit" class="btn">Salvar Alterações</button>

<!-- Secondary outline slate button -->
<button type="button" class="btn btn-secondary">Cancelar</button>
```

---

## 6. Premium Responsive Data Tables (`.table-container` + `.cost-table`)

For listings, logs, and clinical directories, always wrap standard HTML table grids inside a `.table-container` block to enable automatic mobile responsive scrolling and unified table curvatures:

```html
<div class="table-container">
    <table class="cost-table">
        <thead>
            <tr>
                <th style="width: 30%;">Coluna A (Esquerda)</th>
                <th style="width: 70%;">Coluna B (Direita)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Dado 1</strong></td>
                <td>Descrição do elemento 1</td>
            </tr>
            <tr>
                <td><strong>Dado 2</strong></td>
                <td>Descrição do elemento 2</td>
            </tr>
        </tbody>
    </table>
</div>
```

---

## 7. Developer Style Compliance Checklist

1.  **Zero Inline CSS:** Never use the `style="..."` attribute for padding, grid spans, background colors, or border radius adjustments. Use the structural layout classes.
2.  **No Ad-hoc Form Styles:** Avoid styling text inputs, select dropdowns, or buttons with custom colors or margins. Wrap them inside `.input-group` and use `.btn`.
3.  **Active Menu State Representation:** Always set `{% set active_page = '...' %}` at the top of templates so the sidebar correctly applies the glowing `.active` tag to your current page item.
4.  **Extend `base.html`:** Every view page template must inherit the base structure to load the unified navigation sidebar, background gradients, typography fonts, and responsive wrappers.
