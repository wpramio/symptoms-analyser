const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const browseBtn = document.getElementById('browseBtn');
const selectedFileInfo = document.getElementById('selectedFileInfo');
const fileName = document.getElementById('fileName');
const startBtn = document.getElementById('startBtn');
const uploadView = document.getElementById('uploadView');
const processingView = document.getElementById('processingView');
const statusTitle = document.getElementById('statusTitle');
const statusDesc = document.getElementById('statusDesc');
const logConsole = document.getElementById('logConsole');
const viewResultsBtn = document.getElementById('viewResultsBtn');

let currentFile = null;
let taskId = null;

// Trigger file input
browseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
});
dropZone.addEventListener('click', () => fileInput.click());

// Drag & Drop
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
    }
});

// File selection
fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        handleFile(fileInput.files[0]);
    }
});

function handleFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'docx' && ext !== 'txt') {
        alert('Apenas arquivos .docx e .txt são suportados.');
        return;
    }
    currentFile = file;
    fileName.textContent = file.name;
    selectedFileInfo.style.display = 'flex';
}

// Start Upload & Processing
startBtn.addEventListener('click', async () => {
    if (!currentFile) return;

    const skipSanitization = document.getElementById('skipSanitizationOpt').checked;

    const formData = new FormData();
    formData.append('file', currentFile);
    formData.append('skip_sanitization', skipSanitization ? 'true' : 'false');

    uploadView.style.display = 'none';
    processingView.style.display = 'block';
    viewResultsBtn.style.display = 'none';

    addLog(`Enviando arquivo: ${currentFile.name}...`);

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            taskId = data.task_id;
            addLog(`Upload concluído. Iniciando tarefa de processamento...`);
            pollStatus();
        } else {
            handleError(data.error || 'Erro no upload.');
        }
    } catch (err) {
        handleError('Falha de conexão ao enviar o arquivo.');
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
    statusTitle.textContent = 'Erro no Processamento';
    statusTitle.style.color = 'var(--error)';
    statusDesc.textContent = 'Ocorreu um problema. Veja os logs abaixo.';
    document.querySelector('.spinner').style.display = 'none';
    addLog(msg, 'error');
}

// Poll for task status
async function pollStatus() {
    if (!taskId) return;

    try {
        const response = await fetch(`/api/status/${taskId}`);
        const data = await response.json();

        if (data.status === 'processing') {
            // Update logs based on data.logs
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
            document.querySelector('.spinner').style.display = 'none';
            statusTitle.textContent = 'Análise Concluída!';
            statusTitle.style.color = '#10b981';
            statusDesc.textContent = 'O relatório da sessão foi gerado com sucesso e está pronto.';
            addLog('Processamento finalizado com sucesso.', 'success');
            viewResultsBtn.style.display = 'inline-flex';
        } else if (data.status === 'error') {
            handleError(data.error || 'Erro desconhecido durante o processamento.');
        }
    } catch (err) {
        console.error("Polling error", err);
        setTimeout(pollStatus, 3000);
    }
}
