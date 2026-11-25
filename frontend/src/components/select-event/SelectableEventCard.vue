<script setup lang="ts">
import { computed } from 'vue'

import { CalendarDays, Check, Globe, Lock, Star, Users } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent } from '@/components/ui/card'

import MarkdownBody from '@/components/content/MarkdownBody.vue'
import EventLogo from '@/components/events/EventLogo.vue'

import type { EventRead } from '@/client/types.gen'
import { isWordmark } from '@/lib/event-appearance'
import { roleLabelKey } from '@/lib/event-roles'
import { formatDate } from '@/lib/format'

export type EventStats = { taskCount: number; totalShifts: number; openShifts: number }

const props = defineProps<{
  event: EventRead
  stats: EventStats | undefined
  isCurrent: boolean
  isPending: boolean
  /**
   * "pick" — an event you already belong to, chosen with a radio-style tap.
   * "discover" — a public event you could ask to join, with its own button.
   */
  variant?: 'pick' | 'discover'
  requesting?: boolean
}>()

const wide = computed(() => isWordmark(props.event))

const emit = defineEmits<{
  select: [event: EventRead]
  requestJoin: [event: EventRead]
}>()

const { t } = useI18n()

const isDiscover = computed(() => props.variant === 'discover')
const requestStatus = computed(() => props.event.join_request_status ?? null)
const hasRequested = computed(() => requestStatus.value === 'pending')

// Clicking the card body only stages a selection in "pick" mode; in Discover
// the meaningful action is the explicit button, so the card is inert.
function handleActivate() {
  if (isDiscover.value) return
  emit('select', props.event)
}
</script>

<template>
  <Card
    data-testid="select-event-card"
    :data-event-id="props.event.id"
    :data-selected="props.isPending ? 'true' : undefined"
    :role="isDiscover ? undefined : 'radio'"
    :aria-checked="isDiscover ? undefined : props.isPending"
    :tabindex="isDiscover ? undefined : 0"
    class="transition-colors"
    :class="[
      isDiscover ? '' : 'cursor-pointer hover:border-primary',
      props.isPending ? 'border-primary ring-2 ring-primary/30' : '',
    ]"
    @click="handleActivate"
    @keydown.enter.prevent="handleActivate"
    @keydown.space.prevent="handleActivate"
  >
    <!-- A wordmark is wide: it gets a row of its own above the details, with
         the action beside it, rather than squeezing the details into a strip. -->
    <CardContent
      class="gap-4 p-5"
      :class="wide ? 'grid grid-cols-[minmax(0,1fr)_auto] items-start' : 'flex items-center'"
    >
      <EventLogo :event="props.event" size="lg" class="self-start" />
      <div class="min-w-0 flex-1 space-y-1.5" :class="{ 'col-span-2 row-start-2': wide }">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="truncate text-lg font-semibold">{{ props.event.name }}</h3>
          <Badge v-if="props.isCurrent" variant="secondary">
            {{ t('duties.selectEvent.pick.current') }}
          </Badge>
          <Badge v-if="props.event.my_role" variant="outline" data-testid="event-role-badge">
            {{ t(roleLabelKey(props.event.my_role)) }}
          </Badge>
          <Badge v-if="props.event.is_featured" variant="secondary" class="gap-1">
            <Star class="h-3 w-3" />
            {{ t('duties.events.featured.badge') }}
          </Badge>
          <Badge v-if="props.event.status === 'draft'" variant="outline">
            {{ t('duties.events.status.draft') }}
          </Badge>
        </div>

        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span class="flex items-center gap-2">
            <CalendarDays class="h-4 w-4 shrink-0" />
            {{ formatDate(props.event.start_date) }} – {{ formatDate(props.event.end_date) }}
          </span>
          <span class="flex items-center gap-1.5">
            <Users class="h-4 w-4 shrink-0" />
            {{
              t(
                'duties.events.members.count',
                { count: props.event.member_count ?? 0 },
                props.event.member_count ?? 0,
              )
            }}
          </span>
          <span class="flex items-center gap-1.5">
            <component
              :is="props.event.visibility === 'public' ? Globe : Lock"
              class="h-4 w-4 shrink-0"
            />
            {{ t(`duties.events.visibility.${props.event.visibility}.label`) }}
          </span>
        </div>

        <p v-if="!isDiscover" class="text-sm font-medium">
          {{
            t(
              'duties.selectEvent.pick.stats',
              {
                tasks: props.stats?.taskCount ?? 0,
                shifts: props.stats?.openShifts ?? 0,
              },
              props.stats?.taskCount ?? 0,
            )
          }}
        </p>
        <MarkdownBody
          v-else-if="props.event.description"
          :source="props.event.description"
          :clamp="2"
          class="text-sm text-muted-foreground"
        />
      </div>

      <!-- Discover: an explicit request-to-join action -->
      <div v-if="isDiscover" class="shrink-0" :class="{ 'col-start-2 row-start-1': wide }">
        <Badge v-if="hasRequested" variant="secondary" data-testid="join-requested-badge">
          {{ t('duties.events.join.requested') }}
        </Badge>
        <Button
          v-else
          size="sm"
          data-testid="btn-request-join"
          :disabled="props.requesting"
          @click.stop="emit('requestJoin', props.event)"
        >
          {{ t('duties.events.join.request') }}
        </Button>
      </div>

      <!-- Pick: radio-style indicator -->
      <div
        v-else
        :class="[
          'flex size-11 shrink-0 items-center justify-center rounded-full transition-colors',
          wide ? 'col-start-2 row-start-1' : '',
          props.isPending
            ? 'bg-primary text-primary-foreground'
            : 'border-2 border-muted-foreground/30',
        ]"
        aria-hidden="true"
      >
        <Check v-if="props.isPending" class="h-5 w-5" :stroke-width="2.5" />
      </div>
    </CardContent>
  </Card>
</template>
