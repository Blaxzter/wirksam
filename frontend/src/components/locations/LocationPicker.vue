<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import { useLocations } from '@/composables/useLocations'

import Input from '@/components/ui/input/Input.vue'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import LocationFormDialog from '@/components/locations/LocationFormDialog.vue'

import type { LocationRead } from '@/client/types.gen'

/**
 * Pick where a task or shift happens: one of the event's locations, a free
 * text, or nothing. Admins can also create a location on the spot.
 *
 * Two models, because the API wants both: `locationId` is the link and `text`
 * the display name. Choosing a location sets the text to its name; choosing
 * "other" clears the link and shows an input for the text; "no location"
 * clears both. Callers send `location_id` and `location` together — a text
 * without the id unlinks the row on the server.
 *
 * `inputId` lands on the select trigger, so a `<Label :for>` outside works.
 */
const props = withDefaults(
  defineProps<{
    eventId: string | null | undefined
    inputId?: string
    /** Offer "New location…". Defaults to whether the user manages the event. */
    allowCreate?: boolean
    /** Stack the create dialog above an already open dialog. */
    priority?: boolean
    /**
     * Leave out "choose an event first" while there is no event — for a form
     * that is creating the event, where there is nothing to choose.
     */
    hideNoEventHint?: boolean
  }>(),
  { inputId: undefined, allowCreate: undefined, priority: false, hideNoEventHint: false },
)

const locationId = defineModel<string | null>('locationId', { default: null })
const text = defineModel<string>('text', { default: '' })

const { t } = useI18n()
const authStore = useAuthStore()

const { locations } = useLocations(() => props.eventId ?? null)

const NONE = '__none'
const CUSTOM = '__custom'
const CREATE = '__new'

const canCreate = computed(
  () => !!props.eventId && (props.allowCreate ?? authStore.canManageEvent(props.eventId)),
)

function selectionFromModels(): string {
  if (locationId.value) return locationId.value
  return text.value.trim() ? CUSTOM : NONE
}

const selection = ref<string>(selectionFromModels())

// The models can change from outside after mount — an edit form fills in once
// its data has loaded. Follow them, but don't drop out of "other" just because
// its text was emptied while typing.
watch([locationId, text], () => {
  const next = selectionFromModels()
  if (next === NONE && selection.value === CUSTOM) return
  selection.value = next
})

// A linked location not (yet) in the list — still loading, or just created —
// keeps an option so the trigger shows its name rather than nothing.
const orphan = computed<Pick<LocationRead, 'id' | 'name'> | null>(() => {
  const id = locationId.value
  if (!id || locations.value.some((l) => l.id === id)) return null
  return { id, name: text.value.trim() || '…' }
})

const formOpen = ref(false)

function onSelect(value: unknown) {
  const v = String(value ?? NONE)
  if (v === CREATE) {
    // Not a real choice: keep the current one until the dialog saves.
    formOpen.value = true
    return
  }
  selection.value = v
  if (v === NONE) {
    locationId.value = null
    text.value = ''
  } else if (v === CUSTOM) {
    // Keep the text of the location that was picked before as a starting
    // point; the link goes.
    locationId.value = null
  } else {
    const loc = locations.value.find((l) => l.id === v)
    locationId.value = v
    if (loc) text.value = loc.name
  }
}

function onCreated(location: LocationRead) {
  selection.value = location.id
  locationId.value = location.id
  text.value = location.name
}
</script>

<template>
  <div class="space-y-2">
    <Select :model-value="selection" @update:model-value="onSelect">
      <SelectTrigger :id="inputId" class="w-full" data-testid="location-picker">
        <SelectValue :placeholder="t('locations.picker.none')" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem :value="NONE" data-testid="location-option-none">
          {{ t('locations.picker.none') }}
        </SelectItem>
        <SelectItem
          v-for="location in locations"
          :key="location.id"
          :value="location.id"
          :data-testid="`location-option-${location.id}`"
        >
          {{ location.name }}
        </SelectItem>
        <SelectItem v-if="orphan" :value="orphan.id">{{ orphan.name }}</SelectItem>
        <SelectSeparator />
        <SelectItem :value="CUSTOM" data-testid="location-option-custom">
          {{ t('locations.picker.custom') }}
        </SelectItem>
        <SelectItem v-if="canCreate" :value="CREATE" data-testid="location-option-create">
          {{ t('locations.picker.createNew') }}
        </SelectItem>
      </SelectContent>
    </Select>

    <p
      v-if="!eventId && !hideNoEventHint"
      class="text-muted-foreground text-xs"
      data-testid="location-picker-no-event"
    >
      {{ t('locations.picker.noEvent') }}
    </p>

    <Input
      v-if="selection === CUSTOM"
      :id="inputId ? `${inputId}-custom` : undefined"
      v-model="text"
      :placeholder="t('locations.picker.customPlaceholder')"
      :aria-label="t('locations.picker.customPlaceholder')"
      data-testid="location-custom-input"
    />

    <LocationFormDialog
      v-if="canCreate && eventId"
      v-model:open="formOpen"
      :event-id="eventId"
      :initial-name="selection === CUSTOM ? text.trim() : ''"
      :priority="priority"
      @saved="onCreated"
    />
  </div>
</template>
