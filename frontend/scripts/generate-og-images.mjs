/**
 * Renders the link-preview cards (`og:image`) for the public pages.
 *
 * Writes public/og/wirksam-<locale>.png at 1200×630, the size WhatsApp, Slack,
 * LinkedIn and X all crop to. The cards are built from the running app rather
 * than drawn separately: the dev server serves the landing page, the hero's
 * shift board is copied out of it in its finished state, and the card around
 * it is laid out with the app's own stylesheet and theme tokens. A redesign of
 * the hero shows up here the next time this runs.
 *
 * The PNGs are committed; nothing runs at build or deploy time. Re-run after
 * changing the hero copy, the board, or the theme:
 *
 *   pnpm generate-og-images
 */
import { chromium } from '@playwright/test'
import { mkdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { createServer } from 'vite'

const ROOT = resolve(import.meta.dirname, '..')
const OUT = join(ROOT, 'public/og')
const WIDTH = 1200
const HEIGHT = 630
const LOCALES = { en: '/', de: '/de' }
const DOMAIN = 'wirksam.app'

const server = await createServer({
  root: ROOT,
  logLevel: 'error',
  server: { port: 0, strictPort: false },
})
await server.listen()
const base = server.resolvedUrls.local[0].replace(/\/$/, '')

const browser = await chromium.launch()
mkdirSync(OUT, { recursive: true })

try {
  for (const [locale, path] of Object.entries(LOCALES)) {
    const hero = JSON.parse(readFileSync(join(ROOT, `src/locales/${locale}/preauth.json`), 'utf8'))
      .landing.hero

    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      deviceScaleFactor: 1,
      // Reduced motion makes the board skip its fill-up animation and show
      // the finished roster straight away.
      reducedMotion: 'reduce',
      colorScheme: 'light',
    })
    await context.addInitScript(() => {
      localStorage.setItem('vueuse-color-scheme', 'light')
      localStorage.setItem('wirksam-palette', 'default')
    })
    const page = await context.newPage()
    await page.goto(base + path)

    const board = page.locator('#app [role="img"]').first()
    await board.waitFor()
    // The "you" badge is the last thing the finished board shows.
    await page.waitForFunction(() =>
      [...document.querySelectorAll('#app [role="img"] li span')].some(
        (el) => el.classList.contains('bg-primary') && el.classList.contains('absolute'),
      ),
    )

    await page.evaluate(
      ({ width, height, hero, domain }) => {
        const boardEl = document.querySelector('#app [role="img"]')
        const logoSrc = document.querySelector('header img')?.getAttribute('src') ?? ''

        const card = document.createElement('div')
        card.id = 'og-card'
        card.style.cssText = `
          position: fixed; inset: 0 auto auto 0; z-index: 2147483647;
          width: ${width}px; height: ${height}px; overflow: hidden;
          display: grid; grid-template-columns: 1fr 470px; gap: 56px; align-items: center;
          padding: 64px 72px; box-sizing: border-box;
          background: var(--hero); color: var(--hero-foreground);
          font-family: inherit;
        `
        // The same two tonal glows as the hero band (LandingSection.vue).
        const glow = document.createElement('div')
        glow.style.cssText = `
          position: absolute; inset: 0; pointer-events: none;
          background:
            radial-gradient(ellipse 90% 70% at 15% 0%,
              color-mix(in oklab, var(--hero-speck) var(--hero-speck-opacity), transparent) 0%, transparent 65%),
            radial-gradient(ellipse 100% 80% at 100% 100%,
              color-mix(in oklab, var(--hero-speck) var(--hero-speck-opacity), transparent) 0%, transparent 70%);
        `
        card.append(glow)

        const left = document.createElement('div')
        left.style.cssText = 'position: relative; display: flex; flex-direction: column; gap: 28px;'
        left.innerHTML = `
          <div style="display:flex; align-items:center; gap:14px;">
            <img src="${logoSrc}" alt="" style="width:56px; height:56px; border-radius:14px;" />
            <span style="font-size:34px; font-weight:700; letter-spacing:-0.01em;"></span>
          </div>
          <h1 style="margin:0; font-size:50px; line-height:1.08; font-weight:700; letter-spacing:-0.02em; text-wrap:balance;"></h1>
          <ul style="margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:10px; font-size:21px; opacity:0.88;"></ul>
          <span style="font-size:20px; font-weight:600; opacity:0.75;"></span>
        `
        left.querySelector('span').textContent = 'WirkSam'
        left.querySelector('h1').textContent = hero.title
        const list = left.querySelector('ul')
        for (const key of ['free', 'noInstall', 'privacy']) {
          const li = document.createElement('li')
          li.style.cssText = 'display:flex; align-items:center; gap:12px;'
          li.innerHTML =
            '<span style="width:8px; height:8px; border-radius:999px; background:var(--hero-speck); flex:none;"></span>'
          li.append(hero.proof[key])
          list.append(li)
        }
        left.lastElementChild.textContent = domain

        // The finished board itself, on a solid card so it reads at preview size.
        const right = document.createElement('div')
        right.style.cssText = 'position: relative;'
        const clone = boardEl.cloneNode(true)
        clone.removeAttribute('role')
        clone.style.background = 'var(--card)'
        clone.style.color = 'var(--foreground)'
        right.append(clone)

        card.append(left, right)
        document.body.append(card)
      },
      { width: WIDTH, height: HEIGHT, hero, domain: DOMAIN },
    )

    await page.locator('#og-card img').evaluate((img) => img.decode())
    const file = join(OUT, `wirksam-${locale}.png`)
    await page.locator('#og-card').screenshot({ path: file })
    console.log(`  public/og/wirksam-${locale}.png`)
    await context.close()
  }
} finally {
  await browser.close()
  await server.close()
}
