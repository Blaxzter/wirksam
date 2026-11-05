import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

import dePreauth from '@/locales/de/preauth.json'
import enPreauth from '@/locales/en/preauth.json'

import { parseDoc } from '../../../scripts/docs-plugin'
import { DOC_GROUPS, DOC_PAGES, docId, docPageById, docPath, docRouteName } from '../content-pages'
import type { Doc, DocShot } from '../doc-types'
import { docFor, docIds, loadDoc } from '../docs-content'
import { publicPageFor } from '../seo'

const pages = DOC_PAGES.map((page) => docId(page))

await Promise.all(pages.flatMap((id) => [loadDoc(id, 'en'), loadDoc(id, 'de')]))
const SCREENSHOTS = resolve(__dirname, '../../../public/screenshots')

const shotsOf = (doc: Doc): DocShot[] =>
  [doc.intro, ...doc.sections.map((section) => section.blocks)]
    .flat()
    .flatMap((block) => (block.type === 'shots' ? block.shots : []))

const htmlOf = (doc: Doc): string =>
  [doc.intro, ...doc.sections.map((section) => section.blocks)]
    .flat()
    .flatMap((block) => (block.type === 'html' ? [block.html] : []))
    .concat(doc.faq.map((item) => item.html))
    .join('\n')

describe('parseDoc', () => {
  const source = (body: string, extra = '') =>
    `---\ntitle: Title: with a colon\nlede: The lede\n${extra}---\n\n${body}\n`

  it('reads the front matter', () => {
    const doc = parseDoc(source('Text', 'related: guide/one, feature/two\n'), 'en')
    expect(doc.title).toBe('Title: with a colon')
    expect(doc.lede).toBe('The lede')
    expect(doc.related).toEqual(['guide/one', 'feature/two'])
  })

  it('has no related pages unless it names some', () => {
    expect(parseDoc(source('Text'), 'en').related).toEqual([])
  })

  it('refuses a page without front matter, a title or a lede', () => {
    expect(() => parseDoc('Just text', 'en', 'a.md')).toThrow('a.md: no front matter')
    expect(() => parseDoc('---\nlede: x\n---\nText', 'en', 'b.md')).toThrow('b.md: no title')
    expect(() => parseDoc('---\ntitle: x\n---\nText', 'en', 'c.md')).toThrow('c.md: no lede')
  })

  it('reads the same with Windows line endings', () => {
    const doc = parseDoc(
      '---\r\ntitle: T\r\nlede: L\r\n---\r\nIntro\r\n\r\n## One\r\n\r\nText\r\n',
      'en',
    )
    expect(doc.title).toBe('T')
    expect(doc.sections.map((section) => section.title)).toEqual(['One'])
  })

  it('splits sections at second-level headings, keeping what stands before them as intro', () => {
    const doc = parseDoc(source('Intro\n\n## First one\n\nA\n\n## Zweite Größe\n\nB'), 'de')
    expect(doc.intro).toEqual([{ type: 'html', html: '<p>Intro</p>\n' }])
    expect(doc.sections.map(({ id, title, text }) => ({ id, title, text }))).toEqual([
      { id: 'first-one', title: 'First one', text: 'A' },
      { id: 'zweite-groesse', title: 'Zweite Größe', text: 'B' },
    ])
  })

  it('keeps anchors unique', () => {
    const doc = parseDoc(source('## Same\n\nA\n\n## Same\n\nB'), 'en')
    expect(doc.sections.map((section) => section.id)).toEqual(['same', 'same-2'])
  })

  it('takes screenshots out of the text and puts adjacent ones in one row', () => {
    const doc = parseDoc(
      source(
        '## S\n\nBefore\n\n![One](phone:one-shot)\n![Two](phone:two)\n\nBetween\n\n![Three](shot:three)',
      ),
      'en',
    )
    expect(doc.sections[0]!.blocks).toEqual([
      { type: 'html', html: '<p>Before</p>\n' },
      {
        type: 'shots',
        shots: [
          { alt: 'One', phone: true, name: 'one-shot' },
          { alt: 'Two', phone: true, name: 'two' },
        ],
      },
      { type: 'html', html: '<p>Between</p>\n' },
      { type: 'shots', shots: [{ alt: 'Three', phone: false, name: 'three' }] },
    ])
    expect(doc.sections[0]!.text).toBe('Before Between')
  })

  it.each(['Frequently asked questions', 'Häufige Fragen'])(
    'moves the questions under "%s" out of the body',
    (heading) => {
      const doc = parseDoc(
        source(
          `## Body\n\nA\n\n## ${heading}\n\n### Why?\n\nBecause **so**.\n\n### How?\n\nLike so.`,
        ),
        'en',
      )
      expect(doc.sections.map((section) => section.title)).toEqual(['Body'])
      expect(doc.faq.map(({ id, question, text }) => ({ id, question, text }))).toEqual([
        { id: 'faq-why', question: 'Why?', text: 'Because so.' },
        { id: 'faq-how', question: 'How?', text: 'Like so.' },
      ])
      expect(doc.faq[0]!.html).toContain('<strong>so</strong>')
    },
  )

  it('keeps an internal link in the language of the page', () => {
    const body = '[Teams](/features/teams)'
    expect(JSON.stringify(parseDoc(source(body), 'en').intro)).toContain(
      'href=\\"/features/teams\\"',
    )
    expect(JSON.stringify(parseDoc(source(body), 'de').intro)).toContain(
      'href=\\"/de/features/teams\\"',
    )
  })

  it('opens an outside link in a new tab', () => {
    const html = JSON.stringify(parseDoc(source('[Code](https://example.org)'), 'de').intro)
    expect(html).toContain('href=\\"https://example.org\\"')
    expect(html).toContain('target=\\"_blank\\"')
    expect(html).toContain('rel=\\"noopener\\"')
  })

  it('escapes raw HTML', () => {
    const html = JSON.stringify(parseDoc(source('<script>alert(1)</script>'), 'en').intro)
    expect(html).not.toContain('<script>')
  })

  it('writes entities out in the plain text', () => {
    const doc = parseDoc(source('## S\n\n"Fish" & <chips> are here.'), 'en')
    expect(doc.sections[0]!.text).toBe('"Fish" & <chips> are here.')
  })
})

describe('docFor', () => {
  it('finds a page in the given language', () => {
    expect(docFor('feature/vouchers', 'de')?.title).toBe('Marken statt Papier')
  })

  it('falls back to English for a language without the page', () => {
    expect(docFor('feature/vouchers', 'fr')?.title).toBe(docFor('feature/vouchers', 'en')?.title)
  })

  it('answers undefined for a page that does not exist', async () => {
    await loadDoc('feature/nope', 'en')
    expect(docFor('feature/nope', 'en')).toBeUndefined()
  })
})

describe('loadDoc', () => {
  const fresh = async () => {
    vi.resetModules()
    return import('../docs-content')
  }

  it('has nothing until a page is asked for', async () => {
    const content = await fresh()
    expect(content.docFor('guide/vouchers', 'de')).toBeUndefined()
  })

  it('fetches only the page and language asked for', async () => {
    const content = await fresh()
    await content.loadDoc('guide/vouchers', 'de')
    expect(content.docFor('guide/vouchers', 'de')?.title).toBe('Marken einrichten')
    expect(content.docFor('guide/teams', 'de')).toBeUndefined()
  })

  it('fetches English for a language without the page', async () => {
    const content = await fresh()
    await content.loadDoc('guide/vouchers', 'fr')
    expect(content.docFor('guide/vouchers', 'fr')?.title).toBe('Set up vouchers')
  })

  it('keeps showing the copy it has while another language is on its way', async () => {
    const content = await fresh()
    await content.loadDoc('guide/vouchers', 'de')
    expect(content.docFor('guide/vouchers', 'en')?.title).toBe('Marken einrichten')

    await content.loadDoc('guide/vouchers', 'en')
    expect(content.docFor('guide/vouchers', 'en')?.title).toBe('Set up vouchers')
    expect(content.docFor('guide/vouchers', 'de')?.title).toBe('Marken einrichten')
  })

  it('does not fetch a page twice', async () => {
    const content = await fresh()
    await content.loadDoc('guide/vouchers', 'de')
    const first = content.docFor('guide/vouchers', 'de')
    await content.loadDoc('guide/vouchers', 'de')
    expect(content.docFor('guide/vouchers', 'de')).toBe(first)
  })
})

describe('docIds', () => {
  it('lists every page, and nothing for an unknown language', () => {
    expect([...docIds('en')].sort()).toEqual([...pages].sort())
    expect([...docIds('de')].sort()).toEqual([...pages].sort())
    expect(docIds('fr')).toEqual([])
  })
})

describe('the page list', () => {
  it('finds a page by id, and nothing for an unknown one', () => {
    expect(docPageById('guide/vouchers')?.key).toBe('guideVouchers')
    expect(docPageById('guide/nope')).toBeUndefined()
  })

  it('gives every page a prerendered public page that goes with the landing page', () => {
    for (const page of DOC_PAGES) {
      const entry = publicPageFor(docRouteName(page))
      expect(entry?.path).toBe(docPath(page))
      expect(entry?.prerender).toBe(true)
      expect(entry?.requires).toBe('LANDING_ENABLED')
      expect(publicPageFor(entry?.parent)).toBeDefined()
    }
  })

  it('shows every page in exactly one group of its own kind', () => {
    const grouped = [...DOC_GROUPS.feature, ...DOC_GROUPS.guide].flatMap((group) => group.pages)
    expect([...grouped].sort()).toEqual([...pages].sort())
    for (const group of DOC_GROUPS.feature) {
      for (const id of group.pages) expect(docPageById(id)?.kind).toBe('feature')
    }
    for (const group of DOC_GROUPS.guide) {
      for (const id of group.pages) expect(docPageById(id)?.kind).toBe('guide')
    }
  })
})

// The locale files have a parity check that fails the commit. These Markdown
// files have this instead, so a page can't drift apart between the languages.
describe.each(pages)('%s', (id) => {
  const en = docFor(id, 'en')!
  const de = docFor(id, 'de')!

  it('exists in both languages, with its own text in each', () => {
    expect(docIds('en')).toContain(id)
    expect(docIds('de')).toContain(id)
    expect(de.lede).not.toBe(en.lede)
  })

  it('has the same structure in both languages', () => {
    expect(de.sections).toHaveLength(en.sections.length)
    expect(de.faq).toHaveLength(en.faq.length)
    expect(de.related).toEqual(en.related)
    expect(shotsOf(de).map((shot) => [shot.name, shot.phone])).toEqual(
      shotsOf(en).map((shot) => [shot.name, shot.phone]),
    )
  })

  it('has something in every section', () => {
    expect(en.sections.length).toBeGreaterThan(0)
    for (const section of [...en.sections, ...de.sections]) {
      expect(section.text, section.title).toBeTruthy()
    }
  })

  it('points only at pages that exist, other than itself', () => {
    expect(en.related.length).toBeGreaterThan(0)
    for (const related of en.related) {
      expect(docPageById(related), related).toBeDefined()
      expect(related).not.toBe(id)
    }
  })

  it.each(['en', 'de'] as const)('links only to public pages in %s', (locale) => {
    const html = htmlOf(locale === 'en' ? en : de)
    const prefix = locale === 'en' ? '' : `/${locale}`
    for (const [, href] of html.matchAll(/href="(\/[^"#]*)/g)) {
      expect(href!.startsWith(`${prefix}/`), href).toBe(true)
      const path = href!.slice(prefix.length)
      expect(
        DOC_PAGES.some((page) => docPath(page) === path) || ['/features', '/guides'].includes(path),
        href,
      ).toBe(true)
    }
  })

  it.each(['en', 'de'] as const)('only shows screenshots that were taken, in %s', (locale) => {
    for (const shot of shotsOf(locale === 'en' ? en : de)) {
      expect(shot.alt).toBeTruthy()
      for (const mode of ['light', 'dark']) {
        const file = resolve(SCREENSHOTS, locale, `${shot.name}-${mode}.png`)
        expect(existsSync(file), file).toBe(true)
      }
    }
  })
})

describe.each([
  ['en', enPreauth],
  ['de', dePreauth],
])('%s copy', (_locale, messages) => {
  it.each(DOC_PAGES.map((page) => page.key))('has a name for %s', (key) => {
    expect(messages.docs.pages[key as keyof typeof messages.docs.pages].name).toBeTruthy()
  })

  it('has a heading for every group', () => {
    for (const group of DOC_GROUPS.feature) {
      expect(messages.docs.groups.feature[group.key]).toBeTruthy()
    }
    for (const group of DOC_GROUPS.guide) {
      expect(messages.docs.groups.guide[group.key]).toBeTruthy()
    }
  })

  it.each(['feature', 'guide'] as const)('has the overview copy for %s', (kind) => {
    const hub = messages.docs.hubs[kind]
    for (const field of ['all', 'breadcrumb', 'eyebrow', 'lede', 'title'] as const) {
      expect(hub[field]).toBeTruthy()
    }
  })
})
