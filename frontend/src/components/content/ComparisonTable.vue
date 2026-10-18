<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { COMPARED_TOOLS, COMPARISON_CRITERIA } from '@/lib/content-pages'

/**
 * The comparison as a real table on wide screens and as one card per tool
 * below `lg`. Eight columns of prose do not fit a phone, and a table that
 * scrolls sideways hides most of itself, so small screens get the same facts
 * as a definition list per tool. Both are in the markup; CSS shows one.
 */
const { t } = useI18n()

const cell = (tool: string, criterion: string) =>
  t(`preauth.alternatives.tools.${tool}.cells.${criterion}`)
</script>

<template>
  <div>
    <div class="hidden overflow-hidden rounded-2xl border bg-card shadow-sm lg:block">
      <table class="w-full table-fixed text-left text-sm" data-testid="comparison-table">
        <caption class="sr-only">
          {{
            t('preauth.alternatives.table.caption')
          }}
        </caption>
        <thead class="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th scope="col" class="w-36 px-4 py-3 font-semibold">
              {{ t('preauth.alternatives.table.toolColumn') }}
            </th>
            <th
              v-for="criterion in COMPARISON_CRITERIA"
              :key="criterion"
              scope="col"
              class="px-3 py-3 font-semibold"
            >
              {{ t(`preauth.alternatives.criteria.${criterion}`) }}
            </th>
          </tr>
        </thead>
        <tbody class="divide-y">
          <tr
            v-for="tool in COMPARED_TOOLS"
            :key="tool.key"
            :class="tool.key === 'wirksam' ? 'bg-primary/5' : ''"
          >
            <th scope="row" class="px-4 py-4 align-top font-semibold">
              {{ t(`preauth.alternatives.tools.${tool.key}.name`) }}
            </th>
            <td
              v-for="criterion in COMPARISON_CRITERIA"
              :key="criterion"
              class="px-3 py-4 align-top leading-relaxed text-muted-foreground"
            >
              {{ cell(tool.key, criterion) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ul class="space-y-4 lg:hidden" data-testid="comparison-cards">
      <li
        v-for="tool in COMPARED_TOOLS"
        :key="tool.key"
        class="rounded-2xl border bg-card p-5 shadow-sm"
        :class="tool.key === 'wirksam' ? 'border-primary/40' : ''"
      >
        <h3 class="text-lg font-semibold">
          {{ t(`preauth.alternatives.tools.${tool.key}.name`) }}
        </h3>
        <dl class="mt-3 divide-y text-sm">
          <div
            v-for="criterion in COMPARISON_CRITERIA"
            :key="criterion"
            class="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-3 py-2.5"
          >
            <dt class="text-muted-foreground">
              {{ t(`preauth.alternatives.criteria.${criterion}`) }}
            </dt>
            <dd class="leading-relaxed">{{ cell(tool.key, criterion) }}</dd>
          </div>
        </dl>
      </li>
    </ul>
  </div>
</template>
