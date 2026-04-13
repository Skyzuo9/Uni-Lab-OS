import { defineConfig } from 'vite';

export default defineConfig({
    root: '.',
    server: {
        port: 3000,
        open: '/dev-test.html',
        proxy: {
            '/api': 'http://localhost:8002',
            '/meshes': 'http://localhost:8002',
        },
    },
});
