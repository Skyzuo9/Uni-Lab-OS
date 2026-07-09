import { defineConfig } from 'vite';

export default defineConfig({
    root: '.',
    server: {
        host: '0.0.0.0',
        port: 3001,
        open: '/dev-test.html',
        proxy: {
            '/api': 'http://localhost:8002',
            '/meshes': 'http://localhost:8002',
        },
    },
});