import { type MaybeRefOrGetter, getCurrentScope, onScopeDispose, toValue, watchEffect } from 'vue'

import { eventColourAttr } from '@/lib/event-appearance'

/** Each a preset's name or an own colour (`#rrggbb`), as `data-event-*` takes it. */
interface Colours {
  primary: string | null
  secondary: string | null
  base: string | null
}

/** What a caller passes: an event, an invitation preview, or nothing. */
export interface EventColoursSource {
  primary_color?: string | null
  secondary_color?: string | null
  base_color?: string | null
}

/**
 * Everyone currently asking for colours, oldest first; the newest decides.
 *
 * A stack rather than "set it, remove it on unmount", because a page that
 * leaves and a page that arrives can overlap: the leaving one's cleanup must
 * not strip the colours the arriving one has just put on.
 */
const owners: Colours[] = []

function apply() {
  if (typeof document === 'undefined') return
  const top = owners.at(-1)
  const root = document.documentElement
  if (top?.primary) root.dataset.eventPrimary = top.primary
  else delete root.dataset.eventPrimary
  if (top?.secondary) root.dataset.eventSecondary = top.secondary
  else delete root.dataset.eventSecondary
  if (top?.base) root.dataset.eventBase = top.base
  else delete root.dataset.eventBase
}

/**
 * Dress the whole page in an event's colours while the calling component is
 * mounted: `data-event-primary`, `data-event-secondary` and `data-event-base`
 * on `<html>`, which `index.css` turns into the app's tokens. An own colour is
 * made into a preset first (`custom-colour.ts`). A missing colour (or a name
 * this build does not know) keeps the app's own for that one, and so does a
 * base tone that follows a main colour the event does not have.
 *
 * Used by the signed-in layout (the selected event) and the invitation page
 * (the event being joined).
 */
export function useEventColors(source: MaybeRefOrGetter<EventColoursSource | null | undefined>) {
  const owner: Colours = { primary: null, secondary: null, base: null }
  owners.push(owner)
  watchEffect(() => {
    const value = toValue(source)
    owner.primary = eventColourAttr('primary', value?.primary_color) ?? null
    owner.secondary = eventColourAttr('secondary', value?.secondary_color) ?? null
    const base = eventColourAttr('base', value?.base_color) ?? null
    owner.base = base === 'primary' && !owner.primary ? null : base
    apply()
  })
  if (getCurrentScope()) {
    onScopeDispose(() => {
      owners.splice(owners.indexOf(owner), 1)
      apply()
    })
  }
}
