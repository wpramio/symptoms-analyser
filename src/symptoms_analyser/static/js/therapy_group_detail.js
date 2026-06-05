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
    const graphData     = _page.graphData;

    // ── Interaction Scroll List (uses raw edges from synthesis) ───────────────
    if (synthesisData && synthesisData.interactions_mapping) {
        const interactionScrollList = document.getElementById('interactionScrollList');
        if (interactionScrollList) {
            const rawEdges = synthesisData.interactions_mapping.edges || [];
            if (rawEdges.length > 0) {
                interactionScrollList.innerHTML = '';
                rawEdges.forEach(edge => {
                    const card = document.createElement('div');
                    card.className = `interaction-item-card ${edge.type}`;

                    const meta = document.createElement('div');
                    meta.className = 'interaction-meta-line';

                    const sourceText = document.createElement('strong');
                    sourceText.textContent = edge.source;
                    sourceText.style.color = getSpeakerColor(edge.source);

                    const targetText = document.createElement('strong');
                    targetText.textContent = edge.target;
                    targetText.style.color = getSpeakerColor(edge.target);

                    const badge = document.createElement('span');
                    badge.className = `interaction-type-badge ${edge.type}`;
                    badge.textContent = edge.type;

                    meta.appendChild(sourceText);
                    meta.appendChild(document.createTextNode(' ➔ '));
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
    }

    // ── Cytoscape Social Network Graph (consumes pre-computed graphData) ──────
    if (graphData) {
        const tooltipEl = document.getElementById('graphTooltip');
        const graphContainer = document.getElementById('socialNetworkGraph');

        if (graphContainer) {
            let cyInstance = null;

            // All graph analysis is pre-computed server-side
            const { nodes_ordered, subgroups, isolated, node_meta,
                    aggregated_edges, pair_edge_counts } = graphData;

            const uniqueNodes = nodes_ordered.map(id => ({ id, label: id }));

            // Layout coordinates inside a 440x440 viewport
            const nodeCoords = {};

            if (subgroups.length === 0) {
                // Fallback: place all nodes in a circle
                const CX = 220;
                const CY = 200;
                const R = 130;
                uniqueNodes.forEach((node, idx) => {
                    const angle = (2 * Math.PI * idx) / uniqueNodes.length - Math.PI / 2;
                    nodeCoords[node.id] = {
                        x: CX + R * Math.cos(angle),
                        y: CY + R * Math.sin(angle)
                    };
                });
            } else if (subgroups.length === 1) {
                // Single subgroup: place it in the center, and isolated nodes at the bottom
                const CX = 220;
                const CY = 170;
                const R = 110;
                const subNodes = subgroups[0];
                subNodes.forEach((nodeId, idx) => {
                    const angle = (2 * Math.PI * idx) / subNodes.length - Math.PI / 2;
                    nodeCoords[nodeId] = {
                        x: CX + R * Math.cos(angle),
                        y: CY + R * Math.sin(angle)
                    };
                });
            } else if (subgroups.length === 2) {
                // Two subgroups: place them side-by-side
                const centers = [
                    { x: 115, y: 165, r: 70 },
                    { x: 325, y: 165, r: 70 }
                ];
                subgroups.forEach((subNodes, subIdx) => {
                    const center = centers[subIdx] || { x: 220, y: 165, r: 70 };
                    subNodes.forEach((nodeId, idx) => {
                        const angle = (2 * Math.PI * idx) / subNodes.length - Math.PI / 2;
                        nodeCoords[nodeId] = {
                            x: center.x + center.r * Math.cos(angle),
                            y: center.y + center.r * Math.sin(angle)
                        };
                    });
                });
            } else if (subgroups.length === 3) {
                // Three subgroups: place them in a triangle
                const centers = [
                    { x: 115, y: 115, r: 55 },
                    { x: 325, y: 115, r: 55 },
                    { x: 220, y: 270, r: 55 }
                ];
                subgroups.forEach((subNodes, subIdx) => {
                    const center = centers[subIdx] || { x: 220, y: 165, r: 55 };
                    subNodes.forEach((nodeId, idx) => {
                        const angle = (2 * Math.PI * idx) / subNodes.length - Math.PI / 2;
                        nodeCoords[nodeId] = {
                            x: center.x + center.r * Math.cos(angle),
                            y: center.y + center.r * Math.sin(angle)
                        };
                    });
                });
            } else {
                // Fallback: place all non-isolated nodes in one big circle
                const CX = 220;
                const CY = 175;
                const R = 115;
                const allSubNodes = [];
                subgroups.forEach(comp => allSubNodes.push(...comp));
                allSubNodes.forEach((nodeId, idx) => {
                    const angle = (2 * Math.PI * idx) / allSubNodes.length - Math.PI / 2;
                    nodeCoords[nodeId] = {
                        x: CX + R * Math.cos(angle),
                        y: CY + R * Math.sin(angle)
                    };
                });
            }

            // Place isolated nodes in a neat horizontal row at the bottom of the viewport
            if (isolated.length > 0) {
                const startX = 50;
                const endX = 390;
                const width = endX - startX;
                const step = isolated.length > 1 ? width / (isolated.length - 1) : width / 2;
                const isolatedY = 400;

                const sortedIsolated = [...isolated].sort((a, b) => {
                    const numA = parseInt(a.match(/\d+/)?.[0] || 0, 10);
                    const numB = parseInt(b.match(/\d+/)?.[0] || 0, 10);
                    return numA - numB;
                });

                sortedIsolated.forEach((nodeId, idx) => {
                    const x = isolated.length === 1 ? 220 : startX + idx * step;
                    nodeCoords[nodeId] = {
                        x: x,
                        y: isolatedY
                    };
                });
            }

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
                        apoio: '#10b981',
                        validacao: '#3b82f6',
                        confronto: '#f59e0b'
                    };

                    aggregated_edges.forEach((edge, idx) => {
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
                                is_bridge: edge.is_bridge,
                                evidences: edge.evidences || [],
                                sessions: edge.sessions || []
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
                                    'width': function(ele) {
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
                                selector: 'edge[?is_bridge]',
                                style: {
                                    'line-style': 'dashed',
                                    'line-dash-pattern': [6, 4]
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
                                    'border-color': function(ele) {
                                        return ele.data('ringColor') || '#ffffff';
                                    },
                                    'border-width': function(ele) {
                                        return ele.data('ringColor') ? 3.5 : 2.5;
                                    },
                                    'opacity': 1
                                }
                            },
                            {
                                selector: 'edge.highlighted',
                                style: {
                                    'opacity': 1,
                                    'width': function(ele) {
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

                    // Project model coordinates to draw background separator and text on canvas
                    cyInstance.on('render', () => {
                        const r = cyInstance.renderer();
                        if (!r || !r.gc || isolated.length === 0) return;
                        const ctx = r.gc;
                        const pan = cyInstance.pan();
                        const zoom = cyInstance.zoom();

                        ctx.save();
                        ctx.translate(pan.x, pan.y);
                        ctx.scale(zoom, zoom);

                        // Separator line
                        ctx.beginPath();
                        ctx.moveTo(25, 356);
                        ctx.lineTo(415, 356);
                        ctx.strokeStyle = 'rgba(148, 163, 184, 0.25)';
                        ctx.lineWidth = 1;
                        ctx.setLineDash([3, 3]);
                        ctx.stroke();

                        // Label
                        ctx.fillStyle = '#64748b';
                        ctx.font = "bold 10px 'Inter', sans-serif";
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'bottom';
                        ctx.fillText('MEMBROS ISOLADOS', 220, 350);

                        ctx.restore();
                    });

                    // Event listeners
                    let hoverTimeout = null;

                    cyInstance.on('mouseover', 'node', (e) => {
                        if (hoverTimeout) clearTimeout(hoverTimeout);
                        const node = e.target;
                        const patientId = node.id();
                        const origEvent = e.originalEvent;
                        const mouseX = origEvent.clientX;
                        const mouseY = origEvent.clientY;

                        hoverTimeout = setTimeout(() => {
                            const sent = aggregated_edges.filter(edge => edge.source === patientId).reduce((sum, edge) => sum + edge.count, 0);
                            const rec = aggregated_edges.filter(edge => edge.target === patientId).reduce((sum, edge) => sum + edge.count, 0);

                            const wrapperRect = graphContainer.parentNode.getBoundingClientRect();
                            let x = mouseX - wrapperRect.left;
                            let y = mouseY - wrapperRect.top - 10;

                            if (tooltipEl) {
                                const compInfo = node_meta[patientId];
                                let subtitleHtml = '';
                                if (compInfo && compInfo.type === 'subgroup') {
                                    subtitleHtml = `<div style="font-weight: 800; color: ${compInfo.color}; font-size: 0.7rem; margin-top: 0.1rem; text-transform: uppercase;">${compInfo.name}</div>`;
                                } else {
                                    subtitleHtml = `<div style="font-weight: 800; color: #94a3b8; font-size: 0.7rem; margin-top: 0.1rem; text-transform: uppercase;">Paciente Isolado</div>`;
                                }

                                tooltipEl.innerHTML = `
                                    <div class="tooltip-title" style="margin-bottom: 0px;"><strong>${patientId}</strong></div>
                                    ${subtitleHtml}
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
                                const isBridge = edgeData.is_bridge;
                                const color = edgeData.color;
                                const interactionLabel = edgeData.count === 1 ? 'interação' : 'interações';
                                let subtitleHtml = `<div style="font-weight: 800; color: ${color}; text-transform: uppercase; font-size: 0.65rem; margin-bottom: 0.25rem;">${edgeData.type} (${edgeData.count} ${interactionLabel})</div>`;
                                if (isBridge) {
                                    subtitleHtml = `
                                        <div style="display: flex; gap: 0.25rem; align-items: center; margin-bottom: 0.25rem;">
                                            <span style="font-weight: 800; color: ${color}; text-transform: uppercase; font-size: 0.65rem;">${edgeData.type} (${edgeData.count})</span>
                                            <span style="background-color: #f59e0b; color: #0f172a; font-weight: 800; font-size: 0.55rem; padding: 0.05rem 0.25rem; border-radius: 4px; text-transform: uppercase; border: 1px solid #d97706;">Ponte</span>
                                        </div>
                                    `;
                                }

                                let tooltipHtml = `
                                    <div class="tooltip-title"><strong>${sourceId}</strong> ➜ <strong>${targetId}</strong></div>
                                    ${subtitleHtml}
                                `;

                                const limit = 3;
                                const displayed = edgeData.evidences.slice(0, limit);
                                tooltipHtml += `<div class="tooltip-body" style="max-height: 120px; overflow-y: auto; display: flex; flex-direction: column; gap: 0.25rem; margin-top: 0.25rem;">`;
                                displayed.forEach((ev, idx) => {
                                    const sessName = edgeData.sessions[idx] ? `[${edgeData.sessions[idx]}] ` : '';
                                    tooltipHtml += `<div style="border-left: 2px solid ${color}; padding-left: 0.25rem; margin-bottom: 0.15rem; font-style: italic;">${sessName}"${ev}"</div>`;
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
                            edge.source().removeClass('dimmed');
                            edge.target().removeClass('dimmed');
                        }, 50);
                    });

                    cyInstance.on('mouseout', 'edge', () => {
                        if (hoverTimeout) clearTimeout(hoverTimeout);
                        if (tooltipEl) tooltipEl.style.opacity = '0';
                        cyInstance.elements().removeClass('dimmed');
                        cyInstance.elements().removeClass('highlighted');
                    });

                    // Generate Subgroups Legend
                    const subgroupsLegendEl = document.getElementById('subgroupsLegend');
                    const subgroupsListEl = document.getElementById('subgroupsList');
                    if (subgroupsLegendEl && subgroupsListEl) {
                        subgroupsListEl.innerHTML = '';
                        if (subgroups.length > 0) {
                            subgroupsLegendEl.style.display = 'block';
                            subgroups.forEach((comp, idx) => {
                                const compInfo = node_meta[comp[0]];
                                const item = document.createElement('div');
                                item.className = 'subgroup-legend-item';
                                item.style.display = 'flex';
                                item.style.alignItems = 'center';
                                item.style.gap = '0.5rem';
                                item.style.cursor = 'pointer';
                                item.style.padding = '0.25rem 0.5rem';
                                item.style.borderRadius = '4px';
                                item.style.transition = 'background-color 0.2s';

                                const sortedMembers = [...comp].sort((a, b) => {
                                    const numA = parseInt(a.match(/\d+/)?.[0] || 0, 10);
                                    const numB = parseInt(b.match(/\d+/)?.[0] || 0, 10);
                                    return numA - numB;
                                });

                                item.innerHTML = `
                                    <span style="width: 12px; height: 12px; border-radius: 50%; background-color: ${compInfo.color}; display: inline-block; border: 2px solid white; box-shadow: 0 0 0 1px ${compInfo.color}"></span>
                                    <span style="font-weight: 600; color: var(--text-main);">${compInfo.name}</span>
                                    <span style="color: var(--text-muted); font-size: 0.75rem;">(${sortedMembers.join(', ')})</span>
                                `;

                                item.addEventListener('mouseenter', () => {
                                    item.style.backgroundColor = 'rgba(59, 130, 246, 0.05)';
                                    cyInstance.elements().addClass('dimmed');
                                    
                                    comp.forEach(memberId => {
                                        const node = cyInstance.getElementById(memberId);
                                        node.removeClass('dimmed');
                                        node.addClass('highlighted');
                                        node.data('ringColor', compInfo.color);
                                    });

                                    cyInstance.edges().forEach(edge => {
                                        const sourceId = edge.source().id();
                                        const targetId = edge.target().id();
                                        if (comp.includes(sourceId) && comp.includes(targetId)) {
                                            edge.removeClass('dimmed');
                                            edge.addClass('highlighted');
                                        }
                                    });
                                });

                                item.addEventListener('mouseleave', () => {
                                    item.style.backgroundColor = 'transparent';
                                    cyInstance.elements().removeClass('dimmed');
                                    cyInstance.elements().removeClass('highlighted');
                                    comp.forEach(memberId => {
                                        cyInstance.getElementById(memberId).removeData('ringColor');
                                    });
                                });

                                subgroupsListEl.appendChild(item);
                            });

                            if (isolated.length > 0) {
                                const sortedIsolated = [...isolated].sort((a, b) => {
                                    const numA = parseInt(a.match(/\d+/)?.[0] || 0, 10);
                                    const numB = parseInt(b.match(/\d+/)?.[0] || 0, 10);
                                    return numA - numB;
                                });
                                const item = document.createElement('div');
                                item.style.display = 'flex';
                                item.style.alignItems = 'center';
                                item.style.gap = '0.5rem';
                                item.style.cursor = 'pointer';
                                item.style.padding = '0.25rem 0.5rem';
                                item.style.borderRadius = '4px';
                                item.style.transition = 'background-color 0.2s';
                                item.innerHTML = `
                                    <span style="width: 12px; height: 12px; border-radius: 50%; background-color: #94a3b8; display: inline-block; border: 2px solid white; box-shadow: 0 0 0 1px #94a3b8"></span>
                                    <span style="font-weight: 600; color: var(--text-main);">Membros Isolados</span>
                                    <span style="color: var(--text-muted); font-size: 0.75rem;">(${sortedIsolated.join(', ')})</span>
                                `;

                                item.addEventListener('mouseenter', () => {
                                    item.style.backgroundColor = 'rgba(59, 130, 246, 0.05)';
                                    cyInstance.elements().addClass('dimmed');
                                    isolated.forEach(memberId => {
                                        const node = cyInstance.getElementById(memberId);
                                        node.removeClass('dimmed');
                                        node.addClass('highlighted');
                                    });
                                });

                                item.addEventListener('mouseleave', () => {
                                    item.style.backgroundColor = 'transparent';
                                    cyInstance.elements().removeClass('dimmed');
                                    cyInstance.elements().removeClass('highlighted');
                                });

                                subgroupsListEl.appendChild(item);
                            }
                        } else {
                            subgroupsLegendEl.style.display = 'none';
                        }
                    }

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
});
