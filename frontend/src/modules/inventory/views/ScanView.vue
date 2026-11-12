<script setup lang="ts">
/** Scan any label to open the item it belongs to. */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { showError } from '@/utils/feedback'

import { inventoryApi } from '../api'
import { normaliseCode, pickSerial } from '../barcode'
import BarcodeScanner from '../components/BarcodeScanner.vue'

const router = useRouter()
const feedback = ref<{ tone: 'ok' | 'warn' | 'bad'; text: string } | null>(null)
const typed = ref('')

async function find(code: string): Promise<boolean> {
  const raw = normaliseCode(code)
  const verdict = pickSerial(code, null)
  const tries = [...new Set([verdict.kind === 'serial' ? verdict.serial : raw, raw])]
  try {
    for (const serial of tries) {
      const check = await inventoryApi.checkSerial(serial)
      if (check.exists && check.item_id) {
        await router.replace(`/inventory/items/${check.item_id}`)
        return true
      }
    }
    feedback.value = { tone: 'warn', text: `${tries[0]} is not registered.` }
  } catch (e) {
    showError(e)
  }
  return false
}

async function findAll(codes: string[]): Promise<void> {
  for (const c of codes) if (await find(c)) return
  feedback.value = { tone: 'warn', text: `None of these is registered: ${codes.join(', ')}.` }
}
</script>

<template>
  <div class="scan">
    <BarcodeScanner :feedback="feedback" caption="Scan any label to open the item" @code="find" @codes="findAll" @close="router.back()" />
    <el-input v-model="typed" size="large" placeholder="Or type the serial number" @keyup.enter="find(typed)">
      <template #append><el-button @click="find(typed)">Find</el-button></template>
    </el-input>
  </div>
</template>

<style scoped>
.scan {
  display: grid;
  gap: 12px;
}
.scan :deep(.viewport) {
  max-height: 62vh;
  aspect-ratio: 3 / 4;
}
</style>
