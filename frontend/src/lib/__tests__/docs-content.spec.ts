import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

import allCaptures from '@/docs/captures.json'
import dePreauth from '@/locales/de/preauth.json'
import enPreauth from '@/locales/en/preauth.json'

import { parseDoc } from '../../../scripts/docs-plugin'
import {
  DOC_GROUPS,
  DOC_PAGES,
  PAGE_ART,
  docId,
  docPageById,
  docPath,
  docRouteName,
} from '../content-pages'
import { shotFile } from '../doc-shots'
import type { Captures, Doc, DocDevice, DocShot, MarkPlace } from '../doc-types'
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

  it('reads the points, separated by a bar, and has none unless it names some', () => {
    const doc = parseDoc(source('Text', 'points: One thing | Another thing | A third\n'), 'en')
    expect(doc.points).toEqual(['One thing', 'Another thing', 'A third'])
    expect(parseDoc(source('Text'), 'en').points).toEqual([])
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
    const captures: Captures = {
      'one-shot': { marks: {} },
      'one-shot-phone': { marks: {} },
      'two-phone': { marks: {} },
    }
    const doc = parseDoc(
      source(
        '## S\n\nBefore\n\n![One](shot:one-shot)\n![Two](shot:two)\n\nBetween\n\n![Three](shot:three)',
      ),
      'en',
      'a.md',
      captures,
    )
    expect(doc.sections[0]!.blocks).toEqual([
      { type: 'html', html: '<p>Before</p>\n' },
      {
        type: 'shots',
        shots: [
          { alt: 'One', name: 'one-shot', devices: { desktop: [], phone: [] } },
          { alt: 'Two', name: 'two', devices: { phone: [] } },
        ],
      },
      { type: 'html', html: '<p>Between</p>\n' },
      // Not captured at all: from the computer, as before there were phones.
      { type: 'shots', shots: [{ alt: 'Three', name: 'three', devices: { desktop: [] } }] },
    ])
    expect(doc.sections[0]!.text).toBe('Before Between')
  })

  it('numbers the marks a section names, per device, in the order it names them', () => {
    const captures: Captures = {
      form: {
        marks: {
          save: { box: [0.8, 0.1, 0.1, 0.05], pin: [0.78, 0.12] },
          name: { box: [0.1, 0.2, 0.5, 0.05], pin: [0.08, 0.22] },
        },
      },
      'form-phone': { marks: { name: { box: [0.05, 0.3, 0.9, 0.04], pin: [0.5, 0.27] } } },
    }
    const doc = parseDoc(
      source(
        '## S\n\nType a name [[name]], then save [[save]]. Saved [[save]].\n\n![Form](shot:form)',
      ),
      'en',
      'a.md',
      captures,
    )
    const [text, shots] = doc.sections[0]!.blocks
    const name = 'data-mark="name" data-desktop="1" data-phone="1"'
    const save = 'data-mark="save" data-desktop="2"'
    expect(text).toEqual({
      type: 'html',
      html:
        `<p>Type a name<span class="doc-mark" ${name} aria-hidden="true"></span>, ` +
        `then save<span class="doc-mark" ${save} aria-hidden="true"></span>. ` +
        `Saved<span class="doc-mark" ${save} aria-hidden="true"></span>.</p>\n`,
    })
    expect(shots).toEqual({
      type: 'shots',
      shots: [
        {
          alt: 'Form',
          name: 'form',
          devices: {
            desktop: [
              { key: 'name', n: 1, box: [0.1, 0.2, 0.5, 0.05], pin: [0.08, 0.22] },
              { key: 'save', n: 2, box: [0.8, 0.1, 0.1, 0.05], pin: [0.78, 0.12] },
            ],
            phone: [{ key: 'name', n: 1, box: [0.05, 0.3, 0.9, 0.04], pin: [0.5, 0.27] }],
          },
        },
      ],
    })
    // The marks are pictures of numbers, not words.
    expect(doc.sections[0]!.text).toBe('Type a name, then save. Saved.')
  })

  it('leaves a mark without a number where no screenshot of its section shows it', () => {
    const doc = parseDoc(source('## S\n\nSee [[nowhere]].'), 'en')
    expect(doc.sections[0]!.blocks[0]).toEqual({
      type: 'html',
      html: '<p>See<span class="doc-mark" data-mark="nowhere" aria-hidden="true"></span>.</p>\n',
    })
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

  it('has a drawing beside its title', () => {
    expect(PAGE_ART[id], id).toBeDefined()
  })

  it.each(['en', 'de'] as const)(
    'sums itself up in three short points in %s, or not at all',
    (locale) => {
      const { points } = locale === 'en' ? en : de
      if (docPageById(id)?.kind === 'guide') return
      expect(points).toHaveLength(3)
      for (const point of points) {
        // One line in a box of three: a point that needs two sentences is text.
        expect(point.length, point).toBeLessThanOrEqual(60)
        expect(point, point).not.toMatch(/[.|]$/)
      }
    },
  )

  it('has the same structure in both languages', () => {
    expect(de.sections).toHaveLength(en.sections.length)
    expect(de.faq).toHaveLength(en.faq.length)
    expect(de.related).toEqual(en.related)
    expect(de.points).toHaveLength(en.points.length)
    expect(shotsOf(de).map((shot) => shot.name)).toEqual(shotsOf(en).map((shot) => shot.name))
    // The same parts marked, in the same order: a number means the same in both.
    const marksOf = (doc: Doc) =>
      shotsOf(doc).map((shot) => (shot.devices.desktop ?? []).map((mark) => mark.key))
    expect(marksOf(de)).toEqual(marksOf(en))
  })

  it.each(['en', 'de'] as const)(
    'marks only what a screenshot beside it shows, in %s',
    (locale) => {
      const html = htmlOf(locale === 'en' ? en : de)
      for (const [mark] of html.matchAll(/<span class="doc-mark"[^>]*>/g)) {
        expect(mark, mark).toMatch(/data-(desktop|phone)=/)
      }
    },
  )

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
      // Every screen on a computer and on a phone, so the choice between them holds.
      expect(Object.keys(shot.devices).sort(), shot.name).toEqual(['desktop', 'phone'])
      for (const device of Object.keys(shot.devices) as DocDevice[]) {
        for (const mode of ['light', 'dark']) {
          const file = resolve(SCREENSHOTS, locale, `${shotFile(shot.name, device)}-${mode}.png`)
          expect(existsSync(file), file).toBe(true)
        }
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

  it.each(DOC_PAGES.map((page) => page.key))('has one short line for %s', (key) => {
    const { tagline } = messages.docs.pages[key as keyof typeof messages.docs.pages]
    expect(tagline).toBeTruthy()
    // A card on the overview is read at a glance: the search description is not it.
    expect(tagline.length).toBeLessThanOrEqual(90)
    expect(tagline).not.toMatch(/[@|{]/)
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

describe.each(['en', 'de'] as const)('the marks measured in %s', (locale) => {
  const inside = (share: number) => share >= 0 && share <= 1
  // JSON's numbers come as plain arrays, not the tuples the type names.
  const captures = (allCaptures as unknown as Record<string, Captures>)[locale] ?? {}
  const marks = Object.entries(captures).flatMap(([file, { marks }]) =>
    Object.entries(marks).map(([key, place]): [string, MarkPlace] => [`${file} ${key}`, place]),
  )

  it('were measured', () => {
    expect(marks.length).toBeGreaterThan(0)
  })

  it.each(marks)('puts %s and its number on the capture', (_name, { box, pin }) => {
    const [left, top, width, height] = box
    expect([left, top, left + width, top + height].every(inside)).toBe(true)
    expect(width).toBeGreaterThan(0)
    expect(height).toBeGreaterThan(0)
    expect(pin.every(inside)).toBe(true)
  })
})
