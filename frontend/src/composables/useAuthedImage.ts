import {
  type MaybeRefOrGetter,
  type Ref,
  getCurrentScope,
  onScopeDispose,
  ref,
  toValue,
  watch,
} from 'vue'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

export interface AuthedImage {
  /** A `blob:` URL for `<img src>` / SVG `<image href>`, or `null`. */
  src: Ref<string | null>
  loading: Ref<boolean>
  /** The last failure, cleared when the next load starts. */
  error: Ref<unknown>
  /**
   * Resolves once the current URL has finished loading — successfully or not.
   * Call it again after the URL changes; print views await it before
   * `window.print()` so the picture is on the page.
   */
  ready: () => Promise<void>
}

/**
 * Load an image that needs the bearer token.
 *
 * `<img>` and SVG `<image>` cannot send an `Authorization` header, and plan
 * images are member-only (`Cache-Control: private`), so the bytes are fetched
 * here and handed to the element as an object URL. The URL carries the etag
 * (`?v=…`), so the browser's HTTP cache still answers repeat loads.
 *
 * The previous object URL is revoked whenever the source changes and when the
 * calling scope is disposed, so a component that cycles through plans does not
 * leak blobs.
 */
export function useAuthedImage(url: MaybeRefOrGetter<string | null | undefined>): AuthedImage {
  const { getAuthToken } = useAuthenticatedClient()

  const src = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<unknown>(null)

  let current: Promise<void> = Promise.resolve()
  // Bumped per load, so a slow response for an old URL cannot overwrite a newer one.
  let generation = 0

  function revoke() {
    if (src.value) URL.revokeObjectURL(src.value)
    src.value = null
  }

  async function load(target: string, gen: number) {
    try {
      const token = await getAuthToken()
      const res = await fetch(target, { headers: { Authorization: `Bearer ${token}` } })
      if (!res.ok) throw new Error(`Image request failed with status ${res.status}`)
      const blob = await res.blob()
      if (gen !== generation) return
      src.value = URL.createObjectURL(blob)
    } catch (e) {
      if (gen !== generation) return
      error.value = e
    } finally {
      if (gen === generation) loading.value = false
    }
  }

  watch(
    () => toValue(url) ?? null,
    (target) => {
      const gen = ++generation
      revoke()
      error.value = null
      if (!target) {
        loading.value = false
        current = Promise.resolve()
        return
      }
      loading.value = true
      current = load(target, gen)
    },
    { immediate: true },
  )

  if (getCurrentScope()) {
    onScopeDispose(() => {
      generation++
      revoke()
    })
  }

  return { src, loading, error, ready: () => current }
}
