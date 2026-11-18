<script setup lang="ts">
/**
 * "Demo" in the header of a demo's list, and of the page of whoever signed up
 * through one: a pill that opens the full note. It sits out of the way of the
 * shifts, yet in view on every step, so that whatever a visitor wrote into the
 * list's heading, the page cannot pass for a real one. The note says that
 * nothing is mailed and that every sign-up goes with the demo.
 *
 * Teleported into `GuestLayout`'s header slot.
 */
import { FlaskConicalIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

const { t } = useI18n()
</script>

<template>
  <Teleport defer to="#guest-header-slot">
    <Popover>
      <PopoverTrigger as-child>
        <button
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-full border border-dashed border-primary/60 bg-primary/10 px-3 text-xs font-semibold text-primary outline-none hover:bg-primary/15 focus-visible:ring-[3px] focus-visible:ring-ring/50"
          data-testid="guest-demo-notice"
        >
          <FlaskConicalIcon class="size-3.5" aria-hidden="true" />
          {{ t('guestSignup.demo.badge') }}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" class="w-72 text-sm" data-testid="guest-demo-notice-text">
        <p class="font-semibold">{{ t('guestSignup.demo.title') }}</p>
        <p class="mt-1 text-muted-foreground">{{ t('guestSignup.demo.text') }}</p>
      </PopoverContent>
    </Popover>
  </Teleport>
</template>
