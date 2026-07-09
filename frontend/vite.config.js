import { defineConfig } from 'vite';
import path from 'path';

export default defineConfig({
  root: '.',
  build: {
    outDir: path.resolve(__dirname, '../unilabos/app/web/static/dist'),
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'src/layout-app.js'),
      output: {
        entryFileNames: 'layout-app.js',
        format: 'iife',
        name: 'LayoutApp',
      },
    },
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://localhost:8002',
      '/meshes': 'http://localhost:8002',
    },
  },
});
