<script setup lang="ts">
import { computed } from 'vue'

import { ExternalLink, MapPin, User } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { LocationDetailRead, LocationRead } from '@/client/types.gen'
import { renderMarkdown } from '@/lib/markdown'

/**
 * What a location looks like to someone heading there: the admin's markdown
 * description, the address, a link to an outside map and who to ask.
 *
 * This is the only place `renderMarkdown` output reaches `v-html` — see
 * `lib/markdown.ts` for why that is safe. `compact` clamps the description to
 * three lines and leaves out the contact, for list cards and previews.
 */
const props = withDefaults(
  defineProps<{
    location: LocationRead | LocationDetailRead
    compact?: boolean
  }>(),
  { compact: false },
)

const { t } = useI18n()

const html = computed(() => renderMarkdown(props.location.description))

// The API only accepts http(s) here; checking again costs nothing and keeps a
// stray `javascript:` from ever becoming an href.
const mapUrl = computed(() => {
  const url = props.location.map_url?.trim()
  return url && /^https?:\/\//i.test(url) ? url : null
})
</script>

<template>
  <div class="space-y-2 text-sm" data-testid="location-description">
    <div
      v-if="html"
      class="location-markdown text-muted-foreground"
      :class="{ 'line-clamp-3': compact }"
      data-testid="location-description-body"
      v-html="html"
    />

    <dl v-if="location.address || mapUrl || (!compact && location.contact)" class="space-y-1.5">
      <div v-if="location.address" class="flex items-start gap-1.5">
        <dt class="shrink-0 pt-0.5">
          <MapPin class="text-muted-foreground size-4" />
          <span class="sr-only">{{ t('venueMap.locationDetails.address') }}</span>
        </dt>
        <dd class="min-w-0 whitespace-pre-line break-words">{{ location.address }}</dd>
      </div>
      <div v-if="!compact && location.contact" class="flex items-start gap-1.5">
        <dt class="shrink-0 pt-0.5">
          <User class="text-muted-foreground size-4" />
          <span class="sr-only">{{ t('venueMap.locationDetails.contact') }}</span>
        </dt>
        <dd class="min-w-0 whitespace-pre-line break-words">{{ location.contact }}</dd>
      </div>
      <div v-if="mapUrl">
        <dt class="sr-only">{{ t('venueMap.locationDetails.openInMaps') }}</dt>
        <dd>
          <a
            :href="mapUrl"
            target="_blank"
            rel="noopener noreferrer nofollow"
            class="text-primary inline-flex items-center gap-1.5 font-medium underline-offset-4 hover:underline"
            data-testid="location-map-link"
          >
            <ExternalLink class="size-4" />
            {{ t('venueMap.locationDetails.openInMaps') }}
          </a>
        </dd>
      </div>
    </dl>
  </div>
</template>

<style scoped>
/* No typography plugin in this app, so the few elements markdown produces are
   styled here, in the same spirit as the changelog. */
.location-markdown :deep(p),
.location-markdown :deep(ul),
.location-markdown :deep(ol) {
  margin-bottom: 0.5rem;
  line-height: 1.6;
}
.location-markdown :deep(> :last-child) {
  margin-bottom: 0;
}
.location-markdown :deep(ul) {
  list-style-type: disc;
  padding-left: 1.25rem;
}
.location-markdown :deep(ol) {
  list-style-type: decimal;
  padding-left: 1.25rem;
}
.location-markdown :deep(strong) {
  color: var(--foreground);
  font-weight: 600;
}
.location-markdown :deep(h1),
.location-markdown :deep(h2),
.location-markdown :deep(h3),
.location-markdown :deep(h4) {
  color: var(--foreground);
  font-weight: 600;
  margin: 0.75rem 0 0.25rem;
}
.location-markdown :deep(a) {
  color: var(--primary);
  text-decoration: underline;
  text-underline-offset: 2px;
  overflow-wrap: anywhere;
}
.location-markdown :deep(code) {
  font-size: 0.8125rem;
  background: var(--muted);
  padding: 0.0625rem 0.25rem;
  border-radius: calc(var(--radius) - 4px);
}
.location-markdown :deep(blockquote) {
  border-left: 3px solid var(--border);
  padding-left: 0.75rem;
}
</style>
