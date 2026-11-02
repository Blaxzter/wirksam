/**
 * Accessibility helpers for the E2E suite (issue #138).
 *
 * The suite is built on shadcn-vue / reka-ui, which ships solid a11y primitives
 * that are easy to lose when a component is customised. These helpers make an
 * axe-core scan a one-liner so every route can afford one:
 *
 *   await expectNoA11yViolations(page)
 *
 * Only `serious` and `critical` findings fail a test. Gating on `moderate` and
 * `minor` floods the report with cosmetic noise, and a noisy check is a check
 * that gets switched off. Tightening the bar later is a one-line change to
 * BLOCKING_IMPACTS below.
 *
 * axe is static analysis — it cannot tell you whether a dialog traps focus or
 * whether a date picker is reachable from the keyboard. The keyboard helpers at
 * the bottom of this file cover that half.
 */
import { AxeBuilder } from '@axe-core/playwright'
import { type Page, expect } from '@playwright/test'

/**
 * Result types are derived from AxeBuilder rather than imported from `axe-core`.
 * `axe-core` is a transitive dependency of `@axe-core/playwright` and is not
 * resolvable from here under pnpm's strict node_modules layout.
 */
type AxeResults = Awaited<ReturnType<AxeBuilder['analyze']>>
export type A11yViolation = AxeResults['violations'][number]
type A11yNode = A11yViolation['nodes'][number]

/** Violation impacts that fail a test. Everything else is reported by axe but ignored. */
const BLOCKING_IMPACTS: ReadonlySet<string> = new Set(['serious', 'critical'])

/**
 * WCAG 2.0 + 2.1, levels A and AA — the conformance target for a public
 * volunteer-facing app. `best-practice` is deliberately excluded: those rules
 * are opinions, not requirements, and they are the main source of noise.
 */
export const DEFAULT_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] as const

/** The string a passing scan compares against, so failures diff into a readable report. */
const PASS = 'no serious or critical accessibility violations'

/** Cap the per-violation element list so a systemic failure stays readable. */
const MAX_NODES_PER_VIOLATION = 5

/**
 * `vite-plugin-vue-devtools` injects an overlay into every page in dev mode. It
 * is not our markup and cannot be fixed here, so it is excluded when present.
 * CI runs against `pnpm preview` (a production build) where it does not exist,
 * but the local Docker E2E stack uses Dockerfile.dev and does have it.
 *
 * These ids were read off the running app, not guessed — both are direct
 * children of <body>. Excluding by selector (rather than disabling the rules)
 * keeps <html> in scope, which matters because `html-has-lang` fires there.
 * Verified: excluding these drops 6 phantom `aria-prohibited-attr` nodes that
 * belong to the devtools panel.
 */
const DEV_OVERLAY_SELECTORS = ['#__vue-devtools-container__', '#vue-inspector-container']

export interface DisabledRule {
  /** axe rule id, e.g. `color-contrast`. */
  id: string
  /**
   * Why this rule cannot apply to this scan.
   *
   * Required on purpose. "Any rule that must be disabled carries an inline
   * comment explaining why" is an acceptance criterion of #138, so the type
   * signature asks for the justification instead of trusting reviewers to
   * notice it is missing.
   */
  reason: string
}

export interface A11yScanOptions {
  /** Restrict the scan to these CSS selectors (e.g. `[role="dialog"]`). */
  include?: string | string[]
  /** Drop these CSS selectors from the scan. */
  exclude?: string | string[]
  /** Override the rule tags to run. Defaults to {@link DEFAULT_TAGS}. */
  tags?: readonly string[]
  /** Rules to switch off for this scan. Every entry must carry a reason. */
  disableRules?: DisabledRule[]
  /** Name used in the failure message. Defaults to the current path. */
  label?: string
}

function toArray(value: string | string[] | undefined): string[] {
  if (!value) return []
  return Array.isArray(value) ? value : [value]
}

/** Validate `disableRules` and return the bare rule ids for AxeBuilder. */
function ruleIdsWithReasons(rules: DisabledRule[]): string[] {
  return rules.map((rule) => {
    const id = rule.id.trim()
    const reason = rule.reason.trim()
    if (!id) {
      throw new Error('a11y: every disableRules entry needs an axe rule id.')
    }
    if (!reason) {
      throw new Error(
        `a11y: refusing to disable axe rule "${id}" without a reason. ` +
          'Pass { id, reason } and explain why the rule cannot apply here.',
      )
    }
    return id
  })
}

/**
 * Let any fading-in overlay finish before axe measures colours.
 *
 * `color-contrast` reads *computed* colours, so an element caught mid-transition
 * is measured at whatever opacity it happens to have: the cookie notice
 * (`transition duration-300`) reported 3.94:1 and 4.45:1 on the about and
 * how-it-works scans, which is `text-muted-foreground` on `bg-card` composited
 * at ~0.75 and ~0.80 — the settled pair is 7.34:1 and passes comfortably. That
 * is an intermittent failure, not a defect, and it only became visible once
 * #148 turned the rule on.
 *
 * Waiting rather than dismissing the notice: it is part of what an anonymous
 * visitor sees, so it belongs in the scan.
 *
 * Toasts fade in the same way (400 ms). The organiser's dashboard raises one
 * ("4 people are waiting to join") the moment its feed arrives, which is when
 * a scan that waits for the cards starts: its "Review" button came out at
 * 4.35:1 mid-fade, against about 8:1 once it has settled.
 */
async function settleOverlays(page: Page): Promise<void> {
  const notice = page.getByTestId('cookie-notice')
  if ((await notice.count()) > 0) await expect(notice).toHaveCSS('opacity', '1')
  for (const toast of await page.locator('[data-sonner-toast][data-visible="true"]').all()) {
    await expect(toast).toHaveCSS('opacity', '1')
  }
}

/** Only exclude dev-only overlays that are actually on the page. */
async function presentDevOverlays(page: Page): Promise<string[]> {
  const present: string[] = []
  for (const selector of DEV_OVERLAY_SELECTORS) {
    if ((await page.locator(selector).count()) > 0) present.push(selector)
  }
  return present
}

function routeLabel(page: Page): string {
  const url = page.url()
  try {
    const parsed = new URL(url)
    return `${parsed.pathname}${parsed.search}`
  } catch {
    return url
  }
}

function formatTarget(node: A11yNode): string {
  return node.target
    .map((part) => (Array.isArray(part) ? part.join(' >> ') : String(part)))
    .join(', ')
}

function formatNode(node: A11yNode): string {
  const lines = [`    - ${formatTarget(node)}`]
  const summary = (node.failureSummary ?? '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .join(' | ')
  if (summary) lines.push(`      ${summary}`)
  return lines.join('\n')
}

function formatViolation(violation: A11yViolation, index: number): string {
  const shown = violation.nodes.slice(0, MAX_NODES_PER_VIOLATION).map(formatNode)
  const hidden = violation.nodes.length - shown.length
  return [
    `${index + 1}. [${violation.impact ?? 'unknown'}] ${violation.id} — ${violation.help}`,
    `   help: ${violation.helpUrl}`,
    `   ${violation.nodes.length} failing element(s):`,
    ...shown,
    ...(hidden > 0 ? [`    ... and ${hidden} more element(s)`] : []),
  ].join('\n')
}

/**
 * Build the actionable failure report: rule id, impact, help URL and the
 * failing selectors. "expected 0 to be 3" tells nobody what to fix.
 */
export function formatViolations(label: string, violations: A11yViolation[]): string {
  const elements = violations.reduce((total, violation) => total + violation.nodes.length, 0)
  return [
    `${violations.length} serious/critical accessibility violation(s) ` +
      `across ${elements} element(s) on ${label}:`,
    '',
    ...violations.map(formatViolation),
  ].join('\n')
}

/** Run axe against the current page state and return the raw results. */
/**
 * Rules deferred repo-wide, with the reason recorded here rather than repeated
 * at ~25 call sites. This list should only ever shrink.
 *
 * Empty since #148: every serious/critical rule, `color-contrast` included, is
 * now enforced at zero. Adding an entry back needs a written reason — see
 * {@link DisabledRule}.
 */
const DEFERRED_RULES: readonly DisabledRule[] = []

export async function scanA11y(page: Page, options: A11yScanOptions = {}): Promise<AxeResults> {
  await settleOverlays(page)

  let builder = new AxeBuilder({ page }).withTags([...(options.tags ?? DEFAULT_TAGS)])

  for (const selector of toArray(options.include)) {
    builder = builder.include(selector)
  }
  for (const selector of [...toArray(options.exclude), ...(await presentDevOverlays(page))]) {
    builder = builder.exclude(selector)
  }

  const disabled = ruleIdsWithReasons([...DEFERRED_RULES, ...(options.disableRules ?? [])])
  if (disabled.length > 0) {
    builder = builder.disableRules(disabled)
  }

  return builder.analyze()
}

/**
 * Fail the test if the current page has any serious or critical a11y violation.
 *
 * @example
 * await page.goto('/app/home')
 * await expect(page.getByTestId('page-heading')).toBeVisible()
 * await expectNoA11yViolations(page)
 */
export async function expectNoA11yViolations(
  page: Page,
  options: A11yScanOptions = {},
): Promise<void> {
  const label = options.label ?? routeLabel(page)
  const results = await scanA11y(page, options)
  const blocking = results.violations.filter((violation) =>
    BLOCKING_IMPACTS.has(violation.impact ?? ''),
  )
  const report = blocking.length === 0 ? PASS : formatViolations(label, blocking)
  expect(report, `axe-core accessibility scan of ${label}`).toBe(PASS)
}

// ── Keyboard / focus helpers ─────────────────────────────────────────────────
// These live here rather than in a spec so the loops and branches they need
// stay out of test bodies (and out of playwright/no-conditional-in-test).

/**
 * `e2e/tsconfig.json` extends @tsconfig/node22, whose `lib` has no `dom`, so
 * `document` is not declared for these files. The callbacks below are
 * serialised and executed in the browser, where the real DOM exists; this is
 * just enough of a type to keep the compiler honest about how it is used.
 */
interface EvalElement {
  readonly tagName: string
  readonly textContent: string | null
  getAttribute(name: string): string | null
  matches(selector: string): boolean
  contains(other: EvalElement | null): boolean
}
declare const document: {
  readonly activeElement: EvalElement | null
  querySelectorAll(selector: string): ArrayLike<EvalElement>
}

/** A short, human-readable description of `document.activeElement`. */
export async function describeFocus(page: Page): Promise<string> {
  return page.evaluate(() => {
    const el = document.activeElement
    if (!el) return '<nothing>'
    const parts: string[] = [el.tagName.toLowerCase()]
    for (const attr of ['data-testid', 'data-slot', 'aria-label', 'type']) {
      const value = el.getAttribute(attr)
      if (value) parts.push(`[${attr}="${value}"]`)
    }
    const text = (el.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, 40)
    if (text) parts.push(`"${text}"`)
    return parts.join(' ')
  })
}

/** True when `document.activeElement` sits inside an element matching `selector`. */
export async function focusIsInside(page: Page, selector: string): Promise<boolean> {
  return page.evaluate((sel) => {
    const active = document.activeElement
    if (!active) return false
    return Array.from(document.querySelectorAll(sel)).some((el) => el.contains(active))
  }, selector)
}

/** Read an attribute off `document.activeElement`, or null if it has none. */
export async function focusedAttribute(page: Page, attribute: string): Promise<string | null> {
  return page.evaluate((attr) => document.activeElement?.getAttribute(attr) ?? null, attribute)
}

/**
 * Press Tab until the focused element matches `selector`.
 *
 * Throws with the element focus actually landed on, which is the information
 * you need when a roving-tabindex widget stops being reachable.
 *
 * @returns how many Tab presses it took.
 */
export async function tabUntilFocused(
  page: Page,
  selector: string,
  maxPresses = 15,
): Promise<number> {
  for (let presses = 1; presses <= maxPresses; presses++) {
    await page.keyboard.press('Tab')
    const matched = await page.evaluate(
      (sel) => document.activeElement?.matches(sel) ?? false,
      selector,
    )
    if (matched) return presses
  }
  throw new Error(
    `Pressed Tab ${maxPresses} times without reaching "${selector}". ` +
      `Focus ended on: ${await describeFocus(page)}`,
  )
}
