<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'
import { fmtDate, fmtDateTime } from '@/utils/format'

import { inventoryApi } from '../api'
import AttributeFields from '../components/AttributeFields.vue'
import ItemStatusTag from '../components/ItemStatusTag.vue'
import { MOVEMENT_LABEL, WITHDRAWAL_STATUS_LABEL, showValue } from '../format'
import { useInventoryLookups } from '../lookups'
import type { AttributeValue, ItemDetail } from '../types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const lk = useInventoryLookups()
const item = ref<ItemDetail | null>(null)

const live = computed(() => !!item.value && !item.value.deleted_at)
const can = (p: string) => live.value && auth.can(p)
const fields = computed(() => lk.category(item.value?.category_id)?.fields ?? [])
const shownFields = computed(() => fields.value.filter((f) => !f.retired || item.value?.attributes[f.key] != null))
const stores = computed(() => (lk.data.value?.locations ?? []).filter((l) => l.kind === 'STORE' && l.is_active))

// ---- edit ----
const editOpen = ref(false)
const edit = ref<{ warranty_start: string | null; warranty_end: string | null; attributes: Record<string, AttributeValue>; remarks: string }>({
  warranty_start: null,
  warranty_end: null,
  attributes: {},
  remarks: '',
})
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const saving = ref(false)

// ---- delete and return ----
const deleteOpen = ref(false)
const deleteReason = ref('')
const returnOpen = ref(false)
const returnStore = ref<number | null>(null)
const returnReason = ref('')

async function load(): Promise<void> {
  try {
    await lk.load()
    item.value = await inventoryApi.item(Number(route.params.id))
  } catch (e) {
    showError(e)
  }
}
watch(() => route.params.id, load, { immediate: true })

function reset(): void {
  errors.value = {}
  formError.value = null
}

function openEdit(): void {
  if (!item.value) return
  edit.value = {
    warranty_start: item.value.warranty_start,
    warranty_end: item.value.warranty_end,
    attributes: { ...item.value.attributes },
    remarks: item.value.remarks ?? '',
  }
  reset()
  editOpen.value = true
}

async function run(task: () => Promise<ItemDetail>, done: string, close: () => void): Promise<void> {
  saving.value = true
  reset()
  try {
    item.value = await task()
    close()
    showSuccess(done)
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

const saveEdit = () =>
  run(
    () =>
      inventoryApi.updateItem(item.value!.id, {
        version: item.value!.version,
        warranty_start: edit.value.warranty_start,
        warranty_end: edit.value.warranty_end,
        attributes: edit.value.attributes,
        remarks: edit.value.remarks.trim() || null,
      }),
    'Details saved.',
    () => (editOpen.value = false),
  )

const confirmDelete = () =>
  run(
    () => inventoryApi.deleteItem(item.value!.id, item.value!.version, deleteReason.value.trim()),
    'Item deleted. It no longer appears in the inventory.',
    () => (deleteOpen.value = false),
  )

const confirmReturn = () =>
  run(
    () => inventoryApi.returnItem(item.value!.id, item.value!.version, returnStore.value!, returnReason.value.trim() || null),
    'Returned to stock.',
    () => (returnOpen.value = false),
  )

function openDelete(): void {
  deleteReason.value = ''
  reset()
  deleteOpen.value = true
}

function openReturn(): void {
  returnStore.value = stores.value.length === 1 ? stores.value[0]!.id : null
  returnReason.value = ''
  reset()
  returnOpen.value = true
}

function requestWithdrawal(): void {
  if (!item.value) return
  router.push({ path: '/inventory/withdrawals/new', query: { project: String(item.value.project.id), items: String(item.value.id) } })
}

function changeText(c: { from: AttributeValue; to: AttributeValue }): string {
  const show = (v: AttributeValue) => (v === null || v === '' ? 'empty' : typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v))
  return `${show(c.from)} → ${show(c.to)}`
}
</script>

<template>
  <div v-if="item" class="page">
    <div class="page-head">
      <div>
        <RouterLink :to="{ path: '/inventory', query: { project: String(item.project.id) } }" class="back">{{ item.project.name }}</RouterLink>
        <h1 class="mono serial">{{ item.serial_no }}</h1>
        <p class="sub">{{ item.category_name }} · {{ item.model_no }} · <ItemStatusTag :status="item.status" /></p>
      </div>
      <div class="actions">
        <el-button v-if="can('inventory.withdraw') && item.status === 'IN_STOCK'" type="primary" @click="requestWithdrawal">Request withdrawal</el-button>
        <el-button v-if="can('inventory.return') && item.status === 'DEPLOYED'" type="primary" @click="openReturn">Return to stock</el-button>
        <el-button v-if="can('inventory.edit')" @click="openEdit">Edit</el-button>
        <el-button v-if="can('inventory.delete') && item.status !== 'REQUESTED'" type="danger" plain @click="openDelete">Delete</el-button>
      </div>
    </div>

    <el-alert v-if="item.deleted_at" type="error" :closable="false" show-icon :title="`Deleted on ${fmtDateTime(item.deleted_at)} by ${item.deleted_by?.display_name ?? 'someone'}`">
      <template #default>{{ item.delete_reason }}. The item no longer appears in the inventory; its record and history are kept.</template>
    </el-alert>
    <el-alert v-else-if="item.open_withdrawal" type="info" :closable="false" show-icon>
      <template #title>
        In withdrawal request
        <RouterLink :to="`/inventory/withdrawals/${item.open_withdrawal.id}`">{{ item.open_withdrawal.request_no }}</RouterLink>
        · {{ WITHDRAWAL_STATUS_LABEL[item.open_withdrawal.status] }}
      </template>
    </el-alert>

    <div class="cols">
      <section class="panel">
        <h2>Details</h2>
        <dl class="facts">
          <div><dt>Project</dt><dd>{{ item.project.name }} <span class="muted mono">{{ item.project.code }}</span></dd></div>
          <div><dt>Location</dt><dd>{{ item.location.name }}</dd></div>
          <div><dt>Warranty</dt><dd>{{ fmtDate(item.warranty_start) }} – {{ fmtDate(item.warranty_end) }}</dd></div>
          <div v-for="f in shownFields" :key="f.key">
            <dt>{{ f.label }}<span v-if="f.retired" class="muted"> (retired)</span></dt>
            <dd>{{ showValue(f, item.attributes[f.key]) }}</dd>
          </div>
          <div v-if="item.remarks" class="full"><dt>Remarks</dt><dd class="pre">{{ item.remarks }}</dd></div>
        </dl>
      </section>

      <section class="panel">
        <h2>History</h2>
        <ol class="timeline">
          <li v-for="m in item.history" :key="m.id">
            <div class="what">
              <b>{{ MOVEMENT_LABEL[m.kind] ?? m.kind }}</b>
              <span class="muted small">{{ fmtDateTime(m.occurred_at) }} · {{ m.actor.display_name }}</span>
            </div>
            <div v-if="m.to_location && m.to_location !== m.from_location" class="small">
              {{ m.from_location ? `${m.from_location} → ${m.to_location}` : m.to_location }}
            </div>
            <div v-if="m.withdrawal_no" class="small">
              Request <RouterLink :to="`/inventory/withdrawals/${m.withdrawal_id}`">{{ m.withdrawal_no }}</RouterLink>
            </div>
            <ul v-if="m.changes" class="changes small">
              <li v-for="(c, label) in m.changes" :key="label"><b>{{ label }}</b>: {{ changeText(c) }}</li>
            </ul>
            <div v-if="m.reason" class="reason small">{{ m.reason }}</div>
          </li>
        </ol>
      </section>
    </div>

    <el-dialog v-model="editOpen" :title="`Edit ${item.serial_no}`" width="min(680px, 96vw)">
      <el-form label-position="top">
        <div class="grid">
          <el-form-item label="Warranty start" :error="errors.warranty_start">
            <el-date-picker v-model="edit.warranty_start" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" />
          </el-form-item>
          <el-form-item label="Warranty end" :error="errors.warranty_end">
            <el-date-picker v-model="edit.warranty_end" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" />
          </el-form-item>
        </div>
        <AttributeFields v-model="edit.attributes" :fields="fields" :errors="errors" id-prefix="edit" />
        <el-form-item label="Remarks" for="edit-remarks">
          <el-input id="edit-remarks" v-model="edit.remarks" type="textarea" :autosize="{ minRows: 2 }" maxlength="2000" />
        </el-form-item>
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">Save</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="returnOpen" :title="`Return ${item.serial_no} to stock`" width="min(480px, 96vw)">
      <el-form label-position="top">
        <el-form-item label="Store" required :error="errors.location_id">
          <el-select v-model="returnStore" placeholder="Choose the store" style="width: 100%">
            <el-option v-for="l in stores" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Comment (optional)" for="ret-reason">
          <el-input id="ret-reason" v-model="returnReason" type="textarea" :autosize="{ minRows: 2 }" maxlength="2000" />
        </el-form-item>
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
      </el-form>
      <template #footer>
        <el-button @click="returnOpen = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" :disabled="!returnStore" @click="confirmReturn">Return to stock</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="deleteOpen" :title="`Delete ${item.serial_no}?`" width="min(480px, 96vw)">
      <p class="muted">The item disappears from the inventory. Its record and history are kept, so the deletion can be traced.</p>
      <el-form label-position="top">
        <el-form-item label="Reason" required :error="errors.reason" for="del-reason">
          <el-input id="del-reason" v-model="deleteReason" type="textarea" :autosize="{ minRows: 2 }" maxlength="2000" placeholder="For example: registered twice by mistake" />
        </el-form-item>
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
      </el-form>
      <template #footer>
        <el-button @click="deleteOpen = false">Cancel</el-button>
        <el-button type="danger" :loading="saving" :disabled="!deleteReason.trim()" @click="confirmDelete">Delete</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.back {
  font-size: 13px;
  text-decoration: none;
}
.back::before {
  content: '‹ ';
}
.serial {
  font-size: 24px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.actions .el-button + .el-button {
  margin-left: 0;
}
.cols {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
@media (max-width: 860px) {
  .cols {
    grid-template-columns: minmax(0, 1fr);
  }
}
.facts {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px 20px;
}
.facts dt {
  font-size: 12px;
  color: var(--erf-muted);
}
.facts dd {
  margin: 2px 0 0;
  overflow-wrap: anywhere;
}
.facts .full {
  grid-column: 1 / -1;
}
.small {
  font-size: 12.5px;
}
.timeline {
  list-style: none;
  margin: 0;
  padding: 0 0 0 14px;
  border-left: 2px solid var(--erf-line);
  display: grid;
  gap: 14px;
}
.timeline > li {
  position: relative;
  display: grid;
  gap: 3px;
}
.timeline > li::before {
  content: '';
  position: absolute;
  left: -20px;
  top: 6px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--erf-surface);
  border: 2px solid var(--erf-accent);
}
.what {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 10px;
  align-items: baseline;
}
.changes {
  margin: 0;
  padding-left: 16px;
}
.reason {
  background: var(--erf-surface-2);
  border-radius: 6px;
  padding: 6px 10px;
  white-space: pre-wrap;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0 16px;
}
.grid :deep(.el-date-editor) {
  width: 100%;
}
</style>
