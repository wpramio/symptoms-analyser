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

    // ── SVG Social Network Graph (consumes pre-computed graphData) ────────────
    if (graphData) {
        const graphEdgesG = document.getElementById('graphEdges');
        const graphNodesG = document.getElementById('graphNodes');
        const tooltipEl   = document.getElementById('graphTooltip');
        const svgEl       = document.getElementById('socialNetworkGraph');

        if (graphEdgesG && graphNodesG && svgEl) {
            graphEdgesG.innerHTML = '';
            graphNodesG.innerHTML = '';
            let hoverTimeout = null;

            // All graph analysis is pre-computed server-side
            const { nodes_ordered, subgroups, isolated, node_meta,
                    aggregated_edges, pair_edge_counts } = graphData;

            const uniqueNodes = nodes_ordered.map(id => ({ id, label: id }));

            // Layout coordinates inside a 320x320 viewport
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

            // Place isolated nodes in a neat horizontal row at the bottom of the SVG
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

            // Draw directed edges — aggregated and bridge-flagged by the server
            const typeColors = {
                apoio: '#10b981',
                validacao: '#3b82f6',
                confronto: '#f59e0b'
            };

            const drawnEdges = {};
            aggregated_edges.forEach((edge, idx) => {
                const start = nodeCoords[edge.source];
                const end = nodeCoords[edge.target];
                if (!start || !end) return;

                const color = typeColors[edge.type] || '#64748b';
                const key = [edge.source, edge.target].sort().join('-');
                drawnEdges[key] = (drawnEdges[key] || 0) + 1;
                const lineIndex = drawnEdges[key] - 1;

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

                // Spread the curves: e.g. -14, 14, -28, 28...
                const hasMultipleLines = pair_edge_counts[key] > 1;
                let curveDisplacement = 0;
                if (hasMultipleLines) {
                    const spread = 14;
                    curveDisplacement = (lineIndex % 2 === 0 ? 1 : -1) * Math.ceil(lineIndex / 2) * spread;
                    if (pair_edge_counts[key] === 2) {
                        curveDisplacement = (lineIndex === 0 ? -12 : 12);
                    }
                }

                // If bidirectional and has 1 line in each direction, apply curves to separate them
                const isBidirectional = aggregated_edges.some(e => e.source === edge.target && e.target === edge.source);
                if (!hasMultipleLines && isBidirectional) {
                    curveDisplacement = 12;
                }

                if (curveDisplacement !== 0) {
                    const ctrlX = midX + nx * curveDisplacement;
                    const ctrlY = midY + ny * curveDisplacement;
                    pathD = `M ${start.x} ${start.y} Q ${ctrlX} ${ctrlY} ${end.x} ${end.y}`;
                } else {
                    pathD = `M ${start.x} ${start.y} L ${end.x} ${end.y}`;
                }

                // Create SVG path element
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                path.setAttribute('d', pathD);
                path.setAttribute('fill', 'none');
                path.setAttribute('stroke', color);

                // Opacity & Stroke Width based on frequency count
                const strokeWidth = 2 + Math.min(edge.count * 0.75, 5.5);
                path.setAttribute('stroke-width', strokeWidth.toString());
                path.setAttribute('marker-end', `url(#arrow-${edge.type})`);
                path.setAttribute('class', 'edge-path');
                path.setAttribute('opacity', '0.75');

                if (edge.is_bridge) {
                    path.setAttribute('stroke-dasharray', '5,5');
                }

                // Attach tooltip data attributes
                path.dataset.source = edge.source;
                path.dataset.target = edge.target;
                path.dataset.type = edge.type;
                path.dataset.originalWidth = strokeWidth.toString();

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
                            const interactionLabel = edge.count === 1 ? 'interação' : 'interações';
                            let subtitleHtml = `<div style="font-weight: 800; color: ${color}; text-transform: uppercase; font-size: 0.65rem; margin-bottom: 0.25rem;">${edge.type} (${edge.count} ${interactionLabel})</div>`;
                            if (isBridge) {
                                subtitleHtml = `
                                    <div style="display: flex; gap: 0.25rem; align-items: center; margin-bottom: 0.25rem;">
                                        <span style="font-weight: 800; color: ${color}; text-transform: uppercase; font-size: 0.65rem;">${edge.type} (${edge.count})</span>
                                        <span style="background-color: #f59e0b; color: #0f172a; font-weight: 800; font-size: 0.55rem; padding: 0.05rem 0.25rem; border-radius: 4px; text-transform: uppercase; border: 1px solid #d97706;">Ponte</span>
                                    </div>
                                `;
                            }

                            let tooltipHtml = `
                                <div class="tooltip-title"><strong>${edge.source}</strong> ➜ <strong>${edge.target}</strong></div>
                                ${subtitleHtml}
                            `;

                            // List unique sessions or limit list of evidences
                            const limit = 3;
                            const displayed = edge.evidences.slice(0, limit);
                            tooltipHtml += `<div class="tooltip-body" style="max-height: 120px; overflow-y: auto; display: flex; flex-direction: column; gap: 0.25rem; margin-top: 0.25rem;">`;
                            displayed.forEach((ev, idx) => {
                                const sessName = edge.sessions[idx] ? `[${edge.sessions[idx]}] ` : '';
                                tooltipHtml += `<div style="border-left: 2px solid ${color}; padding-left: 0.25rem; margin-bottom: 0.15rem; font-style: italic;">${sessName}"${ev}"</div>`;
                            });
                            if (edge.evidences.length > limit) {
                                tooltipHtml += `<div style="font-size: 0.65rem; color: #94a3b8; text-align: right; margin-top: 0.1rem;">+ ${edge.evidences.length - limit} interações...</div>`;
                            }
                            tooltipHtml += `</div>`;

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

                // All nodes start with a neutral white border.
                // The subgroup color ring is revealed only on legend hover.
                circle.style.stroke = '#ffffff';
                circle.style.strokeWidth = '2px';

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
                    // Capture mouse coords immediately — they won't be valid inside setTimeout
                    const mouseX = e.clientX;
                    const mouseY = e.clientY;
                    hoverTimeout = setTimeout(() => {
                        const patientId = node.id;
                        const sent = aggregated_edges.filter(e => e.source === patientId).reduce((sum, e) => sum + e.count, 0);
                        const rec = aggregated_edges.filter(e => e.target === patientId).reduce((sum, e) => sum + e.count, 0);

                        const wrapperRect = svgEl.parentNode.getBoundingClientRect();
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

            // Draw a separator line and label for isolated nodes inside the SVG if they exist
            if (isolated.length > 0) {
                const sepLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                sepLine.setAttribute('x1', '25');
                sepLine.setAttribute('y1', '356');
                sepLine.setAttribute('x2', '415');
                sepLine.setAttribute('y2', '356');
                sepLine.setAttribute('stroke', 'rgba(148, 163, 184, 0.25)');
                sepLine.setAttribute('stroke-width', '1');
                sepLine.setAttribute('stroke-dasharray', '3,3');
                graphNodesG.appendChild(sepLine);

                const sepText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                sepText.setAttribute('x', '220');
                sepText.setAttribute('y', '350');
                sepText.setAttribute('text-anchor', 'middle');
                sepText.setAttribute('fill', '#64748b');
                sepText.setAttribute('font-size', '10px');
                sepText.setAttribute('font-weight', '700');
                sepText.setAttribute('letter-spacing', '0.05em');
                sepText.textContent = 'MEMBROS ISOLADOS';
                graphNodesG.appendChild(sepText);
            }

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

                        // Sort members numerically for cleaner presentation
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

                        // Hover highlighting
                        item.addEventListener('mouseenter', () => {
                            item.style.backgroundColor = 'rgba(59, 130, 246, 0.05)';
                            document.querySelectorAll('.edge-path').forEach(p => {
                                const isInternal = comp.includes(p.dataset.source) && comp.includes(p.dataset.target);
                                p.style.opacity = isInternal ? '1' : '0.05';
                                if (isInternal) p.style.strokeWidth = '4px';
                            });
                            document.querySelectorAll('.node-circle').forEach(c => {
                                const isMember = comp.includes(c.dataset.patientId);
                                c.style.opacity = isMember ? '1' : '0.15';
                                // Reveal the subgroup color ring on member nodes
                                if (isMember) {
                                    c.style.stroke = compInfo.color;
                                    c.style.strokeWidth = '3.5px';
                                }
                            });
                        });

                        item.addEventListener('mouseleave', () => {
                            item.style.backgroundColor = 'transparent';
                            document.querySelectorAll('.edge-path').forEach(p => {
                                p.style.opacity = '0.75';
                                p.style.strokeWidth = '3';
                            });
                            document.querySelectorAll('.node-circle').forEach(c => {
                                c.style.opacity = '1';
                                // Reset border back to neutral white
                                c.style.stroke = '#ffffff';
                                c.style.strokeWidth = '2px';
                            });
                        });

                        subgroupsListEl.appendChild(item);
                    });

                    // Also show isolated members if any
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
                            document.querySelectorAll('.edge-path').forEach(p => {
                                p.style.opacity = '0.05';
                            });
                            document.querySelectorAll('.node-circle').forEach(c => {
                                const isIsolated = isolated.includes(c.dataset.patientId);
                                c.style.opacity = isIsolated ? '1' : '0.15';
                            });
                        });

                        item.addEventListener('mouseleave', () => {
                            item.style.backgroundColor = 'transparent';
                            document.querySelectorAll('.edge-path').forEach(p => {
                                p.style.opacity = '0.75';
                                p.style.strokeWidth = '3';
                            });
                            document.querySelectorAll('.node-circle').forEach(c => c.style.opacity = '1');
                        });

                        subgroupsListEl.appendChild(item);
                    }
                } else {
                    subgroupsLegendEl.style.display = 'none';
                }
            }

            // =========================================================
            // Initialize svg-pan-zoom for interactive navigation
            // svg-pan-zoom must not be initialized on a hidden element —
            // it can't measure dimensions when display:none, producing a
            // broken transform. We lazy-init on the first time the tab
            // becomes visible instead.
            // =========================================================
            let panZoomInstance = null;

            function initPanZoom() {
                if (panZoomInstance || typeof svgPanZoom === 'undefined') return;

                // rAF ensures the browser has painted the tab as visible
                requestAnimationFrame(() => {
                    panZoomInstance = svgPanZoom(svgEl, {
                        zoomEnabled: true,
                        panEnabled: true,
                        controlIconsEnabled: false,
                        fit: false,
                        center: true,
                        minZoom: 0.25,
                        maxZoom: 8,
                        zoomScaleSensitivity: 0.25,
                        mouseWheelZoomEnabled: false,
                        dblClickZoomEnabled: true,
                        preventMouseEventsDefault: false,
                        // Clamp pan so at least `margin` px of content is always
                        // visible on every edge — prevents losing the graph off-screen.
                        beforePan: function(oldPan, newPan) {
                            const sizes  = this.getSizes();
                            const margin = 80; // minimum visible content (px)
                            const cw = sizes.viewBox.width  * sizes.realZoom;
                            const ch = sizes.viewBox.height * sizes.realZoom;
                            return {
                                x: Math.max(margin - cw, Math.min(sizes.width  - margin, newPan.x)),
                                y: Math.max(margin - ch, Math.min(sizes.height - margin, newPan.y))
                            };
                        }
                    });

                    const zoomInBtn = document.getElementById('graphZoomInBtn');
                    const zoomOutBtn = document.getElementById('graphZoomOutBtn');
                    const resetBtn = document.getElementById('graphResetBtn');

                    if (zoomInBtn) zoomInBtn.addEventListener('click', () => panZoomInstance.zoomIn());
                    if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => panZoomInstance.zoomOut());
                    if (resetBtn) resetBtn.addEventListener('click', () => { panZoomInstance.reset(); panZoomInstance.center(); });
                });
            }

            // Hook into the dynamics tab button click
            const dynamicsTabBtn = document.querySelector('[data-target="tab-dynamics"]');
            if (dynamicsTabBtn) {
                dynamicsTabBtn.addEventListener('click', initPanZoom);
            }

            // Also init immediately if the dynamics tab happens to be active on load
            if (document.getElementById('tab-dynamics')?.classList.contains('active')) {
                initPanZoom();
            }
        }
    }
});
