<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { Phone, ShieldCheck } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
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
import { Textarea } from '@/components/ui/textarea'

import TeamFileField from '@/components/events/teams/TeamFileField.vue'
import { uploadTeamDocument } from '@/components/events/teams/teamDocuments'

import type { EventTeamMemberRead, EventTeamRead, TeamRequirementRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * Ask to join a team that needs approval: what the team is, who to ask, what
 * they will check (with a file slot for each requirement that takes one), and
 * an optional note for whoever decides.
 *
 * The one request dialog, opened from the Teams page and in place from a
 * locked task or shift (`TeamJoinButton`). The request is a plain JSON call
 * and the files follow one upload each, so a failed upload never loses the
 * request — it can be attached again from the waiting team row.
 */
const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  eventId: string
  team: EventTeamRead
  /** Demo events take no files; the slots are replaced by a note. */
  sandbox?: boolean
  /** Stack above an already open dialog (a shift's detail). */
  priority?: boolean
}>()

const emit = defineEmits<{
  /** The request went out; `approved` if the team turned out to be open. */
  done: [status: 'approved' | 'pending']
}>()

const { t, locale } = useI18n()
const { post, getAuthToken } = useAuthenticatedClient()

const message = ref('')
const files = reactive<Record<string, File | null>>({})
const sending = ref(false)

const requirements = computed(() => props.team.requirements ?? [])
const takesFiles = computed(() => requirements.value.some((r) => r.accepts_document))
const noteId = computed(() => `team-join-note-${props.team.id}`)

const leadNames = computed(() => {
  const names = props.team.lead_names ?? []
  if (names.length === 0) return ''
  return new Intl.ListFormat(locale.value, { type: 'disjunction' }).format(names)
})

watch(open, (isOpen) => {
  if (!isOpen) return
  message.value = ''
  for (const key of Object.keys(files)) delete files[key]
})

function requirementDetail(r: TeamRequirementRead): string {
  const parts: string[] = []
  if (r.ask_issue_date) parts.push(t('teams.join.issueDate'))
  if (r.valid_for_years)
    parts.push(t('teams.join.validFor', { count: r.valid_for_years }, r.valid_for_years))
  return parts.join(' · ')
}

async function send() {
  if (sending.value) return
  sending.value = true
  let status: 'approved' | 'pending'
  try {
    const res = await post<{ data: EventTeamMemberRead }>({
      url: `/events/${props.eventId}/teams/${props.team.id}/join`,
      body: { message: message.value.trim() || null },
    })
    status = res.data?.status === 'approved' ? 'approved' : 'pending'
  } catch (error) {
    toastApiError(error)
    sending.value = false
    return
  }
  let uploadFailed = false
  const picked = Object.entries(files).filter((entry): entry is [string, File] => !!entry[1])
  if (status === 'pending' && picked.length > 0) {
    const token = await getAuthToken()
    for (const [requirementId, file] of picked) {
      try {
        await uploadTeamDocument(token, props.eventId, props.team.id, requirementId, file)
      } catch (error) {
        uploadFailed = true
        toastApiError(error, t('teams.join.uploadFailed'))
      }
    }
  }
  if (!uploadFailed) {
    toast.success(
      status === 'approved'
        ? t('teams.join.joined', { name: props.team.name })
        : t('teams.join.sent', { name: props.team.name }),
    )
  }
  sending.value = false
  open.value = false
  emit('done', status)
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent
      dialog-class="sm:max-w-lg"
      :priority="priority"
      data-testid="team-join-dialog"
    >
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>{{
          t('teams.join.title', { team: team.name })
        }}</ResponsiveDialogTitle>
        <ResponsiveDialogDescription>{{ t('teams.join.description') }}</ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <form class="contents" @submit.prevent="send">
        <ResponsiveDialogBody class="space-y-5 pb-4">
          <p v-if="team.description" class="text-sm whitespace-pre-line">
            {{ team.description }}
          </p>

          <p
            v-if="team.contact"
            class="text-muted-foreground flex items-center gap-2 text-sm"
            data-testid="team-join-contact"
          >
            <Phone class="size-3.5 shrink-0" aria-hidden="true" />
            {{ t('teams.join.contact', { contact: team.contact }) }}
          </p>

          <section
            v-if="requirements.length > 0"
            class="space-y-2"
            :aria-labelledby="`team-join-checks-${team.id}`"
            data-testid="team-join-checks"
          >
            <h3
              :id="`team-join-checks-${team.id}`"
              class="text-muted-foreground text-xs font-semibold tracking-wide uppercase"
            >
              {{ t('teams.join.requirementsTitle') }}
            </h3>
            <ul class="space-y-2">
              <li
                v-for="req in requirements"
                :key="req.id"
                class="space-y-2 rounded-md border p-3"
                :data-testid="`team-join-requirement-${req.id}`"
              >
                <div>
                  <p class="text-sm font-medium">{{ req.label }}</p>
                  <p v-if="req.description" class="text-muted-foreground text-xs">
                    {{ req.description }}
                  </p>
                  <p v-if="requirementDetail(req)" class="text-muted-foreground text-xs">
                    {{ requirementDetail(req) }}
                  </p>
                </div>
                <template v-if="req.accepts_document">
                  <p v-if="sandbox" class="text-muted-foreground text-xs">
                    {{ t('teams.join.noAttachDemo') }}
                  </p>
                  <TeamFileField
                    v-else
                    :filename="files[req.id]?.name"
                    :label="req.label"
                    :busy="sending"
                    :testid="`team-join-file-${req.id}`"
                    @choose="(file) => (files[req.id] = file)"
                    @remove="files[req.id] = null"
                  />
                </template>
                <p v-else class="text-muted-foreground flex items-start gap-1.5 text-xs">
                  <ShieldCheck class="mt-px size-3.5 shrink-0" aria-hidden="true" />
                  {{ t('teams.join.showDontSend') }}
                </p>
              </li>
            </ul>
            <p v-if="takesFiles && !sandbox" class="text-muted-foreground text-xs">
              {{ t('teams.join.attachHint') }}
            </p>
          </section>

          <div class="space-y-2">
            <Label :for="noteId">{{ t('teams.join.note') }}</Label>
            <Textarea
              :id="noteId"
              v-model="message"
              rows="3"
              maxlength="500"
              :placeholder="t('teams.join.notePlaceholder')"
              data-testid="team-join-note"
            />
          </div>

          <p class="text-muted-foreground text-sm">
            {{
              leadNames ? t('teams.join.afterNamed', { names: leadNames }) : t('teams.join.after')
            }}
          </p>
        </ResponsiveDialogBody>

        <ResponsiveDialogFooter>
          <Button type="button" variant="outline" :disabled="sending" @click="open = false">
            {{ t('common.dialog.confirm.cancelText') }}
          </Button>
          <Button type="submit" :disabled="sending" data-testid="btn-team-join-send">
            {{ t('teams.join.send') }}
          </Button>
        </ResponsiveDialogFooter>
      </form>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
