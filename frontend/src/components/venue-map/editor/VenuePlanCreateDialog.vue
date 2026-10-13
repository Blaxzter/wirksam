<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { ImageUp, PencilRuler } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
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

import type { VenuePlanCreate } from '@/client/types.gen'

export type PlanCreateMode = 'blank' | 'picture'
export type PlanAspect = NonNullable<VenuePlanCreate['canvas']>

/**
 * "New map": a name, and whether to draw the map here (on a blank area in
 * landscape, portrait or square) or to start from a picture. The aspect of a
 * drawn map cannot change later — it would distort the drawing — so it is
 * asked here. In the demo pictures cannot be uploaded, so that choice is
 * disabled with a short reason.
 */
const props = defineProps<{
  sandbox?: boolean
  saving?: boolean
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  submit: [value: { name: string; mode: PlanCreateMode; canvas: PlanAspect }]
}>()

const { t } = useI18n()

const name = ref('')
const mode = ref<PlanCreateMode>('blank')
const canvas = ref<PlanAspect>('landscape')
const ASPECTS: { value: PlanAspect; w: number; h: number }[] = [
  { value: 'landscape', w: 16, h: 10 },
  { value: 'portrait', w: 10, h: 16 },
  { value: 'square', w: 12, h: 12 },
]

watch(open, (isOpen) => {
  if (!isOpen) return
  name.value = ''
  mode.value = 'blank'
  canvas.value = 'landscape'
})

const trimmed = computed(() => name.value.trim())

function submit() {
  if (!trimmed.value || props.saving) return
  emit('submit', {
    name: trimmed.value,
    mode: props.sandbox ? 'blank' : mode.value,
    canvas: canvas.value,
  })
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
          :disabled="!trimmed || saving"
          data-testid="plan-name-save"
        >
          {{ t('mapEditor.create.submit') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
