// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * `useInstallPrompt` keeps its state at module level and `listenForInstallPrompt`
 * attaches its listeners once, so every test starts from a fresh import
 * (`vi.resetModules()`), with the display mode and user agent it needs set up
 * before that import runs the listener.
 */
interface Setup {
  standalone?: boolean
  userAgent?: string
  maxTouchPoints?: number
}

const CHROME_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0'
const IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15'
const IPAD_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15'

async function load({ standalone = false, userAgent = CHROME_UA, maxTouchPoints = 0 }: Setup = {}) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({ matches: standalone && query.includes('standalone') })),
  )
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(userAgent)
  // Not in jsdom at all, so defined rather than spied on.
  Object.defineProperty(navigator, 'maxTouchPoints', { value: maxTouchPoints, configurable: true })
  vi.resetModules()
  const mod = await import('../useInstallPrompt')
  mod.listenForInstallPrompt()
  return mod
}

function firePrompt(outcome: 'accepted' | 'dismissed' = 'accepted') {
  const event = new Event('beforeinstallprompt', { cancelable: true })
  const prompt = vi.fn(() => Promise.resolve())
  Object.assign(event, { prompt, userChoice: Promise.resolve({ outcome, platform: 'web' }) })
  window.dispatchEvent(event)
  return { event, prompt }
}

let listeners: [string, EventListenerOrEventListenerObject][] = []
beforeEach(() => {
  // Each fresh import adds its own window listeners; drop them afterwards so
  // one test's module does not react to the next test's events.
  listeners = []
  const add = window.addEventListener.bind(window)
  vi.spyOn(window, 'addEventListener').mockImplementation((type, listener, options) => {
    listeners.push([type, listener])
    add(type, listener, options)
  })
})

afterEach(() => {
  for (const [type, listener] of listeners) window.removeEventListener(type, listener)
  Reflect.deleteProperty(navigator, 'maxTouchPoints')
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('useInstallPrompt', () => {
  it('offers nothing before the browser fires the prompt', async () => {
    const { useInstallPrompt } = await load()
    const { canInstall, canPrompt, needsManualInstall } = useInstallPrompt()
    expect(canInstall.value).toBe(false)
    expect(canPrompt.value).toBe(false)
    expect(needsManualInstall.value).toBe(false)
  })

  it('keeps the prompt and suppresses the browser mini-infobar', async () => {
    const { useInstallPrompt } = await load()
    const { canInstall, canPrompt } = useInstallPrompt()
    const { event } = firePrompt()
    expect(event.defaultPrevented).toBe(true)
    expect(canPrompt.value).toBe(true)
    expect(canInstall.value).toBe(true)
  })

  it('shares the prompt between callers', async () => {
    const { useInstallPrompt } = await load()
    firePrompt()
    expect(useInstallPrompt().canPrompt.value).toBe(true)
  })

  it('opens the prompt and reports an accepted install', async () => {
    const { useInstallPrompt } = await load()
    const { install, canInstall, installed } = useInstallPrompt()
    const { prompt } = firePrompt('accepted')
    await expect(install()).resolves.toBe(true)
    expect(prompt).toHaveBeenCalledOnce()
    expect(installed.value).toBe(true)
    expect(canInstall.value).toBe(false)
  })

  it('drops a dismissed prompt, which cannot be shown twice', async () => {
    const { useInstallPrompt } = await load()
    const { install, canPrompt, installed } = useInstallPrompt()
    firePrompt('dismissed')
    await expect(install()).resolves.toBe(false)
    expect(canPrompt.value).toBe(false)
    expect(installed.value).toBe(false)
  })

  it('does nothing when asked to install without a prompt', async () => {
    const { useInstallPrompt } = await load()
    await expect(useInstallPrompt().install()).resolves.toBe(false)
  })

  it('hides the offer once the app is installed from elsewhere', async () => {
    const { useInstallPrompt } = await load()
    const { canInstall, installed } = useInstallPrompt()
    firePrompt()
    window.dispatchEvent(new Event('appinstalled'))
    expect(installed.value).toBe(true)
    expect(canInstall.value).toBe(false)
  })

  it('offers nothing when already running as an installed app', async () => {
    const { useInstallPrompt } = await load({ standalone: true })
    const { canInstall, installed } = useInstallPrompt()
    firePrompt()
    expect(installed.value).toBe(true)
    expect(canInstall.value).toBe(false)
  })

  it("treats iOS Safari's home-screen flag as installed", async () => {
    Object.defineProperty(navigator, 'standalone', { value: true, configurable: true })
    try {
      const { useInstallPrompt } = await load({ userAgent: IPHONE_UA })
      expect(useInstallPrompt().installed.value).toBe(true)
      expect(useInstallPrompt().canInstall.value).toBe(false)
    } finally {
      Reflect.deleteProperty(navigator, 'standalone')
    }
  })

  it('points iPhone users to the manual install', async () => {
    const { useInstallPrompt } = await load({ userAgent: IPHONE_UA })
    const { canInstall, canPrompt, needsManualInstall } = useInstallPrompt()
    expect(needsManualInstall.value).toBe(true)
    expect(canPrompt.value).toBe(false)
    expect(canInstall.value).toBe(true)
  })

  it('recognises an iPad, which reports itself as a Mac', async () => {
    const { useInstallPrompt } = await load({ userAgent: IPAD_UA, maxTouchPoints: 5 })
    expect(useInstallPrompt().needsManualInstall.value).toBe(true)
  })

  it('does not take a desktop Mac for an iPad', async () => {
    const { useInstallPrompt } = await load({ userAgent: IPAD_UA, maxTouchPoints: 0 })
    expect(useInstallPrompt().needsManualInstall.value).toBe(false)
  })

  it('attaches its listeners only once', async () => {
    const mod = await load()
    const before = listeners.length
    mod.listenForInstallPrompt()
    expect(listeners.length).toBe(before)
  })
})
