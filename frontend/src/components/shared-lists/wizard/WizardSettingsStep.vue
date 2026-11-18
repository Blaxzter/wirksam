<script setup lang="ts">
/**
 * The wizard's second step: what the list says, what it asks for, what others
 * see on it, how many shifts one person may take, and how long it stays open.
 * Every field is a model of the parent's draft.
 */
import { computed } from 'vue'

import { type DateValue, parseDate } from '@internationalized/date'
import { TriangleAlert } from '@lucide/vue'
import type { AcceptableValue } from 'reka-ui'
import { useI18n } from 'vue-i18n'

import { useSharedListFormat } from '@/composables/useSharedListFormat'

import { DatePicker } from '@/components/ui/date-picker'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

import {
  type AskMode,
  type EndsMode,
  INTRO_MAX,
  SHARE_NOTE_MAX,
  type ShowNames,
  TITLE_MAX,
} from '@/lib/shared-list-draft'
import type { WizardShift } from '@/lib/shared-list-selection'

const props = defineProps<{
  /** What `show_names` was before this edit; `null` while creating a list. */
  savedShowNames: ShowNames | null
  /** How many shifts the list offers. */
  includedCount: number
  /** The choices for shifts per person, `null` being "as many as are free". */
  maxOptions: readonly (number | null)[]
  /** The shift that starts last, which a "last shift" list closes with. */
  lastShift: WizardShift | null
  /** Today on the event's clock, `YYYY-MM-DD`. */
  today: string
}>()

const title = defineModel<string>('title', { required: true })
const intro = defineModel<string>('intro', { required: true })
const shareNote = defineModel<string>('shareNote', { required: true })
const askEmail = defineModel<AskMode>('askEmail', { required: true })
const askPhone = defineModel<AskMode>('askPhone', { required: true })
const showNames = defineModel<ShowNames>('showNames', { required: true })
const maxPerPerson = defineModel<number | null>('maxPerPerson', { required: true })
const endsMode = defineModel<EndsMode>('endsMode', { required: true })
const endsOn = defineModel<string | null>('endsOn', { required: true })

const { t } = useI18n()
const { longDay, shortDay, formatTime } = useSharedListFormat()

/** E-mail can be off in the API, but the wizard offers only these two. */
const EMAIL_MODES: readonly AskMode[] = ['required', 'optional']
const PHONE_MODES: readonly AskMode[] = ['off', 'optional', 'required']
const SHOW_NAMES: readonly ShowNames[] = ['none', 'first']

const showNamesChanged = computed(
  () => props.savedShowNames !== null && showNames.value !== props.savedShowNames,
)

/** The select speaks strings; '' stands for "as many as are free". */
/** "As many as are free" as the picker's value: reka's Select keeps "" for "nothing chosen". */
const UNLIMITED = 'all'
const maxPerValue = computed<AcceptableValue>({
  get: () => (maxPerPerson.value === null ? UNLIMITED : String(maxPerPerson.value)),
  set: (value) => {
    maxPerPerson.value = value === UNLIMITED || value == null ? null : Number(value)
  },
})

const endsOnValue = computed<DateValue | undefined>({
  get: () => (endsOn.value ? parseDate(endsOn.value) : undefined),
  set: (value) => {
    endsOn.value = value ? value.toString() : null
  },
})

const minDate = computed(() => parseDate(props.today))
const maxDate = computed(() => (props.lastShift ? parseDate(props.lastShift.date) : undefined))

/** "Samstag, 6. Dezember, 16:00": an untimed shift starts with its day. */
const lastShiftWhen = computed(() =>
  props.lastShift
    ? t('sharedListWizard.settings.ends.lastShift.hint', {
        date: longDay(props.lastShift.date),
        time: formatTime(props.lastShift.start_time ?? '00:00'),
      })
    : '',
)

function setAsk(field: 'email' | 'phone', value: unknown) {
  // A single toggle group hands back '' when its pressed item is clicked
  // again; one of the modes always stays chosen.
  if (typeof value !== 'string' || !value) return
  if (field === 'email') askEmail.value = value as AskMode
  else askPhone.value = value as AskMode
}
</script>

<template>
  <div class="grid gap-6">
    <div class="grid gap-2">
      <Label for="wizard-title">{{ t('sharedListWizard.settings.title.label') }}</Label>
      <Input
        id="wizard-title"
        v-model="title"
        :maxlength="TITLE_MAX"
        aria-describedby="wizard-title-hint"
        data-testid="wizard-title"
      />
      <p id="wizard-title-hint" class="text-xs text-muted-foreground">
        {{ t('sharedListWizard.settings.title.hint') }}
      </p>
    </div>

    <div class="grid gap-2">
      <Label for="wizard-intro">
        {{ t('sharedListWizard.settings.intro.label') }}
        <span class="font-normal text-muted-foreground">
          {{ t('sharedListWizard.settings.optional') }}
        </span>
      </Label>
      <Textarea
        id="wizard-intro"
        v-model="intro"
        rows="3"
        :maxlength="INTRO_MAX"
        :placeholder="t('sharedListWizard.settings.intro.placeholder')"
        data-testid="wizard-intro"
      />
    </div>

    <div class="grid gap-2">
      <Label for="wizard-share-note">
        {{ t('sharedListWizard.settings.shareNote.label') }}
        <span class="font-normal text-muted-foreground">
          {{ t('sharedListWizard.settings.optional') }}
        </span>
      </Label>
      <Input
        id="wizard-share-note"
        v-model="shareNote"
        :maxlength="SHARE_NOTE_MAX"
        :placeholder="t('sharedListWizard.settings.shareNote.placeholder')"
        aria-describedby="wizard-share-note-hint"
        data-testid="wizard-share-note"
      />
      <p id="wizard-share-note-hint" class="text-xs text-muted-foreground">
        {{ t('sharedListWizard.settings.shareNote.hint') }}
      </p>
    </div>

    <fieldset class="grid gap-3">
      <legend class="mb-3 text-sm font-semibold">
        {{ t('sharedListWizard.settings.ask.legend') }}
      </legend>
      <div class="divide-y rounded-lg border">
        <div class="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
          <span>{{ t('sharedListWizard.settings.ask.name') }}</span>
          <span class="text-muted-foreground">{{ t('sharedListWizard.settings.ask.always') }}</span>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm">
          <span id="wizard-ask-email">{{ t('sharedListWizard.settings.ask.email') }}</span>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            :model-value="askEmail"
            aria-labelledby="wizard-ask-email"
            data-testid="wizard-ask-email"
            @update:model-value="(value) => setAsk('email', value)"
          >
            <ToggleGroupItem
              v-for="mode in EMAIL_MODES"
              :key="mode"
              :value="mode"
              :data-testid="`wizard-ask-email-${mode}`"
            >
              {{ t(`sharedListWizard.settings.ask.${mode}`) }}
            </ToggleGroupItem>
          </ToggleGroup>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm">
          <span id="wizard-ask-phone">{{ t('sharedListWizard.settings.ask.phone') }}</span>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            :model-value="askPhone"
            aria-labelledby="wizard-ask-phone"
            data-testid="wizard-ask-phone"
            @update:model-value="(value) => setAsk('phone', value)"
          >
            <ToggleGroupItem
              v-for="mode in PHONE_MODES"
              :key="mode"
              :value="mode"
              :data-testid="`wizard-ask-phone-${mode}`"
            >
              {{ t(`sharedListWizard.settings.ask.${mode}`) }}
            </ToggleGroupItem>
          </ToggleGroup>
        </div>
      </div>
      <p v-if="askEmail !== 'required'" class="flex items-start gap-1.5 text-xs text-warning">
        <TriangleAlert class="mt-px size-3.5 shrink-0" aria-hidden="true" />
        {{ t('sharedListWizard.settings.ask.emailOptionalWarning') }}
      </p>
    </fieldset>

    <fieldset class="grid gap-3">
      <legend id="wizard-show-names-legend" class="mb-3 text-sm font-semibold">
        {{ t('sharedListWizard.settings.showNames.legend') }}
      </legend>
      <RadioGroup
        v-model="showNames"
        aria-labelledby="wizard-show-names-legend"
        class="grid gap-2"
        data-testid="wizard-show-names"
      >
        <div
          v-for="option in SHOW_NAMES"
          :key="option"
          class="flex items-start gap-3 rounded-lg border p-3"
        >
          <RadioGroupItem
            :id="`wizard-show-names-${option}`"
            :value="option"
            class="mt-0.5"
            :data-testid="`wizard-show-names-${option}`"
          />
          <Label :for="`wizard-show-names-${option}`" class="grid cursor-pointer gap-1">
            <span>{{ t(`sharedListWizard.settings.showNames.${option}.label`) }}</span>
            <span class="text-xs leading-snug font-normal text-muted-foreground">
              {{ t(`sharedListWizard.settings.showNames.${option}.hint`) }}
            </span>
          </Label>
        </div>
      </RadioGroup>
      <p
        v-if="showNamesChanged"
        class="flex items-start gap-1.5 text-xs text-warning"
        data-testid="wizard-show-names-changed"
      >
        <TriangleAlert class="mt-px size-3.5 shrink-0" aria-hidden="true" />
        {{ t('sharedListWizard.settings.showNames.changed') }}
      </p>
    </fieldset>

    <div class="grid gap-2 sm:max-w-xs">
      <Label for="wizard-max-per">{{ t('sharedListWizard.settings.maxPer.label') }}</Label>
      <Select v-model="maxPerValue">
        <SelectTrigger
          id="wizard-max-per"
          class="w-full"
          aria-describedby="wizard-max-per-hint"
          data-testid="wizard-max-per"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem
            v-for="option in maxOptions"
            :key="option ?? UNLIMITED"
            :value="option === null ? UNLIMITED : String(option)"
          >
            {{
              option === null
                ? t('sharedListWizard.settings.maxPer.unlimited')
                : t('sharedListWizard.settings.maxPer.atMost', { count: option })
            }}
          </SelectItem>
        </SelectContent>
      </Select>
      <p id="wizard-max-per-hint" class="text-xs text-muted-foreground">
        {{ t('sharedListWizard.settings.maxPer.hint', { count: includedCount }, includedCount) }}
      </p>
    </div>

    <fieldset class="grid gap-3">
      <legend id="wizard-ends-legend" class="mb-3 text-sm font-semibold">
        {{ t('sharedListWizard.settings.ends.legend') }}
      </legend>
      <RadioGroup
        v-model="endsMode"
        aria-labelledby="wizard-ends-legend"
        class="grid gap-2"
        data-testid="wizard-ends"
      >
        <div class="flex items-start gap-3 rounded-lg border p-3">
          <RadioGroupItem
            id="wizard-ends-last_shift"
            value="last_shift"
            class="mt-0.5"
            data-testid="wizard-ends-last_shift"
          />
          <Label for="wizard-ends-last_shift" class="grid cursor-pointer gap-1">
            <span>{{ t('sharedListWizard.settings.ends.lastShift.label') }}</span>
            <span class="text-xs leading-snug font-normal text-muted-foreground">
              {{ lastShiftWhen }}
            </span>
          </Label>
        </div>
        <div class="flex items-start gap-3 rounded-lg border p-3">
          <RadioGroupItem
            id="wizard-ends-date"
            value="date"
            class="mt-0.5"
            data-testid="wizard-ends-date"
          />
          <div class="grid min-w-0 flex-1 gap-3">
            <Label for="wizard-ends-date" class="grid cursor-pointer gap-1">
              <span>{{ t('sharedListWizard.settings.ends.date.label') }}</span>
              <span v-if="lastShift" class="text-xs leading-snug font-normal text-muted-foreground">
                {{
                  t('sharedListWizard.settings.ends.date.hint', { date: shortDay(lastShift.date) })
                }}
              </span>
            </Label>
            <div
              v-if="endsMode === 'date'"
              role="group"
              aria-labelledby="wizard-ends-on-label"
              class="grid gap-1.5 sm:max-w-xs"
              data-testid="wizard-ends-on"
            >
              <span id="wizard-ends-on-label" class="text-xs font-medium">
                {{ t('sharedListWizard.settings.ends.date.pick') }}
              </span>
              <DatePicker v-model="endsOnValue" :min-value="minDate" :max-value="maxDate" />
            </div>
          </div>
        </div>
        <div class="flex items-start gap-3 rounded-lg border p-3">
          <RadioGroupItem
            id="wizard-ends-manual"
            value="manual"
            class="mt-0.5"
            data-testid="wizard-ends-manual"
          />
          <Label for="wizard-ends-manual" class="grid cursor-pointer gap-1">
            <span>{{ t('sharedListWizard.settings.ends.manual.label') }}</span>
            <span class="text-xs leading-snug font-normal text-muted-foreground">
              {{ t('sharedListWizard.settings.ends.manual.hint') }}
            </span>
          </Label>
        </div>
      </RadioGroup>
    </fieldset>
  </div>
</template>
