<script setup lang="ts">
import { type Component, ref } from 'vue'

import {
  BellIcon,
  CalendarClockIcon,
  CalendarPlusIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClipboardListIcon,
  HandHeartIcon,
  MailOpenIcon,
  SendIcon,
  UserPlusIcon,
  WandSparklesIcon,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

import LandingSection from './LandingSection.vue'
import SectionHeading from './SectionHeading.vue'

const { t } = useI18n()

/**
 * Both journeys, four steps each, drawn as a chain: a raised icon bubble feeds
 * into the card that explains it, and an arrow carries you to the next pair.
 *
 * The chain runs left to right from `xl`, where there is room for four pairs,
 * and folds into a vertical one below that. The connectors are decorative — the
 * order is already carried by the `<ol>`.
 */
const tracks: { key: string; icon: Component; steps: { key: string; icon: Component }[] }[] = [
  {
    key: 'organiser',
    icon: ClipboardListIcon,
    steps: [
      { key: 'create', icon: CalendarPlusIcon },
      { key: 'invite', icon: UserPlusIcon },
      { key: 'generate', icon: WandSparklesIcon },
      { key: 'publish', icon: SendIcon },
    ],
  },
  {
    key: 'volunteer',
    icon: HandHeartIcon,
    steps: [
      { key: 'accept', icon: MailOpenIcon },
      { key: 'availability', icon: CalendarClockIcon },
      { key: 'book', icon: HandHeartIcon },
      { key: 'reminders', icon: BellIcon },
    ],
  },
]

const track = ref<string>('organiser')
</script>

<template>
  <LandingSection id="how-it-works" width="full">
    <SectionHeading
      :eyebrow="t('preauth.landing.journey.eyebrow')"
      :title="t('preauth.landing.journey.title')"
      :lede="t('preauth.landing.journey.lede')"
    />

    <Tabs v-model="track" class="mt-10 items-center gap-10">
      <!-- Segmented control: one pill, two halves, active side filled. -->
      <TabsList class="h-auto gap-1 rounded-full border bg-muted/60 p-1.5">
        <TabsTrigger
          v-for="item in tracks"
          :key="item.key"
          :value="item.key"
          class="gap-2 rounded-full px-5 py-2 text-sm font-medium text-muted-foreground transition-colors data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm"
        >
          <component :is="item.icon" class="size-4" aria-hidden="true" />
          {{ t(`preauth.landing.journey.${item.key}.tab`) }}
        </TabsTrigger>
      </TabsList>

      <TabsContent v-for="item in tracks" :key="item.key" :value="item.key" class="w-full">
        <p class="mx-auto mb-10 max-w-2xl text-center text-pretty text-lg leading-relaxed">
          {{ t(`preauth.landing.journey.${item.key}.intro`) }}
        </p>
        <ol class="flex flex-col items-stretch gap-2 xl:flex-row xl:items-stretch">
          <li
            v-for="(step, index) in item.steps"
            :key="step.key"
            class="flex flex-col items-center xl:min-w-0 xl:flex-1 xl:flex-row xl:items-stretch"
          >
            <!-- Bubble: lifted off the surface, numbered on the corner. -->
            <span
              class="relative z-10 flex size-14 shrink-0 items-center justify-center self-center rounded-full border bg-card shadow-lg ring-4 ring-background"
            >
              <component :is="step.icon" class="size-6 text-primary" aria-hidden="true" />
              <span
                aria-hidden="true"
                class="absolute -bottom-1 -right-1 flex size-5 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground"
              >
                {{ index + 1 }}
              </span>
            </span>

            <span aria-hidden="true" class="h-3 w-px self-center bg-border xl:h-px xl:w-3" />

            <div
              class="w-full rounded-2xl border bg-card p-4 text-center shadow-sm xl:min-w-0 xl:flex-1 xl:text-left"
            >
              <h3 class="text-sm font-semibold">
                {{ t(`preauth.landing.journey.${item.key}.steps.${step.key}.title`) }}
              </h3>
              <p class="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                {{ t(`preauth.landing.journey.${item.key}.steps.${step.key}.description`) }}
              </p>
            </div>

            <!-- Carries the eye to the next pair; never the last one. -->
            <span
              v-if="index < item.steps.length - 1"
              aria-hidden="true"
              class="flex shrink-0 items-center justify-center self-center py-2 text-muted-foreground/50 xl:px-1.5 xl:py-0"
            >
              <ChevronDownIcon class="size-5 xl:hidden" />
              <ChevronRightIcon class="hidden size-5 xl:block" />
            </span>
          </li>
        </ol>

        <p class="mt-8 text-center text-sm text-muted-foreground">
          {{ t(`preauth.landing.journey.${item.key}.footnote`) }}
        </p>
      </TabsContent>
    </Tabs>
  </LandingSection>
</template>
