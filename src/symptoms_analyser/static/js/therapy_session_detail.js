document.addEventListener('DOMContentLoaded', () => {
    const _page = JSON.parse(document.getElementById('page-data').textContent);
    const sessionId = _page.sessionId;
    const evaluationId = _page.evaluationId;
    const initialTranscriptStatus = _page.transcriptStatus;

    // =========================================================================
    // Speaking Airtime (Tempo de Fala) Donut Chart rendering
    // =========================================================================
    const airtimeData = _page.airtime;
    if (airtimeData && airtimeData.speakers && airtimeData.speakers.length > 0) {
        const HSL_COLORS = [
            'hsl(142, 71%, 45%)',  // Green (Index 1 -> Paciente1)
            'hsl(38,  92%, 50%)',  // Yellow/Orange (Index 2 -> Paciente2)
            'hsl(350, 89%, 60%)',  // Red (Index 3 -> Paciente3)
            'hsl(280, 87%, 65%)',  // Purple (Index 4 -> Paciente4)
            'hsl(180, 70%, 45%)',  // Teal (Index 5 -> Paciente5)
            'hsl(25,  95%, 55%)',  // Orange
            'hsl(320, 80%, 60%)',  // Pink
            'hsl(160, 84%, 39%)',  // Mint
            'hsl(260, 60%, 50%)',  // Indigo
        ];

        // Resolves speaker pseudonym deterministically to a fixed color
        function getSpeakerColor(name) {
            const lower = name.toLowerCase();
            // Clinician always gets a dedicated slate blue accent
            if (lower === 'terapeuta' || lower === 'clinico' || lower === 'clínico' || lower === 'clinician') {
                return 'hsl(217, 91%, 60%)'; // Elegant Blue
            }

            // Extract the numeric identifier for patient pseudonyms (e.g. Paciente1 -> 1)
            const match = name.match(/\d+/);
            if (match) {
                const num = parseInt(match[0], 10);
                // Map cleanly onto color array
                const index = (num - 1) % HSL_COLORS.length;
                return HSL_COLORS[index];
            }

            // Fallback deterministic string hash
            let hash = 0;
            for (let i = 0; i < name.length; i++) {
                hash = name.charCodeAt(i) + ((hash << 5) - hash);
            }
            const index = Math.abs(hash) % HSL_COLORS.length;
            return HSL_COLORS[index];
        }

        const labels = airtimeData.speakers.map(s => s.speaker);
        const percentages = airtimeData.speakers.map(s => s.word_percentage);
        const counts = airtimeData.speakers.map(s => s.word_count);
        const colors = airtimeData.speakers.map(s => getSpeakerColor(s.speaker));

        // 1. Assign dot colors in the legend dynamically
        document.querySelectorAll('.airtime-legend-color-dot').forEach(dot => {
            const index = parseInt(dot.dataset.speakerIndex);
            if (!isNaN(index) && airtimeData.speakers[index]) {
                const speakerName = airtimeData.speakers[index].speaker;
                dot.style.backgroundColor = getSpeakerColor(speakerName);
            }
        });

        // 2. Instantiate Chart.js Donut Chart
        const canvas = document.getElementById('airtimeChart');
        if (canvas) {
            new Chart(canvas.getContext('2d'), {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: percentages,
                        backgroundColor: colors,
                        borderWidth: 2,
                        borderColor: '#ffffff',
                        hoverOffset: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '65%',
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            padding: 10,
                            backgroundColor: 'rgba(30, 41, 59, 0.95)',
                            titleFont: { family: "'Inter', sans-serif", weight: '700', size: 12 },
                            bodyFont: { family: "'Inter', sans-serif", size: 12 },
                            callbacks: {
                                label: function (context) {
                                    const index = context.dataIndex;
                                    const pct = percentages[index];
                                    const cnt = counts[index];
                                    return ` ${pct}% (${cnt.toLocaleString('pt-BR')} palavras)`;
                                }
                            }
                        }
                    }
                }
            });
        }
    }

    // =========================================================================
    // Social Network Visualization
    // =========================================================================
    const synthesisData = _page.clinical_analysis;
    if (synthesisData && synthesisData.interactions_mapping) {
        const supportMapping = synthesisData.interactions_mapping || { nodes: [], edges: [] };
        if (supportMapping.edges) {
            supportMapping.edges.forEach(edge => {
                if (edge.type) {
                    const normalized = edge.type.trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
                    if (normalized === 'validacao') {
                        edge.type = 'validacao';
                    } else if (normalized === 'apoio') {
                        edge.type = 'apoio';
                    } else if (normalized === 'confronto') {
                        edge.type = 'confronto';
                    }
                }
            });
        }

        // 2. Populate Interactions Scroll List
        const interactionScrollList = document.getElementById('interactionScrollList');
        if (interactionScrollList) {
            const edges = supportMapping.edges || [];
            if (edges.length > 0) {
                interactionScrollList.innerHTML = ''; // Clear fallback text
                edges.forEach(edge => {
                    const card = document.createElement('div');
                    card.className = `interaction-item-card ${edge.type}`;

                    const meta = document.createElement('div');
                    meta.className = 'interaction-meta-line';

                    const sourceText = document.createElement('strong');
                    sourceText.textContent = edge.source;
                    sourceText.style.color = getSpeakerColor(edge.source);

                    const arrowText = document.createTextNode(' ➔ ');

                    const targetText = document.createElement('strong');
                    targetText.textContent = edge.target;
                    targetText.style.color = getSpeakerColor(edge.target);

                    const badge = document.createElement('span');
                    badge.className = `interaction-type-badge ${edge.type}`;
                    badge.textContent = edge.type;

                    meta.appendChild(sourceText);
                    meta.appendChild(arrowText);
                    meta.appendChild(targetText);
                    meta.appendChild(badge);

                    const quote = document.createElement('div');
                    quote.className = 'interaction-evidence-text';
                    quote.textContent = `"${edge.evidence}"`;

                    card.appendChild(meta);
                    card.appendChild(quote);
                    interactionScrollList.appendChild(card);
                });
            } else {
                interactionScrollList.innerHTML = '<p class="text-muted text-medium">Nenhuma interação social explícita detectada nesta sessão.</p>';
            }
        }

        // 3. Render Interactive Cytoscape Social Network Graph
        const tooltipEl = document.getElementById('graphTooltip');
        const graphContainer = document.getElementById('socialNetworkGraph');

        if (graphContainer) {
            let cyInstance = null;

            const nodes = supportMapping.nodes || [];
            const edges = supportMapping.edges || [];

            // Build the set of all unique nodes from both the nodes list and the edges to ensure no dangling references
            let nodeSet = new Set();
            if (Array.isArray(nodes)) {
                nodes.forEach(n => {
                    if (n && n.id) nodeSet.add(n.id);
                });
            }
            if (Array.isArray(edges)) {
                edges.forEach(edge => {
                    if (edge.source) nodeSet.add(edge.source);
                    if (edge.target) nodeSet.add(edge.target);
                });
            }

            const uniqueNodes = Array.from(nodeSet).map(id => ({ id: id, label: id }));

            // Layout coordinates inside a 320x320 viewport
            const CX = 160;
            const CY = 160;
            const R = 90;
            const nodeCoords = {};

            uniqueNodes.forEach((node, idx) => {
                const angle = (2 * Math.PI * idx) / uniqueNodes.length - Math.PI / 2;
                nodeCoords[node.id] = {
                    x: CX + R * Math.cos(angle),
                    y: CY + R * Math.sin(angle)
                };
            });

            // Aggregate edges by source, target, and type to avoid cluttering the visual graph
            const edgeMap = {};
            edges.forEach(edge => {
                if (edge.source === edge.target) return; // Skip self-loops
                const key = `${edge.source}->${edge.target}[${edge.type}]`;
                if (!edgeMap[key]) {
                    edgeMap[key] = {
                        source: edge.source,
                        target: edge.target,
                        type: edge.type,
                        count: 0,
                        evidences: []
                    };
                }
                edgeMap[key].count++;
                if (edge.evidence) {
                    edgeMap[key].evidences.push(edge.evidence);
                }
            });
            const aggregatedEdges = Object.values(edgeMap);

            function initCytoscape() {
                if (cyInstance || typeof cytoscape === 'undefined') return;

                // Resolve text main color dynamically for labels
                const textMainColor = getComputedStyle(document.documentElement).getPropertyValue('--text-main').trim() || '#1e293b';

                requestAnimationFrame(() => {
                    const elements = [];

                    // Add nodes
                    uniqueNodes.forEach(node => {
                        const coord = nodeCoords[node.id];
                        if (!coord) return;
                        elements.push({
                            group: 'nodes',
                            data: {
                                id: node.id,
                                label: node.id,
                                color: getSpeakerColor(node.id)
                            },
                            position: { x: coord.x, y: coord.y }
                        });
                    });

                    // Add edges
                    const typeColors = {
                        apoio: '#10b981',      // Green
                        validacao: '#3b82f6',  // Blue
                        confronto: '#f59e0b'   // Orange
                    };

                    aggregatedEdges.forEach((edge, idx) => {
                        if (!nodeCoords[edge.source] || !nodeCoords[edge.target]) return;
                        const color = typeColors[edge.type] || '#64748b';
                        elements.push({
                            group: 'edges',
                            data: {
                                id: `edge-${idx}`,
                                source: edge.source,
                                target: edge.target,
                                type: edge.type,
                                count: edge.count,
                                color: color,
                                evidences: edge.evidences
                            }
                        });
                    });

                    cyInstance = cytoscape({
                        container: graphContainer,
                        elements: elements,
                        style: [
                            {
                                selector: 'node',
                                style: {
                                    'width': 30,
                                    'height': 30,
                                    'background-color': 'data(color)',
                                    'label': 'data(label)',
                                    'color': textMainColor,
                                    'font-family': "'Inter', sans-serif",
                                    'font-weight': 'bold',
                                    'font-size': '11px',
                                    'text-valign': 'bottom',
                                    'text-margin-y': 6,
                                    'text-halign': 'center',
                                    'border-width': 2.5,
                                    'border-color': '#ffffff',
                                    'overlay-opacity': 0
                                }
                            },
                            {
                                selector: 'edge',
                                style: {
                                    'width': function (ele) {
                                        return 1.5 + Math.min(ele.data('count') * 0.4, 3.5);
                                    },
                                    'line-color': 'data(color)',
                                    'target-arrow-color': 'data(color)',
                                    'target-arrow-shape': 'triangle',
                                    'arrow-scale': 0.8,
                                    'curve-style': 'bezier',
                                    'control-point-step-size': 20,
                                    'opacity': 0.75,
                                    'overlay-opacity': 0
                                }
                            },
                            {
                                selector: '.dimmed',
                                style: {
                                    'opacity': 0.15
                                }
                            },
                            {
                                selector: 'node.highlighted',
                                style: {
                                    'border-color': '#ffffff',
                                    'border-width': 2.5,
                                    'opacity': 1
                                }
                            },
                            {
                                selector: 'edge.highlighted',
                                style: {
                                    'opacity': 1,
                                    'width': function (ele) {
                                        return 2.5 + Math.min(ele.data('count') * 0.4, 3.5);
                                    }
                                }
                            }
                        ],
                        layout: {
                            name: 'preset'
                        },
                        userZoomingEnabled: true,
                        userPanningEnabled: true,
                        boxSelectionEnabled: false
                    });

                    // Interactive Tooltips & Highlights (debounced 50ms)
                    let hoverTimeout = null;

                    cyInstance.on('mouseover', 'node', (e) => {
                        if (hoverTimeout) clearTimeout(hoverTimeout);
                        const node = e.target;
                        const patientId = node.id();
                        const origEvent = e.originalEvent;
                        const mouseX = origEvent.clientX;
                        const mouseY = origEvent.clientY;

                        hoverTimeout = setTimeout(() => {
                            const sent = edges.filter(e => e.source === patientId).length;
                            const rec = edges.filter(e => e.target === patientId).length;

                            const wrapperRect = graphContainer.parentNode.getBoundingClientRect();
                            let x = mouseX - wrapperRect.left;
                            let y = mouseY - wrapperRect.top - 10;

                            if (tooltipEl) {
                                tooltipEl.innerHTML = `
                                    <div class="tooltip-title" style="margin-bottom: 0px;"><strong>${patientId}</strong></div>
                                    <div style="font-size: 0.7rem; color: #cbd5e1; margin-top: 0.25rem;">
                                        Ofereceu: <strong>${sent}</strong> interações<br/>
                                        Recebeu: <strong>${rec}</strong> interações
                                    </div>
                                `;
                                tooltipEl.style.left = `${x}px`;
                                tooltipEl.style.top = `${y}px`;
                                tooltipEl.style.transform = 'translate(-50%, -100%)';
                                tooltipEl.style.opacity = '1';
                            }

                            cyInstance.elements().addClass('dimmed');
                            node.removeClass('dimmed');
                            node.addClass('highlighted');
                            node.connectedEdges().forEach(edge => {
                                edge.removeClass('dimmed');
                                edge.addClass('highlighted');
                                edge.connectedNodes().removeClass('dimmed');
                            });
                        }, 50);
                    });

                    cyInstance.on('mouseout', 'node', () => {
                        if (hoverTimeout) clearTimeout(hoverTimeout);
                        if (tooltipEl) tooltipEl.style.opacity = '0';
                        cyInstance.elements().removeClass('dimmed');
                        cyInstance.elements().removeClass('highlighted');
                    });

                    cyInstance.on('mouseover', 'edge', (e) => {
                        if (hoverTimeout) clearTimeout(hoverTimeout);
                        const edge = e.target;
                        const sourceId = edge.source().id();
                        const targetId = edge.target().id();
                        const edgeData = edge.data();
                        const origEvent = e.originalEvent;
                        const mouseX = origEvent.clientX;
                        const mouseY = origEvent.clientY;

                        hoverTimeout = setTimeout(() => {
                            const wrapperRect = graphContainer.parentNode.getBoundingClientRect();
                            let x = mouseX - wrapperRect.left;
                            let y = mouseY - wrapperRect.top - 10;

                            if (tooltipEl) {
                                const color = edgeData.color;
                                const interactionLabel = edgeData.count === 1 ? 'interação' : 'interações';
                                let subtitleHtml = `<div style="font-weight: 800; color: ${color}; text-transform: uppercase; font-size: 0.65rem; margin-bottom: 0.25rem;">${edgeData.type} (${edgeData.count} ${interactionLabel})</div>`;

                                let tooltipHtml = `
                                    <div class="tooltip-title"><strong>${sourceId}</strong> ➜ <strong>${targetId}</strong></div>
                                    ${subtitleHtml}
                                `;

                                const limit = 3;
                                const displayed = edgeData.evidences.slice(0, limit);
                                tooltipHtml += `<div class="tooltip-body" style="max-height: 120px; overflow-y: auto; display: flex; flex-direction: column; gap: 0.25rem; margin-top: 0.25rem;">`;
                                displayed.forEach((ev) => {
                                    tooltipHtml += `<div style="border-left: 2px solid ${color}; padding-left: 0.25rem; margin-bottom: 0.15rem; font-style: italic;">"${ev}"</div>`;
                                });
                                if (edgeData.evidences.length > limit) {
                                    tooltipHtml += `<div style="font-size: 0.65rem; color: #94a3b8; text-align: right; margin-top: 0.1rem;">+ ${edgeData.evidences.length - limit} interações...</div>`;
                                }
                                tooltipHtml += `</div>`;

                                tooltipEl.innerHTML = tooltipHtml;
                                tooltipEl.style.left = `${x}px`;
                                tooltipEl.style.top = `${y}px`;
                                tooltipEl.style.transform = 'translate(-50%, -100%)';
                                tooltipEl.style.opacity = '1';
                            }

                            cyInstance.elements().addClass('dimmed');
                            edge.removeClass('dimmed');
                            edge.addClass('highlighted');
                            edge.connectedNodes().removeClass('dimmed');
                            edge.connectedNodes().addClass('highlighted');
                        }, 50);
                    });

                    cyInstance.on('mouseout', 'edge', () => {
                        if (hoverTimeout) clearTimeout(hoverTimeout);
                        if (tooltipEl) tooltipEl.style.opacity = '0';
                        cyInstance.elements().removeClass('dimmed');
                        cyInstance.elements().removeClass('highlighted');
                    });

                    // Navigation buttons
                    const zoomInBtn = document.getElementById('graphZoomInBtn');
                    const zoomOutBtn = document.getElementById('graphZoomOutBtn');
                    const resetBtn = document.getElementById('graphResetBtn');

                    if (zoomInBtn) zoomInBtn.addEventListener('click', () => {
                        if (cyInstance) cyInstance.zoom({
                            level: cyInstance.zoom() * 1.25,
                            renderedPosition: { x: graphContainer.clientWidth / 2, y: graphContainer.clientHeight / 2 }
                        });
                    });
                    if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => {
                        if (cyInstance) cyInstance.zoom({
                            level: cyInstance.zoom() / 1.25,
                            renderedPosition: { x: graphContainer.clientWidth / 2, y: graphContainer.clientHeight / 2 }
                        });
                    });
                    if (resetBtn) resetBtn.addEventListener('click', () => {
                        if (cyInstance) {
                            cyInstance.reset();
                            cyInstance.center();
                        }
                    });
                });
            }

            // Hook into the dynamics tab button click
            const dynamicsTabBtn = document.querySelector('[data-target="tab-dynamics"]');
            if (dynamicsTabBtn) {
                dynamicsTabBtn.addEventListener('click', initCytoscape);
            }

            // Also init immediately if the dynamics tab happens to be active on load
            if (document.getElementById('tab-dynamics')?.classList.contains('active')) {
                initCytoscape();
            }
        }
    }

    // Shared UI Elements
    const logConsole = document.getElementById('logConsole');
    const processingView = document.getElementById('processingView');
    const statusTitle = document.getElementById('statusTitle');
    const statusDesc = document.getElementById('statusDesc');

    // =========================================================================
    // SHARED UTILITY FUNCTIONS
    // =========================================================================
    function addLog(msg, type = 'normal') {
        if (!logConsole) return;
        const entry = document.createElement('div');
        entry.className = 'log-entry';

        if (type === 'success') entry.classList.add('success-text');
        else if (type === 'error') entry.classList.add('error-text');
        else if (type === 'system') entry.classList.add('system-text');

        const time = new Date().toLocaleTimeString();
        entry.textContent = `[${time}] ${msg}`;
        logConsole.appendChild(entry);
        logConsole.scrollTop = logConsole.scrollHeight;
    }

    function showElement(el, displayClass = '') {
        if (!el) return;
        el.classList.remove('display-none');
        if (displayClass) el.classList.add(displayClass);
    }

    function hideElement(el, displayClass = '') {
        if (!el) return;
        el.classList.add('display-none');
        if (displayClass) el.classList.remove(displayClass);
    }

    // =========================================================================
    // STATE 1: CLINICAL DASHBOARD LOGIC (When analyzed)
    // =========================================================================
    if (evaluationId) {


        // Lightweight patient tab toggler
        const patientTabs = document.getElementById('patientTabs');
        if (patientTabs) {
            patientTabs.addEventListener('click', (e) => {
                const tab = e.target.closest('.patient-tab');
                if (!tab) return;
                const targetPatient = tab.dataset.patient;

                // Hide all patient views, show active one using active class
                document.querySelectorAll('.patient-view-section').forEach(view => {
                    view.classList.toggle('active', view.id === `patient-view-${targetPatient}`);
                });

                // Update tab styles using active class
                document.querySelectorAll('.patient-tab').forEach(t => {
                    t.classList.toggle('active', t === tab);
                });
            });
        }

        // Accordion expand/collapse toggle for clinical dimensions (delegated click listener)
        document.addEventListener('click', (e) => {
            const header = e.target.closest('.dimension-header');
            if (!header) return;

            const dimensionItem = header.closest('.dimension-item');
            if (!dimensionItem) return;

            dimensionItem.classList.toggle('open');
        });

        // Main session detail tabs navigation switcher
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

        // Transcript Tab Switcher (Anonymized vs Raw)
        const btnShowAnonymized = document.getElementById('btnShowAnonymized');
        const btnShowRaw = document.getElementById('btnShowRaw');
        const transcriptTextContent = document.getElementById('transcriptTextContent');

        if (btnShowAnonymized && btnShowRaw && transcriptTextContent) {
            btnShowAnonymized.addEventListener('click', () => {
                btnShowAnonymized.classList.add('active');
                btnShowRaw.classList.remove('active');
                transcriptTextContent.textContent = transcriptTextContent.dataset.anonymized || '';
            });

            btnShowRaw.addEventListener('click', () => {
                btnShowRaw.classList.add('active');
                btnShowAnonymized.classList.remove('active');
                transcriptTextContent.textContent = transcriptTextContent.dataset.raw || '';
            });
        }

        // =========================================================================
        // CLINICAL EVALUATION REVISION LOGIC (Workstation)
        // =========================================================================
        const btnStartRevision = document.getElementById('btnStartRevision');
        const btnSaveRevision = document.getElementById('btnSaveRevision');
        const btnCancelRevision = document.getElementById('btnCancelRevision');
        const tdpmCard = document.querySelector('.tdpm-analysis-card');

        if (btnStartRevision && tdpmCard) {
            // Enter Edit Mode
            btnStartRevision.addEventListener('click', () => {
                tdpmCard.classList.add('tdpm-analysis-card--editing');
                addLog('Entrou no modo de revisão clínica manual.', 'system');
            });
        }

        if (btnCancelRevision) {
            // Cancel and restore by reloading
            btnCancelRevision.addEventListener('click', () => {
                window.location.reload();
            });
        }

        // Dynamic HSL Score Color coloring on select drop-down change
        document.querySelectorAll('.score-select-compact').forEach(select => {
            select.addEventListener('change', () => {
                select.dataset.score = select.value;
            });
        });

        // Add Evidence Handler
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.btn-add-evidence');
            if (!btn) return;

            const formGroup = btn.closest('.add-evidence-form-group');
            const input = formGroup.querySelector('.add-evidence-input');
            const val = input.value.trim();
            if (!val) return;

            const container = btn.closest('.evidence-editor-container');
            const list = container.querySelector('.evidence-editor-list');

            const li = document.createElement('li');
            li.className = 'evidence-editor-item';
            li.innerHTML = `
                <span class="evidence-text-field">${escapeHtml(val)}</span>
                <button type="button" class="btn-delete-evidence" title="Remover evidência">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        <line x1="10" y1="11" x2="10" y2="17"></line>
                        <line x1="14" y1="11" x2="14" y2="17"></line>
                    </svg>
                </button>
            `;
            list.appendChild(li);
            input.value = '';
        });

        // Support Enter key inside Add Evidence input field
        document.addEventListener('keydown', (e) => {
            const input = e.target.closest('.add-evidence-input');
            if (!input || e.key !== 'Enter') return;
            e.preventDefault();
            const btn = input.closest('.add-evidence-form-group').querySelector('.btn-add-evidence');
            if (btn) btn.click();
        });

        // Delete Evidence Handler (Delegated click)
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.btn-delete-evidence');
            if (!btn) return;
            const li = btn.closest('.evidence-editor-item');
            if (li) li.remove();
        });

        // Helper to Escape HTML
        function escapeHtml(str) {
            return str
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        // Save Revisions via API endpoint
        if (btnSaveRevision) {
            btnSaveRevision.addEventListener('click', async () => {
                btnSaveRevision.disabled = true;
                const originalText = btnSaveRevision.innerHTML;
                btnSaveRevision.innerHTML = `
                    <svg class="spinner" viewBox="0 0 24 24" width="16" height="16" style="margin-right: 6px; animation: spin 1s linear infinite; display: inline-block;">
                        <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="4" stroke-dasharray="31.415, 31.415" stroke-linecap="round"></circle>
                    </svg>
                    Salvando...
                `;

                // Gather revisions data
                const edits = { patients: {} };
                document.querySelectorAll('.patient-view-section').forEach(view => {
                    const patientName = view.id.replace('patient-view-', '');
                    edits.patients[patientName] = { items: {} };

                    view.querySelectorAll('.score-select-compact').forEach(select => {
                        const itemId = select.dataset.itemId;
                        const score = parseInt(select.value);

                        const evidenceList = [];
                        view.querySelectorAll(`.evidence-editor-list[data-item-id="${itemId}"] .evidence-text-field`).forEach(span => {
                            evidenceList.push(span.textContent.trim());
                        });

                        edits.patients[patientName].items[itemId] = {
                            score: score,
                            evidence: evidenceList
                        };
                    });
                });

                try {
                    const response = await fetch(`/api/evaluations/${evaluationId}/revise`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(edits)
                    });
                    const data = await response.json();

                    if (response.ok && data.success) {
                        showToast('Revisão clínica salva com sucesso! Atualizando laudo...', 'success');
                        setTimeout(() => {
                            window.location.reload();
                        }, 1200);
                    } else {
                        throw new Error(data.error || 'Erro inesperado ao salvar revisão.');
                    }
                } catch (err) {
                    console.error("Save revision error:", err);
                    showToast(err.message || 'Falha ao conectar com o servidor.', 'error');
                    btnSaveRevision.disabled = false;
                    btnSaveRevision.innerHTML = originalText;
                }
            });
        }

        // =========================================================================
        // CLINICAL ANALYSIS HANDLERS
        // =========================================================================
        const btnCopySynthesis = document.getElementById('btn-copy-synthesis');
        const progressNoteTextarea = document.getElementById('group-progress-note-textarea');

        if (progressNoteTextarea) {
            const rawText = progressNoteTextarea.textContent.trim();
            if (rawText && !rawText.includes('<p>')) {
                // Split text into sentences using positive lookbehind for periods followed by spacing
                const sentences = rawText.split(/(?<=\.)\s+/).filter(s => s.trim().length > 0);
                if (sentences.length > 0) {
                    let htmlContent = '';
                    sentences.forEach(sentence => {
                        htmlContent += `<p class="synthesis-bullet-item">${sentence}</p>`;
                    });
                    progressNoteTextarea.innerHTML = htmlContent;
                }
            }
        }

        if (btnCopySynthesis && progressNoteTextarea) {
            btnCopySynthesis.addEventListener('click', () => {
                // innerText fetches only the textual sentences; CSS generated ::before markers (bullets) are excluded!
                const text = (progressNoteTextarea.value || progressNoteTextarea.innerText || progressNoteTextarea.textContent || '').trim();
                navigator.clipboard.writeText(text).then(() => {
                    const btnText = document.getElementById('btn-copy-text');
                    const originalText = btnText.textContent;

                    // Visual feedback
                    btnCopySynthesis.classList.add('btn-success-animated');
                    btnText.textContent = 'Copiado!';

                    setTimeout(() => {
                        btnCopySynthesis.classList.remove('btn-success-animated');
                        btnText.textContent = originalText;
                    }, 2000);
                }).catch(err => {
                    console.error('Failed to copy text: ', err);
                    showToast('Falha ao copiar a minuta.', 'error');
                });
            });
        }
    }

    // =========================================================================
    // STATE 2: PIPELINE POLLING LOGIC (When actively running)
    // =========================================================================
    if (initialTranscriptStatus && ['preprocessing', 'evaluating', 'queued'].includes(initialTranscriptStatus)) {
        addLog(`Iniciando monitoramento de execução da sessão ${sessionId}`, 'system');

        async function pollDatabaseStatus() {
            try {
                const response = await fetch(`/api/sessions/${sessionId}/status`);
                const data = await response.json();

                if (data.status === 'completed') {
                    addLog('Processamento finalizado com sucesso! Atualizando painel clínico', 'success');
                    setTimeout(() => {
                        window.location.reload();
                    }, 1500);
                } else if (data.status === 'failed') {
                    addLog(`Falha na pipeline: ${data.error || 'Erro desconhecido'}`, 'error');
                    setTimeout(() => {
                        window.location.reload();
                    }, 5000);
                } else {
                    // Update progress in the DOM
                    const progressSpan = document.querySelector('.status-badge[data-status="preprocessing"]');
                    if (progressSpan) {
                        progressSpan.textContent = `Processando (${data.progress_percent}%)`;
                    }

                    if (data.logs && data.logs.length > 0) {
                        // Clear wait message
                        if (logConsole.children.length === 1 && logConsole.children[0].textContent.includes('Aguardando')) {
                            logConsole.innerHTML = '';
                        }

                        const lastLogCount = parseInt(logConsole.dataset.logCount || '0');
                        if (data.logs.length > lastLogCount) {
                            for (let i = lastLogCount; i < data.logs.length; i++) {
                                addLog(data.logs[i]);
                            }
                            logConsole.dataset.logCount = data.logs.length;
                        }
                    } else {
                        addLog(`Pipeline em execução: status='${data.status}' | Progresso: ${data.progress_percent}%`);
                    }
                    setTimeout(pollDatabaseStatus, 2000);
                }
            } catch (err) {
                console.error("Error polling database status:", err);
                setTimeout(pollDatabaseStatus, 3000);
            }
        }

        pollDatabaseStatus();
    }

    // =========================================================================
    // STATE 3: UPLOAD WORKFLOW LOGIC (When no transcript / failed)
    // =========================================================================
    const dropZone = document.getElementById('dropZone');
    if (dropZone) {
        const fileInput = document.getElementById('fileInput');
        const selectedFilePanel = document.getElementById('selectedFilePanel');
        const fileName = document.getElementById('fileName');
        const removeFileBtn = document.getElementById('removeFileBtn');
        const startBtn = document.getElementById('startBtn');
        const newSessionView = document.getElementById('newSessionView');

        let selectedFile = null;
        let activePolling = false;

        // Click selection triggers
        dropZone.addEventListener('click', () => fileInput.click());

        // File selection input changes
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                handleFileSelection(fileInput.files[0]);
            }
        });

        // Drag & Drop
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                handleFileSelection(e.dataTransfer.files[0]);
            }
        });

        function handleFileSelection(file) {
            const ext = file.name.split('.').pop().toLowerCase();
            if (ext !== 'docx' && ext !== 'txt') {
                showToast('Apenas arquivos de transcrição .docx e .txt são suportados.', 'error');
                return;
            }
            selectedFile = file;
            fileName.textContent = file.name;
            hideElement(dropZone);
            showElement(selectedFilePanel, 'selected-file-panel-styled');
        }

        // Remove selected file
        removeFileBtn.addEventListener('click', (e) => {
            e.preventDefault();
            selectedFile = null;
            fileInput.value = '';
            hideElement(selectedFilePanel, 'selected-file-panel-styled');
            showElement(dropZone);
        });

        // Initiate upload and start async task
        startBtn.addEventListener('click', async () => {
            if (!selectedFile) {
                showToast('Por favor, selecione um arquivo de transcrição para fazer o upload.', 'error');
                return;
            }

            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('therapy_session_id', sessionId.toString());

            // Switch view state to Processing Console
            hideElement(newSessionView);
            showElement(processingView, 'active');
            statusTitle.textContent = 'Enviando Arquivo...';
            addLog(`Iniciando upload de ${selectedFile.name}`, 'system');

            try {
                const response = await fetch(`/therapy_sessions/${sessionId}/upload_transcript`, {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();

                if (response.ok && data.success) {
                    statusTitle.textContent = 'Processando Transcrição...';
                    statusDesc.textContent = 'O pipeline assíncrono de IA está ativado no banco de dados. Acompanhe os logs de telemetria abaixo.';

                    // Start polling database status
                    activePolling = true;
                    pollDatabaseStatusAfterUpload();
                } else {
                    handleUploadError(data.error || 'Erro no envio da transcrição.');
                }
            } catch (err) {
                handleUploadError('Falha de rede ao conectar-se com o servidor Symptoms Analyser.');
            }
        });

        function handleUploadError(msg) {
            statusTitle.textContent = 'Erro na Transcrição';
            statusDesc.textContent = 'A ingestão falhou antes de disparar o pipeline.';
            if (processingView) {
                processingView.classList.add('has-error');
            }
            addLog(msg, 'error');
        }

        async function pollDatabaseStatusAfterUpload() {
            if (!activePolling) return;

            try {
                const response = await fetch(`/api/sessions/${sessionId}/status`);
                const data = await response.json();

                if (data.status === 'completed') {
                    addLog('Diagnóstico TDPM-20 finalizado com sucesso! Atualizando laudo clínico', 'success');
                    setTimeout(() => {
                        window.location.reload();
                    }, 1500);
                } else if (data.status === 'failed') {
                    handleUploadError(data.error || 'Falha inesperada no processamento da transcrição.');
                } else {
                    if (data.logs && data.logs.length > 0) {
                        const lastLogCount = parseInt(logConsole.dataset.logCount || '0');
                        if (data.logs.length > lastLogCount) {
                            for (let i = lastLogCount; i < data.logs.length; i++) {
                                addLog(data.logs[i]);
                            }
                            logConsole.dataset.logCount = data.logs.length;
                        }
                    } else {
                        addLog(`Status da pipeline: status='${data.status}' | Progresso: ${data.progress_percent}%`);
                    }
                    setTimeout(pollDatabaseStatusAfterUpload, 2000);
                }
            } catch (err) {
                console.error("Polling error after upload:", err);
                setTimeout(pollDatabaseStatusAfterUpload, 3000);
            }
        }
    }
});
