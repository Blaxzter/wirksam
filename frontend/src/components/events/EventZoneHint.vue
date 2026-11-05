<script setup lang="ts">
import { computed } from 'vue'

import { Globe } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { browserTimeZone, isSameTimeZone, timeZoneLabel } from '@/lib/timezones'

/**
 * One quiet line for someone whose device is in another zone than the event:
 * the shift times on the page are the venue's, as written, and not converted.
 * In the same zone, which is nearly everyone, it renders nothing at all.
 */
const props = defineProps<{ zone?: string | null }>()

const { t } = useI18n()

const elsewhere = computed(() => !!props.zone && !isSameTimeZone(props.zone, browserTimeZone()))
</script>

<template>
  <p
    v-if="elsewhere"
    class="flex items-center gap-1.5 text-xs text-muted-foreground"
    data-testid="event-zone-hint"
  >
    <Globe class="size-3.5 shrink-0" aria-hidden="true" />
    {{ t('duties.events.timezone.localTimes', { zone: timeZoneLabel(zone!) }) }}
  </p>
</template>
