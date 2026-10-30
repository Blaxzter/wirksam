<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { EllipsisVertical, UserMinus } from '@lucide/vue'
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

import type { EventMemberRead, TaskManagerBrief } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { initials } from '@/lib/format'

/**
 * Put event members in charge of a task, or take them off it. Organisers only;
 * the server refuses everyone else. Every change is saved at once, then
 * `reload` fetches the task again, whose `managers` come back in through the
 * prop. The editor stays busy until that reload is in, so the list never shows
 * the old state after the success message.
 */
const props = defineProps<{
  taskId: string
  eventId: string
  managers: TaskManagerBrief[]
  reload: () => Promise<unknown>
}>()

const { t } = useI18n()
const { get, post, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const members = ref<EventMemberRead[]>([])
const busyUserId = ref<string | null>(null)

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

async function loadMembers() {
  try {
    const res = await get<{ data: EventMemberRead[] }>({ url: `/events/${props.eventId}/members` })
    members.value = res.data
  } catch (err) {
    toastApiError(err)
  }
}

watch(() => props.eventId, loadMembers, { immediate: true })

async function act(userId: string, run: () => Promise<unknown>, message: string) {
  busyUserId.value = userId
  try {
    await run()
    await props.reload()
    toast.success(message)
  } catch (err) {
    toastApiError(err)
  } finally {
    busyUserId.value = null
  }
}

function pick(member: EventMemberRead) {
  const name = member.name || member.email || '?'
  void act(
    member.user_id,
    () => post({ url: `/tasks/${props.taskId}/managers`, body: { user_id: member.user_id } }),
    t('duties.tasks.managers.added', { name }),
  )
}

async function remove(m: TaskManagerBrief) {
  const name = nameOf(m)
  const ok = await confirmDestructive({
    title: t('duties.tasks.managers.removeConfirmTitle', { name }),
    text: t('duties.tasks.managers.removeConfirmText', { name }),
    confirmText: t('duties.tasks.managers.remove'),
  })
  if (!ok) return
  await act(
    m.user_id,
    () => del({ url: `/tasks/${props.taskId}/managers/${m.user_id}` }),
    t('duties.tasks.managers.removed', { name }),
  )
}
</script>

<template>
  <div class="space-y-4" data-testid="task-managers-editor">
    <EventMemberPicker
      :members="members"
      :unavailable="unavailable"
      :label="t('duties.tasks.managers.add')"
      :placeholder="t('teams.roster.addPlaceholder')"
      :input-id="`task-add-manager-${taskId}`"
      :disabled="busyUserId !== null"
      :action-hint="t('teams.roster.enterToAdd')"
      testid="task-add-manager"
      @pick="pick"
    />

    <p
      v-if="managers.length === 0"
      class="text-muted-foreground rounded-md border border-dashed px-4 py-6 text-center text-sm"
      data-testid="task-managers-empty"
    >
      {{ t('duties.tasks.managers.empty') }}
    </p>

    <ul v-else class="space-y-2">
      <li
        v-for="m in managers"
        :key="m.user_id"
        class="flex items-center gap-3 rounded-md border px-3 py-2"
        :data-testid="`task-manager-row-${m.user_id}`"
      >
        <Avatar class="size-8 shrink-0">
          <AvatarImage
            v-if="avatarUrlFor({ id: m.user_id, avatar_etag: m.avatar_etag })"
            :src="avatarUrlFor({ id: m.user_id, avatar_etag: m.avatar_etag })!"
          />
          <AvatarFallback class="text-[10px]">{{ initials(nameOf(m)) }}</AvatarFallback>
        </Avatar>
        <span class="min-w-0 flex-1 truncate text-sm font-medium">{{ nameOf(m) }}</span>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button
              variant="ghost"
              size="icon"
              class="size-8 shrink-0"
              :disabled="busyUserId === m.user_id"
              :aria-label="t('teams.roster.actionsFor', { name: nameOf(m) })"
              :data-testid="`btn-task-manager-actions-${m.user_id}`"
            >
              <EllipsisVertical class="size-4" />
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
    </ul>
  </div>
</template>
