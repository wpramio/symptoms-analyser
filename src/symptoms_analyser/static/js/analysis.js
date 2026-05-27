document.addEventListener('DOMContentLoaded', () => {
    const fileSelect = document.getElementById('fileSelect');
    const welcomeMessage = document.getElementById('welcomeMessage');
    const dashboard = document.getElementById('dashboard');
    const metaSession = document.getElementById('metaSession');
    const metaModel = document.getElementById('metaModel');
    const metaChunks = document.getElementById('metaChunks');
    const metaTime = document.getElementById('metaTime');
    const metaTokens = document.getElementById('metaTokens');

    // Floating popover metadata elements
    const btnShowSessionMeta = document.getElementById('btnShowSessionMeta');
    const metaPopover = document.getElementById('metaPopover');

    const patientTabs = document.getElementById('patientTabs');
    const patientContent = document.getElementById('patientContent');
    const patientTemplate = document.getElementById('patientTemplate');

    let currentData = null;

    // Toggle popover visibility
    if (btnShowSessionMeta && metaPopover) {
        btnShowSessionMeta.addEventListener('click', (e) => {
            e.stopPropagation();
            const isShown = metaPopover.classList.toggle('show');
            btnShowSessionMeta.classList.toggle('active', isShown);
        });

        // Close popover when clicking anywhere else
        document.addEventListener('click', (e) => {
            if (!metaPopover.contains(e.target) && e.target !== btnShowSessionMeta) {
                metaPopover.classList.remove('show');
                btnShowSessionMeta.classList.remove('active');
            }
        });
    }

    // Fetch list of evaluations
    fetch('/api/evaluations')
        .then(res => res.json())
        .then(files => {
            fileSelect.innerHTML = '<option value="" disabled selected>Selecione uma sessão...</option>';
            files.forEach(file => {
                const opt = document.createElement('option');
                opt.value = file.path;
                opt.textContent = file.name;
                fileSelect.appendChild(opt);
            });

            // Restore saved file
            const savedFile = localStorage.getItem('viewer_selected_file');
            if (savedFile && files.some(f => f.path === savedFile)) {
                fileSelect.value = savedFile;
                fileSelect.dispatchEvent(new Event('change'));
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

        welcomeMessage.style.display = 'none';
        dashboard.style.display = 'block';

        // Render Meta
        metaSession.textContent = currentData.session || '-';
        metaModel.textContent = currentData.model || '-';
        metaChunks.textContent = currentData.chunks_analyzed || '-';
        const formattedTime = currentData.total_elapsed_seconds ? currentData.total_elapsed_seconds + 's' : '-';
        metaTime.textContent = formattedTime;

        if (currentData.token_usage) {
            metaTokens.textContent = `${currentData.token_usage.prompt_tokens} / ${currentData.token_usage.completion_tokens}`;
        } else {
            metaTokens.textContent = '-';
        }

        // Show meta info button when data is loaded
        if (btnShowSessionMeta) {
            btnShowSessionMeta.style.display = 'inline-flex';
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
