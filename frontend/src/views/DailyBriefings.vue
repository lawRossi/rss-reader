<template>
  <div class="space-y-6">
    <!-- ═══ 日报列表 ═══ -->
    <div class="flex items-center justify-between flex-wrap gap-3">
      <h2 class="text-xl font-bold text-[var(--color-text)]">🎙️ 每日播报</h2>
      <div class="flex items-center gap-3 flex-wrap">
        <select v-model="selectedTimeRange"
          class="px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]">
          <option value="today">📅 当天</option>
          <option value="12h">🕐 近12小时</option>
          <option value="24h">🕐 近24小时</option>
        </select>
        <select v-model="selectedGroupId"
          class="px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]">
          <option :value="null">📂 全部</option>
          <option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}</option>
        </select>
        <!-- Reference audio selector (only for nano engine) -->
        <select v-if="ttsEngine === 'moss-tts-nano'" v-model="selectedRefAudioId"
          class="px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] max-w-[160px]">
          <option :value="null">🎤 默认音色</option>
          <option v-for="audio in refAudios" :key="audio.id" :value="audio.id">
            {{ audio.name }}{{ audio.active ? ' (当前)' : '' }}
          </option>
        </select>
        <!-- Edge TTS voice selector -->
        <select v-if="ttsEngine === 'edge-tts'" v-model="selectedEdgeVoice"
          class="px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] max-w-[180px]">
          <option :value="null">🌐 默认音色</option>
          <option v-for="v in edgeVoices" :key="v.short_name" :value="v.short_name">
            {{ v.display_name }} ({{ v.gender === 'Female' ? '女声' : '男声' }})
          </option>
        </select>
        <button @click="generateBriefing" :disabled="generating"
          class="px-4 py-2 bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-secondary)] text-white rounded-lg text-sm font-medium disabled:opacity-50 whitespace-nowrap">
          {{ generating ? '生成中...' : '生成播报' }}
        </button>
      </div>
    </div>

    <div class="space-y-3">
      <div v-for="briefing in briefingStore.briefings" :key="briefing.id"
        class="bg-[var(--color-surface)] rounded-xl p-4 border border-[var(--color-border)] group">
        <div class="flex items-start justify-between gap-2">
          <router-link :to="`/daily/${briefing.id}`" class="flex-1 min-w-0">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-2">
              <!-- Mobile: title + status on same row -->
              <div class="flex items-center justify-between gap-2 sm:hidden">
                <h3 class="font-semibold text-[var(--color-text)] truncate text-sm flex-1">{{ briefing.title }}</h3>
                <span class="px-2 py-0.5 rounded-full text-xs whitespace-nowrap shrink-0"
                  :class="statusClass(briefing.status)">
                  {{ statusText(briefing.status) }}
                </span>
              </div>
              <!-- Desktop: title only -->
              <h3 class="font-semibold text-[var(--color-text)] truncate text-base hidden sm:block">{{ briefing.title }}</h3>

              <!-- Mobile: date + play | Desktop: status + play -->
              <div class="flex items-center justify-between sm:justify-end gap-2 sm:gap-1">
                <p class="text-xs sm:text-sm text-[var(--color-text-secondary)]">{{ briefing.date }}</p>
                <div class="flex items-center gap-1 shrink-0">
                  <span class="px-2 py-0.5 sm:py-1 rounded-full text-xs whitespace-nowrap hidden sm:inline"
                    :class="statusClass(briefing.status)">
                    {{ statusText(briefing.status) }}
                  </span>
                  <span class="text-base sm:text-lg">▶️</span>
                </div>
              </div>
            </div>
          </router-link>
          <button @click.stop="confirmDelete(briefing)"
            class="p-1.5 rounded-lg text-[var(--color-text-secondary)] md:opacity-0 md:group-hover:opacity-100 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500 transition-all self-center sm:self-center mt-0 sm:mt-0"
            title="删除">
            🗑️
          </button>
        </div>
      </div>
      <div v-if="!briefingStore.briefings.length" class="text-center py-12 text-[var(--color-text-secondary)]">
        <p class="text-4xl mb-3">📻</p>
        <p>还没有日报，点击上方按钮生成</p>
      </div>
    </div>

    <!-- ═══ 定时任务 ═══ -->
    <div class="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] overflow-hidden">
      <button @click="showScheduledSection = !showScheduledSection"
        class="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-[var(--color-bg)]/50 transition-colors">
        <h3 class="text-lg font-bold text-[var(--color-text)]">⏰ 定时任务</h3>
        <div class="flex items-center gap-3">
          <span class="text-xs text-[var(--color-text-secondary)]">{{ scheduledTaskStore.tasks.length }} 个任务</span>
          <span class="text-sm text-[var(--color-text-secondary)] transition-transform"
            :class="showScheduledSection ? 'rotate-180' : ''">▼</span>
        </div>
      </button>

      <div v-if="showScheduledSection" class="px-6 pb-6 space-y-4">
        <!-- New task button -->
        <div class="flex justify-end">
          <button @click="openCreateModal"
            class="px-4 py-2 bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-secondary)] text-white rounded-lg text-sm font-medium">
            + 新建定时任务
          </button>
        </div>

        <!-- Task list -->
        <div v-if="scheduledTaskStore.tasks.length === 0" class="text-center py-8 text-[var(--color-text-secondary)]">
          <p class="text-3xl mb-2">⏰</p>
          <p>暂无定时任务，点击上方按钮创建</p>
        </div>

        <div v-else class="space-y-2">
          <div v-for="task in scheduledTaskStore.tasks" :key="task.id"
            class="flex flex-col sm:flex-row sm:items-center sm:justify-between p-3 rounded-xl border border-[var(--color-border)] hover:border-[var(--color-primary)]/30 transition-colors gap-2 sm:gap-3">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-[var(--color-text)] text-sm">{{ task.name }}</span>
                <span class="px-1.5 py-0.5 rounded text-xs font-mono bg-[var(--color-bg)] text-[var(--color-text-secondary)]">
                  {{ cronToHuman(task.cron_expr) }}
                </span>
              </div>
              <div class="flex items-center gap-3 mt-1 text-xs text-[var(--color-text-secondary)] flex-wrap">
                <span>{{ timeRangeLabel(task.time_range) }}</span>
                <span>{{ task.group_id ? (groupName(task.group_id) || '分组' + task.group_id) : '📂 全部' }}</span>
                <span>{{ task.include_audio ? '🔊 含音频' : '📄 仅文本' }}</span>
                <span v-if="task.ref_audio_id && task.include_audio">🎤 指定音色</span>
                <span v-if="task.tts_edge_voice && task.include_audio">🌐 {{ task.tts_edge_voice }}</span>
                <span v-if="task.last_run_at">上次: {{ formatTime(task.last_run_at) }}</span>
                <span v-else>尚未执行</span>
              </div>
            </div>
            <div class="flex items-center gap-1 shrink-0 self-end sm:self-center">
              <!-- Toggle switch -->
              <button @click="toggleTask(task)"
                class="relative w-10 h-5 rounded-full transition-colors"
                :class="task.enabled ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'"
                :title="task.enabled ? '点击禁用' : '点击启用'">
                <span class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"
                  :class="task.enabled ? 'translate-x-5' : ''"></span>
              </button>
              <!-- Execute now -->
              <button @click="executeNow(task)"
                class="p-1.5 rounded-lg text-sm hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:text-blue-500"
                title="立即执行"
                :disabled="executingTasks.has(task.id)">
                {{ executingTasks.has(task.id) ? '⏳' : '▶️' }}
              </button>
              <!-- Edit -->
              <button @click="openEditModal(task)"
                class="p-1.5 rounded-lg text-sm hover:bg-gray-100 dark:hover:bg-gray-700"
                title="编辑">
                ✏️
              </button>
              <!-- Delete -->
              <button @click="confirmDeleteTask(task)"
                class="p-1.5 rounded-lg text-sm hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500"
                title="删除">
                🗑️
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 新建/编辑 弹窗 ═══ -->
    <div v-if="showTaskModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="closeTaskModal">
      <div class="bg-[var(--color-surface)] rounded-2xl p-6 w-full max-w-md shadow-xl">
        <h3 class="text-lg font-bold text-[var(--color-text)] mb-4">
          {{ editingTask ? '编辑定时任务' : '新建定时任务' }}
        </h3>

        <div class="space-y-4">
          <!-- Name -->
          <div>
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">任务名称 *</label>
            <input v-model="taskForm.name" type="text" placeholder="例如：每日早间播报"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
          </div>

          <!-- Time: simplified HH:MM mode -->
          <div>
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">执行时间</label>
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-sm text-[var(--color-text-secondary)]">每天</span>
              <div class="flex items-center gap-1">
                <input v-model="taskForm.timeHour" type="number" min="0" max="23"
                  class="w-14 sm:w-16 px-2 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] text-center focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                  placeholder="08" />
                <span class="text-sm text-[var(--color-text-secondary)]">:</span>
                <input v-model="taskForm.timeMinute" type="number" min="0" max="59"
                  class="w-14 sm:w-16 px-2 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] text-center focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                  placeholder="00" />
              </div>
              <button @click="showRawCron = !showRawCron" class="text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-primary)]">
                {{ showRawCron ? '简化模式' : '高级' }}
              </button>
            </div>
            <!-- Raw cron input (advanced) -->
            <div v-if="showRawCron" class="mt-2">
              <input v-model="taskForm.cron_expr" type="text" placeholder="0 8 * * *"
                class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
              <p class="text-xs text-[var(--color-text-secondary)] mt-1">标准 Cron 表达式（分 时 日 月 周）</p>
            </div>
          </div>

          <!-- Time range -->
          <div>
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">时间范围</label>
            <select v-model="taskForm.time_range"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]">
              <option value="today">📅 当天</option>
              <option value="12h">🕐 近12小时</option>
              <option value="24h">🕐 近24小时</option>
            </select>
          </div>

          <!-- Group -->
          <div>
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">分组</label>
            <select v-model="taskForm.group_id"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]">
              <option :value="null">📂 全部</option>
              <option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}</option>
            </select>
          </div>

          <!-- Include audio -->
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium text-[var(--color-text)]">生成音频</label>
            <button @click="taskForm.include_audio = !taskForm.include_audio"
              class="relative w-10 h-5 rounded-full transition-colors"
              :class="taskForm.include_audio ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'">
              <span class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"
                :class="taskForm.include_audio ? 'translate-x-5' : ''"></span>
            </button>
          </div>

          <!-- Reference audio (only for nano engine) -->
          <div v-if="ttsEngine === 'moss-tts-nano'">
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">参考音色</label>
            <select v-model="taskForm.ref_audio_id"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]">
              <option :value="null">🎤 使用全局默认</option>
              <option v-for="audio in refAudios" :key="audio.id" :value="audio.id">
                {{ audio.name }}{{ audio.active ? ' (当前默认)' : '' }}
              </option>
            </select>
          </div>

          <!-- Edge TTS voice (only for edge engine) -->
          <div v-if="ttsEngine === 'edge-tts'">
            <label class="block text-sm font-medium text-[var(--color-text)] mb-1">语音音色</label>
            <select v-model="taskForm.tts_edge_voice"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]">
              <option :value="null">🌐 使用全局默认</option>
              <option v-for="v in edgeVoices" :key="v.short_name" :value="v.short_name">
                {{ v.display_name }} ({{ v.gender === 'Female' ? '女声' : '男声' }})
              </option>
            </select>
          </div>
        </div>

        <div class="flex gap-2 mt-6">
          <button @click="closeTaskModal"
            class="flex-1 px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)] text-sm">
            取消
          </button>
          <button @click="saveTask" :disabled="savingTask"
            class="flex-1 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm disabled:opacity-50">
            {{ savingTask ? '保存中...' : (editingTask ? '保存' : '创建') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, inject, computed } from 'vue'
import { useBriefingStore } from '../stores/briefingStore'
import { useScheduledTaskStore } from '../stores/scheduledTaskStore'
import { groupsApi, settingsApi } from '../api'
import api from '../api'

const briefingStore = useBriefingStore()
const scheduledTaskStore = useScheduledTaskStore()
const showToast = inject('showToast')

const generating = ref(false)
const selectedTimeRange = ref('today')
const selectedGroupId = ref(null)
const selectedRefAudioId = ref(null)
const refAudios = ref([])
const ttsEngine = ref('edge-tts')
const groups = ref([])
const selectedEdgeVoice = ref(null)
const edgeVoices = ref([])
const edgeVoicesLoading = ref(false)

// ── Scheduled tasks UI state ──
const showScheduledSection = ref(true)
const showTaskModal = ref(false)
const editingTask = ref(null)
const savingTask = ref(false)
const showRawCron = ref(false)
const executingTasks = ref(new Set())

const taskForm = reactive({
  name: '',
  cron_expr: '0 8 * * *',
  time_range: 'today',
  group_id: null,
  include_audio: true,
  ref_audio_id: null,
  tts_edge_voice: null,
  timeHour: 8,
  timeMinute: 0,
})

// ── Lifecycle ──
onMounted(async () => {
  await Promise.all([
    briefingStore.loadBriefings(),
    scheduledTaskStore.loadTasks(),
    loadGroups(),
    loadRefAudios(),
    loadTtsEngine(),
    loadEdgeVoices(),
  ])
})

async function loadGroups() {
  try {
    const res = await groupsApi.list()
    groups.value = res.data
  } catch (e) {
    console.error('Failed to load groups:', e)
  }
}

async function loadRefAudios() {
  try {
    const res = await api.get('/settings/tts-ref-audios')
    refAudios.value = res.data.audios || []
  } catch (e) {
    console.error('Failed to load ref audios:', e)
  }
}

async function loadTtsEngine() {
  try {
    const res = await settingsApi.getAll()
    const engine = res.data.find(item => item.key === 'tts_engine')
    if (engine) ttsEngine.value = engine.value
  } catch (e) {
    console.error('Failed to load TTS engine:', e)
  }
}

async function loadEdgeVoices() {
  edgeVoicesLoading.value = true
  try {
    const res = await api.get('/settings/tts-edge-voices', { timeout: 15000 })
    // Only show Chinese voices in the briefings page selector
    edgeVoices.value = (res.data.voices || []).filter(v => v.is_chinese)
  } catch (e) {
    console.error('Failed to load edge voices:', e)
  } finally {
    edgeVoicesLoading.value = false
  }
}

// ── Helpers ──

function statusClass(status) {
  switch (status) {
    case 'completed': return 'bg-green-100 dark:bg-green-900/30 text-green-600'
    case 'generating': return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-600'
    case 'failed': return 'bg-red-100 dark:bg-red-900/30 text-red-600'
    default: return 'bg-gray-100 dark:bg-gray-800 text-gray-500'
  }
}

function statusText(status) {
  switch (status) {
    case 'completed': return '已完成'
    case 'generating': return '生成中'
    case 'failed': return '失败'
    default: return '待生成'
  }
}

function timeRangeLabel(tr) {
  switch (tr) {
    case 'today': return '📅 当天'
    case '12h': return '🕐 近12小时'
    case '24h': return '🕐 近24小时'
    default: return tr
  }
}

function formatTime(dt) {
  if (!dt) return ''
  // Ensure UTC timezone: if the string lacks timezone suffix, treat as UTC
  // Valid timezone suffixes: Z, +HH:MM, -HH:MM
  const hasTz = /[Z+-]\d{2}:\d{2}$/.test(dt) || dt.endsWith('Z')
  const utcStr = hasTz ? dt : dt + 'Z'
  const d = new Date(utcStr)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function groupName(id) {
  const g = groups.value.find(g => g.id === id)
  return g ? g.name : null
}

/**
 * Convert cron expression to human-readable Chinese text.
 * Supports common patterns like "0 8 * * *" → "每天 08:00"
 */
function cronToHuman(cron) {
  if (!cron) return cron
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return cron

  const [minute, hour, dom, month, dow] = parts

  // Daily: "0 8 * * *"
  if (dom === '*' && month === '*' && dow === '*') {
    return `每天 ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
  }

  // Weekdays: "0 9 * * 1-5"
  if (dom === '*' && month === '*' && dow === '1-5') {
    return `工作日 ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
  }

  // Weekly: "0 9 * * 1" etc.
  if (dom === '*' && month === '*' && /^[0-6]$/.test(dow)) {
    const weekdays = ['日', '一', '二', '三', '四', '五', '六']
    return `每周${weekdays[parseInt(dow)]} ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
  }

  // Fallback: show raw
  return cron
}

// ── Generate briefing ──

async function generateBriefing() {
  generating.value = true
  try {
    const res = await briefingStore.generateBriefing({
      time_range: selectedTimeRange.value,
      group_id: selectedGroupId.value,
      ref_audio_id: selectedRefAudioId.value,
      tts_edge_voice: selectedEdgeVoice.value,
    })
    if (res?.no_content) {
      showToast('所选时间范围内没有新文章', 'info')
    } else if (res?.status === 'failed') {
      showToast('生成失败：' + (res.script_text || 'LLM API 配置有误'), 'error')
    } else if (res?.audio_path) {
      showToast('日报生成完成（含音频）🎉', 'success')
    } else {
      showToast('脚本已生成，音频正在合成中…', 'success')
    }
  } catch (e) {
    const msg = e.response?.data?.detail || e.message || ''
    showToast(msg.includes('API') ? '请先在设置中配置 LLM API' : '生成失败：' + msg, 'error')
  } finally {
    generating.value = false
  }
}

async function confirmDelete(briefing) {
  if (!confirm(`确定要删除「${briefing.title}」吗？`)) return
  try {
    await briefingStore.deleteBriefing(briefing.id)
    showToast('已删除', 'success')
  } catch (e) {
    showToast('删除失败', 'error')
  }
}

// ── Scheduled task CRUD ──

function openCreateModal() {
  editingTask.value = null
  showRawCron.value = false
  taskForm.name = ''
  taskForm.cron_expr = '0 8 * * *'
  taskForm.time_range = 'today'
  taskForm.group_id = null
  taskForm.include_audio = true
  taskForm.ref_audio_id = null
  taskForm.tts_edge_voice = null
  taskForm.timeHour = 8
  taskForm.timeMinute = 0
  showTaskModal.value = true
}

function openEditModal(task) {
  editingTask.value = task
  const parts = task.cron_expr.split(/\s+/)
  taskForm.name = task.name
  taskForm.cron_expr = task.cron_expr
  taskForm.time_range = task.time_range
  taskForm.group_id = task.group_id
  taskForm.include_audio = task.include_audio
  taskForm.ref_audio_id = task.ref_audio_id || null
  taskForm.tts_edge_voice = task.tts_edge_voice || null
  // Parse hour/minute from cron
  if (parts.length === 5) {
    taskForm.timeMinute = parseInt(parts[0]) || 0
    taskForm.timeHour = parseInt(parts[1]) || 8
  } else {
    taskForm.timeHour = 8
    taskForm.timeMinute = 0
  }
  showRawCron.value = parts.length !== 5 || parts[2] !== '*' || parts[3] !== '*' || parts[4] !== '*'
  showTaskModal.value = true
}

function closeTaskModal() {
  showTaskModal.value = false
  editingTask.value = null
}

function buildCronExpr() {
  if (showRawCron.value && taskForm.cron_expr.trim()) {
    return taskForm.cron_expr.trim()
  }
  const h = String(taskForm.timeHour).padStart(2, '0')
  const m = String(taskForm.timeMinute).padStart(2, '0')
  return `${m} ${h} * * *`
}

async function saveTask() {
  if (!taskForm.name.trim()) {
    showToast('请填写任务名称', 'error')
    return
  }

  savingTask.value = true
  try {
    const data = {
      name: taskForm.name.trim(),
      cron_expr: buildCronExpr(),
      time_range: taskForm.time_range,
      group_id: taskForm.group_id,
      include_audio: taskForm.include_audio,
      ref_audio_id: taskForm.ref_audio_id,
      tts_edge_voice: taskForm.tts_edge_voice,
    }

    if (editingTask.value) {
      await scheduledTaskStore.updateTask(editingTask.value.id, data)
      showToast('定时任务已更新', 'success')
    } else {
      await scheduledTaskStore.createTask(data)
      showToast('定时任务已创建', 'success')
    }
    closeTaskModal()
  } catch (e) {
    const msg = e.response?.data?.detail || e.message || ''
    showToast('保存失败：' + msg, 'error')
  } finally {
    savingTask.value = false
  }
}

async function toggleTask(task) {
  try {
    await scheduledTaskStore.toggleTask(task.id)
    showToast(task.enabled ? '已禁用' : '已启用', 'success')
  } catch (e) {
    showToast('操作失败', 'error')
  }
}

async function executeNow(task) {
  executingTasks.value.add(task.id)
  try {
    const res = await scheduledTaskStore.executeNow(task.id)
    if (res?.no_content) {
      showToast('所选时间范围内没有新文章', 'info')
    } else if (res?.briefing_id) {
      showToast('执行完成，日报已生成 🎉', 'success')
      await briefingStore.loadBriefings()
    } else {
      showToast('执行失败', 'error')
    }
  } catch (e) {
    const msg = e.response?.data?.detail || e.message || ''
    showToast('执行失败：' + msg, 'error')
  } finally {
    executingTasks.value.delete(task.id)
  }
}

async function confirmDeleteTask(task) {
  if (!confirm(`确定要删除定时任务「${task.name}」吗？`)) return
  try {
    await scheduledTaskStore.deleteTask(task.id)
    showToast('已删除', 'success')
  } catch (e) {
    showToast('删除失败', 'error')
  }
}
</script>
