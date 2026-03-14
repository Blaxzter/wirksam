<script setup lang="ts">
import { Users } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'
import type { PreviewSlot } from '@/composables/useSlotPreview'

import Badge from '@/components/ui/badge/Badge.vue'
import { Card, CardContent } from '@/components/ui/card'

defineProps<{
  slotsByDate: Map<string, PreviewSlot[]>
  isSlotExcluded: (slot: PreviewSlot) => boolean
  getBookingCount?: (slot: PreviewSlot) => number
}>()

const emit = defineEmits<{
  toggleExclusion: [slot: PreviewSlot]
}>()

const { t } = useI18n()
const { formatDateLabel } = useFormatters()
</script>

<template>
  <div class="space-y-4">
    <div v-for="[dateStr, slots] in slotsByDate" :key="dateStr" class="space-y-2">
      <div class="flex items-center gap-2">
        <p class="font-medium">{{ formatDateLabel(dateStr) }}</p>
        <Badge variant="outline">
          {{ t('duties.events.createView.preview.slotsOnDate', { count: slots.filter(s => !isSlotExcluded(s)).length }) }}
        </Badge>
      </div>
      <div class="grid grid-cols-2 items-center gap-2 sm:grid-cols-3 md:grid-cols-4">
        <Card
          v-for="slot in slots"
          :key="slot.startTime"
          class="cursor-pointer p-2 transition-opacity"
          :class="[
            isSlotExcluded(slot) ? 'opacity-30' : 'hover:ring-1 hover:ring-destructive/40',
            getBookingCount && getBookingCount(slot) > 0 && !isSlotExcluded(slot)
              ? 'ring-1 ring-primary/30'
              : '',
          ]"
          @click="emit('toggleExclusion', slot)"
        >
          <CardContent class="p-0">
            <p
              class="text-center text-sm font-mono"
              :class="isSlotExcluded(slot) ? 'line-through text-muted-foreground' : ''"
            >
              {{ slot.startTime }} - {{ slot.endTime }}
            </p>
            <p
              v-if="getBookingCount && getBookingCount(slot) > 0"
              class="mt-0.5 flex items-center justify-center gap-1 text-xs"
              :class="isSlotExcluded(slot) ? 'text-destructive line-through' : 'text-primary'"
            >
              <Users class="h-3 w-3" />
              {{ t('duties.events.editView.preview.booked', { count: getBookingCount(slot) }) }}
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  </div>
</template>
