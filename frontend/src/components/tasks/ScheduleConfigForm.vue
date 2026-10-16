<script setup lang="ts">
import { computed, watch } from 'vue'

import { CircleAlert, Plus, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'
import type { RemainderMode } from '@/composables/useShiftPreview'

import Button from '@/components/ui/button/Button.vue'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import Separator from '@/components/ui/separator/Separator.vue'
import { TimePicker } from '@/components/ui/time-picker'

const props = defineProps<{
  hasRemainder: boolean
  availableDates: string[]
  showOverrides?: boolean
  // HH:MM:SS — when both set, a soft reminder appears if the configured task
  // schedule falls outside the event's default window.
  eventStartTime?: string | null
  eventEndTime?: string | null
}>()

const defaultStartTime = defineModel<string>('defaultStartTime', { required: true })
const defaultEndTime = defineModel<string>('defaultEndTime', { required: true })
const shiftDurationMinutes = defineModel<number>('shiftDurationMinutes', { required: true })
const peoplePerShift = defineModel<number>('peoplePerShift', { required: true })
const remainderMode = defineModel<RemainderMode>('remainderMode', { required: true })
const overrides = defineModel<Array<{ date: string; startTime: string; endTime: string }>>(
  'overrides',
  { required: true },
)

const { t } = useI18n()
const { formatDateLabel } = useFormatters()

const durationOptions = [15, 30, 45, 60, 90, 120]

const addOverride = () => {
  overrides.value.push({
    date: '',
    startTime: defaultStartTime.value,
    endTime: defaultEndTime.value,
  })
}

const removeOverride = (index: number) => {
  overrides.value.splice(index, 1)
}

watch(
  () => props.hasRemainder,
  (val) => {
    if (!val) remainderMode.value = 'drop'
  },
)

function toMinutes(hhmm: string): number | null {
  const [h, m] = hhmm.split(':')
  const hi = parseInt(h, 10)
  const mi = parseInt(m, 10)
  if (Number.isNaN(hi) || Number.isNaN(mi)) return null
  return hi * 60 + mi
}

const eventWindow = computed(() => {
  if (!props.eventStartTime || !props.eventEndTime) return null
  const start = toMinutes(props.eventStartTime.slice(0, 5))
  const end = toMinutes(props.eventEndTime.slice(0, 5))
  if (start === null || end === null) return null
  return { start, end, label: `${props.eventStartTime.slice(0, 5)}–${props.eventEndTime.slice(0, 5)}` }
})

const outsideEventWindow = computed(() => {
  const w = eventWindow.value
  if (!w) return false
  const start = toMinutes(defaultStartTime.value)
  const end = toMinutes(defaultEndTime.value)
  if (start === null || end === null) return false
  return start < w.start || end > w.end
})
</script>

<template>
  <div class="grid grid-cols-2 gap-4" data-testid="input-daily-window">
    <div class="space-y-2">
      <Label>{{ t('duties.tasks.createView.schedule.defaultStartTime') }}</Label>
      <TimePicker v-model="defaultStartTime" />
    </div>
    <div class="space-y-2">
      <Label>{{ t('duties.tasks.createView.schedule.defaultEndTime') }}</Label>
      <TimePicker v-model="defaultEndTime" />
    </div>
  </div>
  <p
    v-if="outsideEventWindow && eventWindow"
    class="text-muted-foreground -mt-2 flex items-start gap-1.5 text-xs"
    data-testid="task-outside-event-window"
  >
    <CircleAlert class="text-amber-500 mt-0.5 size-3.5 shrink-0" />
    <span>{{ t('duties.tasks.createView.schedule.outsideEventWindow', { range: eventWindow.label }) }}</span>
  </p>
  <div class="grid grid-cols-2 gap-4">
    <div class="space-y-2" data-testid="input-shift-duration">
      <Label>{{ t('duties.tasks.createView.schedule.slotDuration') }}</Label>
      <Select v-model="shiftDurationMinutes">
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="d in durationOptions" :key="d" :value="d">
            {{ t('duties.tasks.createView.schedule.minutes', { n: d }) }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>
    <div class="space-y-2" data-testid="input-people-per-shift">
      <Label>{{ t('duties.tasks.createView.schedule.peoplePerShift') }}</Label>
      <Input v-model.number="peoplePerShift" type="number" min="1" />
    </div>
  </div>

  <!-- Remainder handling -->
  <Transition
    enter-active-class="grid transition-[grid-template-rows,opacity] duration-300 ease-out"
    enter-from-class="grid-rows-[0fr] opacity-0"
    enter-to-class="grid-rows-[1fr] opacity-100"
    leave-active-class="grid transition-[grid-template-rows,opacity] duration-200 ease-in"
    leave-from-class="grid-rows-[1fr] opacity-100"
    leave-to-class="grid-rows-[0fr] opacity-0"
  >
    <div v-if="hasRemainder">
      <div class="overflow-hidden">
        <div class="space-y-2">
          <Label>{{ t('duties.tasks.createView.schedule.remainder') }}</Label>
          <p class="text-sm text-muted-foreground">
            {{ t('duties.tasks.createView.schedule.remainderDesc') }}
          </p>
          <RadioGroup v-model="remainderMode" class="flex gap-4 pt-1">
            <div class="flex items-center gap-2">
              <RadioGroupItem value="drop" id="rm-drop" />
              <Label for="rm-drop">{{
                t('duties.tasks.createView.schedule.remainderMode.drop')
              }}</Label>
            </div>
            <div class="flex items-center gap-2">
              <RadioGroupItem value="short" id="rm-short" />
              <Label for="rm-short">{{
                t('duties.tasks.createView.schedule.remainderMode.short')
              }}</Label>
            </div>
            <div class="flex items-center gap-2">
              <RadioGroupItem value="extend" id="rm-extend" />
              <Label for="rm-extend">{{
                t('duties.tasks.createView.schedule.remainderMode.extend')
              }}</Label>
            </div>
          </RadioGroup>
        </div>
      </div>
    </div>
  </Transition>

  <!-- Date exceptions -->
  <template v-if="showOverrides">
    <Separator />
    <div class="space-y-3">
      <div class="flex items-center justify-between gap-2">
        <div class="min-w-0">
          <p class="font-medium">{{ t('duties.tasks.createView.schedule.overrides') }}</p>
          <p class="text-sm text-muted-foreground">
            {{ t('duties.tasks.createView.schedule.overridesDesc') }}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          class="shrink-0"
          :disabled="availableDates.length === 0"
          @click="addOverride"
        >
          <Plus class="sm:mr-1.5 h-4 w-4" />
          <span class="hidden sm:inline">{{
            t('duties.tasks.createView.schedule.addException')
          }}</span>
        </Button>
      </div>

      <div
        v-for="(override, index) in overrides"
        :key="index"
        class="flex items-end gap-3 rounded-md border p-3"
      >
        <div class="flex-1 space-y-2">
          <Label>{{ t('duties.shifts.fields.date') }}</Label>
          <Select v-model="override.date">
            <SelectTrigger class="min-w-40">
              <SelectValue :placeholder="t('duties.shifts.pickDate')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="d in availableDates" :key="d" :value="d">
                {{ formatDateLabel(d) }}
              </SelectItem>
              <!-- Keep selected date visible even if filtered -->
              <SelectItem
                v-if="override.date && !availableDates.includes(override.date)"
                :value="override.date"
              >
                {{ formatDateLabel(override.date) }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label>{{ t('duties.shifts.fields.startTime') }}</Label>
          <TimePicker v-model="override.startTime" />
        </div>
        <div class="space-y-2">
          <Label>{{ t('duties.shifts.fields.endTime') }}</Label>
          <TimePicker v-model="override.endTime" />
        </div>
        <Button
          variant="ghost"
          size="icon"
          :aria-label="t('duties.tasks.createView.schedule.removeExceptionLabel')"
          @click="removeOverride(index)"
        >
          <Trash2 class="h-4 w-4 text-destructive" />
        </Button>
      </div>
    </div>
  </template>
</template>
