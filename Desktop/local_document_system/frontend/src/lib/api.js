const BASE_URL = '';

/**
 * Robust fetch wrapper for DocuSync.
 */
export const apiFetch = async (endpoint, options = {}) => {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  const config = {
    ...options,
    headers,
  };

  if (options.body instanceof FormData) {
    delete config.headers['Content-Type'];
  }

  if (!endpoint) {
    throw new Error('API endpoint is undefined.');
  }

  const path = endpoint.startsWith('http') ? endpoint : (endpoint.startsWith('/') ? endpoint : `/${endpoint}`);
  const url = endpoint.startsWith('http') ? endpoint : `${BASE_URL}${path}`;

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || response.statusText || 'Request failed');
    }

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json();
    }

    // Default to Blob for all other types (PDF, DOCX download)
    return await response.blob();
  } catch (error) {
    console.error('API call failed:', error);
    throw error;
  }
};

export const endpoints = {
  documents: {
    all: '/documents',
    upload: '/upload',
    download: (id) => `/documents/${id}/download`,
    delete: (id) => `/documents/${id}`,
    text: (id) => `/documents/${id}/text`,
    status: (id) => `/documents/${id}/status`,
    search: '/search',
    tags: '/tags',
    reset: '/reset',
    retag: '/retag',
    health: '/health',
  }
};
