<script setup lang="ts">
/**
 * A list's settings in words: what it asks, what others see, how many shifts,
 * until when. Rows in the default slot go first, as `<dt>` and `<dd>` pairs.
 */
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { useSharedListText } from '@/components/shared-lists/sharedListText'

import type { SharedListDetail } from '@/client/types.gen'
import { askedFieldKeys } from '@/lib/shared-lists'

const props = defineProps<{
  list: Pick<
    SharedListDetail,
    | 'ask_email'
    | 'ask_phone'
    | 'show_names'
    | 'max_per_person'
    | 'ends_mode'
    | 'ends_on'
    | 'closes_at'
  >
}>()

const { t } = useI18n()
const { joinList, endsText } = useSharedListText()

const rows = computed(() => {
  const { list } = props
  return [
    {
      key: 'asked',
      label: t('sharedLists.settings.asked'),
      value: joinList(askedFieldKeys(list.ask_email, list.ask_phone).map((key) => t(key))),
    },
    {
      key: 'others',
      label: t('sharedLists.settings.others'),
      value: t(`sharedLists.settings.names.${list.show_names}`),
    },
    {
      key: 'perPerson',
      label: t('sharedLists.settings.perPerson'),
      value: list.max_per_person
        ? t('sharedLists.settings.maxPer', { count: list.max_per_person }, list.max_per_person)
        : t('sharedLists.settings.unlimited'),
    },
    { key: 'open', label: t('sharedLists.settings.open'), value: endsText(list) },
  ]
})
</script>

<template>
  <dl
    class="grid gap-x-4 gap-y-1 text-[13.5px] sm:grid-cols-[minmax(8rem,auto)_minmax(0,1fr)] sm:gap-y-2"
    data-testid="shared-list-settings"
  >
    <slot />
    <template v-for="row in rows" :key="row.key">
      <dt class="text-muted-foreground">{{ row.label }}</dt>
      <dd class="mb-2 sm:mb-0" :data-testid="`shared-list-setting-${row.key}`">{{ row.value }}</dd>
    </template>
  </dl>
</template>
