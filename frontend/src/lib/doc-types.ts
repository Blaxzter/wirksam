/**
 * What a feature page or guide looks like once `scripts/docs-plugin.ts` has
 * turned its Markdown into data. Types only, so the build plugin and the app can
 * share them without the app importing anything from `scripts/`.
 */

/** What a screenshot was taken on: a 1440x900 window, or a 390x844 phone. */
export type DocDevice = 'desktop' | 'phone'

/** Left, top, width and height of a part of a capture, each a share of the capture's size. */
export type MarkBox = [number, number, number, number]

/**
 * The centre of a mark's number, as shares of the capture's size. Picked when
 * the capture is taken, beside the part where nothing else is, so the number
 * never covers what it points at.
 */
export type MarkPin = [number, number]

/** Where a marked part is on a capture, and where its number sits. */
export interface MarkPlace {
  box: MarkBox
  pin: MarkPin
}

/**
 * What `just screenshots` took in one language, by file name (`tasks`,
 * `tasks-phone`), with where each marked part ended up. Written by
 * `scripts/take-screenshots.ts` into `src/docs/captures.json`.
 */
export type Captures = Record<string, { marks: Record<string, MarkPlace> }>

/** A part of a screenshot that the text points at, with the number both show. */
export interface DocMark extends MarkPlace {
  key: string
  n: number
}

/** One product screenshot, see `components/landing/ScreenshotFrame.vue`. */
export interface DocShot {
  /** The screen: file basename, without `-phone`, the `-light`/`-dark` suffix or extension. */
  name: string
  alt: string
  /** The captures there are of it, each with the marks the text around it points at. */
  devices: Partial<Record<DocDevice, DocMark[]>>
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
  /** The page in a few short lines, shown in a box above the text. Empty on a page without one. */
  points: string[]
  /** What stands before the first `##` heading. */
  intro: DocBlock[]
  /** One per `##` heading. In a guide, these are the steps. */
  sections: DocSection[]
  faq: DocFaqItem[]
}
