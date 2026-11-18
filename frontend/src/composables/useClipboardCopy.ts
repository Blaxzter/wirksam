import { type Ref, getCurrentScope, onScopeDispose, shallowRef } from 'vue'

/** How long a copy button shows its tick. */
export const COPIED_MS = 2000

export interface ClipboardCopy<K> {
  /** What was copied last, for `COPIED_MS`: its button shows a tick meanwhile. */
  copied: Readonly<Ref<K | null>>
  /**
   * Copy `text` and tick `key`. Resolves to false when the clipboard is
   * blocked (an insecure page, a denied permission); the caller then shows the
   * text, so it can still be copied by hand.
   */
  copy: (key: K, text: string) => Promise<boolean>
}

/** Copy buttons that show a tick for a moment, one tick at a time. */
export function useClipboardCopy<K>(): ClipboardCopy<K> {
  const copied = shallowRef<K | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined

  async function copy(key: K, text: string): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      return false
    }
    copied.value = key
    clearTimeout(timer)
    timer = setTimeout(() => (copied.value = null), COPIED_MS)
    return true
  }

  if (getCurrentScope()) onScopeDispose(() => clearTimeout(timer))

  return { copied, copy }
}
