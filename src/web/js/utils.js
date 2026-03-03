// FormicOS v0.7.9 — Utility functions (standalone, no imports)

const MAX_VISIBLE_TOASTS = 3;

/**
 * Simple string hash for DOM guard comparisons (djb2).
 */
export function hashString(str) {
    let hash = 5381;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) + hash) + str.charCodeAt(i);
        hash = hash & hash; // Convert to 32-bit int
    }
    return String(hash);
}

/**
 * Escape HTML special characters for safe innerHTML insertion.
 */
export function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Escape a string for use inside HTML attribute values.
 */
export function escapeAttr(str) {
    return escapeHtml(str);
}

/**
 * Truncate a string to maxLen characters, appending "..." if truncated.
 */
export function truncateStr(str, max) {
    if (!str) return '';
    str = String(str);
    if (str.length <= max) return str;
    return str.substring(0, max) + '...';
}

/**
 * Format an ISO timestamp into a locale-appropriate display string.
 */
export function formatTimestamp(ts) {
    if (!ts || ts === '--') return '--';
    try {
        const d = new Date(ts);
        if (isNaN(d.getTime())) return String(ts);
        return d.toLocaleString();
    } catch (e) {
        return String(ts);
    }
}

/**
 * Render markdown text to HTML using the marked library (if available).
 * Falls back to escapeHtml if marked is not loaded.
 */
export function renderMarkdown(text) {
    if (typeof marked !== 'undefined' && marked.parse) {
        try {
            let html = marked.parse(text);
            // Highlight code blocks if hljs available
            if (typeof hljs !== 'undefined') {
                const temp = document.createElement('div');
                temp.innerHTML = html;
                const codeBlocks = temp.querySelectorAll('pre code');
                for (let i = 0; i < codeBlocks.length; i++) {
                    hljs.highlightElement(codeBlocks[i]);
                }
                return temp.innerHTML;
            }
            return html;
        } catch (e) {
            return escapeHtml(text);
        }
    }
    return escapeHtml(text);
}

/**
 * Show a toast notification in the notification area.
 * @param {string} message - Text to display.
 * @param {string} type    - 'success' | 'error' | 'warning' | 'info'
 */
export function showNotification(message, type) {
    const area = document.getElementById('notification-area');
    if (!area) return;

    // Cap visible toasts
    while (area.childNodes.length >= MAX_VISIBLE_TOASTS) {
        area.removeChild(area.firstChild);
    }

    const notif = document.createElement('div');
    notif.className = 'notification ' + (type || 'info');
    notif.textContent = message;
    area.appendChild(notif);

    // Auto-remove after 4 seconds
    setTimeout(function () {
        notif.classList.add('fade-out');
        setTimeout(function () {
            if (notif.parentNode) notif.parentNode.removeChild(notif);
        }, 300);
    }, 4000);
}

/**
 * Trap keyboard focus within a modal element for accessibility.
 */
export function trapFocus(modal) {
    if (!modal) return;
    const focusable = modal.querySelectorAll('button, input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    first.focus();
    modal._focusTrapHandler = function (e) {
        if (e.key !== 'Tab') return;
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    modal.addEventListener('keydown', modal._focusTrapHandler);
}

/**
 * Release focus trap from a modal element.
 */
export function releaseFocusTrap(modal) {
    if (!modal || !modal._focusTrapHandler) return;
    modal.removeEventListener('keydown', modal._focusTrapHandler);
    modal._focusTrapHandler = null;
}
