/**
 * patient_detail.js
 *
 * Handles ONLY the interactive controls on the patient evolution page.
 * All data (KPIs, heatmap, timeline) is server-rendered by Jinja2.
 * This file is responsible for:
 *   1. Chart.js rendering using pre-computed data from the page-data island
 *   2. Chart metric selector (total vs. per-dimension)
 *   3. Dimension checkbox grid for the per-dimension view
 *   4. Evidence timeline client-side filter
 *   5. Heatmap empty-dimension toggle (rows hidden via CSS class)
 */

document.addEventListener('DOMContentLoaded', () => {
    const _page = JSON.parse(document.getElementById('page-data').textContent);
    const { chartLabels, chartTotals, chartDimensions } = _page;

    const HSL_COLORS = [
        'hsl(217, 91%, 60%)',
        'hsl(142, 71%, 45%)',
        'hsl(38,  92%, 50%)',
        'hsl(350, 89%, 60%)',
        'hsl(280, 87%, 65%)',
        'hsl(180, 70%, 45%)',
        'hsl(25,  95%, 55%)',
        'hsl(320, 80%, 60%)',
        'hsl(160, 84%, 39%)',
        'hsl(260, 60%, 50%)',
    ];

    // =========================================================================
    // 1. Chart initialisation
    // =========================================================================
    const chartCanvas = document.getElementById('evolutionChart');
    let chartInstance = null;

    function renderTotalChart() {
        if (chartInstance) chartInstance.destroy();

        const ctx = chartCanvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, 'rgba(59, 130, 246, 0.3)');
        gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartLabels,
                datasets: [{
                    label: 'Gravidade Geral (Soma de Sintomas)',
                    data: chartTotals,
                    borderColor: 'var(--primary)',
                    borderWidth: 3,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.25,
                    pointBackgroundColor: 'var(--primary)',
                    pointBorderColor: 'white',
                    pointBorderWidth: 2,
                    pointRadius: 5,
                    pointHoverRadius: 7,
                }],
            },
            options: chartOptions({ stepSize: 5 }),
        });
    }

    function renderDimensionChart(selectedKeys) {
        if (chartInstance) chartInstance.destroy();

        const ctx = chartCanvas.getContext('2d');
        const datasets = chartDimensions
            .filter(d => selectedKeys.includes(d.key))
            .map((d, i) => {
                const color = HSL_COLORS[i % HSL_COLORS.length];
                return {
                    label: d.name,
                    data: d.data,
                    borderColor: color,
                    borderWidth: 2.5,
                    backgroundColor: color,
                    fill: false,
                    tension: 0.2,
                    pointBackgroundColor: color,
                    pointBorderColor: 'white',
                    pointBorderWidth: 1.5,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                };
            });

        chartInstance = new Chart(ctx, {
            type: 'line',
            data: { labels: chartLabels, datasets },
            options: chartOptions({ stepSize: 1, suggestedMax: 8, legendSize: 11 }),
        });
    }

    function chartOptions({ stepSize = 5, suggestedMax, legendSize = 13 } = {}) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        boxWidth: 8,
                        font: { family: "'Inter', sans-serif", weight: '600', size: legendSize }
                    },
                },
                tooltip: {
                    padding: 12,
                    backgroundColor: 'rgba(30, 41, 59, 0.95)',
                    titleFont: { family: "'Inter', sans-serif", weight: '700' },
                    bodyFont:  { family: "'Inter', sans-serif" },
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { family: "'Inter', sans-serif", weight: '500' } },
                },
                y: {
                    beginAtZero: true,
                    ...(suggestedMax !== undefined ? { suggestedMax } : {}),
                    grid: { color: 'var(--border)' },
                    ticks: { stepSize, font: { family: "'Inter', sans-serif", weight: '500' } },
                },
            },
        };
    }

    // Render on load
    renderTotalChart();

    // =========================================================================
    // 2. Metric selector
    // =========================================================================
    const chartMetricSelect = document.getElementById('chartMetricSelect');
    const dimCheckboxContainer = document.getElementById('dimensionCheckboxContainer');

    chartMetricSelect.addEventListener('change', () => {
        if (chartMetricSelect.value === 'dimensions') {
            buildDimensionCheckboxes();
            dimCheckboxContainer.style.display = 'grid';
        } else {
            dimCheckboxContainer.style.display = 'none';
            renderTotalChart();
        }
    });

    function buildDimensionCheckboxes() {
        if (dimCheckboxContainer.dataset.built) {
            // Already built — just re-render chart with current selections
            updateDimensionChart();
            return;
        }
        dimCheckboxContainer.innerHTML = '';

        if (chartDimensions.length === 0) {
            dimCheckboxContainer.innerHTML = '<p style="grid-column:1/-1;color:var(--text-muted);font-size:0.85rem;">Nenhum sintoma ativo para este paciente.</p>';
            return;
        }

        chartDimensions.forEach((dim, i) => {
            const label = document.createElement('label');
            label.className = 'checkbox-label';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.value = dim.key;
            cb.checked = true;
            cb.addEventListener('change', updateDimensionChart);

            label.appendChild(cb);
            label.appendChild(document.createTextNode(dim.name));
            dimCheckboxContainer.appendChild(label);
        });

        dimCheckboxContainer.dataset.built = '1';
        updateDimensionChart();
    }

    function updateDimensionChart() {
        const selected = Array.from(
            dimCheckboxContainer.querySelectorAll('input:checked')
        ).map(cb => cb.value);
        renderDimensionChart(selected);
    }

    // =========================================================================
    // 3. Evidence timeline dimension filter
    // =========================================================================
    const timelineFilter = document.getElementById('timelineDimensionFilter');
    const timelineContainer = document.getElementById('evidenceTimeline');

    if (timelineFilter && timelineContainer) {
        timelineFilter.addEventListener('change', () => {
            const selected = timelineFilter.value;
            timelineContainer.querySelectorAll('.timeline-entry').forEach(entry => {
                const cards = entry.querySelectorAll('.timeline-card');
                let anyVisible = false;

                cards.forEach(card => {
                    const match = selected === 'all' || card.dataset.dim === selected;
                    card.style.display = match ? '' : 'none';
                    if (match) anyVisible = true;
                });

                entry.style.display = anyVisible ? '' : 'none';
            });
        });
    }

    // =========================================================================
    // 4. Heatmap empty-dimension toggle (show/hide zero-score rows)
    // =========================================================================
    const btnToggle = document.getElementById('btnToggleEmptyDimensions');
    if (btnToggle) {
        btnToggle.addEventListener('click', () => {
            const isShowingEmpty = btnToggle.textContent.includes('Ocultar');
            
            const inactiveRows = document.querySelectorAll('.inactive-row');
            inactiveRows.forEach(row => {
                row.classList.toggle('display-none', isShowingEmpty);
            });
            
            btnToggle.textContent = isShowingEmpty
                ? 'Mostrar dimensões sem sintomas'
                : 'Ocultar dimensões sem sintomas';
            btnToggle.classList.toggle('btn-secondary', isShowingEmpty);
        });
    }

    // =========================================================================
    // 5. Main patient detail tabs navigation switcher
    // =========================================================================
    const tabButtons = document.querySelectorAll('.session-tab-btn');
    const tabPanels = document.querySelectorAll('.session-tab-panel');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.dataset.target;
            if (!targetId) return;

            // Deactivate all tab buttons and panels
            tabButtons.forEach(b => b.classList.remove('active'));
            tabPanels.forEach(p => p.classList.remove('active'));

            // Activate selected tab button and panel
            btn.classList.add('active');
            const targetPanel = document.getElementById(targetId);
            if (targetPanel) {
                targetPanel.classList.add('active');
            }

            // Force a resize event to ensure Chart.js scales dynamically when its container becomes visible
            window.dispatchEvent(new Event('resize'));
        });
    });
});
