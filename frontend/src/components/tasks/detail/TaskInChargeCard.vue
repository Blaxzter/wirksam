<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { ChevronRight, Info, LogOut, Mail, UserCheck } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { avatarUrlFor } from '@/composables/useAvatarUrl'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import Button from '@/components/ui/button/Button.vue'

import type { TaskManagerBrief, TaskManagerInvitationRead, TaskRead } from '@/client/types.gen'
import { initials } from '@/lib/format'

/**
 * "In charge" on the task page: who runs the task, by name.
 *
 * Organisers also see the invitations still waiting for an answer, and a
 * "Manage" button for the dialog where they change all of it. A person in
 * charge finds the way to step down here, together with why they can't change
 * the shifts when the event keeps those with the organisers.
 *
 * Invitations are the organisers' to see (the server answers 403 to anyone
 * else), so they are only fetched for them. The page calls
 * `reloadInvitations` after the dialog changed something.
 */
const props = defineProps<{
  task: TaskRead
  /** The viewer is an organiser of the task's event. */
  canAdmin?: boolean
  /** The viewer's own user id, to mark their row. */
  myId?: string | null
  /** The viewer is in charge without being an organiser: offer stepping down. */
  inCharge?: boolean
  /** They may change the details but not the shifts (voucher shifts kept by the organisers). */
  shiftsLocked?: boolean
  /** Phone layout. */
  compact?: boolean
}>()

const emit = defineEmits<{
  manage: []
  stepDown: []
}>()

const { t } = useI18n()
const { get } = useAuthenticatedClient()

const invitations = ref<TaskManagerInvitationRead[]>([])

async function reloadInvitations() {
  if (!props.canAdmin) {
    invitations.value = []
    return
  }
  const taskId = props.task.id
  try {
    const res = await get<{ data: TaskManagerInvitationRead[] }>({
      url: `/tasks/${taskId}/managers/invitations`,
    })
    if (props.task.id === taskId) invitations.value = res.data
  } catch {
    // Not worth a toast: the dialog lists them again, with its own errors.
    invitations.value = []
  }
}

watch(() => [props.task.id, props.canAdmin], reloadInvitations, { immediate: true })

defineExpose({ reloadInvitations })

const managers = computed(() => props.task.managers ?? [])
const isEmpty = computed(() => managers.value.length === 0 && invitations.value.length === 0)

const nameOf = (m: TaskManagerBrief) => m.name || '?'
const isMe = (m: TaskManagerBrief) => !!props.myId && m.user_id === props.myId

function invitationLine(invitation: TaskManagerInvitationRead): string {
  if (invitation.is_member_now) return t('duties.tasks.managers.pendingIsMember')
  if (invitation.expired) return t('duties.tasks.managers.invitationExpired')
  return t('duties.tasks.managers.waiting')
}

const expired = (invitation: TaskManagerInvitationRead) =>
  invitation.expired && !invitation.is_member_now
</script>

<template>
  <section
    aria-labelledby="task-in-charge-title"
    data-testid="task-in-charge-card"
    class="flex min-w-0 flex-col border bg-card text-card-foreground"
    :class="compact ? 'gap-3 rounded-[18px] p-4' : 'gap-3.5 rounded-[20px] px-[22px] py-5'"
  >
    <div class="flex min-h-10 items-center justify-between gap-3">
      <h2 id="task-in-charge-title" class="flex items-center gap-2 text-base font-bold">
        <UserCheck class="size-[18px] shrink-0 text-primary" aria-hidden="true" />
        {{ t('duties.tasks.managers.label') }}
      </h2>
      <template v-if="canAdmin">
        <button
          v-if="compact"
          type="button"
          data-testid="btn-task-managers-card"
          class="-my-2 -mr-1.5 flex min-h-11 items-center gap-0.5 rounded-lg px-1.5 text-sm font-bold text-primary outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50"
          @click="emit('manage')"
        >
          {{ t('duties.tasks.managers.manageShort') }}
          <ChevronRight class="size-4" aria-hidden="true" />
        </button>
        <Button
          v-else
          variant="outline"
          data-testid="btn-task-managers-card"
          class="h-10 rounded-[10px] bg-background px-3.5 font-semibold shadow-none"
          @click="emit('manage')"
        >
          {{ t('duties.tasks.managers.manageShort') }}
        </Button>
      </template>
    </div>

    <p v-if="isEmpty" class="text-sm text-muted-foreground" data-testid="task-in-charge-empty">
      {{ t('duties.tasks.managers.empty') }}
    </p>

    <ul v-else class="flex flex-col gap-2.5" data-testid="task-managers">
      <li v-for="m in managers" :key="m.user_id" class="flex min-w-0 items-center gap-3">
        <Avatar class="shrink-0" :class="compact ? 'size-9' : 'size-[38px]'">
          <AvatarImage
            v-if="avatarUrlFor({ id: m.user_id, avatar_etag: m.avatar_etag })"
            :src="avatarUrlFor({ id: m.user_id, avatar_etag: m.avatar_etag })!"
            alt=""
          />
          <AvatarFallback
            class="text-[13px] font-bold"
            :class="isMe(m) ? 'bg-primary/15 text-primary' : 'bg-accent text-accent-foreground'"
          >
            {{ initials(nameOf(m)) }}
          </AvatarFallback>
        </Avatar>
        <span class="min-w-0 flex-1 truncate text-[15px] font-semibold">{{ nameOf(m) }}</span>
        <span
          v-if="isMe(m)"
          class="shrink-0 rounded-full bg-primary/12 px-2.5 py-0.5 text-xs font-bold text-primary"
          data-testid="task-you-are-in-charge"
        >
          {{ t('duties.tasks.managers.you') }}
        </span>
      </li>

      <li
        v-for="invitation in invitations"
        :key="invitation.id"
        class="flex min-w-0 items-center gap-3"
        :data-testid="`task-in-charge-invitation-${invitation.email}`"
      >
        <span
          class="flex shrink-0 items-center justify-center rounded-full border-[1.5px] border-dashed border-muted-foreground/50 text-muted-foreground"
          :class="compact ? 'size-9' : 'size-[38px]'"
          aria-hidden="true"
        >
          <Mail class="size-4" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block truncate text-[15px] font-semibold">{{ invitation.email }}</span>
          <span v-if="!compact" class="block text-[13px] text-muted-foreground">
            {{ invitationLine(invitation) }}
          </span>
        </span>
        <span
          class="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-bold"
          :class="
            expired(invitation) ? 'bg-muted text-muted-foreground' : 'bg-warning/12 text-warning'
          "
        >
          {{
            expired(invitation)
              ? t('duties.tasks.managers.pendingExpired')
              : t('duties.tasks.managers.pendingTitle')
          }}
        </span>
      </li>
    </ul>

    <p
      v-if="canAdmin && !compact && !isEmpty"
      class="mt-auto border-t pt-3 text-[13px] text-muted-foreground"
    >
      {{ t('duties.tasks.managers.cardHint') }}
    </p>

    <div
      v-if="inCharge"
      class="flex flex-col border-t"
      :class="compact ? 'gap-1.5 pt-2.5' : 'mt-auto gap-2.5 pt-3'"
    >
      <p
        v-if="shiftsLocked"
        class="flex gap-2 text-[13px] text-muted-foreground"
        data-testid="task-voucher-shifts-locked"
      >
        <Info class="mt-px size-4 shrink-0" aria-hidden="true" />
        <span>{{
          compact
            ? t('duties.tasks.managers.voucherShiftsLockedShort')
            : t('duties.tasks.managers.voucherShiftsLocked')
        }}</span>
      </p>
      <button
        type="button"
        data-testid="btn-task-step-down"
        class="-ml-2 flex items-center gap-1.5 self-start rounded-lg px-2 text-sm font-semibold text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
        :class="compact ? 'min-h-11' : 'min-h-10'"
        @click="emit('stepDown')"
      >
        <LogOut class="size-4" aria-hidden="true" />
        {{ t('duties.tasks.managers.stepDown') }}
      </button>
    </div>
  </section>
</template>
