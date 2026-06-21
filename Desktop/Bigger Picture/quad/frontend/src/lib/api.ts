import axios from 'axios';

// Create central API client.
// In development, the API is served from the same host or port 8000.
// Let's set baseURL dynamically or default to / to support relative path proxying, or http://localhost:8000.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
});

console.log('API baseURL:', import.meta.env.VITE_API_URL || '(empty - using relative paths)');

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('quad_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('quad_token');
      localStorage.removeItem('quad_user');
      // Dispatch custom logout event if context is listening
      window.dispatchEvent(new Event('quad_logout'));
    }
    return Promise.reject(error);
  }
);

export default api;
