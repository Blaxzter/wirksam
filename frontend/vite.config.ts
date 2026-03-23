import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { execSync } from 'node:child_process'
import { URL, fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

function getGitVersion(): { version: string; date: string } {
  // In Docker builds, APP_VERSION is passed as an env var since .git is not available
  if (process.env.APP_VERSION && process.env.APP_VERSION !== 'dev') {
    return { version: process.env.APP_VERSION, date: new Date().toISOString().split('T')[0] }
  }
  try {
    const version = execSync('git describe --tags --abbrev=0', { encoding: 'utf-8' }).trim()
    const date = execSync(`git log -1 --format=%aI ${version}`, { encoding: 'utf-8' }).trim()
    return { version, date: date.split('T')[0] }
  } catch {
    return { version: 'dev', date: new Date().toISOString().split('T')[0] }
  }
}

// https://vite.dev/config/
export default defineConfig(async ({ mode }) => {
  const gitInfo = getGitVersion()

  return {
    define: {
      __APP_VERSION__: JSON.stringify(gitInfo.version),
      __APP_VERSION_DATE__: JSON.stringify(gitInfo.date),
    },
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
  }
})
