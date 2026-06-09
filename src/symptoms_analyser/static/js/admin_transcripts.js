document.addEventListener('DOMContentLoaded', () => {
    // Tables
    const jobsTableBody = document.getElementById('jobsTableBody');
    const evalTelemetryTableBody = document.getElementById('evalTelemetryTableBody');

    // Modal
    const tracebackModal = document.getElementById('tracebackModal');
    const tracebackContent = document.getElementById('tracebackContent');
    const closeTracebackBtn = document.getElementById('closeTracebackBtn');

    // --- Event Delegation for Failed Jobs Badges Click ---
    if (jobsTableBody) {
        jobsTableBody.addEventListener('click', (e) => {
            const badge = e.target.closest('.status-badge[data-status="failed"]');
            if (badge) {
                const errMsg = badge.dataset.error;
                if (errMsg) {
                    tracebackContent.textContent = errMsg;
                    tracebackModal.style.display = 'flex';
                }
                return;
            }

            const deleteBtn = e.target.closest('.delete-transcript-btn');
            if (deleteBtn) {
                const transcriptId = deleteBtn.dataset.id;
                if (!transcriptId) return;

                const confirmed = confirm(`Deseja realmente excluir a transcrição ID ${transcriptId} e todas as suas análises associadas? Esta ação é irreversível.`);
                if (!confirmed) return;

                // Disable button
                deleteBtn.disabled = true;
                deleteBtn.textContent = 'Excluindo...';

                fetch(`/api/admin/transcripts/${transcriptId}`, {
                    method: 'DELETE',
                })
                .then(response => response.json().then(result => ({ response, result })))
                .then(({ response, result }) => {
                    if (response.ok && result.success) {
                        window.location.reload();
                    } else {
                        alert(`Erro ao excluir transcrição: ${result.error || 'Erro desconhecido'}`);
                        deleteBtn.disabled = false;
                        deleteBtn.textContent = 'Excluir';
                    }
                })
                .catch(error => {
                    console.error('Error deleting transcript:', error);
                    alert('Ocorreu um erro de rede ao tentar excluir a transcrição.');
                    deleteBtn.disabled = false;
                    deleteBtn.textContent = 'Excluir';
                });
            }
        });
    }

    // --- Event Delegation for Failed Evaluation Badges Click ---
    if (evalTelemetryTableBody) {
        evalTelemetryTableBody.addEventListener('click', (e) => {
            const badge = e.target.closest('.status-badge[data-status="failed"]');
            if (!badge) return;

            const errMsg = badge.dataset.error;
            if (errMsg) {
                tracebackContent.textContent = errMsg;
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
});
