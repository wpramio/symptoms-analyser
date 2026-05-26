document.addEventListener('DOMContentLoaded', () => {
    // Stats Elements
    const statTranscripts = document.getElementById('statTranscripts');
    const statSuccess = document.getElementById('statSuccess');
    const statTokens = document.getElementById('statTokens');
    const statTokensDesc = document.getElementById('statTokensDesc');

    // Tables
    const jobsTableBody = document.getElementById('jobsTableBody');
    const telemetryTableBody = document.getElementById('telemetryTableBody');

    // Modal
    const tracebackModal = document.getElementById('tracebackModal');
    const tracebackContent = document.getElementById('tracebackContent');
    const closeTracebackBtn = document.getElementById('closeTracebackBtn');

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
                statTranscripts.textContent = data.total_transcripts;
                statSuccess.textContent = data.success_rate + '%';
                
                const totalTokens = data.total_prompt_tokens + data.total_completion_tokens;
                statTokens.textContent = totalTokens.toLocaleString();
                statTokensDesc.textContent = `Prompt: ${data.total_prompt_tokens.toLocaleString()} | Comp: ${data.total_completion_tokens.toLocaleString()}`;
            })
            .catch(err => console.error("Error loading admin stats:", err));
    }

    // --- 2. Monitor Pipelines (Ingest List with active status polling) ---
    function fetchJobs() {
        fetch('/api/admin/transcripts')
            .then(res => res.json())
            .then(jobs => {
                if (jobs.length === 0) {
                    jobsTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 3rem;">Nenhuma ingestão registrada no banco de dados.</td></tr>`;
                    return;
                }

                let html = '';
                jobs.forEach(job => {
                    const progressVal = job.progress_percent || 0;
                    let progressHtml = '';

                    if (job.status === 'preprocessing' || job.status === 'analyzing') {
                        progressHtml = `
                            <div style="font-size: 0.8rem; color: var(--text-muted); font-weight: 600; display: flex; justify-content: space-between;">
                                <span>${job.status === 'preprocessing' ? 'Pré-processando' : 'Analisando'}</span>
                                <span>${progressVal.toFixed(0)}%</span>
                            </div>
                            <div class="progress-bar-container">
                                <div class="progress-bar-fill" style="width: ${progressVal}%"></div>
                            </div>
                        `;
                    } else {
                        progressHtml = `<span>Progresso: ${progressVal.toFixed(0)}%</span>`;
                    }

                    const statusText = job.status === 'failed' ? 'Falha (Ver erro)' : job.status;
                    const cursorStyle = job.status === 'failed' ? 'style="cursor: pointer;"' : '';

                    html += `
                        <tr>
                            <td><strong style="color: var(--primary);">${job.id}</strong></td>
                            <td>${job.filename}</td>
                            <td>${formatBytes(job.file_size_bytes)}</td>
                            <td>
                                <div class="status-badge" data-status="${job.status}" ${cursorStyle} data-id="${job.id}">
                                    ${statusText}
                                </div>
                                <div style="margin-top: 0.5rem;">${progressHtml}</div>
                            </td>
                            <td style="color: var(--text-muted); font-size: 0.85rem;">${formatDate(job.created_at)}</td>
                        </tr>
                    `;
                });

                jobsTableBody.innerHTML = html;

                // Bind click to open traceback logs modal
                const failedBadges = jobsTableBody.querySelectorAll('.status-badge[data-status="failed"]');
                failedBadges.forEach(badge => {
                    badge.addEventListener('click', () => {
                        const jobID = badge.dataset.id;
                        const job = jobs.find(j => j.id === jobID);
                        if (job && job.error_message) {
                            tracebackContent.textContent = job.error_message;
                            tracebackModal.style.display = 'flex';
                        }
                    });
                });
            })
            .catch(err => console.error("Error loading job listings:", err));
    }

    // --- 3. Telemetry Log Loader ---
    function fetchTelemetryData() {
        fetch('/api/admin/telemetry')
            .then(res => res.json())
            .then(items => {
                if (items.length === 0) {
                    telemetryTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 3rem;">Nenhum log de telemetria encontrado.</td></tr>`;
                    return;
                }

                let html = '';
                items.forEach(tele => {
                    let corrHtml = '';
                    const entries = Object.entries(tele.corrections_map || {});
                    if (entries.length > 0) {
                        corrHtml = `<div class="corrections-grid">`;
                        entries.forEach(([orig, corr]) => {
                            corrHtml += `
                                <span class="correction-pill">
                                    <span style="color: var(--text-muted); text-decoration: line-through;">${orig}</span>
                                    <span class="correction-arrow">→</span>
                                    <strong style="color: var(--primary);">${corr}</strong>
                                </span>
                            `;
                        });
                        corrHtml += `</div>`;
                    } else {
                        corrHtml = `<span style="color: var(--text-muted); font-size: 0.85rem;">Nenhuma correção necessária</span>`;
                    }

                    let flagHtml = '';
                    if (tele.anonymization_flags && tele.anonymization_flags.length > 0) {
                        flagHtml = `<div class="phi-leaks-grid">`;
                        tele.anonymization_flags.forEach(flag => {
                            flagHtml += `<span class="flag-warning-badge">PHI Leak: ${flag}</span>`;
                        });
                        flagHtml += `</div>`;
                    } else {
                        flagHtml = `<span class="flag-safe-badge">✓ Seguro (Sem vazamento)</span>`;
                    }

                    html += `
                        <tr>
                            <td><strong style="color: var(--text-main);">${tele.transcript_id}</strong></td>
                            <td style="font-size: 0.85rem;">
                                <strong>Modelo:</strong> ${tele.model}<br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">Estratégia: ${tele.strategy}</span><br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">Blocos: ${tele.chunks_completed || 0}</span><br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">Tokens: ${tele.prompt_tokens ? (tele.prompt_tokens.toLocaleString() + ' / ' + tele.completion_tokens.toLocaleString()) : '0 / 0'}</span>
                            </td>
                            <td>${corrHtml}</td>
                            <td>${flagHtml}</td>
                            <td style="font-size: 0.85rem;">
                                <strong>${tele.elapsed_seconds}s</strong><br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">Turns: ${tele.turns_merged}</span>
                            </td>
                        </tr>
                    `;
                });

                telemetryTableBody.innerHTML = html;
            })
            .catch(err => console.error("Error loading telemetry logs:", err));
    }

    // Modal Closer Events
    closeTracebackBtn.addEventListener('click', () => { tracebackModal.style.display = 'none'; });
    tracebackModal.addEventListener('click', (e) => {
        if (e.target === tracebackModal) tracebackModal.style.display = 'none';
    });

    // Boot and start poller loops
    fetchStats();
    fetchJobs();
    fetchTelemetryData();

    setInterval(fetchStats, 60000); // 1 minute stats update
    setInterval(fetchJobs, 3000);   // 3 seconds pipeline update
    setInterval(fetchTelemetryData, 10000); // 10 seconds telemetry log update
});
