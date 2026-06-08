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
            if (!badge) return;

            const errMsg = badge.dataset.error;
            if (errMsg) {
                tracebackContent.textContent = errMsg;
                tracebackModal.style.display = 'flex';
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
