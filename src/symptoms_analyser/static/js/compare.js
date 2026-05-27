document.addEventListener('DOMContentLoaded', () => {
    const compareSelect1 = document.getElementById('compareSelect1');
    const compareSelect2 = document.getElementById('compareSelect2');
    const compareDashboard = document.getElementById('compareDashboard');
    const compareMetaCard1 = document.getElementById('compareMetaCard1');
    const compareMetaCard2 = document.getElementById('compareMetaCard2');
    const compareMetaPlaceholder1 = document.getElementById('compareMetaPlaceholder1');
    const compareMetaPlaceholder2 = document.getElementById('compareMetaPlaceholder2');
    const compareMetaSession1 = document.getElementById('compareMetaSession1');
    const compareMetaModel1 = document.getElementById('compareMetaModel1');
    const compareMetaChunks1 = document.getElementById('compareMetaChunks1');
    const compareMetaTime1 = document.getElementById('compareMetaTime1');
    const compareMetaTokens1 = document.getElementById('compareMetaTokens1');
    const compareMetaSession2 = document.getElementById('compareMetaSession2');
    const compareMetaModel2 = document.getElementById('compareMetaModel2');
    const compareMetaChunks2 = document.getElementById('compareMetaChunks2');
    const compareMetaTime2 = document.getElementById('compareMetaTime2');
    const compareMetaTokens2 = document.getElementById('compareMetaTokens2');
    const btnToggleAll = document.getElementById('btnToggleAll');
    const compareActions = document.getElementById('compareActions');
    const comparePatientsContent = document.getElementById('comparePatientsContent');

    let compareData1 = null;
    let compareData2 = null;
    let allExpanded = false;

    // Fetch list of evaluations
    fetch('/api/evaluations')
        .then(res => res.json())
        .then(files => {
            compareSelect1.innerHTML = '<option value="" disabled selected>Selecione a análise A...</option>';
            compareSelect2.innerHTML = '<option value="" disabled selected>Selecione a análise B...</option>';

            files.forEach(file => {
                const optA = document.createElement('option');
                optA.value = file.path;
                optA.textContent = file.name;
                compareSelect1.appendChild(optA);

                const optB = document.createElement('option');
                optB.value = file.path;
                optB.textContent = file.name;
                compareSelect2.appendChild(optB);
            });

            // Restore saved selections
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
        .catch(err => console.error("Error loading files for compare:", err));

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
            if (data && data.aggregated?.patients && data.aggregated.patients[name]) {
                return data.aggregated.patients[name];
            }
            return null;
        };

        comparePatientsContent.innerHTML = '';

        patientNames.forEach(pName => {
            const p1 = getPatient(data1, pName);
            const p2 = getPatient(data2, pName);

            // Combined list of dimensions
            let allDimNames = new Set();
            if (p1 && p1.dimensions) Object.values(p1.dimensions).forEach(d => allDimNames.add(d.name));
            if (p2 && p2.dimensions) Object.values(p2.dimensions).forEach(d => allDimNames.add(d.name));

            // Map dimensions to keys and sort by dimension key/ID
            const dimMapping = p1?.dimensions || p2?.dimensions || {};
            const getDimKey = (name) => Object.keys(dimMapping).find(k => dimMapping[k].name === name) || "99";
            const sortedDims = Array.from(allDimNames).sort((a, b) => {
                const ka = parseInt(getDimKey(a));
                const kb = parseInt(getDimKey(b));
                return ka - kb;
            });

            const patientCard = document.createElement('div');
            patientCard.className = 'compare-section-card patient-compare-card';

            let dimsHtml = '';
            sortedDims.forEach(dName => {
                const dKey = getDimKey(dName);
                const d1 = p1?.dimensions ? Object.values(p1.dimensions).find(d => d.name === dName) : null;
                const d2 = p2?.dimensions ? Object.values(p2.dimensions).find(d => d.name === dName) : null;

                const score1 = d1 ? d1.dimension_sum : 0;
                const score2 = d2 ? d2.dimension_sum : 0;

                if (score1 === 0 && score2 === 0) return; // Only show dimensions with symptoms

                const maxSize = (dKey === "16" ? 3 : 2) * 4;
                const sev1 = d1 ? (Math.ceil((score1 / maxSize) * 4) || 1) : 0;
                const sev2 = d2 ? (Math.ceil((score2 / maxSize) * 4) || 1) : 0;

                // Evidences
                const items1 = p1?.items ? Object.entries(p1.items).filter(([itemId]) => itemId.startsWith(dKey + '.')) : [];
                const items2 = p2?.items ? Object.entries(p2.items).filter(([itemId]) => itemId.startsWith(dKey + '.')) : [];

                const makeEvidenceHtml = (items) => {
                    if (items.length === 0) return '<p class="no-evidence">Nenhuma evidência clínica.</p>';
                    return items.map(([itemId, item]) => `
                        <div class="compare-item-evidence-block">
                            <strong>${itemId} - ${item.name} <span class="score-badge" data-severity="${item.score}">${item.score}</span></strong>
                            <ul>
                                ${item.evidence.map(ev => `<li>"${ev}"</li>`).join('')}
                            </ul>
                        </div>
                    `).join('');
                };

                const changeClass = score1 === score2 ? 'stable' : (score1 < score2 ? 'increased' : 'decreased');
                const changeSymbol = score1 === score2 ? '●' : (score1 < score2 ? '▲' : '▼');
                const changeLabel = score1 === score2 ? 'Sem alteração' : (score1 < score2 ? 'Sintomas aumentaram' : 'Sintomas diminuíram');

                dimsHtml += `
                    <div class="dimension-item ${allExpanded ? 'open' : ''}">
                        <div class="dimension-header compare-header">
                            <span class="dimension-name">${dKey}. ${dName}</span>
                            <div class="compare-badge-pair">
                                <span class="score-badge" data-severity="${sev1}">${d1 ? `${score1}/${maxSize}` : '-'}</span>
                                <span class="compare-trend-indicator ${changeClass}" title="${changeLabel}">${changeSymbol}</span>
                                <span class="score-badge" data-severity="${sev2}">${d2 ? `${score2}/${maxSize}` : '-'}</span>
                            </div>
                        </div>
                        <div class="dimension-body">
                            <div class="compare-grid">
                                <div>
                                    <h5 class="column-title">Evidências (Sessão A)</h5>
                                    ${makeEvidenceHtml(items1)}
                                </div>
                                <div>
                                    <h5 class="column-title">Evidências (Sessão B)</h5>
                                    ${makeEvidenceHtml(items2)}
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            });

            patientCard.innerHTML = `
                <h3 class="patient-compare-title">Paciente: ${pName}</h3>
                <div class="compare-dimensions-list">
                    ${dimsHtml || '<p class="no-symptoms-found">Nenhum sintoma detectado em nenhuma das sessões.</p>'}
                </div>
            `;
            comparePatientsContent.appendChild(patientCard);
        });

        // Populate Metas
        if (data1) {
            compareMetaPlaceholder1.style.display = 'none';
            compareMetaCard1.style.display = 'block';
            compareMetaSession1.textContent = data1.session || '-';
            compareMetaModel1.textContent = data1.model || '-';
            compareMetaChunks1.textContent = data1.chunks_analyzed || '-';
            compareMetaTime1.textContent = data1.total_elapsed_seconds ? data1.total_elapsed_seconds + 's' : '-';
            compareMetaTokens1.textContent = data1.token_usage ? `${data1.token_usage.prompt_tokens} / ${data1.token_usage.completion_tokens}` : '-';
        } else {
            compareMetaPlaceholder1.style.display = 'block';
            compareMetaCard1.style.display = 'none';
        }

        if (data2) {
            compareMetaPlaceholder2.style.display = 'none';
            compareMetaCard2.style.display = 'block';
            compareMetaSession2.textContent = data2.session || '-';
            compareMetaModel2.textContent = data2.model || '-';
            compareMetaChunks2.textContent = data2.chunks_analyzed || '-';
            compareMetaTime2.textContent = data2.total_elapsed_seconds ? data2.total_elapsed_seconds + 's' : '-';
            compareMetaTokens2.textContent = data2.token_usage ? `${data2.token_usage.prompt_tokens} / ${data2.token_usage.completion_tokens}` : '-';
        } else {
            compareMetaPlaceholder2.style.display = 'block';
            compareMetaCard2.style.display = 'none';
        }

        if (data1 && data2 && patientNames.length > 0) {
            compareActions.style.display = 'block';
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
});
