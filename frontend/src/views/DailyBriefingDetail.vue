<template>
  <div class="space-y-4">
    <button @click="$router.back()" class="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-primary)]">
      ← 返回日报列表
    </button>

    <div v-if="loading" class="animate-pulse space-y-4">
      <div class="h-8 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div>
      <div class="h-32 bg-gray-200 dark:bg-gray-700 rounded"></div>
    </div>

    <div v-else-if="briefing" class="space-y-4">
      <div class="bg-[var(--color-surface)] rounded-2xl p-6 border border-[var(--color-border)]">
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0 flex-1">
            <h1 class="text-2xl font-bold text-[var(--color-text)] truncate">{{ briefing.title }}</h1>
            <p class="text-sm text-[var(--color-text-secondary)] mt-1">{{ briefing.date }}</p>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <!-- Engine badge -->
            <span class="px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap"
              :class="isDialogue
                ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-600'
                : 'bg-cyan-100 dark:bg-cyan-900/30 text-cyan-600'"
              :title="ttsEngineName === 'moss-tts-nano' ? '音色克隆：使用参考音频音色' : '双人对播'">
              {{ isDialogue ? '🎙️ 双人对播' : (ttsEngineName === 'moss-tts-nano' ? '🎤 音色克隆' : '🎤 单人播报') }}
            </span>
            <!-- Reference audio label -->
            <span v-if="briefing.ref_audio_id && refAudioLabel"
              class="px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-600 whitespace-nowrap"
              title="此次使用的参考音色">
              🎤 {{ refAudioLabel }}
            </span>
            <!-- Delete button -->
            <button @click="confirmDelete"
              class="p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500 transition-all"
              title="删除这篇播报">
              🗑️
            </button>
            <!-- Regenerate audio button -->
            <button @click="regenerateAudio" v-if="briefing.audio_path || streamState === 'done'"
              class="p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-amber-50 dark:hover:bg-amber-900/20 hover:text-amber-500 transition-all"
              title="重新生成音频">
              🔄
            </button>
          </div>
        </div>

        <!-- Audio Player / Stream -->
        <div class="mt-4 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl">
          <!-- Streaming in progress -->
          <div v-if="streamState === 'connecting'" class="text-center text-sm text-[var(--color-text-secondary)]">
            <span class="inline-block animate-pulse">🔌 正在连接音频流...</span>
          </div>
          <div v-else-if="streamState === 'streaming'" class="flex items-center gap-4">
            <button @click="togglePlay" class="w-12 h-12 rounded-full bg-[var(--color-primary)] text-white flex items-center justify-center text-xl hover:bg-[var(--color-primary-dark)] shrink-0">
              {{ playing ? '⏸' : '▶️' }}
            </button>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-xs text-[var(--color-text-secondary)] w-10">{{ formatTime(currentTime) }}</span>
                <div class="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-full cursor-pointer relative" @click="seek">
                  <div class="h-full bg-[var(--color-primary)] rounded-full" :style="{ width: progress + '%' }"></div>
                </div>
                <span class="text-xs text-[var(--color-text-secondary)] w-10 text-right">{{ formatTime(duration) }}</span>
              </div>
            </div>
          </div>
          <!-- Standard player (audio file ready) -->
          <div v-else-if="briefing.audio_path" class="flex items-center gap-4">
            <audio ref="audioEl" :src="audioUrl" @timeupdate="onTimeUpdate" @loadedmetadata="onLoaded" class="hidden"></audio>
            <button @click="togglePlay" class="w-12 h-12 rounded-full bg-[var(--color-primary)] text-white flex items-center justify-center text-xl hover:bg-[var(--color-primary-dark)] shrink-0">
              {{ playing ? '⏸' : '▶️' }}
            </button>
            <div class="flex-1">
              <div class="flex items-center gap-2">
                <span class="text-xs text-[var(--color-text-secondary)] w-10">{{ formatTime(currentTime) }}</span>
                <div class="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-full cursor-pointer relative" @click="seek">
                  <div class="h-full bg-[var(--color-primary)] rounded-full" :style="{ width: progress + '%' }"></div>
                </div>
                <span class="text-xs text-[var(--color-text-secondary)] w-10 text-right">{{ formatTime(duration) }}</span>
              </div>
              <div class="flex items-center gap-2 mt-2">
                <button v-for="rate in [0.5, 1, 1.5, 2]" :key="rate" @click="setPlaybackRate(rate)"
                  class="px-2 py-0.5 rounded text-xs"
                  :class="playbackRate === rate ? 'bg-[var(--color-primary)] text-white' : 'bg-gray-200 dark:bg-gray-700 text-[var(--color-text-secondary)]'">
                  {{ rate }}x
                </button>
              </div>
            </div>
          </div>
          <!-- No audio yet, show status -->
          <div v-else class="text-center text-sm" :class="
            briefing.script_text && briefing.status !== 'failed'
              ? 'text-yellow-600 dark:text-yellow-400'
              : 'text-[var(--color-text-secondary)]'">
            {{ streamState === 'polling' ? '⏳ 音频合成中，请稍候...' : (briefing.script_text && briefing.status !== 'failed' ? '🎵 音频准备中...' : '暂无音频') }}
          </div>
        </div>
      </div>

      <!-- Script -->
      <div class="bg-[var(--color-surface)] rounded-2xl p-6 border border-[var(--color-border)]">
        <h3 class="font-semibold text-[var(--color-text)] mb-4">📜 播报脚本</h3>

        <!-- Dual-speaker dialogue style -->
        <div v-if="isDialogue" class="space-y-4" ref="scriptContainer">
          <div v-for="(segment, index) in scriptSegments" :key="index"
            class="p-3 rounded-xl">
            <span class="inline-block px-2 py-0.5 rounded text-xs font-medium mb-1"
              :class="segment.speaker === 'S1' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600' : 'bg-green-100 dark:bg-green-900/30 text-green-600'">
              {{ segment.speaker === 'S1' ? '🎤 主播一' : '🎤 主播二' }}
            </span>
            <p class="text-sm text-[var(--color-text)] leading-relaxed">{{ segment.text }}</p>
          </div>
        </div>

        <!-- Single narration style -->
        <div v-else class="prose prose-sm max-w-none" ref="scriptContainer">
          <div v-for="(paragraph, index) in narrationParagraphs" :key="index"
            class="p-3 rounded-xl mb-2">
            <p class="text-sm text-[var(--color-text)] leading-relaxed">{{ paragraph }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBriefingStore } from '../stores/briefingStore'
import { briefingsApi } from '../api'
import api from '../api'

const route = useRoute()
const router = useRouter()
const briefingStore = useBriefingStore()
const showToast = inject('showToast')

const briefing = ref(null)
const loading = ref(true)
const audioUrl = ref('')
const audioEl = ref(null)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const progress = ref(0)
const playbackRate = ref(1)
const scriptContainer = ref(null)
const refAudios = ref([])

// ── Reference audio label lookup ──
const refAudioLabel = computed(() => {
  if (!briefing.value?.ref_audio_id) return ''
  const found = refAudios.value.find(a => a.id === briefing.value.ref_audio_id)
  return found ? found.name : briefing.value.ref_audio_id
})

// Streaming state
const streamState = ref('idle') // 'idle' | 'connecting' | 'streaming' | 'done' | 'error'
const streamChunksReceived = ref(0)
const streamTotalChunks = ref(0)
const streamDonePending = ref(false) // true: all chunks received, AudioContext still playing
const ttsEngineName = ref('')
let eventSource = null
let audioContext = null
let scheduledTime = 0
let progressInterval = null

// Detect engine type from script content
const isDialogue = computed(() => {
  if (!briefing.value?.script_text) return false
  return briefing.value.script_text.includes('[S1]') || briefing.value.script_text.includes('[S2]')
})

// Parse [S1]/[S2] segments for dialogue display
const scriptSegments = computed(() => {
  if (!briefing.value?.script_text) return []
  const parts = briefing.value.script_text.split(/(\[S1\]|\[S2\])/).filter(Boolean)
  const segments = []
  let currentSpeaker = 'S1'
  for (const part of parts) {
    if (part === '[S1]') { currentSpeaker = 'S1'; continue }
    if (part === '[S2]') { currentSpeaker = 'S2'; continue }
    if (part.trim()) {
      segments.push({ speaker: currentSpeaker, text: part.trim() })
    }
  }
  return segments
})

// Split narration into paragraphs for single-speaker display
const narrationParagraphs = computed(() => {
  if (!briefing.value?.script_text) return []
  return briefing.value.script_text
    .split('\n')
    .map(p => p.trim())
    .filter(p => p.length > 0)
})

onMounted(async () => {
  const data = await briefingStore.getBriefing(route.params.id)
  briefing.value = data

  if (data.audio_path) {
    // Audio file already exists — play directly
    audioUrl.value = briefingsApi.getAudio(data.id)
  } else if (data.script_text && data.script_text !== '暂无新闻更新。' && data.status !== 'failed') {
    // Script is ready but no audio yet — start streaming immediately
    startStreaming(data.id)
  }

  // Check current TTS config for voice info display
  try {
    const ttsRes = await briefingsApi.getTtsBackends()
    ttsEngineName.value = ttsRes.data.active
  } catch (_) {}
  // Load ref audio list for label lookup
  try {
    const res = await api.get('/settings/tts-ref-audios')
    refAudios.value = res.data.audios || []
  } catch (_) {}
  loading.value = false
})

onUnmounted(() => {
  stopStreaming()
  if (audioEl.value) {
    audioEl.value.pause()
    audioEl.value = null
  }
})

// ─── Streaming ───

function startStreaming(briefingId) {
  streamState.value = 'connecting'
  const url = `/api/daily-briefings/${briefingId}/stream-audio`

  eventSource = new EventSource(url)

  eventSource.onopen = () => {
    streamState.value = 'streaming'
  }

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)

      if (data.type === 'chunk') {
        streamChunksReceived.value = data.index + 1
        streamTotalChunks.value = data.total
        playAudioChunk(data.audio_base64, data.sample_rate)
      } else       if (data.type === 'done') {
        // Streaming logically complete — don't close AudioContext yet,
        // let it finish playing the already-scheduled chunks naturally.
        streamDonePending.value = true
        eventSource.close()
        eventSource = null

        // Update briefing with the saved audio path for later replay
        if (data.audio_path && briefing.value) {
          briefing.value.audio_path = data.audio_path
          briefing.value.status = 'completed'
          audioUrl.value = briefingsApi.getAudio(briefing.value.id)
        }
        showToast('音频已生成', 'success')
      } else if (data.type === 'error') {
        streamState.value = 'error'
        showToast(data.message || '音频生成失败', 'error')
        eventSource.close()
        eventSource = null
        if (progressInterval) {
          clearInterval(progressInterval)
          progressInterval = null
        }
      }
    } catch (e) {
      console.error('Failed to parse SSE event:', e)
    }
  }

  eventSource.onerror = () => {
    if (streamState.value === 'done' || streamState.value === 'error' || streamDonePending.value) return
    console.error('SSE connection error, will auto-reconnect...')
  }
}

function stopStreaming() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  streamDonePending.value = false
  if (audioContext) {
    audioContext.close().catch(() => {})
    audioContext = null
  }
  if (progressInterval) {
    clearInterval(progressInterval)
    progressInterval = null
  }
}

function playAudioChunk(audioBase64, sampleRate) {
  // Create/resume AudioContext on first chunk
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)()
    scheduledTime = audioContext.currentTime
  }
  if (audioContext.state === 'suspended') {
    audioContext.resume()
  }

  // Decode base64 → PCM float32 bytes → Float32Array
  const binaryStr = atob(audioBase64)
  const bytes = new Uint8Array(binaryStr.length)
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i)
  }
  const float32Array = new Float32Array(bytes.buffer)

  // Create AudioBuffer for this chunk
  const buffer = audioContext.createBuffer(1, float32Array.length, sampleRate)
  buffer.getChannelData(0).set(float32Array)

  // Schedule playback immediately (seamless concatenation)
  const source = audioContext.createBufferSource()
  source.buffer = buffer
  source.connect(audioContext.destination)
  source.start(scheduledTime)

  const chunkDuration = float32Array.length / sampleRate
  scheduledTime += chunkDuration

  // Update UI
  if (!playing.value) {
    playing.value = true
  }
  duration.value = scheduledTime

  // Track progress
  if (!progressInterval) {
    progressInterval = setInterval(() => {
      // Check if AudioContext has finished playing all scheduled chunks
      if (streamDonePending.value && audioContext && scheduledTime > 0) {
        if (audioContext.currentTime >= scheduledTime) {
          // All chunks finished — clean up and switch to done state
          audioContext.close().catch(() => {})
          audioContext = null
          streamDonePending.value = false
          streamState.value = 'done'
          playing.value = false
          currentTime.value = 0
          progress.value = 0
          clearInterval(progressInterval)
          progressInterval = null
          return
        }
      }
      // Normal progress update
      if (audioContext && playing.value) {
        const elapsed = audioContext.currentTime
        currentTime.value = elapsed
        if (scheduledTime > 0) {
          progress.value = Math.min((elapsed / scheduledTime) * 100, 100)
        }
      }
    }, 250)
  }
}

// ─── CRUD & Playback ───

async function confirmDelete() {
  if (!briefing.value) return
  if (!confirm(`确定要删除「${briefing.value.title}」吗？`)) return
  stopStreaming()
  try {
    await briefingStore.deleteBriefing(briefing.value.id)
    showToast('已删除', 'success')
    router.back()
  } catch (e) {
    showToast('删除失败', 'error')
  }
}

function togglePlay() {
  if (streamState.value === 'streaming') {
    // Toggle AudioContext during streaming
    if (audioContext) {
      if (audioContext.state === 'suspended') {
        audioContext.resume()
        playing.value = true
      } else {
        audioContext.suspend()
        playing.value = false
      }
    }
    return
  }

  // Standard <audio> element playback
  if (!audioEl.value) return
  if (playing.value) {
    audioEl.value.pause()
  } else {
    audioEl.value.play()
  }
  playing.value = !playing.value
}

async function regenerateAudio() {
  if (!confirm('确定要重新生成音频吗？现有音频将被删除。')) return
  stopStreaming()
  try {
    await fetch(`/api/daily-briefings/${briefing.value.id}/regenerate-audio`, { method: 'POST' })
    briefing.value.audio_path = null
    briefing.value.status = 'completed'
    audioUrl.value = ''
    showToast('音频已重置，开始重新生成...', 'success')
    // Start streaming
    startStreaming(briefing.value.id)
  } catch (e) {
    showToast('重置失败', 'error')
  }
}

function onTimeUpdate() {
  if (!audioEl.value) return
  currentTime.value = audioEl.value.currentTime
  duration.value = audioEl.value.duration || 0
  progress.value = duration.value ? (currentTime.value / duration.value) * 100 : 0
}

function onLoaded() {
  duration.value = audioEl.value?.duration || 0
}

function seek(e) {
  if (streamState.value === 'streaming') return // Can't seek during live stream
  if (!audioEl.value) return
  const rect = e.currentTarget.getBoundingClientRect()
  const pos = (e.clientX - rect.left) / rect.width
  audioEl.value.currentTime = pos * duration.value
}

function setPlaybackRate(rate) {
  playbackRate.value = rate
  if (audioEl.value) audioEl.value.playbackRate = rate
}

function formatTime(t) {
  if (!t || !isFinite(t)) return '0:00'
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
</script>

<style>
.prose {
  color: var(--color-text);
  line-height: 1.8;
}
.prose img {
  max-width: 100%;
  border-radius: 8px;
}
.prose a {
  color: var(--color-primary);
  text-decoration: underline;
}
.prose blockquote {
  border-left: 3px solid var(--color-primary);
  padding-left: 1rem;
  margin: 1rem 0;
  opacity: 0.8;
}
.prose pre {
  background: #1e293b;
  color: #e2e8f0;
  padding: 1rem;
  border-radius: 8px;
  overflow-x: auto;
}
.prose code {
  font-size: 0.875em;
}
</style>
