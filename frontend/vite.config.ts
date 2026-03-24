import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: 'index.html',
    },
  },
  server: {
    proxy: {
      '/ws': { target: 'ws://localhost:8080', ws: true },
      '/mcp': { target: 'http://localhost:8080' },
      '/.well-known': { target: 'http://localhost:8080' },
    },
  },
});
