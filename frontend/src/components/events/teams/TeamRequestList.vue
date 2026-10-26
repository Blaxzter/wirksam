<script setup lang="ts">
import { computed, ref } from 'vue'

import { Check, Paperclip, ShieldCheck } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { avatarUrlFor } from '@/composables/useAvatarUrl'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import TeamReviewDialog from '@/components/events/teams/TeamReviewDialog.vue'
import {
  type ReviewPerson,
  displayName,
  initials,
  joinNames,
  needsReview,
} from '@/components/events/teams/teamHelpers'

import type { EventTeamMemberRead, EventTeamRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * Every waiting request the viewer may decide, across the event's teams.
 *
 * A request to a team without requirements is decided right in its row. One
 * with requirements says what has to be checked and opens the review dialog
 * instead, because approving it needs a tick (and maybe an issue date) per
 * requirement.
 */
const props = defineProps<{
  eventId: string
  requests: EventTeamMemberRead[]
  teams: EventTeamRead[]
}>()

const emit = defineEmits<{ updated: [] }>()

const { t, locale } = useI18n()
const { post } = useAuthenticatedClient()

const busyId = ref<string | null>(null)
const reviewOpen = ref(false)
const reviewing = ref<EventTeamMemberRead | null>(null)

const teamsById = computed(() => new Map(props.teams.map((team) => [team.id, team])))
const reviewTeam = computed(() =>
  reviewing.value ? teamsById.value.get(reviewing.value.team_id) : undefined,
)
const reviewPerson = computed<ReviewPerson | null>(() =>
  reviewing.value
    ? {
        user_id: reviewing.value.user_id,
        name: displayName(reviewing.value),
        email: reviewing.value.user_email,
        avatar_etag: reviewing.value.user_avatar_etag,
      }
    : null,
)

function teamOf(row: EventTeamMemberRead): EventTeamRead | undefined {
  return teamsById.value.get(row.team_id)
}

function toCheck(row: EventTeamMemberRead): string {
  const labels = (teamOf(row)?.requirements ?? []).map((r) => r.label)
  return t('teams.requests.toCheck', { list: joinNames(labels, locale.value) })
}

async function decide(row: EventTeamMemberRead, approve: boolean) {
  busyId.value = row.id
  try {
    await post({
      url: `/events/${props.eventId}/teams/${row.team_id}/members/${row.user_id}/decide`,
      body: { approve },
    })
    toast.success(
      approve
        ? t('teams.requests.approved', { name: displayName(row), team: row.team_name ?? '' })
        : t('teams.requests.declined'),
    )
    emit('updated')
  } catch (error) {
    toastApiError(error)
  } finally {
    busyId.value = null
  }
}

function review(row: EventTeamMemberRead) {
  reviewing.value = row
  reviewOpen.value = true
}
</script>

<template>
  <Card class="gap-3 py-4" data-testid="team-requests">
    <CardHeader class="px-4">
      <CardTitle id="team-requests-title" class="text-base">
        {{ t('teams.requests.title', { count: requests.length }, requests.length) }}
      </CardTitle>
    </CardHeader>
    <CardContent class="px-4">
      <ul class="divide-y md:space-y-2 md:divide-y-0" aria-labelledby="team-requests-title">
        <li
          v-for="row in requests"
          :key="row.id"
          class="flex flex-col gap-3 py-3 first:pt-0 last:pb-0 md:flex-row md:items-start md:rounded-md md:border md:p-3 md:first:pt-3 md:last:pb-3"
          :data-testid="`team-request-${row.id}`"
        >
          <div class="flex min-w-0 flex-1 items-start gap-3">
            <Avatar class="size-9 shrink-0">
              <AvatarImage
                v-if="avatarUrlFor({ id: row.user_id, avatar_etag: row.user_avatar_etag })"
                :src="avatarUrlFor({ id: row.user_id, avatar_etag: row.user_avatar_etag })!"
              />
              <AvatarFallback class="text-xs">{{ initials(displayName(row)) }}</AvatarFallback>
            </Avatar>
            <div class="min-w-0 flex-1 space-y-1.5">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1 pt-1.5">
                <span class="font-semibold leading-none">{{ displayName(row) }}</span>
                <Badge variant="secondary" class="rounded-full">{{ row.team_name }}</Badge>
              </div>
              <p
                v-if="needsReview(teamOf(row))"
                class="flex items-start gap-1.5 text-xs text-muted-foreground"
              >
                <ShieldCheck class="mt-px size-3.5 shrink-0" />
                {{ toCheck(row) }}
                <template v-if="row.documents?.length">
                  <span aria-hidden="true">·</span>
                  <Paperclip class="mt-px size-3.5 shrink-0" />
                  {{ t('teams.requests.fileAttached', row.documents.length) }}
                </template>
              </p>
              <!-- Their own words, quoted, so a long note never pushes the
                   buttons off a phone screen. -->
              <blockquote
                v-if="row.message"
                class="line-clamp-3 rounded-md bg-muted px-3 py-2 text-sm whitespace-pre-line break-words"
                :title="row.message"
              >
                {{ row.message }}
              </blockquote>
            </div>
          </div>

          <div class="flex shrink-0 gap-2 md:pt-0.5">
            <Button
              v-if="needsReview(teamOf(row))"
              variant="outline"
              class="w-full border-primary/50 md:w-auto"
              :aria-label="
                t('teams.requests.reviewNamed', { name: displayName(row), team: row.team_name })
              "
              :data-testid="`btn-review-team-request-${row.id}`"
              @click="review(row)"
            >
              {{ t('teams.requests.review') }}
            </Button>
            <template v-else>
              <Button
                variant="outline"
                class="flex-1 md:flex-none"
                :disabled="busyId === row.id"
                :aria-label="
                  t('teams.requests.declineNamed', { name: displayName(row), team: row.team_name })
                "
                :data-testid="`btn-decline-team-request-${row.id}`"
                @click="decide(row, false)"
              >
                {{ t('teams.requests.decline') }}
              </Button>
              <Button
                class="flex-1 md:flex-none"
                :disabled="busyId === row.id"
                :aria-label="
                  t('teams.requests.approveNamed', { name: displayName(row), team: row.team_name })
                "
                :data-testid="`btn-approve-team-request-${row.id}`"
                @click="decide(row, true)"
              >
                <Check class="mr-1.5 size-4" />
                {{ t('teams.requests.approve') }}
              </Button>
            </template>
          </div>
        </li>
      </ul>
    </CardContent>

    <TeamReviewDialog
      v-if="reviewing && reviewTeam && reviewPerson"
      v-model:open="reviewOpen"
      :event-id="eventId"
      :team="reviewTeam"
      :person="reviewPerson"
      mode="request"
      :row="reviewing"
      @done="emit('updated')"
    />
  </Card>
</template>
