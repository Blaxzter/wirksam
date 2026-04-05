<script setup lang="ts">
import { Mail, MessageCircle, Smartphone } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import type { NotificationType } from '@/stores/notification'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'

const props = defineProps<{
  groupedTypes: Record<string, NotificationType[]>
  preferences: Map<string, { email: boolean; push: boolean; telegram: boolean }>
}>()

const emit = defineEmits<{
  'set-preference': [typeId: string, channel: 'email' | 'push' | 'telegram', value: boolean]
}>()

const { t } = useI18n()

const categoryLabels: Record<string, string> = {
  booking: 'notifications.categories.booking',
  slot: 'notifications.categories.slot',
  event: 'notifications.categories.event',
  event_group: 'notifications.categories.eventGroup',
  availability: 'notifications.categories.availability',
  admin: 'notifications.categories.admin',
  user: 'notifications.categories.user',
}

function getCategoryLabel(category: string): string {
  const key = categoryLabels[category]
  return key ? t(key) : category
}

function getPreference(typeId: string) {
  return props.preferences.get(typeId) || { email: true, push: true, telegram: false }
}
</script>

<template>
  <div v-bind="$attrs">
    <Card v-for="(categoryTypes, category) in groupedTypes" :key="category">
      <CardHeader>
        <CardTitle>{{ getCategoryLabel(category as string) }}</CardTitle>
      </CardHeader>
      <CardContent class="space-y-0">
        <!-- Column headers -->
        <div
          class="text-muted-foreground mb-3 flex items-center gap-2 sm:gap-4 text-xs font-medium"
        >
          <div class="min-w-0 flex-1" />
          <div class="flex w-10 sm:w-24 items-center justify-center gap-1">
            <Mail class="h-3.5 w-3.5 shrink-0" />
            <span class="hidden sm:inline">{{ t('notifications.channels.email') }}</span>
          </div>
          <div class="flex w-10 sm:w-24 items-center justify-center gap-1">
            <Smartphone class="h-3.5 w-3.5 shrink-0" />
            <span class="hidden sm:inline">{{ t('notifications.channels.push') }}</span>
          </div>
          <div class="flex w-10 sm:w-24 items-center justify-center gap-1">
            <MessageCircle class="h-3.5 w-3.5 shrink-0" />
            <span class="hidden sm:inline">{{ t('notifications.channels.telegram') }}</span>
          </div>
        </div>

        <Separator />

        <div
          v-for="type in categoryTypes as NotificationType[]"
          :key="type.id"
          class="flex items-center gap-2 sm:gap-4 py-3"
        >
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium">
              {{ t(`notifications.types.${type.code}.name`, type.name) }}
            </p>
            <p v-if="type.description" class="text-muted-foreground text-xs">
              {{ t(`notifications.types.${type.code}.description`, type.description) }}
            </p>
            <Badge v-if="type.is_admin_only" variant="secondary" class="mt-1 text-[10px]">
              {{ t('notifications.adminOnly') }}
            </Badge>
          </div>
          <div class="flex w-10 sm:w-24 justify-center">
            <Switch
              :model-value="getPreference(type.id).email"
              @update:model-value="(v: boolean) => emit('set-preference', type.id, 'email', v)"
            />
          </div>
          <div class="flex w-10 sm:w-24 justify-center">
            <Switch
              :model-value="getPreference(type.id).push"
              @update:model-value="(v: boolean) => emit('set-preference', type.id, 'push', v)"
            />
          </div>
          <div class="flex w-10 sm:w-24 justify-center">
            <Switch
              :model-value="getPreference(type.id).telegram"
              @update:model-value="(v: boolean) => emit('set-preference', type.id, 'telegram', v)"
            />
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
