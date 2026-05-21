document.addEventListener('DOMContentLoaded', () => {
    const fileSelect = document.getElementById('fileSelect');
    const dashboard = document.getElementById('dashboard');
    const welcomeMessage = document.getElementById('welcomeMessage');

    // Meta elements
    const metaSession = document.getElementById('metaSession');
    const metaModel = document.getElementById('metaModel');
    const metaChunks = document.getElementById('metaChunks');
    const metaTime = document.getElementById('metaTime');
    const metaTokens = document.getElementById('metaTokens');

    const patientTabs = document.getElementById('patientTabs');
    const patientContent = document.getElementById('patientContent');
    const patientTemplate = document.getElementById('patientTemplate');

    // Navigation and Calculator elements
    const navAnalysis = document.getElementById('navAnalysis');
    const navCompare = document.getElementById('navCompare');
    const navCalculator = document.getElementById('navCalculator');
    const fileSelectorContainer = document.getElementById('fileSelectorContainer');
    const calculatorView = document.getElementById('calculatorView');
    const compareView = document.getElementById('compareView');
    const compareSelect1 = document.getElementById('compareSelect1');
    const compareSelect2 = document.getElementById('compareSelect2');
    const compareDashboard = document.getElementById('compareDashboard');
    const comparePatientsContent = document.getElementById('comparePatientsContent');
    const compareActions = document.getElementById('compareActions');
    const btnToggleAll = document.getElementById('btnToggleAll');

    // Meta elements - A
    const compareMetaCard1 = document.getElementById('compareMetaCard1');
    const compareMetaPlaceholder1 = document.getElementById('compareMetaPlaceholder1');
    const compareMetaSession1 = document.getElementById('compareMetaSession1');
    const compareMetaModel1 = document.getElementById('compareMetaModel1');
    const compareMetaChunks1 = document.getElementById('compareMetaChunks1');
    const compareMetaTime1 = document.getElementById('compareMetaTime1');
    const compareMetaTokens1 = document.getElementById('compareMetaTokens1');

    // Meta elements - B
    const compareMetaCard2 = document.getElementById('compareMetaCard2');
    const compareMetaPlaceholder2 = document.getElementById('compareMetaPlaceholder2');
    const compareMetaSession2 = document.getElementById('compareMetaSession2');
    const compareMetaModel2 = document.getElementById('compareMetaModel2');
    const compareMetaChunks2 = document.getElementById('compareMetaChunks2');
    const compareMetaTime2 = document.getElementById('compareMetaTime2');
    const compareMetaTokens2 = document.getElementById('compareMetaTokens2');

    let compareData1 = null;
    let compareData2 = null;
    let allExpanded = false;

    const calcPrepPrompt = document.getElementById('calcPrepPrompt');
    const calcPrepComp = document.getElementById('calcPrepComp');
    const calcAnaPrompt = document.getElementById('calcAnaPrompt');
    const calcAnaComp = document.getElementById('calcAnaComp');
    const calcSessions = document.getElementById('calcSessions');
    const costTableBody = document.querySelector('#costTable tbody');

    const hybridPrepSelect = document.getElementById('hybridPrepSelect');
    const hybridAnaSelect = document.getElementById('hybridAnaSelect');
    const hybridSessionCost = document.getElementById('hybridSessionCost');
    const hybridTotalCost = document.getElementById('hybridTotalCost');

    let currentData = null;
    let pricingData = [];

    // Setup navigation toggles
    navAnalysis.addEventListener('click', () => {
        localStorage.setItem('viewer_active_tab', 'analysis');
        document.body.dataset.activeTab = 'analysis';
        navAnalysis.classList.add('active');
        navCalculator.classList.remove('active');
        navCompare.classList.remove('active');
        fileSelectorContainer.style.display = 'flex';
        calculatorView.style.display = 'none';
        compareView.style.display = 'none';

        if (currentData) {
            welcomeMessage.style.display = 'none';
            dashboard.style.display = 'block';
        } else {
            welcomeMessage.style.display = 'block';
            dashboard.style.display = 'none';
        }
    });

    navCalculator.addEventListener('click', () => {
        localStorage.setItem('viewer_active_tab', 'calculator');
        document.body.dataset.activeTab = 'calculator';
        navCalculator.classList.add('active');
        navAnalysis.classList.remove('active');
        navCompare.classList.remove('active');
        fileSelectorContainer.style.display = 'none';
        welcomeMessage.style.display = 'none';
        dashboard.style.display = 'none';
        calculatorView.style.display = 'block';
        compareView.style.display = 'none';

        if (pricingData.length === 0) {
            loadPricingData();
        }
    });

    navCompare.addEventListener('click', () => {
        localStorage.setItem('viewer_active_tab', 'compare');
        document.body.dataset.activeTab = 'compare';
        navCompare.classList.add('active');
        navAnalysis.classList.remove('active');
        navCalculator.classList.remove('active');
        fileSelectorContainer.style.display = 'none';
        welcomeMessage.style.display = 'none';
        dashboard.style.display = 'none';
        calculatorView.style.display = 'none';
        compareView.style.display = 'flex';
    });

    // Restore saved tab
    const savedActiveTab = localStorage.getItem('viewer_active_tab');
    if (savedActiveTab === 'compare') {
        navCompare.click();
    } else if (savedActiveTab === 'calculator') {
        navCalculator.click();
    } else {
        navAnalysis.click();
    }

    function handleCompareChange() {
        const path1 = compareSelect1.value;
        const path2 = compareSelect2.value;

        if (path1) localStorage.setItem('viewer_compare_select_1', path1);
        if (path2) localStorage.setItem('viewer_compare_select_2', path2);

        if (!path1 && !path2) return;

        compareDashboard.style.display = 'flex';

        // Reset toggle all state
        allExpanded = false;
        btnToggleAll.textContent = 'Expandir tudo';

        let promise1 = path1 && path1 !== compareData1?.path ? fetch(path1).then(res => res.json()) : Promise.resolve(compareData1);
        let promise2 = path2 && path2 !== compareData2?.path ? fetch(path2).then(res => res.json()) : Promise.resolve(compareData2);

        Promise.all([promise1, promise2]).then(([data1, data2]) => {
            if (data1 && data1 !== compareData1) {
                data1.path = path1;
                compareData1 = data1;
            }
            if (data2 && data2 !== compareData2) {
                data2.path = path2;
                compareData2 = data2;
            }
            renderCompareGrid(compareData1, compareData2);
        });
    }

    compareSelect1.addEventListener('change', handleCompareChange);
    compareSelect2.addEventListener('change', handleCompareChange);

    btnToggleAll.addEventListener('click', () => {
        allExpanded = !allExpanded;
        const items = comparePatientsContent.querySelectorAll('.dimension-item');
        items.forEach(item => {
            if (allExpanded) {
                item.classList.add('open');
            } else {
                item.classList.remove('open');
            }
        });
        btnToggleAll.textContent = allExpanded ? 'Colapsar tudo' : 'Expandir tudo';
    });

    function renderCompareGrid(data1, data2) {
        if (!compareDashboard) return;

        let allPatientNames = new Set();
        if (data1 && data1.aggregated?.patients) {
            Object.keys(data1.aggregated.patients).forEach(k => allPatientNames.add(k));
        }
        if (data2 && data2.aggregated?.patients) {
            Object.keys(data2.aggregated.patients).forEach(k => allPatientNames.add(k));
        }
        const patientNames = Array.from(allPatientNames).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));

        const getPatient = (data, name) => {
            if (!data) return null;
            const patients = data.aggregated?.patients || {};
            return patients[name] ? { name: name, data: patients[name] } : null;
        };

        const updateMetaCard = (data, cardEl, placeholderEl, sessionEl, modelEl, chunksEl, timeEl, tokensEl) => {
            if (!data) {
                cardEl.style.display = 'none';
                placeholderEl.style.display = 'block';
                return;
            }
            cardEl.style.display = 'block';
            placeholderEl.style.display = 'none';

            sessionEl.textContent = data.session || '-';
            modelEl.textContent = data.model || '-';
            chunksEl.textContent = data.chunks_analyzed || '-';
            timeEl.textContent = data.total_elapsed_seconds ? data.total_elapsed_seconds + 's' : '-';
            tokensEl.textContent = data.token_usage ? `${data.token_usage.prompt_tokens} / ${data.token_usage.completion_tokens}` : '-';
        };

        updateMetaCard(data1, compareMetaCard1, compareMetaPlaceholder1, compareMetaSession1, compareMetaModel1, compareMetaChunks1, compareMetaTime1, compareMetaTokens1);
        updateMetaCard(data2, compareMetaCard2, compareMetaPlaceholder2, compareMetaSession2, compareMetaModel2, compareMetaChunks2, compareMetaTime2, compareMetaTokens2);

        const renderHeader = (p, label) => {
            return `
                <div class="section-header" style="margin-top: 0; margin-bottom: 0.5rem;">
                    <h3 style="font-size: 1.05rem; ${!p ? 'color: var(--text-muted);' : ''}">${label} ${!p ? '(Ausente)' : ''}</h3>
                </div>
            `;
        };

        const renderTop3 = (p) => {
            if (!p) return `<div></div>`;
            let html = `<div class="top3-grid" style="grid-template-columns: 1fr; gap: 0.75rem; align-self: start; width: 100%;">`;
            if (p.data.top3 && p.data.top3.length > 0) {
                p.data.top3.forEach((dim, index) => {
                    const maxSize = (dim.dim === "16" ? 3 : 2) * 4;
                    const severity = Math.ceil((dim.sum / maxSize) * 4) || 1;
                    html += `
                        <div class="top3-card" style="padding: 1rem;">
                            <div class="top3-title" style="font-size: 1rem; margin-bottom: 0.5rem;">#${index + 1} ${dim.name}</div>
                            <div class="score-badge" data-severity="${severity}">Pontuação: ${dim.sum}/${maxSize}</div>
                        </div>
                    `;
                });
            } else {
                html += `<p>Nenhuma prioridade.</p>`;
            }
            html += `</div>`;
            return html;
        };

        const renderDimensions = (p) => {
            if (!p) return `<div></div>`;
            let html = `<div class="dimensions-list" style="margin-top: 1.5rem; margin-bottom: 1rem; gap: 0.5rem; align-self: start; width: 100%;">`;
            if (p.data.dimensions) {
                const dims = Object.values(p.data.dimensions).sort((a, b) => b.dimension_sum - a.dimension_sum);
                dims.forEach(dim => {
                    const dimKey = Object.keys(p.data.dimensions).find(k => p.data.dimensions[k].name === dim.name);
                    const relevantItems = Object.entries(p.data.items || {}).filter(([itemId]) => itemId.startsWith(dimKey + '.'));

                    let itemsHtml = '';
                    relevantItems.forEach(([itemId, item]) => {
                        const evidenceHtml = item.evidence.map(ev => `<li class="evidence-quote">"${ev}"</li>`).join('');
                        itemsHtml += `
                            <div class="item-row">
                                <div class="item-header">
                                    <span class="item-name">${itemId} - ${item.name}</span>
                                    <span class="score-badge" data-severity="${item.score}">Pontuação: ${item.score}</span>
                                </div>
                                <ul class="item-evidence">
                                    ${evidenceHtml}
                                </ul>
                            </div>
                        `;
                    });

                    const maxSize = (dimKey === "16" ? 3 : 2) * 4;
                    const severity = Math.ceil((dim.dimension_sum / maxSize) * 4) || 1;

                    html += `
                        <div class="dimension-item ${allExpanded ? 'open' : ''}">
                            <div class="dimension-header" style="padding: 0.75rem 1rem;">
                                <span class="dimension-name" style="font-size: 0.9rem;">${dim.name}</span>
                                <div class="score-badge" data-severity="${severity}">${dim.dimension_sum}/${maxSize}</div>
                            </div>
                            <div class="dimension-body">
                                ${itemsHtml}
                            </div>
                        </div>
                    `;
                });
            }
            html += `</div>`;
            return html;
        };

        let html = '';

        patientNames.forEach((name) => {
            const p1 = getPatient(data1, name);
            const p2 = getPatient(data2, name);

            html += `
                <div class="compare-section-card">
                    <h2 style="font-size: 1.35rem; color: var(--text-main); margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem;">${name}</h2>
                    <div class="compare-grid">
                        ${renderHeader(p1, data1?.session || "Análise A")}
                        ${renderHeader(p2, data2?.session || "Análise B")}
                        ${renderTop3(p1)}
                        ${renderTop3(p2)}
                        ${renderDimensions(p1)}
                        ${renderDimensions(p2)}
                    </div>
                </div>
            `;
        });

        if (patientNames.length === 0) {
            html += `<div class="compare-section-card" style="text-align: center; color: var(--text-muted);">Nenhum paciente encontrado nas análises.</div>`;
        }

        comparePatientsContent.innerHTML = html;

        // Toggle Actions show/hide
        if (patientNames.length > 0) {
            compareActions.style.display = 'flex';
        } else {
            compareActions.style.display = 'none';
        }

        // Attach click listeners to all dimension headers in the compare view
        comparePatientsContent.querySelectorAll('.dimension-header').forEach(header => {
            header.addEventListener('click', () => {
                const item = header.closest('.dimension-item');
                if (item) {
                    item.classList.toggle('open');
                }
            });
        });
    }

    // Calculator Logic
    function loadPricingData() {
        fetch('/viewer/prices.csv')
            .then(res => res.text())
            .then(csv => {
                const lines = csv.trim().split('\n');
                pricingData = lines.slice(1).map(line => {
                    const parts = line.split(',');
                    return {
                        provider: parts[0],
                        model: parts[1],
                        inputPrice: parseFloat(parts[2]),
                        outputPrice: parseFloat(parts[3])
                    };
                });

                // Populate selects
                hybridPrepSelect.innerHTML = '';
                hybridAnaSelect.innerHTML = '';
                pricingData.forEach((item, index) => {
                    const opt1 = document.createElement('option');
                    opt1.value = index;
                    opt1.textContent = `${item.provider} - ${item.model}`;
                    hybridPrepSelect.appendChild(opt1);

                    const opt2 = document.createElement('option');
                    opt2.value = index;
                    opt2.textContent = `${item.provider} - ${item.model}`;
                    hybridAnaSelect.appendChild(opt2);
                });

                // Set selections (restore or default)
                const savedHybridPrep = localStorage.getItem('viewer_hybrid_prep_select');
                const savedHybridAna = localStorage.getItem('viewer_hybrid_ana_select');

                if (savedHybridPrep !== null && parseInt(savedHybridPrep) < pricingData.length) {
                    hybridPrepSelect.value = savedHybridPrep;
                } else if (pricingData.length > 0) {
                    hybridPrepSelect.selectedIndex = 0; // First item usually flash/cheap
                }

                if (savedHybridAna !== null && parseInt(savedHybridAna) < pricingData.length) {
                    hybridAnaSelect.value = savedHybridAna;
                } else if (pricingData.length > 0) {
                    hybridAnaSelect.selectedIndex = Math.min(1, pricingData.length - 1); // Second item usually pro
                }

                updateCalculator();
            })
            .catch(err => console.error("Error loading CSV", err));
    }

    function updateCalculator() {
        if (pricingData.length === 0) return;

        const pPrompt = parseInt(calcPrepPrompt.value) || 0;
        const pComp = parseInt(calcPrepComp.value) || 0;
        const aPrompt = parseInt(calcAnaPrompt.value) || 0;
        const aComp = parseInt(calcAnaComp.value) || 0;
        const sessions = parseInt(calcSessions.value) || 0;

        // Save values to localStorage
        localStorage.setItem('viewer_calc_prep_prompt', calcPrepPrompt.value);
        localStorage.setItem('viewer_calc_prep_comp', calcPrepComp.value);
        localStorage.setItem('viewer_calc_ana_prompt', calcAnaPrompt.value);
        localStorage.setItem('viewer_calc_ana_comp', calcAnaComp.value);
        localStorage.setItem('viewer_calc_sessions', calcSessions.value);
        localStorage.setItem('viewer_hybrid_prep_select', hybridPrepSelect.value);
        localStorage.setItem('viewer_hybrid_ana_select', hybridAnaSelect.value);

        const totalInputTokens = pPrompt + aPrompt;
        const totalOutputTokens = pComp + aComp;

        costTableBody.innerHTML = '';

        pricingData.forEach(item => {
            const inputCost = (totalInputTokens / 1000000) * item.inputPrice;
            const outputCost = (totalOutputTokens / 1000000) * item.outputPrice;
            const sessionCost = inputCost + outputCost;
            const totalCost = sessionCost * sessions;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="provider-cell">${item.provider}</td>
                <td>${item.model}</td>
                <td>$${item.inputPrice.toFixed(3).replace('.', ',')}</td>
                <td>$${item.outputPrice.toFixed(3).replace('.', ',')}</td>
                <td class="total-cell">$${sessionCost.toFixed(3).replace('.', ',')}</td>
                <td class="total-cell">$${totalCost.toFixed(2).replace('.', ',')}</td>
            `;
            costTableBody.appendChild(tr);
        });

        // Calculate Hybrid
        const prepIndex = parseInt(hybridPrepSelect.value);
        const anaIndex = parseInt(hybridAnaSelect.value);

        if (!isNaN(prepIndex) && !isNaN(anaIndex) && pricingData[prepIndex] && pricingData[anaIndex]) {
            const prepModel = pricingData[prepIndex];
            const anaModel = pricingData[anaIndex];

            const prepCost = (pPrompt / 1000000) * prepModel.inputPrice + (pComp / 1000000) * prepModel.outputPrice;
            const anaCost = (aPrompt / 1000000) * anaModel.inputPrice + (aComp / 1000000) * anaModel.outputPrice;

            const hSessionCost = prepCost + anaCost;
            const hTotalCost = hSessionCost * sessions;

            hybridSessionCost.textContent = '$' + hSessionCost.toFixed(3).replace('.', ',');
            hybridTotalCost.textContent = '$' + hTotalCost.toFixed(2).replace('.', ',');
        }
    }

    // Restore calculator values
    const savedPrepPrompt = localStorage.getItem('viewer_calc_prep_prompt');
    const savedPrepComp = localStorage.getItem('viewer_calc_prep_comp');
    const savedAnaPrompt = localStorage.getItem('viewer_calc_ana_prompt');
    const savedAnaComp = localStorage.getItem('viewer_calc_ana_comp');
    const savedSessions = localStorage.getItem('viewer_calc_sessions');

    if (savedPrepPrompt !== null) calcPrepPrompt.value = savedPrepPrompt;
    if (savedPrepComp !== null) calcPrepComp.value = savedPrepComp;
    if (savedAnaPrompt !== null) calcAnaPrompt.value = savedAnaPrompt;
    if (savedAnaComp !== null) calcAnaComp.value = savedAnaComp;
    if (savedSessions !== null) calcSessions.value = savedSessions;

    [calcPrepPrompt, calcPrepComp, calcAnaPrompt, calcAnaComp, calcSessions, hybridPrepSelect, hybridAnaSelect].forEach(input => {
        if (input) {
            input.addEventListener('input', updateCalculator);
            input.addEventListener('change', updateCalculator);
        }
    });

    // Fetch list of files
    fetch('/api/files')
        .then(res => res.json())
        .then(files => {
            fileSelect.innerHTML = '<option value="" disabled selected>Selecione uma sessão...</option>';
            compareSelect1.innerHTML = '<option value="" disabled selected>Selecione a análise A...</option>';
            compareSelect2.innerHTML = '<option value="" disabled selected>Selecione a análise B...</option>';

            files.forEach(file => {
                const opt = document.createElement('option');
                opt.value = file.path;
                opt.textContent = file.name;
                fileSelect.appendChild(opt);

                const optA = document.createElement('option');
                optA.value = file.path;
                optA.textContent = file.name;
                compareSelect1.appendChild(optA);

                const optB = document.createElement('option');
                optB.value = file.path;
                optB.textContent = file.name;
                compareSelect2.appendChild(optB);
            });

            // Restore saved files
            const savedFile = localStorage.getItem('viewer_selected_file');
            if (savedFile && files.some(f => f.path === savedFile)) {
                fileSelect.value = savedFile;
                fileSelect.dispatchEvent(new Event('change'));
            }

            const savedCompare1 = localStorage.getItem('viewer_compare_select_1');
            const savedCompare2 = localStorage.getItem('viewer_compare_select_2');
            let compareChanged = false;
            if (savedCompare1 && files.some(f => f.path === savedCompare1)) {
                compareSelect1.value = savedCompare1;
                compareChanged = true;
            }
            if (savedCompare2 && files.some(f => f.path === savedCompare2)) {
                compareSelect2.value = savedCompare2;
                compareChanged = true;
            }
            if (compareChanged) {
                handleCompareChange();
            }
        })
        .catch(err => {
            console.error(err);
            fileSelect.innerHTML = '<option value="" disabled>Erro ao carregar arquivos</option>';
        });

    // Handle file selection
    fileSelect.addEventListener('change', (e) => {
        const path = e.target.value;
        if (!path) return;

        localStorage.setItem('viewer_selected_file', path);

        fetch(path)
            .then(res => res.json())
            .then(data => {
                currentData = data;
                renderDashboard();
            })
            .catch(err => {
                console.error("Failed to load JSON:", err);
                alert("Falha ao carregar o arquivo selecionado.");
            });
    });

    function renderDashboard() {
        if (!currentData) return;

        const activeTab = document.body.dataset.activeTab;
        if (activeTab === 'analysis') {
            welcomeMessage.style.display = 'none';
            dashboard.style.display = 'block';
        } else {
            welcomeMessage.style.display = 'none';
            dashboard.style.display = 'none';
        }

        // Render Meta
        metaSession.textContent = currentData.session || '-';
        metaModel.textContent = currentData.model || '-';
        metaChunks.textContent = currentData.chunks_analyzed || '-';
        metaTime.textContent = currentData.total_elapsed_seconds ? currentData.total_elapsed_seconds + 's' : '-';

        if (currentData.token_usage) {
            metaTokens.textContent = `${currentData.token_usage.prompt_tokens} / ${currentData.token_usage.completion_tokens}`;
        } else {
            metaTokens.textContent = '-';
        }

        // Render Patient Tabs
        patientTabs.innerHTML = '';
        const patients = currentData.aggregated?.patients || {};
        const patientNames = Object.keys(patients).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));

        if (patientNames.length === 0) {
            patientContent.innerHTML = '<p>Nenhum dado de paciente encontrado.</p>';
            return;
        }

        patientNames.forEach((name, index) => {
            const li = document.createElement('li');
            li.className = `patient-tab ${index === 0 ? 'active' : ''}`;
            li.textContent = name;
            li.dataset.patient = name;
            li.addEventListener('click', () => selectPatient(name, li));
            patientTabs.appendChild(li);
        });

        // Restore selected patient tab or select the first one by default
        const savedPatient = localStorage.getItem('viewer_selected_patient');
        const defaultIndex = (savedPatient && patientNames.includes(savedPatient))
            ? patientNames.indexOf(savedPatient)
            : 0;
        selectPatient(patientNames[defaultIndex], patientTabs.children[defaultIndex]);
    }

    function selectPatient(name, tabElement) {
        if (!tabElement) return;
        localStorage.setItem('viewer_selected_patient', name);

        // Update active tab UI
        document.querySelectorAll('.patient-tab').forEach(tab => tab.classList.remove('active'));
        tabElement.classList.add('active');

        const patientData = currentData.aggregated.patients[name];

        // Clone template
        patientContent.innerHTML = '';
        const clone = patientTemplate.content.cloneNode(true);
        const tplTop3 = clone.querySelector('#tplTop3');
        const tplDimensions = clone.querySelector('#tplDimensions');

        // Render Top 3
        if (patientData.top3 && patientData.top3.length > 0) {
            patientData.top3.forEach((dim, index) => {
                const maxSize = (dim.dim === "16" ? 3 : 2) * 4;
                const severity = Math.ceil((dim.sum / maxSize) * 4) || 1;
                const card = document.createElement('div');
                card.className = 'top3-card';
                card.innerHTML = `
                    <div class="top3-rank">Prioridade #${index + 1}</div>
                    <div class="top3-title">${dim.name}</div>
                    <div class="score-badge" data-severity="${severity}">Pontuação: ${dim.sum}/${maxSize}</div>
                `;
                tplTop3.appendChild(card);
            });
        } else {
            tplTop3.innerHTML = '<p>Nenhuma prioridade encontrada.</p>';
        }

        // Render Dimensions List
        if (patientData.dimensions && Object.keys(patientData.dimensions).length > 0) {
            // Sort dimensions by score descending
            const dims = Object.values(patientData.dimensions).sort((a, b) => b.dimension_sum - a.dimension_sum);

            dims.forEach(dim => {
                const dimEl = document.createElement('div');
                dimEl.className = 'dimension-item';

                // Better approach: filter items where item ID starts with dimension ID
                // Since dimension key is not always present in the object directly, we map it
                const dimKey = Object.keys(patientData.dimensions).find(k => patientData.dimensions[k].name === dim.name);
                const relevantItems = Object.entries(patientData.items).filter(([itemId]) => itemId.startsWith(dimKey + '.'));


                let itemsHtml = '';
                relevantItems.forEach(([itemId, item]) => {
                    const evidenceHtml = item.evidence.map(ev => `<li class="evidence-quote">"${ev}"</li>`).join('');
                    itemsHtml += `
                        <div class="item-row">
                            <div class="item-header">
                                <span class="item-name">${itemId} - ${item.name}</span>
                                <span class="score-badge" data-severity="${item.score}">Pontuação: ${item.score}</span>
                            </div>
                            <ul class="item-evidence">
                                ${evidenceHtml}
                            </ul>
                        </div>
                    `;
                });

                const maxSize = (dimKey === "16" ? 3 : 2) * 4;
                const severity = Math.ceil((dim.dimension_sum / maxSize) * 4) || 1;
                dimEl.innerHTML = `
                    <div class="dimension-header">
                        <div class="dimension-title-group">
                            <span class="dimension-name">${dim.name}</span>
                        </div>
                        <div class="score-badge" data-severity="${severity}">Pontuação: ${dim.dimension_sum}/${maxSize}</div>
                    </div>
                    <div class="dimension-body">
                        ${itemsHtml}
                    </div>
                `;

                // Toggle accordion
                const header = dimEl.querySelector('.dimension-header');
                header.addEventListener('click', () => {
                    dimEl.classList.toggle('open');
                });

                tplDimensions.appendChild(dimEl);
            });
        } else {
            tplDimensions.innerHTML = '<p>Nenhuma dimensão com pontuação > 0.</p>';
        }

        patientContent.appendChild(clone);
    }
});
