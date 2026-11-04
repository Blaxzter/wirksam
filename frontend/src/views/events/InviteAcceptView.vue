<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { CalendarDays, CheckCircle2, UserCheck, XCircle } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import type { EventInvitationPreview, EventRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { roleLabelKey } from '@/lib/event-roles'
import { formatDate } from '@/lib/format'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { get, post } = useAuthenticatedClient()

const token = computed(() => String(route.params.token ?? ''))

const preview = ref<EventInvitationPreview | null>(null)
const loading = ref(true)
const accepting = ref(false)
const notFound = ref(false)

/**
 * Why this link cannot be used, as a human sentence.
 *
 * A dead link deserves a reason — "expired" and "sent to a different address"
 * call for very different next steps from the person holding it.
 */
const invalidMessage = computed(() => {
  const reason = preview.value?.invalid_reason
  if (!reason) return null
  return t(`duties.events.invite.invalid.${reason}`)
})

/**
 * The preview needs a signed-in user, so a visitor without an account would
 * only ever see "invitation not found". Offer them the two ways in instead,
 * carrying the invitation along: back here after signing in, and to the
 * registration form, where it is what lets an invitation-only deployment
 * accept the signup.
 */
const signedOut = computed(() => !authStore.isAuthenticated)
const returnPath = computed(() => `/invite/${encodeURIComponent(token.value)}`)

async function loadPreview() {
  if (signedOut.value) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const res = await get<{ data: EventInvitationPreview }>({
      url: `/invitations/${token.value}`,
    })
    preview.value = res.data
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

/**
 * The tasks this invitation asks the person to run. The server lists them to
 * the addressee only; to anyone else (`email_mismatch`) the list is empty.
 * It also lists them to a member whose invitation is spent, expired or
 * withdrawn, but nothing is asked of them any more, so they are not shown.
 */
const tasks = computed(() => (preview.value?.is_valid ? (preview.value.tasks ?? []) : []))

/**
 * A member who opens an invitation that is gone: they are in the event, but
 * not put in charge of anything, and they should be told why. A used one
 * needs no word, as they have already accepted it.
 */
const memberInvalidMessage = computed(() => {
  const reason = preview.value?.invalid_reason
  return reason === 'expired' || reason === 'revoked' ? invalidMessage.value : null
})

/**
 * Someone who joined the event another way still holds an invitation to be
 * in charge: accepting it puts them in charge, so they get the button too.
 */
const canAcceptTasks = computed(
  () => !!preview.value?.already_member && !!preview.value.is_valid && tasks.value.length > 0,
)

function taskDates(task: { start_date: string; end_date: string }): string {
  const day = (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(locale.value, {
      day: 'numeric',
      month: 'short',
    })
  return task.start_date === task.end_date
    ? day(task.start_date)
    : `${day(task.start_date)} – ${day(task.end_date)}`
}

async function accept() {
  const wasMember = !!preview.value?.already_member
  const asked = tasks.value
  accepting.value = true
  try {
    const res = await post<{ data: EventRead }>({
      url: `/invitations/${token.value}/accept`,
    })
    // Refresh the profile so the new membership is reflected in the store,
    // then drop the user straight into the event they just joined.
    await authStore.loadProfile()
    await authStore.setSelectedEvent(res.data.id)
    // Asked to run one task: that task is where they want to be. With
    // several, the dashboard lists them.
    if (asked.length === 1) {
      const task = asked[0]
      toast.success(
        wasMember
          ? t('duties.events.invite.nowInCharge', { task: task.name })
          : t('duties.events.invite.joinedInCharge', { name: res.data.name, task: task.name }),
      )
      router.push({ name: 'task-detail', params: { eventId: task.task_id } })
      return
    }
    toast.success(t('duties.events.invite.joined', { name: res.data.name }))
    router.push({ name: 'home' })
  } catch (error) {
    toastApiError(error)
    accepting.value = false
  }
}

function goToEvent() {
  if (!preview.value) return
  void authStore.setSelectedEvent(preview.value.event_id).then(() => {
    router.push({ name: 'home' })
  })
}

onMounted(loadPreview)
</script>

<template>
  <div class="flex min-h-screen items-center justify-center p-4">
    <Card class="w-full max-w-md" data-testid="invite-card">
      <template v-if="loading">
        <CardContent class="py-12 text-center text-muted-foreground">
          {{ t('common.states.loading') }}
        </CardContent>
      </template>

      <template v-else-if="signedOut">
        <CardHeader class="text-center">
          <CheckCircle2 class="mx-auto h-10 w-10 text-primary" />
          <CardTitle data-testid="invite-signed-out">
            {{ t('duties.events.invite.signedOutTitle') }}
          </CardTitle>
          <CardDescription>{{ t('duties.events.invite.signedOutBody') }}</CardDescription>
        </CardHeader>
        <CardContent class="space-y-2">
          <Button
            class="w-full"
            data-testid="btn-invite-register"
            @click="
              router.push({
                name: 'register',
                query: { invite: token, redirect: returnPath },
              })
            "
          >
            {{ t('duties.events.invite.createAccount') }}
          </Button>
          <Button
            class="w-full"
            variant="outline"
            data-testid="btn-invite-login"
            @click="router.push({ name: 'login', query: { redirect: returnPath } })"
          >
            {{ t('duties.events.invite.signIn') }}
          </Button>
        </CardContent>
      </template>

      <template v-else-if="notFound || !preview">
        <CardHeader class="text-center">
          <XCircle class="mx-auto h-10 w-10 text-destructive" />
          <CardTitle data-testid="invite-not-found">
            {{ t('duties.events.invite.notFoundTitle') }}
          </CardTitle>
          <CardDescription>{{ t('duties.events.invite.notFoundBody') }}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button class="w-full" variant="outline" @click="router.push({ name: 'home' })">
            {{ t('duties.events.invite.goHome') }}
          </Button>
        </CardContent>
      </template>

      <template v-else>
        <CardHeader class="space-y-3 text-center">
          <CheckCircle2
            v-if="preview.is_valid || preview.already_member"
            class="mx-auto h-10 w-10 text-primary"
          />
          <XCircle v-else class="mx-auto h-10 w-10 text-destructive" />

          <CardTitle data-testid="invite-event-name">{{ preview.event_name }}</CardTitle>
          <CardDescription>
            <template v-if="preview.invited_by_name">
              {{ t('duties.events.invite.fromNamed', { name: preview.invited_by_name }) }}
            </template>
            <template v-else>{{ t('duties.events.invite.from') }}</template>
          </CardDescription>
        </CardHeader>

        <CardContent class="space-y-4">
          <div class="space-y-2 rounded-lg border p-3 text-sm">
            <p class="flex items-center gap-2 text-muted-foreground">
              <CalendarDays class="h-4 w-4 shrink-0" />
              {{ formatDate(preview.start_date) }} – {{ formatDate(preview.end_date) }}
            </p>
            <p v-if="preview.event_description" class="text-muted-foreground">
              {{ preview.event_description }}
            </p>
            <p class="flex items-center gap-2">
              <span class="text-muted-foreground">
                {{ t('duties.events.invite.asRole') }}
              </span>
              <Badge variant="secondary">{{ t(roleLabelKey(preview.role)) }}</Badge>
            </p>
          </div>

          <div
            v-if="tasks.length > 0"
            class="space-y-2 rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm"
            data-testid="invite-tasks"
          >
            <p class="flex items-center gap-2 font-semibold">
              <UserCheck class="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              {{ t('duties.events.invite.tasksTitle') }}
            </p>
            <ul class="space-y-1">
              <li
                v-for="task in tasks"
                :key="task.task_id"
                class="flex flex-wrap items-baseline justify-between gap-x-3"
              >
                <span class="font-medium">{{ task.name }}</span>
                <span class="text-xs text-muted-foreground">{{ taskDates(task) }}</span>
              </li>
            </ul>
            <p class="text-muted-foreground">{{ t('duties.events.invite.tasksHint') }}</p>
          </div>

          <template v-if="canAcceptTasks">
            <p
              class="text-center text-sm text-muted-foreground"
              data-testid="invite-already-member"
            >
              {{ t('duties.events.invite.alreadyMember') }}
            </p>
            <Button
              class="w-full"
              data-testid="btn-accept-invite"
              :disabled="accepting"
              @click="accept"
            >
              {{ t('duties.events.invite.acceptTasks') }}
            </Button>
            <Button class="w-full" variant="ghost" :disabled="accepting" @click="goToEvent">
              {{ t('duties.events.invite.openEvent') }}
            </Button>
          </template>

          <template v-else-if="preview.already_member">
            <p
              v-if="memberInvalidMessage"
              class="text-center text-sm text-destructive"
              data-testid="invite-invalid"
            >
              {{ memberInvalidMessage }}
            </p>
            <p
              class="text-center text-sm text-muted-foreground"
              data-testid="invite-already-member"
            >
              {{ t('duties.events.invite.alreadyMember') }}
            </p>
            <Button class="w-full" data-testid="btn-open-event" @click="goToEvent">
              {{ t('duties.events.invite.openEvent') }}
            </Button>
          </template>

          <template v-else-if="preview.is_valid">
            <Button
              class="w-full"
              data-testid="btn-accept-invite"
              :disabled="accepting"
              @click="accept"
            >
              {{ t('duties.events.invite.accept') }}
            </Button>
            <Button
              class="w-full"
              variant="ghost"
              :disabled="accepting"
              @click="router.push({ name: 'home' })"
            >
              {{ t('duties.events.invite.decline') }}
            </Button>
          </template>

          <template v-else>
            <p class="text-center text-sm text-destructive" data-testid="invite-invalid">
              {{ invalidMessage }}
            </p>
            <Button class="w-full" variant="outline" @click="router.push({ name: 'home' })">
              {{ t('duties.events.invite.goHome') }}
            </Button>
          </template>
        </CardContent>
      </template>
    </Card>
  </div>
</template>
