const BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export async function fetchDocuments(docType = null, tag = null, dimension = null, value = null) {
  const params = new URLSearchParams();
  if (docType) params.set('type', docType);
  if (tag) params.set('tag', tag);
  if (dimension) params.set('dimension', dimension);
  if (value) params.set('value', value);
  const qs = params.toString() ? '?' + params.toString() : '';
  const r = await fetch(`${BASE}/documents${qs}`);
  if (!r.ok) throw new Error('Failed to load documents');
  return r.json();
}

export async function fetchTags() {
  const r = await fetch(`${BASE}/tags`);
  if (!r.ok) throw new Error('Failed to load tags');
  return r.json();
}

export async function fetchTagsConfig() {
  const r = await fetch(`${BASE}/tags/config`);
  if (!r.ok) throw new Error('Failed to load tags config');
  return r.json();
}

export async function fetchPerspectives() {
  const r = await fetch(`${BASE}/tags/perspectives`);
  if (!r.ok) throw new Error('Failed to load perspectives');
  return r.json();
}

export async function fetchCounts() {
  const r = await fetch(`${BASE}/documents/counts`);
  if (!r.ok) throw new Error('Failed to load counts');
  return r.json();
}

export async function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch(`${BASE}/upload`, { method: 'POST', body: fd });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
    throw new Error(err.detail || 'Upload failed');
  }
  return r.json();
}

export async function searchDocuments(query, limit = 10) {
  const r = await fetch(`${BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, limit }),
  });
  if (!r.ok) throw new Error('Search failed');
  return r.json();
}

export async function deleteDocument(id) {
  const r = await fetch(`${BASE}/documents/${id}`, { method: 'DELETE' });
  if (!r.ok) throw new Error('Delete failed');
}

export async function fetchDocumentText(id) {
  const r = await fetch(`${BASE}/documents/${id}/text`);
  if (!r.ok) throw new Error('Could not retrieve document text');
  return r.json();
}

export async function fetchDocumentStatus(id) {
  const r = await fetch(`${BASE}/documents/${id}/status`);
  if (!r.ok) throw new Error('Status fetch failed');
  return r.json();
}

export async function fetchDocumentInsights(id) {
  const r = await fetch(`${BASE}/documents/${id}/insights`);
  if (!r.ok) throw new Error('Insights fetch failed');
  return r.json();
}

export function downloadUrl(id) {
  return `${BASE}/documents/${id}/download`;
}
