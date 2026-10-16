import { type MaybeRefOrGetter, type Ref, ref, toValue, watch } from 'vue'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import type {
  VenueTemplateRead,
  VenueTemplateShape,
  VenueTemplateSummary,
} from '@/client/types.gen'

/**
 * The signed-in user's venue plan templates: saved drawings (canvas, picture
 * and shapes, never pins or place links) to start new plans from, in any of
 * their events. Only the owner ever sees a template.
 *
 * The drawing of a template never changes after it is saved (only its name
 * does), so the shapes for a thumbnail are cached at module level by template
 * id. Deleting a template drops its entry.
 */
const shapeCache = new Map<string, Promise<VenueTemplateShape[]>>()

/** Forget a template's cached drawing (every template's when omitted). */
export function forgetTemplateShapes(templateId?: string) {
  if (templateId) shapeCache.delete(templateId)
  else shapeCache.clear()
}

export interface VenueTemplates {
  templates: Ref<VenueTemplateSummary[]>
  loading: Ref<boolean>
  /** The last load failed; the list is then not "empty", just unknown. */
  loadError: Ref<boolean>
  load: () => Promise<void>
  /** Rename one; throws what the API threw. */
  rename: (id: string, name: string) => Promise<VenueTemplateRead>
  /** Delete one; throws what the API threw. */
  remove: (id: string) => Promise<void>
}

export function useVenueTemplates(): VenueTemplates {
  const { get, patch, delete: del } = useAuthenticatedClient()

  const templates = ref<VenueTemplateSummary[]>([])
  const loading = ref(false)
  const loadError = ref(false)
  // A slow, older list response must not overwrite a newer one.
  let generation = 0

  async function load() {
    const gen = ++generation
    loading.value = true
    loadError.value = false
    try {
      const res = await get<{ data: VenueTemplateSummary[] }>({ url: '/venue-templates' })
      if (gen === generation) templates.value = res.data
    } catch {
      if (gen === generation) {
        templates.value = []
        loadError.value = true
      }
    } finally {
      if (gen === generation) loading.value = false
    }
  }

  async function rename(id: string, name: string) {
    const res = await patch<{ data: VenueTemplateRead }>({
      url: `/venue-templates/${id}`,
      body: { name },
    })
    const index = templates.value.findIndex((t) => t.id === id)
    if (index >= 0) templates.value[index] = res.data
    return res.data
  }

  async function remove(id: string) {
    await del({ url: `/venue-templates/${id}` })
    templates.value = templates.value.filter((t) => t.id !== id)
    forgetTemplateShapes(id)
  }

  return { templates, loading, loadError, load, rename, remove }
}

export interface TemplateShapes {
  shapes: Ref<VenueTemplateShape[]>
  loading: Ref<boolean>
  error: Ref<unknown>
}

/**
 * One template's drawing, for its thumbnail.
 *
 * @param templateId the template, or `null` for none
 * @param enabled `false` skips the request (a template with no shapes)
 */
export function useTemplateShapes(
  templateId: MaybeRefOrGetter<string | null | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
): TemplateShapes {
  const { get } = useAuthenticatedClient()

  const shapes = ref<VenueTemplateShape[]>([])
  const loading = ref(false)
  const error = ref<unknown>(null)
  let generation = 0

  function fetchShapes(id: string): Promise<VenueTemplateShape[]> {
    let pending = shapeCache.get(id)
    if (!pending) {
      pending = get<{ data: VenueTemplateRead }>({ url: `/venue-templates/${id}` }).then(
        (res) => res.data.shapes ?? [],
      )
      shapeCache.set(id, pending)
      // A failure is not worth remembering; the next caller retries.
      pending.catch(() => {
        if (shapeCache.get(id) === pending) shapeCache.delete(id)
      })
    }
    return pending
  }

  watch(
    [() => toValue(templateId), () => toValue(enabled)],
    async ([id, on]) => {
      const gen = ++generation
      error.value = null
      if (!id || !on) {
        shapes.value = []
        loading.value = false
        return
      }
      loading.value = true
      try {
        const data = await fetchShapes(id)
        if (gen === generation) shapes.value = data
      } catch (e) {
        if (gen === generation) {
          shapes.value = []
          error.value = e
        }
      } finally {
        if (gen === generation) loading.value = false
      }
    },
    { immediate: true },
  )

  return { shapes, loading, error }
}
