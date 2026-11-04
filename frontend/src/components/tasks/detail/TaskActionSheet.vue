<script lang="ts">
import type { Component } from 'vue'

export interface TaskSheetAction {
  key: string
  label: string
  icon: Component
  destructive?: boolean
  testid?: string
}
</script>

<script setup lang="ts">
import { nextTick, watch } from 'vue'

import { useI18n } from 'vue-i18n'

import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer'

/**
 * A phone action sheet: a short list of full-width rows over the page, with
 * "Cancel" underneath, as the task page's ⋯ menu and "Add shifts" open on a
 * phone. Picking a row closes the sheet first and then reports the row, so a
 * dialog the row opens never has to fight the closing sheet for focus.
 */
defineProps<{
  title: string
  /** Read out only; the sheet shows the title alone. */
  description?: string
  actions: TaskSheetAction[]
  testid?: string
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ select: [key: string] }>()

const { t } = useI18n()

/** The button that opened the sheet (the page's ⋯), noted as the sheet opens. */
let opener: HTMLElement | null = null
watch(open, (isOpen) => {
  if (!isOpen) return
  const active = document.activeElement
  opener = active instanceof HTMLElement && active !== document.body ? active : null
})

/**
 * A row's dialog opens while the sheet is still sliding away, and remembers
 * whatever has focus then to give it back on close. That would be the row,
 * gone by then, so the sheet's button takes focus first: once the sheet is
 * closing it no longer holds on to focus.
 */
async function pick(key: string) {
  open.value = false
  await nextTick()
  if (opener?.isConnected) opener.focus({ preventScroll: true })
  emit('select', key)
}
</script>

<template>
  <Drawer v-model:open="open">
    <DrawerContent :data-testid="testid">
      <DrawerHeader class="px-4 pt-3 pb-1 text-left">
        <DrawerTitle
          class="truncate text-[13px] font-bold tracking-[0.05em] text-muted-foreground uppercase"
        >
          {{ title }}
        </DrawerTitle>
        <DrawerDescription class="sr-only">{{ description ?? title }}</DrawerDescription>
      </DrawerHeader>
      <div class="px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
        <div class="flex flex-col">
          <button
            v-for="(action, index) in actions"
            :key="action.key"
            type="button"
            :data-testid="action.testid"
            class="flex min-h-[54px] items-center gap-3.5 px-1 text-left text-base outline-none focus-visible:bg-accent"
            :class="[
              index < actions.length - 1 ? 'border-b' : '',
              action.destructive ? 'text-destructive' : '',
            ]"
            @click="pick(action.key)"
          >
            <component
              :is="action.icon"
              class="size-5 shrink-0"
              :class="action.destructive ? '' : 'text-muted-foreground'"
              aria-hidden="true"
            />
            {{ action.label }}
          </button>
        </div>
        <button
          type="button"
          class="mt-3 min-h-[50px] w-full rounded-xl border bg-card text-base font-semibold outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          @click="open = false"
        >
          {{ t('common.actions.cancel') }}
        </button>
      </div>
    </DrawerContent>
  </Drawer>
</template>
