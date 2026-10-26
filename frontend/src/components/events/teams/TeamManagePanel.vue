<script setup lang="ts">
import { Lock, LockOpen, Pencil, Phone, ShieldCheck, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'
import Button from '@/components/ui/button/Button.vue'

import TeamRoster from '@/components/events/teams/TeamRoster.vue'
import { joinNames } from '@/components/events/teams/teamHelpers'

import type { EventMemberRead, EventTeamRead } from '@/client/types.gen'

/** One team as an event admin sees it: what it is, then its roster. */
defineProps<{
  eventId: string
  team: EventTeamRead
  eventMembers: EventMemberRead[]
  isEventAdmin: boolean
  currentUserId?: string | null
  busy?: boolean
  version?: number
}>()

const emit = defineEmits<{
  edit: [team: EventTeamRead]
  delete: [team: EventTeamRead]
  updated: []
}>()

const { t, locale } = useI18n()
</script>

<template>
  <section
    :aria-labelledby="`team-panel-${team.id}`"
    class="space-y-4 rounded-xl border bg-card p-4"
    :data-testid="`team-panel-${team.id}`"
  >
    <div class="flex flex-wrap items-center gap-2">
      <h2 :id="`team-panel-${team.id}`" class="text-lg font-semibold">{{ team.name }}</h2>
      <Badge variant="outline" class="rounded-full">
        <component :is="team.requires_approval ? Lock : LockOpen" />
        {{ team.requires_approval ? t('teams.summary.approval') : t('teams.summary.open') }}
      </Badge>
      <div v-if="isEventAdmin" class="ml-auto flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          :aria-label="t('teams.manage.editNamed', { name: team.name })"
          :data-testid="`btn-edit-team-${team.id}`"
          @click="emit('edit', team)"
        >
          <Pencil class="size-3.5 sm:mr-1.5" />
          <span class="max-sm:sr-only">{{ t('teams.manage.edit') }}</span>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          class="size-8 text-muted-foreground hover:text-destructive"
          :disabled="busy"
          :aria-label="t('teams.manage.deleteNamed', { name: team.name })"
          :data-testid="`btn-delete-team-${team.id}`"
          @click="emit('delete', team)"
        >
          <Trash2 class="size-4" />
        </Button>
      </div>
    </div>

    <div
      v-if="team.description || team.contact || team.tasks?.length || team.requirements?.length"
      class="space-y-1.5 text-sm"
    >
      <p v-if="team.description" class="whitespace-pre-line">{{ team.description }}</p>
      <p v-if="team.tasks?.length" class="text-muted-foreground">
        {{
          t('teams.summary.unlocks', {
            tasks: joinNames(
              team.tasks.map((task) => task.name),
              locale,
            ),
          })
        }}
      </p>
      <p v-else class="text-muted-foreground">{{ t('teams.manage.noTasks') }}</p>
      <p v-if="team.requirements?.length" class="flex items-start gap-1.5 text-muted-foreground">
        <ShieldCheck class="mt-0.5 size-4 shrink-0" />
        {{
          t('teams.summary.needs', {
            list: joinNames(
              team.requirements.map((r) => r.label),
              locale,
            ),
          })
        }}
      </p>
      <p v-if="team.contact" class="flex items-center gap-1.5 text-muted-foreground">
        <Phone class="size-3.5 shrink-0" />
        {{ team.contact }}
      </p>
    </div>

    <TeamRoster
      :event-id="eventId"
      :team="team"
      :event-members="eventMembers"
      :is-event-admin="isEventAdmin"
      :current-user-id="currentUserId"
      :version="version"
      @updated="emit('updated')"
    />
  </section>
</template>
