// TraceSphere Console — Vite 配置（跨平台：Linux + Node 22 亦直接可用）
//
// 说明：这里刻意使用 `.mjs` 而非 `.ts`。Vite 需要先把 TS 配置编译成 JS 才能读取，
// 这一步会拉起 esbuild 子进程；在受限沙箱 / 无子进程权限的环境里会直接失败。
// 纯 ESM 配置可被 Node 原生 import，构建链路不再依赖配置转译。
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const target = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8010';

  return {
    base: './',
    plugins: [react()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: false,
      // 反向代理：把 /api 打到本机诊断服务，前端同源，避免任何 CORS 依赖。
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: '127.0.0.1',
      port: 4173,
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      chunkSizeWarningLimit: 1600,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            antd: ['antd', '@ant-design/icons'],
            g6: ['@antv/g6'],
            echarts: ['echarts'],
          },
        },
      },
    },
  };
});
