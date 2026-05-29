document.addEventListener('DOMContentLoaded', () => {
    const _page = JSON.parse(document.getElementById('page-data').textContent);
    const sessionId = _page.sessionId;
    const evaluationId = _page.evaluationId;
    const evaluationPath = _page.evaluationPath;
    const initialTranscriptStatus = _page.transcriptStatus;

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
        const btnShowSessionMeta = document.getElementById('btnShowSessionMeta');
        const metaPopover = document.getElementById('metaPopover');

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
            // Skip transcript accordion, which is handled separately
            if (header.id === 'toggleTranscriptHeader') return;

            const dimensionItem = header.closest('.dimension-item');
            if (!dimensionItem) return;

            dimensionItem.classList.toggle('open');
        });

        // Collapsible Transcript Handler
        const toggleTranscriptHeader = document.getElementById('toggleTranscriptHeader');
        const transcriptCard = document.querySelector('.transcript-card');
        const transcriptToggleIndicator = document.getElementById('transcriptToggleIndicator');

        if (toggleTranscriptHeader && transcriptCard) {
            toggleTranscriptHeader.addEventListener('click', () => {
                const isOpen = transcriptCard.classList.toggle('open');
                transcriptToggleIndicator.textContent = isOpen ? 'Recolher ▲' : 'Expandir ▼';
            });
        }

        // Transcript Tab Switcher (Sanitized vs Raw)
        const btnShowSanitized = document.getElementById('btnShowSanitized');
        const btnShowRaw = document.getElementById('btnShowRaw');
        const transcriptTextContent = document.getElementById('transcriptTextContent');

        if (btnShowSanitized && btnShowRaw && transcriptTextContent) {
            btnShowSanitized.addEventListener('click', () => {
                btnShowSanitized.classList.add('active');
                btnShowRaw.classList.remove('active');
                transcriptTextContent.textContent = transcriptTextContent.dataset.sanitized || '';
            });

            btnShowRaw.addEventListener('click', () => {
                btnShowRaw.classList.add('active');
                btnShowSanitized.classList.remove('active');
                transcriptTextContent.textContent = transcriptTextContent.dataset.raw || '';
            });
        }
    }

    // =========================================================================
    // STATE 2: PIPELINE POLLING LOGIC (When actively running)
    // =========================================================================
    if (initialTranscriptStatus && ['preprocessing', 'analyzing', 'queued'].includes(initialTranscriptStatus)) {
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
        const skipSanitizationOpt = document.getElementById('skipSanitizationOpt');
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
            formData.append('skip_sanitization', skipSanitizationOpt.checked ? 'true' : 'false');
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
