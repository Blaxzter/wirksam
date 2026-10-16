<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { ChevronDown, ChevronUp, Clock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import HoursBreakdown from '@/components/events/HoursBreakdown.vue'

import type { VolunteerHoursDetail } from '@/client/types.gen'
import { formatHours } from '@/lib/format'

const { t } = useI18n()
const { get } = useAuthenticatedClient()
const authStore = useAuthStore()

const detail = ref<VolunteerHoursDetail | null>(null)
const expanded = ref(false)

const eventId = computed(() => authStore.selectedEventId)
const userId = computed(() => authStore.profile?.id ?? null)

const hoursLabel = (minutes: number) => t('duties.hours.unit', { value: formatHours(minutes) })

const isEmpty = computed(
  () =>
    !!detail.value &&
    detail.value.summary.total_minutes === 0 &&
    detail.value.summary.upcoming_shift_count === 0,
)

async function load() {
  detail.value = null
  if (!eventId.value || !userId.value) return
  try {
    const res = await get<{ data: VolunteerHoursDetail }>({
      url: `/events/${eventId.value}/hours/${userId.value}`,
    })
    detail.value = res.data
  } catch {
    // Not in the selected event (any more) — the card simply stays hidden.
  }
}

watch([eventId, userId], load)
onMounted(load)

defineExpose({ reload: load })
</script>

<template>
  <Card v-if="detail" data-testid="my-hours-card">
    <CardHeader class="pb-3">
      <CardTitle class="flex items-center gap-2 text-lg">
        <Clock class="h-5 w-5 shrink-0" />
        {{ t('duties.hours.my.title') }}
      </CardTitle>
      <CardDescription>{{ t('duties.hours.my.subtitle') }}</CardDescription>
    </CardHeader>

    <CardContent class="space-y-4">
      <p v-if="isEmpty" class="text-sm text-muted-foreground">
        {{ t('duties.hours.my.empty') }}
      </p>

      <template v-else>
        <dl class="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <dt class="text-xs text-muted-foreground">{{ t('duties.hours.my.total') }}</dt>
            <dd class="text-2xl font-bold tabular-nums" data-testid="my-hours-total">
              {{ hoursLabel(detail.summary.total_minutes) }}
            </dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">{{ t('duties.hours.my.fromShifts') }}</dt>
            <dd class="text-lg font-semibold tabular-nums">
              {{ hoursLabel(detail.summary.shift_minutes) }}
            </dd>
            <dd class="text-xs text-muted-foreground">
              {{
                t(
                  'duties.hours.my.shiftCount',
                  { count: detail.summary.shift_count },
                  detail.summary.shift_count,
                )
              }}
            </dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">{{ t('duties.hours.my.manual') }}</dt>
            <dd class="text-lg font-semibold tabular-nums">
              {{ hoursLabel(detail.summary.manual_minutes) }}
            </dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">{{ t('duties.hours.my.upcoming') }}</dt>
            <dd class="text-lg font-semibold tabular-nums text-muted-foreground">
              {{ hoursLabel(detail.summary.upcoming_shift_minutes) }}
            </dd>
          </div>
        </dl>

        <Button
          variant="ghost"
          size="sm"
          class="-ml-2"
          data-testid="btn-toggle-hours-breakdown"
          @click="expanded = !expanded"
        >
          <component :is="expanded ? ChevronUp : ChevronDown" class="mr-1.5 h-4 w-4" />
          {{ expanded ? t('duties.hours.my.hideDetails') : t('duties.hours.my.showDetails') }}
        </Button>
        <HoursBreakdown v-if="expanded" :detail="detail" />
      </template>
    </CardContent>
  </Card>
</template>
