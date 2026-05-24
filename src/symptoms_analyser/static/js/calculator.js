document.addEventListener('DOMContentLoaded', () => {
    const calcPrepPrompt = document.getElementById('calcPrepPrompt');
    const calcPrepComp = document.getElementById('calcPrepComp');
    const calcAnaPrompt = document.getElementById('calcAnaPrompt');
    const calcAnaComp = document.getElementById('calcAnaComp');
    const calcSessions = document.getElementById('calcSessions');
    const hybridPrepSelect = document.getElementById('hybridPrepSelect');
    const hybridAnaSelect = document.getElementById('hybridAnaSelect');
    const hybridSessionCost = document.getElementById('hybridSessionCost');
    const hybridTotalCost = document.getElementById('hybridTotalCost');
    const costTable = document.getElementById('costTable');
    const costTableBody = costTable.querySelector('tbody');

    let pricingData = [];

    function loadPricingData() {
        fetch('/static/prices.csv')
            .then(res => res.text())
            .then(csv => {
                const lines = csv.trim().split('\n');
                pricingData = lines.slice(1).map(line => {
                    const parts = line.split(',');
                    return {
                        provider: parts[0],
                        model: parts[1],
                        inputPrice: parseFloat(parts[2]),
                        outputPrice: parseFloat(parts[3])
                    };
                });

                // Populate selects
                hybridPrepSelect.innerHTML = '';
                hybridAnaSelect.innerHTML = '';
                pricingData.forEach((item, index) => {
                    const opt1 = document.createElement('option');
                    opt1.value = index;
                    opt1.textContent = `${item.provider} - ${item.model}`;
                    hybridPrepSelect.appendChild(opt1);

                    const opt2 = document.createElement('option');
                    opt2.value = index;
                    opt2.textContent = `${item.provider} - ${item.model}`;
                    hybridAnaSelect.appendChild(opt2);
                });

                // Set selections (restore or default)
                const savedHybridPrep = localStorage.getItem('viewer_hybrid_prep_select');
                const savedHybridAna = localStorage.getItem('viewer_hybrid_ana_select');

                if (savedHybridPrep !== null && parseInt(savedHybridPrep) < pricingData.length) {
                    hybridPrepSelect.value = savedHybridPrep;
                } else if (pricingData.length > 0) {
                    hybridPrepSelect.selectedIndex = 0; // First item usually flash/cheap
                }

                if (savedHybridAna !== null && parseInt(savedHybridAna) < pricingData.length) {
                    hybridAnaSelect.value = savedHybridAna;
                } else if (pricingData.length > 0) {
                    hybridAnaSelect.selectedIndex = Math.min(1, pricingData.length - 1); // Second item usually pro
                }

                updateCalculator();
            })
            .catch(err => console.error("Error loading CSV", err));
    }

    function updateCalculator() {
        if (pricingData.length === 0) return;

        const pPrompt = parseInt(calcPrepPrompt.value) || 0;
        const pComp = parseInt(calcPrepComp.value) || 0;
        const aPrompt = parseInt(calcAnaPrompt.value) || 0;
        const aComp = parseInt(calcAnaComp.value) || 0;
        const sessions = parseInt(calcSessions.value) || 0;

        // Save values to localStorage
        localStorage.setItem('viewer_calc_prep_prompt', calcPrepPrompt.value);
        localStorage.setItem('viewer_calc_prep_comp', calcPrepComp.value);
        localStorage.setItem('viewer_calc_ana_prompt', calcAnaPrompt.value);
        localStorage.setItem('viewer_calc_ana_comp', calcAnaComp.value);
        localStorage.setItem('viewer_calc_sessions', calcSessions.value);
        localStorage.setItem('viewer_hybrid_prep_select', hybridPrepSelect.value);
        localStorage.setItem('viewer_hybrid_ana_select', hybridAnaSelect.value);

        const totalInputTokens = pPrompt + aPrompt;
        const totalOutputTokens = pComp + aComp;

        costTableBody.innerHTML = '';

        pricingData.forEach(item => {
            const inputCost = (totalInputTokens / 1000000) * item.inputPrice;
            const outputCost = (totalOutputTokens / 1000000) * item.outputPrice;
            const sessionCost = inputCost + outputCost;
            const totalCost = sessionCost * sessions;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="provider-cell">${item.provider}</td>
                <td>${item.model}</td>
                <td>$${item.inputPrice.toFixed(3).replace('.', ',')}</td>
                <td>$${item.outputPrice.toFixed(3).replace('.', ',')}</td>
                <td class="total-cell">$${sessionCost.toFixed(3).replace('.', ',')}</td>
                <td class="total-cell">$${totalCost.toFixed(2).replace('.', ',')}</td>
            `;
            costTableBody.appendChild(tr);
        });

        // Calculate Hybrid
        const prepIndex = parseInt(hybridPrepSelect.value);
        const anaIndex = parseInt(hybridAnaSelect.value);

        if (!isNaN(prepIndex) && !isNaN(anaIndex) && pricingData[prepIndex] && pricingData[anaIndex]) {
            const prepModel = pricingData[prepIndex];
            const anaModel = pricingData[anaIndex];

            const prepCost = (pPrompt / 1000000) * prepModel.inputPrice + (pComp / 1000000) * prepModel.outputPrice;
            const anaCost = (aPrompt / 1000000) * anaModel.inputPrice + (aComp / 1000000) * anaModel.outputPrice;

            const hSessionCost = prepCost + anaCost;
            const hTotalCost = hSessionCost * sessions;

            hybridSessionCost.textContent = '$' + hSessionCost.toFixed(3).replace('.', ',');
            hybridTotalCost.textContent = '$' + hTotalCost.toFixed(2).replace('.', ',');
        }
    }

    // Restore calculator values
    const savedPrepPrompt = localStorage.getItem('viewer_calc_prep_prompt');
    const savedPrepComp = localStorage.getItem('viewer_calc_prep_comp');
    const savedAnaPrompt = localStorage.getItem('viewer_calc_ana_prompt');
    const savedAnaComp = localStorage.getItem('viewer_calc_ana_comp');
    const savedSessions = localStorage.getItem('viewer_calc_sessions');

    if (savedPrepPrompt !== null) calcPrepPrompt.value = savedPrepPrompt;
    if (savedPrepComp !== null) calcPrepComp.value = savedPrepComp;
    if (savedAnaPrompt !== null) calcAnaPrompt.value = savedAnaPrompt;
    if (savedAnaComp !== null) calcAnaComp.value = savedAnaComp;
    if (savedSessions !== null) calcSessions.value = savedSessions;

    [calcPrepPrompt, calcPrepComp, calcAnaPrompt, calcAnaComp, calcSessions, hybridPrepSelect, hybridAnaSelect].forEach(input => {
        if (input) {
            input.addEventListener('input', updateCalculator);
            input.addEventListener('change', updateCalculator);
        }
    });

    // Start load
    loadPricingData();
});
