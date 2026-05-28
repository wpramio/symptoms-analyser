document.addEventListener('DOMContentLoaded', () => {
    const compareSelect1 = document.getElementById('compareSelect1');
    const compareSelect2 = document.getElementById('compareSelect2');
    const btnToggleAll = document.getElementById('btnToggleAll');
    const comparePatientsContent = document.getElementById('comparePatientsContent');

    let allExpanded = false;

    // 1. Restore saved selections from localStorage if query parameters are missing
    const urlParams = new URLSearchParams(window.location.search);
    const paramA = urlParams.get('a');
    const paramB = urlParams.get('b');

    if (!paramA && !paramB) {
        const savedCompare1 = localStorage.getItem('viewer_compare_select_1');
        const savedCompare2 = localStorage.getItem('viewer_compare_select_2');
        if (savedCompare1 || savedCompare2) {
            const query = new URLSearchParams();
            if (savedCompare1) query.set('a', savedCompare1);
            if (savedCompare2) query.set('b', savedCompare2);
            window.location.href = `/admin/compare_tdpm_analysis?${query.toString()}`;
            return;
        }
    }

    // 2. Save current query parameters to localStorage if present
    if (paramA) localStorage.setItem('viewer_compare_select_1', paramA);
    if (paramB) localStorage.setItem('viewer_compare_select_2', paramB);

    // 3. Dropdown change listener redirects with updated query parameters
    function handleCompareChange() {
        const path1 = compareSelect1.value;
        const path2 = compareSelect2.value;
        
        if (path1) localStorage.setItem('viewer_compare_select_1', path1);
        if (path2) localStorage.setItem('viewer_compare_select_2', path2);

        const query = new URLSearchParams();
        if (path1) query.set('a', path1);
        if (path2) query.set('b', path2);
        
        window.location.href = `/admin/compare_tdpm_analysis?${query.toString()}`;
    }

    if (compareSelect1) compareSelect1.addEventListener('change', handleCompareChange);
    if (compareSelect2) compareSelect2.addEventListener('change', handleCompareChange);

    // 4. "Expand all / Collapse all" logic
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

    // 5. Individual dimension header expand/collapse accordion logic (delegated click handler)
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
