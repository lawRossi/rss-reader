# RSS Reader - 功能丰富的 RSS 阅读 Web 应用

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Python](https://img.shields.io/badge/Python-3.9+-green)
![Vue](https://img.shields.io/badge/Vue-3-brightgreen)

一个集成了 AI 能力的现代化 RSS 阅读器，不仅能阅读，还能**听**新闻。

## ✨ 功能特性

### 📡 RSS 源管理
- 添加/编辑/删除 RSS 订阅源
- RSS 源分组管理（创建/编辑分组）
- **OPML 批量导入** — 支持拖拽上传 OPML 文件
- 自动获取源元数据（标题、描述、图标）

### 📰 文章阅读
- 文章列表（支持无限滚动加载）
- 多种筛选（按源、分组、标签、收藏、关键词搜索）
- 已读/未读标记
- 文章收藏 ⭐
- 字号调节
- 响应式设计，移动端友好

### 🏷️ 标签系统
- 创建/编辑/删除标签（支持颜色选择）
- 为文章打标签/取消标签
- 按标签筛选文章

### 🤖 AI 摘要
- 一键生成文章摘要
- **流式输出** — 逐字显示生成过程
- 摘要自动缓存
- 支持自定义 LLM API（兼容 OpenAI 接口）

### 🎙️ 每日播报
- AI 自动生成播报式新闻日报
- 双人对话播报脚本（[S1]/[S2] 主播切换）
- **音频合成** — MOSS-TTSD 后台生成音频
- **音频播放器** — 播放/暂停/进度拖拽/倍速播放
- 播放时文本段落高亮同步

### 📤 内容导出
- Markdown 格式导出
- **PDF 格式导出**
- 支持单篇/批量导出

### 🎨 界面设计
- 扁平清新设计风格
- **暗色/亮色主题** 一键切换
- 移动端优先的响应式布局
- 平滑的页面过渡动画
- 骨架屏加载效果

## 🚀 快速开始

### 前置条件

- Python 3.9+
- Node.js 18+
- Poetry（Python 包管理）
- npm（Node 包管理）

### 1️⃣ 安装后端

```bash
# 进入后端目录
cd backend

# 安装依赖
poetry install

# 启动后端服务（开发模式，热重载）
poetry run python run.py
```

后端服务运行在 `http://localhost:8000`

### 2️⃣ 安装前端

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动前端开发服务器
npm run dev
```

前端开发服务器运行在 `http://localhost:5173`

### 3️⃣ 配置 LLM API

1. 打开前端页面 `http://localhost:5173`
2. 进入「设置」页面
3. 输入你的 LLM API Endpoint（如 `https://api.openai.com/v1`）
4. 输入 API Key
5. 选择模型（如 `gpt-3.5-turbo` 或 `gpt-4`）
6. 点击「测试连接」验证配置
7. 点击「保存设置」

> **支持的 LLM API**：任何兼容 OpenAI 接口的服务（OpenAI、DeepSeek、通义千问、Claude 等）

### 4️⃣ 添加 RSS 源

1. 进入「订阅源」页面
2. 点击「+ 添加源」
3. 输入 RSS 链接（如 `https://feeds.feedburner.com/ruanyifeng`）
4. 选择分组（可选）
5. 点击「添加」

或批量导入：点击「导入 OPML」上传 OPML 文件。

### 5️⃣ 使用功能

| 功能 | 位置 | 说明 |
|------|------|------|
| 阅读文章 | 首页 / 文章列表 | 点击文章卡片 |
| AI 摘要 | 文章详情页 | 点击「生成 AI 摘要」按钮 |
| 收藏 | 文章详情页 | 点击星标按钮 |
| 标签 | 文章详情页 | 点击标签按钮 |
| 每日播报 | 日报页面 | 点击「生成今日播报」 |
| 导出 | 文章列表 / 日报详情 | 点击导出按钮 |

## 🏗️ 技术栈

### 后端
- **框架**: FastAPI
- **ORM**: SQLAlchemy 2.0 (async)
- **数据库**: SQLite (aiosqlite)
- **RSS 解析**: feedparser
- **内容提取**: BeautifulSoup4 + lxml
- **LLM 调用**: httpx (OpenAI 兼容接口)
- **PDF 生成**: weasyprint
- **依赖管理**: Poetry

### 前端
- **框架**: Vue 3 (Composition API)
- **构建工具**: Vite
- **样式**: Tailwind CSS
- **状态管理**: Pinia
- **路由**: Vue Router 4
- **HTTP 客户端**: Axios

## 📁 项目结构

```
rss_reader/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置管理
│   │   ├── database.py          # 数据库配置
│   │   ├── models/              # 7个数据模型
│   │   │   ├── setting.py       # 系统设置
│   │   │   ├── group.py         # 分组
│   │   │   ├── feed.py          # RSS源
│   │   │   ├── article.py       # 文章
│   │   │   ├── tag.py           # 标签
│   │   │   ├── article_tag.py   # 文章-标签关联
│   │   │   └── daily_briefing.py # 日报
│   │   ├── routes/              # 8个API路由模块
│   │   ├── schemas/             # Pydantic验证模型
│   │   └── services/            # 业务逻辑
│   │       ├── feed_fetcher.py  # RSS抓取
│   │       ├── opml_importer.py # OPML导入
│   │       ├── llm_service.py   # LLM调用
│   │       ├── summarizer.py    # 摘要生成
│   │       ├── briefing_generator.py # 日报生成
│   │       ├── tts_service.py   # 语音合成
│   │       └── exporter.py      # 内容导出
│   ├── pyproject.toml
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── api/                 # API封装
│   │   ├── router/              # 路由配置
│   │   ├── stores/              # Pinia状态管理
│   │   ├── views/               # 11个页面
│   │   ├── components/          # 通用组件
│   │   └── App.vue              # 布局主组件
│   └── vite.config.js
├── audio/                       # 音频文件存储
└── plans/                       # 计划文档
```

## 🔌 API 概览

| 分组 | 端点 | 说明 |
|------|------|------|
| Settings | `GET/PUT /api/settings` | 系统设置 |
| Groups | `CRUD /api/groups` | 分组管理 |
| Feeds | `CRUD /api/feeds` + `POST /import-opml` + `POST /{id}/fetch` | 订阅源管理 |
| Articles | `GET /api/articles` + `GET/PATCH /{id}` + `POST /batch` | 文章管理 |
| Tags | `CRUD /api/tags` + `POST /articles/{id}/tags` | 标签管理 |
| Summary | `GET/POST /api/articles/{id}/summary` | AI摘要(SSE流式) |
| Briefings | `CRUD /api/daily-briefings` + `POST /generate` + `GET /{id}/audio` | 日报 |
| Export | `GET /articles/export` + `GET /daily-briefings/{id}/export` | 导出 |

## 🎵 MOSS-TTSD 配置（可选）

如需音频播报功能，需安装并启动 MOSS-TTSD：

```bash
# 安装 MOSS-TTSD
git clone --recursive https://github.com/open-moss/moss-ttsd.git
cd moss-ttsd
pip install -r requirements.txt

# 启动服务
python api.py --port 8765
```

TTS 服务运行后，生成日报时会自动检测并调用。

## 📝 License

MIT
