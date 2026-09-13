<script setup lang="ts">
import { Users } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'
import type { PreviewShift } from '@/composables/useShiftPreview'

import Badge from '@/components/ui/badge/Badge.vue'
import { Card, CardContent } from '@/components/ui/card'

const props = defineProps<{
  shiftsByDate: Map<string, PreviewShift[]>
  isShiftExcluded: (shift: PreviewShift) => boolean
  getBookingCount?: (shift: PreviewShift) => number
  /**
   * Show the grid without its strike-out affordances.
   *
   * Where nothing can be excluded — the clone wizard's preview of an event that
   * does not exist yet — the cards must not offer the pointer cursor and the
   * destructive hover ring they carry when a click really removes a shift.
   *
   * It also flattens the chips to an outline. The grid is already three
   * surfaces deep there, and in the dark palette `--card` sits *above*
   * `--background`, so a filled chip at the bottom of that stack reads as the
   * raised one — the lighting inverted.
   */
  readonly?: boolean
}>()

const emit = defineEmits<{
  toggleExclusion: [shift: PreviewShift]
}>()

const { t } = useI18n()
const { formatDateLabel } = useFormatters()
</script>

<template>
  <div class="space-y-4">
    <div v-for="[dateStr, shifts] in shiftsByDate" :key="dateStr" class="space-y-2">
      <div class="flex items-center gap-2">
        <p class="font-medium">{{ formatDateLabel(dateStr) }}</p>
        <Badge variant="outline">
          {{
            t('duties.tasks.createView.preview.shiftsOnDate', {
              count: shifts.filter((s) => !isShiftExcluded(s)).length,
            })
          }}
        </Badge>
      </div>
      <div class="grid grid-cols-2 items-center gap-2 sm:grid-cols-3 md:grid-cols-4">
        <Card
          v-for="shift in shifts"
          :key="shift.startTime"
          class="p-2 transition-opacity"
          :class="[
            props.readonly ? 'bg-transparent shadow-none' : 'cursor-pointer',
            isShiftExcluded(shift)
              ? 'opacity-30'
              : props.readonly
                ? ''
                : 'hover:ring-1 hover:ring-destructive/40',
            getBookingCount && getBookingCount(shift) > 0 && !isShiftExcluded(shift)
              ? 'ring-1 ring-primary/30'
              : '',
          ]"
          @click="props.readonly ? undefined : emit('toggleExclusion', shift)"
        >
          <CardContent class="p-0">
            <p
              class="text-center text-sm font-mono"
              :class="isShiftExcluded(shift) ? 'line-through text-muted-foreground' : ''"
            >
              {{ shift.startTime }} - {{ shift.endTime }}
            </p>
            <p
              v-if="getBookingCount && getBookingCount(shift) > 0"
              class="mt-0.5 flex items-center justify-center gap-1 text-xs"
              :class="isShiftExcluded(shift) ? 'text-destructive line-through' : 'text-primary'"
            >
              <Users class="h-3 w-3" />
              {{ t('duties.tasks.editView.preview.booked', { count: getBookingCount(shift) }) }}
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  </div>
</template>
