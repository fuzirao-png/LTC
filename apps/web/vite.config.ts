import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const API_TARGET = process.env.LTC_API_ORIGIN ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    allowedHosts: ['host.docker.internal', 'localhost', '.docker.internal'],
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
      '/internal': { target: API_TARGET, changeOrigin: true },
    },
  },
})
