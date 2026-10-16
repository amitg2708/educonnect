/**
 * EduConnect Core Client-side Scripts
 */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize all Bootstrap tooltips if any
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map((tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl));

    // Console branding
    console.log(
        '%cEduConnect%c Platform Initialized | Powered by Django 6 & Official MongoDB Backend',
        'background: #6366f1; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;',
        'color: #10b981; padding-left: 8px;'
    );
});
