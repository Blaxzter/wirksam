<script setup lang="ts">
import { computed } from 'vue'

import { ExternalLink, MapPin, User } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import MarkdownBody from '@/components/content/MarkdownBody.vue'

import type { LocationDetailRead, LocationRead } from '@/client/types.gen'

/**
 * What a location looks like to someone heading there: the admin's markdown
 * description, the address, a link to an outside map and who to ask.
 *
 * The description goes through `MarkdownBody`, the one place markdown reaches
 * `v-html`. `compact` clamps it to three lines and leaves out the contact, for
 * list cards and previews.
 */
const props = withDefaults(
  defineProps<{
    location: LocationRead | LocationDetailRead
    compact?: boolean
  }>(),
  { compact: false },
)

const { t } = useI18n()

// The API only accepts http(s) here; checking again costs nothing and keeps a
// stray `javascript:` from ever becoming an href.
const mapUrl = computed(() => {
  const url = props.location.map_url?.trim()
  return url && /^https?:\/\//i.test(url) ? url : null
})
</script>

<template>
  <div class="space-y-2 text-sm" data-testid="location-description">
    <MarkdownBody
      :source="location.description"
      :clamp="compact ? 3 : undefined"
      class="text-muted-foreground"
      data-testid="location-description-body"
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
