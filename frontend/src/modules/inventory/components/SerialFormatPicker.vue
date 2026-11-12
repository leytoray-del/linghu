<script setup lang="ts">
/**
 * Choose a model's serial number format from one real serial number, without writing a pattern.
 */
import { computed, ref, watch } from 'vue'

import { describeFormat, formatMatches, suggestFormats } from '../serialFormat'

const props = defineProps<{ initialSample?: string; idPrefix?: string }>()
const pattern = defineModel<string | null>({ required: true })

const sample = ref(props.initialSample ?? '')
const advanced = ref(false)
const options = computed(() => suggestFormats(sample.value))
/** The chosen option, by position; -1 when the current format is not one of the suggestions. */
const chosen = computed(() => options.value.findIndex((o) => o.pattern === pattern.value))

watch(
  () => props.initialSample,
  (v) => {
    if (v) sample.value = v
  },
)
// When the example changes, keep the format if it still matches it; otherwise suggest the safest one.
watch(sample, () => {
  if (!sample.value.trim()) return
  if (!pattern.value || !formatMatches(pattern.value, sample.value) || chosen.value < 0) {
    pattern.value = options.value[0]?.pattern ?? null
  }
})
if (sample.value && pattern.value === null) pattern.value = options.value[0]?.pattern ?? null
</script>

<template>
  <div class="picker">
    <el-form-item label="One real serial number of this model" :for="`${idPrefix ?? 'fmt'}-sample`">
      <el-input :id="`${idPrefix ?? 'fmt'}-sample`" v-model="sample" placeholder="Type it as printed on the label, or scan it" autocapitalize="characters" />
    </el-form-item>
    <div v-if="sample.trim()" class="options" role="radiogroup" aria-label="Serial number format">
      <button
        v-for="(o, i) in options"
        :key="String(o.pattern)"
        type="button"
        role="radio"
        :aria-checked="i === chosen"
        class="option"
        @click="pattern = o.pattern"
      >
        <span class="radio" aria-hidden="true" />
        <span class="text">
          <b>{{ o.description }}</b>
          <small>{{ o.hint }}</small>
        </span>
      </button>
    </div>
    <p v-else class="muted small">Enter a serial number to see the suggested formats.</p>
    <p v-if="pattern && chosen < 0" class="small current">Current format: {{ describeFormat(pattern) }}</p>
    <button type="button" class="link small" @click="advanced = !advanced">{{ advanced ? 'Hide' : 'Show' }} the format as written</button>
    <el-input v-if="advanced" :model-value="pattern ?? ''" class="mono" placeholder="No check" @update:model-value="(v: string) => (pattern = v.trim() || null)" />
  </div>
</template>

<style scoped>
.picker {
  display: grid;
  gap: 8px;
}
.options {
  display: grid;
  gap: 6px;
}
.option {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  text-align: left;
  font: inherit;
  color: inherit;
  background: var(--erf-surface);
  border: 1px solid var(--erf-line);
  border-radius: var(--erf-radius);
  padding: 10px 12px;
  cursor: pointer;
}
.option[aria-checked='true'] {
  border-color: var(--erf-accent);
  background: color-mix(in srgb, var(--erf-accent) 6%, var(--erf-surface));
}
.radio {
  flex: none;
  width: 16px;
  height: 16px;
  margin-top: 2px;
  border-radius: 50%;
  border: 2px solid var(--erf-line);
}
.option[aria-checked='true'] .radio {
  border: 5px solid var(--erf-accent);
}
.text {
  display: grid;
  gap: 2px;
}
.text small {
  color: var(--erf-muted);
  font-size: 12.5px;
}
.small {
  font-size: 12.5px;
  margin: 0;
}
.current {
  color: var(--erf-warn);
}
.link {
  justify-self: start;
  background: none;
  border: 0;
  padding: 0;
  color: var(--erf-accent);
  cursor: pointer;
  font: inherit;
  font-size: 12.5px;
}
</style>
