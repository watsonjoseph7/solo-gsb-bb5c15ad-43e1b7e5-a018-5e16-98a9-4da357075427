import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 后端（FastAPI 基座）默认监听 8000 端口；
// 开发服务器把 /api 与 /health 代理过去，避免 CORS。
const API_TARGET = process.env.KERF_API_ORIGIN || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
      '/health': { target: API_TARGET, changeOrigin: true },
    },
  },
})
