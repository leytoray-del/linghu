<script setup lang="ts">
/** Add a model on the spot, for example while registering a delivery of a new device type. */
import { computed, reactive, ref, watch } from 'vue'

import { useAuthStore } from '@/stores/auth'
import { errorMessage, fieldErrors, showSuccess } from '@/utils/feedback'

import { inventoryApi } from '../api'
import { useInventoryLookups } from '../lookups'
import type { ItemModel } from '../types'
import SerialFormatPicker from './SerialFormatPicker.vue'

const props = defineProps<{ sample?: string; categoryId?: number | null }>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ created: [model: ItemModel] }>()

const auth = useAuthStore()
const lk = useInventoryLookups()
const form = reactive({ category_id: null as number | null, model_no: '', manufacturer: '', serial_pattern: null as string | null })
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const saving = ref(false)
const categories = computed(() => (lk.data.value?.categories ?? []).filter((c) => c.is_active))

watch(open, (v) => {
  if (!v) return
  Object.assign(form, { category_id: props.categoryId ?? null, model_no: '', manufacturer: '', serial_pattern: null })
  errors.value = {}
  formError.value = null
})

async function save(): Promise<void> {
  if (!form.category_id) {
    errors.value = { category_id: 'Choose the kind of equipment.' }
    return
  }
  saving.value = true
  errors.value = {}
  formError.value = null
  try {
    const model = await inventoryApi.saveModel({
      category_id: form.category_id,
      model_no: form.model_no.trim(),
      name: null,
      manufacturer: form.manufacturer.trim() || null,
      serial_pattern: form.serial_pattern,
      is_active: true,
    })
    await lk.load(true)
    showSuccess(`Model ${model.model_no} added.`)
    emit('created', model)
    open.value = false
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-drawer v-model="open" title="Add a new model" direction="btt" size="92%" class="sheet" append-to-body>
    <el-form label-position="top" @submit.prevent="save">
      <el-form-item label="Kind of equipment" required :error="errors.category_id">
        <el-select v-model="form.category_id" placeholder="Choose" style="width: 100%">
          <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <div class="muted hint">
          Not in the list?
          <template v-if="auth.can('inventory.admin')">Add it under Administration, Inventory categories, then come back.</template>
          <template v-else>Ask an administrator to add the kind of equipment first.</template>
        </div>
      </el-form-item>
      <el-form-item label="Model number" required :error="errors.model_no" for="nm-no">
        <el-input id="nm-no" v-model="form.model_no" maxlength="64" placeholder="As printed on the label, for example UR4" autocapitalize="characters" />
      </el-form-item>
      <el-form-item label="Manufacturer" for="nm-maker">
        <el-input id="nm-maker" v-model="form.manufacturer" maxlength="120" placeholder="Optional" />
      </el-form-item>
      <h3 class="section">Serial number format</h3>
      <p class="muted hint">Labels often have several barcodes. With a format, scanning keeps only this model's serial number.</p>
      <SerialFormatPicker v-model="form.serial_pattern" :initial-sample="sample" id-prefix="nm" />
      <p v-if="errors.serial_pattern" class="err">{{ errors.serial_pattern }}</p>
      <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon class="alert" />
    </el-form>
    <template #footer>
      <div class="footer">
        <el-button size="large" @click="open = false">Cancel</el-button>
        <el-button size="large" type="primary" :loading="saving" @click="save">Add model</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.hint {
  font-size: 12.5px;
  line-height: 1.45;
  margin: 4px 0 0;
  width: 100%;
}
.section {
  font-size: 15px;
  margin: 8px 0 0;
}
.err {
  color: var(--erf-bad);
  font-size: 13px;
}
.alert {
  margin-top: 12px;
}
.footer {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 10px;
}
.footer .el-button + .el-button {
  margin-left: 0;
}
</style>
