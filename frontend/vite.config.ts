import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { execSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { extname, join, posix, resolve } from 'node:path'
import { URL, fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'

function changelogPlugin(): Plugin {
  return {
    name: 'generate-changelog',
    buildStart() {
      execSync('pnpm generate-changelog', { stdio: 'inherit' })
    },
  }
}

/**
 * Make `vite preview` route like nginx/default.conf: a prerendered public page
 * at `<path>/index.html`, and the empty shell, `spa.html`, for everything else.
 * Preview's own fallback is `index.html`, which after the prerender is the
 * English landing page, and the E2E suite runs against preview on CI.
 */
function prerenderedPreviewPlugin(): Plugin {
  return {
    name: 'prerendered-preview-fallback',
    configurePreviewServer(server) {
      const outDir = resolve(server.config.root, server.config.build.outDir)
      server.middlewares.use((req, _res, next) => {
        const [path = '/', query] = (req.url ?? '/').split('?')
        if (req.method === 'GET' && !extname(path)) {
          // Rewrite to the exact file: left alone, preview's own fallback
          // answers `/de/terms` with the root index.html.
          const page = posix.join(path, 'index.html')
          const target = existsSync(join(outDir, decodeURIComponent(page))) ? page : '/spa.html'
          if (existsSync(join(outDir, target))) {
            req.url = query ? `${target}?${query}` : target
          }
        }
        next()
      })
    },
  }
}

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
      port: 5555,
      allowedHosts: true,
    },
    plugins: [
      changelogPlugin(),
      prerenderedPreviewPlugin(),
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
