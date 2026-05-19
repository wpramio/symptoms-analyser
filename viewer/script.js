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
    const navCalculator = document.getElementById('navCalculator');
    const fileSelectorContainer = document.getElementById('fileSelectorContainer');
    const calculatorView = document.getElementById('calculatorView');

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
        navAnalysis.classList.add('active');
        navCalculator.classList.remove('active');
        fileSelectorContainer.style.display = 'flex';
        calculatorView.style.display = 'none';

        if (currentData) {
            welcomeMessage.style.display = 'none';
            dashboard.style.display = 'block';
        } else {
            welcomeMessage.style.display = 'block';
            dashboard.style.display = 'none';
        }
    });

    navCalculator.addEventListener('click', () => {
        navCalculator.classList.add('active');
        navAnalysis.classList.remove('active');
        fileSelectorContainer.style.display = 'none';
        welcomeMessage.style.display = 'none';
        dashboard.style.display = 'none';
        calculatorView.style.display = 'block';

        if (pricingData.length === 0) {
            loadPricingData();
        }
    });

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
                
                // Set default selections if possible
                if (pricingData.length > 0) {
                    hybridPrepSelect.selectedIndex = 0; // First item usually flash/cheap
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

    [calcPrepPrompt, calcPrepComp, calcAnaPrompt, calcAnaComp, calcSessions, hybridPrepSelect, hybridAnaSelect].forEach(input => {
        if(input) {
            input.addEventListener('input', updateCalculator);
            input.addEventListener('change', updateCalculator);
        }
    });

    // Fetch list of files
    fetch('/api/files')
        .then(res => res.json())
        .then(files => {
            fileSelect.innerHTML = '<option value="" disabled selected>Selecione uma sessão...</option>';
            files.forEach(file => {
                const opt = document.createElement('option');
                opt.value = file.path;
                opt.textContent = file.name;
                fileSelect.appendChild(opt);
            });
        })
        .catch(err => {
            console.error(err);
            fileSelect.innerHTML = '<option value="" disabled>Erro ao carregar arquivos</option>';
        });

    // Handle file selection
    fileSelect.addEventListener('change', (e) => {
        const path = e.target.value;
        if (!path) return;

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

        welcomeMessage.style.display = 'none';
        dashboard.style.display = 'block';

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

        // Select first patient by default
        selectPatient(patientNames[0], patientTabs.firstElementChild);
    }

    function selectPatient(name, tabElement) {
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
                const card = document.createElement('div');
                card.className = 'top3-card';
                card.innerHTML = `
                    <div class="top3-rank">Prioridade #${index + 1}</div>
                    <div class="top3-title">${dim.name}</div>
                    <div class="score-badge" data-score="${dim.mean}">Média: ${dim.mean.toFixed(1).replace('.', ',')}</div>
                `;
                tplTop3.appendChild(card);
            });
        } else {
            tplTop3.innerHTML = '<p>Nenhuma prioridade encontrada.</p>';
        }

        // Render Dimensions List
        if (patientData.dimensions && Object.keys(patientData.dimensions).length > 0) {
            // Sort dimensions by score descending
            const dims = Object.values(patientData.dimensions).sort((a, b) => b.dimension_mean - a.dimension_mean);

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
                                <span class="score-badge" data-score="${item.score}">Pontuação: ${item.score}</span>
                            </div>
                            <ul class="item-evidence">
                                ${evidenceHtml}
                            </ul>
                        </div>
                    `;
                });

                dimEl.innerHTML = `
                    <div class="dimension-header">
                        <div class="dimension-title-group">
                            <span class="dimension-name">${dim.name}</span>
                        </div>
                        <div class="score-badge" data-score="${dim.dimension_mean}">Média: ${dim.dimension_mean.toFixed(1).replace('.', ',')}</div>
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
