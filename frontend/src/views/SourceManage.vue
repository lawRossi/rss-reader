<template>
  <div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <h2 class="text-xl font-bold text-[var(--color-text)]">订阅源管理</h2>
      <div class="flex items-center gap-2 flex-wrap">
        <button @click="showCreateGroup = true"
          class="px-3 py-2 sm:px-4 border border-[var(--color-border)] text-[var(--color-text)] rounded-lg text-xs sm:text-sm hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors whitespace-nowrap">
          📁 新建分组
        </button>
        <button @click="showImportOpml = true"
          class="px-3 py-2 sm:px-4 border border-[var(--color-border)] text-[var(--color-text)] rounded-lg text-xs sm:text-sm hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors whitespace-nowrap">
          📂 导入 OPML
        </button>
        <button @click="showAddFeed = true"
          class="px-3 py-2 sm:px-4 bg-[var(--color-primary)] text-white rounded-lg text-xs sm:text-sm hover:bg-[var(--color-primary-dark)] transition-colors whitespace-nowrap">
          + 添加源
        </button>
      </div>
    </div>

    <!-- Groups and feeds -->
    <div v-if="loading" class="space-y-4">
      <div v-for="i in 3" :key="i" class="animate-pulse bg-[var(--color-surface)] rounded-xl p-4 border border-[var(--color-border)]">
        <div class="h-5 bg-gray-200 dark:bg-gray-700 rounded w-1/3"></div>
      </div>
    </div>
    <div v-else-if="feedStore.feeds.length === 0" class="text-center py-16 text-[var(--color-text-secondary)]">
      <p class="text-5xl mb-4">📡</p>
      <p class="text-lg font-medium mb-2">还没有订阅源</p>
      <p class="text-sm mb-6">点击上方"添加源"或导入 OPML 文件开始使用</p>
      <div class="flex items-center justify-center gap-3">
        <button @click="showAddFeed = true"
          class="px-5 py-2.5 bg-[var(--color-primary)] text-white rounded-lg text-sm hover:bg-[var(--color-primary-dark)]">
          + 添加订阅源
        </button>
        <button @click="showImportOpml = true"
          class="px-5 py-2.5 border border-[var(--color-border)] text-[var(--color-text)] rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-800">
          📂 导入 OPML
        </button>
      </div>
    </div>
    <div v-else class="space-y-4">
      <div v-for="item in feedStore.feedsByGroup" :key="item.group.id" class="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] overflow-hidden">
        <div class="px-4 py-3 flex items-center justify-between border-b border-[var(--color-border)]">
          <router-link :to="`/group/${item.group.id}`" class="font-semibold text-[var(--color-text)] hover:text-[var(--color-primary)] transition-colors">
            {{ item.group.name }}
          </router-link>
          <div class="flex items-center gap-2">
            <span class="text-sm text-[var(--color-text-secondary)]">{{ item.feeds.length }} 个源</span>
            <button v-if="item.group.id !== 0" @click="deleteGroup(item.group.id)"
              class="text-sm text-red-500 hover:text-red-600">删除</button>
          </div>
        </div>
        <div class="divide-y divide-[var(--color-border)]">
          <div v-for="feed in item.feeds" :key="feed.id"
            class="px-4 py-3 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-800/50">
            <div class="flex-1 min-w-0">
              <router-link :to="`/source/${feed.id}`" class="font-medium text-[var(--color-text)] hover:text-[var(--color-primary)] truncate block">
                {{ feed.title }}
              </router-link>
              <p class="text-xs text-[var(--color-text-secondary)] truncate mt-0.5">{{ feed.url }}</p>
            </div>
            <div class="flex items-center gap-2 ml-3">
              <select @change="moveFeed(feed.id, $event.target.value)"
                class="text-xs bg-transparent border border-[var(--color-border)] rounded px-1 py-0.5 text-[var(--color-text-secondary)] cursor-pointer hover:border-[var(--color-primary)] focus:outline-none">
                <option value="" disabled>移动到...</option>
                <option :value="null">未分组</option>
                <option v-for="g in feedStore.groups" :key="g.id" :value="g.id"
                  :selected="feed.group_id === g.id">{{ g.name }}</option>
              </select>
              <span class="text-xs text-[var(--color-text-secondary)]">{{ feed.article_count || 0 }} 篇</span>
              <button @click="deleteFeed(feed.id)" class="text-xs text-red-500 hover:text-red-600">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- OPML Import Modal -->
    <div v-if="showImportOpml" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="showImportOpml = false">
      <div class="bg-[var(--color-surface)] rounded-2xl p-6 w-full max-w-md">
        <h3 class="text-lg font-bold text-[var(--color-text)] mb-4">📂 导入 OPML 文件</h3>
        <p class="text-sm text-[var(--color-text-secondary)] mb-4">上传其他 RSS 阅读器导出的 OPML 文件，批量导入订阅源。</p>
        <div class="border-2 border-dashed border-[var(--color-border)] rounded-xl p-8 text-center"
          @dragover.prevent @drop.prevent="handleOpmlDrop">
          <input ref="fileInput" type="file" accept=".opml,.xml" class="hidden" @change="handleOpmlFile" />
          <p class="text-[var(--color-text-secondary)] mb-3">拖拽文件到此处</p>
          <button @click="fileInput?.click()"
            class="px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm">
            选择文件
          </button>
        </div>
        <div v-if="importResult" class="mt-4 p-3 rounded-lg text-sm" :class="importResult.success_count > 0 ? 'bg-green-50 dark:bg-green-900/20 text-green-600' : 'bg-red-50 dark:bg-red-900/20 text-red-600'">
          <p>{{ importResult.message }}</p>
          <ul v-if="importResult.failures?.length" class="mt-2 text-xs space-y-1">
            <li v-for="f in importResult.failures" :key="f.url">❌ {{ f.url }}: {{ f.reason }}</li>
          </ul>
        </div>
        <div class="flex gap-2 mt-4">
          <button @click="showImportOpml = false"
            class="flex-1 px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)]">关闭</button>
        </div>
      </div>
    </div>

    <!-- Create Group Modal -->
    <div v-if="showCreateGroup" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="showCreateGroup = false">
      <div class="bg-[var(--color-surface)] rounded-2xl p-6 w-full max-w-sm">
        <h3 class="text-lg font-bold text-[var(--color-text)] mb-4">📁 新建分组</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">分组名称</label>
            <input v-model="newGroupName" placeholder="如：科技、新闻、博客"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
          </div>
          <div>
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">排序位置</label>
            <input v-model.number="newGroupSort" type="number" min="0" placeholder="0"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
          </div>
          <div class="flex gap-2 pt-2">
            <button @click="showCreateGroup = false"
              class="flex-1 px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)]">取消</button>
            <button @click="createGroup" :disabled="!newGroupName"
              class="flex-1 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg disabled:opacity-50">创建</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Add Feed Modal -->
    <div v-if="showAddFeed" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="showAddFeed = false">
      <div class="bg-[var(--color-surface)] rounded-2xl p-6 w-full max-w-md">
        <h3 class="text-lg font-bold text-[var(--color-text)] mb-4">添加订阅源</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">RSS 链接</label>
            <input v-model="newFeedUrl" type="url" placeholder="https://example.com/rss"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
          </div>
          <div>
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">分组</label>
            <select v-model="newFeedGroup"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]">
              <option :value="null">未分组</option>
              <option v-for="g in feedStore.groups" :key="g.id" :value="g.id">{{ g.name }}</option>
            </select>
          </div>
          <div class="flex gap-2 pt-2">
            <button @click="showAddFeed = false"
              class="flex-1 px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)]">取消</button>
            <button @click="addFeed" :disabled="!newFeedUrl"
              class="flex-1 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg hover:bg-[var(--color-primary-dark)] disabled:opacity-50">
              添加
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
import { useFeedStore } from '../stores/feedStore'
import { feedsApi } from '../api'

const feedStore = useFeedStore()
const showToast = inject('showToast')
const loading = ref(true)
const showAddFeed = ref(false)
const showImportOpml = ref(false)
const showCreateGroup = ref(false)
const importResult = ref(null)
const fileInput = ref(null)
const newFeedUrl = ref('')
const newFeedGroup = ref(null)
const newGroupName = ref('')
const newGroupSort = ref(0)

onMounted(async () => {
  await feedStore.loadFeeds()
  loading.value = false
})

async function createGroup() {
  try {
    await feedStore.createGroup({ name: newGroupName.value, sort_order: newGroupSort.value })
    showCreateGroup.value = false
    newGroupName.value = ''
    newGroupSort.value = 0
    showToast('分组创建成功！', 'success')
  } catch (e) {
    showToast(e.response?.data?.detail || '创建失败', 'error')
  }
}

async function moveFeed(feedId, groupId) {
  try {
    const targetGroup = groupId === 'null' || groupId === '' ? null : Number(groupId)
    await feedsApi.update(feedId, { group_id: targetGroup })
    await feedStore.loadFeeds()
    showToast('分组已更新', 'success')
  } catch (e) {
    showToast('移动失败', 'error')
  }
}

async function addFeed() {
  try {
    await feedStore.addFeed({ url: newFeedUrl.value, group_id: newFeedGroup.value })
    showAddFeed.value = false
    newFeedUrl.value = ''
    showToast('订阅源添加成功！', 'success')
  } catch (e) {
    showToast(e.response?.data?.detail || '添加失败', 'error')
  }
}

async function deleteFeed(id) {
  if (!confirm('确定删除这个订阅源吗？')) return
  try {
    await feedStore.deleteFeed(id)
    showToast('订阅源已删除', 'success')
  } catch (e) {
    showToast('删除失败', 'error')
  }
}

async function deleteGroup(id) {
  if (!confirm('确定删除这个分组吗？分组下的源将变为未分组。')) return
  try {
    await feedStore.deleteGroup(id)
    showToast('分组已删除', 'success')
  } catch (e) {
    showToast('删除失败', 'error')
  }
}

function handleOpmlDrop(e) {
  const file = e.dataTransfer.files[0]
  if (file) uploadOpml(file)
}

function handleOpmlFile(e) {
  const file = e.target.files[0]
  if (file) uploadOpml(file)
}

async function uploadOpml(file) {
  importResult.value = null
  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await feedsApi.importOpml(formData)
    importResult.value = res.data
    await feedStore.loadFeeds()
    showToast(`导入完成: ${res.data.success_count} 成功, ${res.data.fail_count} 失败`, res.data.fail_count > 0 ? 'info' : 'success')
  } catch (e) {
    showToast('导入失败: ' + (e.response?.data?.detail || e.message), 'error')
  }
}
</script>
