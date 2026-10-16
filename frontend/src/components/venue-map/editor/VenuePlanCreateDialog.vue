<script setup lang="ts">
import { type ComponentPublicInstance, computed, ref, shallowReactive, watch } from 'vue'

import { EllipsisVertical, ImageUp, LayoutTemplate, Pencil, PencilRuler, Trash2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useDialog } from '@/composables/useDialog'
import { forgetTemplateShapes, useVenueTemplates } from '@/composables/useVenueTemplates'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import { Skeleton } from '@/components/ui/skeleton'

import HintTooltip from '@/components/utils/HintTooltip.vue'
import VenueTemplateNameDialog from '@/components/venue-map/editor/VenueTemplateNameDialog.vue'
import VenueTemplateThumb from '@/components/venue-map/editor/VenueTemplateThumb.vue'

import type { VenuePlanCreate, VenueTemplateSummary } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

export type PlanCreateMode = 'blank' | 'picture' | 'template'
export type PlanAspect = NonNullable<VenuePlanCreate['canvas']>
export type PlanCreateValue = {
  name: string
  mode: PlanCreateMode
  canvas: PlanAspect
  /** Set with `mode: 'template'`: the template to copy the drawing from. */
  templateId: string | null
}

/**
 * "New map": a name, and whether to draw the map here (on a blank area in
 * landscape, portrait or square), to start from a picture, or to start from
 * one of my templates (a copy of its drawing and picture; pins come after).
 * The aspect of a drawn map cannot change later — it would distort the
 * drawing — so it is asked here. In the demo pictures cannot be uploaded, so
 * that choice is disabled with a short reason.
 *
 * The template list is also where my templates are managed: each card has a
 * menu to rename or delete it.
 */
const props = defineProps<{
  sandbox?: boolean
  saving?: boolean
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  submit: [value: PlanCreateValue]
}>()

const { t } = useI18n()
const { confirmDestructive } = useDialog()
const venueTemplates = useVenueTemplates()
const { templates, loading: templatesLoading, loadError: templatesError } = venueTemplates

const name = ref('')
const mode = ref<PlanCreateMode>('blank')
const canvas = ref<PlanAspect>('landscape')
const ASPECTS: { value: PlanAspect; w: number; h: number }[] = [
  { value: 'landscape', w: 16, h: 10 },
  { value: 'portrait', w: 10, h: 16 },
  { value: 'square', w: 12, h: 12 },
]

const templateId = ref<string | null>(null)
/** The name a template pick filled in, so the next pick may replace it. */
let autoName = ''

watch(open, (isOpen) => {
  if (!isOpen) return
  name.value = ''
  mode.value = 'blank'
  canvas.value = 'landscape'
  templateId.value = null
  autoName = ''
  void venueTemplates.load()
})

const trimmed = computed(() => name.value.trim())
const canSubmit = computed(
  () => !!trimmed.value && !props.saving && (mode.value !== 'template' || !!templateId.value),
)

function pickTemplate(template: VenueTemplateSummary) {
  templateId.value = template.id
  // Name the new map after the template, unless a name was typed already.
  if (!trimmed.value || name.value === autoName) {
    name.value = template.name
    autoName = template.name
  }
}

function submit() {
  if (!canSubmit.value) return
  const chosen = props.sandbox && mode.value === 'picture' ? 'blank' : mode.value
  emit('submit', {
    name: trimmed.value,
    mode: chosen,
    canvas: canvas.value,
    templateId: chosen === 'template' ? templateId.value : null,
  })
}

/**
 * The template picked for "Start from a template" no longer exists (deleted
 * in another tab, say): drop the pick and reload the list, so a retry is not
 * the same dead end.
 */
function templateGone(id: string) {
  if (templateId.value === id) templateId.value = null
  forgetTemplateShapes(id)
  void venueTemplates.load()
}

defineExpose({ templateGone })

// ── Managing my templates ───────────────────────────────────────────────
const renaming = ref<VenueTemplateSummary | null>(null)
const renameOpen = ref(false)
const savingRename = ref(false)

function openRename(template: VenueTemplateSummary) {
  renaming.value = template
  renameOpen.value = true
}

async function submitRename(newName: string) {
  const template = renaming.value
  if (!template || savingRename.value) return
  savingRename.value = true
  try {
    await venueTemplates.rename(template.id, newName)
    if (templateId.value === template.id && name.value === autoName) {
      name.value = newName
      autoName = newName
    }
    toast.success(t('mapEditor.templates.renamed'))
    renameOpen.value = false
  } catch (error) {
    toastApiError(error)
  } finally {
    savingRename.value = false
  }
}

async function deleteTemplate(template: VenueTemplateSummary) {
  const confirmed = await confirmDestructive({
    text: t('mapEditor.templates.deleteConfirm', { name: template.name }),
    confirmText: t('common.actions.delete'),
  })
  if (!confirmed) return
  try {
    await venueTemplates.remove(template.id)
    if (templateId.value === template.id) templateId.value = null
    toast.success(t('mapEditor.templates.deleted'))
  } catch (error) {
    toastApiError(error)
  }
}

// The menu trigger sits inside a HintTooltip, so it anchors to the tooltip,
// not to its own menu: the menu content is told where each button is, or it
// opens off-screen (reka-ui finds an anchor through the nearest popup root).
const actionButtons = shallowReactive(new Map<string, Element>())
function setActionButton(id: string, el: Element | ComponentPublicInstance | null) {
  const node = el && '$el' in el ? (el.$el as Element) : el
  if (node) actionButtons.set(id, node)
  else actionButtons.delete(id)
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent>
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>{{ t('mapEditor.create.title') }}</ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="sr-only">
          {{ t('mapEditor.create.description') }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>
      <ResponsiveDialogBody class="pb-2">
        <form id="map-editor-plan-create" class="space-y-4" @submit.prevent="submit">
          <div class="space-y-1.5">
            <Label for="map-editor-plan-create-name">{{ t('mapEditor.create.name') }}</Label>
            <Input
              id="map-editor-plan-create-name"
              v-model="name"
              maxlength="120"
              :placeholder="t('mapEditor.plans.namePlaceholder')"
              data-testid="plan-name-input"
            />
          </div>

          <div class="space-y-2" role="radiogroup" :aria-label="t('mapEditor.create.title')">
            <label
              class="has-[:checked]:border-primary has-[:checked]:bg-primary/5 flex cursor-pointer gap-3 rounded-lg border p-3"
              data-testid="plan-create-blank"
            >
              <input
                v-model="mode"
                type="radio"
                name="map-editor-plan-mode"
                value="blank"
                class="accent-primary mt-1"
              />
              <PencilRuler
                class="text-muted-foreground mt-0.5 size-5 shrink-0"
                aria-hidden="true"
              />
              <span class="min-w-0 space-y-1">
                <span class="block font-medium">{{ t('mapEditor.create.blank') }}</span>
                <span class="text-muted-foreground block text-sm">
                  {{ t('mapEditor.create.blankHint') }}
                </span>
              </span>
            </label>

            <div v-if="mode === 'blank'" class="space-y-1.5 pl-1">
              <p id="map-editor-plan-aspect" class="text-sm font-medium">
                {{ t('mapEditor.create.aspectLabel') }}
              </p>
              <div
                class="flex flex-wrap gap-2"
                role="radiogroup"
                aria-labelledby="map-editor-plan-aspect"
              >
                <label
                  v-for="aspect in ASPECTS"
                  :key="aspect.value"
                  class="has-[:checked]:border-primary has-[:checked]:bg-primary/10 has-[:focus-visible]:ring-ring/50 flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm has-[:focus-visible]:ring-[3px]"
                  :data-testid="`plan-aspect-${aspect.value}`"
                >
                  <input
                    v-model="canvas"
                    type="radio"
                    name="map-editor-plan-aspect"
                    :value="aspect.value"
                    class="sr-only"
                  />
                  <span
                    class="border-foreground/60 inline-block rounded-[2px] border-2"
                    :style="{ width: `${aspect.w}px`, height: `${aspect.h}px` }"
                    aria-hidden="true"
                  />
                  {{ t(`mapEditor.create.aspect.${aspect.value}`) }}
                </label>
              </div>
            </div>

            <label
              class="has-[:checked]:border-primary has-[:checked]:bg-primary/5 flex cursor-pointer gap-3 rounded-lg border p-3"
              data-testid="plan-create-template"
            >
              <input
                v-model="mode"
                type="radio"
                name="map-editor-plan-mode"
                value="template"
                class="accent-primary mt-1"
              />
              <LayoutTemplate
                class="text-muted-foreground mt-0.5 size-5 shrink-0"
                aria-hidden="true"
              />
              <span class="min-w-0 space-y-1">
                <span class="block font-medium">{{ t('mapEditor.create.template') }}</span>
                <span class="text-muted-foreground block text-sm">
                  {{ t('mapEditor.create.templateHint') }}
                </span>
              </span>
            </label>

            <div v-if="mode === 'template'" class="space-y-1.5 pl-1" data-testid="template-list">
              <p id="map-editor-plan-template" class="text-sm font-medium">
                {{ t('mapEditor.templates.pickLabel') }}
              </p>
              <div
                v-if="templatesLoading && templates.length === 0"
                class="grid grid-cols-2 gap-2 sm:grid-cols-3"
              >
                <Skeleton v-for="n in 2" :key="n" class="aspect-[4/3] w-full" />
              </div>
              <div
                v-else-if="templatesError"
                class="flex flex-wrap items-center gap-2 rounded-md border border-dashed p-3 text-sm"
                role="alert"
                data-testid="template-list-error"
              >
                <span class="text-muted-foreground min-w-0 flex-1">
                  {{ t('mapEditor.templates.loadError') }}
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  data-testid="template-list-retry"
                  @click="venueTemplates.load()"
                >
                  {{ t('venueMap.view.retry') }}
                </Button>
              </div>
              <div
                v-else-if="templates.length === 0"
                class="space-y-1 rounded-md border border-dashed p-3 text-sm"
                data-testid="template-list-empty"
              >
                <p class="font-medium">{{ t('mapEditor.templates.empty') }}</p>
                <p class="text-muted-foreground">{{ t('mapEditor.templates.emptyHint') }}</p>
              </div>
              <div
                v-else
                class="grid grid-cols-2 gap-2 sm:grid-cols-3"
                role="radiogroup"
                aria-labelledby="map-editor-plan-template"
              >
                <div
                  v-for="template in templates"
                  :key="template.id"
                  class="relative"
                  :data-testid="`template-card-${template.id}`"
                >
                  <label
                    class="has-[:checked]:border-primary has-[:checked]:bg-primary/5 has-[:focus-visible]:ring-ring/50 flex h-full cursor-pointer flex-col gap-1.5 rounded-lg border p-1.5 has-[:focus-visible]:ring-[3px]"
                  >
                    <input
                      type="radio"
                      name="map-editor-plan-template"
                      :value="template.id"
                      :checked="templateId === template.id"
                      class="sr-only"
                      data-testid="template-pick"
                      @change="pickTemplate(template)"
                    />
                    <VenueTemplateThumb :template="template" />
                    <span
                      class="line-clamp-2 min-h-8 pr-8 text-sm leading-4 font-medium break-words"
                    >
                      {{ template.name }}
                    </span>
                  </label>
                  <DropdownMenu>
                    <HintTooltip :label="t('mapEditor.templates.actions', { name: template.name })">
                      <DropdownMenuTrigger as-child>
                        <Button
                          :ref="(el) => setActionButton(template.id, el)"
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          class="absolute right-1 bottom-1"
                          :aria-label="t('mapEditor.templates.actions', { name: template.name })"
                          data-testid="template-actions"
                        >
                          <EllipsisVertical />
                        </Button>
                      </DropdownMenuTrigger>
                    </HintTooltip>
                    <DropdownMenuContent align="end" :reference="actionButtons.get(template.id)">
                      <DropdownMenuItem
                        data-testid="template-rename"
                        @select="openRename(template)"
                      >
                        <Pencil />
                        {{ t('mapEditor.templates.rename') }}
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        variant="destructive"
                        data-testid="template-delete"
                        @select="deleteTemplate(template)"
                      >
                        <Trash2 />
                        {{ t('mapEditor.templates.delete') }}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            </div>

            <label
              class="flex gap-3 rounded-lg border p-3"
              :class="
                sandbox
                  ? 'cursor-not-allowed opacity-70'
                  : 'has-[:checked]:border-primary has-[:checked]:bg-primary/5 cursor-pointer'
              "
              data-testid="plan-create-picture"
            >
              <input
                v-model="mode"
                type="radio"
                name="map-editor-plan-mode"
                value="picture"
                class="accent-primary mt-1"
                :disabled="sandbox"
              />
              <ImageUp class="text-muted-foreground mt-0.5 size-5 shrink-0" aria-hidden="true" />
              <span class="min-w-0 space-y-1">
                <span class="block font-medium">{{ t('mapEditor.create.picture') }}</span>
                <span class="text-muted-foreground block text-sm">
                  {{
                    sandbox
                      ? t('mapEditor.create.pictureSandbox')
                      : t('mapEditor.create.pictureHint')
                  }}
                </span>
              </span>
            </label>
          </div>
        </form>
      </ResponsiveDialogBody>
      <ResponsiveDialogFooter>
        <Button variant="outline" @click="open = false">
          {{ t('common.actions.cancel') }}
        </Button>
        <Button
          type="submit"
          form="map-editor-plan-create"
          :disabled="!canSubmit"
          data-testid="plan-name-save"
        >
          {{ t('mapEditor.create.submit') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>

  <VenueTemplateNameDialog
    v-model:open="renameOpen"
    :title="t('mapEditor.templates.renameTitle')"
    :description="t('mapEditor.templates.renameDescription')"
    :submit-label="t('common.actions.save')"
    :initial-name="renaming?.name ?? ''"
    :saving="savingRename"
    priority
    @submit="submitRename"
  />
</template>
