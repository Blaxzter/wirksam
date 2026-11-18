// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'

import { firstCheckbox } from '@/lib/focus'

describe('firstCheckbox', () => {
  it('finds the first checkbox that can be ticked', () => {
    const root = document.createElement('div')
    root.innerHTML = `
      <button role="checkbox" disabled data-id="header"></button>
      <button role="checkbox" data-id="row-1"></button>
      <button role="checkbox" data-id="row-2"></button>`
    expect(firstCheckbox(root)?.dataset.id).toBe('row-1')
  })

  it('finds nothing without a root or a checkbox', () => {
    expect(firstCheckbox(undefined)).toBeNull()
    expect(firstCheckbox(document.createElement('div'))).toBeNull()
  })
})
