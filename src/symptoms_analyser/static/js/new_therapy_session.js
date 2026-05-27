document.addEventListener('DOMContentLoaded', () => {
    // Form Inputs
    const sessionName = document.getElementById('sessionName');
    const sessionClinician = document.getElementById('sessionClinician');
    const sessionStart = document.getElementById('sessionStart');
    const sessionDuration = document.getElementById('sessionDuration');
    const sessionPatients = document.getElementById('sessionPatients');

    // Import Options
    const enableImportOpt = document.getElementById('enableImportOpt');
    const importContainer = document.getElementById('importContainer');
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const browseBtn = document.getElementById('browseBtn');
    const selectedFilePanel = document.getElementById('selectedFilePanel');
    const fileName = document.getElementById('fileName');
    const removeFileBtn = document.getElementById('removeFileBtn');
    const autoExtractInfoOpt = document.getElementById('autoExtractInfoOpt');
    const skipSanitizationOpt = document.getElementById('skipSanitizationOpt');

    // Submit Button & Views
    const startBtn = document.getElementById('startBtn');
    const newSessionView = document.getElementById('newSessionView');
    const processingView = document.getElementById('processingView');
    
    // Status Console
    const statusTitle = document.getElementById('statusTitle');
    const statusDesc = document.getElementById('statusDesc');
    const logConsole = document.getElementById('logConsole');
    const viewResultsBtn = document.getElementById('viewResultsBtn');

    let selectedFile = null;
    let taskId = null;

    // 1. Initialize default date to local timezone
    const now = new Date();
    const offsetMs = now.getTimezoneOffset() * 60000;
    const localISO = new Date(now.getTime() - offsetMs).toISOString().slice(0, 16);
    sessionStart.value = localISO;

    // 2. Toggle Transcript Import Container
    enableImportOpt.addEventListener('change', () => {
        if (enableImportOpt.checked) {
            importContainer.style.display = 'block';
            startBtn.textContent = 'Salvar e Analisar Transcrição';
        } else {
            importContainer.style.display = 'none';
            startBtn.textContent = 'Registrar Sessão';
        }
    });

    // 3. File upload click handlers
    browseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
    });
    dropZone.addEventListener('click', () => fileInput.click());

    // 4. Drag & Drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });

    // 5. File selection input change
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileSelection(fileInput.files[0]);
        }
    });

    function handleFileSelection(file) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (ext !== 'docx' && ext !== 'txt') {
            alert('Apenas arquivos .docx e .txt são suportados.');
            return;
        }
        selectedFile = file;
        fileName.textContent = file.name;
        dropZone.style.display = 'none';
        selectedFilePanel.style.display = 'flex';

        // Auto-generate session name if currently empty
        if (!sessionName.value.trim()) {
            sessionName.value = `Sessão: ${file.name.split('.')[0]}`;
        }
    }

    // 6. Remove selected file
    removeFileBtn.addEventListener('click', (e) => {
        e.preventDefault();
        selectedFile = null;
        fileInput.value = '';
        selectedFilePanel.style.display = 'none';
        dropZone.style.display = 'block';
    });

    // 7. Submit therapy session registration
    startBtn.addEventListener('click', async () => {
        const nameVal = sessionName.value.trim();
        const clinicianVal = sessionClinician ? (sessionClinician.value.trim() || 'clinician_1') : 'clinician_1';
        const startVal = sessionStart.value;
        const durationVal = sessionDuration.value;
        const patientsVal = sessionPatients.value.trim();

        // Basic validation
        if (!nameVal && (!enableImportOpt.checked || !selectedFile)) {
            alert('Por favor, defina um nome público para a sessão de terapia.');
            return;
        }

        const formData = new FormData();
        formData.append('session_name', nameVal);
        formData.append('clinician_id', clinicianVal);
        formData.append('start_at', startVal.replace('T', ' ') + ':00');
        formData.append('duration', durationVal);
        formData.append('patient_ids', patientsVal);

        const hasImport = enableImportOpt.checked && selectedFile;
        if (hasImport) {
            formData.append('file', selectedFile);
            formData.append('skip_sanitization', skipSanitizationOpt.checked ? 'true' : 'false');
            formData.append('auto_fill', autoExtractInfoOpt.checked ? 'true' : 'false');

            newSessionView.style.display = 'none';
            processingView.style.display = 'block';
            viewResultsBtn.style.display = 'none';

            addLog(`Enviando arquivo de transcrição: ${selectedFile.name}...`);
        }

        try {
            const response = await fetch('/api/upload_transcript', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                if (data.task_id) {
                    taskId = data.task_id;
                    addLog('Upload concluído. Iniciando processamento relacional da sessão...');
                    pollStatus();
                } else {
                    // Successful manual creation without file
                    alert('Sessão registrada com sucesso no banco de dados!');
                    // Redirect to sessions listings table inside monitor
                    window.location.href = '/admin/transcripts';
                }
            } else {
                handleError(data.error || 'Erro no registro da sessão.');
            }
        } catch (err) {
            handleError('Falha na conexão de rede ao enviar os dados.');
        }
    });

    function addLog(msg, type = 'normal') {
        const entry = document.createElement('div');
        entry.className = `log-entry ${type === 'success' ? 'success-text' : type === 'error' ? 'error-text' : ''}`;
        
        const time = new Date().toLocaleTimeString();
        entry.textContent = `[${time}] ${msg}`;
        
        logConsole.appendChild(entry);
        logConsole.scrollTop = logConsole.scrollHeight;
    }

    function handleError(msg) {
        statusTitle.textContent = 'Erro no Registro';
        statusTitle.style.color = 'var(--error)';
        statusDesc.textContent = 'Ocorreu um problema no pipeline de criação.';
        const spinner = document.querySelector('.spinner');
        if (spinner) spinner.style.display = 'none';
        addLog(msg, 'error');
    }

    // 8. Poll for task status
    async function pollStatus() {
        if (!taskId) return;

        try {
            const response = await fetch(`/api/status/${taskId}`);
            const data = await response.json();

            if (data.status === 'processing') {
                if (data.logs && data.logs.length > 0) {
                    const lastLogCount = parseInt(logConsole.dataset.logCount || '0');
                    if (data.logs.length > lastLogCount) {
                        for (let i = lastLogCount; i < data.logs.length; i++) {
                            addLog(data.logs[i]);
                        }
                        logConsole.dataset.logCount = data.logs.length;
                    }
                }
                setTimeout(pollStatus, 2000);
            } else if (data.status === 'completed') {
                const spinner = document.querySelector('.spinner');
                if (spinner) spinner.style.display = 'none';
                statusTitle.textContent = 'Sessão Registrada e Analisada!';
                statusTitle.style.color = '#10b981';
                statusDesc.textContent = 'A transcrição foi processada, os dados relacionais salvos e o laudo de sintomas está disponível.';
                addLog('Sessão registrada e pontuação clínica TDPM-20 finalizada com sucesso.', 'success');
                viewResultsBtn.style.display = 'inline-flex';
            } else if (data.status === 'error') {
                handleError(data.error || 'Falha inexplicável durante o processamento.');
            }
        } catch (err) {
            console.error("Polling error", err);
            setTimeout(pollStatus, 3000);
        }
    }
});
