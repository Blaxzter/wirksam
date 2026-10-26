<script setup lang="ts">
/**
 * The organiser's to-do list, and only theirs — a plain member never gets this
 * block at all, because the backend sends `attention: null` for them.
 *
 * Every line is a count that implies an action, so every line is a link. The
 * card renders nothing when all four are zero: an empty "needs your attention"
 * panel trains people to stop reading it.
 */
import { computed } from 'vue'

import {
  AlertTriangle,
  ChevronRight,
  FileEdit,
  ShieldCheck,
  UserPlus,
  UsersRound,
} from '@lucide/vue'
import type { LucideIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import type { RouteLocationRaw } from 'vue-router'

import { teamsPageLocation } from '@/composables/useTeams'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { DashboardAttention } from '@/client'

const props = defineProps<{
  attention: DashboardAttention
  /** The event the counts are for; the team requests link to its Teams page. */
  eventId?: string | null
}>()

const { t } = useI18n()

interface AttentionItem {
  key: string
  icon: LucideIcon
  label: string
  urgent: boolean
  to: RouteLocationRaw
}

const items = computed<AttentionItem[]>(() => {
  // Every count carries a server-side default, so the generated client
  // types them optional. Filling them in once here keeps the four blocks
  // below reading as arithmetic rather than as null handling.
  const a = {
    empty_shifts_soon: props.attention.empty_shifts_soon ?? 0,
    short_shifts_soon: props.attention.short_shifts_soon ?? 0,
    pending_join_requests: props.attention.pending_join_requests ?? 0,
    pending_team_requests: props.attention.pending_team_requests ?? 0,
    draft_tasks: props.attention.draft_tasks ?? 0,
    horizon_days: props.attention.horizon_days ?? 7,
  }
  const out: AttentionItem[] = []
  if (a.empty_shifts_soon > 0) {
    out.push({
      key: 'empty',
      icon: AlertTriangle,
      urgent: true,
      label: t(
        'dashboard.home.attention.emptyShifts',
        { count: a.empty_shifts_soon, days: a.horizon_days },
        a.empty_shifts_soon,
      ),
      to: { name: 'tasks', query: { hide_full: 'true' } },
    })
  }
  if (a.short_shifts_soon > 0) {
    out.push({
      key: 'short',
      icon: UsersRound,
      urgent: false,
      label: t(
        'dashboard.home.attention.shortShifts',
        { count: a.short_shifts_soon, days: a.horizon_days },
        a.short_shifts_soon,
      ),
      to: { name: 'tasks', query: { hide_full: 'true' } },
    })
  }
  if (a.pending_join_requests > 0) {
    out.push({
      key: 'requests',
      icon: UserPlus,
      urgent: false,
      label: t(
        'dashboard.home.attention.joinRequests',
        { count: a.pending_join_requests },
        a.pending_join_requests,
      ),
      to: { name: 'my-events', query: { tab: 'requests' } },
    })
  }
  if (a.pending_team_requests > 0) {
    out.push({
      key: 'team-requests',
      icon: ShieldCheck,
      urgent: false,
      label: t(
        'teamLocks.attention.teamRequests',
        { count: a.pending_team_requests },
        a.pending_team_requests,
      ),
      to: teamsPageLocation(props.eventId),
    })
  }
  if (a.draft_tasks > 0) {
    out.push({
      key: 'drafts',
      icon: FileEdit,
      urgent: false,
      label: t('dashboard.home.attention.draftTasks', { count: a.draft_tasks }, a.draft_tasks),
      to: { name: 'tasks' },
    })
  }
  return out
})
</script>

<template>
  <Card v-if="items.length > 0" data-testid="dashboard-attention">
    <CardHeader>
      <CardTitle class="text-base">{{ t('dashboard.home.attention.title') }}</CardTitle>
    </CardHeader>
    <CardContent class="space-y-1">
      <RouterLink
        v-for="item in items"
        :key="item.key"
        :to="item.to"
        :data-testid="'attention-' + item.key"
        class="flex items-center gap-3 rounded-lg border border-transparent p-2 text-sm transition-colors hover:border-border hover:bg-accent/50"
      >
        <span
          class="flex size-8 shrink-0 items-center justify-center rounded-full"
          :class="
            item.urgent ? 'bg-destructive/10 text-destructive' : 'bg-muted text-muted-foreground'
          "
        >
          <component :is="item.icon" class="h-4 w-4" />
        </span>
        <span class="min-w-0 flex-1">{{ item.label }}</span>
        <ChevronRight class="h-4 w-4 shrink-0 text-muted-foreground" />
      </RouterLink>
    </CardContent>
  </Card>
</template>
