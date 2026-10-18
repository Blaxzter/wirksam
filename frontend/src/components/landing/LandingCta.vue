<script setup lang="ts">
import { ArrowRightIcon, FlaskConicalIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import LandingSection from './LandingSection.vue'
import SectionHeading from './SectionHeading.vue'

defineProps<{
  isAuthenticated: boolean
  /** Whether the deployment offers demo sessions at all — see `stores/sandbox.ts`. */
  demoEnabled: boolean
  /** A content page's own heading; the landing page's otherwise. */
  title?: string
}>()
const emit = defineEmits<{ signIn: []; dashboard: []; demo: [] }>()

const { t } = useI18n()
</script>

<template>
  <LandingSection id="get-started" tone="hero">
    <SectionHeading
      tone="hero"
      :eyebrow="t('preauth.landing.finalCta.eyebrow')"
      :title="title ?? t('preauth.landing.finalCta.title')"
      :lede="t('preauth.landing.finalCta.lede')"
    />

    <div class="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
      <!-- `secondary` is a dark grey in dark mode, which vanishes against the
           green band. Invert the hero tokens instead so the button reads in
           both palettes and both modes. -->
      <Button
        data-testid="btn-cta-footer"
        size="lg"
        class="w-full gap-2 bg-hero-foreground text-hero hover:bg-hero-foreground/90 sm:w-auto"
        @click="isAuthenticated ? emit('dashboard') : emit('signIn')"
      >
        {{
          isAuthenticated
            ? t('preauth.layout.navigation.goToDashboard')
            : t('preauth.landing.finalCta.button')
        }}
        <ArrowRightIcon class="size-4" />
      </Button>

      <!-- Same reasoning, one step quieter: `outline` would paint itself
           `bg-card` and carries `dark:` overrides that outrank anything set
           here, so this stays on the default variant and repaints every colour
           from the hero tokens. -->
      <Button
        v-if="demoEnabled"
        data-testid="btn-cta-demo-footer"
        size="lg"
        class="w-full gap-2 border border-hero-foreground/40 bg-transparent text-hero-foreground hover:bg-hero-foreground/10 sm:w-auto"
        @click="emit('demo')"
      >
        <FlaskConicalIcon class="size-4" />
        {{ t('preauth.landing.finalCta.demoButton') }}
      </Button>
    </div>
  </LandingSection>
</template>
