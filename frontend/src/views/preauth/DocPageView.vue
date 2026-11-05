<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { ArrowRightIcon, ChevronDownIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { ScreenshotItem } from '@/composables/useScreenshotSource'

import ContentPageShell from '@/components/content/ContentPageShell.vue'
import DocBlocks from '@/components/content/DocBlocks.vue'
import LandingSection from '@/components/landing/LandingSection.vue'
import ScreenshotLightbox from '@/components/landing/ScreenshotLightbox.vue'
import SectionHeading from '@/components/landing/SectionHeading.vue'

import { type DocPage, docPageById, docRouteName } from '@/lib/content-pages'
import type { DocBlock, DocShot } from '@/lib/doc-types'
import { docFor, loadDoc } from '@/lib/docs-content'

/**
 * One feature page or guide. The route passes the page's id, and all of the text
 * comes from its Markdown in `src/docs/`. A guide's sections are numbered steps,
 * which the prerender mirrors into HowTo JSON-LD, and the FAQ into FAQPage.
 */
const props = defineProps<{ id: string }>()

const { t, locale } = useI18n()
const router = useRouter()

const page = computed(() => docPageById(props.id)!)
// The route loaded this page in the language it opened in. Switching language
// here fetches the other copy, and `docFor` keeps the old one up until it's in.
watch([() => props.id, locale], ([id, language]) => void loadDoc(id, language), {
  immediate: true,
})
const doc = computed(() => docFor(props.id, locale.value)!)
const isGuide = computed(() => page.value.kind === 'guide')
const hub = computed(() => (isGuide.value ? 'guides' : 'features'))

const related = computed(() =>
  doc.value.related.map(docPageById).filter((item): item is DocPage => Boolean(item)),
)

// Every screenshot on the page in order, so the viewer can page between them.
const shots = computed<DocShot[]>(() =>
  [doc.value.intro, ...doc.value.sections.map((section) => section.blocks)]
    .flat()
    .flatMap((block: DocBlock) => (block.type === 'shots' ? block.shots : [])),
)
const gallery = computed<ScreenshotItem[]>(() =>
  shots.value.map((shot) => ({ name: shot.name, alt: shot.alt, caption: shot.alt })),
)
const zoomed = ref<number | null>(null)

function zoom(shot: DocShot) {
  zoomed.value = shots.value.indexOf(shot)
}

// The links in the Markdown are plain anchors, which is what a crawler needs.
// A click on one stays in the app instead of reloading it.
function onBodyClick(event: MouseEvent) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  const link = (event.target as HTMLElement).closest('a')
  const href = link?.getAttribute('href')
  if (!href?.startsWith('/') || link?.target) return
  event.preventDefault()
  router.push(href)
}
</script>

<template>
  <ContentPageShell
    :eyebrow="t(`preauth.docs.hubs.${page.kind}.eyebrow`)"
    :title="doc.title"
    :lede="doc.lede"
    :breadcrumb="t(`preauth.docs.pages.${page.key}.name`)"
    :parent="{ routeName: hub, label: t(`preauth.docs.hubs.${page.kind}.breadcrumb`) }"
    :hide-actions="isGuide"
    :cta-title="t('preauth.docs.ctaTitle')"
  >
    <LandingSection id="content" width="wide">
      <div class="lg:grid lg:grid-cols-[minmax(0,1fr)_13rem] lg:gap-12" @click="onBodyClick">
        <article class="min-w-0" data-testid="doc-body">
          <DocBlocks :blocks="doc.intro" @zoom="zoom" />

          <!-- An ordered list in a guide: the numbers carry meaning, and screen
               readers say so. -->
          <component
            :is="isGuide ? 'ol' : 'div'"
            class="space-y-12"
            :class="{ 'mt-12': doc.intro.length > 0 }"
          >
            <component
              :is="isGuide ? 'li' : 'section'"
              v-for="(section, index) in doc.sections"
              :id="section.id"
              :key="section.id"
              class="scroll-mt-24"
            >
              <h2 class="flex items-center gap-3 text-2xl font-semibold tracking-tight">
                <span
                  v-if="isGuide"
                  class="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground"
                  aria-hidden="true"
                >
                  {{ index + 1 }}
                </span>
                {{ section.title }}
              </h2>
              <div class="mt-4">
                <DocBlocks :blocks="section.blocks" @zoom="zoom" />
              </div>
            </component>
          </component>
        </article>

        <nav
          v-if="doc.sections.length > 1"
          :aria-label="t('preauth.docs.onThisPage')"
          class="sticky top-24 hidden self-start text-sm lg:block"
        >
          <p class="font-semibold">{{ t('preauth.docs.onThisPage') }}</p>
          <ul class="mt-3 space-y-2 border-l pl-3">
            <li v-for="section in doc.sections" :key="section.id">
              <a
                :href="`#${section.id}`"
                class="block leading-snug text-muted-foreground transition-colors hover:text-foreground"
              >
                {{ section.title }}
              </a>
            </li>
          </ul>
        </nav>
      </div>
      <ScreenshotLightbox v-model:index="zoomed" :items="gallery" />
    </LandingSection>

    <LandingSection v-if="doc.faq.length" id="faq" tone="tinted">
      <SectionHeading :title="t('preauth.docs.faqTitle')" />
      <!-- Native <details>, like LandingFaq: every answer stays in the prerendered
           HTML that search engines and LLM crawlers read. -->
      <div class="mx-auto mt-10 max-w-3xl divide-y rounded-2xl border bg-card shadow-sm">
        <details v-for="item in doc.faq" :id="item.id" :key="item.id" class="group scroll-mt-24">
          <summary
            class="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-5 text-left font-semibold [&::-webkit-details-marker]:hidden"
          >
            <h3 class="text-base">{{ item.question }}</h3>
            <ChevronDownIcon
              class="size-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
              aria-hidden="true"
            />
          </summary>
          <div class="px-6 pb-3" @click="onBodyClick">
            <DocBlocks :blocks="[{ type: 'html', html: item.html }]" />
          </div>
        </details>
      </div>
    </LandingSection>

    <LandingSection id="read-on">
      <h2 class="text-center text-2xl font-bold tracking-tight">
        {{ t('preauth.docs.readOn') }}
      </h2>
      <ul class="mx-auto mt-8 grid max-w-3xl gap-4 sm:grid-cols-2">
        <li v-for="item in related" :key="item.key">
          <RouterLink
            :to="{ name: docRouteName(item) }"
            :data-testid="`doc-related-${item.key}`"
            class="group flex h-full flex-col rounded-2xl border bg-card p-5 shadow-sm transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <span class="flex items-center justify-between gap-3 font-semibold">
              {{ t(`preauth.docs.pages.${item.key}.name`) }}
              <ArrowRightIcon
                class="size-4 shrink-0 text-primary transition-transform group-hover:translate-x-0.5"
                aria-hidden="true"
              />
            </span>
            <span class="mt-2 text-sm leading-relaxed text-muted-foreground">
              {{ t(`preauth.seo.${item.key}.description`) }}
            </span>
          </RouterLink>
        </li>
      </ul>
      <p class="mt-6 text-center">
        <RouterLink
          :to="{ name: hub }"
          data-testid="doc-hub-link"
          class="text-sm font-medium text-primary underline underline-offset-2"
        >
          {{ t(`preauth.docs.hubs.${page.kind}.all`) }}
        </RouterLink>
      </p>
    </LandingSection>
  </ContentPageShell>
</template>
