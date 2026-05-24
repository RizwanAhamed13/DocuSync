// State Management
let currentDocuments = [];
let activeSearchHits = [];
let activeTag = null;
let pollingInterval = null;

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
    setupDropzone();
    setupSearch();
    startPolling();
});

// Toast Notification Helper
function showToast(message, isSpinner = false) {
    toastMessage.textContent = message;
    
    // Remove existing spinners
    const existingSpinner = toast.querySelector(".spinner");
    if (existingSpinner) existingSpinner.remove();

    if (isSpinner) {
        const spinner = document.createElement("div");
        spinner.className = "spinner";
        toast.insertBefore(spinner, toast.firstChild);
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
    
    showToast(`Uploading ${files.length} file(s)...`, true);

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch(`${API_BASE}/upload`, {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Upload failed");
            }
            
            showToast(`Ingesting: ${file.name} in background...`, true);
        } catch (error) {
            console.error(error);
            showToast(`Error uploading ${file.name}: ${error.message}`);
        }
    }

    // Refresh lists and start aggressive polling
    fetchDocuments();
    startPolling();
}

// Fetch Documents
async function fetchDocuments() {
    try {
        const response = await fetch(`${API_BASE}/documents`);
        if (!response.ok) throw new Error("Could not load documents");
        currentDocuments = await response.json();
        renderFileList();
        updateDashboardStats();
        
        // Stop polling if no files are in processing state
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

// Fetch Tags
async function fetchTags() {
    try {
        const response = await fetch(`${API_BASE}/tags`);
        if (!response.ok) throw new Error("Could not load tags");
        const tags = await response.json();
        renderTagCloud(tags);
    } catch (error) {
        console.error(error);
    }
}

// Setup Polling for Ingestion Status
function startPolling() {
    if (pollingInterval) return;
    pollingInterval = setInterval(() => {
        fetchDocuments();
        fetchTags();
    }, 3000);
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
        fileItem.className = "file-item";
        
        let statusBadgeClass = "";
        let statusText = doc.status;
        if (doc.status === "processing") statusBadgeClass = "status-processing";
        else if (doc.status === "completed") statusBadgeClass = "status-completed";
        else if (doc.status === "failed") statusBadgeClass = "status-failed";

        const sizeKb = (doc.file_size_bytes / 1024).toFixed(1);

        fileItem.innerHTML = `
            <div class="file-info">
                <i class="fa-solid ${doc.filename.endsWith('.pdf') ? 'fa-file-pdf' : 'fa-file-word'}"></i>
                <div class="file-text" style="min-width:0;">
                    <div class="file-name" title="${doc.filename}">${doc.filename}</div>
                    <span style="font-size:10px; color:var(--text-muted);">${doc.page_count} pgs | ${sizeKb} KB</span>
                </div>
            </div>
            <div style="display:flex; align-items:center;">
                <span class="file-status-badge ${statusBadgeClass}">${statusText}</span>
                ${doc.status === 'completed' ? `
                <a class="btn-delete-file" href="/documents/${doc.id}/download" target="_blank" onclick="event.stopPropagation();" title="Open Original File" style="color: var(--text-muted); margin-left: 8px;">
                    <i class="fa-solid fa-file-arrow-down"></i>
                </a>
                ` : ''}
                <button class="btn-delete-file" onclick="deleteDocument('${doc.id}', event)" title="Delete Document">
                    <i class="fa-regular fa-trash-can"></i>
                </button>
            </div>
        `;
        
        if (doc.status === "completed") {
            fileItem.style.cursor = "pointer";
            fileItem.addEventListener("click", () => {
                viewFullDocument(doc.id, doc.filename);
            });
        }
        
        fileList.appendChild(fileItem);
    });
}

// Render Tag Cloud
function renderTagCloud(tags) {
    tagCloud.innerHTML = "";
    
    if (tags.length === 0) {
        tagCloud.innerHTML = '<p class="empty-state">No tags generated yet.</p>';
        return;
    }

    tags.forEach(tag => {
        const badge = document.createElement("div");
        badge.className = `tag-badge ${activeTag === tag.name ? 'active' : ''}`;
        badge.innerHTML = `${tag.name} <span>${tag.count}</span>`;
        
        badge.addEventListener("click", () => {
            if (activeTag === tag.name) {
                activeTag = null;
            } else {
                activeTag = tag.name;
                // Auto populate search box to help users understand they can query by tag
                searchInput.value = `tag:${tag.name} `;
                searchInput.focus();
            }
            fetchTags();
            renderFileList();
        });
        
        tagCloud.appendChild(badge);
    });
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
                <p>Try searching using different keywords or check if Ollama successfully processed the uploads.</p>
            </div>
        `;
        return;
    }

    activeSearchHits.forEach((hit, idx) => {
        const card = document.createElement("div");
        card.className = "result-card";
        card.setAttribute("data-idx", idx);
        
        const relevancy = Math.round(hit.score * 100);
        
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
    const completed = currentDocuments.filter(doc => doc.status === "completed").length;
    const processing = currentDocuments.filter(doc => doc.status === "processing").length;
    const failed = currentDocuments.filter(doc => doc.status === "failed").length;
    
    document.getElementById("statCompleted").textContent = completed;
    document.getElementById("statProcessing").textContent = processing;
    document.getElementById("statFailed").textContent = failed;
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
