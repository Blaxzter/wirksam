<script setup lang="ts">
import { UserIcon } from 'lucide-vue-next'

import { useAuthStore } from '@/stores/auth'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

withDefaults(
  defineProps<{
    direction?: 'horizontal' | 'vertical'
  }>(),
  {
    direction: 'horizontal',
  },
)

defineEmits<{
  navigate: []
}>()

const authStore = useAuthStore()
</script>

<template>
  <div
    :class="[
      'cursor-pointer hover:bg-muted rounded',
      direction === 'horizontal'
        ? 'flex items-center space-x-3 p-1'
        : 'flex flex-col items-center gap-2 p-3',
    ]"
    @click="$emit('navigate')"
  >
    <Avatar class="h-8 w-8">
      <AvatarImage
        :src="authStore.user?.picture || ''"
        :alt="authStore.user?.name || authStore.user?.email || 'User'"
      />
      <AvatarFallback>
        <UserIcon class="h-4 w-4" />
      </AvatarFallback>
    </Avatar>
    <div :class="direction === 'vertical' ? 'flex flex-col items-center' : 'flex flex-col'">
      <span class="text-sm font-medium">{{
        authStore.user?.name || authStore.user?.email
      }}</span>
      <span class="text-xs text-muted-foreground">
        {{ $t('preauth.layout.navigation.goToDashboard') }}
      </span>
    </div>
  </div>
</template>
