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
    const { chartLabels, chartTotals, chartDimensions, latestDimensions } = _page;

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
        if (!chartCanvas) return;
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
                    borderColor: '#3b82f6',
                    borderWidth: 3,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.25,
                    pointBackgroundColor: '#3b82f6',
                    pointBorderColor: 'white',
                    pointBorderWidth: 2,
                    pointRadius: 5,
                    pointHoverRadius: 7,
                }],
            },
            options: chartOptions({ stepSize: 5 }),
        });
    }

    function renderDimensionChart() {
        if (!chartCanvas) return;
        if (chartInstance) chartInstance.destroy();

        const ctx = chartCanvas.getContext('2d');
        const datasets = chartDimensions
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
            options: chartOptions({ stepSize: 1, suggestedMax: 4, legendSize: 11 }),
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
                    bodyFont: { family: "'Inter', sans-serif" },
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

    // =========================================================================
    // 2. Metric selector & initialization
    // =========================================================================
    const chartMetricSelect = document.getElementById('chartMetricSelect');

    // Render on load based on current selection
    if (chartMetricSelect && chartMetricSelect.value === 'dimensions') {
        renderDimensionChart();
    } else {
        renderTotalChart();
    }

    if (chartMetricSelect) {
        chartMetricSelect.addEventListener('change', () => {
            if (chartMetricSelect.value === 'dimensions') {
                renderDimensionChart();
            } else {
                renderTotalChart();
            }
        });
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

    // =========================================================================
    // 6. Radar Chart rendering (latest session dimensions)
    // =========================================================================
    const radarCanvas = document.getElementById('radarChart');
    if (radarCanvas && latestDimensions && latestDimensions.length > 0) {
        const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#e2e8f0';

        const getCategoryColor = (key) => {
            const num = parseInt(key, 10);
            if (num >= 1 && num <= 5) return '#0284c7';      // Neurofisiológicas
            if (num >= 6 && num <= 10) return '#4f46e5';     // Neuropsicológicas
            if (num >= 11 && num <= 15) return '#d97706';    // Busca
            if (num >= 16 && num <= 20) return '#db2777';    // Alarme
            return '#3b82f6';
        };

        const pointColors = latestDimensions.map(d => getCategoryColor(d.key));
        const pointRadii = latestDimensions.map(d => d.value > 0 ? 5.5 : 0);
        const pointHoverRadii = latestDimensions.map(d => d.value > 0 ? 8 : 0);

        const radarBgPlugin = {
            id: 'radarCategoryBg',
            beforeDatasetsDraw(chart) {
                const { ctx, scales: { r } } = chart;
                if (!r) return;

                const x = r.xCenter;
                const y = r.yCenter;
                const radius = r.drawingArea;
                const count = chart.data.labels.length;
                if (count === 0) return;

                const sectorColors = [
                    'rgba(2, 132, 199, 0.25)',   // Neurofisiológicas: Blue
                    'rgba(79, 70, 229, 0.25)',   // Neuropsicológicas: Indigo
                    'rgba(217, 119, 6, 0.25)',    // Busca: Orange
                    'rgba(219, 39, 119, 0.25)'    // Alarme: Pink
                ];

                ctx.save();
                const startAngle = r.startAngle || -Math.PI / 2;
                const sliceAngle = (2 * Math.PI) / count;

                const labelsText = ['NEUROFISIOLÓGICA', 'NEUROPSICOLÓGICA', 'BUSCA', 'ALARME'];
                const textColors = [
                    'rgba(2, 132, 199, 0.7)',
                    'rgba(79, 70, 229, 0.7)',
                    'rgba(217, 119, 6, 0.7)',
                    'rgba(219, 39, 119, 0.7)'
                ];

                for (let i = 0; i < 4; i++) {
                    const angleStart = startAngle + (i * 5 - 0.5) * sliceAngle;
                    const angleEnd = startAngle + (i * 5 + 4.5) * sliceAngle;

                    // Draw sector slice background
                    ctx.beginPath();
                    ctx.moveTo(x, y);
                    ctx.arc(x, y, radius, angleStart, angleEnd);
                    ctx.closePath();
                    ctx.fillStyle = sectorColors[i];
                    ctx.fill();

                    // Draw sector text watermark label
                    const midAngle = startAngle + (i * 5 + 2) * sliceAngle;
                    const labelRadius = radius * 0.72;
                    const tx = x + Math.cos(midAngle) * labelRadius;
                    const ty = y + Math.sin(midAngle) * labelRadius;

                    ctx.fillStyle = textColors[i];
                    ctx.font = 'bold 9px "Inter", sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(labelsText[i], tx, ty);
                }
                ctx.restore();
            }
        };

        const radarCtx = radarCanvas.getContext('2d');
        new Chart(radarCtx, {
            type: 'radar',
            plugins: [radarBgPlugin],
            data: {
                labels: latestDimensions.map(d => d.key),
                datasets: [{
                    label: 'Gravidade Média',
                    data: latestDimensions.map(d => d.value),
                    borderColor: (context) => {
                        const chart = context.chart;
                        const { ctx, scales: { r } } = chart;
                        if (!ctx || !r || typeof ctx.createConicGradient !== 'function') {
                            return '#475569';
                        }
                        const x = r.xCenter;
                        const y = r.yCenter;
                        if (x === undefined || y === undefined) return '#475569';
                        try {
                            const startAngle = r.startAngle !== undefined ? r.startAngle : -Math.PI / 2;
                            const sliceAngle = (2 * Math.PI) / 20;
                            const gradient = ctx.createConicGradient(startAngle - 0.5 * sliceAngle, x, y);
                            gradient.addColorStop(0, '#0369a1');
                            gradient.addColorStop(0.25, '#0369a1');
                            gradient.addColorStop(0.2501, '#3730a3');
                            gradient.addColorStop(0.5, '#3730a3');
                            gradient.addColorStop(0.5001, '#b45309');
                            gradient.addColorStop(0.75, '#b45309');
                            gradient.addColorStop(0.7501, '#be185d');
                            gradient.addColorStop(1, '#be185d');
                            return gradient;
                        } catch (err) {
                            return '#475569';
                        }
                    },
                    backgroundColor: (context) => {
                        const chart = context.chart;
                        const { ctx, scales: { r } } = chart;
                        if (!ctx || !r || typeof ctx.createConicGradient !== 'function') {
                            return 'rgba(148, 163, 184, 0.15)';
                        }
                        const x = r.xCenter;
                        const y = r.yCenter;
                        if (x === undefined || y === undefined) return 'rgba(148, 163, 184, 0.15)';
                        try {
                            const startAngle = r.startAngle !== undefined ? r.startAngle : -Math.PI / 2;
                            const sliceAngle = (2 * Math.PI) / 20;
                            const gradient = ctx.createConicGradient(startAngle - 0.5 * sliceAngle, x, y);
                            gradient.addColorStop(0, 'rgba(2, 132, 199, 0.15)');
                            gradient.addColorStop(0.25, 'rgba(2, 132, 199, 0.15)');
                            gradient.addColorStop(0.2501, 'rgba(79, 70, 229, 0.15)');
                            gradient.addColorStop(0.5, 'rgba(79, 70, 229, 0.15)');
                            gradient.addColorStop(0.5001, 'rgba(217, 119, 6, 0.15)');
                            gradient.addColorStop(0.75, 'rgba(217, 119, 6, 0.15)');
                            gradient.addColorStop(0.7501, 'rgba(219, 39, 119, 0.15)');
                            gradient.addColorStop(1, 'rgba(219, 39, 119, 0.15)');
                            return gradient;
                        } catch (err) {
                            return 'rgba(148, 163, 184, 0.15)';
                        }
                    },
                    borderWidth: 3,
                    pointBackgroundColor: pointColors,
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: pointColors,
                    pointRadius: pointRadii,
                    pointHoverRadius: pointHoverRadii
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    r: {
                        angleLines: {
                            display: true,
                            color: gridColor
                        },
                        grid: {
                            color: gridColor
                        },
                        suggestedMin: 0,
                        suggestedMax: 4,
                        ticks: {
                            stepSize: 1,
                            font: { family: "'Inter', sans-serif", weight: '500' }
                        },
                        pointLabels: {
                            font: {
                                family: "'Inter', sans-serif",
                                size: 10,
                                weight: '700'
                            },
                            color: pointColors
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        padding: 12,
                        backgroundColor: 'rgba(30, 41, 59, 0.95)',
                        titleFont: { family: "'Inter', sans-serif", weight: '700' },
                        bodyFont: { family: "'Inter', sans-serif" },
                        filter: function (context) {
                            return context.raw > 0;
                        },
                        callbacks: {
                            title: function (context) {
                                if (!context || !context[0] || context[0].dataIndex === undefined) return '';
                                const index = context[0].dataIndex;
                                return latestDimensions[index] ? latestDimensions[index].name : '';
                            },
                            label: function (context) {
                                if (!context || context.raw === undefined) return '';
                                const valStr = context.raw.toFixed(1).replace('.', ',');
                                return `Gravidade Média: ${valStr}`;
                            },
                            labelColor: function (context) {
                                const index = context.dataIndex;
                                const color = latestDimensions[index] ? getCategoryColor(latestDimensions[index].key) : '#3b82f6';
                                return {
                                    borderColor: color,
                                    backgroundColor: color,
                                    borderWidth: 1
                                };
                            }
                        }
                    }
                }
            }
        });
    }
});
