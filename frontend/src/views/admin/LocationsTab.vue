<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { orgApi } from '@/api'
import type { Location, LocationKind } from '@/types/api'
import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'

const KINDS: { value: LocationKind; label: string; hint: string }[] = [
  { value: 'STORE', label: 'Store', hint: 'Deliveries are received into stores, and repaired items return to one.' },
  { value: 'SITE', label: 'Site', hint: 'A customer or project site where equipment is installed.' },
  { value: 'REPAIR', label: 'Repair centre', hint: 'Where faulty items are repaired.' },
  { value: 'OTHER', label: 'Other', hint: '' },
]
const kindLabel = (k: string) => KINDS.find((x) => x.value === k)?.label ?? k

const rows = ref<Location[]>([])
const loading = ref(true)
const dialog = ref(false)
const editing = ref<Location | null>(null)
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const form = reactive({ name: '', kind: 'STORE' as LocationKind, is_active: true })

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await orgApi.locations()
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function open(row: Location | null): void {
  editing.value = row
  Object.assign(form, row ? { name: row.name, kind: row.kind, is_active: row.is_active } : { name: '', kind: 'STORE', is_active: true })
  errors.value = {}
  formError.value = null
  dialog.value = true
}

async function save(): Promise<void> {
  saving.value = true
  errors.value = {}
  formError.value = null
  try {
    await orgApi.saveLocation({ ...form }, editing.value?.id)
    showSuccess('Location saved.')
    dialog.value = false
    await load()
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="tab">
    <div class="bar">
      <p class="muted intro">Stores, sites and repair centres where equipment can be. Stores are shared by all projects; each item still belongs to its project.</p>
      <el-button type="primary" @click="open(null)">Add location</el-button>
    </div>
    <el-table v-loading="loading" :data="rows">
      <el-table-column prop="name" label="Name" min-width="220" />
      <el-table-column label="Kind" width="150"><template #default="{ row }">{{ kindLabel(row.kind) }}</template></el-table-column>
      <el-table-column label="Status" width="110">
        <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? 'Active' : 'Inactive' }}</el-tag></template>
      </el-table-column>
      <el-table-column width="90" align="right">
        <template #default="{ row }"><el-button size="small" @click="open(row as Location)">Edit</el-button></template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="editing ? `Edit ${editing.name}` : 'Add location'" width="min(460px, 94vw)">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="Name" required :error="errors.name" for="loc-name"><el-input id="loc-name" v-model="form.name" maxlength="120" /></el-form-item>
        <el-form-item label="Kind" required>
          <el-radio-group v-model="form.kind">
            <el-radio-button v-for="k in KINDS" :key="k.value" :value="k.value">{{ k.label }}</el-radio-button>
          </el-radio-group>
          <div class="muted hint">{{ KINDS.find((k) => k.value === form.kind)?.hint }}</div>
        </el-form-item>
        <el-form-item label="Status"><el-switch v-model="form.is_active" active-text="Active" inactive-text="Inactive" /></el-form-item>
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="save">Save</el-button>
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
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}
.intro {
  margin: 0;
  max-width: 70ch;
}
.hint {
  font-size: 12.5px;
  width: 100%;
  margin-top: 4px;
}
</style>
