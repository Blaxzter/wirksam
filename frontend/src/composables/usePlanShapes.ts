import { type MaybeRefOrGetter, type Ref, ref, toValue, watch } from 'vue'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import type { VenuePlanShapesRead, VenueShapeRead } from '@/client/types.gen'

/**
 * The drawn shapes of one venue plan, for views that only know a plan by id
 * and revision: the task mini-map and its print copy (`VenueMiniMap`). The map
 * page and the editor get shapes nested in the plan and do not need this.
 *
 * Responses are cached at module level by `planId:revision`. The revision is
 * bumped by every saved drawing, so a new revision is a new key and a stale
 * drawing is never served. The editor additionally calls
 * {@link invalidatePlanShapes} after each save, which drops every cached
 * revision of that plan and reloads it wherever it is on screen.
 */
const cache = new Map<string, Promise<VenueShapeRead[]>>()
// Bumped by `invalidatePlanShapes`; every instance watches it.
const version = ref(0)

const key = (planId: string, revision: number) => `${planId}:${revision}`

/** Forget a plan's cached shapes (every plan's when omitted) and reload them. */
export function invalidatePlanShapes(planId?: string | null) {
  if (planId) {
    for (const k of [...cache.keys()]) if (k.startsWith(`${planId}:`)) cache.delete(k)
  } else {
    cache.clear()
  }
  version.value++
}

export interface PlanShapes {
  shapes: Ref<VenueShapeRead[]>
  loading: Ref<boolean>
  error: Ref<unknown>
  /** Resolves once the current load has settled, successfully or not. */
  ready: () => Promise<void>
}

/**
 * @param planId the plan, or `null` for none
 * @param revision the plan's `shapes_revision`, used only as the cache key.
 *   Whether there is anything to fetch is `enabled`'s call: a copied plan can
 *   hold shapes at any revision.
 * @param enabled `false` skips the request (e.g. a pin whose `shape_count` is 0)
 */
export function usePlanShapes(
  planId: MaybeRefOrGetter<string | null | undefined>,
  revision: MaybeRefOrGetter<number | null | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
): PlanShapes {
  const { get } = useAuthenticatedClient()

  const shapes = ref<VenueShapeRead[]>([])
  const loading = ref(false)
  const error = ref<unknown>(null)
  let current: Promise<void> = Promise.resolve()
  // Guards against an older request resolving after a newer one.
  let generation = 0

  function fetchShapes(id: string, rev: number): Promise<VenueShapeRead[]> {
    const k = key(id, rev)
    let pending = cache.get(k)
    if (!pending) {
      pending = get<{ data: VenuePlanShapesRead }>({ url: `/venue-plans/${id}/shapes` }).then(
        (res) => res.data.shapes,
      )
      cache.set(k, pending)
      // A failure is not worth remembering; the next caller retries.
      pending.catch(() => {
        if (cache.get(k) === pending) cache.delete(k)
      })
    }
    return pending
  }

  async function load(id: string, rev: number, gen: number) {
    try {
      const data = await fetchShapes(id, rev)
      if (gen === generation) shapes.value = data
    } catch (e) {
      if (gen === generation) {
        shapes.value = []
        error.value = e
      }
    } finally {
      if (gen === generation) loading.value = false
    }
  }

  watch(
    [() => toValue(planId), () => toValue(revision), () => toValue(enabled), version],
    ([id, rev, on]) => {
      const gen = ++generation
      error.value = null
      if (!id || !on) {
        shapes.value = []
        loading.value = false
        current = Promise.resolve()
        return
      }
      loading.value = true
      current = load(id, rev ?? 0, gen)
    },
    { immediate: true },
  )

  return { shapes, loading, error, ready: () => current }
}
