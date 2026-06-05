document.addEventListener("DOMContentLoaded", () => {
    // Tab switching
    const tabButtons = document.querySelectorAll(".session-tab-btn");
    const tabPanels = document.querySelectorAll(".session-tab-panel");

    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            tabButtons.forEach(b => b.classList.remove("active"));
            tabPanels.forEach(p => p.classList.remove("active"));

            btn.classList.add("active");
            const target = btn.dataset.target;
            document.getElementById(target).classList.add("active");
        });
    });

    // Load page-level data island
    const pageDataEl = document.getElementById('page-data');
    if (!pageDataEl) return;
    const _page = JSON.parse(pageDataEl.textContent);

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
        'hsl(45,  90%, 45%)',  // Amber (Index 10 -> Paciente10)
        'hsl(195, 85%, 45%)',  // Cyan/Blue (Index 11 -> Paciente11)
        'hsl(340, 75%, 55%)',  // Crimson
        'hsl(120, 50%, 45%)',  // Sage Green
        'hsl(210, 80%, 55%)',  // Sky Blue
        'hsl(295, 70%, 50%)',  // Violet
        'hsl(15,  85%, 50%)',  // Terracotta
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

    // =========================================================================
    // Speaking Airtime (Tempo de Fala) Donut Chart rendering
    // =========================================================================
    const airtimeData = _page.airtime;
    if (airtimeData && airtimeData.speakers && airtimeData.speakers.length > 0) {
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
    // Social Cohesion & Mutual Support Network Visualization
    // =========================================================================
    const synthesisData = _page.synthesis;
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

                    if (edge.session_name) {
                        const sessionSpan = document.createElement('span');
                        sessionSpan.className = 'interaction-session-name';
                        sessionSpan.textContent = ` (${edge.session_name})`;
                        sessionSpan.style.fontSize = '0.75rem';
                        sessionSpan.style.color = 'var(--text-muted)';
                        meta.appendChild(sessionSpan);
                    }

                    const quote = document.createElement('div');
                    quote.className = 'interaction-evidence-text';
                    quote.textContent = `"${edge.evidence}"`;

                    card.appendChild(meta);
                    card.appendChild(quote);
                    interactionScrollList.appendChild(card);
                });
            } else {
                interactionScrollList.innerHTML = '<p class="text-muted text-medium">Nenhuma interação identificada para este grupo.</p>';
            }
        }

        // 3. Render Interactive SVG Social Network Graph
        const graphEdgesG = document.getElementById('graphEdges');
        const graphNodesG = document.getElementById('graphNodes');
        const tooltipEl = document.getElementById('graphTooltip');
        const svgEl = document.getElementById('socialNetworkGraph');

        if (graphEdgesG && graphNodesG && svgEl) {
            graphEdgesG.innerHTML = '';
            graphNodesG.innerHTML = '';
            let hoverTimeout = null;

            const nodes = supportMapping.nodes || [];
            const edges = supportMapping.edges || [];

            // If we have edges but no nodes were parsed, auto-generate nodes from speakers
            let nodeSet = new Set(nodes.map(n => n.id));
            if (nodeSet.size === 0 && edges.length > 0) {
                edges.forEach(edge => {
                    nodeSet.add(edge.source);
                    nodeSet.add(edge.target);
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

            // Draw directed edges (interaction lines)
            const typeColors = {
                apoio: '#10b981',      // Green
                validacao: '#3b82f6',  // Blue
                confronto: '#f59e0b'   // Orange
            };

            // Count parallel edges to apply offset/curving if multiple interactions exist between same nodes
            const edgeCounts = {};
            edges.forEach(edge => {
                const key = [edge.source, edge.target].sort().join('-');
                edgeCounts[key] = (edgeCounts[key] || 0) + 1;
            });

            const drawnEdges = {};
            edges.forEach((edge, idx) => {
                const start = nodeCoords[edge.source];
                const end = nodeCoords[edge.target];
                if (!start || !end) return;

                const color = typeColors[edge.type] || '#64748b';
                const key = [edge.source, edge.target].sort().join('-');
                drawnEdges[key] = (drawnEdges[key] || 0) + 1;

                // If source and target are same, skip self-loop to keep it clean
                if (edge.source === edge.target) return;

                // Math to draw arrows: curve if there are parallel lines
                let pathD = '';
                const midX = (start.x + end.x) / 2;
                const midY = (start.y + end.y) / 2;

                // Calculate normal vector for displacement
                const dx = end.x - start.x;
                const dy = end.y - start.y;
                const len = Math.sqrt(dx * dx + dy * dy);
                const nx = -dy / len;
                const ny = dx / len;

                // Adjust curve depth based on edge index
                const isBidirectional = (edges.some(e => e.source === edge.target && e.target === edge.source));
                const curveDisplacement = isBidirectional ? 16 : 0;
                const ctrlX = midX + nx * curveDisplacement;
                const ctrlY = midY + ny * curveDisplacement;

                if (isBidirectional) {
                    pathD = `M ${start.x} ${start.y} Q ${ctrlX} ${ctrlY} ${end.x} ${end.y}`;
                } else {
                    pathD = `M ${start.x} ${start.y} L ${end.x} ${end.y}`;
                }

                // Create SVG path element
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                path.setAttribute('d', pathD);
                path.setAttribute('fill', 'none');
                path.setAttribute('stroke', color);
                path.setAttribute('stroke-width', '3');
                path.setAttribute('marker-end', `url(#arrow-${edge.type})`);
                path.setAttribute('class', 'edge-path');
                path.setAttribute('opacity', '0.75');

                // Attach tooltip data attributes
                path.dataset.source = edge.source;
                path.dataset.target = edge.target;
                path.dataset.type = edge.type;
                path.dataset.evidence = edge.evidence;

                // Hover interaction effects
                path.addEventListener('mouseenter', (e) => {
                    if (hoverTimeout) clearTimeout(hoverTimeout);
                    hoverTimeout = setTimeout(() => {
                        const wrapperRect = svgEl.parentNode.getBoundingClientRect();

                        // Coordinates relative to graph wrapper container
                        let x = e.clientX - wrapperRect.left;
                        let y = e.clientY - wrapperRect.top - 10;

                        // Populate tooltip
                        if (tooltipEl) {
                            let tooltipHtml = `
                                <div class="tooltip-title"><strong>${edge.source}</strong> ➜ <strong>${edge.target}</strong></div>
                                <div style="font-weight: 800; color: ${color}; text-transform: uppercase; font-size: 0.65rem; margin-bottom: 0.25rem;">${edge.type}</div>
                            `;
                            if (edge.session_name) {
                                tooltipHtml += `<div style="font-size: 0.7rem; color: #cbd5e1; margin-bottom: 0.25rem;">Sessão: ${edge.session_name}</div>`;
                            }
                            tooltipHtml += `<div class="tooltip-body">"${edge.evidence}"</div>`;
                            
                            tooltipEl.innerHTML = tooltipHtml;
                            tooltipEl.style.left = `${x}px`;
                            tooltipEl.style.top = `${y}px`;
                            tooltipEl.style.transform = 'translate(-50%, -100%)';
                            tooltipEl.style.opacity = '1';
                        }

                        // Dim other paths and nodes
                        document.querySelectorAll('.edge-path').forEach(p => {
                            if (p !== path) p.style.opacity = '0.15';
                        });
                        document.querySelectorAll('.node-circle').forEach(circle => {
                            const pid = circle.dataset.patientId;
                            if (pid !== edge.source && pid !== edge.target) {
                                circle.style.opacity = '0.3';
                            }
                        });
                    }, 50);
                });

                path.addEventListener('mouseleave', () => {
                    if (hoverTimeout) clearTimeout(hoverTimeout);
                    if (tooltipEl) tooltipEl.style.opacity = '0';
                    document.querySelectorAll('.edge-path').forEach(p => p.style.opacity = '0.75');
                    document.querySelectorAll('.node-circle').forEach(c => c.style.opacity = '1');
                });

                graphEdgesG.appendChild(path);
            });

            // Draw patient nodes (circles)
            uniqueNodes.forEach(node => {
                const coord = nodeCoords[node.id];
                if (!coord) return;

                const nodeColor = getSpeakerColor(node.id);
                const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');

                // SVG Circle
                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', coord.x.toString());
                circle.setAttribute('cy', coord.y.toString());
                circle.setAttribute('r', '15');
                circle.setAttribute('fill', nodeColor);
                circle.setAttribute('class', 'node-circle');
                circle.dataset.patientId = node.id;

                // SVG Text label
                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', coord.x.toString());
                text.setAttribute('y', (coord.y + 22).toString()); // Offset label below the circle node
                text.setAttribute('class', 'node-label');
                text.textContent = node.id;

                g.appendChild(circle);
                g.appendChild(text);

                // Node Hover interaction effects
                circle.addEventListener('mouseenter', (e) => {
                    if (hoverTimeout) clearTimeout(hoverTimeout);
                    hoverTimeout = setTimeout(() => {
                        const patientId = node.id;
                        const sent = edges.filter(e => e.source === patientId).length;
                        const rec = edges.filter(e => e.target === patientId).length;

                        const wrapperRect = svgEl.parentNode.getBoundingClientRect();
                        let x = coord.x * (wrapperRect.width / 320);
                        let y = (coord.y - 20) * (wrapperRect.height / 320);

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

                        // Focus/Highlight connected paths
                        document.querySelectorAll('.edge-path').forEach(p => {
                            const isConnected = p.dataset.source === patientId || p.dataset.target === patientId;
                            p.style.opacity = isConnected ? '1' : '0.1';
                            if (isConnected) p.style.strokeWidth = '4px';
                        });

                        document.querySelectorAll('.node-circle').forEach(c => {
                            if (c !== circle) c.style.opacity = '0.3';
                        });
                    }, 50);
                });

                circle.addEventListener('mouseleave', () => {
                    if (hoverTimeout) clearTimeout(hoverTimeout);
                    if (tooltipEl) tooltipEl.style.opacity = '0';
                    document.querySelectorAll('.edge-path').forEach(p => {
                        p.style.opacity = '0.75';
                        p.style.strokeWidth = '3';
                    });
                    document.querySelectorAll('.node-circle').forEach(c => c.style.opacity = '1');
                });

                graphNodesG.appendChild(g);
            });
        }
    }
});
