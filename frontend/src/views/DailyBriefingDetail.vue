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
            <button @click="regenerateAudio" v-if="briefing.audio_path || streamState === 'done' || streamState === 'error' || briefing.status === 'failed'"
              class="p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-amber-50 dark:hover:bg-amber-900/20 hover:text-amber-500 transition-all"
              title="重新生成音频">
              🔄
            </button>
          </div>
        </div>

        <!-- Audio Player / Stream -->
        <div class="mt-4 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl">
          <!-- Hidden audio element used by both streaming and standard playback -->
          <audio ref="audioEl" :src="audioUrl" @timeupdate="onTimeUpdate" @loadedmetadata="onLoaded" @ended="onEnded" preload="auto" class="hidden"></audio>

          <!-- Streaming in progress -->
          <div v-if="streamState === 'connecting'" class="text-center text-sm text-[var(--color-text-secondary)]">
            <span class="inline-block animate-pulse">🔌 正在连接音频流...</span>
          </div>
          <div v-else-if="streamState === 'streaming' || (streamDonePending && playing && !fullAudioReady)" class="flex items-center gap-4">
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
import { ref, computed, onMounted, onUnmounted, inject, nextTick } from 'vue'
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
const streamDonePending = ref(false) // true: all chunks received, playing from partial blob
const ttsEngineName = ref('')
let eventSource = null

// WAV Blob playback (replaces Web Audio API — iOS doesn't play AudioContext reliably)
let rawPcmBuffers = []         // {float32: Float32Array, sampleRate: number}[]
let rawPcmTotalSamples = 0     // total float32 samples accumulated
let estimatedDuration = 0
let partialBlobUrl = null      // object URL for partial playback
let fullAudioReady = false     // true when saved .wav file is available

// ── Playback progress persistence (localStorage) ──
// Stores both absolute time AND ratio (currentTime / duration).
// On restore, try absolute first; if the audio duration differs (e.g. re-generated),
// fall back to ratio to preserve position in content.
const PROGRESS_PREFIX = 'briefing_progress_'
const PROGRESS_TTL = 24 * 60 * 60 * 1000  // 24 hours
let progressSaveInterval = null
let progressRetryTimer = null
let suppressProgressSave = false  // prevents overwriting saved position during src transitions
let pendingRestoreTime = null     // used during streaming: seek after WAV blob is built

function saveProgress() {
  if (suppressProgressSave) return  // skip during audio src transitions
  if (!briefing.value?.id || !audioEl.value?.duration) return
  if (audioEl.value.duration <= 0) return
  const currentTime = audioEl.value.currentTime
  const duration = audioEl.value.duration
  const key = PROGRESS_PREFIX + briefing.value.id

  // Guard: if currentTime is near 0 (< 0.5s), the audio src was likely just
  // changed/reset. Don't overwrite a valid position with 0.
  if (currentTime < 0.5) {
    try {
      const prevRaw = localStorage.getItem(key)
      if (prevRaw) {
        const prev = JSON.parse(prevRaw)
        if (prev.currentTime >= 1 && prev.ratio > 0) {
          console.log(`[Progress] SKIPPED (currentTime=${currentTime.toFixed(1)}s too small, keeping ${prev.currentTime.toFixed(1)}s)`)
          return
        }
      }
    } catch (_) {}
  }

  const data = {
    currentTime,
    duration,
    ratio: duration > 0 ? currentTime / duration : 0,
    updatedAt: Date.now()
  }
  try {
    localStorage.setItem(key, JSON.stringify(data))
    console.log(`[Progress] SAVED briefing=${briefing.value.id} currentTime=${currentTime.toFixed(1)}s duration=${duration.toFixed(1)}s ratio=${data.ratio.toFixed(4)}`)
  } catch (_) {}
}

function loadProgress() {
  if (!briefing.value?.id) return null
  try {
    const raw = localStorage.getItem(PROGRESS_PREFIX + briefing.value.id)
    if (!raw) return null
    const data = JSON.parse(raw)
    // Expired
    if (Date.now() - data.updatedAt > PROGRESS_TTL) {
      localStorage.removeItem(PROGRESS_PREFIX + briefing.value.id)
      console.log(`[Progress] EXPIRED briefing=${briefing.value.id}`)
      return null
    }
    // Nearly finished — treat as complete
    if (data.duration > 0 && data.currentTime >= data.duration - 1) {
      localStorage.removeItem(PROGRESS_PREFIX + briefing.value.id)
      console.log(`[Progress] CLEARED (near end) briefing=${briefing.value.id}`)
      return null
    }
    console.log(`[Progress] LOADED briefing=${briefing.value.id} currentTime=${data.currentTime?.toFixed(1)}s duration=${data.duration?.toFixed(1)}s ratio=${data.ratio?.toFixed(4)}`)
    return data
  } catch (_) {
    return null
  }
}

function clearProgress() {
  if (briefing.value?.id) {
    try {
      localStorage.removeItem(PROGRESS_PREFIX + briefing.value.id)
    } catch (_) {}
  }
}

/**
 * Restore saved playback progress on the <audio> element.
 * Tries absolute time first; if the audio duration changed, falls back to ratio.
 * Retries periodically until the audio metadata is loaded.
 */
function restoreProgress(saved) {
  if (!saved || !audioEl.value) return
  console.log(`[Progress] RESTORE attempt: saved.ct=${saved.currentTime?.toFixed(1)}s`)

  let attempts = 0
  const maxAttempts = 30

  const tryRestore = () => {
    if (!audioEl.value) return false
    const el = audioEl.value
    const dur = el.duration
    if (!dur || dur <= 0 || !isFinite(dur)) return false

    let targetTime = null

    // Strategy 1: absolute time (same audio file)
    if (saved.currentTime < dur - 1) {
      targetTime = saved.currentTime
    } else {
      // Strategy 2: ratio-based (audio duration changed)
      const t = saved.ratio * dur
      if (t < dur - 1 && t > 0) targetTime = t
    }

    if (targetTime !== null) {
      el.currentTime = targetTime
      currentTime.value = targetTime
      console.log(`[Progress] RESTORED ${targetTime.toFixed(1)}s / ${dur.toFixed(1)}s`)
      return true
    }
    return false
  }

  if (tryRestore()) return

  const poll = () => {
    if (tryRestore() || attempts >= maxAttempts) return
    attempts++
    progressRetryTimer = setTimeout(poll, 300)
  }
  progressRetryTimer = setTimeout(poll, 300)
}

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

  // Must set loading=false AND await nextTick BEFORE accessing audioEl ref,
  // because <audio> is inside v-else-if="briefing" inside v-if="loading".
  loading.value = false
  await nextTick()

  if (data.audio_path) {
    // ── Audio file already exists — load the full file ──
    audioUrl.value = briefingsApi.getAudio(data.id)
    // Restore saved playback progress
    const saved = loadProgress()
    if (saved) {
      restoreProgress(saved)
    }
  } else if (data.script_text && data.script_text !== '暂无新闻更新。' && data.status !== 'failed') {
    // ── Script is ready but no audio yet — start streaming ──
    startStreaming(data.id)
    // Save target position for later restore when WAV blob is played
    const saved = loadProgress()
    if (saved) {
      pendingRestoreTime = saved.currentTime
      console.log(`[Progress] Streaming: will restore to ${pendingRestoreTime.toFixed(1)}s when blob is ready`)
    }
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

  // ── Progress persistence setup ──
  window.addEventListener('beforeunload', saveProgress)
  progressSaveInterval = setInterval(saveProgress, 10000)  // every 10s
})

onUnmounted(() => {
  saveProgress()
  window.removeEventListener('beforeunload', saveProgress)
  if (progressSaveInterval) {
    clearInterval(progressSaveInterval)
    progressSaveInterval = null
  }
  if (progressRetryTimer) {
    clearTimeout(progressRetryTimer)
    progressRetryTimer = null
  }
  stopStreaming()
  if (audioEl.value) {
    audioEl.value.pause()
    audioEl.value = null
  }
})

function stopStreaming() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  streamDonePending.value = false
  fullAudioReady = false
  pendingRestoreTime = null
  revokePartialBlob()
  rawPcmBuffers = []
  rawPcmTotalSamples = 0
  estimatedDuration = 0
  if (audioEl.value) {
    audioEl.value.pause()
    audioEl.value.currentTime = 0
  }
}

function revokePartialBlob() {
  if (partialBlobUrl) {
    URL.revokeObjectURL(partialBlobUrl)
    partialBlobUrl = null
  }
}

/**
 * Convert accumulated raw PCM float32 data to a WAV Blob.
 * Uses the sample rate from the first chunk (all chunks share the same rate).
 */
function buildWavBlob() {
  if (rawPcmBuffers.length === 0 || rawPcmTotalSamples === 0) return null

  const sampleRate = rawPcmBuffers[0].sampleRate
  const numChannels = 1
  const bitsPerSample = 16
  const bytesPerSample = bitsPerSample / 8
  const dataSize = rawPcmTotalSamples * bytesPerSample
  const bufferSize = 44 + dataSize

  const arrayBuffer = new ArrayBuffer(bufferSize)
  const view = new DataView(arrayBuffer)

  // WAV header
  writeString(view, 0, 'RIFF')
  view.setUint32(4, bufferSize - 8, true)
  writeString(view, 8, 'WAVE')
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true) // PCM
  view.setUint16(20, 1, true) // format = 1 (PCM)
  view.setUint16(22, numChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * numChannels * bytesPerSample, true) // byte rate
  view.setUint16(32, numChannels * bytesPerSample, true) // block align
  view.setUint16(34, bitsPerSample, true)
  writeString(view, 36, 'data')
  view.setUint32(40, dataSize, true)

  // Interleave & write PCM16 samples
  let offset = 44
  for (const chunk of rawPcmBuffers) {
    const arr = chunk.float32
    for (let i = 0; i < arr.length; i++) {
      const s = Math.max(-1, Math.min(1, arr[i]))
      const intSample = s < 0 ? s * 0x8000 : s * 0x7FFF
      view.setInt16(offset, intSample, true)
      offset += 2
    }
  }

  return new Blob([arrayBuffer], { type: 'audio/wav' })
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}

/**
 * Decode base64-encoded float32 PCM bytes → Float32Array.
 */
function decodePcmChunk(audioBase64) {
  const binaryStr = atob(audioBase64)
  const bytes = new Uint8Array(binaryStr.length)
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i)
  }
  return new Float32Array(bytes.buffer)
}

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
        bufferAudioChunk(data.audio_base64, data.sample_rate)
      } else if (data.type === 'done') {
        // ── Suppress progress saves immediately, before any src change ──
        suppressProgressSave = true

        // All chunks received.
        streamDonePending.value = true
        eventSource.close()
        eventSource = null

        // Save the audio path info
        if (data.audio_path && briefing.value) {
          briefing.value.audio_path = data.audio_path
          briefing.value.status = 'completed'
        }
        showToast('音频已生成', 'success')

        // If user was playing from a partial blob, switch to full saved file
        if (playing.value && partialBlobUrl && data.audio_path && briefing.value) {
          fullAudioReady = true
          audioUrl.value = briefingsApi.getAudio(briefing.value.id)
          transitionToFullAudio()
        } else {
          // User hasn't clicked play yet — just set the URL for later replay
          if (data.audio_path && briefing.value) {
            audioUrl.value = briefingsApi.getAudio(briefing.value.id)
            // Restore saved progress if we have a pending position
            if (pendingRestoreTime !== null) {
              const targetTime = pendingRestoreTime
              pendingRestoreTime = null
              // Wait for the full file to load, then seek
              const seekAfterLoad = () => {
                if (!audioEl.value) return
                const dur = audioEl.value.duration
                if (dur && dur > 0 && isFinite(dur) && targetTime < dur - 1) {
                  audioEl.value.currentTime = targetTime
                  currentTime.value = targetTime
                  console.log(`[Progress] Done (no play) seeked to ${targetTime.toFixed(1)}s`)
                }
              }
              if (audioEl.value?.readyState >= HTMLMediaElement.HAVE_METADATA) {
                seekAfterLoad()
              } else if (audioEl.value) {
                audioEl.value.addEventListener('loadedmetadata', seekAfterLoad, { once: true })
              }
            }
          }
          if (rawPcmBuffers.length > 0) {
            streamState.value = 'done'
            rawPcmBuffers = []
            rawPcmTotalSamples = 0
            estimatedDuration = 0
          }
          // Don't reset suppressProgressSave here — the src change (via Vue async DOM update)
          // happens later and would reset currentTime to 0.
          // The saveProgress() guard (currentTime < 0.5 skip) protects against saving 0.
          // Reset after a short delay to allow the audio to settle.
          setTimeout(() => { suppressProgressSave = false }, 2000)
        }
      } else if (data.type === 'error') {
        suppressProgressSave = false  // reset flag on error
        streamState.value = 'error'
        showToast(data.message || '音频生成失败', 'error')
        eventSource.close()
        eventSource = null
        revokePartialBlob()
        rawPcmBuffers = []
        rawPcmTotalSamples = 0
        estimatedDuration = 0
      }
    } catch (e) {
      console.error('Failed to parse SSE event:', e)
    }
  }

  eventSource.onerror = () => {
    if (streamState.value === 'done' || streamState.value === 'error' || streamDonePending.value) return
    console.error('SSE connection error, will auto-reconnect...')
    // If the audio file was saved while we were away, the SSE endpoint returns
    // 400 (audio already exists). Stop reconnecting and load the full file.
    if (briefing.value?.audio_path) {
      console.log('[Stream] SSE failed but audio_path exists, switching to full file')
      eventSource?.close()
      eventSource = null
      streamState.value = 'done'
      audioUrl.value = briefingsApi.getAudio(briefing.value.id)
      // Restore saved progress
      const saved = loadProgress()
      if (saved) restoreProgress(saved)
    }
  }
}

/**
 * Buffer an incoming audio chunk.
 * Raw PCM data is accumulated; no AudioContext is involved.
 * When user clicks play, the accumulated buffer is converted to a WAV Blob
 * and played via the standard <audio> element (works reliably on iOS).
 */
function bufferAudioChunk(audioBase64, sampleRate) {
  const float32 = decodePcmChunk(audioBase64)
  rawPcmBuffers.push({ float32, sampleRate })
  rawPcmTotalSamples += float32.length
  const chunkDuration = float32.length / sampleRate
  estimatedDuration += chunkDuration

  // Update progress bar estimate
  duration.value = estimatedDuration
}

/**
 * Play all accumulated PCM data as a WAV Blob via the standard <audio> element.
 * Called on user gesture (click play) — works on iOS because the <audio>
 * element handles playback natively, no AudioContext restrictions.
 */
function playAccumulatedAudio() {
  if (rawPcmBuffers.length === 0 || rawPcmTotalSamples === 0) return

  const blob = buildWavBlob()
  if (!blob) return

  revokePartialBlob()
  partialBlobUrl = URL.createObjectURL(blob)

  if (audioEl.value) {
    audioEl.value.src = partialBlobUrl
    audioEl.value.play()
    playing.value = true

    // If there's a pending restore position (from a previous visit during streaming),
    // seek to it once the blob's metadata is loaded.
    if (pendingRestoreTime !== null) {
      const targetTime = pendingRestoreTime
      pendingRestoreTime = null  // consume once
      if (audioEl.value) {
        const doSeek = () => {
          if (!audioEl.value) return
          const dur = audioEl.value.duration
          if (dur && dur > 0 && isFinite(dur) && targetTime < dur - 1) {
            audioEl.value.currentTime = targetTime
            currentTime.value = targetTime
            console.log(`[Progress] Stream blob seeked to ${targetTime.toFixed(1)}s`)
          }
        }
        if (audioEl.value.readyState >= HTMLMediaElement.HAVE_METADATA) {
          doSeek()
        } else {
          audioEl.value.addEventListener('loadedmetadata', doSeek, { once: true })
        }
      }
    }
  }
}

/**
 * Transition from partial WAV Blob playback to the full saved audio file.
 * Called when streaming finishes and we were playing from a partial blob.
 * Waits for the full file's metadata to load before seeking, so the browser
 * can honor the seek position reliably.
 * Suppresses automatic saveProgress during the transition to prevent the
 * intermediate currentTime=0 from overwriting the saved position.
 */
function transitionToFullAudio() {
  if (!audioEl.value || !audioUrl.value) return

  // Save current playback position
  const currentPos = audioEl.value.currentTime
  console.log(`[Progress] transitionToFullAudio: saving pos=${currentPos.toFixed(1)}s, switching to full file`)
  suppressProgressSave = true

  // Switch to full file
  revokePartialBlob()
  audioEl.value.src = audioUrl.value

  // Wait for metadata to load before seeking — otherwise the browser may clamp to 0
  const doSeek = () => {
    if (!audioEl.value) {
      suppressProgressSave = false
      return
    }
    audioEl.value.currentTime = currentPos
    console.log(`[Progress] transitionToFullAudio: seeked to ${currentPos.toFixed(1)}s`)
    suppressProgressSave = false  // re-enable saves after seek
    if (playing.value) {
      audioEl.value.play()
    }
  }

  if (audioEl.value.readyState >= HTMLMediaElement.HAVE_METADATA) {
    doSeek()
  } else {
    audioEl.value.addEventListener('loadedmetadata', doSeek, { once: true })
  }

  streamState.value = 'done'
  rawPcmBuffers = []
  rawPcmTotalSamples = 0
  estimatedDuration = 0
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
  if (streamState.value === 'streaming' || (streamDonePending.value && !fullAudioReady)) {
    if (playing.value) {
      // Pause <audio> element
      if (audioEl.value) {
        audioEl.value.pause()
        playing.value = false
      }
    } else {
      // Play: convert accumulated PCM to WAV Blob and play via <audio> element.
      // This works on iOS because <audio> uses the native audio pipeline,
      // not Web Audio API (which has strict user-gesture restrictions on iOS).
      playAccumulatedAudio()
    }
    return
  }

  // Standard <audio> element playback (full saved file)
  if (!audioEl.value) return
  if (playing.value) {
    audioEl.value.pause()
  } else {
    audioEl.value.play()
  }
  playing.value = !playing.value
}

function onEnded() {
  playing.value = false
  currentTime.value = 0
  progress.value = 0
  clearProgress()
  // If we were playing from a partial blob and full audio is ready, switch
  if (fullAudioReady && audioUrl.value) {
    transitionToFullAudio()
  }
}

async function regenerateAudio() {
  if (!confirm('确定要重新生成音频吗？现有音频将被删除。')) return
  stopStreaming()
  try {
    await fetch(`/api/daily-briefings/${briefing.value.id}/regenerate-audio`, { method: 'POST' })
    briefing.value.audio_path = null
    briefing.value.status = 'completed'
    audioUrl.value = ''
    fullAudioReady = false
    showToast('音频已重置，开始重新生成...', 'success')
    // Start streaming
    startStreaming(briefing.value.id)
  } catch (e) {
    showToast('重置失败', 'error')
  }
}

function onTimeUpdate() {
  if (!audioEl.value) return
  const prevTime = currentTime.value
  currentTime.value = audioEl.value.currentTime
  duration.value = audioEl.value.duration || 0
  progress.value = duration.value ? (currentTime.value / duration.value) * 100 : 0
  if (Math.abs(currentTime.value - prevTime) > 2) {
    console.log(`[Progress] onTimeUpdate JUMP: ${prevTime?.toFixed(1)}s → ${currentTime.value?.toFixed(1)}s`)
  }
}

function onLoaded() {
  duration.value = audioEl.value?.duration || 0
}

function seek(e) {
  if (!audioEl.value || !duration.value) return
  const rect = e.currentTarget.getBoundingClientRect()
  const pos = (e.clientX - rect.left) / rect.width
  audioEl.value.currentTime = pos * duration.value
  // Clear saved progress if seeking near the start
  if (pos * duration.value < 1) {
    clearProgress()
  }
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
