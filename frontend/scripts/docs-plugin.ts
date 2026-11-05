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
 * - Front matter with `title`, `lede` and optionally `related`.
 * - `![alt](shot:name)` on a line of its own is a product screenshot, and
 *   `![alt](phone:name)` one taken on a phone. Adjacent ones share a row.
 * - A `##` heading starts a section, which in a guide is a step. A section called
 *   "Frequently asked questions" or "Häufige Fragen" holds `###` questions, which
 *   leave the body and become the page's FAQ.
 * - A link starting with `/` stays in the page's language.
 */
import MarkdownIt from 'markdown-it'
import type { Plugin } from 'vite'

import type { Doc, DocBlock, DocFaqItem, DocSection, DocShot } from '../src/lib/doc-types.ts'

const DEFAULT_LOCALE = 'en'
const FAQ_HEADINGS = new Set(['frequently asked questions', 'häufige fragen'])
const SHOT_LINE = /^!\[([^\]]*)\]\((shot|phone):([a-z0-9-]+)\)\s*$/

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

/** Markdown lines into text and screenshot blocks, with adjacent screenshots in one row. */
function toBlocks(lines: string[], md: MarkdownIt): DocBlock[] {
  const blocks: DocBlock[] = []
  let text: string[] = []

  const flushText = () => {
    const source = text.join('\n').trim()
    text = []
    if (source) blocks.push({ type: 'html', html: md.render(source) })
  }

  for (const line of lines) {
    const shot = line.match(SHOT_LINE)
    if (shot) {
      flushText()
      const item: DocShot = { alt: shot[1]!, phone: shot[2] === 'phone', name: shot[3]! }
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

/** `locale` decides what links stay in; `source` names the file in an error. */
export function parseDoc(raw: string, locale: string, source = 'document'): Doc {
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
    const blocks = toBlocks(chunk.lines, md)
    sections.push({ id: slug(chunk.title), title: chunk.title, text: blocksToText(blocks), blocks })
  }

  return {
    title: meta.title,
    lede: meta.lede,
    related: (meta.related ?? '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
    intro: toBlocks(intro, md),
    sections,
    faq,
  }
}

export function docsPlugin(): Plugin {
  return {
    name: 'wirksam-docs',
    enforce: 'pre',
    transform(code, id) {
      const path = id.split('?')[0]!.replace(/\\/g, '/')
      const match = path.match(/\/src\/docs\/([a-z]+)\/.+\.md$/)
      if (!match) return null
      return {
        code: `export default ${JSON.stringify(parseDoc(code, match[1]!, path))}`,
        map: null,
      }
    },
  }
}
