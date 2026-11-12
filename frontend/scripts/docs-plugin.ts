/**
 * Turns the feature pages and guides in `src/docs/<locale>/` from Markdown into
 * data at build time, so a page imports `.md` and gets a `Doc`.
 *
 * They are Markdown rather than `preauth.json` because the locale files are all
 * loaded up front on every page of the app, and these are long. The view that
 * shows them is a lazy chunk, so only a visitor reading one pays for them.
 *
 * What the format adds to plain Markdown:
 *
 * - Front matter with `title`, `lede` and optionally `related` and `points`,
 *   the page in a few short lines, separated by ` | `.
 * - `![alt](shot:name)` on a line of its own is a product screenshot, taken on
 *   a computer and on a phone (`src/docs/captures.json` says which). Adjacent
 *   ones share a row.
 * - `[[key]]` in the text points at the part of a screenshot in the same
 *   section that the capture marked as `key`. Both show the same number,
 *   counted per section and per device, since a phone may not show everything.
 * - A `##` heading starts a section, which in a guide is a step. A section called
 *   "Frequently asked questions" or "Häufige Fragen" holds `###` questions, which
 *   leave the body and become the page's FAQ.
 * - A link starting with `/` stays in the page's language.
 */
import MarkdownIt from 'markdown-it'
import { readFileSync } from 'node:fs'
import type { Plugin } from 'vite'

import type {
  Captures,
  Doc,
  DocBlock,
  DocDevice,
  DocFaqItem,
  DocMark,
  DocSection,
  DocShot,
} from '../src/lib/doc-types.ts'

const DEFAULT_LOCALE = 'en'
const FAQ_HEADINGS = new Set(['frequently asked questions', 'häufige fragen'])
const SHOT_LINE = /^!\[([^\]]*)\]\(shot:([a-z0-9-]+)\)\s*$/
const MARK = /\[\[([a-z0-9-]+)\]\]/g
// The space before a mark goes into it, so a mark a device hides leaves none behind.
const MARK_IN_HTML = /\s?\[\[([a-z0-9-]+)\]\]/g
const DEVICES: DocDevice[] = ['desktop', 'phone']

const fileOf = (name: string, device: DocDevice) => (device === 'phone' ? `${name}-phone` : name)

function renderer(locale: string): MarkdownIt {
  const md = new MarkdownIt({ html: false, linkify: false, typographer: false })
  md.renderer.rules.link_open = (tokens, idx, options, _env, self) => {
    const token = tokens[idx]!
    const href = token.attrGet('href') ?? ''
    if (href.startsWith('/')) {
      if (locale !== DEFAULT_LOCALE) token.attrSet('href', `/${locale}${href}`)
    } else {
      token.attrSet('target', '_blank')
      token.attrSet('rel', 'noopener')
    }
    return self.renderToken(tokens, idx, options)
  }
  return md
}

function parseFrontMatter(raw: string, source: string) {
  const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/)
  if (!match) throw new Error(`${source}: no front matter`)
  const meta: Record<string, string> = {}
  for (const line of match[1]!.split(/\r?\n/)) {
    const colon = line.indexOf(':')
    if (colon > 0) meta[line.slice(0, colon).trim()] = line.slice(colon + 1).trim()
  }
  return { meta, body: match[2]! }
}

function toPlainText(html: string): string {
  return html
    .replace(/<[^>]+>/g, ' ')
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/\s+/g, ' ')
    .replace(/\s([.,:;!?])/g, '$1')
    .trim()
}

/** An anchor from a heading: "Marken einlösen" → `marken-einloesen`. Unique per page. */
function slugger() {
  const seen = new Map<string, number>()
  return (heading: string) => {
    const base = heading
      .toLowerCase()
      .replace(/ä/g, 'ae')
      .replace(/ö/g, 'oe')
      .replace(/ü/g, 'ue')
      .replace(/ß/g, 'ss')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
    const count = (seen.get(base) ?? 0) + 1
    seen.set(base, count)
    return count === 1 ? base : `${base}-${count}`
  }
}

/**
 * The marks a section's text points at, numbered per device in the order the
 * text first names them. A mark counts on a device if one of the section's
 * screenshots shows it there.
 */
function numberMarks(lines: string[], names: string[], captures: Captures) {
  const keys = [...new Set(lines.flatMap((line) => [...line.matchAll(MARK)].map((m) => m[1]!)))]
  const numbers = new Map<DocDevice, Map<string, number>>()
  for (const device of DEVICES) {
    const shown = keys.filter((key) =>
      names.some((name) => captures[fileOf(name, device)]?.marks[key]),
    )
    numbers.set(device, new Map(shown.map((key, index) => [key, index + 1])))
  }
  return { keys, numbers }
}

/** A mark in the text. Its number comes from CSS, for the device the page shows. */
function markHtml(key: string, numbers: Map<DocDevice, Map<string, number>>): string {
  const counts = DEVICES.map((device) => [device, numbers.get(device)!.get(key)] as const)
    .filter(([, n]) => n)
    .map(([device, n]) => ` data-${device}="${n}"`)
    .join('')
  return `<span class="doc-mark" data-mark="${key}"${counts} aria-hidden="true"></span>`
}

/** Markdown lines into text and screenshot blocks, with adjacent screenshots in one row. */
function toBlocks(lines: string[], md: MarkdownIt, captures: Captures): DocBlock[] {
  const shotLines = lines.map((line) => line.match(SHOT_LINE))
  const names = shotLines.flatMap((shot) => (shot ? [shot[2]!] : []))
  const { keys, numbers } = numberMarks(
    lines.filter((_, index) => !shotLines[index]),
    names,
    captures,
  )

  const shotOf = (alt: string, name: string): DocShot => {
    const devices: DocShot['devices'] = {}
    for (const device of DEVICES) {
      const capture = captures[fileOf(name, device)]
      if (!capture) continue
      devices[device] = keys.flatMap((key): DocMark[] => {
        const place = capture.marks[key]
        return place ? [{ key, n: numbers.get(device)!.get(key)!, ...place }] : []
      })
    }
    // Not in the list of captures: shown as it always was, from the computer.
    if (!devices.desktop && !devices.phone) devices.desktop = []
    return { name, alt, devices }
  }

  const blocks: DocBlock[] = []
  let text: string[] = []

  const flushText = () => {
    const source = text.join('\n').trim()
    text = []
    if (!source) return
    const html = md.render(source).replace(MARK_IN_HTML, (_, key: string) => markHtml(key, numbers))
    blocks.push({ type: 'html', html })
  }

  for (const [index, line] of lines.entries()) {
    const shot = shotLines[index]
    if (shot) {
      flushText()
      const item = shotOf(shot[1]!, shot[2]!)
      const last = blocks.at(-1)
      if (last?.type === 'shots') last.shots.push(item)
      else blocks.push({ type: 'shots', shots: [item] })
    } else {
      text.push(line)
    }
  }
  flushText()
  return blocks
}

function blocksToText(blocks: DocBlock[]): string {
  return blocks
    .filter((block) => block.type === 'html')
    .map((block) => toPlainText(block.html))
    .join(' ')
}

function parseFaq(lines: string[], md: MarkdownIt, slug: (text: string) => string): DocFaqItem[] {
  const items: { question: string; lines: string[] }[] = []
  for (const line of lines) {
    const heading = line.match(/^### (.+)$/)
    if (heading) items.push({ question: heading[1]!.trim(), lines: [] })
    else items.at(-1)?.lines.push(line)
  }
  return items.map(({ question, lines: answer }) => {
    const html = md.render(answer.join('\n').trim())
    return { id: `faq-${slug(question)}`, question, html, text: toPlainText(html) }
  })
}

/**
 * `locale` decides what links stay in; `source` names the file in an error.
 * `captures` are the screenshots taken in that language, with their marks.
 */
export function parseDoc(
  raw: string,
  locale: string,
  source = 'document',
  captures: Captures = {},
): Doc {
  const { meta, body } = parseFrontMatter(raw, source)
  if (!meta.title) throw new Error(`${source}: no title in the front matter`)
  if (!meta.lede) throw new Error(`${source}: no lede in the front matter`)

  const md = renderer(locale)
  const slug = slugger()
  const intro: string[] = []
  const chunks: { title: string; lines: string[] }[] = []

  for (const line of body.split(/\r?\n/)) {
    const heading = line.match(/^## (.+)$/)
    if (heading) chunks.push({ title: heading[1]!.trim(), lines: [] })
    else (chunks.at(-1)?.lines ?? intro).push(line)
  }

  const sections: DocSection[] = []
  let faq: DocFaqItem[] = []
  for (const chunk of chunks) {
    if (FAQ_HEADINGS.has(chunk.title.toLowerCase())) {
      faq = parseFaq(chunk.lines, md, slug)
      continue
    }
    const blocks = toBlocks(chunk.lines, md, captures)
    sections.push({ id: slug(chunk.title), title: chunk.title, text: blocksToText(blocks), blocks })
  }

  return {
    title: meta.title,
    lede: meta.lede,
    related: (meta.related ?? '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
    points: (meta.points ?? '')
      .split(' | ')
      .map((item) => item.trim())
      .filter(Boolean),
    intro: toBlocks(intro, md, captures),
    sections,
    faq,
  }
}

/** What `just screenshots` took, by language, from `captures.json` beside the pages. */
function readCaptures(file: string): Record<string, Captures> {
  return JSON.parse(readFileSync(file, 'utf-8')) as Record<string, Captures>
}

export function docsPlugin(): Plugin {
  return {
    name: 'wirksam-docs',
    enforce: 'pre',
    transform(code, id) {
      const path = id.split('?')[0]!.replace(/\\/g, '/')
      const match = path.match(/^(.*\/src\/docs\/)([a-z]+)\/.+\.md$/)
      if (!match) return null
      const captures = `${match[1]}captures.json`
      // A new capture moves the marks, so the pages are read again with it.
      this.addWatchFile(captures)
      const locale = match[2]!
      const doc = parseDoc(code, locale, path, readCaptures(captures)[locale] ?? {})
      return { code: `export default ${JSON.stringify(doc)}`, map: null }
    },
  }
}
