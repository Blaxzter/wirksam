<script setup lang="ts">
/**
 * "What helpers see": pick one of the event's lists that has not ended and
 * see the page its link opens, as a guest would, with the plain facts about
 * it beside it. Opening the page here counts no visit; the real link, opened
 * from here, is the real thing.
 */
import { computed, onMounted, ref, watch } from 'vue'

import { Check, ExternalLink } from '@lucide/vue'
import type { AcceptableValue } from 'reka-ui'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useSharedListsStore } from '@/stores/sharedLists'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'

import PublicListPreview from '@/components/guest/PublicListPreview.vue'
import { PREVIEW_KEY } from '@/components/shared-lists/pageQuery'
import { useSharedListText } from '@/components/shared-lists/sharedListText'

import type { PublicSharedList, SharedListRow } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { askedFieldKeys, sharedListUrl } from '@/lib/shared-lists'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useSharedListsStore()
const { joinList } = useSharedListText()

const choices = ref<SharedListRow[] | null>(null)
const preview = ref<PublicSharedList | null>(null)

/** The list named in the address, or the first one. */
const selected = computed<SharedListRow | null>(() => {
  const all = choices.value ?? []
  const asked = route.query[PREVIEW_KEY]
  return all.find((row) => row.id === asked) ?? all[0] ?? null
})

const pick = computed<AcceptableValue>({
  get: () => selected.value?.id ?? '',
  set: (value) => {
    if (typeof value !== 'string') return
    void router.replace({ query: { ...route.query, [PREVIEW_KEY]: value }, hash: route.hash })
  },
})

onMounted(async () => {
  try {
    choices.value = await store.fetchPreviewChoices()
  } catch (error) {
    choices.value = []
    toastApiError(error)
  }
})

watch(
  () => selected.value?.id,
  async (id) => {
    preview.value = null
    if (!id) return
    try {
      const page = await store.fetchPreview(id)
      if (selected.value?.id === id) preview.value = page
    } catch (error) {
      toastApiError(error)
    }
  },
)

const facts = computed(() => {
  const list = preview.value
  if (!list) return []
  const asked = joinList(askedFieldKeys(list.ask_email, list.ask_phone).map((key) => t(key)))
  return [
    t('sharedLists.preview.facts.noAccount'),
    t('sharedLists.preview.facts.asked', { fields: asked }),
    list.ask_email === 'off'
      ? t('sharedLists.preview.facts.noConfirmation')
      : t('sharedLists.preview.facts.confirmation'),
    list.show_names === 'first'
      ? t('sharedLists.preview.facts.names')
      : t('sharedLists.preview.facts.noNames'),
    list.max_per_person
      ? t('sharedLists.preview.facts.maxPer', { count: list.max_per_person }, list.max_per_person)
      : t('sharedLists.preview.facts.unlimited'),
  ]
})
</script>

<template>
  <section
    class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_400px] lg:items-start"
    data-testid="shared-lists-preview"
  >
    <div v-if="choices === null" class="grid gap-3" aria-busy="true">
      <Skeleton class="h-10 w-full rounded-lg" />
      <Skeleton class="h-32 w-full rounded-xl" />
    </div>

    <p
      v-else-if="choices.length === 0"
      class="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground lg:col-span-2"
      data-testid="shared-lists-preview-empty"
    >
      {{ t('sharedLists.preview.empty') }}
    </p>

    <template v-else>
      <div class="grid max-w-prose gap-4 lg:sticky lg:top-4">
        <div class="grid gap-1.5">
          <label for="shared-lists-preview-pick" class="text-sm font-semibold">
            {{ t('sharedLists.preview.which') }}
          </label>
          <Select v-model="pick">
            <SelectTrigger
              id="shared-lists-preview-pick"
              class="h-11 w-full sm:h-9"
              data-testid="shared-lists-preview-pick"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="row in choices" :key="row.id" :value="row.id">
                {{ row.title }} ({{ t(`sharedLists.status.${row.effective_status}`) }})
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <p class="text-[15px]">{{ t('sharedLists.preview.intro') }}</p>
        <ul
          v-if="facts.length > 0"
          class="grid gap-2 text-sm"
          data-testid="shared-lists-preview-facts"
        >
          <li v-for="fact in facts" :key="fact" class="flex items-start gap-2">
            <Check class="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            {{ fact }}
          </li>
        </ul>
        <p class="text-[13px] text-muted-foreground">{{ t('sharedLists.preview.realSignups') }}</p>
        <p class="text-[13px] text-muted-foreground">{{ t('sharedLists.preview.hint') }}</p>
        <Button v-if="selected" variant="outline" class="w-fit max-sm:h-11" as-child>
          <a
            :href="sharedListUrl(selected.code)"
            target="_blank"
            rel="noopener noreferrer"
            data-testid="shared-lists-preview-open"
          >
            <ExternalLink aria-hidden="true" />
            {{ t('sharedLists.actions.openLink') }}
            <span class="sr-only">{{ t('sharedLists.preview.newTab') }}</span>
          </a>
        </Button>
      </div>

      <div
        role="region"
        :aria-label="t('sharedLists.preview.label')"
        data-testid="shared-lists-preview-page"
      >
        <PublicListPreview v-if="preview" :list="preview" />
        <Skeleton v-else class="h-96 w-full rounded-2xl" />
      </div>
    </template>
  </section>
</template>
