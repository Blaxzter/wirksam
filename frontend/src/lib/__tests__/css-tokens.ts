import { readFileSync } from 'node:fs'

import { type Rgb, oklchToLinearRgb } from '@/lib/colour-math'

/**
 * Reading colour tokens out of `index.css` and measuring their WCAG 2.x
 * contrast, for the specs that guard the venue map and the event colours.
 * The arithmetic is the app's own (`lib/colour-math.ts`), which derives an
 * event's own colours at runtime.
 */
export { type Rgb, contrast, oklchToLinearRgb, over } from '@/lib/colour-math'

// Read from disk: Vitest hands CSS imports (`?raw` included) back empty.
export const css = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')

export type Tokens = Map<string, string>

/**
 * Every `--name: value;` of every top-level rule whose selector list matches,
 * in `index.css` or in other CSS (the rules generated for an own colour).
 */
export function declarations(selector: (sel: string) => boolean, from: string = css): Tokens {
  const out: Tokens = new Map()
  // Top-level rules only (a rule inside `@media print` follows a `{`, not a
  // `}`): comments stripped, then `selector { body }` with no nesting.
  const source = from.replace(/\/\*[\s\S]*?\*\//g, '')
  const rule = /(?<=^|\})\s*([^{}@]+?)\s*\{([^{}]*)\}/g
  for (const match of source.matchAll(rule)) {
    const selectors = match[1]!.split(',').map((s) => s.trim())
    if (!selectors.some(selector)) continue
    for (const decl of match[2]!.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      out.set(decl[1]!, decl[2]!.trim())
    }
  }
  return out
}

/**
 * A token's colour, following `var(--other)` references, also numbers
 * spliced into an `oklch()` (`oklch(0.17 0.01 var(--hue))`), a fallback
 * (`var(--hue, 80)`) and a product (`calc(0.018 * var(--strength))`).
 */
export function colour(tokens: Tokens, name: string, seen: string[] = []): Rgb {
  const declared = tokens.get(name)
  if (!declared) throw new Error(`${name} is not declared`)
  const ref = /^var\((--[\w-]+)\)$/.exec(declared)
  if (ref) {
    if (seen.includes(ref[1]!)) throw new Error(`cycle at ${name}`)
    return colour(tokens, ref[1]!, [...seen, name])
  }
  let raw = declared
  // Innermost first, until none are left: a value may itself be a var().
  for (let depth = 0; raw.includes('var('); depth++) {
    if (depth > 10) throw new Error(`${name}: too deeply nested`)
    raw = raw.replace(
      /var\((--[\w-]+)(?:,\s*([^()]+))?\)/g,
      (_, inner: string, fallback?: string) => {
        const value = tokens.get(inner) ?? fallback?.trim()
        if (!value) throw new Error(`${name}: ${inner} is not declared`)
        return value
      },
    )
  }
  raw = raw.replace(
    /calc\(\s*([\d.]+)\s*\*\s*([\d.]+)\s*\)/g,
    (_, a: string, b: string) => `${Number(a) * Number(b)}`,
  )
  const m = /^oklch\(\s*([\d.]+)\s+([\d.e-]+)\s+([\d.]+)\s*\)$/.exec(raw)
  if (!m) throw new Error(`${name}: cannot parse "${raw}"`)
  return oklchToLinearRgb(Number(m[1]), Number(m[2]), Number(m[3]))
}
