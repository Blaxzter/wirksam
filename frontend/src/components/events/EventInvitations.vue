<script setup lang="ts">
import { computed, ref } from 'vue'

import { Check, Copy, Link2, Mail, Send, X } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Label from '@/components/ui/label/Label.vue'
import { NativeSelect } from '@/components/ui/native-select'
import Separator from '@/components/ui/separator/Separator.vue'
import Textarea from '@/components/ui/textarea/Textarea.vue'

import { joinNames } from '@/components/events/teams/teamHelpers'

import type { EventInvitationBulkResult, EventInvitationRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { type AssignableEventRole, roleLabelKey } from '@/lib/event-roles'

const props = defineProps<{
  eventId: string
  invitations: EventInvitationRead[]
}>()

const emit = defineEmits<{ updated: [] }>()

const { t, locale } = useI18n()
const { post, delete: del } = useAuthenticatedClient()

const emails = ref('')
const role = ref<AssignableEventRole>('member')
const sending = ref(false)
const creatingLink = ref(false)
const revokingId = ref<string | null>(null)
const copiedToken = ref<string | null>(null)

/** Split on commas, semicolons, whitespace or newlines — however it was pasted. */
const parsedEmails = computed(() =>
  emails.value
    .split(/[\s,;]+/)
    .map((e) => e.trim())
    .filter(Boolean),
)

const emailInvites = computed(() => props.invitations.filter((i) => i.email))
const linkInvites = computed(() => props.invitations.filter((i) => !i.email))

function inviteUrl(token: string): string {
  return `${window.location.origin}/invite/${token}`
}

/** "Bar and Grill": the tasks an invitation asks the person to be in charge of. */
function taskNames(invitation: EventInvitationRead): string {
  return joinNames(
    (invitation.tasks ?? []).map((task) => task.name),
    locale.value,
  )
}

async function sendInvites() {
  if (parsedEmails.value.length === 0) return
  sending.value = true
  try {
    const res = await post<{ data: EventInvitationBulkResult }>({
      url: `/events/${props.eventId}/invitations/bulk`,
      body: { emails: parsedEmails.value, role: role.value },
    })
    const {
      created,
      skipped_existing_members = [],
      skipped_already_invited = [],
      skipped_rate_limited = [],
    } = res.data

    if (created.length > 0) {
      toast.success(t('duties.events.invitations.sent', { count: created.length }, created.length))
    }
    // Skips are informational, not failures — say so plainly rather than
    // letting a partially-applied batch look like it worked completely.
    const skipped = [...skipped_existing_members, ...skipped_already_invited]
    if (skipped.length > 0) {
      toast.info(t('duties.events.invitations.skipped', { emails: skipped.join(', ') }))
    }
    // Refused by the daily limits: not sent, so worth trying again later.
    if (skipped_rate_limited.length > 0) {
      toast.warning(
        t('duties.events.invitations.skippedRateLimited', {
          emails: skipped_rate_limited.join(', '),
        }),
      )
    }

    emails.value = ''
    emit('updated')
  } catch (error) {
    toastApiError(error)
  } finally {
    sending.value = false
  }
}

async function createShareLink() {
  creatingLink.value = true
  try {
    const res = await post<{ data: EventInvitationRead }>({
      url: `/events/${props.eventId}/invitations`,
      body: { role: role.value },
    })
    emit('updated')
    await copyLink(res.data.token)
  } catch (error) {
    toastApiError(error)
  } finally {
    creatingLink.value = false
  }
}

async function copyLink(token: string) {
  try {
    await navigator.clipboard.writeText(inviteUrl(token))
    copiedToken.value = token
    toast.success(t('duties.events.invitations.linkCopied'))
    setTimeout(() => {
      if (copiedToken.value === token) copiedToken.value = null
    }, 2000)
  } catch {
    // Clipboard can be blocked (insecure context, denied permission) — show
    // the URL so it can still be copied by hand.
    toast.info(inviteUrl(token))
  }
}

async function revoke(invitation: EventInvitationRead) {
  revokingId.value = invitation.id
  try {
    await del({ url: `/events/${props.eventId}/invitations/${invitation.id}` })
    emit('updated')
    toast.success(t('duties.events.invitations.revoked'))
  } catch (error) {
    toastApiError(error)
  } finally {
    revokingId.value = null
  }
}
</script>

<template>
  <Card data-testid="section-event-invitations">
    <CardHeader>
      <div class="space-y-1">
        <CardTitle class="flex items-center gap-2">
          <Mail class="h-5 w-5 shrink-0" />
          {{ t('duties.events.invitations.title') }}
        </CardTitle>
        <CardDescription>{{ t('duties.events.invitations.subtitle') }}</CardDescription>
      </div>
    </CardHeader>

    <CardContent class="space-y-4">
      <div class="space-y-2">
        <Label for="invite-emails">{{ t('duties.events.invitations.emailsLabel') }}</Label>
        <Textarea
          id="invite-emails"
          v-model="emails"
          data-testid="input-invite-emails"
          rows="2"
          :placeholder="t('duties.events.invitations.emailsPlaceholder')"
        />
        <p class="text-xs text-muted-foreground">
          {{ t('duties.events.invitations.emailsHint') }}
        </p>
      </div>

      <div class="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div class="space-y-2 sm:w-40">
          <Label for="invite-role">{{ t('duties.events.invitations.roleLabel') }}</Label>
          <NativeSelect id="invite-role" v-model="role" class="h-9">
            <option value="member">{{ t(roleLabelKey('member')) }}</option>
            <option value="admin">{{ t(roleLabelKey('admin')) }}</option>
          </NativeSelect>
        </div>
        <div class="flex flex-1 flex-wrap gap-2">
          <Button
            data-testid="btn-send-invites"
            :disabled="parsedEmails.length === 0 || sending"
            @click="sendInvites"
          >
            <Send class="mr-1.5 h-4 w-4" />
            {{
              parsedEmails.length > 1
                ? t('duties.events.invitations.sendMany', { count: parsedEmails.length })
                : t('duties.events.invitations.send')
            }}
          </Button>
          <Button
            variant="outline"
            data-testid="btn-create-share-link"
            :disabled="creatingLink"
            @click="createShareLink"
          >
            <Link2 class="mr-1.5 h-4 w-4" />
            {{ t('duties.events.invitations.createLink') }}
          </Button>
        </div>
      </div>

      <template v-if="linkInvites.length > 0">
        <Separator />
        <div class="space-y-1.5">
          <p class="text-sm font-medium">{{ t('duties.events.invitations.linksTitle') }}</p>
          <div
            v-for="invitation in linkInvites"
            :key="invitation.id"
            class="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
            data-testid="share-link-row"
          >
            <div class="flex min-w-0 items-center gap-2">
              <Link2 class="h-4 w-4 shrink-0 text-muted-foreground" />
              <code class="truncate text-xs">{{ inviteUrl(invitation.token) }}</code>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <Badge variant="outline">{{ t(roleLabelKey(invitation.role)) }}</Badge>
              <Badge variant="secondary">
                {{
                  t(
                    'duties.events.invitations.uses',
                    { count: invitation.use_count ?? 0 },
                    invitation.use_count ?? 0,
                  )
                }}
              </Badge>
              <Button
                variant="ghost"
                size="icon"
                class="size-7"
                :aria-label="t('duties.events.invitations.copyLink')"
                @click="copyLink(invitation.token)"
              >
                <Check v-if="copiedToken === invitation.token" class="h-3.5 w-3.5" />
                <Copy v-else class="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                class="size-7 text-muted-foreground hover:text-destructive"
                :disabled="revokingId === invitation.id"
                :aria-label="t('duties.events.invitations.revoke')"
                @click="revoke(invitation)"
              >
                <X class="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </template>

      <template v-if="emailInvites.length > 0">
        <Separator />
        <div class="space-y-1.5">
          <p class="text-sm font-medium">{{ t('duties.events.invitations.pendingTitle') }}</p>
          <div
            v-for="invitation in emailInvites"
            :key="invitation.id"
            class="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
            data-testid="pending-invite-row"
          >
            <div class="min-w-0">
              <p class="truncate text-sm">{{ invitation.email }}</p>
              <p
                v-if="invitation.tasks?.length"
                class="text-xs text-muted-foreground"
                data-testid="pending-invite-tasks"
              >
                {{ t('duties.events.invitations.forTasks', { tasks: taskNames(invitation) }) }}
              </p>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <Badge variant="outline">{{ t(roleLabelKey(invitation.role)) }}</Badge>
              <Button
                variant="ghost"
                size="icon"
                class="size-7 text-muted-foreground hover:text-destructive"
                data-testid="btn-revoke-invite"
                :disabled="revokingId === invitation.id"
                :aria-label="t('duties.events.invitations.revoke')"
                @click="revoke(invitation)"
              >
                <X class="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </template>

      <p
        v-if="invitations.length === 0"
        class="text-sm text-muted-foreground"
        data-testid="invitations-empty"
      >
        {{ t('duties.events.invitations.empty') }}
      </p>
    </CardContent>
  </Card>
</template>
