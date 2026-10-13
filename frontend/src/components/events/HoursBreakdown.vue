<script setup lang="ts">
import { Pencil, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'

import type { VolunteerHoursDetail, WorkLogRead } from '@/client/types.gen'
import { formatHours } from '@/lib/format'

defineProps<{
  detail: VolunteerHoursDetail
  /** Event admins may change the hand-entered hours. */
  canEdit?: boolean
}>()

const emit = defineEmits<{
  edit: [entry: WorkLogRead]
  delete: [entry: WorkLogRead]
}>()

const { t } = useI18n()
const { formatDateLabel, formatTimeRange } = useFormatters()

const hoursLabel = (minutes: number) => t('duties.hours.unit', { value: formatHours(minutes) })
</script>

<template>
  <div class="space-y-5">
    <section class="space-y-2">
      <h3 class="text-sm font-semibold">{{ t('duties.hours.detail.shiftsHeading') }}</h3>
      <p v-if="detail.shifts.length === 0" class="text-sm text-muted-foreground">
        {{ t('duties.hours.detail.noShifts') }}
      </p>
      <ul v-else class="divide-y rounded-md border text-sm" data-testid="hours-shift-list">
        <li
          v-for="shift in detail.shifts"
          :key="shift.booking_id"
          class="flex items-center justify-between gap-3 px-3 py-2"
          :class="{ 'text-muted-foreground': !shift.completed }"
        >
          <div class="min-w-0">
            <p class="truncate font-medium">{{ shift.task_name }} · {{ shift.title }}</p>
            <p class="text-xs text-muted-foreground">
              {{ formatDateLabel(shift.date) }}
              <template v-if="shift.start_time && shift.end_time">
                · {{ formatTimeRange(shift.start_time, shift.end_time) }}
              </template>
              <template v-else> · {{ t('duties.hours.detail.noTimes') }}</template>
            </p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <Badge v-if="!shift.completed" variant="outline">
              {{ t('duties.hours.detail.upcoming') }}
            </Badge>
            <span class="tabular-nums">{{ hoursLabel(shift.minutes) }}</span>
          </div>
        </li>
      </ul>
    </section>

    <section class="space-y-2">
      <h3 class="text-sm font-semibold">{{ t('duties.hours.detail.entriesHeading') }}</h3>
      <p v-if="detail.work_logs.length === 0" class="text-sm text-muted-foreground">
        {{ t('duties.hours.detail.noEntries') }}
      </p>
      <ul v-else class="divide-y rounded-md border text-sm" data-testid="hours-entry-list">
        <li
          v-for="entry in detail.work_logs"
          :key="entry.id"
          class="flex items-center justify-between gap-3 px-3 py-2"
        >
          <div class="min-w-0">
            <p class="truncate font-medium">{{ entry.description }}</p>
            <p class="text-xs text-muted-foreground">
              {{ formatDateLabel(entry.date) }}
              <template v-if="entry.created_by_name">
                · {{ t('duties.hours.detail.addedBy', { name: entry.created_by_name }) }}
              </template>
            </p>
          </div>
          <div class="flex shrink-0 items-center gap-1">
            <span class="mr-1 tabular-nums">{{ hoursLabel(entry.minutes) }}</span>
            <template v-if="canEdit">
              <Button
                variant="ghost"
                size="icon"
                class="size-7"
                :aria-label="t('duties.hours.detail.edit')"
                @click="emit('edit', entry)"
              >
                <Pencil class="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                class="size-7 text-muted-foreground hover:text-destructive"
                :aria-label="t('duties.hours.detail.delete')"
                data-testid="btn-delete-work-log"
                @click="emit('delete', entry)"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </Button>
            </template>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>
