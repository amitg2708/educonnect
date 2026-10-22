/**
 * EduConnect Core Client-side Scripts & PWA Integration
 */

// Service Worker Registration & Safe Update Tracking
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js', { scope: '/' })
            .then((registration) => {
                console.log('%c[PWA]%c Service worker active with scope:', 'color: #6366f1; font-weight: bold;', 'color: #10b981;', registration.scope);

                // Check for updates
                registration.onupdatefound = () => {
                    const installingWorker = registration.installing;
                    if (installingWorker) {
                        installingWorker.onstatechange = () => {
                            if (installingWorker.state === 'installed' && navigator.serviceWorker.controller) {
                                console.log('[PWA] New version detected. Ready for reload.');
                            }
                        };
                    }
                };
            })
            .catch((error) => {
                console.warn('[PWA] Service worker registration notice:', error);
            });
    });

    // Listen for controller changes on safe update activation
    navigator.serviceWorker.addEventListener('controllerchange', () => {
        console.log('[PWA] Application cache updated to latest release.');
    });
}

// PWA Installation Prompt Flow
let deferredInstallPrompt = null;

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    
    // Unhide install buttons if present
    const installBtns = document.querySelectorAll('.pwa-install-trigger');
    installBtns.forEach((btn) => {
        btn.classList.remove('d-none');
        btn.onclick = async () => {
            if (deferredInstallPrompt) {
                deferredInstallPrompt.prompt();
                const choice = await deferredInstallPrompt.userChoice;
                console.log('[PWA] User install choice:', choice.outcome);
                deferredInstallPrompt = null;
                btn.classList.add('d-none');
            }
        };
    });
});

window.addEventListener('appinstalled', () => {
    console.log('[PWA] EduConnect app successfully installed.');
    const installBtns = document.querySelectorAll('.pwa-install-trigger');
    installBtns.forEach((btn) => btn.classList.add('d-none'));
});

// DOM Ready Handlers
document.addEventListener('DOMContentLoaded', () => {
    // Initialize all Bootstrap tooltips if any
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map((tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl));

    // Console branding
    console.log(
        '%cEduConnect%c Platform Initialized | Multi-Tenant Architecture & PWA Ready',
        'background: #6366f1; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;',
        'color: #10b981; padding-left: 8px;'
    );
});
