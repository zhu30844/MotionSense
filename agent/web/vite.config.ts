import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// Where /api goes while developing: the simulator's agent, or a board.
const agent = process.env.MS_AGENT || 'http://localhost:3000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), vueDevTools()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  // Served beside the current pages until it replaces them.
  base: '/v2/',
  build: {
    outDir: '../static/v2',
    emptyOutDir: true,
  },
  server: {
    host: true,
    proxy: { '/api': agent },
  },
})
