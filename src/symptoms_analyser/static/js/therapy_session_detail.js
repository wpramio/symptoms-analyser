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
        // CLINICAL SYNTHESIS / MINUTA DE EVOLUÇÃO CLÍNICA HANDLERS
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
        const applySanitizationOpt = document.getElementById('applySanitizationOpt');
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
            formData.append('apply_sanitization', applySanitizationOpt.checked ? 'true' : 'false');
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
