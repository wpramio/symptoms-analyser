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
                    } else if (job.status === 'completed' || job.status === 'preprocessed' || job.status === 'failed') {
                        progressHtml = '';
                    } else {
                        progressHtml = `<span>Progresso: ${progressVal.toFixed(0)}%</span>`;
                    }

                    const statusMap = {
                        'queued': 'Na Fila',
                        'preprocessing': 'Pré-processando',
                        'preprocessed': 'Pré-processado',
                        'analyzing': 'Analisando',
                        'completed': 'Concluído',
                        'failed': 'Falha (Ver erro)'
                    };
                    const statusText = statusMap[job.status] || job.status;
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
                                ${progressHtml ? `<div style="margin-top: 0.5rem;">${progressHtml}</div>` : ''}
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

    // --- 4. Clinical Evaluation Telemetry Loader ---
    function fetchEvaluationTelemetryData() {
        fetch('/api/admin/evaluation-telemetry')
            .then(res => res.json())
            .then(items => {
                if (items.length === 0) {
                    evalTelemetryTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 3rem;">Nenhum log de telemetria de avaliação encontrado.</td></tr>`;
                    return;
                }

                let html = '';
                items.forEach(tele => {
                    const statusText = tele.status === 'success' ? 'Sucesso' : 'Falha (Ver erro)';
                    const statusBadgeVal = tele.status === 'success' ? 'completed' : 'failed';
                    const cursorStyle = tele.status === 'success' ? '' : 'style="cursor: pointer;"';

                    const promptTokens = tele.prompt_tokens || 0;
                    const completionTokens = tele.completion_tokens || 0;
                    const totalTokens = promptTokens + completionTokens;

                    html += `
                        <tr>
                            <td><strong style="color: var(--primary);">${tele.evaluation_id}</strong></td>
                            <td style="font-size: 0.85rem;">
                                <strong>Modelo:</strong> ${tele.model}<br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">Chunks: ${tele.chunks_analyzed || 0}</span><br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">Blocos/Chamada: ${tele.blocks_per_call || 0}</span>
                            </td>
                            <td style="font-size: 0.85rem;">
                                <strong>Total:</strong> ${totalTokens.toLocaleString()}<br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">Prompt: ${promptTokens.toLocaleString()}</span><br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">Comp: ${completionTokens.toLocaleString()}</span>
                            </td>
                            <td>
                                <div class="status-badge" data-status="${statusBadgeVal}" ${cursorStyle} data-id="${tele.evaluation_id}">
                                    ${statusText}
                                </div>
                            </td>
                            <td style="font-size: 0.85rem;">
                                <strong>${tele.elapsed_seconds ? tele.elapsed_seconds + 's' : '-'}</strong><br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">${formatDate(tele.created_at)}</span>
                            </td>
                        </tr>
                    `;
                });

                evalTelemetryTableBody.innerHTML = html;

                // Bind click to open traceback logs modal for evaluation telemetry
                const failedEvalBadges = evalTelemetryTableBody.querySelectorAll('.status-badge[data-status="failed"]');
                failedEvalBadges.forEach(badge => {
                    badge.addEventListener('click', () => {
                        const evalID = badge.dataset.id;
                        const tele = items.find(t => t.evaluation_id === evalID);
                        if (tele && tele.failure_reason) {
                            tracebackContent.textContent = tele.failure_reason;
                            tracebackModal.style.display = 'flex';
                        }
                    });
                });
            })
            .catch(err => console.error("Error loading evaluation telemetry logs:", err));
    }    // Modal Closer Events
    closeTracebackBtn.addEventListener('click', () => { tracebackModal.style.display = 'none'; });
    tracebackModal.addEventListener('click', (e) => {
        if (e.target === tracebackModal) tracebackModal.style.display = 'none';
    });

    // --- 5. Therapy Sessions Manager ---
    const sessionsTableBody = document.getElementById('sessionsTableBody');

    function fetchSessions() {
        fetch('/api/admin/sessions')
            .then(res => res.json())
            .then(sessions => {
                if (sessions.length === 0) {
                    sessionsTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 3rem;">Nenhuma sessão de terapia cadastrada.</td></tr>`;
                    return;
                }

                let html = '';
                sessions.forEach(s => {
                    html += `
                        <tr>
                            <td><strong style="color: var(--primary);">#${s.id}</strong></td>
                            <td><strong style="color: var(--text-main); font-size: 0.95rem;">${s.name}</strong></td>
                            <td style="font-size: 0.9rem;">
                                <span>${s.clinician_name}</span><br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">ID: ${s.clinician_id}</span>
                            </td>
                            <td style="font-size: 0.85rem; color: var(--text-muted);">
                                <strong>${formatDate(s.start_at)}</strong><br>
                                <span>Duração: ${s.duration} min</span>
                            </td>
                            <td>
                                <span style="font-size: 0.85rem; font-weight: 600; color: var(--text-main); background: rgba(255,255,255,0.05); padding: 0.25rem 0.5rem; border-radius: 4px;">
                                    ${s.patients}
                                </span>
                            </td>
                        </tr>
                    `;
                });
                sessionsTableBody.innerHTML = html;
            })
            .catch(err => console.error("Error loading therapy sessions:", err));
    }



    // Boot and start poller loops
    fetchStats();
    fetchJobs();
    fetchSessions();
    fetchTelemetryData();
    fetchEvaluationTelemetryData();

    setInterval(fetchStats, 60000); // 1 minute stats update
    setInterval(fetchJobs, 3000);   // 3 seconds pipeline update
    setInterval(fetchSessions, 5000); // 5 seconds session list update
    setInterval(fetchTelemetryData, 10000); // 10 seconds telemetry log update
    setInterval(fetchEvaluationTelemetryData, 10000); // 10 seconds evaluation telemetry log update
});
