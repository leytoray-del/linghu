<script setup lang="ts">
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import SensitiveNote from '@/components/SensitiveNote.vue'
import { useAuthStore } from '@/stores/auth'
import { errorMessage, fieldErrors, showSuccess } from '@/utils/feedback'

import { inventoryApi } from '../api'
import AttributeFields from '../components/AttributeFields.vue'
import BarcodeScanner from '../components/BarcodeScanner.vue'
import { pickSerial } from '../barcode'
import { useInventoryLookups } from '../lookups'
import type { AttributeValue, DeliveryInput } from '../types'

interface Row {
  serial_no: string
  model_id: number
  warranty_start: string | null
  warranty_end: string | null
  attributes: Record<string, AttributeValue>
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const lk = useInventoryLookups()

const DRAFT_KEY = `erf.inventory.deliveryDraft.${auth.me?.id ?? 0}`

const header = reactive({
  project_id: null as number | null,
  location_id: null as number | null,
  received_on: dayjs().format('YYYY-MM-DD'),
  supplier_id: null as number | null,
  delivery_order_no: '',
  warranty_start: null as string | null,
  warranty_end: null as string | null,
  remarks: '',
})
const modelId = ref<number | null>(null)
/** Values of the category's fields applied to every new item of the current model. */
const common = ref<Record<number, Record<string, AttributeValue>>>({})
const rows = ref<Row[]>([])
const typed = ref('')
const scanning = ref(false)
const notice = ref<{ type: 'success' | 'warning' | 'error'; text: string } | null>(null)
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const restored = ref(false)
const editing = ref<number | null>(null)
const editBuffer = ref<Row | null>(null)

const projects = computed(() => (lk.data.value?.projects ?? []).filter((p) => p.is_active))
const stores = computed(() => (lk.data.value?.locations ?? []).filter((l) => l.kind === 'STORE' && l.is_active))
const suppliers = computed(() => (lk.data.value?.suppliers ?? []).filter((s) => s.is_active))
const models = computed(() => (lk.data.value?.models ?? []).filter((m) => m.is_active))
const model = computed(() => models.value.find((m) => m.id === modelId.value))
const category = computed(() => lk.categoryOfModel(modelId.value))
const commonValues = computed({
  get: () => (modelId.value ? (common.value[modelId.value] ?? {}) : {}),
  set: (v) => {
    if (modelId.value) common.value = { ...common.value, [modelId.value]: v }
  },
})
const counts = computed(() => {
  const by = new Map<number, number>()
  rows.value.forEach((r) => by.set(r.model_id, (by.get(r.model_id) ?? 0) + 1))
  return [...by.entries()].map(([id, n]) => ({ model: models.value.find((m) => m.id === id)?.model_no ?? '?', n }))
})
const headerReady = computed(() => !!header.project_id && !!header.location_id && !!header.received_on)
/** Whether any model in use (or the one being scanned) belongs to a category that requires warranty dates. */
const warrantyRequired = computed(() => {
  const ids = new Set(rows.value.map((r) => r.model_id))
  if (modelId.value) ids.add(modelId.value)
  return [...ids].some((id) => lk.categoryOfModel(id)?.warranty_required)
})

function modelLabel(id: number): string {
  const m = models.value.find((x) => x.id === id)
  const c = m ? lk.category(m.category_id) : undefined
  return m ? `${m.model_no}${c ? ` · ${c.name}` : ''}` : '?'
}

function normalise(value: string): string {
  return value.replace(/\s+/g, '').toUpperCase()
}

/** The latest outcome, also shown on the camera view so it is seen while scanning. */
const scanFeedback = computed(() =>
  notice.value
    ? { tone: notice.value.type === 'success' ? ('ok' as const) : notice.value.type === 'warning' ? ('warn' as const) : ('bad' as const), text: notice.value.text }
    : null,
)

/**
 * Add one serial number. Codes from the camera go through pickSerial, which removes label identifiers
 * such as the "S" before a serial number and skips part numbers and dates. Typed values are taken as
 * typed, and checked against the model's serial number format when it has one.
 */
async function add(raw: string, fromCamera: boolean): Promise<boolean> {
  if (!normalise(raw)) return false
  if (!modelId.value || !model.value) {
    notice.value = { type: 'error', text: 'Choose the model first.' }
    return false
  }
  let serial: string
  if (fromCamera || model.value.serial_pattern) {
    const verdict = pickSerial(raw, model.value.serial_pattern, model.value.model_no)
    if (verdict.kind === 'skip') {
      notice.value = { type: fromCamera ? 'warning' : 'error', text: fromCamera ? `Skipped: ${verdict.reason}` : verdict.reason }
      return false
    }
    serial = verdict.serial
  } else {
    serial = normalise(raw)
  }
  if (rows.value.some((r) => r.serial_no === serial)) {
    // The label of the item just added is usually still in view; do not replace "Added" for it.
    if (fromCamera && rows.value[0]?.serial_no === serial) return false
    notice.value = { type: 'warning', text: `${serial} is already in this delivery.` }
    return false
  }
  try {
    const check = await inventoryApi.checkSerial(serial)
    if (check.exists) {
      notice.value = { type: 'error', text: check.message ?? `${serial} is already registered.` }
      return false
    }
  } catch {
    /* the server checks again when the delivery is saved */
  }
  rows.value.unshift({
    serial_no: serial,
    model_id: modelId.value,
    warranty_start: header.warranty_start,
    warranty_end: header.warranty_end,
    attributes: { ...commonValues.value },
  })
  notice.value = { type: 'success', text: `Added ${serial} (${rows.value.length} in this delivery).` }
  typed.value = ''
  return true
}

/** All barcodes read from one photo: add the serial numbers, and say what was skipped. */
async function addFromPhoto(codes: string[]): Promise<void> {
  const added: string[] = []
  const skipped: string[] = []
  for (const c of codes) {
    if (await add(c, true)) added.push(rows.value[0]!.serial_no)
    else skipped.push(notice.value?.text ?? c)
  }
  if (added.length) {
    notice.value = {
      type: 'success',
      text: `Added ${added.join(', ')}.${skipped.length ? ` ${skipped.length} other barcode${skipped.length === 1 ? '' : 's'} on the label skipped.` : ''}`,
    }
  } else if (skipped.length === 1) {
    notice.value = { type: 'warning', text: skipped[0]! }
  } else {
    notice.value = {
      type: 'warning',
      text: `No serial number was found among ${codes.length} barcodes: ${codes.join(', ')}. Check the model you chose.`,
    }
  }
}

function onTypedEnter(): void {
  add(typed.value, false)
}

function remove(index: number): void {
  rows.value.splice(index, 1)
}

function openDetails(index: number): void {
  editing.value = index
  const r = rows.value[index]!
  editBuffer.value = { ...r, attributes: { ...r.attributes } }
}

function saveDetails(): void {
  if (editing.value === null || !editBuffer.value) return
  rows.value[editing.value] = editBuffer.value
  editing.value = null
}

function rowError(index: number): string | undefined {
  const prefix = `items.${index}.`
  const hit = Object.entries(errors.value).find(([k]) => k.startsWith(prefix))
  return hit?.[1]
}

async function save(): Promise<void> {
  errors.value = {}
  formError.value = null
  if (!headerReady.value) {
    errors.value = {
      project_id: header.project_id ? '' : 'Choose the project.',
      location_id: header.location_id ? '' : 'Choose the store.',
    }
    formError.value = 'Choose the project, the store and the date received.'
    return
  }
  if (!rows.value.length) {
    formError.value = 'Scan or type at least one serial number.'
    return
  }
  // Items scanned before the warranty dates were entered take the delivery's dates.
  rows.value.forEach((r) => {
    r.warranty_start ??= header.warranty_start
    r.warranty_end ??= header.warranty_end
  })
  if (warrantyRequired.value && rows.value.some((r) => !r.warranty_start || !r.warranty_end)) {
    errors.value = {
      warranty_start: header.warranty_start ? '' : 'Enter the warranty start date.',
      warranty_end: header.warranty_end ? '' : 'Enter the warranty end date.',
    }
    formError.value = 'Enter the warranty dates. They are required for this equipment.'
    return
  }
  saving.value = true
  // The server reports problems by position in the list it receives, which is oldest first.
  const ordered = [...rows.value].reverse()
  const body: DeliveryInput = {
    project_id: header.project_id!,
    location_id: header.location_id!,
    received_on: header.received_on,
    supplier_id: header.supplier_id,
    delivery_order_no: header.delivery_order_no.trim() || null,
    remarks: header.remarks.trim() || null,
    items: ordered.map((r) => ({ ...r })),
  }
  try {
    const result = await inventoryApi.registerDelivery(body)
    clearDraft()
    showSuccess(`${result.delivery_no} saved with ${result.item_count} item${result.item_count === 1 ? '' : 's'}.`)
    await router.replace(`/inventory/projects/${result.project.id}`)
  } catch (e) {
    const raw = fieldErrors(e)
    const n = rows.value.length
    errors.value = Object.fromEntries(
      Object.entries(raw).map(([k, v]) => {
        const m = /^items\.(\d+)\.(.*)$/.exec(k)
        return m ? [`items.${n - 1 - Number(m[1])}.${m[2]}`, v] : [k, v]
      }),
    )
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

// ---- draft kept in this browser, so a reload or a lost connection does not lose the scans ----

function saveDraft(): void {
  try {
    if (!rows.value.length) localStorage.removeItem(DRAFT_KEY)
    else localStorage.setItem(DRAFT_KEY, JSON.stringify({ header, modelId: modelId.value, common: common.value, rows: rows.value }))
  } catch {
    /* storage is optional */
  }
}

function clearDraft(): void {
  try {
    localStorage.removeItem(DRAFT_KEY)
  } catch {
    /* storage is optional */
  }
}

async function discardDraft(): Promise<void> {
  try {
    await ElMessageBox.confirm('The scanned items that were not saved will be removed.', 'Discard the unsaved delivery?', {
      confirmButtonText: 'Discard',
      cancelButtonText: 'Keep',
      type: 'warning',
    })
  } catch {
    return
  }
  rows.value = []
  restored.value = false
  clearDraft()
}

watch([rows, modelId, common, () => ({ ...header })], saveDraft, { deep: true })

onMounted(async () => {
  try {
    await lk.load(true)
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (raw) {
      const draft = JSON.parse(raw)
      Object.assign(header, draft.header)
      modelId.value = draft.modelId
      common.value = draft.common ?? {}
      rows.value = draft.rows ?? []
      restored.value = rows.value.length > 0
    }
  } catch {
    /* ignore a damaged draft */
  }
  const fromQuery = Number(route.query.project)
  if (!restored.value && fromQuery) header.project_id = fromQuery
  if (!header.location_id && stores.value.length === 1) header.location_id = stores.value[0]!.id
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>Register a delivery</h1>
        <p class="sub">Choose the project the equipment was delivered for, then scan each item. Everything is saved together.</p>
      </div>
    </div>

    <el-alert v-if="restored" type="info" show-icon :closable="false" title="Your unsaved delivery was restored.">
      <template #default>
        <el-button size="small" link type="primary" @click="discardDraft">Discard it and start again</el-button>
      </template>
    </el-alert>

    <el-form label-position="top" class="layout" @submit.prevent>
      <section class="panel">
        <h2>1. Delivery</h2>
        <div class="grid">
          <el-form-item label="Project" required :error="errors.project_id" for="d-project" class="wide">
            <el-select id="d-project" v-model="header.project_id" filterable placeholder="Choose the project">
              <el-option v-for="p in projects" :key="p.id" :label="`${p.name} (${p.code})`" :value="p.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Store" required :error="errors.location_id" for="d-store">
            <el-select id="d-store" v-model="header.location_id" placeholder="Where the items are kept">
              <el-option v-for="l in stores" :key="l.id" :label="l.name" :value="l.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Received on" required :error="errors.received_on">
            <el-date-picker v-model="header.received_on" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" :clearable="false" />
          </el-form-item>
          <el-form-item label="Supplier" :error="errors.supplier_id" for="d-supplier">
            <el-select id="d-supplier" v-model="header.supplier_id" clearable placeholder="Optional">
              <el-option v-for="s in suppliers" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="Delivery order number" for="d-do">
            <el-input id="d-do" v-model="header.delivery_order_no" maxlength="64" placeholder="Optional" />
          </el-form-item>
          <el-form-item label="Warranty start" :required="warrantyRequired" :error="errors.warranty_start">
            <el-date-picker v-model="header.warranty_start" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" />
          </el-form-item>
          <el-form-item label="Warranty end" :required="warrantyRequired" :error="errors.warranty_end">
            <el-date-picker v-model="header.warranty_end" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" />
          </el-form-item>
        </div>
        <p class="muted small">The warranty dates apply to every item in the delivery. You can change them for a single item under Details.</p>
      </section>

      <section class="panel">
        <h2>2. Items</h2>
        <el-form-item label="Model" required for="d-model">
          <el-select id="d-model" v-model="modelId" filterable placeholder="Choose the model you are scanning">
            <el-option v-for="m in models" :key="m.id" :label="modelLabel(m.id)" :value="m.id" />
          </el-select>
        </el-form-item>

        <template v-if="category">
          <details v-if="category.fields.some((f) => !f.retired)" class="common">
            <summary>Details that are the same for every {{ model?.model_no }} in this delivery (optional)</summary>
            <SensitiveNote text="Record equipment details only. Do not enter passwords, IP addresses or network details." />
            <AttributeFields v-model="commonValues" :fields="category.fields" id-prefix="common" />
          </details>

          <BarcodeScanner
            v-if="scanning"
            :feedback="scanFeedback"
            @code="(c) => add(c, true)"
            @codes="addFromPhoto"
            @close="scanning = false"
          />
          <div class="entry">
            <el-button v-if="!scanning" type="primary" @click="scanning = true">Scan with camera</el-button>
            <el-input
              v-model="typed"
              placeholder="Or type a serial number and press Enter"
              class="typed"
              aria-label="Serial number"
              autocapitalize="characters"
              @keyup.enter="onTypedEnter"
            >
              <template #append><el-button @click="onTypedEnter">Add</el-button></template>
            </el-input>
          </div>
          <p v-if="model?.serial_pattern" class="muted small">
            Only codes that match the {{ model.model_no }} serial number format are added, so other barcodes on the label are ignored.
          </p>
        </template>

        <el-alert v-if="notice" :type="notice.type" :title="notice.text" :closable="false" show-icon class="notice" />

        <div class="list-head">
          <b>{{ rows.length }} item{{ rows.length === 1 ? '' : 's' }}</b>
          <span class="muted small">{{ counts.map((c) => `${c.n} × ${c.model}`).join(' · ') }}</span>
        </div>
        <ol v-if="rows.length" class="rows">
          <li v-for="(r, i) in rows" :key="r.serial_no" :class="{ bad: rowError(i) }">
            <div class="row-main">
              <span class="mono serial">{{ r.serial_no }}</span>
              <span class="muted small">{{ modelLabel(r.model_id) }}</span>
              <span v-if="rowError(i)" class="error small">{{ rowError(i) }}</span>
            </div>
            <el-button size="small" @click="openDetails(i)">Details</el-button>
            <el-button size="small" link type="danger" :aria-label="`Remove ${r.serial_no}`" @click="remove(i)">Remove</el-button>
          </li>
        </ol>
        <p v-else class="muted empty">Scanned items appear here.</p>
      </section>

      <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
      <div class="footer">
        <el-button @click="$router.back()">Cancel</el-button>
        <el-button type="primary" :loading="saving" :disabled="!rows.length" @click="save">
          Save delivery{{ rows.length ? ` (${rows.length})` : '' }}
        </el-button>
      </div>
    </el-form>

    <el-dialog
      :model-value="editing !== null"
      :title="editBuffer ? `Details for ${editBuffer.serial_no}` : ''"
      width="min(640px, 96vw)"
      @close="editing = null"
    >
      <el-form v-if="editBuffer" label-position="top">
        <div class="grid">
          <el-form-item label="Warranty start">
            <el-date-picker v-model="editBuffer.warranty_start" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" />
          </el-form-item>
          <el-form-item label="Warranty end">
            <el-date-picker v-model="editBuffer.warranty_end" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" />
          </el-form-item>
        </div>
        <AttributeFields
          v-model="editBuffer.attributes"
          :fields="lk.categoryOfModel(editBuffer.model_id)?.fields ?? []"
          id-prefix="row"
        />
      </el-form>
      <template #footer>
        <el-button @click="editing = null">Cancel</el-button>
        <el-button type="primary" @click="saveDetails">Done</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  gap: 16px;
  max-width: 900px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0 16px;
}
.grid .wide {
  grid-column: 1 / -1;
}
.grid :deep(.el-select),
.grid :deep(.el-date-editor) {
  width: 100%;
}
:deep(#d-model),
.layout :deep(.el-select) {
  width: 100%;
}
.small {
  font-size: 12.5px;
}
.common {
  border: 1px solid var(--erf-line);
  border-radius: var(--erf-radius);
  padding: 10px 12px;
}
.common summary {
  cursor: pointer;
  font-weight: 500;
  margin-bottom: 4px;
}
.common[open] summary {
  margin-bottom: 12px;
}
.entry {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.typed {
  flex: 1;
  min-width: 220px;
}
.notice {
  padding: 6px 12px;
}
.list-head {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  align-items: baseline;
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
  max-height: 420px;
  overflow-y: auto;
}
.rows li {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--erf-line);
  border-radius: var(--erf-radius);
  padding: 6px 10px;
  background: var(--erf-surface);
}
.rows li.bad {
  border-color: var(--erf-bad);
}
.row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 2px 10px;
  align-items: baseline;
}
.serial {
  font-size: 14px;
  font-weight: 600;
}
.error {
  color: var(--erf-bad);
  flex-basis: 100%;
}
.empty {
  margin: 0;
}
.footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  position: sticky;
  bottom: 0;
  background: var(--erf-bg);
  padding: 10px 0;
}
</style>
