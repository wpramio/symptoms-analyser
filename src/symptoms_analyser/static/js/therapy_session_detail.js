document.addEventListener('DOMContentLoaded', () => {
    const _page = JSON.parse(document.getElementById('page-data').textContent);
    const sessionId = _page.sessionId;
    const evaluationId = _page.evaluationId;
    const evaluationPath = _page.evaluationPath;
    const initialTranscriptStatus = _page.transcriptStatus;

    // =========================================================================
    // STATE 1: CLINICAL DASHBOARD LOGIC (When analyzed)
    // =========================================================================
    if (evaluationId && evaluationPath) {
        const btnShowSessionMeta = document.getElementById('btnShowSessionMeta');
        const metaPopover = document.getElementById('metaPopover');
        const metaModel = document.getElementById('metaModel');
        const metaChunks = document.getElementById('metaChunks');
        const metaTime = document.getElementById('metaTime');
        const metaTokens = document.getElementById('metaTokens');

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

            document.addEventListener('click', (e) => {
                if (!metaPopover.contains(e.target) && e.target !== btnShowSessionMeta) {
                    metaPopover.classList.remove('show');
                    btnShowSessionMeta.classList.remove('active');
                }
            });
        }

        // Fetch evaluation payload
        fetch(evaluationPath)
            .then(res => res.json())
            .then(data => {
                currentData = data;
                renderDashboard();
            })
            .catch(err => {
                console.error("Failed to load JSON payload:", err);
                alert("Falha ao carregar os dados detalhados da análise.");
            });

        function renderDashboard() {
            if (!currentData) return;

            // Render Tech Meta inside popover
            if (metaModel) metaModel.textContent = currentData.model || '-';
            if (metaChunks) metaChunks.textContent = currentData.chunks_analyzed || '-';
            const formattedTime = currentData.total_elapsed_seconds ? currentData.total_elapsed_seconds + 's' : '-';
            if (metaTime) metaTime.textContent = formattedTime;

            if (currentData.token_usage && metaTokens) {
                metaTokens.textContent = `${currentData.token_usage.prompt_tokens} / ${currentData.token_usage.completion_tokens}`;
            } else if (metaTokens) {
                metaTokens.textContent = '-';
            }

            // Render Patient Tabs
            patientTabs.innerHTML = '';
            const patients = currentData.aggregated?.patients || {};
            const patientNames = Object.keys(patients).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));

            if (patientNames.length === 0) {
                patientContent.innerHTML = '<p>Nenhum dado de paciente encontrado nesta sessão.</p>';
                return;
            }

            patientNames.forEach((name, index) => {
                const li = document.createElement('li');
                li.className = `patient-tab ${index === 0 ? 'active' : ''}`;
                li.textContent = name;
                li.dataset.patient = name;
                li.style.padding = '0.75rem 0';
                li.style.cursor = 'pointer';
                li.style.color = 'var(--text-muted)';
                li.style.fontWeight = '500';
                li.style.borderBottom = '2px solid transparent';
                li.style.transition = 'color 0.2s, border-color 0.2s';
                
                li.addEventListener('click', () => selectPatient(name, li));
                patientTabs.appendChild(li);
            });

            // Auto-select first patient
            selectPatient(patientNames[0], patientTabs.children[0]);
        }

        function selectPatient(name, tabElement) {
            if (!tabElement) return;

            // Update active tab UI
            document.querySelectorAll('.patient-tab').forEach(tab => {
                tab.classList.remove('active');
                tab.style.color = 'var(--text-muted)';
                tab.style.borderBottomColor = 'transparent';
            });
            tabElement.classList.add('active');
            tabElement.style.color = 'var(--primary)';
            tabElement.style.borderBottomColor = 'var(--primary)';

            const patientData = currentData.aggregated.patients[name];

            // Clone template
            patientContent.innerHTML = '';
            const clone = patientTemplate.content.cloneNode(true);
            const tplTop3 = clone.querySelector('#tplTop3');
            const tplDimensions = clone.querySelector('#tplDimensions');

            // Render Top 3 Dimensions
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
                tplTop3.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">Nenhuma dimensão prioritária ativa para este paciente nesta sessão.</p>';
            }

            // Render Dimensions List
            if (patientData.dimensions && Object.keys(patientData.dimensions).length > 0) {
                const dims = Object.values(patientData.dimensions).sort((a, b) => b.dimension_sum - a.dimension_sum);

                dims.forEach(dim => {
                    const dimEl = document.createElement('div');
                    dimEl.className = 'dimension-item';

                    const dimKey = Object.keys(patientData.dimensions).find(k => patientData.dimensions[k].name === dim.name);
                    const relevantItems = Object.entries(patientData.items).filter(([itemId]) => itemId.startsWith(dimKey + '.'));

                    let itemsHtml = '';
                    relevantItems.forEach(([itemId, item]) => {
                        const evidenceHtml = item.evidence.map(ev => `<li class="evidence-quote" style="background-color: white; padding: 0.75rem 1rem; border-left: 4px solid var(--primary); border-radius: 0 4px 4px 0; font-size: 0.875rem; color: var(--text-muted); margin-bottom: 0.5rem;">"${ev}"</li>`).join('');
                        itemsHtml += `
                            <div class="item-row" style="margin-top: 1.25rem;">
                                <div class="item-header" style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1.5rem; margin-bottom: 0.5rem;">
                                    <span class="item-name" style="font-weight: 500; color: var(--text-main); font-size: 0.95rem;">${itemId} - ${item.name}</span>
                                    <span class="score-badge" data-severity="${item.score}">Pontuação: ${item.score}</span>
                                </div>
                                <ul class="item-evidence" style="list-style: none; padding: 0; margin: 0;">
                                    ${evidenceHtml}
                                </ul>
                            </div>
                        `;
                    });

                    const maxSize = (dimKey === "16" ? 3 : 2) * 4;
                    const severity = Math.ceil((dim.dimension_sum / maxSize) * 4) || 1;
                    dimEl.innerHTML = `
                        <div class="dimension-header" style="padding: 1.25rem 1.5rem; display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none;">
                            <div class="dimension-title-group" style="display: flex; align-items: center; gap: 1rem;">
                                <span class="dimension-name" style="font-weight: 600; font-size: 1.05rem;">${dimKey}. ${dim.name}</span>
                            </div>
                            <div class="score-badge" data-severity="${severity}">Pontuação: ${dim.dimension_sum}/${maxSize}</div>
                        </div>
                        <div class="dimension-body" style="display: none; padding: 0 1.5rem 1.5rem; border-top: 1px solid var(--border); background-color: #fafafa;">
                            ${itemsHtml}
                        </div>
                    `;

                    // Toggle accordion
                    const header = dimEl.querySelector('.dimension-header');
                    header.addEventListener('click', () => {
                        dimEl.classList.toggle('open');
                        const body = dimEl.querySelector('.dimension-body');
                        body.style.display = dimEl.classList.contains('open') ? 'block' : 'none';
                    });

                    tplDimensions.appendChild(dimEl);
                });
            } else {
                tplDimensions.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">Nenhuma dimensão quantificada para este paciente nesta sessão.</p>';
            }

            patientContent.appendChild(clone);
        }

        // Collapsible Transcript Handler
        const toggleTranscriptHeader = document.getElementById('toggleTranscriptHeader');
        const transcriptBodyContainer = document.getElementById('transcriptBodyContainer');
        const transcriptToggleIndicator = document.getElementById('transcriptToggleIndicator');

        if (toggleTranscriptHeader && transcriptBodyContainer) {
            toggleTranscriptHeader.addEventListener('click', () => {
                const isOpen = transcriptBodyContainer.style.display === 'block';
                transcriptBodyContainer.style.display = isOpen ? 'none' : 'block';
                transcriptToggleIndicator.textContent = isOpen ? 'Expandir ▼' : 'Recolher ▲';
            });
        }
    }

    // =========================================================================
    // STATE 2: PIPELINE POLLING LOGIC (When actively running)
    // =========================================================================
    if (initialTranscriptStatus && ['preprocessing', 'analyzing', 'queued'].includes(initialTranscriptStatus)) {
        const logConsole = document.getElementById('logConsole');
        
        function addLog(msg, type = 'normal') {
            if (!logConsole) return;
            const entry = document.createElement('div');
            entry.className = `log-entry`;
            entry.style.marginBottom = '0.25rem';
            if (type === 'success') entry.style.color = '#10b981';
            else if (type === 'error') entry.style.color = '#ef4444';
            else if (type === 'system') entry.style.color = '#3b82f6';
            
            const time = new Date().toLocaleTimeString();
            entry.textContent = `[${time}] ${msg}`;
            logConsole.appendChild(entry);
            logConsole.scrollTop = logConsole.scrollHeight;
        }

        addLog(`Iniciando monitoramento de execução da sessão ${sessionId}...`, 'system');

        async function pollDatabaseStatus() {
            try {
                const response = await fetch(`/api/sessions/${sessionId}/status`);
                const data = await response.json();

                if (data.status === 'completed') {
                    addLog('Processamento finalizado com sucesso! Atualizando painel clínico...', 'success');
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
        const browseBtn = document.getElementById('browseBtn');
        const selectedFilePanel = document.getElementById('selectedFilePanel');
        const fileName = document.getElementById('fileName');
        const removeFileBtn = document.getElementById('removeFileBtn');
        const skipSanitizationOpt = document.getElementById('skipSanitizationOpt');
        const startBtn = document.getElementById('startBtn');

        const newSessionView = document.getElementById('newSessionView');
        const processingView = document.getElementById('processingView');
        const statusTitle = document.getElementById('statusTitle');
        const statusDesc = document.getElementById('statusDesc');
        const logConsole = document.getElementById('logConsole');

        let selectedFile = null;
        let activePolling = false;

        function addLog(msg, type = 'normal') {
            if (!logConsole) return;
            const entry = document.createElement('div');
            entry.className = `log-entry`;
            entry.style.marginBottom = '0.25rem';
            if (type === 'success') entry.style.color = '#10b981';
            else if (type === 'error') entry.style.color = '#ef4444';
            else if (type === 'system') entry.style.color = '#3b82f6';
            
            const time = new Date().toLocaleTimeString();
            entry.textContent = `[${time}] ${msg}`;
            logConsole.appendChild(entry);
            logConsole.scrollTop = logConsole.scrollHeight;
        }

        // Click selection triggers
        browseBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            fileInput.click();
        });
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
            dropZone.style.borderColor = 'var(--primary)';
            dropZone.style.background = '#f1f5f9';
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.style.borderColor = 'var(--border)';
            dropZone.style.background = '#fafafa';
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = 'var(--border)';
            dropZone.style.background = '#fafafa';
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                handleFileSelection(e.dataTransfer.files[0]);
            }
        });

        function handleFileSelection(file) {
            const ext = file.name.split('.').pop().toLowerCase();
            if (ext !== 'docx' && ext !== 'txt') {
                alert('Apenas arquivos de transcrição .docx e .txt são suportados.');
                return;
            }
            selectedFile = file;
            fileName.textContent = file.name;
            dropZone.style.display = 'none';
            selectedFilePanel.style.display = 'flex';
        }

        // Remove selected file
        removeFileBtn.addEventListener('click', (e) => {
            e.preventDefault();
            selectedFile = null;
            fileInput.value = '';
            selectedFilePanel.style.display = 'none';
            dropZone.style.display = 'block';
        });

        // Initiate upload and start async task
        startBtn.addEventListener('click', async () => {
            if (!selectedFile) {
                alert('Por favor, selecione um arquivo de transcrição para fazer o upload.');
                return;
            }

            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('skip_sanitization', skipSanitizationOpt.checked ? 'true' : 'false');
            formData.append('therapy_session_id', sessionId.toString());

            // Switch view state to Processing Console
            newSessionView.style.display = 'none';
            processingView.style.display = 'block';
            statusTitle.textContent = 'Enviando Arquivo...';
            addLog(`Iniciando upload de ${selectedFile.name}...`, 'system');

            try {
                const response = await fetch(`/therapy_sessions/${sessionId}/upload_transcript`, {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();

                if (response.ok && data.success) {
                    statusTitle.textContent = 'Processando Transcrição...';
                    statusDesc.textContent = 'O pipeline assíncrono de IA está ativado no banco de dados. Acompanhe os logs de telemetria abaixo.';
                    addLog('Upload de arquivo concluído com sucesso. Iniciando pré-processamento...', 'success');
                    
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
            statusTitle.style.color = 'var(--error)';
            statusDesc.textContent = 'A ingestão falhou antes de disparar o pipeline.';
            const spinner = document.querySelector('.spinner');
            if (spinner) spinner.style.display = 'none';
            addLog(msg, 'error');
        }

        async function pollDatabaseStatusAfterUpload() {
            if (!activePolling) return;

            try {
                const response = await fetch(`/api/sessions/${sessionId}/status`);
                const data = await response.json();

                if (data.status === 'completed') {
                    addLog('Diagnóstico TDPM-20 finalizado com sucesso! Atualizando laudo clínico...', 'success');
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
