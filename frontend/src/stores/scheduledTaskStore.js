import { defineStore } from 'pinia'
import { ref } from 'vue'
import { scheduledTasksApi } from '../api'

export const useScheduledTaskStore = defineStore('scheduledTasks', () => {
  const tasks = ref([])
  const loading = ref(false)

  async function loadTasks() {
    loading.value = true
    try {
      const res = await scheduledTasksApi.list()
      tasks.value = res.data
    } catch (e) {
      console.error('Failed to load scheduled tasks:', e)
    } finally {
      loading.value = false
    }
  }

  async function createTask(data) {
    const res = await scheduledTasksApi.create(data)
    await loadTasks()
    return res.data
  }

  async function updateTask(id, data) {
    const res = await scheduledTasksApi.update(id, data)
    await loadTasks()
    return res.data
  }

  async function deleteTask(id) {
    await scheduledTasksApi.delete(id)
    await loadTasks()
  }

  async function toggleTask(id) {
    const res = await scheduledTasksApi.toggle(id)
    await loadTasks()
    return res.data
  }

  async function executeNow(id) {
    const res = await scheduledTasksApi.executeNow(id)
    return res.data
  }

  return {
    tasks,
    loading,
    loadTasks,
    createTask,
    updateTask,
    deleteTask,
    toggleTask,
    executeNow,
  }
})
