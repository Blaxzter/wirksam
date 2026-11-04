<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import QRCode from 'qrcode'

const props = withDefaults(
  defineProps<{
    value: string
    /** Displayed size in CSS pixels. */
    size?: number
    /** Quiet zone around the code, in modules. */
    margin?: number
    /**
     * Render this many image pixels per CSS pixel, so a code shown on a phone
     * stays sharp for a camera to read. Displayed at `size` either way.
     */
    pixelRatio?: number
    alt?: string
  }>(),
  { size: 128, margin: 0, pixelRatio: 1, alt: 'QR Code' },
)

const emit = defineEmits<{
  ready: []
}>()

const dataUrl = ref('')

const generate = async () => {
  if (!props.value) return
  dataUrl.value = await QRCode.toDataURL(props.value, {
    width: Math.round(props.size * props.pixelRatio),
    margin: props.margin,
    errorCorrectionLevel: 'M',
    color: { dark: '#000000', light: '#ffffff' },
  })
  emit('ready')
}

onMounted(generate)
watch(() => [props.value, props.size, props.margin, props.pixelRatio], generate)
</script>

<template>
  <img v-if="dataUrl" :src="dataUrl" :width="size" :height="size" :alt="alt" />
</template>
