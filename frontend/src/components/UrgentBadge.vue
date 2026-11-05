<template>
  <span class="urgent">URGENT</span>
</template>

<style scoped>
.urgent {
  font-family: var(--erf-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  color: var(--erf-bad);
  border: 1px solid color-mix(in srgb, var(--erf-bad) 50%, transparent);
  padding: 0 6px;
  border-radius: 4px;
  white-space: nowrap;
}
</style>
