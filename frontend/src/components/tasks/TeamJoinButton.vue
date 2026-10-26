<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { HTMLAttributes } from 'vue'

import { Clock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { invalidateTeams, useTeams } from '@/composables/useTeams'

import type { ButtonVariants } from '@/components/ui/button'
import Button from '@/components/ui/button/Button.vue'

import TeamJoinDialog from '@/components/events/teams/TeamJoinDialog.vue'

import type { EventTeamMemberRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * Join the team a locked task is reserved for, without leaving the task.
 *
 * An open team is joined on the spot. A team that needs approval opens the
 * same request dialog as the Teams page (`TeamJoinDialog`): what the team is,
 * who to ask, what it checks with a file slot where one is taken, and a note.
 * A request that is already waiting shows as such instead of a button that
 * would only get a 409.
 */
const props = withDefaults(
  defineProps<{
    eventId: string | null | undefined
    teamId: string
    teamName: string
    requiresApproval?: boolean | null
    myStatus?: 'pending' | 'approved' | 'declined' | null
    variant?: ButtonVariants['variant']
    size?: ButtonVariants['size']
    class?: HTMLAttributes['class']
    /** Stack the request dialog above an already open dialog. */
    priority?: boolean
  }>(),
  {
    requiresApproval: true,
    myStatus: null,
    variant: 'default',
    size: 'default',
    class: undefined,
    priority: false,
  },
)

const emit = defineEmits<{
  /** The caller's new status: `approved` for an open team, else `pending`. */
  joined: [status: 'approved' | 'pending']
}>()

const { t } = useI18n()
const { post } = useAuthenticatedClient()
const authStore = useAuthStore()

// What the server said after joining here, ahead of the caller's reload.
const localStatus = ref<'approved' | 'pending' | null>(null)
watch(
  () => [props.teamId, props.myStatus],
  () => (localStatus.value = null),
)
const status = computed(() => localStatus.value ?? props.myStatus ?? null)

const sending = ref(false)
const dialogOpen = ref(false)
// The team (description, contact, requirements) is fetched on the first
// click only; a task list full of locked tasks loads nothing up front.
const wanted = ref(false)
const { teams, loading } = useTeams(() => (wanted.value ? props.eventId : null))
const team = computed(() => teams.value.find((x) => x.id === props.teamId) ?? null)

// A click that came before the team arrived opens the dialog once it does.
const openWhenLoaded = ref(false)
watch(team, (found) => {
  if (found && openWhenLoaded.value) {
    openWhenLoaded.value = false
    dialogOpen.value = true
  }
})

/** Demo events take no files; the dialog says so instead of offering a slot. */
const sandbox = computed(
  () =>
    authStore.profile?.is_sandbox === true ||
    (authStore.selectedEvent?.id === props.eventId && !!authStore.selectedEvent?.is_sandbox),
)

const label = computed(() =>
  props.requiresApproval
    ? t('teamLocks.join.ask', { name: props.teamName })
    : t('teamLocks.join.join', { name: props.teamName }),
)

function settle(next: 'approved' | 'pending') {
  localStatus.value = next
  if (props.eventId) invalidateTeams(props.eventId)
  emit('joined', next)
}

async function joinOpenTeam() {
  if (!props.eventId || sending.value) return
  sending.value = true
  try {
    const res = await post<{ data: EventTeamMemberRead }>({
      url: `/events/${props.eventId}/teams/${props.teamId}/join`,
      body: { message: null },
    })
    const next = res.data.status === 'approved' ? 'approved' : 'pending'
    toast.success(
      next === 'approved'
        ? t('teamLocks.join.joined', { name: props.teamName })
        : t('teams.join.sent', { name: props.teamName }),
    )
    settle(next)
  } catch (error) {
    toastApiError(error)
  } finally {
    sending.value = false
  }
}

function onClick() {
  if (!props.requiresApproval) {
    void joinOpenTeam()
    return
  }
  wanted.value = true
  if (team.value) dialogOpen.value = true
  else openWhenLoaded.value = true
}
</script>

<template>
  <Button
    v-if="status === 'pending'"
    :variant="variant === 'link' ? 'link' : 'outline'"
    :size="size"
    :class="props.class"
    disabled
    :data-testid="`btn-team-pending-${teamId}`"
  >
    <Clock aria-hidden="true" />
    {{ t('teamLocks.join.pending') }}
  </Button>
  <Button
    v-else-if="status !== 'approved'"
    :variant="variant"
    :size="size"
    :class="props.class"
    :disabled="sending || !eventId || (wanted && loading && !team)"
    :data-testid="`btn-team-join-${teamId}`"
    @click.stop="onClick"
  >
    {{ label }}
  </Button>

  <TeamJoinDialog
    v-if="eventId && team"
    v-model:open="dialogOpen"
    :event-id="eventId"
    :team="team"
    :sandbox="sandbox"
    :priority="priority"
    @done="settle"
  />
</template>
