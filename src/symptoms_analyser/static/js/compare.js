document.addEventListener('DOMContentLoaded', () => {
    const btnToggleAll = document.getElementById('btnToggleAll');
    const comparePatientsContent = document.getElementById('comparePatientsContent');

    let allExpanded = false;

    // 1. "Expand all / Collapse all" logic
    if (btnToggleAll && comparePatientsContent) {
        btnToggleAll.addEventListener('click', () => {
            allExpanded = !allExpanded;
            const items = comparePatientsContent.querySelectorAll('.dimension-item');
            items.forEach(item => {
                item.classList.toggle('open', allExpanded);
            });
            btnToggleAll.textContent = allExpanded ? 'Colapsar tudo' : 'Expandir tudo';
        });
    }

    // 2. Individual dimension header expand/collapse accordion logic (delegated click handler)
    if (comparePatientsContent) {
        comparePatientsContent.addEventListener('click', (e) => {
            const header = e.target.closest('.dimension-header');
            if (!header) return;
            const item = header.closest('.dimension-item');
            if (item) {
                item.classList.toggle('open');
            }
        });
    }
});
