(() => {
    const state = { inputId: null, root: null, kind: null, current: null };

    const escapeHtml = (value) => String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');

    function buildModal() {
        const modal = document.createElement('div');
        modal.id = 'docker-file-browser';
        modal.className = 'docker-browser-backdrop';
        modal.hidden = true;
        modal.innerHTML = `
            <section class="docker-browser" role="dialog" aria-modal="true" aria-labelledby="docker-browser-title">
                <header class="docker-browser-header">
                    <h2 id="docker-browser-title">Select path</h2>
                    <button type="button" class="docker-browser-icon" data-action="close" aria-label="Close">&#10005;</button>
                </header>
                <div class="docker-browser-path" id="docker-browser-path"></div>
                <div class="docker-browser-list" id="docker-browser-list"></div>
                <footer class="docker-browser-footer">
                    <button type="button" class="btn btn-secondary" data-action="cancel">Cancel</button>
                    <button type="button" class="btn btn-primary" data-action="select">Select folder</button>
                </footer>
            </section>`;
        document.body.appendChild(modal);
        modal.addEventListener('click', handleModalClick);
    }

    async function openBrowser(inputId, root, kind, title) {
        state.inputId = inputId;
        state.root = root;
        state.kind = kind;
        state.current = null;
        document.getElementById('docker-browser-title').textContent = title;
        document.getElementById('docker-file-browser').hidden = false;
        await loadEntries();
    }

    async function loadEntries(path = '') {
        const list = document.getElementById('docker-browser-list');
        list.innerHTML = '<div class="docker-browser-empty">Loading...</div>';
        const query = new URLSearchParams({ root: state.root, kind: state.kind });
        if (path) query.set('path', path);
        try {
            const response = await fetch(`/api/files?${query}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Unable to browse path');
            state.current = data.path;
            document.getElementById('docker-browser-path').textContent = data.path;
            const rows = [];
            if (data.parent) {
                rows.push(`<button type="button" class="docker-browser-row" data-path="${escapeHtml(data.parent)}" data-type="directory"><span class="docker-browser-symbol">&#8593;</span><span>..</span></button>`);
            }
            for (const entry of data.entries) {
                const symbol = entry.type === 'directory' ? '&#128193;' : '&#128196;';
                rows.push(`<button type="button" class="docker-browser-row" data-path="${escapeHtml(entry.path)}" data-type="${entry.type}"><span class="docker-browser-symbol">${symbol}</span><span>${escapeHtml(entry.name)}</span></button>`);
            }
            list.innerHTML = rows.join('') || '<div class="docker-browser-empty">No matching entries</div>';
            const select = document.querySelector('#docker-file-browser [data-action="select"]');
            select.hidden = state.kind === 'model';
        } catch (error) {
            list.innerHTML = `<div class="docker-browser-error">${escapeHtml(error.message)}</div>`;
        }
    }

    function choose(path) {
        const input = document.getElementById(state.inputId);
        input.value = path;
        input.dispatchEvent(new Event('change', { bubbles: true }));
        localStorage.setItem(`anima_factory_${state.inputId}`, path);
        closeBrowser();
    }

    function closeBrowser() {
        document.getElementById('docker-file-browser').hidden = true;
    }

    async function handleModalClick(event) {
        const action = event.target.closest('[data-action]')?.dataset.action;
        if (action === 'close' || action === 'cancel') return closeBrowser();
        if (action === 'select') return choose(state.current);
        const row = event.target.closest('.docker-browser-row');
        if (!row) return;
        if (row.dataset.type === 'directory') await loadEntries(row.dataset.path);
        else choose(row.dataset.path);
    }

    window.browseFolder = () => openBrowser('dataset-path', 'datasets', 'directory', 'Select dataset folder');
    window.browseOutput = () => openBrowser('output-dir', 'output', 'directory', 'Select output folder');
    window.browseFile = (inputId, title) => openBrowser(inputId, 'models', 'model', title);

    window.addEventListener('DOMContentLoaded', () => {
        buildModal();
        const repairButton = document.getElementById('setup-scripts-btn');
        const repairSection = repairButton?.closest('div[style*="border-top"]');
        if (repairSection) repairSection.style.display = 'none';
        const shutdown = document.getElementById('auto-shutdown');
        if (shutdown) shutdown.checked = false;
        localStorage.removeItem('anima_factory_auto-shutdown');
        const shutdownLabel = shutdown?.closest('label');
        if (shutdownLabel) shutdownLabel.style.display = 'none';
        const placeholders = {
            'dataset-path': '/workspace/datasets/my-dataset',
            'model-path': '/workspace/models/anima-base.safetensors',
            'vae-path': '/workspace/models/anima-vae.safetensors',
            'qwen-path': '/workspace/models/qwen3.safetensors',
            'output-dir': '/workspace/output',
        };
        for (const [id, value] of Object.entries(placeholders)) {
            const input = document.getElementById(id);
            if (input) input.placeholder = value;
        }
    });
})();

