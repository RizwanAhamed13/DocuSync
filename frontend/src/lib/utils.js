export function escapeHtml(t = '') {
  return t.replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[c]));
}

export function highlightText(text, q) {
  if (!q) return escapeHtml(text);
  const words = q.split(/\s+/).map(w => w.replace(/[^a-zA-Z0-9]/g, '')).filter(w => w.length > 1);
  if (!words.length) return escapeHtml(text);
  let out = escapeHtml(text);
  words.forEach(w => { out = out.replace(new RegExp(`(${w})`, 'gi'), '<mark>$1</mark>'); });
  return out;
}

export function fileIcon(filename = '') {
  const f = filename.toLowerCase();
  if (f.endsWith('.pdf'))  return 'ti-file-type-pdf';
  if (f.endsWith('.docx')) return 'ti-file-word';
  return 'ti-file-text';
}
