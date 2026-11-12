import { describe, expect, it } from 'vitest'

import { offersChoice, preferredDevice, shotDevice, shotFile } from '../doc-shots'
import type { DocShot } from '../doc-types'

const shot = (devices: DocShot['devices']): DocShot => ({ name: 'tasks', alt: 'Tasks', devices })

describe('screenshots on a computer and on a phone', () => {
  it('names the phone capture after the screen', () => {
    expect(shotFile('tasks', 'desktop')).toBe('tasks')
    expect(shotFile('tasks', 'phone')).toBe('tasks-phone')
  })

  it('shows the device asked for, or the other one if it was not taken on it', () => {
    const both = shot({ desktop: [], phone: [] })
    expect(shotDevice(both, 'desktop')).toBe('desktop')
    expect(shotDevice(both, 'phone')).toBe('phone')
    expect(shotDevice(shot({ desktop: [] }), 'phone')).toBe('desktop')
    expect(shotDevice(shot({ phone: [] }), 'desktop')).toBe('phone')
  })

  it('offers a choice only where a screen was taken on both', () => {
    expect(offersChoice([shot({ desktop: [] }), shot({ phone: [] })])).toBe(false)
    expect(offersChoice([shot({ desktop: [] }), shot({ desktop: [], phone: [] })])).toBe(true)
    expect(offersChoice([])).toBe(false)
  })

  it("starts with the visitor's last choice, or else what they are reading on", () => {
    expect(preferredDevice('phone', false)).toBe('phone')
    expect(preferredDevice('desktop', true)).toBe('desktop')
    expect(preferredDevice(null, true)).toBe('phone')
    expect(preferredDevice(null, false)).toBe('desktop')
    expect(preferredDevice('tablet', true)).toBe('phone')
  })
})
