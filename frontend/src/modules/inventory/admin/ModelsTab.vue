<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'

import { inventoryApi } from '../api'
import { useInventoryLookups } from '../lookups'
import type { ItemModel, Supplier } from '../types'

const lk = useInventoryLookups()
const loading = ref(true)
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)

const modelDialog = ref(false)
const editingModel = ref<ItemModel | null>(null)
const model = reactive({ category_id: 0, model_no: '', name: '', manufacturer: '', serial_pattern: '', is_active: true })

const supplierDialog = ref(false)
const editingSupplier = ref<Supplier | null>(null)
const supplier = reactive({ name: '', is_active: true })

const categoryName = (id: number) => lk.category(id)?.name ?? '—'
const models = computed(() => lk.data.value?.models ?? [])
const suppliers = computed(() => lk.data.value?.suppliers ?? [])
const testSerial = ref('')
const patternResult = computed(() => {
  if (!model.serial_pattern || !testSerial.value) return null
  try {
    return new RegExp(`^(?:${model.serial_pattern})$`).test(testSerial.value.replace(/\s+/g, '').toUpperCase())
  } catch {
    return 'invalid'
  }
})

async function load(): Promise<void> {
  loading.value = true
  try {
    await lk.load(true)
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function openModel(row: ItemModel | null): void {
  editingModel.value = row
  Object.assign(model, {
    category_id: row?.category_id ?? lk.data.value?.categories[0]?.id ?? 0,
    model_no: row?.model_no ?? '',
    name: row?.name ?? '',
    manufacturer: row?.manufacturer ?? '',
    serial_pattern: row?.serial_pattern ?? '',
    is_active: row?.is_active ?? true,
  })
  testSerial.value = ''
  errors.value = {}
  formError.value = null
  modelDialog.value = true
}

function openSupplier(row: Supplier | null): void {
  editingSupplier.value = row
  Object.assign(supplier, { name: row?.name ?? '', is_active: row?.is_active ?? true })
  errors.value = {}
  formError.value = null
  supplierDialog.value = true
}

async function run(task: () => Promise<unknown>, done: string, close: () => void): Promise<void> {
  saving.value = true
  errors.value = {}
  formError.value = null
  try {
    await task()
    showSuccess(done)
    close()
    await load()
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

const saveModel = () =>
  run(
    () =>
      inventoryApi.saveModel(
        {
          ...model,
          name: model.name.trim() || null,
          manufacturer: model.manufacturer.trim() || null,
          serial_pattern: model.serial_pattern.trim() || null,
        },
        editingModel.value?.id,
      ),
    'Model saved.',
    () => (modelDialog.value = false),
  )
const saveSupplier = () =>
  run(() => inventoryApi.saveSupplier({ ...supplier }, editingSupplier.value?.id), 'Supplier saved.', () => (supplierDialog.value = false))

onMounted(load)
</script>

<template>
  <div class="tab">
    <div class="bar">
      <h3>Models</h3>
      <el-button type="primary" @click="openModel(null)">Add model</el-button>
    </div>
    <el-table v-loading="loading" :data="models">
      <el-table-column label="Model number" min-width="140"><template #default="{ row }"><b>{{ row.model_no }}</b></template></el-table-column>
      <el-table-column label="Category" min-width="130"><template #default="{ row }">{{ categoryName(row.category_id) }}</template></el-table-column>
      <el-table-column label="Manufacturer" min-width="140"><template #default="{ row }">{{ row.manufacturer ?? '—' }}</template></el-table-column>
      <el-table-column label="Serial number format" min-width="180"><template #default="{ row }"><span class="mono">{{ row.serial_pattern ?? 'Any' }}</span></template></el-table-column>
      <el-table-column label="Status" width="110">
        <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? 'Active' : 'Inactive' }}</el-tag></template>
      </el-table-column>
      <el-table-column width="90" align="right"><template #default="{ row }"><el-button size="small" @click="openModel(row as ItemModel)">Edit</el-button></template></el-table-column>
    </el-table>

    <div class="bar">
      <h3>Suppliers</h3>
      <el-button @click="openSupplier(null)">Add supplier</el-button>
    </div>
    <el-table v-loading="loading" :data="suppliers">
      <el-table-column prop="name" label="Supplier" min-width="220" />
      <el-table-column label="Status" width="110">
        <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? 'Active' : 'Inactive' }}</el-tag></template>
      </el-table-column>
      <el-table-column width="90" align="right"><template #default="{ row }"><el-button size="small" @click="openSupplier(row as Supplier)">Edit</el-button></template></el-table-column>
    </el-table>

    <el-dialog v-model="modelDialog" :title="editingModel ? `Edit ${editingModel.model_no}` : 'Add model'" width="min(520px, 94vw)">
      <el-form label-position="top" @submit.prevent="saveModel">
        <el-form-item label="Category" required :error="errors.category_id">
          <el-select v-model="model.category_id">
            <el-option v-for="c in lk.data.value?.categories ?? []" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Model number" required :error="errors.model_no" for="m-no"><el-input id="m-no" v-model="model.model_no" maxlength="64" /></el-form-item>
        <el-form-item label="Name" for="m-name"><el-input id="m-name" v-model="model.name" maxlength="120" placeholder="Optional" /></el-form-item>
        <el-form-item label="Manufacturer" for="m-maker"><el-input id="m-maker" v-model="model.manufacturer" maxlength="120" placeholder="Optional" /></el-form-item>
        <el-form-item label="Serial number format" :error="errors.serial_pattern" for="m-pattern">
          <el-input id="m-pattern" v-model="model.serial_pattern" maxlength="120" class="mono" placeholder="Optional, for example FRX[0-9]{2}[A-Z][0-9]{4}" />
          <div class="muted hint">
            When set, scanning keeps only codes in this format, so other barcodes on the label are ignored. It uses the regular
            expression notation; ask the administrator who set up the system if you need help.
          </div>
        </el-form-item>
        <el-form-item v-if="model.serial_pattern" label="Try a serial number" for="m-test">
          <el-input id="m-test" v-model="testSerial" placeholder="Type a real serial number" />
          <div v-if="patternResult !== null" class="hint" :class="patternResult === true ? 'ok' : 'bad'">
            {{ patternResult === 'invalid' ? 'The format is not valid.' : patternResult ? 'Matches the format.' : 'Does not match the format.' }}
          </div>
        </el-form-item>
        <el-form-item label="Status"><el-switch v-model="model.is_active" active-text="Active" inactive-text="Inactive" /></el-form-item>
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
      </el-form>
      <template #footer>
        <el-button @click="modelDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="saveModel">Save</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="supplierDialog" :title="editingSupplier ? `Edit ${editingSupplier.name}` : 'Add supplier'" width="min(440px, 94vw)">
      <el-form label-position="top" @submit.prevent="saveSupplier">
        <el-form-item label="Name" required :error="errors.name" for="s-name"><el-input id="s-name" v-model="supplier.name" maxlength="120" /></el-form-item>
        <el-form-item label="Status"><el-switch v-model="supplier.is_active" active-text="Active" inactive-text="Inactive" /></el-form-item>
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
      </el-form>
      <template #footer>
        <el-button @click="supplierDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="saveSupplier">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.tab {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
}
.bar h3 {
  margin: 0;
  font-size: 15px;
}
.hint {
  font-size: 12.5px;
  width: 100%;
  margin-top: 4px;
  line-height: 1.45;
}
.ok {
  color: var(--erf-ok);
}
.bad {
  color: var(--erf-bad);
}
:deep(.el-select) {
  width: 100%;
}
</style>
