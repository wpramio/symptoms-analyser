document.addEventListener('DOMContentLoaded', () => {
    // Stats Elements
    const statTranscripts = document.getElementById('statTranscripts');
    const statSuccess = document.getElementById('statSuccess');
    const statTokens = document.getElementById('statTokens');
    const statTokensDesc = document.getElementById('statTokensDesc');

    // Tables
    const jobsTableBody = document.getElementById('jobsTableBody');
    const telemetryTableBody = document.getElementById('telemetryTableBody');
    const evalTelemetryTableBody = document.getElementById('evalTelemetryTableBody');

    // Modal
    const tracebackModal = document.getElementById('tracebackModal');
    const tracebackContent = document.getElementById('tracebackContent');
    const closeTracebackBtn = document.getElementById('closeTracebackBtn');

    // Store fetched jobs and evaluation telemetry locally to pull traceback reasons on click
    let loadedJobs = [];
    let loadedEvalTelemetry = [];

    // --- Format Helpers ---
    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    function formatDate(dateStr) {
        if (!dateStr) return '-';
        const date = new Date(dateStr.replace(' ', 'T') + 'Z');
        if (isNaN(date.getTime())) return dateStr;
        return date.toLocaleDateString('pt-BR') + ' ' + date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }

    // --- 1. Fetch KPI Statistics ---
    function fetchStats() {
        fetch('/api/admin/stats')
            .then(res => res.json())
            .then(data => {
                if (statTranscripts) statTranscripts.textContent = data.total_transcripts;
                if (statSuccess) statSuccess.textContent = data.success_rate + '%';

                const totalTokens = data.total_prompt_tokens + data.total_completion_tokens;
                if (statTokens) statTokens.textContent = totalTokens.toLocaleString('pt-BR');
                if (statTokensDesc) {
                    statTokensDesc.textContent = `Prompt: ${data.total_prompt_tokens.toLocaleString('pt-BR')} | Comp: ${data.total_completion_tokens.toLocaleString('pt-BR')}`;
                }
            })
            .catch(err => console.error("Error loading admin stats:", err));
    }

    // --- 2. Monitor Pipelines (Ingest List update) ---
    function fetchJobs() {
        fetch('/api/admin/transcripts')
            .then(res => res.json())
            .then(jobs => {
                loadedJobs = jobs;
                if (!jobsTableBody) return;

                if (jobs.length === 0) {
                    jobsTableBody.innerHTML = `<tr><td colspan="5" class="text-center text-muted padding-large">Nenhuma ingestão registrada no banco de dados.</td></tr>`;
                    return;
                }

                let html = '';
                jobs.forEach(job => {
                    const progressVal = job.progress_percent || 0;
                    let progressHtml = '';

                    if (job.status === 'preprocessing' || job.status === 'analyzing') {
                        progressHtml = `
                            <div class="text-muted font-bold text-small d-flex-between">
                                <span>${job.status === 'preprocessing' ? 'Pré-processando' : 'Analisando'}</span>
                                <span>${progressVal.toFixed(0)}%</span>
                            </div>
                            <div class="progress-bar-container">
                                <div class="progress-bar-fill" style="width: ${progressVal}%"></div>
                            </div>
                        `;
                    }

                    const statusMap = {
                        'queued': 'Na Fila',
                        'preprocessing': 'Pré-processando',
                        'preprocessed': 'Pré-processada',
                        'analyzing': 'Analisando',
                        'completed': 'Analisada',
                        'failed': 'Falha (Ver erro)'
                    };
                    const statusText = statusMap[job.status] || job.status;
                    const failedClass = job.status === 'failed' ? 'cursor-pointer' : '';

                    html += `
                        <tr>
                            <td><strong class="text-primary">${job.id}</strong></td>
                            <td>${job.filename}</td>
                            <td>${formatBytes(job.file_size_bytes)}</td>
                            <td>
                                <div class="status-badge ${failedClass}" data-status="${job.status}" data-id="${job.id}">
                                    ${statusText}
                                </div>
                                ${progressHtml ? `<div class="margin-top-small">${progressHtml}</div>` : ''}
                            </td>
                            <td class="text-muted text-medium">${formatDate(job.created_at)}</td>
                        </tr>
                    `;
                });

                jobsTableBody.innerHTML = html;
            })
            .catch(err => console.error("Error loading job listings:", err));
    }

    // --- 3. Clinical Evaluation Telemetry Loader (only to keep traceback maps synced) ---
    function fetchEvaluationTelemetryData() {
        fetch('/api/admin/evaluation-telemetry')
            .then(res => res.json())
            .then(items => {
                loadedEvalTelemetry = items;
            })
            .catch(err => console.error("Error syncing evaluation telemetry:", err));
    }

    // --- 4. Event Delegation for Failed Ingestion Badges Click ---
    if (jobsTableBody) {
        jobsTableBody.addEventListener('click', (e) => {
            const badge = e.target.closest('.status-badge[data-status="failed"]');
            if (!badge) return;

            const jobID = parseInt(badge.dataset.id);
            const job = loadedJobs.find(j => j.id === jobID);
            if (job && job.error_message) {
                tracebackContent.textContent = job.error_message;
                tracebackModal.style.display = 'flex';
            }
        });
    }

    // --- 5. Event Delegation for Failed Evaluation Badges Click ---
    if (evalTelemetryTableBody) {
        evalTelemetryTableBody.addEventListener('click', (e) => {
            const badge = e.target.closest('.status-badge[data-status="failed"]');
            if (!badge) return;

            const evalID = badge.dataset.id;
            // First look in local telemetry cache
            let tele = loadedEvalTelemetry.find(t => String(t.evaluation_id) === String(evalID));
            if (tele && tele.failure_reason) {
                tracebackContent.textContent = tele.failure_reason;
                tracebackModal.style.display = 'flex';
            }
        });
    }

    // Modal Closer Events
    if (closeTracebackBtn) {
        closeTracebackBtn.addEventListener('click', () => { tracebackModal.style.display = 'none'; });
    }
    if (tracebackModal) {
        tracebackModal.addEventListener('click', (e) => {
            if (e.target === tracebackModal) tracebackModal.style.display = 'none';
        });
    }

    // Fetch initial list of evaluation telemetry to populate failed badges modal callbacks
    fetchEvaluationTelemetryData();
    // Cache current pre-rendered jobs listing locally on start
    fetchJobs();

    // Boot background pollers strictly for running pipeline and statistics updates
    setInterval(fetchStats, 10000);   // 10 seconds stats update
    setInterval(fetchJobs, 3000);     // 3 seconds pipeline update
});
