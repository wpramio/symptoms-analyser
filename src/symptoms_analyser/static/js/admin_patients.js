document.addEventListener('DOMContentLoaded', () => {
    const registryTableBody = document.getElementById('registryTableBody');
    const toastNotification = document.getElementById('toastNotification');
    const patientPseudonym = document.getElementById('patientPseudonym');
    const patientRealName = document.getElementById('patientRealName');

    function formatDate(dateStr) {
        if (!dateStr) return '-';
        const date = new Date(dateStr.replace(' ', 'T') + 'Z');
        if (isNaN(date.getTime())) return dateStr;
        return date.toLocaleDateString('pt-BR') + ' ' + date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }

    // --- 1. Fetch Pseudonym isolations list ---
    function fetchRegistryData() {
        fetch('/api/admin/patients')
            .then(res => res.json())
            .then(patients => {
                if (patients.length === 0) {
                    registryTableBody.innerHTML = `<tr><td colspan="2" style="text-align: center; color: var(--text-muted); padding: 3rem;">Nenhum registro de paciente encontrado.</td></tr>`;
                    return;
                }

                let html = '';
                patients.forEach(pat => {
                    html += `
                        <tr>
                            <td><strong style="color: var(--primary); font-size: 0.95rem;">${pat.id}</strong></td>
                            <td>
                                <span style="font-size: 0.95rem; font-weight: 600;">${pat.real_name}</span><br>
                                <span style="color: var(--text-muted); font-size: 0.75rem;">Criado em: ${formatDate(pat.created_at)}</span>
                            </td>
                        </tr>
                    `;
                });

                registryTableBody.innerHTML = html;
            })
            .catch(err => console.error("Error loading isolated mapping registry:", err));
    }

    // --- 2. Form submit new Pseudonym mappings ---
    window.submitPatient = function() {
        const pseudonym = patientPseudonym.value.trim();
        const realName = patientRealName.value.trim();

        // Enforce format checking
        if (!/^Paciente\d+$/.test(pseudonym)) {
            alert("Erro: O pseudônimo precisa estar no formato 'PacienteX', onde X é um número inteiro (ex: Paciente8).");
            return;
        }

        fetch('/api/admin/patients/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pseudonym: pseudonym,
                real_name: realName
            })
        })
        .then(res => {
            if (!res.ok) {
                return res.json().then(data => { throw new Error(data.error || "Erro ao salvar paciente"); });
            }
            return res.json();
        })
        .then(data => {
            // Show toast notification
            toastNotification.style.display = 'block';
            setTimeout(() => {
                toastNotification.style.display = 'none';
            }, 3000);

            // Clear inputs
            patientPseudonym.value = '';
            patientRealName.value = '';

            // Refresh table list
            fetchRegistryData();
        })
        .catch(err => {
            console.error("Error submitting patient map:", err);
            alert(`Falha ao registrar vínculo: ${err.message}`);
        });
    };

    // Load initial listings
    fetchRegistryData();
});
