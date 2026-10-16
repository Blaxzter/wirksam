<script setup lang="ts">
import { computed, ref } from 'vue'

import { Clock, Crown, LogOut, ShieldCheck, UserMinus, Users } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { avatarUrlFor } from '@/composables/useAvatarUrl'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { NativeSelect } from '@/components/ui/native-select'

import type { EventMemberRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { type AssignableEventRole, type EventRole, roleLabelKey } from '@/lib/event-roles'
import { formatHours } from '@/lib/format'

const props = defineProps<{
  eventId: string
  members: EventMemberRead[]
  /** True when the viewer is an owner or admin of this event. */
  canEdit?: boolean
  /** True when the viewer owns the event — gates transfer and stricter actions. */
  isOwner?: boolean
  /** Worked minutes per user id. Admins only; omitted, no badge is shown. */
  hoursByUser?: Record<string, number>
}>()

const emit = defineEmits<{
  updated: []
  left: []
}>()

const { t } = useI18n()
const { patch, delete: del, post } = useAuthenticatedClient()
const authStore = useAuthStore()

const busyUserId = ref<string | null>(null)
const transferTargetId = ref<string>('')
const transferring = ref(false)

const myUserId = computed(() => authStore.profile?.id ?? null)

/** Members eligible to take over the event — anyone but the current owner. */
const transferCandidates = computed(() => props.members.filter((m) => m.role !== 'owner'))

function initials(member: EventMemberRead): string {
  return (member.name ?? member.email ?? '?').slice(0, 2).toUpperCase()
}

function avatarSrc(member: EventMemberRead): string | undefined {
  return avatarUrlFor({ id: member.user_id, avatar_etag: member.avatar_etag }) ?? undefined
}

/**
 * Read the new role off the native change event.
 *
 * NativeSelect's `update:modelValue` emit is typed without a payload, so the
 * underlying `<select>` event is what actually carries the value.
 */
function onRoleSelect(member: EventMemberRead, event: Event) {
  const value = (event.target as HTMLSelectElement).value as AssignableEventRole
  void changeRole(member, value)
}

async function changeRole(member: EventMemberRead, role: AssignableEventRole) {
  if (member.role === role) return
  busyUserId.value = member.user_id
  try {
    await patch({
      url: `/events/${props.eventId}/members/${member.user_id}`,
      body: { role },
    })
    emit('updated')
    toast.success(t('duties.events.members.roleChanged'))
  } catch (error) {
    toastApiError(error)
  } finally {
    busyUserId.value = null
  }
}

async function removeMember(member: EventMemberRead) {
  busyUserId.value = member.user_id
  try {
    await del({ url: `/events/${props.eventId}/members/${member.user_id}` })
    const wasMe = member.user_id === myUserId.value
    toast.success(wasMe ? t('duties.events.members.left') : t('duties.events.members.removed'))
    if (wasMe) emit('left')
    else emit('updated')
  } catch (error) {
    toastApiError(error)
  } finally {
    busyUserId.value = null
  }
}

async function transferOwnership() {
  if (!transferTargetId.value) return
  transferring.value = true
  try {
    await post({
      url: `/events/${props.eventId}/transfer-ownership`,
      body: { new_owner_id: transferTargetId.value },
    })
    transferTargetId.value = ''
    emit('updated')
    toast.success(t('duties.events.members.ownershipTransferred'))
  } catch (error) {
    toastApiError(error)
  } finally {
    transferring.value = false
  }
}

function roleIcon(role: EventRole) {
  if (role === 'owner') return Crown
  if (role === 'admin') return ShieldCheck
  return Users
}
</script>

<template>
  <Card data-testid="section-event-members">
    <CardHeader>
      <div class="space-y-1">
        <CardTitle class="flex items-center gap-2">
          <Users class="h-5 w-5 shrink-0" />
          {{ t('duties.events.members.title') }}
        </CardTitle>
        <CardDescription>{{ t('duties.events.members.subtitle') }}</CardDescription>
      </div>
    </CardHeader>

    <CardContent class="space-y-4">
      <p v-if="members.length === 0" class="text-sm text-muted-foreground">
        {{ t('duties.events.members.empty') }}
      </p>

      <div v-else class="space-y-1.5">
        <div
          v-for="member in members"
          :key="member.user_id"
          class="flex flex-wrap items-center justify-between gap-3 rounded-md border px-3 py-2"
          data-testid="event-member-row"
          :data-role="member.role"
        >
          <div class="flex min-w-0 items-center gap-3">
            <Avatar class="size-7">
              <AvatarImage v-if="avatarSrc(member)" :src="avatarSrc(member)!" />
              <AvatarFallback class="text-xs">{{ initials(member) }}</AvatarFallback>
            </Avatar>
            <div class="min-w-0">
              <p class="truncate text-sm font-medium leading-none">
                {{ member.name ?? member.email }}
                <span v-if="member.user_id === myUserId" class="text-muted-foreground">
                  {{ t('duties.events.members.you') }}
                </span>
              </p>
              <p v-if="member.name" class="truncate text-xs text-muted-foreground">
                {{ member.email }}
              </p>
            </div>
          </div>

          <div class="flex shrink-0 items-center gap-2">
            <Badge
              v-if="hoursByUser && hoursByUser[member.user_id]"
              variant="outline"
              class="gap-1 tabular-nums"
              :title="t('duties.hours.memberBadge')"
              data-testid="member-hours-badge"
            >
              <Clock class="h-3 w-3" />
              {{ t('duties.hours.unit', { value: formatHours(hoursByUser[member.user_id]!) }) }}
            </Badge>

            <!-- The owner's role is fixed; it moves only through a transfer. -->
            <Badge v-if="member.role === 'owner'" variant="secondary" class="gap-1">
              <Crown class="h-3 w-3" />
              {{ t(roleLabelKey('owner')) }}
            </Badge>

            <NativeSelect
              v-else-if="canEdit"
              :model-value="member.role"
              class="h-8 w-32 text-xs"
              :disabled="busyUserId === member.user_id"
              :aria-label="
                t('duties.events.members.changeRoleFor', { name: member.name ?? member.email })
              "
              @change="onRoleSelect(member, $event)"
            >
              <option value="admin">{{ t(roleLabelKey('admin')) }}</option>
              <option value="member">{{ t(roleLabelKey('member')) }}</option>
            </NativeSelect>

            <Badge v-else variant="outline" class="gap-1">
              <component :is="roleIcon(member.role)" class="h-3 w-3" />
              {{ t(roleLabelKey(member.role)) }}
            </Badge>

            <Button
              v-if="member.user_id === myUserId && member.role !== 'owner'"
              variant="ghost"
              size="sm"
              class="text-muted-foreground hover:text-destructive"
              data-testid="btn-leave-event"
              :disabled="busyUserId === member.user_id"
              @click="removeMember(member)"
            >
              <LogOut class="mr-1.5 h-3.5 w-3.5" />
              {{ t('duties.events.members.leave') }}
            </Button>
            <Button
              v-else-if="canEdit && member.role !== 'owner'"
              variant="ghost"
              size="icon"
              class="size-7 text-muted-foreground hover:text-destructive"
              data-testid="btn-remove-member"
              :disabled="busyUserId === member.user_id"
              :aria-label="t('duties.events.members.remove', { name: member.name ?? member.email })"
              @click="removeMember(member)"
            >
              <UserMinus class="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>

      <!-- Handing the event on. Owner-only, and never leaves it ownerless. -->
      <div
        v-if="isOwner && transferCandidates.length > 0"
        class="space-y-2 rounded-md border border-dashed p-3"
        data-testid="transfer-ownership"
      >
        <p class="text-sm font-medium">{{ t('duties.events.members.transferTitle') }}</p>
        <p class="text-xs text-muted-foreground">
          {{ t('duties.events.members.transferHint') }}
        </p>
        <div class="flex flex-col gap-2 sm:flex-row">
          <NativeSelect v-model="transferTargetId" class="h-9 flex-1">
            <option value="">{{ t('duties.events.members.transferPlaceholder') }}</option>
            <option v-for="m in transferCandidates" :key="m.user_id" :value="m.user_id">
              {{ m.name ?? m.email }}
            </option>
          </NativeSelect>
          <Button
            variant="outline"
            data-testid="btn-transfer-ownership"
            :disabled="!transferTargetId || transferring"
            @click="transferOwnership"
          >
            <Crown class="mr-1.5 h-4 w-4" />
            {{ t('duties.events.members.transferAction') }}
          </Button>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
