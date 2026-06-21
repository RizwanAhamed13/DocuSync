// State Management
let currentDocuments = [];
let activeSearchHits = [];
let activeTag = null;
let activeDocType = null;     // 'syllabus' | 'notes' | 'assign' | null
let pollingInterval = null;
let sidebarOpen = true;
let drawerOpen = true;
let currentView = 'lib';     // 'lib' | 'search'

// Per-document ingestion progress
const ingestProgress  = {};   // docId → {step, pct, detail, status}
const progressPollers = {};   // docId → intervalId

const STEP_LABELS = {
    queued:     'Queued',
    parsing:    'Parsing',
    ai_tagging: 'AI Analysis',
    chunking:   'Chunking',
    embedding:  'Embedding',
    saving:     'Saving',
    completed:  'Complete',
    failed:     'Failed',
};

const STEP_ICONS = {
    queued:     'fa-clock',
    parsing:    'fa-file-lines',
    ai_tagging: 'fa-wand-magic-sparkles',
    chunking:   'fa-scissors',
    embedding:  'fa-brain',
    saving:     'fa-database',
    completed:  'fa-circle-check',
    failed:     'fa-circle-xmark',
};

// Estimated step weights for ETA display
const STEP_ETA = {
    queued:     '~45s',
    parsing:    '~40s',
    ai_tagging: '~35s',
    chunking:   '~8s',
    embedding:  '~5s',
    saving:     '~2s',
};

// Global variable to track click handler attachment
let resultsClickHandlerAttached = false;

// DOM Elements
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const searchInput = document.getElementById("searchInput");
const searchButton = document.getElementById("searchButton");
const tagCloud = document.getElementById("tagCloud");
const fileList = document.getElementById("fileList");
const searchResults = document.getElementById("searchResults");
const resultsCount = document.getElementById("resultsCount");
const inspectorPanel = document.getElementById("inspectorPanel");
const toast = document.getElementById("toast");
const toastMessage = document.getElementById("toastMessage");

// API Config
const API_BASE = "";

// Initialize App
document.addEventListener("DOMContentLoaded", () => {
    fetchDocuments();
    fetchTags();
    fetchCounts();
    setupDropzone();
    setupSearch();
    setupPanelToggles();
    startPolling();

    // Wire the inline setRailView to also update currentView + library display
    const _origSetRailView = window.setRailView;
    window.setRailView = function(view) {
        currentView = view;
        if (_origSetRailView) _origSetRailView(view);
        // Ensure sidebar is ALWAYS open for tag browsing
        sidebarOpen = true;
        const sidebar = document.querySelector(".sidebar");
        if (sidebar) sidebar.classList.remove("collapsed");
        if (view === 'lib') renderLibraryView();
        if (view === 'tags') {
            renderTagDirectory();
        }
    };
});

// ── Panel collapse / expand ───────────────────────────────────────────────────
function setupPanelToggles() {
    // New HTML already has sb-collapse-tab and drawerToggleBtn wired — skip injection.
    // Only inject legacy compat styles for app.js-generated elements.
    if (!document.getElementById("panelToggleStyles")) {
        const style = document.createElement("style");
        style.id = "panelToggleStyles";
        style.textContent = `
            .panel-toggle-btn {
                position: fixed;
                top: 50%;
                transform: translateY(-50%);
                width: 22px;
                height: 48px;
                border: 1px solid var(--border-color, #2a2a2a);
                border-radius: 6px;
                background: var(--bg-secondary, #1a1a1a);
                color: var(--text-muted, #888);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                z-index: 100;
                transition: background 0.15s, color 0.15s, opacity 0.15s;
                opacity: 0.55;
            }
            .panel-toggle-btn:hover { opacity: 1; color: #fff; }
            .panel-toggle-left  { left: 0px; border-radius: 0 6px 6px 0; border-left: none; }
            .panel-toggle-right { right: 0px; border-radius: 6px 0 0 6px; border-right: none; }

            .sidebar { transition: width 0.25s cubic-bezier(.4,0,.2,1), opacity 0.2s; overflow: hidden; }
            .sidebar.collapsed { width: 0 !important; opacity: 0; pointer-events: none; }

            .col-inspector, #inspectorColumn {
                transition: width 0.25s cubic-bezier(.4,0,.2,1), opacity 0.2s;
                overflow: hidden;
            }
            .col-inspector.collapsed, #inspectorColumn.collapsed {
                width: 0 !important;
                opacity: 0;
                pointer-events: none;
            }

            /* Tag directory grouped sections */
            .tag-group-section { margin-bottom: 8px; }
            .tag-group-label {
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.9px;
                text-transform: uppercase;
                color: var(--text-muted, #666);
                padding: 6px 8px 3px;
                display: flex;
                align-items: center;
                gap: 5px;
            }
            .tag-group-label i { font-size: 10px; }

            /* Library type filter nav */
            .lib-type-nav { display: flex; flex-direction: column; gap: 1px; margin-bottom: 12px; }
            .lib-type-item {
                display: flex; align-items: center; gap: 8px;
                padding: 6px 8px; border-radius: 6px;
                font-size: 12px; color: var(--text-secondary, #aaa);
                cursor: pointer;
                transition: background 0.12s, color 0.12s, transform 0.15s cubic-bezier(.34,1.56,.64,1);
            }
            .lib-type-item:hover { background: var(--bg-hover, #222); transform: translateX(2px); }
            .lib-type-item.active { background: var(--bg-active, #2a2a2a); color: #fff; }
            .lib-type-item i { font-size: 14px; width: 16px; text-align: center; flex-shrink: 0; }
            .lib-type-badge { margin-left: auto; font-size: 10px; background: var(--bg-secondary, #1a1a1a); padding: 1px 6px; border-radius: 10px; }

            .lib-section-label {
                font-size: 9px; font-weight: 700; letter-spacing: 0.9px;
                text-transform: uppercase; color: var(--text-muted, #666);
                padding: 8px 8px 4px; display: block;
            }

            /* Visible collapse/expand buttons with accent color */
            .sb-collapse-tab, .drawer-toggle-btn {
                background: var(--accent, #b09060) !important;
                color: #fff !important;
                opacity: 0.8 !important;
                transition: opacity 0.2s, transform 0.2s;
            }
            .sb-collapse-tab:hover, .drawer-toggle-btn:hover {
                opacity: 1 !important;
                transform: scale(1.1) !important;
            }
        `;
        document.head.appendChild(style);
    }

    // Wire HTML collapse buttons
    setTimeout(() => {
        const sbTab = document.getElementById("sbCollapseTab");
        if (sbTab) {
            sbTab.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                sidebarOpen = !sidebarOpen;
                const sidebar = document.querySelector(".sidebar");
                if (sidebar) sidebar.classList.toggle("collapsed", !sidebarOpen);
                sbTab.innerHTML = sidebarOpen
                    ? '<i class="ti ti-chevron-left"></i>'
                    : '<i class="ti ti-chevron-right"></i>';
                sbTab.title = sidebarOpen ? "Collapse sidebar" : "Expand sidebar";
                sbTab.style.right = sidebarOpen ? 'calc(var(--sb-w) + 8px)' : '8px';
            });
        }

        const drawerBtn = document.getElementById("drawerToggleBtn");
        if (drawerBtn) {
            drawerBtn.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                drawerOpen = !drawerOpen;
                const col = document.querySelector(".col-inspector");
                if (col) col.classList.toggle("collapsed", !drawerOpen);
                drawerBtn.innerHTML = drawerOpen
                    ? '<i class="ti ti-chevron-right"></i>'
                    : '<i class="ti ti-chevron-left"></i>';
                drawerBtn.title = drawerOpen ? "Collapse inspector" : "Expand inspector";
                drawerBtn.style.left = drawerOpen ? 'calc(var(--insp-w) * -1 - 12px)' : '-12px';
            });
        }
    }, 100);
}

function toggleSidebar() {
    sidebarOpen = !sidebarOpen;
    const sidebar = document.querySelector(".sidebar");
    const btn = document.getElementById("sidebarToggleBtn");
    if (sidebar) sidebar.classList.toggle("collapsed", !sidebarOpen);
    if (btn) {
        btn.title = sidebarOpen ? "Collapse sidebar" : "Expand sidebar";
        btn.innerHTML = sidebarOpen
            ? '<i class="fa-solid fa-chevron-left"></i>'
            : '<i class="fa-solid fa-chevron-right"></i>';
        btn.style.left = sidebarOpen ? "0px" : "0px";
    }
}

function toggleDrawer() {
    drawerOpen = !drawerOpen;
    const col = document.querySelector(".col-inspector") || document.getElementById("inspectorColumn");
    const btn = document.getElementById("drawerToggleBtn");
    if (col) col.classList.toggle("collapsed", !drawerOpen);
    if (btn) {
        btn.title = drawerOpen ? "Collapse inspector" : "Expand inspector";
        btn.innerHTML = drawerOpen
            ? '<i class="fa-solid fa-chevron-right"></i>'
            : '<i class="fa-solid fa-chevron-left"></i>';
    }
}

// Toast Notification Helper
function showToast(message, isSpinner = false) {
    toastMessage.textContent = message;

    // Find the inner container (new layout wraps in .toast-inner)
    const inner = toast.querySelector(".toast-inner") || toast;

    // Remove existing spinners/icons
    inner.querySelectorAll(".spinner, .toast-icon").forEach(el => el.remove());

    if (isSpinner) {
        const spinner = document.createElement("div");
        spinner.className = "spinner";
        inner.insertBefore(spinner, inner.firstChild);
    }

    toast.classList.remove("hidden");
    if (!isSpinner) {
        setTimeout(() => {
            toast.classList.add("hidden");
        }, 3000);
    }
}

function hideToast() {
    toast.classList.add("hidden");
}

// Setup Drag & Drop Upload
function setupDropzone() {
    dropzone.addEventListener("click", () => fileInput.click());
    
    fileInput.addEventListener("change", (e) => {
        handleFilesUpload(e.target.files);
    });

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        handleFilesUpload(e.dataTransfer.files);
    });
}

// Upload Files Handler
async function handleFilesUpload(files) {
    if (files.length === 0) return;

    const plural = files.length > 1 ? `${files.length} files` : files[0].name;
    showToast(`Uploading ${plural}…`, true);

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const formData = new FormData();
        formData.append("file", file);

        try {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 60000);
            const response = await fetch(`${API_BASE}/upload`, {
                method: "POST",
                body: formData,
                signal: controller.signal
            });
            clearTimeout(timer);

            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
                throw new Error(err.detail || "Upload failed");
            }

            const responseData = await response.json();
            const docId = responseData.document_id;

            // Kick off granular progress polling immediately
            if (docId) {
                ingestProgress[docId] = { step: "queued", pct: 0, detail: "Starting up…", status: "processing" };
                startProgressPolling(docId);
            }

            showToast(`Processing: ${file.name}`, true);
        } catch (error) {
            console.error(error);
            showToast(`Error uploading ${file.name}: ${error.message}`);
        }
    }

    // Refresh lists and keep background list polling active
    fetchDocuments();
    startPolling();
}

// Fetch Documents (supports active doc_type and tag filters)
async function fetchDocuments() {
    try {
        const params = new URLSearchParams();
        if (activeDocType) params.set("type", activeDocType);
        if (activeTag)     params.set("tag",  activeTag);
        const qs = params.toString() ? "?" + params.toString() : "";
        const response = await fetch(`${API_BASE}/documents${qs}`);
        if (!response.ok) throw new Error("Could not load documents");
        currentDocuments = await response.json();
        renderFileList();
        updateDashboardStats();
        if (currentView === 'lib') renderLibraryView();

        const anyProcessing = currentDocuments.some(doc => doc.status === "processing");
        if (!anyProcessing && pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
            hideToast();
        }
    } catch (error) {
        console.error(error);
    }
}

// Fetch and render grouped tags
async function fetchTags() {
    try {
        const response = await fetch(`${API_BASE}/tags`);
        if (!response.ok) throw new Error("Could not load tags");
        const data = await response.json();
        // New API returns {flat, grouped}; old API returns array
        if (Array.isArray(data)) {
            renderTagCloud(data, null);
        } else {
            currentTagsGrouped = data.grouped || {};
            renderTagCloud(data.flat, data.grouped);
            // Re-render tag directory if in tags view
            if (currentView === 'tags') renderTagDirectory();
        }
    } catch (error) {
        console.error(error);
    }
}

// Fetch sidebar type-counts and update badges
async function fetchCounts() {
    try {
        const r = await fetch(`${API_BASE}/documents/counts`);
        if (!r.ok) return;
        const counts = await r.json();
        const map = { all: "statAll", syllabus: "statSyllabus", notes: "statNotes", assign: "statAssign" };
        for (const [key, elId] of Object.entries(map)) {
            const el = document.getElementById(elId);
            if (el) el.textContent = counts[key] ?? 0;
        }
        // Also update existing dashboard counters
        const c = document.getElementById("statCompleted");
        const p = document.getElementById("statProcessing");
        const f = document.getElementById("statFailed");
        if (c) c.textContent = counts.all ?? 0;
        if (p) p.textContent = counts.processing ?? 0;
        if (f) f.textContent = counts.failed ?? 0;
    } catch (_) {}
}

// Setup Polling for Ingestion Status
function startPolling() {
    if (pollingInterval) return;
    pollingInterval = setInterval(() => {
        fetchDocuments();
        fetchTags();
        fetchCounts();
    }, 5000);
}

// ── Per-document granular progress polling ────────────────────────
function startProgressPolling(docId) {
    if (progressPollers[docId]) return;
    progressPollers[docId] = setInterval(async () => {
        try {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 8000);
            const resp = await fetch(`/documents/${docId}/status`, { signal: controller.signal });
            clearTimeout(timer);
            if (!resp.ok) return;
            const data = await resp.json();

            ingestProgress[docId] = data;
            updateProgressBarDOM(docId, data);

            if (data.status !== 'processing') {
                stopProgressPolling(docId);
                delete ingestProgress[docId];
                // Refresh the full list + tags once done
                await fetchDocuments();
                await fetchTags();
            }
        } catch (_) { /* ignore network blips and aborts */ }
    }, 2500);
}

function stopProgressPolling(docId) {
    if (progressPollers[docId]) {
        clearInterval(progressPollers[docId]);
        delete progressPollers[docId];
    }
}

function updateProgressBarDOM(docId, data) {
    const bar    = document.querySelector(`[data-pb="${docId}"]`);
    const label  = document.querySelector(`[data-pl="${docId}"]`);
    const pct    = document.querySelector(`[data-pp="${docId}"]`);
    const detail = document.querySelector(`[data-pd="${docId}"]`);
    if (!bar) return; // element removed by a re-render — poller will pick it up next tick
    bar.style.width      = `${Math.max(data.pct, 4)}%`;
    if (label) label.innerHTML   = `<i class="fa-solid ${STEP_ICONS[data.step] || 'fa-gear'}"></i> ${STEP_LABELS[data.step] || data.step}`;
    if (pct)   pct.textContent   = `${data.pct}%`;
    if (detail)detail.textContent= data.detail || '';
}

// Render File List in Sidebar
function renderFileList() {
    fileList.innerHTML = "";
    
    if (currentDocuments.length === 0) {
        fileList.innerHTML = '<p class="empty-state">No documents uploaded.</p>';
        return;
    }

    // Filter list if active tag is set
    const filteredDocs = activeTag 
        ? currentDocuments.filter(doc => doc.tags.includes(activeTag))
        : currentDocuments;

    filteredDocs.forEach(doc => {
        const fileItem = document.createElement("div");
        const fileIcon = doc.filename.toLowerCase().endsWith('.pdf') ? 'fa-file-pdf'
                       : doc.filename.toLowerCase().endsWith('.docx') ? 'fa-file-word'
                       : 'fa-file-lines';

        if (doc.status === "processing") {
            // ── Active ingestion: show animated progress bar ──────────
            startProgressPolling(doc.id);
            const prog   = ingestProgress[doc.id] || {};
            const pct    = prog.pct    || 0;
            const step   = prog.step   || 'queued';
            const detail = prog.detail || 'Waiting to start…';

            fileItem.className = "file-item file-item-processing";
            fileItem.innerHTML = `
                <div class="file-header-row">
                    <div class="file-info">
                        <i class="fa-solid ${fileIcon} file-icon-pulse" style="color:var(--status-pending);"></i>
                        <div class="file-text" style="min-width:0;">
                            <div class="file-name" title="${doc.filename}">${doc.filename}</div>
                            <span style="font-size:10px; color:var(--text-muted);">Processing · ETA ${STEP_ETA[step] || '…'}</span>
                        </div>
                    </div>
                    <button class="btn-delete-file" onclick="deleteDocument('${doc.id}', event)" title="Cancel & Delete">
                        <i class="fa-regular fa-trash-can"></i>
                    </button>
                </div>
                <div class="ingest-progress-wrap">
                    <div class="progress-header-row">
                        <span class="progress-step-label" data-pl="${doc.id}">
                            <i class="fa-solid ${STEP_ICONS[step] || 'fa-gear'}"></i>
                            ${STEP_LABELS[step] || step}
                        </span>
                        <span class="progress-pct-badge" data-pp="${doc.id}">${pct}%</span>
                    </div>
                    <div class="progress-bar-track">
                        <div class="progress-bar-fill" data-pb="${doc.id}" style="width:${Math.max(pct,4)}%"></div>
                    </div>
                    <div class="progress-detail-text" data-pd="${doc.id}">${detail}</div>
                </div>
            `;

        } else if (doc.status === "failed") {
            // ── Failed state ─────────────────────────────────────────
            fileItem.className = "file-item";
            const errShort = doc.error_message
                ? doc.error_message.slice(0, 60) + (doc.error_message.length > 60 ? '…' : '')
                : 'Unknown error';
            fileItem.innerHTML = `
                <div class="file-info" style="width:100%; flex-direction:column; gap:4px; align-items:flex-start;">
                    <div style="display:flex; align-items:center; justify-content:space-between; width:100%;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <i class="fa-solid ${fileIcon}" style="color:var(--status-failed);"></i>
                            <div class="file-name" title="${doc.filename}">${doc.filename}</div>
                        </div>
                        <div style="display:flex; align-items:center; gap:4px;">
                            <span class="file-status-badge status-failed">Failed</span>
                            <button class="btn-delete-file" onclick="deleteDocument('${doc.id}', event)" title="Remove">
                                <i class="fa-regular fa-trash-can"></i>
                            </button>
                        </div>
                    </div>
                    <span style="font-size:10px; color:var(--status-failed); padding-left:24px;">${errShort}</span>
                </div>
            `;

        } else {
            // ── Completed state ───────────────────────────────────────
            const sizeKb = (doc.file_size_bytes / 1024).toFixed(1);
            // One-line summary: strip newlines, cap at 80 chars
            const rawSummary = (doc.summary || "").replace(/\s+/g, " ").trim();
            const shortSummary = rawSummary.length > 80
                ? rawSummary.slice(0, 78) + "…"
                : rawSummary;

            fileItem.className = "file-item";
            fileItem.style.cursor = "pointer";
            fileItem.innerHTML = `
                <div class="file-info" style="min-width:0; flex:1;">
                    <i class="fa-solid ${fileIcon}" style="color:var(--accent-blue); flex-shrink:0;"></i>
                    <div class="file-text" style="min-width:0;">
                        <div class="file-name" title="${doc.filename}">${doc.filename}</div>
                        ${shortSummary
                            ? `<span style="font-size:10px; color:var(--text-muted); display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${rawSummary}">${shortSummary}</span>`
                            : `<span style="font-size:10px; color:var(--text-muted);">${doc.page_count} pgs · ${sizeKb} KB</span>`
                        }
                    </div>
                </div>
                <div style="display:flex; align-items:center; gap:4px; flex-shrink:0;">
                    <a class="btn-delete-file" href="/documents/${doc.id}/download" target="_blank"
                       onclick="event.stopPropagation();" title="Download original"
                       style="color:var(--text-muted);">
                        <i class="fa-solid fa-file-arrow-down"></i>
                    </a>
                    <button class="btn-delete-file" onclick="deleteDocument('${doc.id}', event)" title="Delete">
                        <i class="fa-regular fa-trash-can"></i>
                    </button>
                </div>
            `;
            fileItem.addEventListener("click", () => viewFullDocument(doc.id, doc.filename));
        }

        fileList.appendChild(fileItem);
    });
}

// Render Tag Cloud — supports both flat array and grouped object
function renderTagCloud(flatTags, grouped) {
    tagCloud.innerHTML = "";

    // ── Library type filter nav (inject above tag cloud once) ──────────────
    let libNav = document.getElementById("libTypeNav");
    if (!libNav) {
        libNav = document.createElement("div");
        libNav.id = "libTypeNav";
        libNav.className = "lib-type-nav";
        tagCloud.parentElement.insertBefore(libNav, tagCloud);
    }
    // Hide library nav in Tags view, show in Library view
    libNav.style.display = currentView === 'tags' ? 'none' : 'flex';
    libNav.style.flexDirection = 'column';
    libNav.innerHTML = `
        <span class="lib-section-label">Library</span>
        <div class="lib-type-item ${!activeDocType ? 'active' : ''}" onclick="setDocType(null,this)">
            <i class="fa-solid fa-layer-group"></i> All documents
            <span class="lib-type-badge" id="statAll">—</span>
        </div>
        <div class="lib-type-item ${activeDocType==='syllabus' ? 'active' : ''}" onclick="setDocType('syllabus',this)">
            <i class="fa-solid fa-book-open"></i> Syllabi
            <span class="lib-type-badge" id="statSyllabus">—</span>
        </div>
        <div class="lib-type-item ${activeDocType==='notes' ? 'active' : ''}" onclick="setDocType('notes',this)">
            <i class="fa-solid fa-file-lines"></i> Lecture Notes
            <span class="lib-type-badge" id="statNotes">—</span>
        </div>
        <div class="lib-type-item ${activeDocType==='assign' ? 'active' : ''}" onclick="setDocType('assign',this)">
            <i class="fa-solid fa-clipboard-list"></i> Assignments
            <span class="lib-type-badge" id="statAssign">—</span>
        </div>
    `;
    fetchCounts();

    if (!flatTags || flatTags.length === 0) {
        tagCloud.innerHTML = '<p class="empty-state">No tags yet</p>';
        return;
    }

    // ── Build grouped structure from flat array if grouped is empty ──────────
    let finalGrouped = grouped;
    if (!grouped || typeof grouped !== "object" || Object.keys(grouped).length === 0) {
        finalGrouped = { subject: [], doc_type: [], level: [], term: [] };
        const DOC_TYPE_SET = new Set(["Syllabus", "Course Syllabus", "Lecture Notes", "Lab Report", "Lab Notes", "Assignment", "Final Exam", "Midterm Exam", "Exam / Quiz", "Question Bank", "Homework", "Project"]);
        const LEVEL_WORDS = new Set(["Graduate","Doctoral","Undergraduate","Upper","Sophomore","Introductory","Advanced"]);
        const TERM_RE = /^(Spring|Fall|Summer|Winter)\s+\d{4}$/i;

        flatTags.forEach(tag => {
            const cat = tag.category || 'subject';
            if (finalGrouped[cat]) {
                finalGrouped[cat].push(tag);
            }
        });
    }

    // ── Grouped tag directory ──────────────────────────────────────────────
    const GROUP_META = {
        subject:  { icon: "fa-atom",       label: "Subject" },
        doc_type: { icon: "fa-file-check", label: "Document type" },
        level:    { icon: "fa-graduation-cap", label: "Level" },
        term:     { icon: "fa-calendar",  label: "Term" },
    };

    let hasAnyTags = false;
    for (const [key, meta] of Object.entries(GROUP_META)) {
        const items = finalGrouped[key] || [];
        if (items.length === 0) continue;
        hasAnyTags = true;

        const section = document.createElement("div");
        section.className = "tag-group-section";

        // Add section header
        const headerDiv = document.createElement("div");
        headerDiv.className = "tag-group-label";
        headerDiv.innerHTML = `<i class="fa-solid ${meta.icon}"></i> ${meta.label}`;
        headerDiv.style.display = 'flex';
        headerDiv.style.visibility = 'visible';
        section.appendChild(headerDiv);

        // Add tags
        items.forEach(tag => {
            const badge = document.createElement("div");
            badge.className = `tag-badge ${activeTag === tag.name ? 'active' : ''}`;
            badge.innerHTML = `${tag.name} <span>${tag.count}</span>`;
            badge.style.display = 'flex';
            badge.style.visibility = 'visible';
            badge.addEventListener("click", () => selectTag(tag.name));
            section.appendChild(badge);
        });
        tagCloud.appendChild(section);
    }

    if (!hasAnyTags) {
        tagCloud.innerHTML = '<p class="empty-state">No tags yet</p>';
    }
}

// ── Library view: render docs as cards in main results panel ──────────────
function renderLibraryView() {
    const label = activeTag
        ? `Tagged: ${activeTag}`
        : activeDocType === 'syllabus' ? 'Syllabi'
        : activeDocType === 'notes'    ? 'Lecture Notes'
        : activeDocType === 'assign'   ? 'Assignments'
        : 'All Documents';

    // Filter: API already filters by type/tag, but also filter client-side for tag display
    let completed = currentDocuments.filter(d => d.status === 'completed');
    if (activeTag) {
        completed = completed.filter(doc => (doc.tags || []).includes(activeTag));
    }
    resultsCount.textContent = `${completed.length} docs`;

    if (completed.length === 0) {
        searchResults.innerHTML = `
            <div class="empty-card">
                <i class="fa-solid fa-inbox empty-icon"></i>
                <p class="empty-title">No documents in ${label}</p>
                <p class="empty-sub">Upload a PDF, DOCX or TXT to get started — AI tagging runs automatically.</p>
            </div>`;
        return;
    }

    // Build HTML string once instead of creating DOM elements
    let htmlContent = '';
    completed.forEach((doc, idx) => {
        const fileIcon = doc.filename.toLowerCase().endsWith('.pdf') ? 'fa-file-pdf'
                       : doc.filename.toLowerCase().endsWith('.docx') ? 'fa-file-word'
                       : 'fa-file-lines';

        const tagsHtml = (doc.tags || []).slice(0, 4)
            .map(t => `<span class="result-tag-badge">#${t}</span>`).join(" ");

        const summary = (doc.summary || "No summary available.").replace(/\s+/g, " ").trim();
        const sizeKb = doc.file_size_bytes ? (doc.file_size_bytes / 1024).toFixed(1) + ' KB' : '';
        const pages = doc.page_count ? `${doc.page_count} pg${doc.page_count !== 1 ? 's' : ''}` : '';
        const meta = [pages, sizeKb].filter(Boolean).join(' · ');

        const docTypeLabel = doc.doc_type && doc.doc_type !== 'other'
            ? `<span class="result-score" style="background:var(--blue-dim);color:var(--blue);">${doc.doc_type}</span>`
            : '';

        htmlContent += `
            <div class="result-card" data-doc-id="${doc.id}">
                <div class="result-header">
                    <div class="result-doc-name">
                        <i class="fa-solid ${fileIcon}"></i>
                        <span>${doc.filename}</span>
                    </div>
                    <div class="result-meta">
                        ${docTypeLabel}
                        <span class="result-page">${meta}</span>
                    </div>
                </div>
                <div class="result-snippet">${summary}</div>
                <div class="result-tags">${tagsHtml}</div>
            </div>`;
    });

    searchResults.innerHTML = htmlContent;

    // Attach click handler once using event delegation
    if (!resultsClickHandlerAttached) {
        searchResults.addEventListener("click", (e) => {
            const card = e.target.closest(".result-card");
            if (!card) return;

            document.querySelectorAll(".result-card").forEach(c => c.classList.remove("active"));
            card.classList.add("active");

            const docId = card.getAttribute("data-doc-id");
            const doc = currentDocuments.find(d => d.id === docId);
            if (doc) renderDocInspector(doc);
        });
        resultsClickHandlerAttached = true;
    }
}

// ── Inspector for library doc view ────────────────────────────────────────
function renderDocInspector(doc) {
    const fileIcon = doc.filename.toLowerCase().endsWith('.pdf') ? 'fa-file-pdf'
                   : doc.filename.toLowerCase().endsWith('.docx') ? 'fa-file-word'
                   : 'fa-file-lines';

    const tagsHtml = (doc.tags || []).map(t =>
        `<span class="tag-badge" style="cursor:default;">#${t}</span>`).join(" ");

    const findingsHtml = (doc.key_findings || []).length > 0
        ? doc.key_findings.map(f => `<li>${escapeHtml(f)}</li>`).join("")
        : '<li style="color:var(--ink4)">No key findings extracted.</li>';

    const dates = (doc.entities?.Dates || []);
    const datesHtml = dates.length > 0
        ? dates.map(d => `<span class="entity-badge">${d}</span>`).join("")
        : '<span style="color:var(--ink4);font-size:11px">None detected</span>';

    inspectorPanel.innerHTML = `
        <div class="inspector-title">
            <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0;">
                <i class="fa-solid ${fileIcon}"></i>
                <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${doc.filename}</span>
            </div>
            <div style="display:flex;gap:6px;flex-shrink:0;">
                <a class="btn btn-primary" href="/documents/${doc.id}/download" target="_blank"
                   style="font-size:11px;padding:4px 10px;text-decoration:none;">
                    <i class="fa-solid fa-download"></i> Download
                </a>
                <button class="btn btn-primary" style="font-size:11px;padding:4px 10px;"
                    onclick="viewFullDocument('${doc.id}','${doc.filename.replace(/'/g,"\\'")}')">
                    <i class="fa-solid fa-expand"></i> View
                </button>
            </div>
        </div>

        <div class="inspector-section">
            <h4><i class="fa-solid fa-wand-magic-sparkles"></i> AI Summary</h4>
            <p class="inspector-summary">${escapeHtml(doc.summary || 'No summary available.')}</p>
        </div>

        <div class="inspector-section">
            <h4><i class="fa-solid fa-circle-check"></i> Key Findings</h4>
            <ul class="findings-list">${findingsHtml}</ul>
        </div>

        <div class="inspector-section">
            <h4><i class="fa-solid fa-calendar"></i> Dates Mentioned</h4>
            <div class="entity-list">${datesHtml}</div>
        </div>

        <div class="inspector-section">
            <h4><i class="fa-solid fa-tags"></i> Tags</h4>
            <div class="inspector-tags">${tagsHtml}</div>
        </div>
    `;
}

// ── Tag directory view: show all tags organized by category ──────────────────
function renderTagDirectory() {
    resultsCount.textContent = "Tag Directory";

    if (!Object.keys(currentTagsGrouped).length) {
        searchResults.innerHTML = `
            <div class="empty-card">
                <i class="fa-solid fa-tags empty-icon"></i>
                <p class="empty-title">No tags yet</p>
                <p class="empty-sub">Upload documents to generate tags automatically.</p>
            </div>`;
        return;
    }

    const GROUP_META = {
        subject:  { icon: "fa-atom",       label: "Subject" },
        doc_type: { icon: "fa-file-check", label: "Document Type" },
        level:    { icon: "fa-graduation-cap", label: "Level" },
        term:     { icon: "fa-calendar",  label: "Term" },
    };

    let htmlContent = '';

    for (const [key, meta] of Object.entries(GROUP_META)) {
        const items = currentTagsGrouped[key] || [];
        if (items.length === 0) continue;

        htmlContent += `
            <div style="margin-bottom: 28px;">
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px; padding-bottom:8px; border-bottom:1px solid var(--border2);">
                    <i class="fa-solid ${meta.icon}" style="font-size:16px; color:var(--accent);"></i>
                    <h3 style="font-size:14px; font-weight:600; color:var(--ink); margin:0;">${meta.label}</h3>
                </div>
                <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:10px;">`;

        items.forEach(tag => {
            htmlContent += `
                <div style="padding:10px 12px; border:1px solid var(--border2); border-radius:8px; cursor:pointer; transition:all 0.1s; background:var(--surface2);"
                     onclick="selectTag('${tag.name}'); return false;"
                     onmouseover="this.style.borderColor='var(--accent)'; this.style.background='var(--accent-dim)';"
                     onmouseout="this.style.borderColor='var(--border2)'; this.style.background='var(--surface2)';">
                    <div style="font-size:12px; font-weight:500; color:var(--ink2); margin-bottom:4px;">${tag.name}</div>
                    <div style="font-size:10px; color:var(--ink4); background:var(--bg); padding:2px 6px; border-radius:4px; display:inline-block;">${tag.count} doc${tag.count !== 1 ? 's' : ''}</div>
                </div>`;
        });

        htmlContent += `</div></div>`;
    }

    searchResults.innerHTML = htmlContent;
}

// Store current tags for tag directory view
let currentTagsGrouped = {};

function selectTag(name) {
    activeTag = activeTag === name ? null : name;
    currentView = 'lib';
    sidebarOpen = true;
    const sidebar = document.querySelector(".sidebar");
    if (sidebar) sidebar.classList.remove("collapsed");
    fetchDocuments();
    fetchTags();
}

function setDocType(type, el) {
    activeDocType = type;
    activeTag = null;
    currentView = 'lib';
    sidebarOpen = true;  // Ensure sidebar stays open when selecting doc type
    const sidebar = document.querySelector(".sidebar");
    if (sidebar) sidebar.classList.remove("collapsed");
    fetchDocuments();
    fetchTags();
}

// Setup Search Handlers
function setupSearch() {
    searchButton.addEventListener("click", executeSearch);
    searchInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") executeSearch();
    });
}

// Execute Hybrid Search
async function executeSearch() {
    const rawQuery = searchInput.value.trim();
    if (!rawQuery) return;

    // Check if query is looking for tag filtering
    let tagQuery = null;
    let cleanQuery = rawQuery;
    if (rawQuery.startsWith("tag:")) {
        const parts = rawQuery.split(" ");
        tagQuery = parts[0].replace("tag:", "");
        cleanQuery = parts.slice(1).join(" ");
    }

    searchResults.innerHTML = '<div class="welcome-card"><i class="fa-solid fa-spinner fa-spin welcome-icon"></i><h3>Searching vector store...</h3></div>';
    resultsCount.textContent = "Searching...";

    try {
        const response = await fetch(`${API_BASE}/search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: cleanQuery || tagQuery, limit: 10 })
        });

        if (!response.ok) throw new Error("Search request failed");
        
        activeSearchHits = await response.json();
        
        // Filter active hits locally if a tag filter was requested in query
        if (tagQuery) {
            activeSearchHits = activeSearchHits.filter(hit => hit.tags.includes(tagQuery));
        }

        renderSearchResults(cleanQuery || tagQuery);
    } catch (error) {
        console.error(error);
        searchResults.innerHTML = `<div class="welcome-card"><i class="fa-solid fa-triangle-exclamation welcome-icon" style="color:var(--status-failed);"></i><h3>Search Failed</h3><p>${error.message}</p></div>`;
        resultsCount.textContent = "0 Results";
    }
}

// Render Search Results Column
function renderSearchResults(highlightTerm) {
    searchResults.innerHTML = "";
    resultsCount.textContent = `${activeSearchHits.length} Results`;
    
    if (activeSearchHits.length === 0) {
        searchResults.innerHTML = `
            <div class="welcome-card">
                <i class="fa-solid fa-face-frown welcome-icon"></i>
                <h3>No context matches found</h3>
                <p>Try different keywords or upload more documents to expand your library.</p>
            </div>
        `;
        return;
    }

    activeSearchHits.forEach((hit, idx) => {
        const card = document.createElement("div");
        card.className = "result-card";
        card.setAttribute("data-idx", idx);
        
        // Use cosine similarity (0–1) for display — RRF score is a tiny fusion
        // number (~0.03) that looks broken when multiplied by 100.
        const relevancy = Math.round(hit.similarity * 100);
        
        // Highlight logic
        const highlightedText = highlightText(hit.text, highlightTerm);
        
        const tagsHtml = hit.tags.slice(0, 3).map(t => `<span class="result-tag-badge">#${t}</span>`).join(" ");

        card.innerHTML = `
            <div class="result-header">
                <div class="result-doc-name">
                    <i class="fa-solid fa-file-lines"></i>
                    <span>${hit.filename}</span>
                </div>
                <div class="result-meta">
                    <span class="result-score">${relevancy}% Match</span>
                    <span class="result-page">Page ${hit.page}</span>
                </div>
            </div>
            <div class="result-snippet">"...${highlightedText}..."</div>
            <div class="result-tags">${tagsHtml}</div>
        `;
        
        card.addEventListener("click", () => selectSearchHit(idx, card));
        searchResults.appendChild(card);
    });
}

// Text Highlighter
function highlightText(text, searchWord) {
    if (!searchWord) return escapeHtml(text);
    
    // Split query by spaces and clean up special chars to create query regex
    const words = searchWord.split(/\s+/).map(w => w.replace(/[^a-zA-Z0-9]/g, "")).filter(w => w.length > 1);
    if (words.length === 0) return escapeHtml(text);

    let escapedText = escapeHtml(text);
    
    words.forEach(word => {
        const regex = new RegExp(`(${word})`, 'gi');
        escapedText = escapedText.replace(regex, "<mark>$1</mark>");
    });
    
    return escapedText;
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

// Select result hit and inspect document details
function selectSearchHit(idx, cardElement) {
    // Clear active card highlight
    document.querySelectorAll(".result-card").forEach(c => c.classList.remove("active"));
    cardElement.classList.add("active");
    
    const hit = activeSearchHits[idx];
    renderInspectorPanel(hit);
}

// Render Document Inspector Column
function renderInspectorPanel(hit) {
    inspectorPanel.innerHTML = "";
    
    const findingsListHtml = hit.key_findings.map(f => `<li>${f}</li>`).join("");
    
    const companiesHtml = hit.entities.Companies && hit.entities.Companies.length > 0 
        ? hit.entities.Companies.map(c => `<span class="entity-badge">${c}</span>`).join("")
        : '<span style="color:var(--text-muted); font-size:11px;">None detected</span>';
        
    const datesHtml = hit.entities.Dates && hit.entities.Dates.length > 0
        ? hit.entities.Dates.map(d => `<span class="entity-badge">${d}</span>`).join("")
        : '<span style="color:var(--text-muted); font-size:11px;">None detected</span>';

    const projectNamesHtml = hit.entities.Project_Names && hit.entities.Project_Names.length > 0
        ? hit.entities.Project_Names.map(p => `<span class="entity-badge">${p}</span>`).join("")
        : '<span style="color:var(--text-muted); font-size:11px;">None detected</span>';

    const tagsHtml = hit.tags.map(t => `<span class="tag-badge" style="cursor:default;">#${t}</span>`).join(" ");

    inspectorPanel.innerHTML = `
        <div class="inspector-title" style="justify-content: space-between; display: flex; width: 100%;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <i class="fa-solid fa-file-contract"></i>
                <span>${hit.filename} (Page ${hit.page})</span>
            </div>
            <button class="btn btn-primary" style="font-size: 11px; padding: 4px 10px;" onclick="viewFullDocument('${hit.document_id}', '${hit.filename}')">
                <i class="fa-solid fa-expand" style="margin-right: 4px;"></i> View Full File
            </button>
        </div>
        
        <div class="inspector-section">
            <h4><i class="fa-solid fa-quote-left"></i> Matching Passage Context</h4>
            <div class="chunk-full-text-box">
                ${highlightText(hit.text, searchInput.value)}
            </div>
        </div>

        <div class="inspector-section">
            <h4><i class="fa-solid fa-wand-magic-sparkles"></i> AI Executive Summary</h4>
            <p class="inspector-summary">${hit.summary}</p>
        </div>

        <div class="inspector-section">
            <h4><i class="fa-solid fa-circle-check"></i> Key Findings</h4>
            <ul class="findings-list">
                ${findingsListHtml}
            </ul>
        </div>

        <div class="inspector-section">
            <h4><i class="fa-solid fa-diagram-project"></i> Extracted Entities</h4>
            <div class="entities-grid">
                <div class="entity-group">
                    <h5>Companies / Organizations</h5>
                    <div class="entity-list">${companiesHtml}</div>
                </div>
                <div class="entity-group">
                    <h5>Relevant Dates</h5>
                    <div class="entity-list">${datesHtml}</div>
                </div>
                <div class="entity-group" style="grid-column: span 2;">
                    <h5>Project Names / CodeWords</h5>
                    <div class="entity-list">${projectNamesHtml}</div>
                </div>
            </div>
        </div>

        <div class="inspector-section">
            <h4><i class="fa-solid fa-tags"></i> Document Tags</h4>
            <div class="inspector-tags">
                ${tagsHtml}
            </div>
        </div>
    `;
}

// Delete Document Handler
async function deleteDocument(docId, event) {
    event.stopPropagation();
    if (!confirm("Are you sure you want to delete this document and clear its index?")) return;
    
    showToast("Deleting document...", true);
    
    try {
        const response = await fetch(`${API_BASE}/documents/${docId}`, {
            method: "DELETE"
        });

        if (!response.ok) throw new Error("Delete request failed");
        
        showToast("Successfully deleted.");
        
        // Reset Inspector if it was showing deleted doc
        const isShowingDeleted = activeSearchHits.some((hit) => hit.document_id === docId);
        if (isShowingDeleted) {
            inspectorPanel.innerHTML = `
                <div class="empty-inspector">
                    <i class="fa-solid fa-eye empty-icon"></i>
                    <h3>Select a search result to inspect details</h3>
                    <p>Click on any text match card on the left to read context, summaries, and extracted key takeaways.</p>
                </div>
            `;
            searchResults.innerHTML = `
                <div class="welcome-card">
                    <i class="fa-solid fa-arrow-pointer welcome-icon"></i>
                    <h3>Upload a document and start searching</h3>
                    <p>DocuSync extracts your text, tags topics using local AI, and indexing into a semantic vector store.</p>
                </div>
            `;
            resultsCount.textContent = "0 Results";
            activeSearchHits = [];
        }

        // Refresh lists
        fetchDocuments();
        fetchTags();
    } catch (error) {
        console.error(error);
        showToast(`Delete failed: ${error.message}`);
    }
}

// Update Brand Dashboard Stats Counters
function updateDashboardStats() {
    fetchCounts();
}

// Full Document Viewer
async function viewFullDocument(docId, filename) {
    const modal = document.getElementById("fullDocModal");
    const modalTitle = document.getElementById("modalTitle");
    const modalFullText = document.getElementById("modalFullText");
    
    modalFullText.innerHTML = '<div style="display:flex; justify-content:center; align-items:center; height:200px;"><i class="fa-solid fa-spinner fa-spin" style="font-size:24px; color:var(--accent-blue)"></i></div>';
    modalTitle.innerHTML = `<i class="fa-solid fa-file-lines"></i> Full Document: ${filename}`;
    document.getElementById("modalOriginalLink").setAttribute("href", `/documents/${docId}/download`);
    
    modal.classList.remove("hidden");
    
    try {
        const response = await fetch(`/documents/${docId}/text`);
        if (!response.ok) throw new Error("Could not retrieve document text.");
        
        const data = await response.json();
        
        // Highlight terms in full text using query input
        const highlighted = highlightText(data.text, searchInput.value);
        modalFullText.innerHTML = highlighted;
    } catch (error) {
        modalFullText.innerHTML = `<div style="color:var(--status-failed); font-weight:500;">Failed to load file content: ${error.message}</div>`;
    }
}

function closeModal() {
    document.getElementById("fullDocModal").classList.add("hidden");
}

// Close Modal when clicking outside the content area
window.addEventListener("click", (e) => {
    const modal = document.getElementById("fullDocModal");
    if (e.target === modal) {
        closeModal();
    }
});
