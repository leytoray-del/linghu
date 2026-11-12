<script setup lang="ts">
/**
 * The form for a category's own fields. The fields come from the category definition, so a new
 * category or field appears here without any code change.
 */
import { computed } from 'vue'

import type { AttributeValue, FieldDef } from '../types'

const props = defineProps<{ fields: FieldDef[]; errors?: Record<string, string>; idPrefix?: string }>()
const values = defineModel<Record<string, AttributeValue>>({ required: true })

const active = computed(() => props.fields.filter((f) => !f.retired))

function set(key: string, value: AttributeValue | undefined): void {
  values.value = { ...values.value, [key]: value === undefined || value === '' ? null : value }
}
function asBool(v: AttributeValue | undefined): boolean | undefined {
  return typeof v === 'boolean' ? v : undefined
}
function id(f: FieldDef): string {
  return `${props.idPrefix ?? 'attr'}-${f.key}`
}
</script>

<template>
  <div class="attr-grid">
    <el-form-item
      v-for="f in active"
      :key="f.key"
      :label="f.label"
      :required="f.required"
      :error="errors?.[`attributes.${f.key}`] ?? errors?.[f.key]"
      :for="id(f)"
    >
      <el-select
        v-if="f.type === 'choice'"
        :id="id(f)"
        :model-value="(values[f.key] as string | null) ?? undefined"
        clearable
        placeholder="Choose"
        @update:model-value="(v: string | undefined) => set(f.key, v)"
      >
        <el-option v-for="c in f.choices" :key="c" :label="c" :value="c" />
      </el-select>
      <el-radio-group
        v-else-if="f.type === 'boolean'"
        :id="id(f)"
        :model-value="asBool(values[f.key])"
        @update:model-value="(v) => set(f.key, v as boolean)"
      >
        <el-radio-button :value="true">Yes</el-radio-button>
        <el-radio-button :value="false">No</el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-else-if="f.type === 'date'"
        :id="id(f)"
        :model-value="(values[f.key] as string | null) ?? undefined"
        type="date"
        value-format="YYYY-MM-DD"
        format="D MMM YYYY"
        @update:model-value="(v: string | undefined) => set(f.key, v)"
      />
      <el-input
        v-else-if="f.type === 'number'"
        :id="id(f)"
        :model-value="values[f.key] === null || values[f.key] === undefined ? '' : String(values[f.key])"
        inputmode="decimal"
        @update:model-value="(v: string) => set(f.key, v === '' ? null : Number.isNaN(Number(v)) ? v : Number(v))"
      />
      <el-input
        v-else
        :id="id(f)"
        :model-value="(values[f.key] as string | null) ?? ''"
        maxlength="200"
        @update:model-value="(v: string) => set(f.key, v)"
      />
    </el-form-item>
    <p v-if="!active.length" class="muted none">This category has no extra fields.</p>
  </div>
</template>

<style scoped>
.attr-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0 16px;
}
.attr-grid :deep(.el-select),
.attr-grid :deep(.el-date-editor) {
  width: 100%;
}
.none {
  margin: 0 0 12px;
}
</style>
