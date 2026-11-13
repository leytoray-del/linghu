<script setup lang="ts">
/**
 * Request a withdrawal (or revise one that was sent back): items of one project, a new location and a reason.
 * The project's PM approves first, then an operations manager; on approval the items move to the new location.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'

import { inventoryApi } from '../api'
import { normaliseCode, pickSerial } from '../barcode'
import BarcodeScanner from '../components/BarcodeScanner.vue'
import ItemStatusTag from '../components/ItemStatusTag.vue'
import { useInventoryLookups } from '../lookups'
import type { Item, WithdrawalDetail } from '../types'

const route = useRoute()
const router = useRouter()
const lk = useInventoryLookups()

const editingId = computed(() => (route.params.id ? Number(route.params.id) : null))
const existing = ref<WithdrawalDetail | null>(null)
const projectId = ref<number | null>(null)
const chosen = ref<Item[]>([])
const toLocationId = ref<number | null>(null)
const reason = ref('')
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const saving = ref(false)

const pickerOpen = ref(false)
const pickerQuery = ref('')
const stock = ref<Item[]>([])
const loadingStock = ref(false)
const scanning = ref(false)
const scanFeedback = ref<{ tone: 'ok' | 'warn' | 'bad'; text: string; key?: number } | null>(null)
let feedbackKey = 0

const newSiteOpen = ref(false)
const newSiteName = ref('')
const newSiteError = ref('')

const projects = computed(() => (lk.data.value?.projects ?? []).filter((p) => p.is_active))
const project = computed(() => lk.data.value?.projects.find((p) => p.id === projectId.value))
const locations = computed(() => (lk.data.value?.locations ?? []).filter((l) => l.is_active))
const pickerItems = computed(() => {
  const q = pickerQuery.value.trim().toLowerCase()
  return stock.value.filter((i) => !q || `${i.serial_no} ${i.model_no} ${i.category_name} ${i.location.name}`.toLowerCase().includes(q))
})
const isChosen = (id: number) => chosen.value.some((c) => c.id === id)

async function loadStock(): Promise<void> {
  if (!projectId.value) {
    stock.value = []
    return
  }
  loadingStock.value = true
  try {
    const page = await inventoryApi.items({ project_id: projectId.value, status: ['IN_STOCK'], page_size: 200 })
    stock.value = page.items
  } catch (e) {
    showError(e)
  } finally {
    loadingStock.value = false
  }
}

watch(projectId, (now, before) => {
  if (before !== undefined && before !== null && now !== before) chosen.value = []
  loadStock()
})

function toggle(item: Item): void {
  chosen.value = isChosen(item.id) ? chosen.value.filter((c) => c.id !== item.id) : [...chosen.value, item]
}

function say(tone: 'ok' | 'warn' | 'bad', text: string): void {
  scanFeedback.value = { tone, text, key: ++feedbackKey }
}

async function scanned(code: string): Promise<void> {
  const verdict = pickSerial(code, null)
  const serial = verdict.kind === 'serial' ? verdict.serial : normaliseCode(code)
  const hit = stock.value.find((i) => i.serial_no === serial || i.serial_no === normaliseCode(code))
  if (hit) {
    if (isChosen(hit.id)) say('warn', `${hit.serial_no} is already in this request.`)
    else {
      chosen.value = [...chosen.value, hit]
      say('ok', `Added ${hit.serial_no} (${chosen.value.length} in this request).`)
    }
    return
  }
  try {
    const check = await inventoryApi.checkSerial(serial)
    say('bad', check.exists ? `${serial} is not in stock for ${project.value?.name}.` : `${serial} is not registered.`)
  } catch (e) {
    showError(e)
  }
}

async function scannedMany(codes: string[]): Promise<void> {
  for (const c of codes) await scanned(c)
}

async function addSite(): Promise<void> {
  newSiteError.value = ''
  const name = newSiteName.value.trim()
  if (name.length < 2) {
    newSiteError.value = 'Enter the site name or address.'
    return
  }
  try {
    const site = await inventoryApi.addSite(name)
    await lk.load(true)
    toLocationId.value = site.id
    newSiteOpen.value = false
    newSiteName.value = ''
    showSuccess(`${site.name} added.`)
  } catch (e) {
    newSiteError.value = errorMessage(e)
  }
}

async function submit(): Promise<void> {
  errors.value = {}
  formError.value = null
  if (!projectId.value) errors.value.project_id = 'Choose the project.'
  if (!chosen.value.length) errors.value.item_ids = 'Add at least one item.'
  if (!toLocationId.value) errors.value.to_location_id = 'Choose where the items are going.'
  if (!reason.value.trim()) errors.value.reason = 'Explain what the items are needed for.'
  if (Object.keys(errors.value).length) {
    formError.value = 'Some details are missing.'
    return
  }
  saving.value = true
  const body = { project_id: projectId.value!, item_ids: chosen.value.map((c) => c.id), to_location_id: toLocationId.value!, reason: reason.value.trim() }
  try {
    const result = existing.value
      ? await inventoryApi.reviseWithdrawal(existing.value.id, { ...body, version: existing.value.version })
      : await inventoryApi.createWithdrawal(body)
    showSuccess(`${result.request_no} submitted. ${result.waiting_for.map((u) => u.display_name).join(', ')} will be asked to approve.`)
    await router.replace(`/inventory/withdrawals/${result.id}`)
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    await lk.load(true)
    if (editingId.value) {
      const w = await inventoryApi.withdrawal(editingId.value)
      if (!w.can_revise) {
        await router.replace(`/inventory/withdrawals/${w.id}`)
        return
      }
      existing.value = w
      projectId.value = w.project.id
      await loadStock()
      chosen.value = w.items.filter((i) => i.status === 'IN_STOCK')
      toLocationId.value = w.to_location.id
      reason.value = w.reason
      return
    }
    const fromQuery = Number(route.query.project)
    if (fromQuery) {
      projectId.value = fromQuery
      await loadStock()
      const wanted = String(route.query.items ?? '')
        .split(',')
        .map(Number)
        .filter(Boolean)
      chosen.value = stock.value.filter((i) => wanted.includes(i.id))
    }
  } catch (e) {
    showError(e)
  }
})
</script>

<template>
  <div class="form-page">
    <el-alert v-if="existing" type="warning" :closable="false" show-icon :title="`Revising ${existing.request_no}, which was rejected`">
      <template #default>Read the reason on the request, change what is needed and submit again.</template>
    </el-alert>

    <el-form label-position="top" @submit.prevent>
      <section class="block">
        <h2>Project</h2>
        <el-form-item :error="errors.project_id">
          <el-select v-model="projectId" filterable placeholder="Choose the project" size="large" :disabled="!!existing" style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="`${p.name} (${p.code})`" :value="p.id" />
          </el-select>
        </el-form-item>
        <p v-if="project" class="muted small">
          A request is for one project. {{ project.pm ? `${project.pm.display_name} (PM) approves first,` : 'This project has no PM yet;' }} then an
          operations manager.
        </p>
      </section>

      <section class="block">
        <div class="head">
          <h2>Items <span class="muted">{{ chosen.length }}</span></h2>
          <span class="tools">
            <el-button :disabled="!projectId" @click="scanning = !scanning">{{ scanning ? 'Stop scanning' : 'Scan' }}</el-button>
            <el-button :disabled="!projectId" type="primary" plain @click="pickerOpen = true">Choose from stock</el-button>
          </span>
        </div>
        <BarcodeScanner
          v-if="scanning"
          :feedback="scanFeedback"
          :caption="`Scan items of ${project?.name ?? 'the project'}`"
          @code="scanned"
          @codes="scannedMany"
          @close="scanning = false"
        />
        <p v-if="errors.item_ids" class="err">{{ errors.item_ids }}</p>
        <ol v-if="chosen.length" class="rows">
          <li v-for="i in chosen" :key="i.id">
            <div class="grow">
              <b class="mono">{{ i.serial_no }}</b>
              <span class="muted small">{{ i.category_name }} · {{ i.model_no }} · {{ i.location.name }}</span>
            </div>
            <el-button link type="danger" :aria-label="`Remove ${i.serial_no}`" @click="toggle(i)">Remove</el-button>
          </li>
        </ol>
        <p v-else-if="projectId" class="muted">No items yet. Scan them, or choose from the project's stock.</p>
      </section>

      <section class="block">
        <h2>New location</h2>
        <el-form-item :error="errors.to_location_id">
          <el-select v-model="toLocationId" filterable placeholder="Where are the items going?" size="large" style="width: 100%">
            <el-option v-for="l in locations" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-button v-if="!newSiteOpen" link type="primary" @click="newSiteOpen = true">+ The address is not in the list: add a new site</el-button>
        <div v-else class="new-site">
          <el-input v-model="newSiteName" size="large" placeholder="Site name or address, for example HSA Novena, Lobby" maxlength="120" @keyup.enter="addSite" />
          <span class="tools">
            <el-button @click="newSiteOpen = false">Cancel</el-button>
            <el-button type="primary" @click="addSite">Add site</el-button>
          </span>
          <p v-if="newSiteError" class="err">{{ newSiteError }}</p>
        </div>
      </section>

      <section class="block">
        <h2>Reason</h2>
        <el-form-item :error="errors.reason" for="w-reason">
          <el-input id="w-reason" v-model="reason" type="textarea" :autosize="{ minRows: 3 }" maxlength="2000" placeholder="What are the items needed for?" />
        </el-form-item>
      </section>

      <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
    </el-form>

    <div class="bar">
      <el-button size="large" @click="router.back()">Cancel</el-button>
      <el-button size="large" type="primary" :loading="saving" @click="submit">
        {{ existing ? 'Submit again' : 'Submit request' }}{{ chosen.length ? ` (${chosen.length})` : '' }}
      </el-button>
    </div>

    <el-drawer v-model="pickerOpen" direction="btt" size="85%" :title="`In stock: ${project?.name ?? ''}`" append-to-body>
      <el-input v-model="pickerQuery" size="large" placeholder="Search serial number, model or location" clearable />
      <p v-if="!loadingStock && !stock.length" class="muted">This project has nothing in stock.</p>
      <ol class="rows pick">
        <li v-for="i in pickerItems" :key="i.id" :class="{ on: isChosen(i.id) }" @click="toggle(i)">
          <span class="tick" aria-hidden="true">{{ isChosen(i.id) ? '✓' : '' }}</span>
          <div class="grow">
            <b class="mono">{{ i.serial_no }}</b>
            <span class="muted small">{{ i.category_name }} · {{ i.model_no }} · {{ i.location.name }}</span>
          </div>
          <ItemStatusTag :status="i.status" />
        </li>
      </ol>
      <template #footer>
        <el-button size="large" type="primary" class="wide" @click="pickerOpen = false">Done ({{ chosen.length }} chosen)</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.form-page {
  max-width: 720px;
  width: 100%;
  margin: 0 auto;
  display: grid;
  gap: 14px;
  padding-bottom: calc(76px + env(safe-area-inset-bottom, 0px));
}
.block {
  background: var(--erf-surface);
  border: 1px solid var(--erf-line);
  border-radius: 12px;
  padding: 14px 16px;
  display: grid;
  gap: 10px;
  margin-bottom: 12px;
}
.block h2 {
  font-size: 16px;
  margin: 0;
}
.block :deep(.el-form-item) {
  margin-bottom: 0;
}
.head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.tools {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tools .el-button + .el-button {
  margin-left: 0;
}
.small {
  font-size: 12.5px;
}
.muted.small {
  margin: 0;
}
.err {
  color: var(--erf-bad);
  margin: 0;
  font-size: 13px;
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}
.rows li {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--erf-line);
  border-radius: 10px;
  padding: 8px 12px;
}
.grow {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
}
.pick {
  margin-top: 12px;
}
.pick li {
  cursor: pointer;
}
.pick li.on {
  border-color: var(--erf-accent);
  background: color-mix(in srgb, var(--erf-accent) 6%, transparent);
}
.tick {
  width: 24px;
  height: 24px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 6px;
  border: 2px solid var(--erf-line);
  font-weight: 700;
  color: #fff;
}
.pick li.on .tick {
  background: var(--erf-accent);
  border-color: var(--erf-accent);
}
.new-site {
  display: grid;
  gap: 8px;
}
.bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 25;
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 10px;
  padding: 10px max(16px, env(safe-area-inset-right, 0px)) calc(10px + env(safe-area-inset-bottom, 0px))
    max(16px, env(safe-area-inset-left, 0px));
  background: var(--erf-surface);
  border-top: 1px solid var(--erf-line);
}
.bar .el-button + .el-button {
  margin-left: 0;
}
@media (min-width: 861px) {
  .bar {
    position: sticky;
    border: 1px solid var(--erf-line);
    border-radius: 12px;
    padding: 10px 14px;
  }
  .form-page {
    padding-bottom: 0;
  }
}
.wide {
  width: 100%;
}
</style>
