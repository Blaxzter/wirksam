<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { DateValue } from '@internationalized/date'
import { parseDate } from '@internationalized/date'
import { Clock, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import Button from '@/components/ui/button/Button.vue'
import { DatePicker } from '@/components/ui/date-picker'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import Label from '@/components/ui/label/Label.vue'
import { Switch } from '@/components/ui/switch'
import Textarea from '@/components/ui/textarea/Textarea.vue'
import { TimePicker } from '@/components/ui/time-picker'

import type { EventGroupRead, UserAvailabilityRead } from '@/client/types.gen'
import { formatDate } from '@/lib/format'

type AvailabilityType = 'fully_available' | 'specific_dates' | 'time_range'

interface DateEntry {
  date: DateValue | undefined
  start_time: string
  end_time: string
  fullDay: boolean
}

const props = defineProps<{
  group: EventGroupRead
  existingAvailability?: UserAvailabilityRead | null
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  save: [
    payload: {
      availability_type: AvailabilityType
      notes?: string
      default_start_time?: string
      default_end_time?: string
      dates: { date: string; start_time?: string; end_time?: string }[]
    },
  ]
}>()

const { t } = useI18n()

const form = ref({
  availability_type: 'fully_available' as AvailabilityType,
  notes: '',
  default_start_time: '',
  default_end_time: '',
})
const dateEntries = ref<DateEntry[]>([])

const groupMinDate = computed((): DateValue => parseDate(props.group.start_date))
const groupMaxDate = computed((): DateValue => parseDate(props.group.end_date))

const dateRangeLabel = computed(() =>
  t('duties.availability.fields.datesWithRange', {
    start: formatDate(props.group.start_date),
    end: formatDate(props.group.end_date),
  }),
)

const availabilityTypes: AvailabilityType[] = ['fully_available', 'time_range', 'specific_dates']

function resetForm() {
  if (props.existingAvailability) {
    form.value = {
      availability_type: props.existingAvailability.availability_type as AvailabilityType,
      notes: props.existingAvailability.notes ?? '',
      default_start_time: props.existingAvailability.default_start_time ?? '',
      default_end_time: props.existingAvailability.default_end_time ?? '',
    }
    dateEntries.value = (props.existingAvailability.available_dates ?? []).map((d) => ({
      date: parseDate(d.slot_date),
      start_time: d.start_time ?? '',
      end_time: d.end_time ?? '',
      fullDay: !(d.start_time || d.end_time),
    }))
  } else {
    form.value = {
      availability_type: 'fully_available',
      notes: '',
      default_start_time: '',
      default_end_time: '',
    }
    dateEntries.value = []
  }
}

watch(open, (value) => {
  if (value) resetForm()
})

function addDateEntry() {
  dateEntries.value.push({ date: undefined, start_time: '', end_time: '', fullDay: true })
}

function removeDateEntry(idx: number) {
  dateEntries.value.splice(idx, 1)
}

function toggleFullDay(idx: number, value: boolean) {
  dateEntries.value[idx].fullDay = value
  if (value) {
    dateEntries.value[idx].start_time = ''
    dateEntries.value[idx].end_time = ''
  }
}

function resolveTime(entry: { fullDay: boolean; start_time: string; end_time: string }): {
  start_time?: string
  end_time?: string
} {
  if (entry.fullDay) return {}
  return {
    start_time: entry.start_time || undefined,
    end_time: entry.end_time || undefined,
  }
}

function handleSubmit() {
  emit('save', {
    availability_type: form.value.availability_type,
    notes: form.value.notes || undefined,
    default_start_time:
      form.value.availability_type === 'time_range' && form.value.default_start_time
        ? form.value.default_start_time
        : undefined,
    default_end_time:
      form.value.availability_type === 'time_range' && form.value.default_end_time
        ? form.value.default_end_time
        : undefined,
    dates:
      form.value.availability_type === 'specific_dates'
        ? dateEntries.value
            .filter((e) => e.date)
            .map((e) => ({
              date: e.date!.toString(),
              ...resolveTime(e),
            }))
        : [],
  })
}

defineExpose({ resetForm })
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="dialog-availability">
      <DialogHeader>
        <DialogTitle>{{ t('duties.availability.title') }}</DialogTitle>
        <DialogDescription>{{ t('duties.availability.subtitle') }}</DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit.prevent="handleSubmit">
        <!-- Type selection -->
        <div class="space-y-2">
          <Label>{{ t('duties.availability.fields.type') }}</Label>
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="type in availabilityTypes"
              :key="type"
              type="button"
              :data-testid="`availability-type-${type}`"
              class="rounded-lg border-2 p-3 text-left text-sm transition-colors"
              :class="
                form.availability_type === type
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-muted-foreground'
              "
              @click="form.availability_type = type"
            >
              <div class="font-medium">
                {{ t(`duties.availability.types.${type}`) }}
              </div>
            </button>
          </div>
        </div>

        <!-- Time range (for time_range type) -->
        <div v-if="form.availability_type === 'time_range'" class="space-y-2">
          <Label>{{ t('duties.availability.fields.timeRange') }}</Label>
          <p class="text-xs text-muted-foreground">
            {{ t('duties.availability.fields.timeRangeHint') }}
          </p>
          <div class="flex items-center gap-3">
            <div class="flex items-center gap-1.5">
              <span class="text-xs text-muted-foreground">{{
                t('duties.availability.fields.startTime')
              }}</span>
              <TimePicker
                :model-value="form.default_start_time"
                @update:model-value="(val) => (form.default_start_time = val)"
              />
            </div>
            <span class="text-muted-foreground">–</span>
            <div class="flex items-center gap-1.5">
              <span class="text-xs text-muted-foreground">{{
                t('duties.availability.fields.endTime')
              }}</span>
              <TimePicker
                :model-value="form.default_end_time"
                @update:model-value="(val) => (form.default_end_time = val)"
              />
            </div>
          </div>
        </div>

        <!-- Specific dates -->
        <div v-if="form.availability_type === 'specific_dates'" class="space-y-3">
          <Label>{{ dateRangeLabel }}</Label>

          <!-- Date entries -->
          <div class="space-y-3">
            <div
              v-for="(entry, idx) in dateEntries"
              :key="idx"
              class="rounded-lg border p-3 space-y-2"
            >
              <!-- Date row + delete -->
              <div class="flex items-center gap-2">
                <div class="flex-1 min-w-0">
                  <DatePicker
                    :model-value="entry.date as DateValue | undefined"
                    :placeholder="t('duties.eventGroups.pickDate')"
                    :min-value="groupMinDate"
                    :max-value="groupMaxDate"
                    @update:model-value="
                      (val: DateValue | undefined) => (dateEntries[idx].date = val)
                    "
                  />
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  class="shrink-0"
                  @click="removeDateEntry(idx)"
                >
                  <Trash2 class="h-4 w-4 text-destructive" />
                </Button>
              </div>

              <!-- Full day toggle (ON = full day, OFF = show times) -->
              <div class="flex items-center justify-between">
                <label
                  :for="`fullday-toggle-${idx}`"
                  class="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none"
                >
                  <Clock class="h-3.5 w-3.5" />
                  {{
                    entry.fullDay
                      ? t('duties.availability.fields.fullDay')
                      : t('duties.availability.fields.setTimes')
                  }}
                </label>
                <Switch
                  :id="`fullday-toggle-${idx}`"
                  :model-value="entry.fullDay"
                  @update:model-value="(val: boolean) => toggleFullDay(idx, val)"
                />
              </div>

              <!-- Time pickers (shown when NOT full day) -->
              <div v-if="!entry.fullDay" class="flex items-center gap-3">
                <div class="flex items-center gap-1.5">
                  <span class="text-xs text-muted-foreground">{{
                    t('duties.availability.fields.startTime')
                  }}</span>
                  <TimePicker
                    :model-value="dateEntries[idx].start_time"
                    @update:model-value="(val) => (dateEntries[idx].start_time = val)"
                  />
                </div>
                <span class="text-muted-foreground">–</span>
                <div class="flex items-center gap-1.5">
                  <span class="text-xs text-muted-foreground">{{
                    t('duties.availability.fields.endTime')
                  }}</span>
                  <TimePicker
                    :model-value="dateEntries[idx].end_time"
                    @update:model-value="(val) => (dateEntries[idx].end_time = val)"
                  />
                </div>
              </div>
            </div>
          </div>
          <Button type="button" variant="outline" size="sm" data-testid="btn-add-date" @click="addDateEntry">
            + {{ t('duties.availability.fields.dates') }}
          </Button>
        </div>

        <!-- Notes -->
        <div class="space-y-2">
          <Label>{{ t('duties.availability.fields.notes') }}</Label>
          <Textarea v-model="form.notes" rows="2" />
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" data-testid="btn-cancel" @click="open = false">
            {{ t('common.actions.cancel') }}
          </Button>
          <Button type="submit" data-testid="btn-save">{{ t('common.actions.save') }}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
