<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { type DateValue, parseDate } from '@internationalized/date'
import { Check, CircleCheck, ShieldCheck } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { avatarUrlFor } from '@/composables/useAvatarUrl'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import Button from '@/components/ui/button/Button.vue'
import { Checkbox } from '@/components/ui/checkbox'
import { DatePicker } from '@/components/ui/date-picker'
import Label from '@/components/ui/label/Label.vue'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import TeamDocumentPreview from '@/components/events/teams/TeamDocumentPreview.vue'
import {
  type ReviewPerson,
  expiryFor,
  firstName,
  initials,
  issueDateProblem,
  reusableCheckFor,
  todayIso,
} from '@/components/events/teams/teamHelpers'

import type {
  EventTeamMemberRead,
  EventTeamRead,
  TeamCheckIn,
  TeamCheckRead,
  TeamRequirementRead,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * Look at one person against a team's requirements and record the checks.
 *
 * - `request`: decide a join request. Approve stays disabled until every
 *   requirement is ticked (with its issue date where asked); the server
 *   enforces the same (`422 team.checks_missing`).
 * - `add`: place someone straight into a team that has requirements.
 * - `recheck`: renew checks for a member flagged "needs a new check"; only the
 *   ticked requirements change.
 *
 * Nothing but the tick, the date and who ticked it is stored. Attached files
 * are deleted by the server as soon as the request is decided.
 */
const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  eventId: string
  team: EventTeamRead
  person: ReviewPerson
  mode: 'request' | 'add' | 'recheck'
  /** The request (or roster row): note, files, reusable and current checks. */
  row?: EventTeamMemberRead | null
  /**
   * Valid checks from another team of this event, when there is no request
   * row to carry them (adding someone directly). Falls back to the row's.
   */
  reusableChecks?: TeamCheckRead[] | null
}>()

const emit = defineEmits<{ done: [] }>()

const { t, locale } = useI18n()
const { post, put } = useAuthenticatedClient()

const requirements = computed<TeamRequirementRead[]>(() => props.team.requirements ?? [])
const today = todayIso()
const latestIssue = parseDate(today)

// The picker works in DateValues; the checks and their validation keep ISO strings.
function issuedValue(req: TeamRequirementRead): DateValue | undefined {
  const iso = issued[req.id]
  return iso ? parseDate(iso) : undefined
}

function setIssued(req: TeamRequirementRead, value: DateValue | undefined) {
  issued[req.id] = value ? value.toString() : ''
}

const reusable = computed(() => props.reusableChecks ?? props.row?.reusable_checks ?? [])

const ticked = reactive<Record<string, boolean>>({})
const issued = reactive<Record<string, string>>({})
const busy = ref<'approve' | 'decline' | null>(null)

watch(
  open,
  (isOpen) => {
    if (!isOpen) return
    for (const req of requirements.value) {
      ticked[req.id] = false
      // An earlier check in another team of this event fills in the date;
      // the tick stays the decider's to give.
      const reuse = props.mode === 'recheck' ? undefined : reusableCheckFor(req, reusable.value)
      issued[req.id] = reuse?.issued_on ?? ''
    }
    busy.value = null
  },
  { immediate: true },
)

function problemFor(req: TeamRequirementRead) {
  return req.ask_issue_date ? issueDateProblem(req, issued[req.id] || null, today) : null
}

function isReady(req: TeamRequirementRead): boolean {
  if (!ticked[req.id]) return false
  if (!req.ask_issue_date) return true
  return !!issued[req.id] && problemFor(req) === null
}

const canApprove = computed(() =>
  props.mode === 'recheck'
    ? requirements.value.some((r) => ticked[r.id]) &&
      requirements.value.every((r) => !ticked[r.id] || isReady(r))
    : requirements.value.every(isReady),
)

const checks = computed<TeamCheckIn[]>(() =>
  requirements.value
    .filter((r) => ticked[r.id])
    .map((r) => ({
      requirement_id: r.id,
      issued_on: r.ask_issue_date ? issued[r.id] || null : null,
    })),
)

const hasNoCopyRequirement = computed(() => requirements.value.some((r) => !r.accepts_document))
const documents = computed(() => props.row?.documents ?? [])
const shortName = computed(() => firstName(props.person.name))

function documentFor(req: TeamRequirementRead) {
  return documents.value.find((d) => d.requirement_id === req.id)
}

function currentCheckFor(req: TeamRequirementRead) {
  return props.row?.checks?.find((c) => c.requirement_id === req.id)
}

function formatDay(iso: string | null | undefined, withYear = true): string {
  if (!iso) return ''
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return d.toLocaleDateString(locale.value, {
    day: 'numeric',
    month: 'short',
    ...(withYear ? { year: 'numeric' } : {}),
  })
}

const subline = computed(() => {
  const parts: string[] = []
  if (props.row?.created_at && props.mode === 'request')
    parts.push(t('teams.review.asked', { date: formatDay(props.row.created_at, false) }))
  if (props.person.email && props.person.email !== props.person.name) parts.push(props.person.email)
  return parts.join(' · ')
})

const inEvent = computed(() => {
  const parts: string[] = []
  const others = props.row?.other_team_names ?? []
  if (others.length) parts.push(t('teams.review.memberOf', { teams: others.join(', ') }))
  const booked = props.row?.booked_shift_count ?? 0
  parts.push(
    booked > 0
      ? t('teams.review.bookedShifts', { count: booked }, booked)
      : t('teams.review.noBookings'),
  )
  return parts.join(' · ')
})

const title = computed(() => {
  if (props.mode === 'add')
    return t('teams.review.addTitle', { name: props.person.name, team: props.team.name })
  if (props.mode === 'recheck') return t('teams.review.recheckTitle', { name: props.person.name })
  return t('teams.review.title', { name: props.person.name, team: props.team.name })
})

const approveLabel = computed(() => {
  if (props.mode === 'add') return t('teams.review.addName', { name: shortName.value })
  if (props.mode === 'recheck') return t('teams.review.saveChecks')
  return t('teams.review.approveName', { name: shortName.value })
})

const base = computed(() => `/events/${props.eventId}/teams/${props.team.id}/members`)

async function approve() {
  if (!canApprove.value || busy.value) return
  busy.value = 'approve'
  try {
    if (props.mode === 'request') {
      await post({
        url: `${base.value}/${props.person.user_id}/decide`,
        body: { approve: true, checks: checks.value },
      })
      toast.success(
        t('teams.requests.approved', { name: props.person.name, team: props.team.name }),
      )
    } else if (props.mode === 'add') {
      await post({
        url: base.value,
        body: { user_id: props.person.user_id, role: 'member', checks: checks.value },
      })
      toast.success(t('teams.roster.added', { name: props.person.name }))
    } else {
      await put({
        url: `${base.value}/${props.person.user_id}/checks`,
        body: { checks: checks.value },
      })
      toast.success(t('teams.review.checksSaved'))
    }
    open.value = false
    emit('done')
  } catch (error) {
    toastApiError(error)
  } finally {
    busy.value = null
  }
}

async function decline() {
  if (busy.value) return
  busy.value = 'decline'
  try {
    await post({ url: `${base.value}/${props.person.user_id}/decide`, body: { approve: false } })
    toast.success(t('teams.requests.declined'))
    open.value = false
    emit('done')
  } catch (error) {
    toastApiError(error)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent dialog-class="sm:max-w-xl" data-testid="team-review-dialog">
      <ResponsiveDialogHeader>
        <div class="flex items-start gap-3">
          <Avatar class="size-11 shrink-0">
            <AvatarImage
              v-if="avatarUrlFor({ id: person.user_id, avatar_etag: person.avatar_etag })"
              :src="avatarUrlFor({ id: person.user_id, avatar_etag: person.avatar_etag })!"
            />
            <AvatarFallback>{{ initials(person.name) }}</AvatarFallback>
          </Avatar>
          <div class="min-w-0 space-y-1">
            <ResponsiveDialogTitle class="text-lg leading-snug">{{ title }}</ResponsiveDialogTitle>
            <ResponsiveDialogDescription class="text-xs">
              {{ subline }}
              <template v-if="mode === 'request'">
                <span v-if="subline" aria-hidden="true"> · </span>{{ inEvent }}
              </template>
            </ResponsiveDialogDescription>
          </div>
        </div>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="space-y-5 pb-4">
        <figure
          v-if="mode === 'request' && row?.message"
          class="bg-muted rounded-md px-3.5 py-3"
          data-testid="team-review-note"
        >
          <figcaption class="text-muted-foreground mb-1 text-xs font-medium">
            {{ t('teams.review.note') }}
          </figcaption>
          <p class="text-sm whitespace-pre-line break-words">{{ row.message }}</p>
        </figure>

        <section aria-labelledby="team-review-checks" class="space-y-2">
          <h3
            id="team-review-checks"
            class="text-muted-foreground text-xs font-semibold tracking-wide uppercase"
          >
            {{
              mode === 'recheck'
                ? t('teams.review.checksTitle')
                : mode === 'add'
                  ? t('teams.review.beforeAdd')
                  : t('teams.review.beforeApprove')
            }}
          </h3>

          <div
            v-for="req in requirements"
            :key="req.id"
            class="space-y-3 rounded-md border p-3"
            :data-testid="`team-review-requirement-${req.id}`"
          >
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start">
              <div class="flex min-w-0 flex-1 items-start gap-3">
                <Checkbox
                  :id="`team-check-${req.id}`"
                  :model-value="ticked[req.id]"
                  class="mt-0.5"
                  :data-testid="`team-check-${req.id}`"
                  @update:model-value="(v) => (ticked[req.id] = v === true)"
                />
                <div class="min-w-0 space-y-0.5">
                  <Label :for="`team-check-${req.id}`" class="leading-snug">
                    {{ t('teams.review.seen', { label: req.label }) }}
                  </Label>
                  <p v-if="req.description" class="text-muted-foreground text-xs">
                    {{ req.description }}
                  </p>
                  <p
                    v-if="mode !== 'recheck' && reusableCheckFor(req, reusable)"
                    class="text-primary flex items-center gap-1 text-xs"
                    data-testid="team-check-reused"
                  >
                    <CircleCheck class="size-3.5 shrink-0" />
                    {{
                      t('teams.review.alreadyChecked', {
                        team: reusableCheckFor(req, reusable)!.source_team_name ?? '',
                        date: formatDay(reusableCheckFor(req, reusable)!.checked_at),
                      })
                    }}
                  </p>
                  <p
                    v-else-if="mode === 'recheck' && currentCheckFor(req)"
                    class="text-xs"
                    :class="
                      currentCheckFor(req)!.expired
                        ? 'text-amber-700 dark:text-amber-300'
                        : 'text-muted-foreground'
                    "
                  >
                    {{
                      currentCheckFor(req)!.expires_on
                        ? t(
                            currentCheckFor(req)!.expired
                              ? 'teams.roster.checkExpiredOn'
                              : 'teams.roster.checkValidUntil',
                            { date: formatDay(currentCheckFor(req)!.expires_on) },
                          )
                        : t('teams.roster.checkNoExpiry')
                    }}
                  </p>
                </div>
              </div>

              <div v-if="req.ask_issue_date" class="space-y-1 sm:w-44 sm:shrink-0">
                <Label :id="`team-issued-label-${req.id}`" class="text-xs">
                  {{ t('teams.review.issuedOn') }}
                </Label>
                <div
                  role="group"
                  :aria-labelledby="`team-issued-label-${req.id}`"
                  :aria-invalid="problemFor(req) !== null || undefined"
                  :data-testid="`team-issued-${req.id}`"
                >
                  <DatePicker
                    :model-value="issuedValue(req)"
                    :max-value="latestIssue"
                    :placeholder="t('teams.review.issuedPlaceholder')"
                    @update:model-value="setIssued(req, $event)"
                  />
                </div>
                <p
                  v-if="problemFor(req) === 'future'"
                  class="text-destructive text-xs"
                  role="alert"
                >
                  {{ t('teams.review.issuedFuture') }}
                </p>
                <p
                  v-else-if="problemFor(req) === 'expired'"
                  class="text-destructive text-xs"
                  role="alert"
                >
                  {{
                    t(
                      'teams.review.issuedExpired',
                      { count: req.valid_for_years ?? 0 },
                      req.valid_for_years ?? 0,
                    )
                  }}
                </p>
                <p
                  v-else-if="issued[req.id] && req.valid_for_years"
                  class="text-muted-foreground text-xs"
                >
                  {{
                    t('teams.review.validUntil', {
                      date: formatDay(expiryFor(req, issued[req.id] ?? null, today)),
                    })
                  }}
                </p>
              </div>
            </div>

            <template v-if="req.accepts_document && mode === 'request'">
              <TeamDocumentPreview
                v-if="documentFor(req)"
                :event-id="eventId"
                :team-id="team.id"
                :user-id="person.user_id"
                :document="documentFor(req)!"
              />
              <p v-else class="text-muted-foreground text-xs">{{ t('teams.review.noFile') }}</p>
            </template>
          </div>

          <p
            v-if="hasNoCopyRequirement"
            class="text-muted-foreground flex items-start gap-1.5 text-xs"
            data-testid="team-review-no-copy"
          >
            <ShieldCheck class="mt-px size-3.5 shrink-0" />
            {{ t('teams.review.noCopy') }}
          </p>
          <p
            v-if="documents.length > 0 && mode === 'request'"
            class="text-muted-foreground text-xs"
          >
            {{ t('teams.review.fileDeleted') }}
          </p>
        </section>
      </ResponsiveDialogBody>

      <!-- One row on both shells: the hint takes its own line on a phone, the
           two buttons share the next one (Decline narrower than Approve). -->
      <ResponsiveDialogFooter layout="row" class="flex-wrap border-t">
        <p
          v-if="!canApprove"
          class="text-muted-foreground w-full text-xs md:mr-auto md:w-auto"
          data-testid="team-review-hint"
        >
          {{ mode === 'recheck' ? t('teams.review.tickToSave') : t('teams.review.tickToApprove') }}
        </p>
        <div class="flex w-full gap-2 md:ml-auto md:w-auto">
          <Button
            v-if="mode === 'request'"
            variant="outline"
            class="flex-1 md:flex-none"
            :disabled="busy !== null"
            data-testid="btn-team-review-decline"
            @click="decline"
          >
            {{ t('teams.requests.decline') }}
          </Button>
          <Button
            class="flex-[2] md:flex-none"
            :disabled="!canApprove || busy !== null"
            data-testid="btn-team-review-approve"
            @click="approve"
          >
            <Check class="mr-1.5 size-4" />
            {{ approveLabel }}
          </Button>
        </div>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
