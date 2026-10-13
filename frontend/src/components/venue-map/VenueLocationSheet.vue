<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import VenueLocationDetails from '@/components/venue-map/VenueLocationDetails.vue'

import type { LocationRead, VenueLocationStat } from '@/client/types.gen'

/**
 * `VenueLocationDetails` in a `ResponsiveDialog`: a bottom drawer on a phone,
 * a centred dialog on a tablet. A wide screen shows the details in the map's
 * side panel instead.
 */
const props = defineProps<{
  location: LocationRead | null
  /** The day shown on the map, `YYYY-MM-DD`. */
  day: string
  stat?: VenueLocationStat | null
}>()

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  booked: []
}>()

const { t } = useI18n()
const { formatDateLabel } = useFormatters()

const dayLabel = computed(() =>
  formatDateLabel(props.day, { weekday: 'long', day: 'numeric', month: 'long' }),
)
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent data-testid="location-sheet" dialog-class="sm:max-w-lg">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle data-testid="location-sheet-title">
          {{ location?.name }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="sr-only">
          {{ t('venueMap.sheet.shiftsOn', { day: dayLabel }) }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody v-if="location" class="pb-4">
        <VenueLocationDetails
          :location="location"
          :day="day"
          :stat="stat ?? null"
          :active="open"
          :show-heading="false"
          @booked="emit('booked')"
        />
      </ResponsiveDialogBody>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
