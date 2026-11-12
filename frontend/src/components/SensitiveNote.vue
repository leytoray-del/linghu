<script setup lang="ts">
/** A short reminder not to enter sensitive information in the fields that follow. */
defineProps<{ text: string }>()
</script>

<template>
  <div class="sensitive" role="note">
    <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
      <path d="M12 8v5M12 16.5v.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
    </svg>
    <p><b>No sensitive information.</b> {{ text }}</p>
  </div>
</template>

<style scoped>
.sensitive {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  margin: 0 0 16px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--erf-warn) 35%, transparent);
  background: color-mix(in srgb, var(--erf-warn) 9%, var(--erf-surface));
  font-size: 13px;
  line-height: 1.5;
}
.icon {
  flex: none;
  width: 18px;
  height: 18px;
  margin-top: 1px;
  color: var(--erf-warn);
}
p {
  margin: 0;
}
</style>
