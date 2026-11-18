<script setup lang="ts">
/**
 * A task's own sheet: every shift with a line per place, to sign up on paper.
 * No QR code: a notice people sign up from online is a shared list's sheet
 * (`PrintListView`), which the task page's "Drucken" opens for those who may
 * share the task.
 */
import { computed, onMounted, ref, useTemplateRef } from 'vue'

import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { usePrintSheet } from '@/composables/usePrintSheet'

import PrintSheet from '@/components/print/PrintSheet.vue'
import PrintSheetOptions from '@/components/print/PrintSheetOptions.vue'
import PrintToolbar from '@/components/print/PrintToolbar.vue'

import type { ShiftBatchRead, TaskRead } from '@/client/types.gen'
import { formatDate } from '@/lib/format'
import { type SheetShift, fromShift } from '@/lib/print-sheet'
import { sharedLocationId } from '@/lib/venue-map'

const { t } = useI18n()
const route = useRoute()
const { get } = useAuthenticatedClient()
const sheet = usePrintSheet()

const taskId = computed(() => String(route.params.taskId))

const task = ref<TaskRead | null>(null)
const shifts = ref<SheetShift[]>([])
const batches = ref<ShiftBatchRead[]>([])
const loading = ref(true)
const sheetEl = useTemplateRef<InstanceType<typeof PrintSheet>>('sheetEl')

const map = computed(() => sheet.mapFor(task.value?.event_id))

const sections = computed(() =>
  task.value
    ? [
        {
          key: task.value.id,
          heading: null,
          shifts: sheet.visible(shifts.value),
          batches: batches.value,
          canSeeContacts: !!task.value.can_manage,
        },
      ]
    : [],
)

function print() {
  if (sheetEl.value) void sheet.print([sheetEl.value])
}

onMounted(async () => {
  try {
    const [taskRes, own] = await Promise.all([
      get<{ data: TaskRead }>({ url: `/tasks/${taskId.value}` }),
      sheet.fetchShifts([taskId.value]),
    ])
    task.value = taskRes.data
    shifts.value = (own.get(taskId.value) ?? []).map(fromShift)
    sheet.reset([shifts.value], [taskId.value])
    try {
      const batchRes = await get<{ data: ShiftBatchRead[] }>({
        url: `/tasks/${taskId.value}/batches`,
      })
      batches.value = batchRes.data
    } catch {
      // Non-critical: the shifts print without their batches' headings.
    }
    // The task page's rule: one location shared by every shift (or the task's
    // own when it has none yet) gets a map; several get none.
    await sheet.loadLocation(sharedLocationId(shifts.value, task.value.location_id))
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="print-page mx-auto max-w-5xl w-full space-y-4 p-4 print:p-0">
    <PrintToolbar
      data-testid="print-toolbar"
      :disabled="loading || sheet.bookingsLoading.value"
      @print="print"
    >
      <PrintSheetOptions
        v-model:show-title="sheet.showTitle.value"
        v-model:show-location="sheet.showLocation.value"
        v-model:repeat-header="sheet.repeatHeader.value"
        v-model:show-map="sheet.showMap.value"
        v-model:paper-lines="sheet.paperLines.value"
        v-model:selected-dates="sheet.selectedDates.value"
        :include-names="sheet.includeNames.value"
        :dates="sheet.dates.value"
        :has-map="!!sheet.pin.value"
        :listed="false"
        :bookings-loading="sheet.bookingsLoading.value"
        @update:include-names="sheet.setIncludeNames"
      />
    </PrintToolbar>

    <p v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </p>

    <div v-else-if="task" data-testid="print-content">
      <PrintSheet
        ref="sheetEl"
        :heading="task.name"
        :text="task.description"
        :meta="{
          days: `${formatDate(task.start_date)} – ${formatDate(task.end_date)}`,
          location: task.location,
          category: task.category,
        }"
        :sections="sections"
        :options="sheet.options.value"
        :bookings="sheet.bookings.value"
        :map="map"
      />
    </div>
  </div>
</template>
