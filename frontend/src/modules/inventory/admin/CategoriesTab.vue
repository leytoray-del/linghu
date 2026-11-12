<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { errorMessage, fieldErrors, showError, showSuccess } from '@/utils/feedback'

import { inventoryApi, type CategoryInput } from '../api'
import AttributeFields from '../components/AttributeFields.vue'
import { FIELD_TYPE_LABEL } from '../format'
import { useInventoryLookups } from '../lookups'
import type { AttributeValue, Category, FieldDef, FieldType } from '../types'

const lk = useInventoryLookups()
const loading = ref(true)
const dialog = ref(false)
const editing = ref<Category | null>(null)
/** Keys that already exist on the saved category; their type cannot change. */
const savedKeys = ref<Set<string>>(new Set())
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const form = ref<CategoryInput>({ code: '', name: '', fields: [], warranty_required: true, is_active: true })
const choicesText = ref<string[]>([])
const preview = ref<Record<string, AttributeValue>>({})
const TYPES = Object.keys(FIELD_TYPE_LABEL) as FieldType[]

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

function open(row: Category | null): void {
  editing.value = row
  form.value = row
    ? { code: row.code, name: row.name, fields: row.fields.map((f) => ({ ...f, choices: [...f.choices] })), warranty_required: row.warranty_required, is_active: row.is_active }
    : { code: '', name: '', fields: [], warranty_required: true, is_active: true }
  choicesText.value = form.value.fields.map((f) => f.choices.join(', '))
  savedKeys.value = new Set(row?.fields.map((f) => f.key) ?? [])
  preview.value = {}
  errors.value = {}
  formError.value = null
  dialog.value = true
}

function keyFrom(label: string): string {
  const base = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40)
  return /^[a-z]/.test(base) ? base : `f_${base}`.slice(0, 40)
}

function addField(): void {
  form.value.fields.push({ key: '', label: '', type: 'text', choices: [], required: false, show_in_list: false, retired: false })
  choicesText.value.push('')
}

function onLabel(f: FieldDef): void {
  if (!savedKeys.value.has(f.key) || !f.key) f.key = keyFrom(f.label)
}

function move(i: number, by: number): void {
  const j = i + by
  if (j < 0 || j >= form.value.fields.length) return
  const list = form.value.fields
  ;[list[i], list[j]] = [list[j]!, list[i]!]
  const texts = choicesText.value
  ;[texts[i], texts[j]] = [texts[j]!, texts[i]!]
}

function removeNew(i: number): void {
  form.value.fields.splice(i, 1)
  choicesText.value.splice(i, 1)
}

async function save(): Promise<void> {
  saving.value = true
  errors.value = {}
  formError.value = null
  form.value.fields.forEach((f, i) => {
    f.choices = f.type === 'choice' ? (choicesText.value[i] ?? '').split(',').map((c) => c.trim()).filter(Boolean) : []
    if (!f.key) f.key = keyFrom(f.label)
  })
  try {
    await inventoryApi.saveCategory({ ...form.value, code: form.value.code.trim().toUpperCase() }, editing.value?.id)
    showSuccess('Category saved.')
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
      <p class="muted intro">
        Every item has the same common details: serial number, model, project, location and warranty. Each category adds its
        own fields, which appear on the registration form, the item page, the lists and the Excel export. Fields can be added
        at any time. A field that is no longer needed is retired rather than removed, so recorded values are kept.
      </p>
      <el-button type="primary" @click="open(null)">Add category</el-button>
    </div>
    <el-table v-loading="loading" :data="lk.data.value?.categories ?? []">
      <el-table-column prop="name" label="Category" min-width="160" />
      <el-table-column label="Code" width="140"><template #default="{ row }"><span class="mono">{{ row.code }}</span></template></el-table-column>
      <el-table-column label="Fields" min-width="260">
        <template #default="{ row }">{{ row.fields.filter((f: FieldDef) => !f.retired).map((f: FieldDef) => f.label).join(', ') || '—' }}</template>
      </el-table-column>
      <el-table-column label="Status" width="110">
        <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? 'Active' : 'Inactive' }}</el-tag></template>
      </el-table-column>
      <el-table-column width="90" align="right">
        <template #default="{ row }"><el-button size="small" @click="open(row as Category)">Edit</el-button></template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="editing ? `Edit ${editing.name}` : 'Add category'" width="min(900px, 96vw)" top="5vh">
      <el-form label-position="top" @submit.prevent="save">
        <div class="head-grid">
          <el-form-item label="Name" required :error="errors.name" for="cat-name"><el-input id="cat-name" v-model="form.name" maxlength="80" placeholder="For example Camera" /></el-form-item>
          <el-form-item label="Code" required :error="errors.code" for="cat-code">
            <el-input id="cat-code" v-model="form.code" maxlength="32" :disabled="!!editing" placeholder="For example CAMERA" />
          </el-form-item>
          <el-form-item label="Warranty dates"><el-switch v-model="form.warranty_required" active-text="Required" inactive-text="Optional" /></el-form-item>
          <el-form-item label="Status"><el-switch v-model="form.is_active" active-text="Active" inactive-text="Inactive" /></el-form-item>
        </div>

        <h3 class="fields-title">Fields of this category</h3>
        <div class="field-scroll">
          <table class="fields">
            <thead>
              <tr><th>Label</th><th>Type</th><th>Choices</th><th>Required</th><th>In lists</th><th>Retired</th><th /></tr>
            </thead>
            <tbody>
              <tr v-for="(f, i) in form.fields" :key="i" :class="{ retired: f.retired }">
                <td>
                  <el-input v-model="f.label" size="small" maxlength="60" :aria-label="`Label of field ${i + 1}`" @input="onLabel(f)" />
                  <div v-if="errors[`fields.${i}.key`]" class="err">{{ errors[`fields.${i}.key`] }}</div>
                </td>
                <td>
                  <el-select v-model="f.type" size="small" :disabled="savedKeys.has(f.key)" :aria-label="`Type of field ${i + 1}`">
                    <el-option v-for="t in TYPES" :key="t" :label="FIELD_TYPE_LABEL[t]" :value="t" />
                  </el-select>
                  <div v-if="errors[`fields.${i}.type`]" class="err">{{ errors[`fields.${i}.type`] }}</div>
                </td>
                <td>
                  <el-input v-if="f.type === 'choice'" v-model="choicesText[i]" size="small" placeholder="Wall, Pedestal, Desk" :aria-label="`Choices of field ${i + 1}`" />
                  <span v-else class="muted">—</span>
                  <div v-if="errors[`fields.${i}.choices`]" class="err">{{ errors[`fields.${i}.choices`] }}</div>
                </td>
                <td><el-checkbox v-model="f.required" :aria-label="`Field ${i + 1} required`" /></td>
                <td><el-checkbox v-model="f.show_in_list" :aria-label="`Show field ${i + 1} in lists`" /></td>
                <td><el-checkbox v-model="f.retired" :disabled="!savedKeys.has(f.key)" :aria-label="`Retire field ${i + 1}`" /></td>
                <td class="row-actions">
                  <el-button size="small" link :disabled="i === 0" aria-label="Move up" @click="move(i, -1)">↑</el-button>
                  <el-button size="small" link :disabled="i === form.fields.length - 1" aria-label="Move down" @click="move(i, 1)">↓</el-button>
                  <el-button v-if="!savedKeys.has(f.key)" size="small" link type="danger" @click="removeNew(i)">Remove</el-button>
                </td>
              </tr>
              <tr v-if="!form.fields.length"><td colspan="7" class="muted">No fields yet.</td></tr>
            </tbody>
          </table>
        </div>
        <el-button size="small" @click="addField">Add field</el-button>
        <p class="muted small">The type of a saved field cannot change. To change it, retire the field and add a new one.</p>

        <details class="preview">
          <summary>Preview the form</summary>
          <AttributeFields v-model="preview" :fields="form.fields.map((f, i) => ({ ...f, choices: f.type === 'choice' ? (choicesText[i] ?? '').split(',').map((c) => c.trim()).filter(Boolean) : [] }))" id-prefix="preview" />
        </details>
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
  max-width: 75ch;
}
.head-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 0 16px;
}
.fields-title {
  font-size: 14px;
  margin: 4px 0 8px;
}
.field-scroll {
  overflow-x: auto;
  margin-bottom: 8px;
}
.fields {
  width: 100%;
  min-width: 720px;
  border-collapse: collapse;
  font-size: 13px;
}
.fields th {
  text-align: left;
  font-weight: 500;
  color: var(--erf-muted);
  padding: 4px 6px;
  border-bottom: 1px solid var(--erf-line);
}
.fields td {
  padding: 6px;
  border-bottom: 1px solid var(--erf-line);
  vertical-align: top;
}
.fields td:nth-child(1) {
  min-width: 180px;
}
.fields td:nth-child(2) {
  width: 140px;
  min-width: 140px;
}
.fields td :deep(.el-select) {
  width: 100%;
}
.fields tr.retired td {
  opacity: 0.55;
}
.row-actions {
  white-space: nowrap;
}
.err {
  color: var(--erf-bad);
  font-size: 12px;
  margin-top: 2px;
}
.small {
  font-size: 12.5px;
}
.preview {
  margin: 10px 0;
  border: 1px solid var(--erf-line);
  border-radius: var(--erf-radius);
  padding: 8px 12px;
}
.preview summary {
  cursor: pointer;
  margin-bottom: 8px;
}
</style>
