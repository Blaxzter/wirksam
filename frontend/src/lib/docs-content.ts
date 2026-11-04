import { shallowReactive } from 'vue'

import type { Doc } from '@/lib/doc-types'

/**
 * The feature pages and guides, from `src/docs/<locale>/<kind>/<slug>.md`, parsed
 * at build time by `scripts/docs-plugin.ts`.
 *
 * Each file is its own chunk, so someone reading one guide downloads that guide
 * in their language and none of the others. The route loads the page before it
 * shows (`router/routes.ts`), which keeps the prerendered copy on screen until
 * the text is here instead of flashing an empty page.
 */
const importers = import.meta.glob<Doc>('../docs/*/*/*.md', { import: 'default' })

const FALLBACK_LOCALE = 'en'

const pathOf = (id: string, locale: string) => `../docs/${locale}/${id}.md`

/** Reactive, so an open page changes language once the other copy has arrived. */
const loaded = shallowReactive(new Map<string, Doc>())

/** Fetches a page in the given language, or in English if it has no such copy. */
export async function loadDoc(id: string, locale: string): Promise<void> {
  const path = pathOf(id, importers[pathOf(id, locale)] ? locale : FALLBACK_LOCALE)
  if (loaded.has(path)) return
  const importer = importers[path]
  if (importer) loaded.set(path, await importer())
}

/**
 * A page in the given language, else in English, else in whichever language has
 * arrived. The last case is someone switching language on an open page: they
 * keep reading the old copy for the moment it takes the new one to load.
 * `id` is `feature/vouchers`.
 */
export function docFor(id: string, locale: string): Doc | undefined {
  const exact = loaded.get(pathOf(id, locale)) ?? loaded.get(pathOf(id, FALLBACK_LOCALE))
  if (exact) return exact
  for (const [path, doc] of loaded) {
    if (path.endsWith(`/${id}.md`)) return doc
  }
  return undefined
}

/** Every page id written in one language. */
export function docIds(locale: string): string[] {
  const prefix = `../docs/${locale}/`
  return Object.keys(importers)
    .filter((path) => path.startsWith(prefix))
    .map((path) => path.slice(prefix.length, -'.md'.length))
}
