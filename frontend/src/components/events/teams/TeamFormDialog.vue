<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Plus, ShieldCheck, Trash2, UsersRound } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import Input from '@/components/ui/input/Input.vue'
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
import Switch from '@/components/ui/switch/Switch.vue'
import { Textarea } from '@/components/ui/textarea'

import {
  MAX_REQUIREMENTS,
  REQUIREMENT_PRESETS,
  type RequirementDraft,
  type RequirementPresetKey,
  draftFromRequirement,
  draftToPayload,
  labelKey,
  newDraft,
} from '@/components/events/teams/teamHelpers'

import type { EventTeamRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  eventId: string
  /** Edit this team instead of creating one. */
  team?: EventTeamRead | null
}>()

const emit = defineEmits<{ saved: [team: EventTeamRead] }>()

const { t } = useI18n()
const { post, patch } = useAuthenticatedClient()

const name = ref('')
const description = ref('')
const contact = ref('')
const requiresApproval = ref(true)
const requirements = ref<RequirementDraft[]>([])
const saving = ref(false)

const isEdit = computed(() => !!props.team)
/** Checks only make sense when someone decides, so they pin approval on. */
const approvalLocked = computed(() => requirements.value.length > 0)
const atLimit = computed(() => requirements.value.length >= MAX_REQUIREMENTS)

watch(open, (isOpen) => {
  if (!isOpen) return
  name.value = props.team?.name ?? ''
  description.value = props.team?.description ?? ''
  contact.value = props.team?.contact ?? ''
  requiresApproval.value = props.team?.requires_approval ?? true
  requirements.value = (props.team?.requirements ?? []).map(draftFromRequirement)
})

function presetLabel(key: RequirementPresetKey): string {
  return t(`teams.presets.${key}.label`)
}

function presetTaken(key: RequirementPresetKey): boolean {
  const wanted = labelKey(presetLabel(key))
  return requirements.value.some((r) => labelKey(r.label) === wanted)
}

function addPreset(key: RequirementPresetKey) {
  const preset = REQUIREMENT_PRESETS.find((p) => p.key === key)!
  requirements.value.push(
    newDraft({
      label: presetLabel(key),
      description: t(`teams.presets.${key}.description`),
      ask_issue_date: preset.ask_issue_date,
      valid_for_years: preset.valid_for_years,
      accepts_document: preset.accepts_document,
    }),
  )
  requiresApproval.value = true
}

function addCustom() {
  requirements.value.push(newDraft())
  requiresApproval.value = true
}

function removeRequirement(draft: RequirementDraft) {
  requirements.value = requirements.value.filter((r) => r.key !== draft.key)
}

function setYears(draft: RequirementDraft, value: string | number) {
  const n = typeof value === 'number' ? value : Number.parseInt(value, 10)
  draft.valid_for_years = Number.isFinite(n) && n > 0 ? Math.min(n, 50) : null
}

async function save() {
  if (!name.value.trim()) {
    toast.error(t('teams.form.nameRequired'))
    return
  }
  if (requirements.value.some((r) => !r.label.trim())) {
    toast.error(t('teams.form.labelRequired'))
    return
  }
  const labels = requirements.value.map((r) => labelKey(r.label))
  if (new Set(labels).size !== labels.length) {
    toast.error(t('teams.form.labelDuplicate'))
    return
  }
  saving.value = true
  try {
    const body = {
      name: name.value.trim(),
      description: description.value.trim() || null,
      contact: contact.value.trim() || null,
      requires_approval: requiresApproval.value || approvalLocked.value,
      requirements: requirements.value.map(draftToPayload),
    }
    let saved: { data: EventTeamRead }
    if (props.team) {
      saved = await patch<{ data: EventTeamRead }>({
        url: `/events/${props.eventId}/teams/${props.team.id}`,
        body,
      })
      toast.success(t('teams.form.updated'))
    } else {
      saved = await post<{ data: EventTeamRead }>({ url: `/events/${props.eventId}/teams`, body })
      toast.success(t('teams.form.created'))
    }
    open.value = false
    emit('saved', saved.data)
  } catch (error) {
    toastApiError(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent dialog-class="sm:max-w-xl" data-testid="team-form-dialog">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle class="flex items-center gap-2">
          <UsersRound class="h-5 w-5" />
          {{ isEdit ? t('teams.form.editTitle') : t('teams.form.createTitle') }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="text-left">
          {{ t('teams.form.description') }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="space-y-4 pb-2">
        <div class="space-y-2">
          <Label for="team-name">{{ t('teams.form.name') }}</Label>
          <Input
            id="team-name"
            v-model="name"
            maxlength="100"
            :placeholder="t('teams.form.namePlaceholder')"
            data-testid="team-name"
          />
        </div>
        <div class="space-y-2">
          <Label for="team-description">{{ t('teams.form.about') }}</Label>
          <Textarea
            id="team-description"
            v-model="description"
            maxlength="2000"
            rows="3"
            :placeholder="t('teams.form.aboutPlaceholder')"
            data-testid="team-description"
          />
        </div>
        <div class="space-y-2">
          <Label for="team-contact">{{ t('teams.form.contact') }}</Label>
          <Input
            id="team-contact"
            v-model="contact"
            maxlength="255"
            :placeholder="t('teams.form.contactPlaceholder')"
            data-testid="team-contact"
          />
        </div>
        <div class="flex items-start justify-between gap-4 rounded-md border p-3">
          <div class="space-y-1">
            <Label for="team-requires-approval">{{ t('teams.form.requiresApproval') }}</Label>
            <p class="text-xs text-muted-foreground">
              {{
                approvalLocked
                  ? t('teams.form.requirementsNeedApproval')
                  : requiresApproval
                    ? t('teams.form.requiresApprovalOn')
                    : t('teams.form.requiresApprovalOff')
              }}
            </p>
          </div>
          <Switch
            id="team-requires-approval"
            :model-value="requiresApproval || approvalLocked"
            :disabled="approvalLocked"
            data-testid="team-requires-approval"
            @update:model-value="(v: boolean) => (requiresApproval = v)"
          />
        </div>

        <section class="space-y-3" aria-labelledby="team-requirements-title">
          <div class="space-y-1">
            <h3 id="team-requirements-title" class="text-sm font-medium">
              {{ t('teams.form.requirementsTitle') }}
            </h3>
            <p class="text-xs text-muted-foreground">{{ t('teams.form.requirementsHint') }}</p>
          </div>

          <div
            v-for="(draft, index) in requirements"
            :key="draft.key"
            class="space-y-3 rounded-md border p-3"
            :data-testid="`team-requirement-${index}`"
          >
            <div class="flex items-start gap-2">
              <div class="min-w-0 flex-1 space-y-2">
                <Label :for="`team-req-label-${draft.key}`" class="text-xs">
                  {{ t('teams.form.requirementLabel') }}
                </Label>
                <Input
                  :id="`team-req-label-${draft.key}`"
                  v-model="draft.label"
                  maxlength="200"
                  :placeholder="t('teams.form.requirementLabelPlaceholder')"
                  :data-testid="`team-requirement-label-${index}`"
                />
              </div>
              <Button
                variant="ghost"
                size="icon"
                class="mt-6 size-8 shrink-0 text-muted-foreground hover:text-destructive"
                :aria-label="
                  t('teams.form.removeRequirement', {
                    label: draft.label || t('teams.form.requirementUnnamed'),
                  })
                "
                :data-testid="`btn-remove-requirement-${index}`"
                @click="removeRequirement(draft)"
              >
                <Trash2 class="size-4" />
              </Button>
            </div>
            <div class="space-y-2">
              <Label :for="`team-req-note-${draft.key}`" class="text-xs">
                {{ t('teams.form.requirementDescription') }}
              </Label>
              <Input
                :id="`team-req-note-${draft.key}`"
                v-model="draft.description"
                maxlength="2000"
              />
            </div>
            <div class="grid gap-3 sm:grid-cols-2">
              <div class="flex items-center justify-between gap-3">
                <Label :for="`team-req-date-${draft.key}`" class="text-xs font-normal">
                  {{ t('teams.form.askIssueDate') }}
                </Label>
                <Switch
                  :id="`team-req-date-${draft.key}`"
                  :model-value="draft.ask_issue_date"
                  @update:model-value="(v: boolean) => (draft.ask_issue_date = v)"
                />
              </div>
              <div class="flex items-center justify-between gap-3">
                <Label :for="`team-req-file-${draft.key}`" class="text-xs font-normal">
                  {{ t('teams.form.acceptsDocument') }}
                </Label>
                <Switch
                  :id="`team-req-file-${draft.key}`"
                  :model-value="draft.accepts_document"
                  @update:model-value="(v: boolean) => (draft.accepts_document = v)"
                />
              </div>
            </div>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Label :for="`team-req-years-${draft.key}`" class="text-xs font-normal">
                {{ t('teams.form.validFor') }}
              </Label>
              <Input
                :id="`team-req-years-${draft.key}`"
                type="number"
                min="1"
                max="50"
                inputmode="numeric"
                class="h-8 w-20"
                :model-value="draft.valid_for_years ?? ''"
                @update:model-value="(v) => setYears(draft, v)"
              />
              <span class="text-xs text-muted-foreground">{{ t('teams.form.validForHint') }}</span>
            </div>
            <p
              v-if="!draft.accepts_document"
              class="flex items-start gap-1.5 text-xs text-muted-foreground"
            >
              <ShieldCheck class="mt-px size-3.5 shrink-0" />
              {{ t('teams.form.noCopyNote') }}
            </p>
          </div>

          <p v-if="atLimit" class="text-xs text-muted-foreground">
            {{ t('teams.form.maxRequirements', { count: MAX_REQUIREMENTS }) }}
          </p>
          <div v-else class="flex flex-wrap gap-2">
            <Button
              v-for="preset in REQUIREMENT_PRESETS"
              :key="preset.key"
              variant="outline"
              size="sm"
              :disabled="presetTaken(preset.key)"
              :data-testid="`btn-add-preset-${preset.key}`"
              @click="addPreset(preset.key)"
            >
              <Plus class="mr-1 size-3.5" />
              {{ presetLabel(preset.key) }}
            </Button>
            <Button
              variant="outline"
              size="sm"
              data-testid="btn-add-requirement"
              @click="addCustom"
            >
              <Plus class="mr-1 size-3.5" />
              {{ t('teams.form.custom') }}
            </Button>
          </div>
        </section>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter>
        <Button variant="outline" @click="open = false">
          {{ t('common.dialog.confirm.cancelText') }}
        </Button>
        <Button :disabled="saving" data-testid="btn-save-team" @click="save">
          {{ t('teams.form.save') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
