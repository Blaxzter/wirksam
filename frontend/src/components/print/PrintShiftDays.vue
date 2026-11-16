<script setup lang="ts">
/**
 * The shifts of one task on a printed sheet: by batch when it has several,
 * then by day, a row per line to write a name on. A shared list's sheet adds
 * how many places are free and the vouchers a shift earns.
 */
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import type { ShiftBatchRead, TaskBookingEntry } from '@/client/types.gen'
import { formatDate } from '@/lib/format'
import {
  type SheetLine,
  type SheetOptions,
  type SheetShift,
  byBatch,
  byDay,
  sheetLines,
} from '@/lib/print-sheet'

const props = defineProps<{
  shifts: readonly SheetShift[]
  batches: readonly ShiftBatchRead[]
  options: SheetOptions
  bookings: ReadonlyMap<string, readonly TaskBookingEntry[]>
  /** Organisers and the task's people in charge, who see phone numbers. */
  canSeeContacts: boolean
}>()

const { t } = useI18n()
const { formatTime, formatDateLabel } = useFormatters()

/** A shared list's sheet: its shifts carry their free places. */
const listed = computed(() => props.shifts.some((shift) => shift.free !== null))
const showVouchers = computed(() => listed.value && props.shifts.some((s) => s.vouchers > 0))
const showLocationColumn = computed(
  () => props.options.showLocation && props.shifts.some((shift) => shift.location),
)

const lines = computed(
  () =>
    new Map(
      props.shifts.map((shift) => [
        shift.id,
        sheetLines(shift, props.bookings.get(shift.id) ?? [], props.options),
      ]),
    ),
)

/** At least one row per shift, so its time prints even without a line to write on. */
function rowsOf(shift: SheetShift): (SheetLine | null)[] {
  const own = lines.value.get(shift.id) ?? []
  return own.length ? own : [null]
}

/**
 * Phone numbers come only for organisers and the task's people in charge.
 * Anyone else printing the names would get a column of blank lines that looks
 * like it wants filling in, so it goes; a blank sign-up sheet keeps it.
 */
const showContactColumn = computed(
  () =>
    !props.options.includeNames ||
    props.canSeeContacts ||
    [...lines.value.values()].some((own) => own.some((line) => line.contact)),
)

const groups = computed(() => byBatch(props.shifts, props.batches))

function batchLabel(batch: ShiftBatchRead): string {
  return batch.label || `${formatDate(batch.start_date)} – ${formatDate(batch.end_date)}`
}
</script>

<template>
  <div class="space-y-4">
    <div v-for="group in groups" :key="group.batch?.id ?? 'all'" class="space-y-3">
      <h3 v-if="group.batch" class="font-semibold text-lg print-keep-with-next">
        {{ batchLabel(group.batch) }}
        <span v-if="group.batch.location" class="text-sm font-normal text-muted-foreground ml-2">
          {{ group.batch.location }}
        </span>
      </h3>

      <div
        v-for="[date, dayShifts] in byDay(group.shifts)"
        :key="date"
        class="space-y-1 print-keep-together"
      >
        <h4 class="font-medium text-sm bg-muted px-2 py-1 rounded print-bg">
          {{
            formatDateLabel(date, {
              weekday: 'long',
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })
          }}
        </h4>
        <table class="w-full text-sm border-collapse">
          <!-- Times and headers on one line: the wide name columns would squeeze them. -->
          <thead>
            <tr class="border-b text-left whitespace-nowrap">
              <th class="py-1 px-1 font-medium w-20">
                {{ t('duties.shifts.fields.startTime') }}
              </th>
              <th class="py-1 px-1 font-medium w-20">{{ t('duties.shifts.fields.endTime') }}</th>
              <th v-if="options.showTitle" class="py-1 px-1 font-medium">
                {{ t('duties.shifts.fields.title') }}
              </th>
              <th v-if="showLocationColumn" class="py-1 px-1 font-medium">
                {{ t('duties.shifts.fields.location') }}
              </th>
              <th v-if="listed" class="py-1 px-1 font-medium w-14">
                {{ t('print.freeColumn') }}
              </th>
              <th v-if="showVouchers" class="py-1 px-1 font-medium w-16">
                {{ t('print.vouchersColumn') }}
              </th>
              <!-- Narrower on a list's sheet, which has two more columns. -->
              <th class="py-1 px-1 font-medium" :class="listed ? 'w-[30%]' : 'w-[35%]'">
                {{ t('print.nameColumn') }}
              </th>
              <th
                v-if="showContactColumn"
                class="py-1 px-1 font-medium"
                :class="listed ? 'w-[20%]' : 'w-[25%]'"
              >
                {{ t('print.contactColumn') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="shift in dayShifts" :key="shift.id">
              <tr
                v-for="(line, index) in rowsOf(shift)"
                :key="`${shift.id}-${index}`"
                class="border-b border-dashed align-top"
                data-testid="print-shift-line"
              >
                <template v-if="index === 0">
                  <td
                    :rowspan="rowsOf(shift).length"
                    class="py-1 px-1 font-mono whitespace-nowrap border-r border-dashed"
                    data-testid="print-shift-time"
                  >
                    {{ formatTime(shift.start_time) || '—' }}
                  </td>
                  <td
                    :rowspan="rowsOf(shift).length"
                    class="py-1 px-1 font-mono whitespace-nowrap border-r border-dashed"
                    data-testid="print-shift-time"
                  >
                    {{ formatTime(shift.end_time) || '—' }}
                  </td>
                  <td
                    v-if="options.showTitle"
                    :rowspan="rowsOf(shift).length"
                    class="py-1 px-1 border-r border-dashed"
                  >
                    {{ shift.title }}
                  </td>
                  <td
                    v-if="showLocationColumn"
                    :rowspan="rowsOf(shift).length"
                    class="py-1 px-1 border-r border-dashed"
                  >
                    {{ shift.location ?? '' }}
                  </td>
                  <td
                    v-if="listed"
                    :rowspan="rowsOf(shift).length"
                    class="py-1 px-1 tabular-nums border-r border-dashed"
                    data-testid="print-shift-free"
                  >
                    {{ shift.free }}
                  </td>
                  <td
                    v-if="showVouchers"
                    :rowspan="rowsOf(shift).length"
                    class="py-1 px-1 tabular-nums border-r border-dashed"
                  >
                    {{ shift.vouchers || '' }}
                  </td>
                </template>
                <td class="py-1 px-1">
                  <span v-if="line?.name" class="font-medium">{{ line.name }}</span>
                  <div v-else-if="line" class="border-b border-dotted border-foreground/30 h-5" />
                </td>
                <td v-if="showContactColumn" class="py-1 px-1">
                  <span v-if="line?.contact">{{ line.contact }}</span>
                  <div v-else-if="line" class="border-b border-dotted border-foreground/30 h-5" />
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
