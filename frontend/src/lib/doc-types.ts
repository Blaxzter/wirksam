/**
 * What a feature page or guide looks like once `scripts/docs-plugin.ts` has
 * turned its Markdown into data. Types only, so the build plugin and the app can
 * share them without the app importing anything from `scripts/`.
 */

/** One product screenshot, see `components/landing/ScreenshotFrame.vue`. */
export interface DocShot {
  /** File basename, without the `-light`/`-dark` suffix or extension. */
  name: string
  alt: string
  /** Captured on a phone: taller than wide, and shown narrower. */
  phone: boolean
}

export type DocBlock = { type: 'html'; html: string } | { type: 'shots'; shots: DocShot[] }

export interface DocSection {
  /** The anchor, made from the heading. */
  id: string
  title: string
  /** The section as plain text, for structured data. */
  text: string
  blocks: DocBlock[]
}

export interface DocFaqItem {
  id: string
  question: string
  /** The answer as plain text, for FAQPage structured data. */
  text: string
  html: string
}

export interface Doc {
  title: string
  /** The first paragraph, which should already answer the page's question. */
  lede: string
  /** Other pages to read next, as `feature/<slug>` or `guide/<slug>`. */
  related: string[]
  /** What stands before the first `##` heading. */
  intro: DocBlock[]
  /** One per `##` heading. In a guide, these are the steps. */
  sections: DocSection[]
  faq: DocFaqItem[]
}
