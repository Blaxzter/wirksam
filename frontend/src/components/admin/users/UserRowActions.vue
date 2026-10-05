<script setup lang="ts">
import {
  Ban,
  EllipsisVertical,
  MessageSquareWarning,
  Shield,
  ShieldCheck,
  ShieldOff,
  Trash2,
  UserCheck,
  UserX,
} from '@lucide/vue'
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import Button from '@/components/ui/button/Button.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

import type { UserRead } from '@/client/types.gen'
import { userStatus } from '@/lib/user-status'

const props = defineProps<{
  user: UserRead
  disabled: boolean
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

/** Name the row's action menu after its user, so the menus aren't 20 identical "button"s. */
const displayName = computed(() => props.user.name || props.user.email || '')

const status = computed(() => userStatus(props.user))
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button
        variant="ghost"
        size="icon"
        class="h-8 w-8"
        :disabled="disabled"
        :aria-label="t('admin.users.userActions', { name: displayName })"
      >
        <EllipsisVertical class="h-4 w-4" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <!-- The registration queue: decide, or change your mind about a rejection. -->
      <template v-if="status === 'pending' || status === 'rejected'">
        <DropdownMenuItem data-testid="action-approve" @click="emit('approve', props.user)">
          <UserCheck class="mr-2 h-4 w-4" />
          {{ t('admin.users.approve') }}
        </DropdownMenuItem>
        <DropdownMenuItem
          v-if="status === 'pending'"
          data-testid="action-reject"
          @click="emit('reject', props.user)"
        >
          <Ban class="mr-2 h-4 w-4 text-destructive" />
          {{ t('admin.users.reject') }}
        </DropdownMenuItem>
      </template>
      <!-- Moderation of an account that was let in. -->
      <template v-else>
        <DropdownMenuItem @click="emit('toggleActive', props.user)">
          <UserX v-if="props.user.is_active" class="mr-2 h-4 w-4 text-destructive" />
          <UserCheck v-else class="mr-2 h-4 w-4" />
          {{ props.user.is_active ? t('admin.users.deactivate') : t('admin.users.activate') }}
        </DropdownMenuItem>
        <DropdownMenuItem
          v-if="!props.user.is_active"
          data-testid="action-suspend-reason"
          @click="emit('suspendReason', props.user)"
        >
          <MessageSquareWarning class="mr-2 h-4 w-4 text-destructive" />
          {{ t('admin.users.suspendReason') }}
        </DropdownMenuItem>
      </template>
      <DropdownMenuSeparator />
      <DropdownMenuItem @click="emit('toggleAdmin', props.user)">
        <ShieldOff
          v-if="props.user.roles.includes('admin')"
          class="mr-2 h-4 w-4 text-destructive"
        />
        <Shield v-else class="mr-2 h-4 w-4" />
        {{
          props.user.roles.includes('admin')
            ? t('admin.users.removeAdmin')
            : t('admin.users.makeAdmin')
        }}
      </DropdownMenuItem>
      <DropdownMenuItem @click="emit('toggleTaskManager', props.user)">
        <ShieldOff
          v-if="props.user.roles.includes('task_manager')"
          class="mr-2 h-4 w-4 text-amber-500"
        />
        <ShieldCheck v-else class="mr-2 h-4 w-4 text-amber-500" />
        {{
          props.user.roles.includes('task_manager')
            ? t('admin.users.removeTaskManager')
            : t('admin.users.makeTaskManager')
        }}
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        class="text-destructive focus:bg-destructive/10 focus:text-destructive dark:focus:bg-destructive/30"
        @click="emit('delete', props.user)"
      >
        <Trash2 class="mr-2 h-4 w-4 text-destructive" />
        {{ t('admin.users.delete') }}
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
