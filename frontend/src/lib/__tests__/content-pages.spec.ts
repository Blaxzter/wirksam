import { describe, expect, it } from 'vitest'

import dePreauth from '@/locales/de/preauth.json'
import enPreauth from '@/locales/en/preauth.json'

import {
  COMPARED_TOOLS,
  COMPARISON_CRITERIA,
  COMPARISON_SCREENSHOTS,
  ACCENT_COLORS,
  DOC_GROUPS,
  GROUP_ACCENTS,
  PAGE_ACCENTS,
  PAGE_ART,
  RELATED_PAGES,
  USE_CASES,
  type UseCaseKey,
  docAccent,
  pageLook,
  relatedPages,
  useCaseForRoute,
} from '../content-pages'
import { publicPageFor } from '../seo'

const useCaseKeys = Object.keys(USE_CASES) as UseCaseKey[]

describe('useCaseForRoute', () => {
  it('finds the use case a route renders', () => {
    expect(useCaseForRoute('use-case-club-festival')).toBe('clubFestival')
  })

  it('answers undefined for any other route', () => {
    expect(useCaseForRoute('landing')).toBeUndefined()
    expect(useCaseForRoute(undefined)).toBeUndefined()
  })
})

describe('relatedPages', () => {
  it('leaves out the page being read', () => {
    const names = relatedPages('alternatives').map((page) => page.routeName)
    expect(names).not.toContain('alternatives')
    expect(names).toHaveLength(RELATED_PAGES.length - 1)
  })

  it('lists every page from elsewhere', () => {
    expect(relatedPages('terms')).toEqual(RELATED_PAGES)
  })
})

describe('how a page looks', () => {
  it('gives every group of feature pages and guides a colour', () => {
    for (const kind of ['feature', 'guide'] as const) {
      for (const group of DOC_GROUPS[kind]) {
        expect(GROUP_ACCENTS[kind][group.key], group.key).toBeDefined()
      }
    }
  })

  it('colours a feature page or guide like its group', () => {
    expect(docAccent('feature/vouchers')).toBe(GROUP_ACCENTS.feature.thanks)
    expect(docAccent('guide/next-year')).toBe(GROUP_ACCENTS.guide.again)
    expect(docAccent('feature/nothing')).toBe('green')
  })

  it('draws and colours every page that stands alone', () => {
    for (const key of ['features', 'guides', 'alternatives', ...Object.keys(USE_CASES)]) {
      expect(PAGE_ART[key], key).toBeDefined()
      expect(pageLook(key)).toEqual({ art: PAGE_ART[key], color: ACCENT_COLORS[PAGE_ACCENTS[key]!] })
    }
  })

  it('looks up a feature page by its id, and falls back to green for a page it does not know', () => {
    expect(pageLook('feature/vouchers')).toEqual({
      art: 'vouchers',
      color: ACCENT_COLORS[GROUP_ACCENTS.feature.thanks!],
    })
    expect(pageLook('nowhere')).toEqual({ art: undefined, color: ACCENT_COLORS.green })
  })
})

describe('structure', () => {
  it('gives every use case a public page', () => {
    for (const key of useCaseKeys) {
      expect(publicPageFor(USE_CASES[key].routeName)?.prerender).toBe(true)
    }
  })

  it('links only to public pages', () => {
    for (const page of RELATED_PAGES) {
      expect(publicPageFor(page.routeName)).toBeDefined()
    }
  })

  it('cites at least one https source per compared tool', () => {
    for (const tool of COMPARED_TOOLS) {
      expect(tool.url).toMatch(/^https:\/\//)
      expect(tool.sources.length).toBeGreaterThan(0)
      for (const source of tool.sources) expect(source).toMatch(/^https:\/\//)
    }
  })
})

// A missing key renders as its raw path, silently; on a page written for
// search engines that would be the snippet people see.
describe.each([
  ['en', enPreauth],
  ['de', dePreauth],
])('%s copy', (_locale, messages) => {
  it.each(COMPARED_TOOLS.map((tool) => tool.key))('has every cell and note for %s', (key) => {
    const tool = messages.alternatives.tools[key as keyof typeof messages.alternatives.tools]
    for (const field of ['name', 'summary', 'goodFit', 'lessSuited'] as const) {
      expect(tool[field]).toBeTruthy()
    }
    for (const criterion of COMPARISON_CRITERIA) {
      expect(tool.cells[criterion]).toBeTruthy()
      expect(tool.cells[criterion]).not.toMatch(/[@|{]/)
    }
  })

  it('names every criterion', () => {
    for (const criterion of COMPARISON_CRITERIA) {
      expect(messages.alternatives.criteria[criterion]).toBeTruthy()
    }
  })

  it('has captions for the comparison screenshots', () => {
    for (const shot of COMPARISON_SCREENSHOTS) {
      expect(messages.landing.features.rows[shot.key].screenshotAlt).toBeTruthy()
    }
  })

  it('has copy for every related page', () => {
    for (const page of RELATED_PAGES) {
      expect(messages.content.related.pages[page.key].title).toBeTruthy()
    }
  })

  it.each(useCaseKeys)('has every pain, step and question for %s', (key) => {
    const copy = messages.useCases[key]
    const { pains, steps, faq } = USE_CASES[key]
    for (const pain of pains) {
      const item = copy.pains.items[pain as keyof typeof copy.pains.items]
      expect(item.title).toBeTruthy()
      expect(item.description).toBeTruthy()
    }
    for (const step of steps) {
      const item = copy.steps.items[step.key as keyof typeof copy.steps.items]
      expect(item.title).toBeTruthy()
      expect(item.description).toBeTruthy()
      expect(item.screenshotAlt).toBeTruthy()
    }
    for (const question of faq) {
      const item = copy.faq.items[question as keyof typeof copy.faq.items]
      expect(item.question).toBeTruthy()
      expect(item.answer).toBeTruthy()
    }
  })
})
