<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  CircleAlert,
  CircleCheck,
  EllipsisVertical,
  Mail,
  RotateCw,
  Send,
  Undo2,
  UserMinus,
  UserPlus,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { avatarUrlFor } from '@/composables/useAvatarUrl'
import { useDialog } from '@/composables/useDialog'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import Button from '@/components/ui/button/Button.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

import EventMemberPicker from '@/components/events/EventMemberPicker.vue'

import type {
  EventMemberRead,
  TaskManagerBrief,
  TaskManagerInvitationRead,
  TaskManagerInviteResult,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { initials } from '@/lib/format'
import { parseServerDate } from '@/lib/server-time'

/**
 * Put event members in charge of a task, take them off it, or invite someone
 * by e-mail address. Organisers only; the server refuses everyone else. Every
 * change is saved at once, then `reload` fetches the task again, whose
 * `managers` come back in through the prop. The editor stays busy until that
 * reload is in, so the list never shows the old state after the message.
 *
 * Invitations that are still open sit in the same list below the people in
 * charge, marked "Invited", with what can be done about each right on the row
 * (withdraw, send again, invite again once expired, or add now when the
 * address has joined the event another way). What an invitation did is said
 * in a line above the list rather than a toast, as the design has it: it
 * names the address, and it can carry a warning about signing up.
 */
const props = defineProps<{
  taskId: string
  eventId: string
  /** For the line under the search field in the phone picker. */
  taskName?: string
  managers: TaskManagerBrief[]
  reload: () => Promise<unknown>
}>()

const { t, locale } = useI18n()
const { get, post, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const members = ref<EventMemberRead[]>([])
const invitations = ref<TaskManagerInvitationRead[]>([])
/** A user id or an invitation id while its change is on the way. */
const busyId = ref<string | null>(null)

/** The last invitation outcome, shown above the list until the next one. */
const status = ref<{ text: string; warning?: string } | null>(null)

const memberById = computed(() => new Map(members.value.map((m) => [m.user_id, m])))

/** A name for a row: the task's own, else the roster's e-mail. */
function nameOf(m: TaskManagerBrief): string {
  return m.name || memberById.value.get(m.user_id)?.email || '?'
}

/** People already in charge stay in the list, greyed out with the reason. */
const unavailable = computed(() =>
  Object.fromEntries(
    props.managers.map((m) => [m.user_id, t('duties.tasks.managers.alreadyInCharge')]),
  ),
)

const isEmpty = computed(() => props.managers.length === 0 && invitations.value.length === 0)

async function loadMembers() {
  try {
    const res = await get<{ data: EventMemberRead[] }>({ url: `/events/${props.eventId}/members` })
    members.value = res.data
  } catch (err) {
    toastApiError(err)
  }
}

async function loadInvitations() {
  try {
    const res = await get<{ data: TaskManagerInvitationRead[] }>({
      url: `/tasks/${props.taskId}/managers/invitations`,
    })
    invitations.value = res.data
  } catch (err) {
    toastApiError(err)
  }
}

watch(() => props.eventId, loadMembers, { immediate: true })
watch(() => props.taskId, loadInvitations, { immediate: true })

/**
 * Run one change, then bring the task and the open invitations up to date.
 * `null` when it was refused (the refusal is toasted), else what it returned.
 */
async function act<T>(id: string, run: () => Promise<T>): Promise<{ value: T } | null> {
  busyId.value = id
  try {
    const value = await run()
    await Promise.all([props.reload(), loadInvitations()])
    return { value }
  } catch (err) {
    toastApiError(err)
    return null
  } finally {
    busyId.value = null
  }
}

function pick(member: EventMemberRead) {
  const name = member.name || member.email || '?'
  status.value = null
  void act(member.user_id, () =>
    post({ url: `/tasks/${props.taskId}/managers`, body: { user_id: member.user_id } }),
  ).then((done) => {
    if (done) toast.success(t('duties.tasks.managers.added', { name }))
  })
}

/**
 * Put the address in charge, or invite it: a member's address puts them in
 * charge at once, anyone else gets an invitation that names this task.
 * Also "Invite again" for an expired invitation and "Add now" for an address
 * that has joined the event since.
 */
async function invite(email: string, busyKey: string = email) {
  status.value = null
  const outcome = await act(busyKey, async () => {
    const res = await post<{ data: TaskManagerInviteResult }>({
      url: `/tasks/${props.taskId}/managers/invite`,
      body: { email },
    })
    return res.data
  })
  if (!outcome) return
  const result = outcome.value
  if (result.status === 'added') {
    const name = result.manager?.name || email
    toast.success(t('duties.tasks.managers.added', { name }))
    return
  }
  status.value = {
    text: result.emailed
      ? t('duties.tasks.managers.invited', { email })
      : t('duties.tasks.managers.invitedNoMail', { email }),
    warning: result.registration_may_fail ? t('duties.tasks.managers.domainWarning') : undefined,
  }
}

async function resend(invitation: TaskManagerInvitationRead) {
  status.value = null
  const done = await act(invitation.id, () =>
    post({ url: `/tasks/${props.taskId}/managers/invitations/${invitation.id}/resend` }),
  )
  if (done) status.value = { text: t('duties.tasks.managers.resent') }
}

async function withdraw(invitation: TaskManagerInvitationRead) {
  const email = invitation.email
  const confirmed = await confirmDestructive({
    title: t('duties.tasks.managers.withdrawConfirmTitle', { email }),
    text: t('duties.tasks.managers.withdrawConfirmText'),
    confirmText: t('duties.tasks.managers.withdraw'),
  })
  if (!confirmed) return
  status.value = null
  const done = await act(invitation.id, () =>
    del({ url: `/tasks/${props.taskId}/managers/invitations/${invitation.id}` }),
  )
  if (done) status.value = { text: t('duties.tasks.managers.withdrawn') }
}

async function remove(m: TaskManagerBrief) {
  const name = nameOf(m)
  const confirmed = await confirmDestructive({
    title: t('duties.tasks.managers.removeConfirmTitle', { name }),
    text: t('duties.tasks.managers.removeConfirmText', { name }),
    confirmText: t('duties.tasks.managers.remove'),
  })
  if (!confirmed) return
  status.value = null
  const done = await act(m.user_id, () =>
    del({ url: `/tasks/${props.taskId}/managers/${m.user_id}` }),
  )
  if (done) toast.success(t('duties.tasks.managers.removed', { name }))
}

function formatDay(iso: string | null | undefined): string {
  const date = parseServerDate(iso)
  return date ? date.toLocaleDateString(locale.value, { day: 'numeric', month: 'long' }) : ''
}

/** "Invited on 2 July · Valid until 16 July", or how it stands otherwise. */
function pendingLine(invitation: TaskManagerInvitationRead): string {
  const sent = t('duties.tasks.managers.pendingSent', {
    date: formatDay(invitation.created_at),
  })
  let state = ''
  if (invitation.is_member_now) state = t('duties.tasks.managers.pendingIsMember')
  else if (invitation.expired) state = t('duties.tasks.managers.pendingExpired')
  else if (invitation.expires_at)
    state = t('duties.tasks.managers.pendingExpires', { date: formatDay(invitation.expires_at) })
  return state ? `${sent} · ${state}` : sent
}
</script>

<template>
  <div class="space-y-4" data-testid="task-managers-editor">
    <EventMemberPicker
      :members="members"
      :unavailable="unavailable"
      :label="t('duties.tasks.managers.add')"
      :placeholder="t('duties.tasks.managers.searchPlaceholder')"
      :input-id="`task-add-manager-${taskId}`"
      :disabled="busyId !== null"
      :action-hint="t('teams.roster.enterToAdd')"
      testid="task-add-manager"
      allow-email
      phone-sheet
      :sheet-title="t('duties.tasks.managers.pickerTitle')"
      :sheet-context="
        taskName
          ? t('duties.tasks.managers.pickerContext', { task: taskName })
          : t('duties.tasks.managers.pickerContextNew')
      "
      @pick="pick"
      @invite="invite"
    />

    <div
      v-if="status"
      role="status"
      class="bg-primary/10 text-primary space-y-1 rounded-xl px-3 py-2.5 text-sm font-semibold"
      data-testid="task-managers-status"
    >
      <p class="flex items-start gap-2">
        <CircleCheck class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span class="min-w-0 break-words">{{ status.text }}</span>
      </p>
      <p
        v-if="status.warning"
        class="text-warning flex items-start gap-2 font-normal"
        data-testid="task-managers-domain-warning"
      >
        <CircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ status.warning }}</span>
      </p>
    </div>

    <p
      v-if="isEmpty"
      class="text-muted-foreground rounded-md border border-dashed px-4 py-6 text-center text-sm"
      data-testid="task-managers-empty"
    >
      {{ t('duties.tasks.managers.empty') }}
    </p>

    <ul v-else class="space-y-2">
      <li
        v-for="m in managers"
        :key="m.user_id"
        class="bg-card flex min-h-14 items-center gap-3 rounded-xl border py-1.5 pr-1.5 pl-3"
        :data-testid="`task-manager-row-${m.user_id}`"
      >
        <Avatar class="size-9 shrink-0">
          <AvatarImage
            v-if="avatarUrlFor({ id: m.user_id, avatar_etag: m.avatar_etag })"
            :src="avatarUrlFor({ id: m.user_id, avatar_etag: m.avatar_etag })!"
          />
          <AvatarFallback class="text-xs font-bold">{{ initials(nameOf(m)) }}</AvatarFallback>
        </Avatar>
        <span class="min-w-0 flex-1 truncate font-semibold">{{ nameOf(m) }}</span>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button
              variant="ghost"
              size="icon"
              class="size-11 shrink-0"
              :disabled="busyId === m.user_id"
              :aria-label="t('teams.roster.actionsFor', { name: nameOf(m) })"
              :data-testid="`btn-task-manager-actions-${m.user_id}`"
            >
              <EllipsisVertical class="size-4.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              class="text-destructive focus:text-destructive"
              data-testid="btn-remove-task-manager"
              @select="remove(m)"
            >
              <UserMinus class="mr-2 size-4 text-destructive" />
              {{ t('duties.tasks.managers.remove') }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </li>

      <!-- Open invitations: in charge once they accept -->
      <li
        v-for="invitation in invitations"
        :key="invitation.id"
        class="border-warning/40 bg-warning/5 space-y-1.5 rounded-xl border border-dashed px-3 pt-3 pb-2"
        :data-testid="`task-manager-invitation-${invitation.email}`"
      >
        <div class="flex items-center gap-3">
          <span
            class="border-warning/50 text-warning flex size-9 shrink-0 items-center justify-center rounded-full border-[1.5px] border-dashed"
            aria-hidden="true"
          >
            <Mail class="size-4" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate font-semibold">{{ invitation.email }}</span>
            <span class="text-muted-foreground block text-[13px]">
              {{ pendingLine(invitation) }}
            </span>
          </span>
          <span
            class="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-bold"
            :class="
              invitation.expired && !invitation.is_member_now
                ? 'bg-muted text-muted-foreground'
                : 'bg-warning/12 text-warning'
            "
          >
            {{
              invitation.expired && !invitation.is_member_now
                ? t('duties.tasks.managers.pendingExpired')
                : t('duties.tasks.managers.pendingTitle')
            }}
          </span>
        </div>
        <div
          role="group"
          :aria-label="t('duties.tasks.managers.invitationActions', { email: invitation.email })"
          class="flex flex-wrap items-center justify-end gap-x-1"
        >
          <Button
            v-if="invitation.is_member_now"
            variant="ghost"
            size="sm"
            class="text-primary h-9 font-semibold"
            :disabled="busyId === invitation.id"
            data-testid="btn-invitation-add-now"
            @click="invite(invitation.email, invitation.id)"
          >
            <UserPlus aria-hidden="true" />
            {{ t('duties.tasks.managers.addNow') }}
          </Button>
          <Button
            v-else-if="invitation.expired"
            variant="ghost"
            size="sm"
            class="text-primary h-9 font-semibold"
            :disabled="busyId === invitation.id"
            data-testid="btn-invitation-invite-again"
            @click="invite(invitation.email, invitation.id)"
          >
            <Send aria-hidden="true" />
            {{ t('duties.tasks.managers.inviteAgain') }}
          </Button>
          <Button
            v-else
            variant="ghost"
            size="sm"
            class="text-muted-foreground h-9 font-semibold"
            :disabled="busyId === invitation.id"
            data-testid="btn-invitation-resend"
            @click="resend(invitation)"
          >
            <RotateCw aria-hidden="true" />
            {{ t('duties.tasks.managers.resend') }}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            class="text-muted-foreground h-9 font-semibold"
            :disabled="busyId === invitation.id"
            data-testid="btn-invitation-withdraw"
            @click="withdraw(invitation)"
          >
            <Undo2 aria-hidden="true" />
            {{ t('duties.tasks.managers.withdraw') }}
          </Button>
        </div>
      </li>
    </ul>

    <p
      v-if="invitations.length > 0"
      class="text-muted-foreground text-xs"
      data-testid="task-managers-pending-hint"
    >
      {{ t('duties.tasks.managers.pendingHint') }}
    </p>
  </div>
</template>
