<script setup lang="ts">
import { computed } from 'vue'

import { Globe, Lock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import EventOptionCards from '@/components/events/EventOptionCards.vue'

import type { EventVisibility } from '@/lib/event-roles'

const model = defineModel<EventVisibility>({ required: true })

const { t } = useI18n()

const options = computed(() => [
  {
    value: 'private' as const,
    label: t('duties.events.visibility.private.label'),
    hint: t('duties.events.visibility.private.hint'),
    icon: Lock,
  },
  {
    value: 'public' as const,
    label: t('duties.events.visibility.public.label'),
    hint: t('duties.events.visibility.public.hint'),
    icon: Globe,
  },
])
</script>

<template>
  <EventOptionCards v-model="model" :options="options" testid-prefix="btn-visibility-" />
</template>
