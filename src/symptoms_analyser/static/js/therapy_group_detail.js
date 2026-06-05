/**
 * therapy_group_detail.js
 *
 * Handles client-side interactivity for the therapy group detail workstation:
 *   1. Parent tab switching
 */

document.addEventListener('DOMContentLoaded', () => {
    // =========================================================================
    // 1. Parent Tab Switcher
    // =========================================================================
    const tabButtons = document.querySelectorAll('.session-tab-btn');
    const tabPanels = document.querySelectorAll('.session-tab-panel');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.dataset.target;
            if (!targetId) return;

            // Deactivate all tab buttons and panels
            tabButtons.forEach(b => b.classList.remove('active'));
            tabPanels.forEach(p => p.classList.remove('active'));

            // Activate selected tab button and panel
            btn.classList.add('active');
            const targetPanel = document.getElementById(targetId);
            if (targetPanel) {
                targetPanel.classList.add('active');
            }

            // Force a resize event to ensure elements scale dynamically when visible
            window.dispatchEvent(new Event('resize'));
        });
    });
});
