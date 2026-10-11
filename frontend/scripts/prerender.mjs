/**
 * Build-time prerender of the public pages, plus the files crawlers look for.
 *
 * Runs after `vite build`. Without it every URL answers with an empty
 * `<div id="app">`, which is all that a crawler that does not execute
 * JavaScript (most LLM crawlers, link previews) ever sees. For each page in
 * `src/lib/seo.ts` marked `prerender`, in each language, this writes
 * `dist/<path>/index.html` with the rendered markup, its own title,
 * description, canonical and hreflang links, and JSON-LD. Then:
 *
 *   dist/spa.html     the untouched shell, nginx's fallback for every other URL
 *   dist/sitemap.xml  every public page in every language
 *   dist/robots.txt   points at the sitemap, keeps crawlers out of the app
 *   dist/llms.txt     a plain-text summary for LLMs (https://llmstxt.org)
 *
 * Runtime switches that change what a public page shows (`TOGGLES` below) are
 * rendered both ways. The default, everything on, goes to `dist/` itself; every
 * other combination goes to `dist/_prerender/off-<slugs>/`, and
 * `docker-entrypoint.sh` copies the one a deployment runs with into place.
 *
 * Absolute URLs use SITE_URL, defaulting to the public instance.
 * `docker-entrypoint.sh` rewrites them to FRONTEND_HOST when a deployment runs
 * somewhere else, so one image serves every deployment.
 *
 * Run: pnpm prerender (part of `pnpm build-only`). Plain JavaScript under
 * plain `node` on purpose: under tsx's loader hooks the server bundle got one
 * copy of pinia through `require` and another through `import`, and `inject()`
 * found neither. The shared page list comes out of the server bundle for the
 * same reason, rather than from importing `src/lib/seo.ts` here.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'vite'

const ROOT = resolve(import.meta.dirname, '..')
const DIST = join(ROOT, 'dist')
const SSR_OUT = join(ROOT, 'node_modules/.prerender')
const SITE_URL = (process.env.SITE_URL ?? 'https://wirksam.app').replace(/\/+$/, '')
const REPOSITORY = 'https://github.com/Blaxzter/wirksam'

/**
 * Runtime switches (`window.__APP_CONFIG__`, written by docker-entrypoint.sh)
 * that change what the public pages show. Each is on unless set to the literal
 * 'false', like `stores/sandbox.ts` reads it. The entrypoint walks the same
 * list in the same order to name the variant it needs, so the two must agree.
 */
const TOGGLES = [
  { name: 'SANDBOX_ENABLED', slug: 'sandbox' },
  { name: 'LANDING_ENABLED', slug: 'landing' },
]

/** Every combination of switches: a config to render with, and where it goes. */
function variants() {
  return Array.from({ length: 2 ** TOGGLES.length }, (_, mask) => {
    const off = TOGGLES.filter((_, i) => mask & (1 << i))
    return {
      dir: off.length === 0 ? '' : `_prerender/off-${off.map((t) => t.slug).join('-')}/`,
      config: Object.fromEntries(TOGGLES.map((t) => [t.name, off.includes(t) ? 'false' : 'true'])),
    }
  })
}

const isOn = (config, name) => config[name] !== 'false'

/** The public pages a deployment with this config has (see `requires` in seo.ts). */
const pagesFor = (config) =>
  PUBLIC_PAGES.filter((page) => !page.requires || isOn(config, page.requires))

const OG_LOCALE = { en: 'en_US', de: 'de_DE' }

// ---------------------------------------------------------------------------
// The server bundle. A real SSR build rather than Vite's dev loader, so asset
// imports resolve to the same hashed `/assets/…` URLs as the client build.

await build({
  root: ROOT,
  logLevel: 'warn',
  build: {
    ssr: 'src/entry-prerender.ts',
    outDir: SSR_OUT,
    emptyOutDir: true,
    copyPublicDir: false,
    rollupOptions: { output: { entryFileNames: 'entry.mjs' } },
  },
  // Bundle every dependency except Vue's own packages. Left external, some UI
  // libraries cannot be loaded by Node (`vue-sonner` has no Node export);
  // bundled, Vue would exist twice and `inject()` would find nothing.
  ssr: { noExternal: /^(?!(vue|vue-router|pinia|vue-i18n|@vue\/[^/]+|@intlify\/[^/]+)(\/|$))/ },
})

const {
  render,
  i18n,
  DEFAULT_PUBLIC_LOCALE,
  PUBLIC_LOCALES,
  PUBLIC_PAGES,
  faqKeys,
  localizedPath,
} = await import(pathToFileURL(join(SSR_OUT, 'entry.mjs')).href)
// Components probe numbered keys until one is missing; that is expected here.
i18n.global.missingWarn = false
i18n.global.fallbackWarn = false

function t(locale, key) {
  i18n.global.locale.value = locale
  return i18n.global.t(key)
}

function keysOf(key) {
  i18n.global.locale.value = 'en'
  return Object.keys(i18n.global.tm(key) ?? {})
}

// ---------------------------------------------------------------------------
// HTML helpers

const absolute = (path) => `${SITE_URL}${path === '/' ? '/' : path}`

function escapeAttr(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/** JSON-LD inside a `<script>`: `<` escaped so the content can never close the tag. */
function jsonLd(data) {
  const json = JSON.stringify(data).replace(/</g, '\\u003c')
  return `<script type="application/ld+json">${json}</script>`
}

function setMeta(html, attr, key, content) {
  const pattern = new RegExp(`<meta ${attr}="${key}" content="[^"]*"\\s*/?>`)
  const tag = `<meta ${attr}="${key}" content="${escapeAttr(content)}" />`
  if (!pattern.test(html)) throw new Error(`index.html has no <meta ${attr}="${key}">`)
  return html.replace(pattern, tag)
}

/** The link-preview card, rendered by scripts/generate-og-images.mjs. */
function ogImage(locale) {
  return `${SITE_URL}/og/wirksam-${locale}.png`
}

function screenshot(locale) {
  return `${SITE_URL}/screenshots/${locale}/dashboard-light.png`
}

function faqEntries(locale, config) {
  return faqKeys(isOn(config, 'SANDBOX_ENABLED')).map((key) => ({
    question: t(locale, `preauth.landing.faq.items.${key}.question`),
    answer: t(locale, `preauth.landing.faq.items.${key}.answer`),
  }))
}

function structuredData(page, locale, url, config) {
  if (page.routeName !== 'landing') return []
  const description = t(locale, 'preauth.seo.landing.description')
  return [
    jsonLd({
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'WebSite',
          '@id': `${SITE_URL}/#website`,
          url: absolute('/'),
          name: 'WirkSam',
          inLanguage: [...PUBLIC_LOCALES],
        },
        {
          '@type': 'WebApplication',
          '@id': `${SITE_URL}/#app`,
          name: 'WirkSam',
          url,
          description,
          inLanguage: locale,
          applicationCategory: 'BusinessApplication',
          applicationSubCategory: 'Volunteer scheduling',
          operatingSystem: 'Any (web browser)',
          isAccessibleForFree: true,
          offers: { '@type': 'Offer', price: '0', priceCurrency: 'EUR' },
          screenshot: screenshot(locale),
          license: 'https://opensource.org/licenses/MIT',
          sameAs: [REPOSITORY],
        },
        {
          '@type': 'FAQPage',
          '@id': `${url}#faq`,
          inLanguage: locale,
          mainEntity: faqEntries(locale, config).map(({ question, answer }) => ({
            '@type': 'Question',
            name: question,
            acceptedAnswer: { '@type': 'Answer', text: answer },
          })),
        },
      ],
    }),
  ]
}

function documentFor(template, page, locale, body, config) {
  const path = localizedPath(page.path, locale)
  const url = absolute(path)
  const title = t(locale, `preauth.seo.${page.seoKey}.title`)
  const description = t(locale, `preauth.seo.${page.seoKey}.description`)

  let html = template
    .replace(/<html lang="[^"]*">/, `<html lang="${locale}">`)
    .replace(/<title>[^<]*<\/title>/, `<title>${escapeAttr(title)}</title>`)
  html = setMeta(html, 'name', 'description', description)
  html = setMeta(html, 'property', 'og:title', title)
  html = setMeta(html, 'property', 'og:description', description)
  html = setMeta(html, 'property', 'og:url', url)
  const imageAlt = `WirkSam: ${t(locale, 'preauth.landing.hero.title')}`
  html = setMeta(html, 'property', 'og:image', ogImage(locale))
  html = setMeta(html, 'property', 'og:image:alt', imageAlt)
  html = setMeta(html, 'name', 'twitter:title', title)
  html = setMeta(html, 'name', 'twitter:description', description)
  html = setMeta(html, 'name', 'twitter:image', ogImage(locale))
  html = setMeta(html, 'name', 'twitter:image:alt', imageAlt)

  const head = [
    `<link rel="canonical" href="${url}" />`,
    ...PUBLIC_LOCALES.map(
      (alt) =>
        `<link rel="alternate" hreflang="${alt}" href="${absolute(localizedPath(page.path, alt))}" />`,
    ),
    `<link rel="alternate" hreflang="x-default" href="${absolute(page.path)}" />`,
    `<meta property="og:locale" content="${OG_LOCALE[locale]}" />`,
    ...PUBLIC_LOCALES.filter((alt) => alt !== locale).map(
      (alt) => `<meta property="og:locale:alternate" content="${OG_LOCALE[alt]}" />`,
    ),
    ...structuredData(page, locale, url, config),
  ]
  html = html.replace('</head>', `    ${head.join('\n    ')}\n  </head>`)

  if (!html.includes('<div id="app"></div>')) throw new Error('index.html has no empty #app')
  // `data-prerendered` tells main.ts to keep this on screen until the app is ready.
  return html.replace('<div id="app"></div>', `<div id="app" data-prerendered>${body}</div>`)
}

function write(relative, content) {
  const file = join(DIST, relative)
  mkdirSync(dirname(file), { recursive: true })
  writeFileSync(file, content)
  console.log(`  ${relative}`)
}

// ---------------------------------------------------------------------------
// llms.txt — English, with a pointer to the German pages.

const en = (key) => t('en', key)
const L = 'preauth.landing'

// Same order as the step chain in components/landing/LandingJourney.vue.
const organiserSteps = ['create', 'invite', 'generate', 'publish']
const volunteerSteps = ['accept', 'availability', 'book', 'reminders']
const steps = (track, keys) =>
  keys
    .map(
      (key, i) =>
        `${i + 1}. **${en(`${L}.journey.${track}.steps.${key}.title`)}**: ${en(`${L}.journey.${track}.steps.${key}.description`)}`,
    )
    .join('\n')

const featureLines = [
  ...keysOf(`${L}.features.rows`).map((key) => `${L}.features.rows.${key}`),
  ...keysOf(`${L}.features.more.items`).map((key) => `${L}.features.more.items.${key}`),
].map((key) => `- **${en(`${key}.title`)}**: ${en(`${key}.description`)}`)

const pageLines = (config) =>
  pagesFor(config).flatMap((page) =>
    PUBLIC_LOCALES.map(
      (locale) =>
        `- [${t(locale, `preauth.seo.${page.seoKey}.title`)}](${absolute(localizedPath(page.path, locale))})${locale === DEFAULT_PUBLIC_LOCALE ? '' : ` (${locale})`}: ${t(locale, `preauth.seo.${page.seoKey}.description`)}`,
    ),
  )

function llmsTxt(config) {
  return `# WirkSam

> ${en('preauth.seo.landing.description')}

${en(`${L}.about.lede`)} ${en(`${L}.hero.subtitle`)}

${en(`${L}.about.nameExplainer`)}

WirkSam is free, non-commercial, open source under the MIT licence, and available in English and German. The German pages live under ${absolute('/de')}.

## Pages

${pageLines(config).join('\n')}
- [Source code on GitHub](${REPOSITORY}): MIT licensed, runs with Docker Compose

## How it works

### For organisers

${steps('organiser', organiserSteps)}

### For volunteers

${steps('volunteer', volunteerSteps)}

## Features

${featureLines.join('\n')}

## FAQ

${faqEntries('en', config)
  .map(({ question, answer }) => `### ${question}\n\n${answer}`)
  .join('\n\n')}
`
}

function sitemapXml(config) {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ...pagesFor(config).flatMap((page) =>
      PUBLIC_LOCALES.map((locale) =>
        [
          '  <url>',
          `    <loc>${absolute(localizedPath(page.path, locale))}</loc>`,
          ...PUBLIC_LOCALES.map(
            (alt) =>
              `    <xhtml:link rel="alternate" hreflang="${alt}" href="${absolute(localizedPath(page.path, alt))}" />`,
          ),
          `    <xhtml:link rel="alternate" hreflang="x-default" href="${absolute(page.path)}" />`,
          `    <changefreq>${page.changefreq}</changefreq>`,
          `    <priority>${page.priority.toFixed(1)}</priority>`,
          '  </url>',
        ].join('\n'),
      ),
    ),
    '</urlset>',
    '',
  ].join('\n')
}

// ---------------------------------------------------------------------------
// Pages

// A second run without a fresh `vite build` finds its own output in index.html;
// the shell it saved last time is the same file before prerendering.
const built = readFileSync(join(DIST, 'index.html'), 'utf8')
const template = built.includes('data-prerendered')
  ? readFileSync(join(DIST, 'spa.html'), 'utf8')
  : built
write('spa.html', template)

for (const { dir, config } of variants()) {
  const present = pagesFor(config)
  for (const page of PUBLIC_PAGES.filter((p) => p.prerender)) {
    for (const locale of PUBLIC_LOCALES) {
      const path = localizedPath(page.path, locale)
      const file = path === '/' ? 'index.html' : `${path.slice(1)}/index.html`
      // A page this deployment does not have gets the empty shell, so its URL
      // never shows a page the router is about to send away from.
      if (!present.includes(page)) {
        write(dir + file, template)
        continue
      }
      const body = await render(path, locale, config)
      write(dir + file, documentFor(template, page, locale, body, config))
    }
  }
  write(`${dir}llms.txt`, llmsTxt(config))
  write(`${dir}sitemap.xml`, sitemapXml(config))
}

// ---------------------------------------------------------------------------
// robots.txt

// Everything behind a sign-in, and the one-shot links mailed to people, is of
// no use in a search result. Login and register stay open: people do search
// for "<name> login".
const robots = `# Search engines and AI crawlers are welcome on the public pages.
User-agent: *
Allow: /
Disallow: /app
Disallow: /print
Disallow: /invite/
Disallow: /reset-password
Disallow: /verify-email
Disallow: /forgot-password
Disallow: /account-suspended
Disallow: /account-pending

Sitemap: ${SITE_URL}/sitemap.xml
`
write('robots.txt', robots)

console.log('Prerender done.')
