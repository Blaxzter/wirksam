<script setup lang="ts">
/**
 * What the QR code on a printed event sheet opens.
 *
 * Someone in the event lands on its tasks, with the event selected, because the
 * task list always shows the selected one. Anyone else lands on Discover, where
 * a public event can be asked to join. There are sheets on paper out there
 * pointing at this address, so it has to stay.
 */
import { onMounted } from 'vue'

import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

onMounted(async () => {
  const eventId = route.params.eventId as string
  if (!authStore.isEventMember(eventId)) {
    await router.replace({
      name: 'select-event',
      query: { mode: authStore.selectedEventId ? 'switch' : 'onboarding', tab: 'discover' },
    })
    return
  }
  try {
    if (authStore.selectedEventId !== eventId) await authStore.setSelectedEvent(eventId)
    await router.replace({ name: 'tasks' })
  } catch (error) {
    toastApiError(error)
    await router.replace({ name: 'home' })
  }
})
</script>

<template>
  <div class="py-12 text-center text-muted-foreground">
    {{ t('common.states.loading') }}
  </div>
</template>
