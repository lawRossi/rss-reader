import { defineStore } from 'pinia'
import { ref } from 'vue'
import { tagsApi } from '../api'

export const useTagStore = defineStore('tags', () => {
  const tags = ref([])
  const loading = ref(false)

  async function loadTags() {
    loading.value = true
    try {
      const res = await tagsApi.list()
      tags.value = res.data
    } catch (e) {
      console.error('Failed to load tags:', e)
    } finally {
      loading.value = false
    }
  }

  async function createTag(data) {
    const res = await tagsApi.create(data)
    await loadTags()
    return res.data
  }

  async function updateTag(id, data) {
    const res = await tagsApi.update(id, data)
    await loadTags()
    return res.data
  }

  async function deleteTag(id) {
    await tagsApi.delete(id)
    await loadTags()
  }

  async function setArticleTags(articleId, tagIds) {
    const res = await tagsApi.setArticleTags(articleId, tagIds)
    return res.data
  }

  return {
    tags,
    loading,
    loadTags,
    createTag,
    updateTag,
    deleteTag,
    setArticleTags,
  }
})
