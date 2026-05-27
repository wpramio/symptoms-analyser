document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const patientSelect = document.getElementById('patientSelect');
    const evolutionWelcome = document.getElementById('evolutionWelcome');
    const evolutionDashboard = document.getElementById('evolutionDashboard');
    
    // KPI elements
    const metricSessionsCount = document.getElementById('metricSessionsCount');
    const metricPeakScore = document.getElementById('metricPeakScore');
    const metricPeakSession = document.getElementById('metricPeakSession');
    const metricTrend = document.getElementById('metricTrend');
    const metricTrendDesc = document.getElementById('metricTrendDesc');
    const metricTopDimension = document.getElementById('metricTopDimension');
    const metricTopDimensionScore = document.getElementById('metricTopDimensionScore');

    // Chart elements
    const chartMetricSelect = document.getElementById('chartMetricSelect');
    const dimensionCheckboxContainer = document.getElementById('dimensionCheckboxContainer');
    let evolutionChartInstance = null;

    // Heatmap elements
    const heatmapHeaders = document.getElementById('heatmapHeaders');
    const heatmapBody = document.getElementById('heatmapBody');
    const btnToggleEmptyDimensions = document.getElementById('btnToggleEmptyDimensions');
    let showEmptyDimensions = false;

    // Timeline elements
    const timelineDimensionFilter = document.getElementById('timelineDimensionFilter');
    const evidenceTimeline = document.getElementById('evidenceTimeline');

    // Full TDPM-20 Ontology Definitions
    const ONTOLOGY_DIMENSIONS = {
        "1": "Desregulação do Apetite",
        "2": "Desregulação do Sono",
        "3": "Desregulação da Energia / Ânimo",
        "4": "Desregulação da Libido",
        "5": "Dor / Sintomas Somáticos",
        "6": "Alteração da Consciência",
        "7": "Desregulação da Orientação",
        "8": "Memória / Comunicação",
        "9": "Desregulação da Atenção",
        "10": "Alteração da Sensopercepção",
        "11": "Desregulação da Volição",
        "12": "Impulsividade",
        "13": "Conexão Social",
        "14": "Compulsão",
        "15": "Restrição / Purgação",
        "16": "Espectro Ansiedade / Fobia / Pânico",
        "17": "Espectro Irritabilidade / Raiva",
        "18": "Espectro Desconfiança / Agressividade",
        "19": "Espectro Tristeza / Depressão",
        "20": "Espectro Euforia / Mania"
    };

    // Global Patient Index State
    let patientIndex = {};
    let allSessionsList = []; // Chronological list of { sessionBase, date, data }

    // Colors for multiple lines in dimension view
    const HSL_COLORS = [
        "hsl(217, 91%, 60%)",  // Blue
        "hsl(142, 71%, 45%)",  // Green
        "hsl(38, 92%, 50%)",   // Yellow/Orange
        "hsl(350, 89%, 60%)",  // Red
        "hsl(280, 87%, 65%)",  // Purple
        "hsl(180, 70%, 45%)",  // Cyan
        "hsl(25, 95%, 55%)",   // Amber/Orange
        "hsl(320, 80%, 60%)",  // Pink
        "hsl(160, 84%, 39%)",  // Emerald
        "hsl(260, 60%, 50%)"   // Violet
    ];

    // Fetch and Compile Data
    fetch('/api/evaluations')
        .then(res => res.json())
        .then(files => {
            if (files.length === 0) {
                patientSelect.innerHTML = '<option value="" disabled>Nenhuma análise encontrada.</option>';
                return;
            }

            // Step 1: Group by session base name, selecting the latest run
            const latestRunsMap = {};
            files.forEach(file => {
                // Split by " (" to isolate the session base name from clinician info
                const sessionBase = file.name.split(' (')[0];
                if (!latestRunsMap[sessionBase]) {
                    latestRunsMap[sessionBase] = {
                        base: sessionBase,
                        name: file.name,
                        path: file.path
                    };
                }
            });

            const uniqueSessions = Object.values(latestRunsMap);

            // Step 2: Fetch all files in parallel
            const fetchPromises = uniqueSessions.map(sess => {
                return fetch(sess.path)
                    .then(res => res.json())
                    .then(data => {
                        // Extract YYYY-MM-DD from baseSession name
                        let clinicalDateStr = sess.base.replace('session_', '').replace('synthetic_from_scratch_', '');
                        clinicalDateStr = clinicalDateStr.replace(/_/g, '-');
                        
                        // Check if there is a date of format DD/MM/YYYY in sess.base
                        const ddmmyyyyMatch = sess.base.match(/(\d{2})\/(\d{2})\/(\d{4})/);
                        if (ddmmyyyyMatch) {
                            clinicalDateStr = `${ddmmyyyyMatch[3]}-${ddmmyyyyMatch[2]}-${ddmmyyyyMatch[1]}`;
                        } else if (clinicalDateStr.length === 15 && clinicalDateStr.includes('-')) {
                            // synthetic_from_scratch_YYYYMMDD_HHMMSS -> YYYY-MM-DD
                            const datePart = clinicalDateStr.split('-')[0];
                            clinicalDateStr = `${datePart.substring(0, 4)}-${datePart.substring(4, 6)}-${datePart.substring(6, 8)}`;
                        } else if (!/^\d{4}-\d{2}-\d{2}$/.test(clinicalDateStr)) {
                            // Fallback to timestamp inside JSON if regex fails
                            if (data.timestamp_utc) {
                                clinicalDateStr = data.timestamp_utc.substring(0, 10);
                            } else {
                                clinicalDateStr = new Date().toISOString().substring(0, 10);
                            }
                        }

                        return {
                            sessionBase: sess.base,
                            date: clinicalDateStr,
                            data: data
                        };
                    })
                    .catch(err => {
                        console.error(`Error loading session ${sess.path}:`, err);
                        return null;
                    });
            });

            return Promise.all(fetchPromises);
        })
        .then(sessions => {
            // Filter invalid or failed parses
            allSessionsList = sessions.filter(s => s && s.data && s.data.aggregated && s.data.aggregated.patients);
            
            // Sort chronologically by date
            allSessionsList.sort((a, b) => a.date.localeCompare(b.date));

            if (allSessionsList.length === 0) {
                patientSelect.innerHTML = '<option value="" disabled>Nenhum dado clínico de paciente encontrado.</option>';
                return;
            }

            // Build Comprehensive Patient Index
            buildPatientIndex();

            // Populate Patient Select dropdown
            populatePatientSelect();
        })
        .catch(err => {
            console.error("Failed to boot Patient Evolution system:", err);
            patientSelect.innerHTML = '<option value="" disabled>Erro ao carregar dados.</option>';
        });

    function buildPatientIndex() {
        patientIndex = {};

        allSessionsList.forEach(sess => {
            const patients = sess.data.aggregated.patients;
            Object.entries(patients).forEach(([pName, pData]) => {
                if (!patientIndex[pName]) {
                    patientIndex[pName] = {
                        name: pName,
                        timeline: [], // { date, totalScore, dimensions: { dimKey: sum }, items }
                        activeDimensions: new Set()
                    };
                }

                // Compute total severity score (sum of all dimension sums)
                let totalScore = 0;
                const dims = {};

                if (pData.dimensions) {
                    Object.entries(pData.dimensions).forEach(([dimKey, dimVal]) => {
                        totalScore += dimVal.dimension_sum;
                        dims[dimKey] = dimVal.dimension_sum;
                        
                        if (dimVal.dimension_sum > 0) {
                            patientIndex[pName].activeDimensions.add(dimKey);
                        }
                    });
                }

                patientIndex[pName].timeline.push({
                    sessionBase: sess.sessionBase,
                    date: sess.date,
                    totalScore: totalScore,
                    dimensions: dims,
                    items: pData.items || {}
                });
            });
        });
    }

    function populatePatientSelect() {
        const sortedPatientNames = Object.keys(patientIndex).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
        
        patientSelect.innerHTML = '<option value="" disabled selected>Selecione um paciente...</option>';
        sortedPatientNames.forEach(name => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            patientSelect.appendChild(opt);
        });

        // Restore saved patient selection or trigger welcome
        const savedPatient = localStorage.getItem('viewer_evolution_selected_patient');
        if (savedPatient && patientIndex[savedPatient]) {
            patientSelect.value = savedPatient;
            handlePatientChange(savedPatient);
        }
    }

    // Patient Change Trigger
    patientSelect.addEventListener('change', (e) => {
        const patientName = e.target.value;
        if (!patientName) return;
        localStorage.setItem('viewer_evolution_selected_patient', patientName);
        handlePatientChange(patientName);
    });

    // Toggle Empty Heatmap Dimensions Trigger
    btnToggleEmptyDimensions.addEventListener('click', () => {
        const patientName = patientSelect.value;
        const patientData = patientIndex[patientName];
        if (!patientData) return;

        showEmptyDimensions = !showEmptyDimensions;
        
        if (showEmptyDimensions) {
            btnToggleEmptyDimensions.textContent = "Ocultar dimensões sem sintomas";
            btnToggleEmptyDimensions.classList.remove('btn-secondary');
        } else {
            btnToggleEmptyDimensions.textContent = "Mostrar dimensões sem sintomas";
            btnToggleEmptyDimensions.classList.add('btn-secondary');
        }

        renderHeatmap(patientData);
    });

    function handlePatientChange(patientName) {
        // Toggle view container
        evolutionWelcome.style.display = 'none';
        evolutionDashboard.style.display = 'flex';

        const patientData = patientIndex[patientName];

        // 1. Render KPIs
        renderKPIs(patientData);

        // 2. Setup Chart view metric choices
        chartMetricSelect.value = 'total';
        dimensionCheckboxContainer.style.display = 'none';
        
        // 3. Render Chart
        renderChart(patientData);

        // 4. Render Heatmap (reset to hidden by default)
        showEmptyDimensions = false;
        btnToggleEmptyDimensions.textContent = "Mostrar dimensões sem sintomas";
        btnToggleEmptyDimensions.classList.add('btn-secondary');
        renderHeatmap(patientData);

        // 5. Setup and Render Evidence Timeline
        setupEvidenceTimelineFilters(patientData);
        renderTimeline(patientData, 'all');
    }

    // 1. KPI Calculations
    function renderKPIs(pData) {
        const timeline = pData.timeline;
        const totalSessions = timeline.length;
        metricSessionsCount.textContent = totalSessions;

        // Peak Severity Score
        let peakScore = 0;
        let peakDate = '-';
        timeline.forEach(t => {
            if (t.totalScore >= peakScore) {
                peakScore = t.totalScore;
                peakDate = t.date;
            }
        });
        metricPeakScore.textContent = peakScore;
        metricPeakSession.textContent = `Na sessão: ${peakDate}`;

        // Trend calculation (first vs last session in timeline)
        if (totalSessions >= 2) {
            const firstScore = timeline[0].totalScore;
            const lastScore = timeline[totalSessions - 1].totalScore;
            const diff = lastScore - firstScore;

            if (diff < 0) {
                metricTrend.className = "metric-value text-success";
                metricTrend.textContent = `▼ ${Math.abs(diff)}`;
                metricTrendDesc.textContent = "Melhora clínica (redução de sintomas)";
            } else if (diff > 0) {
                metricTrend.className = "metric-value text-danger";
                metricTrend.textContent = `▲ +${diff}`;
                metricTrendDesc.textContent = "Piora clínica (aumento de sintomas)";
            } else {
                metricTrend.className = "metric-value text-warning";
                metricTrend.textContent = "● 0";
                metricTrendDesc.textContent = "Estável (mesma pontuação inicial)";
            }
        } else {
            metricTrend.className = "metric-value";
            metricTrend.textContent = "N/A";
            metricTrendDesc.textContent = "Apenas 1 sessão registrada";
        }

        // Most Active Dimension
        const dimensionAverages = {};
        pData.activeDimensions.forEach(dimKey => {
            let sum = 0;
            timeline.forEach(t => {
                sum += (t.dimensions[dimKey] || 0);
            });
            dimensionAverages[dimKey] = sum / totalSessions;
        });

        let topDimKey = null;
        let topDimAvg = 0;
        Object.entries(dimensionAverages).forEach(([dimKey, avg]) => {
            if (avg > topDimAvg) {
                topDimAvg = avg;
                topDimKey = dimKey;
            }
        });

        if (topDimKey) {
            const dimName = ONTOLOGY_DIMENSIONS[topDimKey] || topDimKey;
            const maxSize = (topDimKey === "16" ? 3 : 2) * 4;
            metricTopDimension.textContent = `${topDimKey}. ${dimName}`;
            metricTopDimensionScore.textContent = `Média: ${topDimAvg.toFixed(1)} / ${maxSize}`;
        } else {
            metricTopDimension.textContent = "Nenhum";
            metricTopDimensionScore.textContent = "Média: 0";
        }
    }

    // 2 & 3. Chart Setup
    chartMetricSelect.addEventListener('change', () => {
        const patientName = patientSelect.value;
        const patientData = patientIndex[patientName];
        if (!patientData) return;

        if (chartMetricSelect.value === 'dimensions') {
            dimensionCheckboxContainer.style.display = 'grid';
            renderDimensionSelectorCheckboxes(patientData);
        } else {
            dimensionCheckboxContainer.style.display = 'none';
            renderChart(patientData);
        }
    });

    function renderDimensionSelectorCheckboxes(pData) {
        dimensionCheckboxContainer.innerHTML = '';
        
        // Sort active dimensions numerically
        const sortedActiveDims = Array.from(pData.activeDimensions).sort((a, b) => parseInt(a) - parseInt(b));

        if (sortedActiveDims.length === 0) {
            dimensionCheckboxContainer.innerHTML = '<p style="grid-column: 1/-1; color: var(--text-muted); font-size: 0.85rem;">Nenhum sintoma ativo para este paciente.</p>';
            return;
        }

        sortedActiveDims.forEach((dimKey, index) => {
            const label = document.createElement('label');
            label.className = 'checkbox-label';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = dimKey;
            
            // Check first 3 dimensions by default so the chart is populated
            checkbox.checked = index < 3;
            
            checkbox.addEventListener('change', () => {
                updateDimensionLineChart(pData);
            });

            label.appendChild(checkbox);
            label.appendChild(document.createTextNode(`${dimKey} - ${ONTOLOGY_DIMENSIONS[dimKey] || dimKey}`));
            
            dimensionCheckboxContainer.appendChild(label);
        });

        // Trigger immediate render
        updateDimensionLineChart(pData);
    }

    function renderChart(pData) {
        const ctx = document.getElementById('evolutionChart').getContext('2d');
        if (evolutionChartInstance) {
            evolutionChartInstance.destroy();
        }

        const labels = pData.timeline.map(t => t.date);
        const dataValues = pData.timeline.map(t => t.totalScore);

        // Chart gradient fill
        const gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, 'rgba(59, 130, 246, 0.3)');
        gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

        evolutionChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Gravidade Geral (Soma de Sintomas)',
                    data: dataValues,
                    borderColor: 'var(--primary)',
                    borderWidth: 3,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.25,
                    pointBackgroundColor: 'var(--primary)',
                    pointBorderColor: 'white',
                    pointBorderWidth: 2,
                    pointRadius: 5,
                    pointHoverRadius: 7
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            font: { family: "'Inter', sans-serif", weight: '600' }
                        }
                    },
                    tooltip: {
                        padding: 12,
                        backgroundColor: 'rgba(30, 41, 59, 0.95)',
                        titleFont: { family: "'Inter', sans-serif", weight: '700' },
                        bodyFont: { family: "'Inter', sans-serif" },
                        callbacks: {
                            label: function(context) {
                                return ` Gravidade Geral: ${context.raw} pontos`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { font: { family: "'Inter', sans-serif", weight: '500' } }
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: 'var(--border)' },
                        ticks: {
                            stepSize: 5,
                            font: { family: "'Inter', sans-serif", weight: '500' }
                        }
                    }
                }
            }
        });
    }

    function updateDimensionLineChart(pData) {
        const ctx = document.getElementById('evolutionChart').getContext('2d');
        if (evolutionChartInstance) {
            evolutionChartInstance.destroy();
        }

        const checkedBoxes = dimensionCheckboxContainer.querySelectorAll('input:checked');
        const labels = pData.timeline.map(t => t.date);
        
        const datasets = [];

        checkedBoxes.forEach((box, colorIndex) => {
            const dimKey = box.value;
            const color = HSL_COLORS[colorIndex % HSL_COLORS.length];
            const dataValues = pData.timeline.map(t => t.dimensions[dimKey] || 0);

            datasets.push({
                label: `${dimKey}. ${ONTOLOGY_DIMENSIONS[dimKey] || dimKey}`,
                data: dataValues,
                borderColor: color,
                borderWidth: 2.5,
                backgroundColor: 'transparent',
                tension: 0.2,
                pointBackgroundColor: color,
                pointBorderColor: 'white',
                pointBorderWidth: 1.5,
                pointRadius: 4,
                pointHoverRadius: 6
            });
        });

        evolutionChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            boxWidth: 15,
                            font: { family: "'Inter', sans-serif", weight: '500', size: 11 }
                        }
                    },
                    tooltip: {
                        padding: 12,
                        backgroundColor: 'rgba(30, 41, 59, 0.95)',
                        titleFont: { family: "'Inter', sans-serif", weight: '700' },
                        bodyFont: { family: "'Inter', sans-serif" }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { font: { family: "'Inter', sans-serif", weight: '500' } }
                    },
                    y: {
                        beginAtZero: true,
                        suggestedMax: 8,
                        grid: { color: 'var(--border)' },
                        ticks: {
                            stepSize: 1,
                            font: { family: "'Inter', sans-serif", weight: '500' }
                        }
                    }
                }
            }
        });
    }

    // 4. Monitoring Heatmap Matrix
    function renderHeatmap(pData) {
        const timeline = pData.timeline;

        // Clear and rebuild headers
        heatmapHeaders.innerHTML = '<th>Dimensão Clínica</th>';
        timeline.forEach(t => {
            const th = document.createElement('th');
            th.textContent = t.date;
            th.style.textAlign = 'center';
            heatmapHeaders.appendChild(th);
        });

        // Rebuild body rows (20 dimensions)
        heatmapBody.innerHTML = '';
        
        for (let i = 1; i <= 20; i++) {
            const dimKey = i.toString();

            // Skip rendering if the dimension has no score across all sessions and toggle is off
            if (!showEmptyDimensions) {
                const hasScore = timeline.some(t => (t.dimensions[dimKey] || 0) > 0);
                if (!hasScore) {
                    continue;
                }
            }

            const dimName = ONTOLOGY_DIMENSIONS[dimKey];
            const maxSize = (dimKey === "16" ? 3 : 2) * 4;

            const tr = document.createElement('tr');
            
            // Name cell
            const tdName = document.createElement('td');
            tdName.innerHTML = `<strong>${dimKey}</strong> - ${dimName}`;
            tr.appendChild(tdName);

            // Timeline cells
            timeline.forEach(t => {
                const score = t.dimensions[dimKey] || 0;
                const tdCell = document.createElement('td');
                tdCell.className = 'heatmap-cell';
                tdCell.textContent = `${score}/${maxSize}`;

                // Calculate severity level: 0 (absent), 1 (light), 2 (moderate), 3 (high), 4 (severe)
                const severity = Math.ceil((score / maxSize) * 4) || (score > 0 ? 1 : 0);
                tdCell.dataset.severity = severity;

                // Title tooltip
                const levelLabels = ["Ausente", "Leve", "Moderada", "Alta", "Grave"];
                tdCell.title = `Sessão: ${t.date}\nDimensão: ${dimKey} - ${dimName}\nPontuação: ${score}/${maxSize} (${levelLabels[severity]})`;

                tr.appendChild(tdCell);
            });

            heatmapBody.appendChild(tr);
        }
    }

    // 5. Evidence Timeline
    function setupEvidenceTimelineFilters(pData) {
        timelineDimensionFilter.innerHTML = '<option value="all">Todas as Dimensões</option>';
        
        // Populate filter with active dimensions for this patient
        const sortedActiveDims = Array.from(pData.activeDimensions).sort((a, b) => parseInt(a) - parseInt(b));
        sortedActiveDims.forEach(dimKey => {
            const opt = document.createElement('option');
            opt.value = dimKey;
            opt.textContent = `${dimKey}. ${ONTOLOGY_DIMENSIONS[dimKey] || dimKey}`;
            timelineDimensionFilter.appendChild(opt);
        });

        // Filter event listener
        timelineDimensionFilter.onchange = (e) => {
            renderTimeline(pData, e.target.value);
        };
    }

    function renderTimeline(pData, selectedDim) {
        evidenceTimeline.innerHTML = '';
        const timeline = pData.timeline;

        let hasAnyEvidence = false;

        timeline.forEach(sess => {
            // Filter items within this session based on selected dimension
            let relevantItems = Object.entries(sess.items);
            if (selectedDim !== 'all') {
                relevantItems = relevantItems.filter(([itemId]) => itemId.startsWith(selectedDim + '.'));
            }

            // Group items under this session
            if (relevantItems.length === 0) return;

            hasAnyEvidence = true;

            const entry = document.createElement('div');
            entry.className = 'timeline-entry';

            const badge = document.createElement('div');
            badge.className = 'timeline-badge';
            entry.appendChild(badge);

            const header = document.createElement('div');
            header.className = 'timeline-header';
            header.innerHTML = `<span class="timeline-date">${sess.date}</span>`;
            entry.appendChild(header);

            const cardsContainer = document.createElement('div');
            cardsContainer.className = 'timeline-cards-container';

            relevantItems.forEach(([itemId, item]) => {
                if (item.evidence && item.evidence.length > 0) {
                    const card = document.createElement('div');
                    card.className = 'timeline-card';

                    const cardHeader = document.createElement('div');
                    cardHeader.className = 'timeline-card-header';
                    cardHeader.innerHTML = `
                        <span class="timeline-card-title">${itemId} - ${item.name}</span>
                        <span class="score-badge" data-severity="${item.score}">Score: ${item.score}</span>
                    `;
                    card.appendChild(cardHeader);

                    const quotesList = document.createElement('ul');
                    quotesList.className = 'timeline-card-quotes';

                    item.evidence.forEach(ev => {
                        const li = document.createElement('li');
                        li.className = 'timeline-quote-item';
                        li.textContent = `"${ev}"`;
                        quotesList.appendChild(li);
                    });

                    card.appendChild(quotesList);
                    cardsContainer.appendChild(card);
                }
            });

            entry.appendChild(cardsContainer);
            evidenceTimeline.appendChild(entry);
        });

        if (!hasAnyEvidence) {
            evidenceTimeline.innerHTML = '<p class="no-evidence-timeline" style="color: var(--text-muted); text-align: center; padding: 2rem;">Nenhuma evidência clínica para os filtros selecionados.</p>';
        }
    }
});
