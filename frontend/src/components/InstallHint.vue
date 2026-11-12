<script setup lang="ts">
/**
 * Explains how to add OpsHub to the home screen. Opened from there, it runs full screen without the
 * browser's address bar, like an app. Browsers do not allow a web page to hide the address bar itself.
 */
import { onMounted, ref } from 'vue'

import { isInstalledApp } from '@/composables/useMobile'

interface InstallPrompt extends Event {
  prompt(): Promise<void>
}

const installed = ref(isInstalledApp())
const isIos = /iPhone|iPad|iPod/.test(navigator.userAgent)
const prompt = ref<InstallPrompt | null>(null)
let deferred: InstallPrompt | null = null

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault()
  deferred = e as InstallPrompt
})

onMounted(() => {
  prompt.value = deferred
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    prompt.value = e as InstallPrompt
  })
})

async function install(): Promise<void> {
  await prompt.value?.prompt()
  prompt.value = null
}
</script>

<template>
  <div v-if="!installed" class="install">
    <b>Use OpsHub like an app</b>
    <template v-if="prompt">
      <span>Install it on this phone. It then opens full screen from its own icon, without the browser bar.</span>
      <el-button type="primary" @click="install">Install the app</el-button>
    </template>
    <span v-else-if="isIos">
      Tap the <b>Share</b> button of the browser (the square with an arrow), then <b>Add to Home Screen</b>. Open OpsHub
      from the new icon: it runs full screen, without the address bar.
    </span>
    <span v-else>
      Open the browser menu and choose <b>Add to Home screen</b> or <b>Install app</b>. Open OpsHub from the new icon: it runs
      full screen, without the address bar.
    </span>
  </div>
</template>

<style scoped>
.install {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--erf-accent) 8%, var(--erf-surface));
  border: 1px solid color-mix(in srgb, var(--erf-accent) 30%, transparent);
  font-size: 14px;
  line-height: 1.45;
}
.install .el-button {
  justify-self: start;
}
</style>
