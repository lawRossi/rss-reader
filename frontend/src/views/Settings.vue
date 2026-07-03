<template>
  <div class="space-y-6">
    <h2 class="text-xl font-bold text-[var(--color-text)]">⚙️ 系统设置</h2>

    <!-- LLM Configuration -->
    <div class="bg-[var(--color-surface)] rounded-2xl p-6 border border-[var(--color-border)] space-y-6">
      <h3 class="font-semibold text-[var(--color-text)] border-b border-[var(--color-border)] pb-3">🤖 LLM API 配置</h3>

      <div v-if="loading" class="space-y-4">
        <div v-for="i in 4" :key="i" class="animate-pulse h-10 bg-gray-200 dark:bg-gray-700 rounded"></div>
      </div>

      <div v-else class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-[var(--color-text)] mb-1">API Endpoint</label>
          <input v-model="form.api_endpoint" type="url" placeholder="https://api.openai.com/v1"
            class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
        </div>
        <div>
          <label class="block text-sm font-medium text-[var(--color-text)] mb-1">API Key</label>
          <div class="relative">
            <input v-model="form.api_key" :type="showKey ? 'text' : 'password'" placeholder="sk-..."
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] pr-10" />
            <button @click="showKey = !showKey" class="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-[var(--color-text-secondary)]">
              {{ showKey ? '🙈' : '👁️' }}
            </button>
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium text-[var(--color-text)] mb-1">模型名称</label>
          <input v-model="form.model_name" placeholder="gpt-3.5-turbo"
            class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
        </div>
        <div>
          <label class="block text-sm font-medium text-[var(--color-text)] mb-1">
            Max Tokens: {{ form.max_tokens }}
          </label>
          <input v-model.number="form.max_tokens" type="range" min="256" max="8192" step="128"
            class="w-full accent-[var(--color-primary)]" />
        </div>
        <div>
          <label class="block text-sm font-medium text-[var(--color-text)] mb-1">
            Temperature: {{ form.temperature }}
          </label>
          <input v-model.number="form.temperature" type="range" min="0" max="2" step="0.1"
            class="w-full accent-[var(--color-primary)]" />
        </div>

        <div class="flex gap-3 pt-3">
          <button @click="testConnection" :disabled="testing"
            class="px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)] text-sm disabled:opacity-50">
            {{ testing ? '测试中...' : '🔗 测试连接' }}
          </button>
          <button @click="saveSettings"
            class="px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm hover:bg-[var(--color-primary-dark)]">
            💾 保存设置
          </button>
        </div>

        <div v-if="testResult" class="p-3 rounded-lg text-sm" :class="testResult.success ? 'bg-green-50 dark:bg-green-900/20 text-green-600' : 'bg-red-50 dark:bg-red-900/20 text-red-600'">
          {{ testResult.message }}
        </div>

        <!-- Expandable: Summary-specific LLM config -->
        <div class="border-t border-[var(--color-border)] pt-4">
          <button @click="showSummaryLlm = !showSummaryLlm"
            class="flex items-center justify-between w-full text-sm font-medium text-[var(--color-text)] hover:text-[var(--color-primary)]">
            <span>📝 摘要 LLM 配置（可选）</span>
            <span class="text-xs text-[var(--color-text-secondary)]">{{ showSummaryLlm ? '收起 ▲' : '展开 ▼' }}</span>
          </button>
          <p class="text-xs text-[var(--color-text-secondary)] mt-1">独立配置文章摘要的 LLM，不填则默认使用上方全局配置</p>
          <div v-if="showSummaryLlm" class="mt-4 space-y-4 p-4 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)]">
            <div>
              <label class="block text-sm font-medium text-[var(--color-text)] mb-1">API Endpoint</label>
              <input v-model="form.summary_api_endpoint" type="url" placeholder="默认使用上方配置"
                class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
            </div>
            <div>
              <label class="block text-sm font-medium text-[var(--color-text)] mb-1">API Key</label>
              <div class="relative">
                <input v-model="form.summary_api_key" :type="showSummaryKey ? 'text' : 'password'" placeholder="默认使用上方配置"
                  class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] pr-10" />
                <button @click="showSummaryKey = !showSummaryKey" class="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-[var(--color-text-secondary)]">
                  {{ showSummaryKey ? '🙈' : '👁️' }}
                </button>
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-[var(--color-text)] mb-1">模型名称</label>
              <input v-model="form.summary_model_name" placeholder="默认使用上方配置"
                class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
            </div>
            <div>
              <label class="block text-sm font-medium text-[var(--color-text)] mb-1">
                Max Tokens: {{ form.summary_max_tokens }}
              </label>
              <input v-model.number="form.summary_max_tokens" type="range" min="256" max="8192" step="128"
                class="w-full accent-[var(--color-primary)]" />
            </div>
            <div>
              <label class="block text-sm font-medium text-[var(--color-text)] mb-1">
                Temperature: {{ form.summary_temperature }}
              </label>
              <input v-model.number="form.summary_temperature" type="range" min="0" max="2" step="0.1"
                class="w-full accent-[var(--color-primary)]" />
            </div>
          </div>
        </div>

        <!-- Expandable: Briefing-specific LLM config -->
        <div class="border-t border-[var(--color-border)] pt-4">
          <button @click="showBriefingLlm = !showBriefingLlm"
            class="flex items-center justify-between w-full text-sm font-medium text-[var(--color-text)] hover:text-[var(--color-primary)]">
            <span>📰 日报 LLM 配置（可选）</span>
            <span class="text-xs text-[var(--color-text-secondary)]">{{ showBriefingLlm ? '收起 ▲' : '展开 ▼' }}</span>
          </button>
          <p class="text-xs text-[var(--color-text-secondary)] mt-1">独立配置日报生成的 LLM，不填则默认使用上方全局配置</p>
          <div v-if="showBriefingLlm" class="mt-4 space-y-4 p-4 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)]">
            <div>
              <label class="block text-sm font-medium text-[var(--color-text)] mb-1">API Endpoint</label>
              <input v-model="form.briefing_api_endpoint" type="url" placeholder="默认使用上方配置"
                class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
            </div>
            <div>
              <label class="block text-sm font-medium text-[var(--color-text)] mb-1">API Key</label>
              <div class="relative">
                <input v-model="form.briefing_api_key" :type="showBriefingKey ? 'text' : 'password'" placeholder="默认使用上方配置"
                  class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] pr-10" />
                <button @click="showBriefingKey = !showBriefingKey" class="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-[var(--color-text-secondary)]">
                  {{ showBriefingKey ? '🙈' : '👁️' }}
                </button>
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-[var(--color-text)] mb-1">模型名称</label>
              <input v-model="form.briefing_model_name" placeholder="默认使用上方配置"
                class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
            </div>
            <div>
              <label class="block text-sm font-medium text-[var(--color-text)] mb-1">
                Max Tokens: {{ form.briefing_max_tokens }}
              </label>
              <input v-model.number="form.briefing_max_tokens" type="range" min="256" max="16384" step="128"
                class="w-full accent-[var(--color-primary)]" />
            </div>
            <div>
              <label class="block text-sm font-medium text-[var(--color-text)] mb-1">
                Temperature: {{ form.briefing_temperature }}
              </label>
              <input v-model.number="form.briefing_temperature" type="range" min="0" max="2" step="0.1"
                class="w-full accent-[var(--color-primary)]" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TTS Engine Configuration -->
    <div class="bg-[var(--color-surface)] rounded-2xl p-6 border border-[var(--color-border)] space-y-6">
      <h3 class="font-semibold text-[var(--color-text)] border-b border-[var(--color-border)] pb-3">🔊 语音引擎配置</h3>

      <div v-if="loading" class="space-y-4">
        <div v-for="i in 3" :key="i" class="animate-pulse h-10 bg-gray-200 dark:bg-gray-700 rounded"></div>
      </div>

      <div v-else class="space-y-5">
        <!-- Engine Selector -->
        <div>
          <label class="block text-sm font-medium text-[var(--color-text)] mb-2">语音引擎</label>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div
              v-for="(info, key) in ttsEngines"
              :key="key"
              @click="form.tts_engine = key"
              class="relative p-4 rounded-xl border-2 cursor-pointer transition-all"
              :class="form.tts_engine === key
                ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5'
                : 'border-[var(--color-border)] hover:border-gray-400'"
            >
              <div class="flex items-start justify-between">
                <div>
                  <div class="font-medium text-[var(--color-text)]">{{ info.label }}</div>
                  <div class="text-xs text-[var(--color-text-secondary)] mt-1">{{ info.description }}</div>
                </div>
                <div v-if="form.tts_engine === key"
                  class="w-5 h-5 rounded-full bg-[var(--color-primary)] flex items-center justify-center text-white text-xs">
                  ✓
                </div>
              </div>
              <div v-if="ttsStatus[key] !== undefined" class="mt-2 text-xs" :class="ttsStatus[key] ? 'text-green-500' : 'text-yellow-500'">
                {{ ttsStatus[key] ? '● 可用' : '○ 模型未加载（首次使用会自动下载）' }}
              </div>
            </div>
          </div>
        </div>

        <!-- Nano-specific Settings -->
        <div v-if="form.tts_engine === 'moss-tts-nano'" class="space-y-4 p-4 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)]">
          <h4 class="text-sm font-medium text-[var(--color-text)]">🎤 音色克隆设置</h4>

          <!-- Reference Audio List -->
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <label class="text-sm text-[var(--color-text-secondary)]">参考音频列表</label>
              <button @click="showAddAudio = true"
                class="text-xs px-3 py-1.5 rounded-lg bg-[var(--color-primary)] text-white">
                + 添加音频
              </button>
            </div>

            <!-- Empty state -->
            <div v-if="refAudios.length === 0" class="text-center py-6 text-sm text-[var(--color-text-secondary)]">
              暂无参考音频。添加一段 3-10 秒的人声录音来克隆音色。
            </div>

            <!-- Audio list -->
            <div v-for="audio in refAudios" :key="audio.id"
              class="p-3 rounded-lg border"
              :class="audio.active ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5' : 'border-[var(--color-border)]'">

              <div class="flex items-start justify-between gap-2">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium text-[var(--color-text)] truncate">{{ audio.name }}</span>
                    <span v-if="audio.active"
                      class="px-1.5 py-0.5 rounded text-xs bg-[var(--color-primary)] text-white">使用中</span>
                  </div>
                  <div class="text-xs text-[var(--color-text-secondary)] mt-1 truncate">{{ audio.filename }}</div>
                  <div v-if="audio.text" class="text-xs text-[var(--color-text-secondary)] mt-1 truncate">
                    📝 {{ audio.text }}
                  </div>
                </div>
                <div class="flex items-center gap-1 shrink-0">
                  <button @click="playRefAudioById(audio)"
                    class="p-1.5 rounded-lg text-sm hover:bg-gray-100 dark:hover:bg-gray-700"
                    title="试听">
                    ▶️
                  </button>
                  <button @click="activateAudio(audio.id)" v-if="!audio.active"
                    class="p-1.5 rounded-lg text-sm hover:bg-gray-100 dark:hover:bg-gray-700"
                    title="设为当前音色">
                    ✅
                  </button>
                  <button @click="deleteAudio(audio.id)"
                    class="p-1.5 rounded-lg text-sm hover:bg-red-50 dark:hover:bg-red-900/20"
                    title="删除">
                    🗑️
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Add Audio Modal -->
          <div v-if="showAddAudio" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="showAddAudio = false">
            <div class="bg-[var(--color-surface)] rounded-2xl p-6 w-full max-w-md">
              <h3 class="text-lg font-bold text-[var(--color-text)] mb-4">添加参考音频</h3>

              <div class="space-y-4">
                <div>
                  <label class="block text-sm font-medium text-[var(--color-text)] mb-1">名称</label>
                  <input v-model="newAudioName" type="text" placeholder="例如：女声、男声、主播音色"
                    class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
                </div>

                <div>
                  <label class="block text-sm font-medium text-[var(--color-text)] mb-1">音频文件（3-10 秒人声录音）</label>
                  <div class="flex gap-2">
                    <input ref="addFileInput" type="file" accept=".wav,.mp3,.m4a,.ogg" @change="handleAddFileSelect"
                      class="hidden" />
                    <button @click="$refs.addFileInput.click()"
                      class="flex-1 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm text-[var(--color-text)] text-left">
                      {{ addFileName || '点击选择文件...' }}
                    </button>
                  </div>
                </div>

                <div>
                  <label class="block text-sm font-medium text-[var(--color-text)] mb-1">
                    音频文字内容
                    <span class="text-xs text-[var(--color-text-secondary)]">（必填，极大提升克隆质量）</span>
                  </label>
                  <input v-model="newAudioText" type="text"
                    placeholder="请准确填写参考音频中说出的文字"
                    class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
                </div>
              </div>

              <div class="flex gap-2 mt-6">
                <button @click="showAddAudio = false"
                  class="flex-1 px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)]">取消</button>
                <button @click="addAudio" :disabled="addingAudio"
                  class="flex-1 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg disabled:opacity-50">
                  {{ addingAudio ? '添加中...' : '添加' }}
                </button>
              </div>
            </div>
          </div>

          <!-- Temperature -->
          <div>
            <label class="block text-sm text-[var(--color-text-secondary)] mb-1">
              生成温度: {{ form.tts_nano_temperature }}
            </label>
            <input v-model.number="form.tts_nano_temperature" type="range" min="0.1" max="1.5" step="0.1"
              class="w-full accent-[var(--color-primary)]" />
            <div class="flex justify-between text-xs text-[var(--color-text-secondary)] mt-1">
              <span>稳定 (0.1)</span>
              <span>推荐 (0.5)</span>
              <span>多样 (1.5)</span>
            </div>
          </div>

          <div class="text-xs text-[var(--color-text-secondary)] space-y-1">
            <p>💡 提示：首次使用时会自动下载模型（约 100MB），之后可离线使用</p>
          </div>
        </div>

        <div v-if="form.tts_engine === 'moss-ttsd'" class="p-4 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)]">
          <p class="text-sm text-[var(--color-text-secondary)]">
            🎙️ MOSS-TTSD 使用 [S1]/[S2] 标记生成双人对播对话，无需配置参考音频。
            生成日报时会自动将脚本转换为双人播报音频。
          </p>
        </div>

        <div class="flex gap-3 pt-3">
          <button @click="refreshTtsStatus" :disabled="checkingTts"
            class="px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)] text-sm disabled:opacity-50">
            {{ checkingTts ? '检查中...' : '🔄 刷新状态' }}
          </button>
          <button @click="saveSettings"
            class="px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm hover:bg-[var(--color-primary-dark)]">
            💾 保存设置
          </button>
        </div>
      </div>
    </div>

    <!-- Feed Fetch Configuration -->
    <div class="bg-[var(--color-surface)] rounded-2xl p-6 border border-[var(--color-border)] space-y-6">
      <h3 class="font-semibold text-[var(--color-text)] border-b border-[var(--color-border)] pb-3">📡 定期抓取</h3>

      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-[var(--color-text)] mb-1">抓取间隔（分钟）</label>
          <div class="flex gap-2">
            <input v-model.number="fetchIntervalInput" type="number" min="1" max="1440"
              class="w-32 px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]" />
            <span class="text-sm text-[var(--color-text-secondary)] self-center">分钟（最小 1 分钟）</span>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4 text-sm">
          <div class="p-3 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)]">
            <div class="text-[var(--color-text-secondary)]">上次抓取</div>
            <div class="font-medium text-[var(--color-text)] mt-1">{{ fetchStatus.last_run ? formatTime(fetchStatus.last_run) : '暂无记录' }}</div>
          </div>
          <div class="p-3 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)]">
            <div class="text-[var(--color-text-secondary)]">下次抓取</div>
            <div class="font-medium text-[var(--color-text)] mt-1">{{ fetchStatus.next_run ? formatTime(fetchStatus.next_run) : '未调度' }}</div>
          </div>
        </div>

        <div class="flex gap-3 pt-2">
          <button @click="saveFetchInterval" :disabled="savingFetchInterval"
            class="px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm disabled:opacity-50">
            {{ savingFetchInterval ? '保存中...' : '💾 保存间隔' }}
          </button>
          <button @click="triggerFetch" :disabled="fetchingNow"
            class="px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)] text-sm disabled:opacity-50">
            {{ fetchingNow ? '抓取中...' : '🚀 立即抓取' }}
          </button>
          <button @click="loadFetchStatus" class="px-4 py-2 rounded-lg border border-[var(--color-border)] text-[var(--color-text)] text-sm">
            🔄 刷新状态
          </button>
        </div>

        <div v-if="fetchMessage" class="p-3 rounded-lg text-sm" :class="fetchMessage.success ? 'bg-green-50 dark:bg-green-900/20 text-green-600' : 'bg-red-50 dark:bg-red-900/20 text-red-600'">
          {{ fetchMessage.text }}
        </div>
      </div>
    </div>

    <!-- About -->
    <div class="bg-[var(--color-surface)] rounded-2xl p-6 border border-[var(--color-border)] space-y-4">
      <h3 class="font-semibold text-[var(--color-text)] border-b border-[var(--color-border)] pb-3">📋 关于</h3>
      <div class="text-sm text-[var(--color-text-secondary)] space-y-2">
        <p>RSS Reader v0.1.0</p>
        <p>技术栈：FastAPI + Vue 3 + Tailwind CSS + SQLite</p>
        <p v-if="form.tts_engine === 'moss-ttsd'">语音引擎：MOSS-TTSD (多主播对话)</p>
        <p v-else>语音引擎：MOSS-TTS-Nano (音色克隆)</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, inject } from 'vue'
import { useSettingsStore } from '../stores/settingsStore'
import api, { settingsApi, briefingsApi, feedsApi } from '../api'

const settingsStore = useSettingsStore()
const showToast = inject('showToast')

const loading = ref(true)
const testing = ref(false)
const testResult = ref(null)
const showKey = ref(false)
const showSummaryKey = ref(false)
const showBriefingKey = ref(false)
const showSummaryLlm = ref(false)
const showBriefingLlm = ref(false)

const ttsEngines = ref({})
const ttsStatus = ref({})
const checkingTts = ref(false)

// Feed fetch status
const fetchStatus = ref({ interval_minutes: null, next_run: null, last_run: null })
const fetchIntervalInput = ref(30)
const savingFetchInterval = ref(false)
const fetchingNow = ref(false)
const fetchMessage = ref(null)

const selectedFile = ref(null)
const refAudioName = ref('')
const refAudioPath = ref('')
const uploading = ref(false)
const fileInput = ref(null)

// Multiple reference audios
const refAudios = ref([])
const showAddAudio = ref(false)
const newAudioName = ref('')
const newAudioText = ref('')
const addFileName = ref('')
const addFileInput = ref(null)
const addSelectedFile = ref(null)
const addingAudio = ref(false)

// Show user-friendly label for the current reference audio
const refAudioLabel = computed(() => {
  const active = refAudios.value.find(a => a.active)
  if (active) return active.name
  if (refAudioPath.value) {
    const name = refAudioPath.value.split('/').pop()
    return name === 'default_ref_voice.wav' ? '默认音色' : name
  }
  return '未设置（将使用默认音色）'
})

const form = reactive({
  api_endpoint: 'https://api.openai.com/v1',
  api_key: '',
  model_name: 'gpt-3.5-turbo',
  max_tokens: 1024,
  temperature: 0.7,
  // Summary-specific LLM config
  summary_api_endpoint: '',
  summary_api_key: '',
  summary_model_name: '',
  summary_max_tokens: 1024,
  summary_temperature: 0.7,
  // Briefing-specific LLM config
  briefing_api_endpoint: '',
  briefing_api_key: '',
  briefing_model_name: '',
  briefing_max_tokens: 2048,
  briefing_temperature: 0.7,
  tts_engine: 'moss-ttsd',
  tts_nano_ref_text: '',
  tts_nano_temperature: 0.5,
})

onMounted(async () => {
  // Settings and TTS engines are fast — block on them
  await Promise.all([
    loadSettings(),
    loadTtsEngines(),
    loadRefAudios(),
    loadFetchStatus(),
  ])
  loading.value = false
  // Note: TTS backend status is NOT checked on mount — it requires downloading
  // the MLX model (~100MB) which can hang. Click "刷新状态" to check manually.
})

async function loadSettings() {
  await settingsStore.loadSettings()
  const s = settingsStore.settings
  if (s.llm_api_endpoint) form.api_endpoint = s.llm_api_endpoint
  if (s.llm_api_key) form.api_key = s.llm_api_key
  if (s.llm_model_name) form.model_name = s.llm_model_name
  if (s.llm_max_tokens) form.max_tokens = parseInt(s.llm_max_tokens)
  if (s.llm_temperature) form.temperature = parseFloat(s.llm_temperature)
  // Summary-specific
  if (s.summary_api_endpoint) form.summary_api_endpoint = s.summary_api_endpoint
  if (s.summary_api_key) form.summary_api_key = s.summary_api_key
  if (s.summary_model_name) form.summary_model_name = s.summary_model_name
  if (s.summary_max_tokens) form.summary_max_tokens = parseInt(s.summary_max_tokens)
  if (s.summary_temperature) form.summary_temperature = parseFloat(s.summary_temperature)
  // Briefing-specific
  if (s.briefing_api_endpoint) form.briefing_api_endpoint = s.briefing_api_endpoint
  if (s.briefing_api_key) form.briefing_api_key = s.briefing_api_key
  if (s.briefing_model_name) form.briefing_model_name = s.briefing_model_name
  if (s.briefing_max_tokens) form.briefing_max_tokens = parseInt(s.briefing_max_tokens)
  if (s.briefing_temperature) form.briefing_temperature = parseFloat(s.briefing_temperature)
  if (s.tts_engine) form.tts_engine = s.tts_engine
  if (s.tts_nano_temperature) form.tts_nano_temperature = parseFloat(s.tts_nano_temperature)
  if (s.tts_nano_ref_audio) refAudioPath.value = s.tts_nano_ref_audio
}

async function loadRefAudios() {
  try {
    const res = await api.get('/settings/tts-ref-audios')
    refAudios.value = res.data.audios || []
  } catch (e) {
    console.error('Failed to load reference audios:', e)
  }
}

async function activateAudio(id) {
  try {
    await api.post(`/settings/tts-ref-audios/${id}/activate`)
    await loadRefAudios()
    showToast('已切换音色', 'success')
  } catch (e) {
    showToast('切换失败', 'error')
  }
}

async function deleteAudio(id) {
  const audio = refAudios.value.find(a => a.id === id)
  if (!audio) return
  if (!confirm(`确定要删除「${audio.name}」吗？`)) return
  try {
    await api.delete(`/settings/tts-ref-audios/${id}`)
    await loadRefAudios()
    showToast('已删除', 'success')
  } catch (e) {
    showToast('删除失败', 'error')
  }
}

function handleAddFileSelect(e) {
  addSelectedFile.value = e.target.files[0]
  addFileName.value = addSelectedFile.value?.name || ''
}

async function addAudio() {
  if (!newAudioName.value.trim()) {
    showToast('请填写音频名称', 'error')
    return
  }
  if (!addSelectedFile.value) {
    showToast('请选择音频文件', 'error')
    return
  }
  addingAudio.value = true
  try {
    const formData = new FormData()
    formData.append('name', newAudioName.value.trim())
    formData.append('text', newAudioText.value.trim())
    formData.append('file', addSelectedFile.value)
    const res = await fetch('/api/settings/tts-ref-audios', {
      method: 'POST',
      body: formData,
    })
    if (res.ok) {
      showToast('参考音频已添加', 'success')
      showAddAudio.value = false
      newAudioName.value = ''
      newAudioText.value = ''
      addFileName.value = ''
      addSelectedFile.value = null
      await loadRefAudios()
    } else {
      const data = await res.json()
      showToast(data.detail || '添加失败', 'error')
    }
  } catch (e) {
    showToast('添加失败: ' + e.message, 'error')
  } finally {
    addingAudio.value = false
  }
}

// ── Feed Fetch ──

async function loadFetchStatus() {
  try {
    const res = await feedsApi.fetchStatus()
    fetchStatus.value = res.data
    if (res.data.interval_minutes) {
      fetchIntervalInput.value = res.data.interval_minutes
    }
  } catch (e) {
    console.error('Failed to load fetch status:', e)
  }
}

async function triggerFetch() {
  fetchingNow.value = true
  fetchMessage.value = null
  try {
    const res = await feedsApi.fetchNow()
    fetchMessage.value = { success: true, text: res.data.message || '抓取已触发' }
  } catch (e) {
    fetchMessage.value = { success: false, text: '抓取触发失败: ' + (e.response?.data?.detail || e.message) }
  } finally {
    fetchingNow.value = false
  }
}

async function saveFetchInterval() {
  savingFetchInterval.value = true
  fetchMessage.value = null
  try {
    await settingsStore.saveSettings({
      fetch_interval: String(fetchIntervalInput.value),
    })
    await loadFetchStatus()
    fetchMessage.value = { success: true, text: `抓取间隔已更新为 ${fetchIntervalInput.value} 分钟` }
  } catch (e) {
    fetchMessage.value = { success: false, text: '保存失败: ' + (e.response?.data?.detail || e.message) }
  } finally {
    savingFetchInterval.value = false
  }
}

function formatTime(isoString) {
  if (!isoString) return ''
  const d = new Date(isoString)
  const now = new Date()
  const diffMs = now - d
  const diffMin = Math.floor(diffMs / 60000)

  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`

  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')

  if (year === now.getFullYear() && month === String(now.getMonth() + 1).padStart(2, '0') && day === String(now.getDate()).padStart(2, '0')) {
    return `今天 ${hour}:${min}`
  }
  return `${month}-${day} ${hour}:${min}`
}

async function loadTtsEngines() {
  try {
    const res = await settingsApi.getTtsEngines()
    ttsEngines.value = res.data.engines
  } catch (e) {
    console.error('Failed to load TTS engines:', e)
  }
}

async function loadTtsStatus() {
  try {
    const res = await api.get('/daily-briefings/tts-backends', { timeout: 10000 })
    ttsStatus.value = Object.fromEntries(
      Object.entries(res.data.backends).map(([k, v]) => [k, v.available])
    )
  } catch (e) {
    console.error('Failed to check TTS backends:', e)
    // Mark as unknown on error so UI doesn't look broken
    for (const key of Object.keys(ttsEngines.value)) {
      ttsStatus.value[key] = undefined
    }
  }
}

async function refreshTtsStatus() {
  checkingTts.value = true
  await loadTtsStatus()
  checkingTts.value = false
}

function playRefAudioById(audio) {
  const audioUrl = `/api/settings/tts-ref-audios/${audio.id}/audio`
  const el = new Audio(audioUrl)
  el.play().catch(() => {
    showToast('试听失败', 'error')
  })
}

async function saveSettings() {
  try {
    await settingsStore.saveSettings({
      llm_api_endpoint: form.api_endpoint,
      llm_api_key: form.api_key,
      llm_model_name: form.model_name,
      llm_max_tokens: String(form.max_tokens),
      llm_temperature: String(form.temperature),
      // Summary-specific (always save — empty string means "use global")
      summary_api_endpoint: form.summary_api_endpoint,
      summary_api_key: form.summary_api_key,
      summary_model_name: form.summary_model_name,
      summary_max_tokens: String(form.summary_max_tokens),
      summary_temperature: String(form.summary_temperature),
      // Briefing-specific (always save — empty string means "use global")
      briefing_api_endpoint: form.briefing_api_endpoint,
      briefing_api_key: form.briefing_api_key,
      briefing_model_name: form.briefing_model_name,
      briefing_max_tokens: String(form.briefing_max_tokens),
      briefing_temperature: String(form.briefing_temperature),
      tts_engine: form.tts_engine,
      tts_nano_temperature: String(form.tts_nano_temperature),
    })
    showToast('设置已保存！', 'success')
  } catch (e) {
    showToast('保存失败', 'error')
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    const response = await fetch(`${form.api_endpoint}/models`, {
      headers: { Authorization: `Bearer ${form.api_key}` },
    })
    if (response.ok) {
      testResult.value = { success: true, message: '✅ 连接成功！API 可正常访问。' }
    } else {
      const data = await response.json()
      testResult.value = { success: false, message: `❌ 连接失败: ${data.error?.message || response.statusText}` }
    }
  } catch (e) {
    testResult.value = { success: false, message: `❌ 连接失败: ${e.message}` }
  } finally {
    testing.value = false
  }
}
</script>
