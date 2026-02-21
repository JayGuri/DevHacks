import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/ws': {
        target: 'http://localhost:8080',
        ws: true,
      },
      '/telemetry': {
        target: 'http://localhost:8080',
      },
      '/health': {
        target: 'http://localhost:8080',
      },
      '/metrics': {
        target: 'http://localhost:8080',
      },
      '/admin': {
        target: 'http://localhost:8080',
      },
      '/model': {
        target: 'http://localhost:8080',
      },
    },
  },
});
