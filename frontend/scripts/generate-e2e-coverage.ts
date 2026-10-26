/**
 * Generates the E2E test inventory in `e2e/COVERAGE.md`.
 *
 * Reads:   `playwright test --list --reporter=json` (collection only — this
 *          starts no web server and no browser, so it is safe anywhere)
 * Writes:  e2e/COVERAGE.md
 *
 * Every number in the output is derived from the Playwright listing, so the
 * file cannot drift the way a hand-maintained one does. The output is
 * deterministic — projects and files are sorted, paths are repo-relative and
 * there are no timestamps — so CI can regenerate it and fail on any diff.
 *
 * Run: pnpm generate-e2e-coverage
 */
import { spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import process from 'node:process'

const FRONTEND_DIR = resolve(import.meta.dirname, '..')
const OUTPUT_FILE = join(FRONTEND_DIR, 'e2e', 'COVERAGE.md')
const PLAYWRIGHT_CLI = join(FRONTEND_DIR, 'node_modules', '@playwright', 'test', 'cli.js')

/** Playwright reports spec paths relative to `testDir`; make them repo-relative. */
const TEST_DIR_FROM_REPO_ROOT = 'frontend/e2e'

const REPO_URL = 'https://github.com/Blaxzter/wirksam'
const FENCE = '```'

// ── Playwright JSON reporter shapes (only the fields we consume) ────────────

interface ListedTest {
  projectName: string
}

interface ListedSpec {
  title: string
  file: string
  line: number
  tests: ListedTest[]
}

interface ListedSuite {
  title: string
  file?: string
  specs?: ListedSpec[]
  suites?: ListedSuite[]
}

interface ListReport {
  suites: ListedSuite[]
  errors: unknown[]
}

/** One test, flattened out of the nested suite tree. */
interface Entry {
  project: string
  /** Repo-relative spec path. */
  file: string
  /** Enclosing `test.describe` titles, outermost first. */
  describes: string[]
  title: string
}

// ── Collection ─────────────────────────────────────────────────────────────

function listTests(): ListReport {
  if (!existsSync(PLAYWRIGHT_CLI)) {
    console.error(`Playwright CLI not found at ${PLAYWRIGHT_CLI}. Run \`pnpm install\` first.`)
    process.exit(1)
  }

  const tempDir = mkdtempSync(join(tmpdir(), 'e2e-coverage-'))
  const jsonPath = join(tempDir, 'list.json')

  try {
    const result = spawnSync(
      process.execPath,
      [PLAYWRIGHT_CLI, 'test', '--list', '--reporter=json'],
      {
        cwd: FRONTEND_DIR,
        env: {
          ...process.env,
          // Write the report to a file rather than stdout: dotenv prints a
          // banner to stdout, which would otherwise sit in front of the JSON.
          PLAYWRIGHT_JSON_OUTPUT_NAME: jsonPath,
        },
        encoding: 'utf-8',
        // stdout is the (redundant) JSON dump; let stderr through so Playwright
        // collection errors are visible.
        stdio: ['ignore', 'ignore', 'inherit'],
      },
    )

    if (result.error) {
      console.error(`Failed to run Playwright: ${result.error.message}`)
      process.exit(1)
    }
    if (result.status !== 0) {
      console.error(`\`playwright test --list\` exited with code ${result.status}.`)
      process.exit(1)
    }
    if (!existsSync(jsonPath)) {
      console.error('Playwright produced no JSON report.')
      process.exit(1)
    }

    return JSON.parse(readFileSync(jsonPath, 'utf-8')) as ListReport
  } finally {
    rmSync(tempDir, { recursive: true, force: true })
  }
}

function flatten(report: ListReport): Entry[] {
  const entries: Entry[] = []

  // The top level of `suites` is one entry per spec file; anything below it is
  // a `test.describe`. Recurse so arbitrarily nested describes keep working.
  const walk = (suite: ListedSuite, describes: string[]) => {
    for (const spec of suite.specs ?? []) {
      for (const test of spec.tests) {
        entries.push({
          project: test.projectName,
          file: `${TEST_DIR_FROM_REPO_ROOT}/${spec.file}`,
          describes,
          title: spec.title,
        })
      }
    }
    for (const child of suite.suites ?? []) {
      walk(child, [...describes, child.title])
    }
  }

  for (const fileSuite of report.suites) {
    walk(fileSuite, [])
  }

  return entries
}

// ── Rendering ──────────────────────────────────────────────────────────────

/** Groups preserving insertion order of the values, keyed for later sorting. */
function groupBy<T>(items: T[], key: (item: T) => string): Map<string, T[]> {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const group = groups.get(key(item))
    if (group) group.push(item)
    else groups.set(key(item), [item])
  }
  return groups
}

function sortedKeys<T>(groups: Map<string, T[]>): string[] {
  return [...groups.keys()].sort((a, b) => a.localeCompare(b, 'en'))
}

/** Renders a left-aligned markdown table with padded cells (Prettier's shape). */
function table(headers: string[], rows: string[][]): string {
  const widths = headers.map((header, i) =>
    Math.max(3, header.length, ...rows.map((row) => row[i].length)),
  )
  const row = (cells: string[]) =>
    `| ${cells.map((cell, i) => cell.padEnd(widths[i])).join(' | ')} |`
  const divider = `| ${widths.map((width) => '-'.repeat(width)).join(' | ')} |`
  return [row(headers), divider, ...rows.map(row)].join('\n')
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}

function renderHeader(): string[] {
  return [
    '# E2E Test Coverage',
    '',
    '<!-- Generated by frontend/scripts/generate-e2e-coverage.ts — do not edit by hand. -->',
    '',
    'A complete inventory of the Playwright E2E suite: every project, every spec file, every test',
    'title. All counts are derived from Playwright itself, so this file cannot drift out of sync',
    'with the tests the way a hand-maintained list does.',
    '',
    'Regenerate it after adding, renaming or removing tests:',
    '',
    `${FENCE}bash`,
    'just generate-e2e-coverage      # or: pnpm --prefix frontend generate-e2e-coverage',
    FENCE,
    '',
    'The generator shells out to `playwright test --list`, which only _collects_ tests — it starts',
    'no web server and no browser, so it needs neither a running stack nor installed browsers.',
    '`.github/workflows/lint-frontend.yml` regenerates this file on every PR and fails if the',
    'committed copy differs.',
    '',
    'There is one mode and one project list, so the inventory does not depend on a local',
    '`frontend/.env` — see [README.md](./README.md).',
    '',
    '## Gaps',
    '',
    'Known gaps live in GitHub issues, not in this file — a hand-written "not covered" list goes',
    'stale the moment someone writes the missing test. Open coverage issues:',
    '',
    `- [#149](${REPO_URL}/issues/149) — the date picker freezes the page on an arrow key. The`,
    '  keyboard test for it exists and is written correctly, but is marked `test.fixme()`',
    '  (it wedges the renderer rather than failing an assertion). Remove the `fixme` when fixed.',
    `- [#148](${REPO_URL}/issues/148) — the light theme fails WCAG AA contrast via four theme`,
    '  tokens. `color-contrast` is the one axe rule the a11y suite defers; every other',
    '  serious/critical rule is enforced at zero.',
    '',
    'Not yet covered, and not currently tracked by an issue:',
    '',
    '- User-management table pagination — needs enough seeded users to page. Listed in #136 but',
    '  outside its acceptance criteria; the disposable-user fixture this would build on now exists.',
    '',
  ]
}

function renderSummary(entries: Entry[]): string[] {
  const byProject = groupBy(entries, (entry) => entry.project)
  const rows = sortedKeys(byProject).map((project) => {
    const projectEntries = byProject.get(project) ?? []
    const files = new Set(projectEntries.map((entry) => entry.file))
    return [`\`${project}\``, String(files.size), String(projectEntries.length)]
  })

  const allFiles = new Set(entries.map((entry) => entry.file))
  rows.push(['**Total**', `**${allFiles.size}**`, `**${entries.length}**`])

  return ['## Summary', '', table(['Project', 'Spec files', 'Tests'], rows), '']
}

function renderInventory(entries: Entry[]): string[] {
  const lines = ['## Inventory', '']

  const byProject = groupBy(entries, (entry) => entry.project)
  for (const project of sortedKeys(byProject)) {
    const projectEntries = byProject.get(project) ?? []
    const byFile = groupBy(projectEntries, (entry) => entry.file)
    const fileCount = plural(byFile.size, 'file')
    const testCount = plural(projectEntries.length, 'test')

    lines.push(`### Project \`${project}\` — ${fileCount}, ${testCount}`, '')

    for (const file of sortedKeys(byFile)) {
      const fileEntries = byFile.get(file) ?? []
      lines.push(`#### \`${file}\` — ${plural(fileEntries.length, 'test')}`, '')

      // Describe blocks stay in declaration order; only projects and files are
      // sorted, so a reordered file shows up as a real diff.
      const byDescribe = groupBy(fileEntries, (entry) => entry.describes.join(' › '))
      for (const [describe, describeEntries] of byDescribe) {
        if (describe === '') {
          for (const entry of describeEntries) lines.push(`- ${entry.title}`)
        } else {
          lines.push(`- **${describe}** (${describeEntries.length})`)
          for (const entry of describeEntries) lines.push(`  - ${entry.title}`)
        }
      }
      lines.push('')
    }
  }

  return lines
}

// ── Main ───────────────────────────────────────────────────────────────────

const report = listTests()
if (report.errors.length > 0) {
  console.error('Playwright reported collection errors:')
  console.error(JSON.stringify(report.errors, null, 2))
  process.exit(1)
}

const entries = flatten(report)
if (entries.length === 0) {
  console.error('Playwright listed no tests — refusing to write an empty inventory.')
  process.exit(1)
}

const markdown = [...renderHeader(), ...renderSummary(entries), ...renderInventory(entries)]
  .join('\n')
  .replace(/\n{3,}/g, '\n\n')
  .trimEnd()

writeFileSync(OUTPUT_FILE, `${markdown}\n`)

const files = new Set(entries.map((entry) => entry.file))
console.log(`${entries.length} tests across ${files.size} spec files → ${OUTPUT_FILE}`)
