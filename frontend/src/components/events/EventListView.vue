<script setup lang="ts">
import { Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import type { EventRead } from '@/client/types.gen'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { formatDate } from '@/lib/format'
import { statusVariant } from '@/lib/status'
import { useAuthStore } from '@/stores/auth'

defineProps<{
  events: EventRead[]
}>()

const emit = defineEmits<{
  navigate: [event: EventRead]
  delete: [event: EventRead]
}>()

const { t } = useI18n()
const authStore = useAuthStore()
</script>

<template>
  <div v-if="events.length === 0" class="py-12 text-center text-muted-foreground">
    {{ t('duties.events.empty') }}
  </div>

  <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
    <Card
      v-for="event in events"
      :key="event.id"
      class="cursor-pointer transition-colors hover:bg-muted/50"
      @click="emit('navigate', event)"
    >
      <CardHeader class="pb-3">
        <div class="flex items-start justify-between">
          <CardTitle class="text-lg line-clamp-1 break-words">{{ event.name }}</CardTitle>
          <Badge :variant="statusVariant(event.status)">
            {{ t(`duties.events.statuses.${event.status ?? 'draft'}`) }}
          </Badge>
        </div>
        <CardDescription v-if="event.description" class="line-clamp-2 break-words">
          {{ event.description }}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div class="flex items-center justify-between text-sm text-muted-foreground">
          <span>{{ formatDate(event.start_date) }} – {{ formatDate(event.end_date) }}</span>
          <Button
            v-if="authStore.isAdmin"
            variant="ghost"
            size="icon"
            class="h-8 w-8"
            @click.stop="emit('delete', event)"
          >
            <Trash2 class="h-4 w-4 text-destructive" />
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
