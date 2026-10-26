<script setup lang="ts">
import { Lock, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import TeamJoinButton from '@/components/tasks/TeamJoinButton.vue'
import HintTooltip from '@/components/utils/HintTooltip.vue'

import type { TaskRead } from '@/client/types.gen'
import { formatDate } from '@/lib/format'
import { statusVariant } from '@/lib/status'

defineProps<{
  tasks: TaskRead[]
}>()

const emit = defineEmits<{
  navigate: [task: TaskRead]
  delete: [task: TaskRead]
  teamJoined: []
}>()

const { t } = useI18n()
const authStore = useAuthStore()
</script>

<template>
  <div v-if="tasks.length === 0" class="py-12 text-center text-muted-foreground">
    {{ t('duties.tasks.empty') }}
  </div>

  <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
    <Card
      v-for="task in tasks"
      :key="task.id"
      class="cursor-pointer transition-colors hover:bg-muted/50"
      @click="emit('navigate', task)"
    >
      <CardHeader class="pb-3">
        <div class="flex items-start justify-between">
          <CardTitle class="text-lg line-clamp-1 break-words">{{ task.name }}</CardTitle>
          <Badge v-if="authStore.isManager" :variant="statusVariant(task.status)">
            {{ t(`duties.tasks.statuses.${task.status ?? 'draft'}`) }}
          </Badge>
        </div>
        <CardDescription v-if="task.description" class="line-clamp-2 break-words">
          {{ task.description }}
        </CardDescription>
        <!-- Reserved for a team the viewer is not in -->
        <div v-if="task.locked_by_team && task.team_id && task.team_name" class="space-y-1 pt-1">
          <Badge variant="secondary" class="max-w-full" :data-testid="`task-team-badge-${task.id}`">
            <Lock aria-hidden="true" />
            <span class="truncate">{{ t('teamLocks.badge.only', { name: task.team_name }) }}</span>
          </Badge>
          <div>
            <TeamJoinButton
              :event-id="task.event_id"
              :team-id="task.team_id"
              :team-name="task.team_name"
              :requires-approval="task.team_requires_approval ?? true"
              :my-status="task.my_team_status"
              variant="link"
              size="sm"
              class="h-auto px-0 text-xs font-semibold whitespace-normal"
              @joined="emit('teamJoined')"
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div class="flex items-center justify-between text-sm text-muted-foreground">
          <span>{{ formatDate(task.start_date) }} – {{ formatDate(task.end_date) }}</span>
          <HintTooltip v-if="authStore.isManager" :label="t('duties.tasks.delete')">
            <Button
              variant="ghost"
              size="icon"
              class="h-8 w-8"
              :aria-label="t('duties.tasks.delete')"
              @click.stop="emit('delete', task)"
            >
              <Trash2 class="h-4 w-4 text-destructive" />
            </Button>
          </HintTooltip>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
