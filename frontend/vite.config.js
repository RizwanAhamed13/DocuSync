import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:80';
const proxyRoutes = [
  '/documents',
  '/upload',
  '/search',
  '/tags',
  '/health',
  '/reset',
  '/retag',
  '/classifier-status',
  '/migrate-to-cosine',
];

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom')) {
            return 'react-vendor';
          }
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 3000,
    proxy: Object.fromEntries(
      proxyRoutes.map(route => [route, { target: apiTarget, changeOrigin: true }]),
    ),
  },
});
