/**
 * cohort_analytics.js
 *
 * Manages the interactive client-side components for the Cohort/Group Dashboard.
 * Responsibilities:
 *   1. Dynamic Chart.js rendering for general group severity (Mean/Median total)
 *   2. Multi-line comparison for cohort dimension metrics
 *   3. Toggle between Mean and Median calculations dynamically
 *   4. Show/Hide dimensions in the heatmap without sintoms
 */

document.addEventListener('DOMContentLoaded', () => {
    const pageDataElement = document.getElementById('page-data');
    if (!pageDataElement) return;

    const _page = JSON.parse(pageDataElement.textContent);
    const { chartLabels, chartMeanTotals, chartMedianTotals, chartDimensions } = _page;

    const HSL_COLORS = [
        'hsl(217, 91%, 60%)',  // primary blue
        'hsl(142, 71%, 45%)',  // green
        'hsl(38,  92%, 50%)',  // amber
        'hsl(350, 89%, 60%)',  // red
        'hsl(280, 87%, 65%)',  // purple
        'hsl(180, 70%, 45%)',  // teal
        'hsl(25,  95%, 55%)',  // orange
        'hsl(320, 80%, 60%)',  // pink
        'hsl(160, 84%, 39%)',  // emerald
        'hsl(260, 60%, 50%)',  // indigo
    ];

    // =========================================================================
    // 1. Chart Initialisation
    // =========================================================================
    const chartCanvas = document.getElementById('evolutionChart');
    let chartInstance = null;

    // State variables
    let currentMetric = 'total';  // 'total' or 'dimensions'
    let currentMethod = 'mean';   // 'mean' or 'median'

    function getActiveTotals() {
        return currentMethod === 'mean' ? chartMeanTotals : chartMedianTotals;
    }

    function renderTotalChart() {
        if (chartInstance) chartInstance.destroy();

        const ctx = chartCanvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, 300);
        
        // Dynamic colors depending on Mean vs Median
        const primaryColor = currentMethod === 'mean' ? 'var(--primary)' : 'hsl(280, 87%, 60%)';
        const fillStart = currentMethod === 'mean' ? 'rgba(59, 130, 246, 0.25)' : 'rgba(168, 85, 247, 0.25)';
        
        gradient.addColorStop(0, fillStart);
        gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

        const labelText = currentMethod === 'mean' 
            ? 'Gravidade Coletiva Média (Soma dos Sintomas)' 
            : 'Gravidade Coletiva Mediana (Soma dos Sintomas)';

        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartLabels,
                datasets: [{
                    label: labelText,
                    data: getActiveTotals(),
                    borderColor: primaryColor,
                    borderWidth: 3,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.25,
                    pointBackgroundColor: primaryColor,
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
                const dimensionData = currentMethod === 'mean' ? d.mean_data : d.median_data;
                const methodLabel = currentMethod === 'mean' ? '(Média)' : '(Mediana)';
                
                return {
                    label: `${d.name} ${methodLabel}`,
                    data: dimensionData,
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
            options: chartOptions({ stepSize: 1, suggestedMax: 6, legendSize: 10 }),
        });
    }

    function chartOptions({ stepSize = 5, suggestedMax, legendSize = 12 } = {}) {
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

    // Initial render
    renderTotalChart();

    // =========================================================================
    // 2. Control Selectors (Metric & Method)
    // =========================================================================
    const chartMetricSelect = document.getElementById('chartMetricSelect');
    const chartMethodSelect = document.getElementById('chartMethodSelect');
    const dimCheckboxContainer = document.getElementById('dimensionCheckboxContainer');

    function updateDashboardChart() {
        if (currentMetric === 'dimensions') {
            buildDimensionCheckboxes();
            dimCheckboxContainer.style.display = 'grid';
        } else {
            dimCheckboxContainer.style.display = 'none';
            renderTotalChart();
        }
    }

    chartMetricSelect.addEventListener('change', () => {
        currentMetric = chartMetricSelect.value;
        updateDashboardChart();
    });

    chartMethodSelect.addEventListener('change', () => {
        currentMethod = chartMethodSelect.value;
        updateDashboardChart();
    });

    function buildDimensionCheckboxes() {
        // Clear if built state is dirty or we just need to re-render
        if (dimCheckboxContainer.dataset.built) {
            updateDimensionChart();
            return;
        }
        dimCheckboxContainer.innerHTML = '';

        // Find active dimensions (those with at least one score > 0 in any session)
        const activeDimensions = chartDimensions.filter(d => {
            const data = currentMethod === 'mean' ? d.mean_data : d.median_data;
            return data.some(val => val > 0);
        });

        if (activeDimensions.length === 0) {
            dimCheckboxContainer.innerHTML = '<p style="grid-column:1/-1;color:var(--text-muted);font-size:0.85rem;text-align:center;">Nenhum sintoma ativo coletivo para o grupo.</p>';
            return;
        }

        activeDimensions.forEach((dim, i) => {
            const label = document.createElement('label');
            label.className = 'checkbox-label';
            label.style.display = 'flex';
            label.style.alignItems = 'center';
            label.style.gap = '0.5rem';
            label.style.fontSize = '0.85rem';
            label.style.cursor = 'pointer';
            label.style.color = 'var(--text)';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.value = dim.key;
            cb.checked = i < 5; // Default select top 5
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
        
        if (selected.length === 0) {
            // Select at least one to prevent blank charts
            const firstCb = dimCheckboxContainer.querySelector('input');
            if (firstCb) {
                firstCb.checked = true;
                selected.push(firstCb.value);
            }
        }
        renderDimensionChart(selected);
    }

    // =========================================================================
    // 3. Heatmap Row Toggle (Hide/Show Empty Dimensions)
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
});
