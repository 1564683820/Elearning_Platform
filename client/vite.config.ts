import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/Elearning/',
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-charts': ['recharts'],
          'vendor-markdown': ['react-markdown', 'remark-gfm'],
        },
      },
    },
  },
  server: {
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/Elearning/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/Elearning(?=\/api)/, ''),
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,  // WebSocket 支持
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            const url = req.url || '';
            if (url.includes('generate-sse')) {
              console.log('[Vite Proxy] SSE 请求转发:', req.method, url);
              proxyReq.setHeader('Connection', 'keep-alive');
              proxyReq.setHeader('Accept', 'text/event-stream');
            }
          });
          proxy.on('proxyRes', (proxyRes, req) => {
            if ((req.url || '').includes('generate-sse')) {
              console.log('[Vite Proxy] SSE 响应状态:', proxyRes.statusCode);
              proxyRes.headers['cache-control'] = 'no-cache';
              proxyRes.headers['x-accel-buffering'] = 'no';
            }
          });
          proxy.on('error', (err, req) => {
            if ((req.url || '').includes('generate-sse')) {
              console.error('[Vite Proxy] SSE 代理错误:', err.message);
            }
          });
        },
      },
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
