import { defineStore } from 'pinia'
import { ref } from 'vue'

import { referenceApi } from '@/api'
import type { Lookups, SupportTypeBrief, TeamLookup } from '@/types/api'

export const useLookupStore = defineStore('lookups', () => {
  const data = ref<Lookups | null>(null)

  async function load(force = false): Promise<Lookups> {
    if (!data.value || force) data.value = await referenceApi.lookups()
    return data.value
  }

  function supportType(id: number | null): SupportTypeBrief | undefined {
    return data.value?.support_types.find((s) => s.id === id)
  }

  function teamFor(supportTypeId: number | null): TeamLookup | undefined {
    const st = supportType(supportTypeId)
    return st ? data.value?.teams.find((t) => t.id === st.team_id) : undefined
  }

  return { data, load, supportType, teamFor }
})
