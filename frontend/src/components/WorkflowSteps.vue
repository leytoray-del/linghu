<script setup lang="ts">
import { computed } from 'vue'

import type { RequestDetail } from '@/types/api'

const props = defineProps<{ request: RequestDetail }>()

type StepState = 'done' | 'current' | 'stopped' | 'todo' | 'skipped'
interface Step {
  title: string
  who: string
  state: StepState
}

function names(step: 'TL_REVIEW' | 'DIRECTOR_APPROVAL'): string {
  const r = props.request
  const tasks = r.tasks.filter((t) => t.step === step && t.round === r.round)
  const acted = tasks.find((t) => ['APPROVED', 'RETURNED', 'REJECTED'].includes(t.status))
  if (acted) return acted.assignee.display_name
  const pending = tasks.filter((t) => t.status === 'PENDING').map((t) => t.assignee.display_name)
  if (pending.length) return pending.join(', ')
  return step === 'TL_REVIEW' ? `${r.team?.name ?? 'Team'} leader` : 'Director'
}

// The last step is completed automatically when the director approves.
const confirmedText = computed(() => {
  switch (props.request.status) {
    case 'APPROVED':
    case 'CLOSED':
      return 'Requester and engineers notified'
    case 'REJECTED':
      return 'Not reached: the request was rejected permanently'
    case 'WITHDRAWN':
      return 'Not reached: the request was withdrawn'
    case 'CANCELLED':
      return 'Not reached: the request was cancelled'
    case 'RETURNED':
      return 'Completes when the revised request is approved by the director'
    default:
      return 'Completes automatically when the director approves'
  }
})

const steps = computed<Step[]>(() => {
  const r = props.request
  const lastRoundTasks = r.tasks.filter((t) => t.round === r.round)
  const stoppedAt = lastRoundTasks.find((t) => t.status === 'RETURNED' || t.status === 'REJECTED')?.step
  const state = (index: number): StepState => {
    switch (r.status) {
      case 'DRAFT':
        return 'todo'
      case 'PENDING_TL_REVIEW':
        return index === 0 ? 'done' : index === 1 ? 'current' : 'todo'
      case 'PENDING_DIRECTOR_APPROVAL':
        return index <= 1 ? 'done' : index === 2 ? 'current' : 'todo'
      case 'APPROVED':
      case 'CLOSED':
        return 'done'
      case 'RETURNED':
      case 'REJECTED': {
        const stopIndex = stoppedAt === 'DIRECTOR_APPROVAL' ? 2 : 1
        const after = r.status === 'REJECTED' ? 'skipped' : 'todo'
        return index < stopIndex ? 'done' : index === stopIndex ? 'stopped' : after
      }
      default:
        // Withdrawn or cancelled before approval: the remaining steps will never happen.
        return index === 0 ? 'done' : 'skipped'
    }
  }
  return [
    { title: 'Submitted', who: r.requester.display_name, state: state(0) },
    { title: 'Team leader review', who: names('TL_REVIEW'), state: state(1) },
    { title: 'Director approval', who: names('DIRECTOR_APPROVAL'), state: state(2) },
    { title: 'Resources confirmed', who: confirmedText.value, state: state(3) },
  ]
})

const note: Record<StepState, string> = { done: '', current: ' · waiting', stopped: '', todo: '', skipped: '' }
</script>

<template>
  <ol class="steps">
    <li v-for="s in steps" :key="s.title" :class="s.state">
      <span class="mark" aria-hidden="true">{{ s.state === 'done' ? '✓' : s.state === 'stopped' ? '!' : '' }}</span>
      <div>
        <div class="title">{{ s.title }}</div>
        <div class="who">
          {{ s.who }}{{ note[s.state] }}<template v-if="s.state === 'stopped'"> · {{ request.status === 'RETURNED' ? 'rejected, can resubmit' : 'rejected permanently' }}</template>
        </div>
      </div>
    </li>
  </ol>
</template>

<style scoped>
.steps {
  list-style: none;
  margin: 0;
  padding: 0;
}
li {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 10px;
  padding-bottom: 14px;
  position: relative;
}
li::after {
  content: '';
  position: absolute;
  left: 11px;
  top: 24px;
  bottom: 0;
  width: 2px;
  background: var(--erf-line);
}
li:last-child::after {
  display: none;
}
.mark {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid var(--erf-line);
  background: var(--erf-surface);
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 700;
  z-index: 1;
}
.done .mark {
  background: var(--erf-ok);
  border-color: var(--erf-ok);
  color: #fff;
}
.current .mark {
  border-color: var(--erf-accent);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--erf-accent) 18%, transparent);
}
.stopped .mark {
  background: var(--erf-bad);
  border-color: var(--erf-bad);
  color: #fff;
}
.title {
  font-weight: 500;
}
.skipped .mark {
  border-style: dashed;
}
.skipped .title {
  color: var(--erf-muted);
  text-decoration: line-through;
}
.who {
  font-size: 12px;
  color: var(--erf-muted);
}
</style>
