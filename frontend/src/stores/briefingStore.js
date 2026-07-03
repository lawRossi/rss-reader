import { defineStore } from 'pinia'
import { ref } from 'vue'
import { briefingsApi } from '../api'

export const useBriefingStore = defineStore('briefings', () => {
  const briefings = ref([])
  const currentBriefing = ref(null)
  const loading = ref(false)

  async function loadBriefings() {
    loading.value = true
    try {
      const res = await briefingsApi.list()
      briefings.value = res.data
    } catch (e) {
      console.error('Failed to load briefings:', e)
    } finally {
      loading.value = false
    }
  }

  async function getBriefing(id) {
    const res = await briefingsApi.get(id)
    currentBriefing.value = res.data
    return res.data
  }

  async function generateBriefing(data) {
    const res = await briefingsApi.generate(data)
    await loadBriefings()
    return res.data
  }

  async function deleteBriefing(id) {
    await briefingsApi.delete(id)
    await loadBriefings()
  }

  return {
    briefings,
    currentBriefing,
    loading,
    loadBriefings,
    getBriefing,
    generateBriefing,
    deleteBriefing,
  }
})
