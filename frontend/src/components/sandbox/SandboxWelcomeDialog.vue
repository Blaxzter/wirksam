<script setup lang="ts">
import { computed } from 'vue'

import { ClipboardListIcon, CompassIcon, HandHeartIcon, SparklesIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import { declineTour, offeredTrack, requestTour } from '@/tour/offer'

/**
 * The first thing a demo visitor sees, and the place the tour is *asked for*.
 *
 * It replaces a tour that started on its own over a step that highlighted the
 * page heading — a word the visitor could already read, under a card that
 * greeted them. Two things were wrong with that at once: the highlight pointed
 * at nothing worth pointing at, and nobody had agreed to be guided. So the
 * greeting is a plain dialog now, it says what the demo is and that none of it
 * survives, and it offers a choice with a real second answer.
 *
 * Mounted in `App.vue` beside `SandboxBanner`, for the same reason: it must
 * outlive the layout underneath it, and it is opened by a router hook
 * (`tour/install.ts`) that is nowhere near a component.
 *
 * Nothing here imports the tour engine. `tour/offer.ts` is the whole contract:
 * a ref to read, and a window event to dispatch on the way out.
 */

const { t } = useI18n()

const open = computed(() => offeredTrack.value !== null)

/**
 * Which half of the product the visitor is being welcomed into.
 *
 * Read off the offer rather than the sandbox store so the copy and the tour
 * cannot disagree: whatever track is about to run is the one being described.
 * The fallback only covers the closing frame, where `offeredTrack` has already
 * been cleared and the dialog is still animating out.
 */
const track = computed(() => offeredTrack.value ?? 'helper')

const roleIcon = computed(() => (track.value === 'manager' ? ClipboardListIcon : HandHeartIcon))

function accept() {
  requestTour(track.value)
}

/**
 * Escape, the backdrop and the "I'll look around myself" button all land here.
 *
 * Every one of them is the same answer — no tour — and none of them is a
 * mistake worth guarding against: the banner's "restart the tour" is one click
 * away for as long as the demo lasts.
 */
function decline() {
  declineTour()
}
</script>

<template>
  <ResponsiveDialog :open="open" @update:open="!$event && decline()">
    <ResponsiveDialogContent data-testid="dialog-sandbox-welcome" dialog-class="sm:max-w-lg">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle class="flex items-center gap-2">
          <component :is="roleIcon" aria-hidden="true" class="size-5 shrink-0 text-primary" />
          {{ t('sandbox.welcome.title') }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="text-left">
          {{ t(`sandbox.welcome.${track}.body`) }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="pb-2">
        <p class="rounded-lg border bg-muted/40 p-3 text-sm text-muted-foreground">
          {{ t('sandbox.welcome.playground') }}
        </p>

        <p class="mt-4 text-sm font-medium">{{ t('sandbox.welcome.question') }}</p>
      </ResponsiveDialogBody>

      <!--
        Decline first in the markup: the footer stacks `flex-col-reverse` on a
        phone, so the offer this dialog is making stays the top button there and
        the right-hand one on a desktop.
      -->
      <ResponsiveDialogFooter>
        <Button data-testid="btn-tour-decline" variant="outline" @click="decline">
          <CompassIcon class="size-4" />
          {{ t('sandbox.welcome.explore') }}
        </Button>
        <Button data-testid="btn-tour-accept" @click="accept">
          <SparklesIcon class="size-4" />
          {{ t('sandbox.welcome.tour') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
