import { describe, expect, it } from 'vitest'

import { renderMarkdown } from '@/lib/markdown'

/**
 * Location descriptions are written by event admins and rendered with `v-html`
 * for every member, so the escaping is the part that matters — not the
 * formatting.
 */
describe('renderMarkdown', () => {
  it.each([
    ['null', null],
    ['undefined', undefined],
    ['empty', ''],
    ['whitespace only', '  \n '],
  ])('returns an empty string for %s input', (_label, src) => {
    expect(renderMarkdown(src)).toBe('')
  })

  it('renders basic formatting', () => {
    const html = renderMarkdown('**Hall B**, first floor\n\n- left door\n- right door')
    expect(html).toContain('<strong>Hall B</strong>')
    expect(html).toContain('<li>left door</li>')
  })

  it('turns single line breaks into <br>', () => {
    expect(renderMarkdown('one\ntwo')).toContain('one<br>\ntwo')
  })

  it('escapes raw HTML instead of passing it through', () => {
    const html = renderMarkdown('<script>alert(1)</script><img src=x onerror=alert(1)>')
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;script&gt;')
  })

  it('opens links in a new tab without opener or ranking credit', () => {
    const html = renderMarkdown('[Map](https://example.com/map)')
    expect(html).toContain('href="https://example.com/map"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer nofollow"')
  })

  it('linkifies bare URLs with the same attributes', () => {
    const html = renderMarkdown('See https://example.com for parking')
    expect(html).toContain('<a href="https://example.com"')
    expect(html).toContain('target="_blank"')
  })

  it('does not load images, so readers never fetch an author-chosen URL', () => {
    const html = renderMarkdown('![plan](https://tracker.example/pixel.png)')
    expect(html).not.toContain('<img')
  })

  it('does not render a javascript: link as an href', () => {
    const html = renderMarkdown('[click](javascript:alert(1))')
    expect(html).not.toContain('href="javascript:')
    expect(html).not.toContain('<a ')
  })
})
