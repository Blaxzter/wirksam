<script setup lang="ts">
import { Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
