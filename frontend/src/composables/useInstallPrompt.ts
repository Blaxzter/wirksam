import { computed, readonly, ref } from 'vue'

/**
 * Chromium's install prompt event. Not in lib.dom: only Chromium browsers fire
 * it, and only once the page meets their installability criteria (manifest,
 * icons, service worker).
 */
export interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

/**
 * Module-level, so the menus share one prompt. The browser fires
 * `beforeinstallprompt` once per page load, often before any component that
 * would show an install button has mounted — hence `listenForInstallPrompt()`
 * runs from main.ts and keeps the event until somebody asks for it.
 */
const deferredPrompt = ref<BeforeInstallPromptEvent | null>(null)
const installed = ref(false)
const isIos = ref(false)
let listening = false

function runningStandalone(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    // iOS Safari's own flag for a home-screen web app.
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  )
}

function detectIos(): boolean {
  const { userAgent, maxTouchPoints } = navigator
  // iPadOS reports itself as a Mac; the touch screen gives it away.
  return /iPad|iPhone|iPod/.test(userAgent) || (/Macintosh/.test(userAgent) && maxTouchPoints > 1)
}

/** Starts listening for the install prompt. Call once, before mounting. */
export function listenForInstallPrompt(): void {
  if (listening || typeof window === 'undefined') return
  listening = true

  installed.value = runningStandalone()
  isIos.value = detectIos()

  window.addEventListener('beforeinstallprompt', (event) => {
    // Keep the browser's own mini-infobar out of the way; the menus offer it.
    event.preventDefault()
    deferredPrompt.value = event as BeforeInstallPromptEvent
  })
  window.addEventListener('appinstalled', () => {
    installed.value = true
    deferredPrompt.value = null
  })
}

export function useInstallPrompt() {
  /** A browser prompt is ready: `install()` opens it. */
  const canPrompt = computed(() => !installed.value && deferredPrompt.value !== null)
  /**
   * iOS has no prompt API; Safari installs only through Share → "Add to Home
   * Screen", so the best the app can do is say where that is.
   */
  const needsManualInstall = computed(
    () => !installed.value && deferredPrompt.value === null && isIos.value,
  )
  const canInstall = computed(() => canPrompt.value || needsManualInstall.value)

  /** Opens the browser's install dialog. Resolves to whether it was accepted. */
  async function install(): Promise<boolean> {
    const event = deferredPrompt.value
    if (!event) return false
    // A prompt can be shown only once; a dismissed one is gone until reload.
    deferredPrompt.value = null
    await event.prompt()
    const { outcome } = await event.userChoice
    if (outcome === 'accepted') installed.value = true
    return outcome === 'accepted'
  }

  return {
    canInstall,
    canPrompt,
    needsManualInstall,
    installed: readonly(installed),
    install,
  }
}
