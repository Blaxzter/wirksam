import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { URL, fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(async ({ mode }) => ({
  server: {
    port: 5173,
  },
  plugins: [
    vue(),
    tailwindcss(),
    ...(mode === 'development'
      ? [(await import('vite-plugin-vue-devtools')).default({ launchEditor: 'code' })]
      : []),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
}))
