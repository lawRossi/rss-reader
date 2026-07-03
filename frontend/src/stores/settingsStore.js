import { defineStore } from 'pinia'
import { ref } from 'vue'
import { settingsApi } from '../api'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref({})
  const loading = ref(false)

  async function loadSettings() {
    loading.value = true
    try {
      const res = await settingsApi.getAll()
      const obj = {}
      for (const s of res.data) {
        obj[s.key] = s.value
      }
      settings.value = obj
    } catch (e) {
      console.error('Failed to load settings:', e)
    } finally {
      loading.value = false
    }
  }

  async function saveSettings(newSettings) {
    await settingsApi.update(newSettings)
    await loadSettings()
  }

  return {
    settings,
    loading,
    loadSettings,
    saveSettings,
  }
})
