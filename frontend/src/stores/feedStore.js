import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { feedsApi, groupsApi } from '../api'

export const useFeedStore = defineStore('feeds', () => {
  const feeds = ref([])
  const groups = ref([])
  const loading = ref(false)

  const feedsByGroup = computed(() => {
    const result = {}
    for (const group of groups.value) {
      result[group.id] = {
        group,
        feeds: feeds.value.filter((f) => f.group_id === group.id),
      }
    }
    // Ungrouped feeds
    const ungrouped = feeds.value.filter((f) => !f.group_id)
    if (ungrouped.length) {
      result[0] = { group: { id: 0, name: '未分组' }, feeds: ungrouped }
    }
    return result
  })

  async function loadFeeds() {
    loading.value = true
    try {
      const [feedsRes, groupsRes] = await Promise.all([
        feedsApi.list(),
        groupsApi.list(),
      ])
      feeds.value = feedsRes.data
      groups.value = groupsRes.data
    } catch (e) {
      console.error('Failed to load feeds:', e)
    } finally {
      loading.value = false
    }
  }

  async function addFeed(data) {
    const res = await feedsApi.create(data)
    await loadFeeds()
    return res.data
  }

  async function deleteFeed(id) {
    await feedsApi.delete(id)
    await loadFeeds()
  }

  async function createGroup(data) {
    const res = await groupsApi.create(data)
    await loadFeeds()
    return res.data
  }

  async function deleteGroup(id) {
    await groupsApi.delete(id)
    await loadFeeds()
  }

  return {
    feeds,
    groups,
    loading,
    feedsByGroup,
    loadFeeds,
    addFeed,
    deleteFeed,
    createGroup,
    deleteGroup,
  }
})
