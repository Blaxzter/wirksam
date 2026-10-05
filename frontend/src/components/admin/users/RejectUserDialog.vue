<script setup lang="ts">
import { ref, watch } from 'vue'

import { useI18n } from 'vue-i18n'

import Button from '@/components/ui/button/Button.vue'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import Textarea from '@/components/ui/textarea/Textarea.vue'

import type { UserRead } from '@/client/types.gen'

const props = withDefaults(
  defineProps<{
    open: boolean
    user: UserRead | null
    loading: boolean
    /**
     * `registration` turns a waiting signup away; `suspension` records why an
     * already suspended account was suspended. Same shape, different words:
     * the person reads the reason either way.
     */
    mode?: 'registration' | 'suspension'
  }>(),
  { mode: 'registration' },
)

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: [reason: string]
}>()

const { t } = useI18n()
const reason = ref('')

watch(
  () => props.open,
  (open) => {
    if (open) reason.value = ''
  },
)
</script>

<template>
  <ResponsiveDialog :open="props.open" @update:open="emit('update:open', $event)">
    <ResponsiveDialogContent>
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>{{
          props.mode === 'registration'
            ? t('admin.users.rejectDialogTitle')
            : t('admin.users.suspendDialogTitle')
        }}</ResponsiveDialogTitle>
        <ResponsiveDialogDescription>
          {{
            t(
              props.mode === 'registration'
                ? 'admin.users.rejectDialogDescription'
                : 'admin.users.suspendDialogDescription',
              { name: props.user?.name ?? props.user?.email },
            )
          }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>
      <ResponsiveDialogBody class="pb-2">
        <Textarea
          v-model="reason"
          :placeholder="
            props.mode === 'registration'
              ? t('admin.users.rejectReasonPlaceholder')
              : t('admin.users.suspendReasonPlaceholder')
          "
          rows="3"
        />
      </ResponsiveDialogBody>
      <ResponsiveDialogFooter>
        <Button variant="outline" @click="emit('update:open', false)">
          {{ t('common.actions.cancel') }}
        </Button>
        <Button variant="destructive" :disabled="props.loading" @click="emit('confirm', reason)">
          {{ props.mode === 'registration' ? t('admin.users.reject') : t('common.actions.save') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
