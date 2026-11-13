<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'
import { fmtDate, fmtDateTime } from '@/utils/format'

import { inventoryApi } from '../api'
import AttributeFields from '../components/AttributeFields.vue'
import ItemStatusTag from '../components/ItemStatusTag.vue'
import { ACTION_LABEL, MOVEMENT_LABEL, showValue } from '../format'
import { useInventoryLookups } from '../lookups'
import type { AttributeValue, ItemAction, ItemDetail } from '../types'

const route = useRoute()
const auth = useAuthStore()
const lk = useInventoryLookups()
const item = ref<ItemDetail | null>(null)
// Changing a saved item is a separate permission from registering it.
const canEdit = computed(() => auth.can('inventory.edit'))
const fields = computed(() => lk.category(item.value?.category_id)?.fields ?? [])
const shownFields = computed(() => fields.value.filter((f) => !f.retired || item.value?.attributes[f.key] != null))

const editOpen = ref(false)
const edit = ref<{ warranty_start: string | null; warranty_end: string | null; attributes: Record<string, AttributeValue>; remarks: string }>({
  warranty_start: null,
  warranty_end: null,
  attributes: {},
  remarks: '',
})
const editErrors = ref<Record<string, string>>({})
const editError = ref<string | null>(null)
const saving = ref(false)

const action = ref<ItemAction | null>(null)
const actionLocation = ref<number | null>(null)
const actionReason = ref('')
const actionErrors = ref<Record<string, string>>({})
const actionError = ref<string | null>(null)

const needsLocation = computed(() => action.value === 'move' || action.value === 'repaired')
const needsReason = computed(() => action.value === 'report_fault' || action.value === 'dispose')
const locationChoices = computed(() =>
  (lk.data.value?.locations ?? []).filter(
    (l) => l.is_active && (action.value === 'repaired' ? l.kind === 'STORE' : l.id !== item.value?.location.id),
  ),
)

async function load(): Promise<void> {
  try {
    await lk.load()
    item.value = await inventoryApi.item(Number(route.params.id))
  } catch (e) {
    showError(e)
  }
}
watch(() => route.params.id, load, { immediate: true })

function openEdit(): void {
  if (!item.value) return
  edit.value = {
    warranty_start: item.value.warranty_start,
    warranty_end: item.value.warranty_end,
    attributes: { ...item.value.attributes },
    remarks: item.value.remarks ?? '',
  }
  editErrors.value = {}
  editError.value = null
  editOpen.value = true
}

async function saveEdit(): Promise<void> {
  if (!item.value) return
  saving.value = true
  try {
    item.value = await inventoryApi.updateItem(item.value.id, {
      version: item.value.version,
      warranty_start: edit.value.warranty_start,
      warranty_end: edit.value.warranty_end,
      attributes: edit.value.attributes,
      remarks: edit.value.remarks.trim() || null,
    })
    editOpen.value = false
    showSuccess('Details saved.')
  } catch (e) {
    editErrors.value = fieldErrors(e)
    editError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

function openAction(a: ItemAction): void {
  action.value = a
  actionLocation.value = null
  actionReason.value = ''
  actionErrors.value = {}
  actionError.value = null
}

async function runAction(): Promise<void> {
  if (!item.value || !action.value) return
  saving.value = true
  try {
    item.value = await inventoryApi.act(item.value.id, action.value, {
      version: item.value.version,
      location_id: actionLocation.value,
      reason: actionReason.value.trim() || null,
    })
    showSuccess(`${ACTION_LABEL[action.value]}: done.`)
    action.value = null
  } catch (e) {
    actionErrors.value = fieldErrors(e)
    actionError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
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
        <RouterLink :to="`/inventory/projects/${item.project.id}`" class="back">{{ item.project.name }}</RouterLink>
        <h1 class="mono serial">{{ item.serial_no }}</h1>
        <p class="sub">{{ item.category_name }} · {{ item.model_no }} · <ItemStatusTag :status="item.status" /></p>
      </div>
      <div v-if="canEdit" class="actions">
        <el-button @click="openEdit">Edit details</el-button>
        <el-dropdown v-if="item.actions.length" trigger="click" @command="openAction">
          <el-button type="primary">Record a change</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="a in item.actions" :key="a" :command="a">{{ ACTION_LABEL[a] }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <div class="cols">
      <section class="panel">
        <h2>Details</h2>
        <dl class="facts">
          <div><dt>Project</dt><dd><RouterLink :to="`/inventory/projects/${item.project.id}`">{{ item.project.name }}</RouterLink> <span class="muted mono">{{ item.project.code }}</span></dd></div>
          <div><dt>Location</dt><dd>{{ item.location.name }}</dd></div>
          <div v-if="item.holder"><dt>Held by</dt><dd>{{ item.holder.display_name }}</dd></div>
          <div><dt>Warranty</dt><dd>{{ fmtDate(item.warranty_start) }} – {{ fmtDate(item.warranty_end) }}</dd></div>
          <div><dt>Delivery</dt><dd class="mono">{{ item.delivery_no ?? '—' }}</dd></div>
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
            <div v-if="m.delivery_no" class="small">Delivery <span class="mono">{{ m.delivery_no }}</span><template v-if="m.to_location"> to {{ m.to_location }}</template></div>
            <div v-else-if="m.to_location && m.to_location !== m.from_location" class="small">{{ m.from_location }} → {{ m.to_location }}</div>
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
          <el-form-item label="Warranty start" :error="editErrors.warranty_start">
            <el-date-picker v-model="edit.warranty_start" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" />
          </el-form-item>
          <el-form-item label="Warranty end" :error="editErrors.warranty_end">
            <el-date-picker v-model="edit.warranty_end" type="date" value-format="YYYY-MM-DD" format="D MMM YYYY" />
          </el-form-item>
        </div>
        <AttributeFields v-model="edit.attributes" :fields="fields" :errors="editErrors" id-prefix="edit" />
        <el-form-item label="Remarks" for="edit-remarks">
          <el-input id="edit-remarks" v-model="edit.remarks" type="textarea" :autosize="{ minRows: 2 }" maxlength="2000" />
        </el-form-item>
        <el-alert v-if="editError" :title="editError" type="error" :closable="false" show-icon />
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">Save</el-button>
      </template>
    </el-dialog>

    <el-dialog :model-value="action !== null" :title="action ? ACTION_LABEL[action] : ''" width="min(520px, 96vw)" @close="action = null">
      <el-form label-position="top">
        <el-form-item v-if="needsLocation" :label="action === 'repaired' ? 'Back to which store?' : 'New location'" required :error="actionErrors.location_id" for="act-location">
          <el-select id="act-location" v-model="actionLocation" placeholder="Choose" style="width: 100%">
            <el-option v-for="l in locationChoices" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="needsReason ? 'Reason' : 'Comment (optional)'" :required="needsReason" :error="actionErrors.reason" for="act-reason">
          <el-input id="act-reason" v-model="actionReason" type="textarea" :autosize="{ minRows: 2 }" maxlength="2000" />
        </el-form-item>
        <p v-if="action === 'dispose'" class="muted small">Writing off is final. The item stays in the records with its history.</p>
        <el-alert v-if="actionError" :title="actionError" type="error" :closable="false" show-icon />
      </el-form>
      <template #footer>
        <el-button @click="action = null">Cancel</el-button>
        <el-button :type="action === 'dispose' ? 'danger' : 'primary'" :loading="saving" @click="runAction">Confirm</el-button>
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
