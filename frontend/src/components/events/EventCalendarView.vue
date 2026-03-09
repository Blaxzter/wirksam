<script setup lang="ts">
import type { EventGroupRead, EventRead } from '@/client/types.gen'

import { DutyCalendar } from '@/components/events/duty-calendar'

defineProps<{
  events: EventRead[]
  eventGroups?: EventGroupRead[]
}>()

const emit = defineEmits<{
  navigate: [event: EventRead]
  navigateGroup: [group: EventGroupRead]
}>()
</script>

<template>
  <DutyCalendar
    :events="events"
    :event-groups="eventGroups"
    :show-bookings="false"
    @navigate-event="emit('navigate', $event)"
    @navigate-group="emit('navigateGroup', $event)"
  />
</template>
