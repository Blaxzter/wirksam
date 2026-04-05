<script setup lang="ts">
import { computed } from 'vue'

import { Clock } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import Badge from '@/components/ui/badge/Badge.vue'

import type { UserAvailabilityRead } from '@/client/types.gen'
import { formatDateWithTime } from '@/lib/format'

const props = defineProps<{
  availability: UserAvailabilityRead
}>()

const { t } = useI18n()

const defaultTimeLabel = computed(() => {
  const s = props.availability.default_start_time
  const e = props.availability.default_end_time
  if (!s && !e) return null
  if (s && e) return `${s} – ${e}`
  if (s) return t('duties.availability.fields.afterTime', { time: s })
  return t('duties.availability.fields.beforeTime', { time: e })
})
</script>

<template>
  <div class="space-y-2">
    <div class="flex flex-wrap items-center gap-2">
      <Badge variant="secondary">
        {{ t(`duties.availability.types.${availability.availability_type}`) }}
      </Badge>
      <span
        v-if="defaultTimeLabel"
        class="inline-flex items-center gap-1 text-xs text-muted-foreground"
      >
        <Clock class="h-3 w-3" />
        {{ defaultTimeLabel }}
      </span>
    </div>
    <div v-if="(availability.available_dates?.length ?? 0) > 0" class="flex flex-wrap gap-1">
      <Badge
        v-for="d in availability.available_dates"
        :key="d.id"
        variant="outline"
        class="text-xs"
        :data-testid="`date-${d.slot_date}`"
      >
        {{ formatDateWithTime(d) }}
      </Badge>
    </div>
    <p
      v-if="availability.notes"
      class="line-clamp-3 text-sm text-muted-foreground"
      :title="availability.notes"
    >
      {{ availability.notes }}
    </p>
  </div>
</template>
