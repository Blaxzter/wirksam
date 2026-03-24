<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  botUsername: string
}>()

const emit = defineEmits<{
  auth: [
    data: {
      id: number
      first_name?: string
      last_name?: string
      username?: string
      photo_url?: string
      auth_date: number
      hash: string
    },
  ]
}>()

const container = ref<HTMLDivElement | null>(null)
let scriptEl: HTMLScriptElement | null = null

function mount() {
  if (!container.value || !props.botUsername) return
  cleanup()

  // The Telegram widget calls this global callback on success
  const callbackName = `__telegramLoginCallback_${Date.now()}`
  ;(window as Record<string, unknown>)[callbackName] = (user: Record<string, unknown>) => {
    emit('auth', user as Parameters<typeof emit>[1])
    delete (window as Record<string, unknown>)[callbackName]
  }

  scriptEl = document.createElement('script')
  scriptEl.src = 'https://telegram.org/js/telegram-widget.js?22'
  scriptEl.async = true
  scriptEl.setAttribute('data-telegram-login', props.botUsername)
  scriptEl.setAttribute('data-size', 'large')
  scriptEl.setAttribute('data-radius', '8')
  scriptEl.setAttribute('data-request-access', 'write')
  scriptEl.setAttribute('data-onauth', `${callbackName}(user)`)
  container.value.appendChild(scriptEl)
}

function cleanup() {
  if (scriptEl && container.value?.contains(scriptEl)) {
    container.value.removeChild(scriptEl)
  }
  scriptEl = null
  // Clean up any leftover global callbacks
  for (const key of Object.keys(window)) {
    if (key.startsWith('__telegramLoginCallback_')) {
      delete (window as Record<string, unknown>)[key]
    }
  }
}

onMounted(mount)
watch(() => props.botUsername, mount)
onBeforeUnmount(cleanup)
</script>

<template>
  <div ref="container" />
</template>
