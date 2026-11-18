// @vitest-environment jsdom
import { effectScope } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { COPIED_MS, useClipboardCopy } from '@/composables/useClipboardCopy'

/**
 * A copy button's tick: on for a moment after a copy, one at a time, and none
 * when the clipboard refuses.
 */

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useClipboardCopy', () => {
  it('copies the text and ticks its key for a moment', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    stubClipboard(writeText)
    const { copied, copy } = useClipboardCopy<string>()

    await expect(copy('link', 'https://example.org/l/abc')).resolves.toBe(true)

    expect(writeText).toHaveBeenCalledWith('https://example.org/l/abc')
    expect(copied.value).toBe('link')
    vi.advanceTimersByTime(COPIED_MS - 1)
    expect(copied.value).toBe('link')
    vi.advanceTimersByTime(1)
    expect(copied.value).toBeNull()
  })

  it('moves the tick to the newer copy and keeps it for its own moment', async () => {
    stubClipboard(vi.fn().mockResolvedValue(undefined))
    const { copied, copy } = useClipboardCopy<string>()

    await copy('link', 'a')
    vi.advanceTimersByTime(COPIED_MS / 2)
    await copy('text', 'b')
    vi.advanceTimersByTime(COPIED_MS / 2)
    expect(copied.value).toBe('text')
    vi.advanceTimersByTime(COPIED_MS / 2)
    expect(copied.value).toBeNull()
  })

  it('resolves to false and ticks nothing when the clipboard is blocked', async () => {
    stubClipboard(vi.fn().mockRejectedValue(new Error('denied')))
    const { copied, copy } = useClipboardCopy<string>()

    await expect(copy('link', 'a')).resolves.toBe(false)
    expect(copied.value).toBeNull()
  })

  it('stops its timer with the component that used it', async () => {
    stubClipboard(vi.fn().mockResolvedValue(undefined))
    const scope = effectScope()
    const tick = scope.run(() => useClipboardCopy<string>())!

    await tick.copy('link', 'a')
    scope.stop()
    vi.advanceTimersByTime(COPIED_MS)
    expect(tick.copied.value).toBe('link')
  })
})
