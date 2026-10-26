<script setup lang="ts">
import { computed } from 'vue'

import { ChevronLeft, ChevronRight, Lock, TriangleAlert } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'
import Button from '@/components/ui/button/Button.vue'

import TeamManagePanel from '@/components/events/teams/TeamManagePanel.vue'

import type { EventMemberRead, EventTeamRead } from '@/client/types.gen'

/**
 * Every team of the event for its admins: the list on the left, the chosen
 * team and its roster on the right. Below `lg` there is no room for both, so
 * the list fills the screen and choosing a team swaps it for the team, with a
 * way back — the choice lives in `?team=` so the phone's back button works.
 */
const props = defineProps<{
  eventId: string
  teams: EventTeamRead[]
  eventMembers: EventMemberRead[]
  isEventAdmin: boolean
  currentUserId?: string | null
  /** The team shown on the right (`?team=`), if one is chosen. */
  selectedId: string | null
  busyTeamId?: string | null
  version?: number
}>()

const emit = defineEmits<{
  select: [id: string | null]
  edit: [team: EventTeamRead]
  delete: [team: EventTeamRead]
  updated: []
}>()

const { t } = useI18n()

const selected = computed(() => props.teams.find((team) => team.id === props.selectedId) ?? null)
/** On a wide screen something is always shown on the right. */
const shown = computed(() => selected.value ?? props.teams[0] ?? null)
</script>

<template>
  <div class="grid gap-4 lg:grid-cols-[17rem_minmax(0,1fr)] lg:items-start">
    <nav
      :aria-label="t('teams.manage.teamsLabel')"
      class="space-y-2"
      :class="selected ? 'max-lg:hidden' : ''"
      data-testid="teams-manage-list"
    >
      <button
        v-for="team in teams"
        :key="team.id"
        type="button"
        class="flex w-full items-center gap-3 rounded-xl border bg-card px-3.5 py-3 text-left transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        :class="shown?.id === team.id ? 'lg:border-primary lg:ring-1 lg:ring-primary' : ''"
        :aria-current="shown?.id === team.id ? 'true' : undefined"
        :data-testid="`team-row-${team.id}`"
        @click="emit('select', team.id)"
      >
        <div class="min-w-0 flex-1 space-y-0.5">
          <div class="flex items-center gap-1.5">
            <Lock
              v-if="team.requires_approval"
              class="size-3.5 shrink-0 text-muted-foreground"
              :aria-label="t('teams.summary.approval')"
            />
            <span class="truncate font-semibold">{{ team.name }}</span>
            <span v-if="!team.requires_approval" class="shrink-0 text-xs text-muted-foreground">
              · {{ t('teams.manage.open') }}
            </span>
          </div>
          <p class="truncate text-xs text-muted-foreground">
            {{
              t('teams.summary.members', { count: team.member_count ?? 0 }, team.member_count ?? 0)
            }}
            ·
            {{ t('teams.summary.tasks', { count: team.task_count ?? 0 }, team.task_count ?? 0) }}
          </p>
        </div>
        <Badge
          v-if="team.pending_count"
          variant="warning"
          class="rounded-full"
          :data-testid="`team-pending-count-${team.id}`"
        >
          {{ t('teams.manage.waiting', { count: team.pending_count }, team.pending_count) }}
        </Badge>
        <TriangleAlert
          v-else-if="team.my_needs_recheck"
          class="size-4 shrink-0 text-amber-600 dark:text-amber-400"
          :aria-label="t('teams.roster.needsRecheck')"
        />
        <ChevronRight class="size-4 shrink-0 text-muted-foreground lg:hidden" aria-hidden="true" />
      </button>
    </nav>

    <div v-if="shown" class="space-y-2" :class="selected ? '' : 'max-lg:hidden'">
      <Button
        variant="ghost"
        size="sm"
        class="-ml-2 lg:hidden"
        data-testid="btn-teams-back"
        @click="emit('select', null)"
      >
        <ChevronLeft class="mr-1 size-4" />
        {{ t('teams.page.back') }}
      </Button>
      <TeamManagePanel
        :key="shown.id"
        :event-id="eventId"
        :team="shown"
        :event-members="eventMembers"
        :is-event-admin="isEventAdmin"
        :current-user-id="currentUserId"
        :busy="busyTeamId === shown.id"
        :version="version"
        @edit="emit('edit', $event)"
        @delete="emit('delete', $event)"
        @updated="emit('updated')"
      />
    </div>
  </div>
</template>
