<script setup lang="ts">
/**
 * Register devices that arrived, one step at a time: Project, Details, Model, Scan, Review.
 * Built for phones first: each step fills the screen and the main action is always in the bar at the bottom.
 */
import dayjs from 'dayjs'
import { ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import SensitiveNote from '@/components/SensitiveNote.vue'
import { useAuthStore } from '@/stores/auth'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'
import { fmtDate } from '@/utils/format'

import { inventoryApi } from '../api'
import { pickSerial } from '../barcode'
import AttributeFields from '../components/AttributeFields.vue'
import BarcodeScanner from '../components/BarcodeScanner.vue'
import NewModelDialog from '../components/NewModelDialog.vue'
import { useInventoryLookups } from '../lookups'
import { describeFormat } from '../serialFormat'
import type { AttributeValue, DeliveryInput, ItemModel } from '../types'

type Step = 'project' | 'delivery' | 'model' | 'scan' | 'review'
const STEPS: { key: Step; label: string }[] = [
  { key: 'project', label: 'Project' },
  { key: 'delivery', label: 'Details' },
  { key: 'model', label: 'Model' },
  { key: 'scan', label: 'Scan' },
  { key: 'review', label: 'Review' },
]

interface Row {
  serial_no: string
  model_id: number
  warranty_start: string | null
  warranty_end: string | null
  attributes: Record<string, AttributeValue>
}

interface Notice {
  type: 'success' | 'warning' | 'error'
  text: string
  /** A follow-up the person can take with one tap. */
  action?:
    | { label: string; kind: 'switch'; modelId: number; code: string }
    | { label: string; kind: 'new-model'; code: string }
    | { label: string; kind: 're-add'; code: string }
  /** Changes with every new message, so the camera view flashes even when the text repeats. */
  key?: number
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const lk = useInventoryLookups()
const DRAFT_KEY = `erf.inventory.deliveryDraft.${auth.me?.id ?? 0}`

const step = ref<Step>('project')
const header = reactive({
  project_id: null as number | null,
  location_id: null as number | null,
  received_on: dayjs().format('YYYY-MM-DD'),
  supplier_id: null as number | null,
  delivery_order_no: '',
  warranty_start: dayjs().format('YYYY-MM-DD') as string | null,
  warranty_end: dayjs().add(1, 'year').format('YYYY-MM-DD') as string | null,
  remarks: '',
})

// ---- warranty: one year from the received date unless changed by hand ----
const WARRANTY_YEARS = 1
/** True while the warranty dates still follow the received date; false once someone changes them. */
const warrantyFollows = ref(true)
const plusYears = (d: string) => dayjs(d).add(WARRANTY_YEARS, 'year').format('YYYY-MM-DD')
watch(
  () => header.received_on,
  (d) => {
    if (!warrantyFollows.value || !d) return
    header.warranty_start = d
    header.warranty_end = plusYears(d)
  },
)
function onWarrantyStart(d: string | null): void {
  warrantyFollows.value = false
  // The end moves with the start, keeping the one-year period, unless it was set by hand.
  if (d && (!header.warranty_end || endFollowsStart.value)) header.warranty_end = plusYears(d)
}
const endFollowsStart = ref(true)
function onWarrantyEnd(): void {
  warrantyFollows.value = false
  endFollowsStart.value = false
}
const modelId = ref<number | null>(null)
const common = ref<Record<number, Record<string, AttributeValue>>>({})
const rows = ref<Row[]>([])
const typed = ref('')
const noticeRef = ref<Notice | null>(null)
let noticeCount = 0
/** Every new message gets a new key, so it is visibly shown again even with the same text. */
const notice = computed<Notice | null>({
  get: () => noticeRef.value,
  set: (n) => (noticeRef.value = n ? { ...n, key: ++noticeCount } : null),
})
/** Items removed in this delivery. The camera does not add them back on its own while the label is in view. */
const removed = new Map<string, Row>()
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const saving = ref(false)
const restored = ref(false)
const projectQuery = ref('')
const modelQuery = ref('')
const commonOpen = ref(false)
const listOpen = ref(false)
const newModelOpen = ref(false)
const newModelSample = ref('')
const editing = ref<number | null>(null)
const editBuffer = ref<Row | null>(null)
/** Serial numbers being checked right now, so a second read of the same label cannot add it twice. */
const checking = new Set<string>()

// ---- reference data ----

const projects = computed(() => {
  const q = projectQuery.value.trim().toLowerCase()
  return (lk.data.value?.projects ?? [])
    .filter((p) => p.is_active)
    .filter((p) => !q || `${p.name} ${p.code} ${p.client_name ?? ''}`.toLowerCase().includes(q))
})
const project = computed(() => lk.data.value?.projects.find((p) => p.id === header.project_id))
const stores = computed(() => (lk.data.value?.locations ?? []).filter((l) => l.kind === 'STORE' && l.is_active))
const store = computed(() => stores.value.find((l) => l.id === header.location_id))
const models = computed(() => (lk.data.value?.models ?? []).filter((m) => m.is_active))
const model = computed(() => models.value.find((m) => m.id === modelId.value))
const category = computed(() => lk.categoryOfModel(modelId.value))
const modelGroups = computed(() => {
  const q = modelQuery.value.trim().toLowerCase()
  const groups = new Map<string, ItemModel[]>()
  for (const m of models.value) {
    const cat = lk.category(m.category_id)
    if (q && !`${m.model_no} ${m.manufacturer ?? ''} ${cat?.name ?? ''}`.toLowerCase().includes(q)) continue
    const key = cat?.name ?? 'Other'
    groups.set(key, [...(groups.get(key) ?? []), m])
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b))
})
const commonValues = computed({
  get: () => (modelId.value ? (common.value[modelId.value] ?? {}) : {}),
  set: (v) => {
    if (modelId.value) common.value = { ...common.value, [modelId.value]: v }
  },
})
const counts = computed(() => {
  const by = new Map<number, number>()
  rows.value.forEach((r) => by.set(r.model_id, (by.get(r.model_id) ?? 0) + 1))
  return [...by.entries()].map(([id, n]) => ({ id, label: modelLabel(id), n }))
})
const warrantyRequired = computed(() => {
  const ids = new Set(rows.value.map((r) => r.model_id))
  if (modelId.value) ids.add(modelId.value)
  return [...ids].some((id) => lk.categoryOfModel(id)?.warranty_required)
})
const stepIndex = computed(() => STEPS.findIndex((s) => s.key === step.value))

function modelLabel(id: number): string {
  const m = models.value.find((x) => x.id === id)
  const c = m ? lk.category(m.category_id) : undefined
  return m ? `${m.model_no}${c ? ` · ${c.name}` : ''}` : '?'
}

// ---- moving between steps ----

function go(to: Step): void {
  formError.value = null
  step.value = to
  window.scrollTo({ top: 0 })
}

function chooseProject(id: number): void {
  header.project_id = id
  go('delivery')
}

function deliveryNext(): void {
  const problems: Record<string, string> = {}
  if (!header.location_id) problems.location_id = 'Choose the store where the items are kept.'
  if (!header.received_on) problems.received_on = 'Enter the date the devices arrived.'
  if (header.warranty_start && header.warranty_end && header.warranty_end < header.warranty_start)
    problems.warranty_end = 'The warranty must end on or after its start date.'
  errors.value = problems
  if (Object.keys(problems).length) return
  go(rows.value.length && modelId.value ? 'scan' : 'model')
}

function chooseModel(id: number): void {
  modelId.value = id
  notice.value = null
  go('scan')
}

function back(): void {
  const i = stepIndex.value
  if (i === 0) router.back()
  else go(STEPS[i - 1]!.key)
}

// ---- scanning ----

const scanFeedback = computed(() =>
  notice.value
    ? {
        tone: notice.value.type === 'success' ? ('ok' as const) : notice.value.type === 'warning' ? ('warn' as const) : ('bad' as const),
        text: notice.value.text,
        action: notice.value.action?.label,
        key: notice.value.key,
      }
    : null,
)

function wrongModel(raw: string, reason: string): Notice {
  const other = models.value.find(
    (m) => m.id !== modelId.value && m.serial_pattern && pickSerial(raw, m.serial_pattern, m.model_no).kind === 'serial',
  )
  if (other) {
    return {
      type: 'warning',
      text: `${reason} It matches model ${other.model_no}.`,
      action: { label: `Switch to ${other.model_no} and add it`, kind: 'switch', modelId: other.id, code: raw },
    }
  }
  const code = raw.replace(/\s+/g, '').toUpperCase()
  return {
    type: 'warning',
    text: `${reason} If this is a different device type, add its model.`,
    action: auth.can('inventory.register') ? { label: 'Add a new model for this code', kind: 'new-model', code } : undefined,
  }
}

async function add(raw: string, fromCamera: boolean): Promise<boolean> {
  if (!raw.replace(/\s+/g, '')) return false
  if (!modelId.value || !model.value) {
    notice.value = { type: 'error', text: 'Choose the model first.' }
    return false
  }
  let serial: string
  if (fromCamera || model.value.serial_pattern) {
    const verdict = pickSerial(raw, model.value.serial_pattern, model.value.model_no)
    if (verdict.kind === 'skip') {
      notice.value = verdict.wrongFormat
        ? wrongModel(raw, verdict.reason)
        : { type: fromCamera ? 'warning' : 'error', text: fromCamera ? `Skipped: ${verdict.reason}` : verdict.reason }
      return false
    }
    serial = verdict.serial
  } else {
    serial = raw.replace(/\s+/g, '').toUpperCase()
  }
  if (checking.has(serial)) return false
  if (fromCamera && removed.has(serial)) {
    notice.value = {
      type: 'warning',
      text: `${serial} was removed from this list.`,
      action: { label: 'Add it again', kind: 're-add', code: serial },
    }
    return false
  }
  removed.delete(serial)
  if (rows.value.some((r) => r.serial_no === serial)) {
    if (fromCamera && rows.value[0]?.serial_no === serial) return false
    notice.value = { type: 'warning', text: `${serial} is already in this list.` }
    return false
  }
  checking.add(serial)
  try {
    const check = await inventoryApi.checkSerial(serial)
    if (check.exists) {
      notice.value = { type: 'error', text: check.message ?? `${serial} is already registered.` }
      return false
    }
  } catch {
    /* the server checks again when the delivery is saved */
  } finally {
    checking.delete(serial)
  }
  if (rows.value.some((r) => r.serial_no === serial)) return false
  rows.value.unshift({
    serial_no: serial,
    model_id: modelId.value,
    warranty_start: null,
    warranty_end: null,
    attributes: { ...commonValues.value },
  })
  notice.value = { type: 'success', text: `Added ${serial} (${rows.value.length} to register).` }
  typed.value = ''
  return true
}

async function addFromPhoto(codes: string[]): Promise<void> {
  const added: string[] = []
  let last: Notice | null = null
  for (const c of codes) {
    if (await add(c, true)) added.push(rows.value[0]!.serial_no)
    else last = notice.value
  }
  if (added.length) {
    const skipped = codes.length - added.length
    notice.value = {
      type: 'success',
      text: `Added ${added.join(', ')}.${skipped ? ` ${skipped} other barcode${skipped === 1 ? '' : 's'} on the label skipped.` : ''}`,
    }
  } else if (codes.length === 1 && last) {
    notice.value = last
  } else {
    notice.value = { type: 'warning', text: `No serial number for ${model.value?.model_no} among: ${codes.join(', ')}.` }
  }
}

async function onAction(): Promise<void> {
  const action = notice.value?.action
  if (!action) return
  if (action.kind === 're-add') {
    const row = removed.get(action.code)
    removed.delete(action.code)
    if (row && !rows.value.some((r) => r.serial_no === row.serial_no)) {
      rows.value.unshift(row)
      notice.value = { type: 'success', text: `Added ${row.serial_no} back (${rows.value.length} to register).` }
    } else if (!row) {
      await add(action.code, false)
    }
    return
  }
  if (action.kind === 'switch') {
    modelId.value = action.modelId
    await add(action.code, true)
  } else {
    newModelSample.value = action.code
    newModelOpen.value = true
  }
}

async function onModelCreated(m: ItemModel): Promise<void> {
  modelId.value = m.id
  const pending = newModelSample.value
  newModelSample.value = ''
  if (step.value !== 'scan') go('scan')
  if (pending) await add(pending, true)
}

function openNewModel(): void {
  newModelSample.value = ''
  newModelOpen.value = true
}

function remove(serial: string): void {
  const row = rows.value.find((r) => r.serial_no === serial)
  rows.value = rows.value.filter((r) => r.serial_no !== serial)
  if (row) removed.set(serial, row)
  notice.value = {
    type: 'warning',
    text: `Removed ${serial}. ${rows.value.length} to register.`,
    action: { label: 'Undo', kind: 're-add', code: serial },
  }
}

function openDetails(serial: string): void {
  const i = rows.value.findIndex((r) => r.serial_no === serial)
  if (i < 0) return
  editing.value = i
  const r = rows.value[i]!
  editBuffer.value = { ...r, attributes: { ...r.attributes } }
}

function saveDetails(): void {
  if (editing.value === null || !editBuffer.value) return
  rows.value[editing.value] = editBuffer.value
  editing.value = null
}

function rowError(serial: string): string | undefined {
  const i = rows.value.findIndex((r) => r.serial_no === serial)
  const hit = Object.entries(errors.value).find(([k]) => k.startsWith(`items.${i}.`))
  return hit?.[1]
}

// ---- saving ----

async function save(): Promise<void> {
  errors.value = {}
  formError.value = null
  rows.value.forEach((r) => {
    r.warranty_start ??= header.warranty_start
    r.warranty_end ??= header.warranty_end
  })
  if (warrantyRequired.value && rows.value.some((r) => !r.warranty_start || !r.warranty_end)) {
    errors.value = {
      warranty_start: header.warranty_start ? '' : 'Enter the warranty start date.',
      warranty_end: header.warranty_end ? '' : 'Enter the warranty end date.',
    }
    formError.value = 'Enter the warranty dates on the Details step. They are required for this equipment.'
    return
  }
  saving.value = true
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
    const result = await inventoryApi.registerDevices(body)
    clearDraft()
    showSuccess(`${result.item_count} item${result.item_count === 1 ? '' : 's'} registered and in stock at ${result.location.name}.`)
    await router.replace({ path: '/inventory', query: { project: String(result.project.id) } })
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

// ---- draft kept in this browser ----

function saveDraft(): void {
  try {
    if (!rows.value.length && !header.project_id) localStorage.removeItem(DRAFT_KEY)
    else localStorage.setItem(DRAFT_KEY, JSON.stringify({ step: step.value, header, modelId: modelId.value, common: common.value, rows: rows.value }))
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

async function startAgain(): Promise<void> {
  try {
    await ElMessageBox.confirm('The items scanned so far will be removed.', 'Start a new registration?', {
      confirmButtonText: 'Start again',
      cancelButtonText: 'Keep',
      type: 'warning',
    })
  } catch {
    return
  }
  clearDraft()
  rows.value = []
  const today = dayjs().format('YYYY-MM-DD')
  Object.assign(header, {
    project_id: null,
    supplier_id: null,
    delivery_order_no: '',
    received_on: today,
    warranty_start: today,
    warranty_end: plusYears(today),
    remarks: '',
  })
  warrantyFollows.value = true
  endFollowsStart.value = true
  modelId.value = null
  restored.value = false
  go('project')
}

watch([rows, modelId, common, step, () => ({ ...header })], saveDraft, { deep: true })

onMounted(async () => {
  try {
    await lk.load(true)
  } catch (e) {
    showError(e)
  }
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (raw) {
      const draft = JSON.parse(raw)
      Object.assign(header, draft.header)
      modelId.value = draft.modelId
      common.value = draft.common ?? {}
      rows.value = draft.rows ?? []
      step.value = draft.step ?? 'project'
      restored.value = rows.value.length > 0
    }
  } catch {
    /* ignore a damaged draft */
  }
  const fromQuery = Number(route.query.project)
  if (!restored.value && fromQuery && lk.data.value?.projects.some((p) => p.id === fromQuery && p.is_active)) {
    header.project_id = fromQuery
    step.value = 'delivery'
  }
  if (!header.location_id && stores.value.length === 1) header.location_id = stores.value[0]!.id
})
</script>

<template>
  <div class="flow">
    <div class="progress" aria-label="Steps">
      <ol>
        <li v-for="(s, i) in STEPS" :key="s.key" :class="{ done: i < stepIndex, current: i === stepIndex }" :aria-current="i === stepIndex ? 'step' : undefined">
          <span class="dot">{{ i < stepIndex ? '✓' : i + 1 }}</span>
          <span class="label">{{ s.label }}</span>
        </li>
      </ol>
    </div>

    <el-alert v-if="restored && step !== 'review'" type="info" :closable="false" show-icon :title="`Continuing the registration you started: ${rows.length} items so far.`">
      <template #default><el-button link type="primary" @click="startAgain">Start a new registration instead</el-button></template>
    </el-alert>

    <!-- 1. Project -->
    <section v-if="step === 'project'" class="step">
      <h2>Which project are the devices for?</h2>
      <el-input v-model="projectQuery" size="large" placeholder="Search name, WBS code or client" clearable />
      <div class="choices">
        <button v-for="p in projects" :key="p.id" type="button" class="choice" :aria-pressed="p.id === header.project_id" @click="chooseProject(p.id)">
          <b>{{ p.name }}</b>
          <small><span class="mono">{{ p.code }}</span><template v-if="p.client_name"> · {{ p.client_name }}</template></small>
        </button>
        <p v-if="!projects.length" class="muted">No active project matches. An administrator adds projects under Administration, Projects.</p>
      </div>
    </section>

    <!-- 2. Delivery -->
    <el-form v-else-if="step === 'delivery'" label-position="top" class="step" @submit.prevent="deliveryNext">
      <h2>Where and when</h2>
      <p class="muted">For {{ project?.name }}</p>
      <el-form-item label="Store" required :error="errors.location_id">
        <div class="choices compact">
          <button v-for="l in stores" :key="l.id" type="button" class="choice" :aria-pressed="l.id === header.location_id" @click="header.location_id = l.id">
            <b>{{ l.name }}</b>
          </button>
        </div>
      </el-form-item>
      <el-form-item label="Received on" required :error="errors.received_on">
        <el-date-picker v-model="header.received_on" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" :clearable="false" size="large" />
      </el-form-item>
      <div class="two">
        <el-form-item label="Warranty start" :required="warrantyRequired" :error="errors.warranty_start">
          <el-date-picker v-model="header.warranty_start" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" size="large" @change="onWarrantyStart" />
        </el-form-item>
        <el-form-item label="Warranty end" :required="warrantyRequired" :error="errors.warranty_end">
          <el-date-picker v-model="header.warranty_end" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" size="large" @change="onWarrantyEnd" />
        </el-form-item>
      </div>
      <p class="muted small">
        The warranty is one year from the received date unless you change it. It applies to every item; you can change it for one item on the Review step.
      </p>
    </el-form>

    <!-- 3. Model -->
    <section v-else-if="step === 'model'" class="step">
      <h2>Which model are you scanning?</h2>
      <p class="muted">If there are several models, scan one model at a time and switch between them.</p>
      <el-input v-model="modelQuery" size="large" placeholder="Search model number or kind of equipment" clearable />
      <div v-for="[cat, list] in modelGroups" :key="cat" class="model-group">
        <span class="group-title">{{ cat }}</span>
        <div class="choices">
          <button v-for="m in list" :key="m.id" type="button" class="choice" :aria-pressed="m.id === modelId" @click="chooseModel(m.id)">
            <b>{{ m.model_no }}</b>
            <small>{{ m.manufacturer ?? '' }}<template v-if="m.manufacturer"> · </template>{{ describeFormat(m.serial_pattern) }}</small>
          </button>
        </div>
      </div>
      <button v-if="auth.can('inventory.register')" type="button" class="choice add" @click="openNewModel">
        <b>+ Add a new model</b>
        <small>For a device type that is not in the list yet</small>
      </button>
    </section>

    <!-- 4. Scan -->
    <section v-else-if="step === 'scan'" class="step scan-step">
      <BarcodeScanner :feedback="scanFeedback" :caption="model ? `Scanning ${modelLabel(model.id)}` : ''" @code="(c) => add(c, true)" @codes="addFromPhoto" @action="onAction" @close="go('review')" />
      <div class="scanned">
        <div class="scanned-head">
          <b>{{ rows.length }} scanned</b>
          <span class="muted small">{{ counts.map((c) => `${c.n} × ${c.label.split(' · ')[0]}`).join(' · ') }}</span>
          <el-button v-if="rows.length > 3" link type="primary" @click="listOpen = true">View all</el-button>
        </div>
        <ol class="rows">
          <li v-for="r in rows.slice(0, 3)" :key="r.serial_no">
            <span class="mono serial">{{ r.serial_no }}</span>
            <span class="muted small grow">{{ modelLabel(r.model_id).split(' · ')[0] }}</span>
            <el-button link type="danger" :aria-label="`Remove ${r.serial_no}`" @click="remove(r.serial_no)">Remove</el-button>
          </li>
        </ol>
      </div>
      <el-input v-model="typed" size="large" placeholder="Or type a serial number" aria-label="Serial number" autocapitalize="characters" @keyup.enter="add(typed, false)">
        <template #append><el-button @click="add(typed, false)">Add</el-button></template>
      </el-input>
      <div class="tools">
        <el-button @click="go('model')">Change model</el-button>
        <el-button v-if="category?.fields.some((f) => !f.retired)" @click="commonOpen = true">Same details for every {{ model?.model_no }}</el-button>
      </div>
    </section>

    <!-- 5. Review -->
    <section v-else class="step">
      <h2>Check and save</h2>
      <div class="summary">
        <div><span>Project</span><b>{{ project?.name }}</b><button type="button" class="edit" @click="go('project')">Change</button></div>
        <div>
          <span>Details</span>
          <b>{{ store?.name }} · {{ fmtDate(header.received_on) }}</b>
          <small class="muted">
            Warranty {{ header.warranty_start ? `${fmtDate(header.warranty_start)} – ${fmtDate(header.warranty_end)}` : 'not entered' }}
          </small>
          <button type="button" class="edit" @click="go('delivery')">Change</button>
        </div>
        <div>
          <span>Items</span>
          <b>{{ rows.length }}</b>
          <small class="muted">{{ counts.map((c) => `${c.n} × ${c.label}`).join(' · ') || 'None yet' }}</small>
          <button type="button" class="edit" @click="go('scan')">Scan more</button>
        </div>
      </div>
      <p v-if="errors.warranty_start || errors.warranty_end" class="err">{{ errors.warranty_start || errors.warranty_end }}</p>
      <el-form-item label="Remarks" class="remarks">
        <el-input v-model="header.remarks" type="textarea" :autosize="{ minRows: 2 }" maxlength="2000" placeholder="Optional" />
      </el-form-item>
      <ol class="rows full">
        <li v-for="r in rows" :key="r.serial_no" :class="{ bad: rowError(r.serial_no) }">
          <div class="grow stack">
            <span class="mono serial">{{ r.serial_no }}</span>
            <span class="muted small">{{ modelLabel(r.model_id) }}</span>
            <div v-if="rowError(r.serial_no)" class="err small">{{ rowError(r.serial_no) }}</div>
          </div>
          <el-button size="small" @click="openDetails(r.serial_no)">Details</el-button>
          <el-button size="small" link type="danger" @click="remove(r.serial_no)">Remove</el-button>
        </li>
      </ol>
      <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
    </section>

    <div class="bar">
      <el-button size="large" @click="back">{{ stepIndex === 0 ? 'Cancel' : 'Back' }}</el-button>
      <el-button v-if="step === 'delivery'" size="large" type="primary" @click="deliveryNext">Next</el-button>
      <el-button v-else-if="step === 'scan'" size="large" type="primary" :disabled="!rows.length" @click="go('review')">Review ({{ rows.length }})</el-button>
      <el-button v-else-if="step === 'review'" size="large" type="primary" :loading="saving" :disabled="!rows.length" @click="save">Save</el-button>
      <el-button v-else-if="step === 'model' && modelId" size="large" type="primary" @click="go('scan')">Continue scanning</el-button>
      <span v-else />
    </div>

    <el-drawer v-model="commonOpen" direction="btt" size="80%" :title="`Same details for every ${model?.model_no}`" append-to-body>
      <SensitiveNote text="Record equipment details only. Do not enter passwords, IP addresses or network details." />
      <el-form label-position="top">
        <AttributeFields v-model="commonValues" :fields="category?.fields ?? []" id-prefix="common" />
      </el-form>
      <p class="muted small">Applied to the items you scan from now on. Items already scanned keep their details.</p>
      <template #footer><el-button size="large" type="primary" class="wide" @click="commonOpen = false">Done</el-button></template>
    </el-drawer>

    <el-drawer v-model="listOpen" direction="btt" size="85%" :title="`${rows.length} scanned`" append-to-body>
      <ol class="rows full">
        <li v-for="r in rows" :key="r.serial_no">
          <span class="mono serial grow">{{ r.serial_no }}</span>
          <span class="muted small">{{ modelLabel(r.model_id).split(' · ')[0] }}</span>
          <el-button link type="danger" @click="remove(r.serial_no)">Remove</el-button>
        </li>
      </ol>
    </el-drawer>

    <el-drawer :model-value="editing !== null" direction="btt" size="85%" :title="editBuffer ? `Details for ${editBuffer.serial_no}` : ''" append-to-body @close="editing = null">
      <el-form v-if="editBuffer" label-position="top">
        <div class="two">
          <el-form-item label="Warranty start">
            <el-date-picker v-model="editBuffer.warranty_start" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" :placeholder="`As on Details: ${fmtDate(header.warranty_start)}`" />
          </el-form-item>
          <el-form-item label="Warranty end">
            <el-date-picker v-model="editBuffer.warranty_end" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" :placeholder="`As on Details: ${fmtDate(header.warranty_end)}`" />
          </el-form-item>
        </div>
        <AttributeFields v-model="editBuffer.attributes" :fields="lk.categoryOfModel(editBuffer.model_id)?.fields ?? []" id-prefix="row" />
      </el-form>
      <template #footer><el-button size="large" type="primary" class="wide" @click="saveDetails">Done</el-button></template>
    </el-drawer>

    <NewModelDialog v-model="newModelOpen" :sample="newModelSample" :category-id="category?.id ?? null" @created="onModelCreated" />
  </div>
</template>

<style scoped>
.flow {
  max-width: 720px;
  width: 100%;
  margin: 0 auto;
  display: grid;
  gap: 14px;
  padding-bottom: calc(76px + env(safe-area-inset-bottom, 0px));
}
.progress ol {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 4px;
}
.progress li {
  display: grid;
  justify-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--erf-muted);
  position: relative;
}
.progress li:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 13px;
  left: calc(50% + 16px);
  right: calc(-50% + 16px);
  height: 2px;
  background: var(--erf-line);
}
.progress li.done:not(:last-child)::after {
  background: var(--erf-ok);
}
.dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-weight: 600;
  font-size: 13px;
  background: var(--erf-surface);
  border: 2px solid var(--erf-line);
}
.progress li.current {
  color: var(--erf-fg);
  font-weight: 600;
}
.progress li.current .dot {
  border-color: var(--erf-accent);
  color: var(--erf-accent);
}
.progress li.done .dot {
  background: var(--erf-ok);
  border-color: var(--erf-ok);
  color: #fff;
}
.step {
  display: grid;
  gap: 12px;
  align-content: start;
}
.step h2 {
  font-size: 19px;
  margin: 0;
}
.step > .muted {
  margin: -6px 0 0;
}
.small {
  font-size: 13px;
}
.choices {
  display: grid;
  gap: 8px;
  width: 100%;
}
.choice {
  display: grid;
  gap: 2px;
  text-align: left;
  font: inherit;
  color: inherit;
  background: var(--erf-surface);
  border: 1px solid var(--erf-line);
  border-radius: 12px;
  padding: 14px 16px;
  cursor: pointer;
}
.choice b {
  font-size: 16px;
}
.choice small {
  color: var(--erf-muted);
  font-size: 13px;
}
.choice[aria-pressed='true'] {
  border-color: var(--erf-accent);
  box-shadow: inset 0 0 0 1px var(--erf-accent);
}
.choice.add {
  border-style: dashed;
}
.choice.add b {
  color: var(--erf-accent);
}
.compact .choice {
  padding: 10px 14px;
}
.model-group {
  display: grid;
  gap: 6px;
}
.group-title {
  font-family: var(--erf-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--erf-muted);
}
.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 12px;
}
.step :deep(.el-date-editor),
.step :deep(.el-select),
.two :deep(.el-date-editor) {
  width: 100%;
}
.tools {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tools .el-button + .el-button {
  margin-left: 0;
}
.scanned {
  display: grid;
  gap: 6px;
}
.scanned-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
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
  gap: 8px;
  border: 1px solid var(--erf-line);
  border-radius: 10px;
  padding: 8px 12px;
  background: var(--erf-surface);
}
.rows li.bad {
  border-color: var(--erf-bad);
}
.serial {
  font-size: 14px;
  font-weight: 600;
}
.grow {
  flex: 1;
  min-width: 0;
}
.stack {
  display: grid;
  gap: 2px;
  overflow-wrap: anywhere;
}
.summary {
  display: grid;
  gap: 1px;
  background: var(--erf-line);
  border: 1px solid var(--erf-line);
  border-radius: 12px;
  overflow: hidden;
}
.summary > div {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr) auto;
  gap: 2px 10px;
  align-items: baseline;
  background: var(--erf-surface);
  padding: 12px 14px;
}
.summary span {
  color: var(--erf-muted);
  font-size: 13px;
}
.summary small {
  grid-column: 2;
}
.summary .edit {
  grid-column: 3;
  grid-row: 1;
  font: inherit;
  font-size: 13px;
  color: var(--erf-accent);
  background: none;
  border: 0;
  cursor: pointer;
}
.remarks {
  margin: 0;
}
.err {
  color: var(--erf-bad);
  margin: 0;
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
  .flow {
    padding-bottom: 0;
  }
}
.wide {
  width: 100%;
}
</style>
