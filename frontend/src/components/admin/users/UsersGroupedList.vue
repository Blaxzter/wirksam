<script setup lang="ts">
import { computed } from 'vue'

import { Ban, UserCheck } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { avatarUrlFor } from '@/composables/useAvatarUrl'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent } from '@/components/ui/card'

import UserRowActions from './UserRowActions.vue'

import type { UserRead } from '@/client/types.gen'
import { userStatus, userStatusBadgeVariant } from '@/lib/user-status'

const props = defineProps<{
  users: UserRead[]
  updatingId: string | null
}>()

const emit = defineEmits<{
  approve: [user: UserRead]
  reject: [user: UserRead]
  toggleActive: [user: UserRead]
  suspendReason: [user: UserRead]
  toggleAdmin: [user: UserRead]
  toggleTaskManager: [user: UserRead]
  delete: [user: UserRead]
}>()

const { t } = useI18n()

const pendingUsers = computed(() => props.users.filter((u) => userStatus(u) === 'pending'))
const activeUsers = computed(() => props.users.filter((u) => userStatus(u) === 'active'))
/** Rejected registrations and suspended accounts: both turned away, both may have a reason. */
const rejectedUsers = computed(() =>
  props.users.filter((u) => ['rejected', 'suspended'].includes(userStatus(u))),
)

const getInitials = (user: UserRead) => {
  if (user.name) {
    return user.name
      .split(' ')
      .map((w) => w.replace(/[^a-zA-Z]/g, '')[0])
      .filter(Boolean)
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }
  return user.email?.[0]?.toUpperCase() ?? '?'
}

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
</script>

<template>
  <div data-testid="users-grouped-list" class="space-y-6">
    <section v-if="pendingUsers.length > 0" class="space-y-3">
      <Card v-for="user in pendingUsers" :key="user.id" class="border-amber-500/40">
        <CardContent class="space-y-4 p-4">
          <div class="flex items-start gap-3">
            <Avatar class="h-10 w-10 rounded-sm">
              <AvatarImage
              v-if="avatarUrlFor(user)"
              :src="avatarUrlFor(user)!"
              :alt="user.name ?? ''"
            />
              <AvatarFallback class="rounded-sm text-sm">{{ getInitials(user) }}</AvatarFallback>
            </Avatar>
            <div class="min-w-0 flex-1 space-y-1">
              <p class="truncate font-medium">{{ user.name ?? '—' }}</p>
              <p class="truncate text-sm text-muted-foreground">{{ user.email ?? '—' }}</p>
              <p class="text-xs text-muted-foreground">
                {{ t('admin.users.columns.memberSince') }}: {{ formatDate(user.created_at) }}
              </p>
            </div>
          </div>
          <div class="flex gap-2">
            <Button
              class="flex-1"
              :disabled="updatingId === user.id"
              @click="emit('approve', user)"
            >
              <UserCheck class="mr-2 h-4 w-4" />
              {{ t('admin.users.approve') }}
            </Button>
            <Button
              variant="outline"
              class="flex-1"
              :disabled="updatingId === user.id"
              @click="emit('reject', user)"
            >
              <Ban class="mr-2 h-4 w-4 text-destructive" />
              {{ t('admin.users.reject') }}
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>

    <section v-if="activeUsers.length > 0" class="space-y-2">
      <div class="divide-y rounded-lg border">
        <div
          v-for="user in activeUsers"
          :key="user.id"
          class="flex items-center gap-3 p-3"
        >
          <Avatar class="h-9 w-9 shrink-0 rounded-sm">
            <AvatarImage
              v-if="avatarUrlFor(user)"
              :src="avatarUrlFor(user)!"
              :alt="user.name ?? ''"
            />
            <AvatarFallback class="rounded-sm text-xs">{{ getInitials(user) }}</AvatarFallback>
          </Avatar>
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-medium">{{ user.name ?? '—' }}</p>
            <p class="truncate text-xs text-muted-foreground">{{ user.email ?? '—' }}</p>
            <div v-if="user.roles.length > 0" class="mt-1 flex flex-wrap gap-1">
              <Badge v-for="role in user.roles" :key="role" variant="secondary" class="text-[10px]">
                {{ role }}
              </Badge>
            </div>
          </div>
          <UserRowActions
            :user="user"
            :disabled="updatingId === user.id"
            @approve="emit('approve', $event)"
            @reject="emit('reject', $event)"
            @toggle-active="emit('toggleActive', $event)"
            @suspend-reason="emit('suspendReason', $event)"
            @toggle-admin="emit('toggleAdmin', $event)"
            @toggle-task-manager="emit('toggleTaskManager', $event)"
            @delete="emit('delete', $event)"
          />
        </div>
      </div>
    </section>

    <section v-if="rejectedUsers.length > 0" class="space-y-2">
      <div class="divide-y rounded-lg border">
        <div
          v-for="user in rejectedUsers"
          :key="user.id"
          class="flex items-start gap-3 p-3"
        >
          <Avatar class="h-9 w-9 shrink-0 rounded-sm opacity-60">
            <AvatarImage
              v-if="avatarUrlFor(user)"
              :src="avatarUrlFor(user)!"
              :alt="user.name ?? ''"
            />
            <AvatarFallback class="rounded-sm text-xs">{{ getInitials(user) }}</AvatarFallback>
          </Avatar>
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-medium">{{ user.name ?? '—' }}</p>
            <p class="truncate text-xs text-muted-foreground">{{ user.email ?? '—' }}</p>
            <Badge
              :variant="userStatusBadgeVariant(userStatus(user))"
              class="mt-1 text-[10px]"
            >
              {{ t(`admin.users.${userStatus(user)}`) }}
            </Badge>
            <p
              v-if="user.rejection_reason"
              class="mt-1 text-xs italic text-muted-foreground"
            >
              "{{ user.rejection_reason }}"
            </p>
          </div>
          <UserRowActions
            :user="user"
            :disabled="updatingId === user.id"
            @approve="emit('approve', $event)"
            @reject="emit('reject', $event)"
            @toggle-active="emit('toggleActive', $event)"
            @suspend-reason="emit('suspendReason', $event)"
            @toggle-admin="emit('toggleAdmin', $event)"
            @toggle-task-manager="emit('toggleTaskManager', $event)"
            @delete="emit('delete', $event)"
          />
        </div>
      </div>
    </section>

    <div
      v-if="users.length === 0"
      class="rounded-lg border py-12 text-center text-sm text-muted-foreground"
    >
      {{ t('admin.users.empty') }}
    </div>
  </div>
</template>
