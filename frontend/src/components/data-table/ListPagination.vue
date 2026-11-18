<script setup lang="ts">
/**
 * Pages of a server-paginated list, in the app's language.
 *
 * Wraps the shadcn `Pagination*` parts, whose built-in labels (and reka's
 * `aria-label`s under them) are English, so every label is passed in here.
 * Renders nothing, not even its spacing, while everything fits on one page.
 *
 * It measures its own width rather than the viewport's, because it also sits
 * in narrow dialogs: below `WIDE_FROM` px it drops the first/last buttons and
 * the neighbouring pages, which keeps it on one line on a 320 px phone.
 */
import { computed, useTemplateRef } from 'vue'

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, MoreHorizontal } from '@lucide/vue'
import { useElementSize } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationFirst,
  PaginationItem,
  PaginationLast,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'

const props = defineProps<{
  /** 1-based. */
  page: number
  /** Rows in the whole list, not on this page. */
  total: number
  pageSize: number
}>()

const emit = defineEmits<{ 'update:page': [page: number] }>()

const { t } = useI18n()

/** First, previous and next with words, last, and a page either side of the current one. */
const WIDE_FROM = 560

const root = useTemplateRef<HTMLElement>('root')
const { width } = useElementSize(root)
const wide = computed(() => width.value >= WIDE_FROM)

const pageCount = computed(() => Math.ceil(props.total / Math.max(1, props.pageSize)))

const ACTIVE_CLASS =
  'border-primary bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
</script>

<template>
  <div v-if="pageCount > 1" ref="root" class="w-full" data-testid="list-pagination">
    <Pagination
      :page="props.page"
      :total="props.total"
      :items-per-page="props.pageSize"
      :sibling-count="wide ? 1 : 0"
      show-edges
      :aria-label="t('common.pagination.label')"
      @update:page="emit('update:page', $event)"
    >
      <PaginationContent v-slot="{ items }">
        <PaginationFirst
          v-if="wide"
          size="icon"
          class="px-0"
          :aria-label="t('common.pagination.first')"
        >
          <ChevronsLeft aria-hidden="true" />
        </PaginationFirst>
        <PaginationPrevious
          :size="wide ? 'default' : 'icon'"
          :aria-label="t('common.pagination.previous')"
        >
          <ChevronLeft aria-hidden="true" />
          <span v-if="wide">{{ t('common.pagination.previous') }}</span>
        </PaginationPrevious>
        <template v-for="(item, index) in items" :key="index">
          <PaginationItem
            v-if="item.type === 'page'"
            :value="item.value"
            :is-active="item.value === props.page"
            :class="item.value === props.page ? ACTIVE_CLASS : undefined"
            :aria-label="t('common.pagination.pageOf', { page: item.value, count: pageCount })"
          >
            {{ item.value }}
          </PaginationItem>
          <PaginationEllipsis v-else>
            <MoreHorizontal class="size-4" aria-hidden="true" />
            <span class="sr-only">{{ t('common.pagination.morePages') }}</span>
          </PaginationEllipsis>
        </template>
        <PaginationNext :size="wide ? 'default' : 'icon'" :aria-label="t('common.pagination.next')">
          <span v-if="wide">{{ t('common.pagination.next') }}</span>
          <ChevronRight aria-hidden="true" />
        </PaginationNext>
        <PaginationLast
          v-if="wide"
          size="icon"
          class="px-0"
          :aria-label="t('common.pagination.last')"
        >
          <ChevronsRight aria-hidden="true" />
        </PaginationLast>
      </PaginationContent>
    </Pagination>
  </div>
</template>
