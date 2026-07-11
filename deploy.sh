#!/usr/bin/env bash
# ============================================================================
# RSS Reader - 一键部署脚本
# 适用系统: Linux (CentOS 7+ / Ubuntu 18.04+ / Debian 10+)
# 功能: 安装依赖、构建前端、配置 nginx(8888端口) + supervisord 进程管理
# ============================================================================

set -euo pipefail

# ─── 颜色输出 ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ─── 项目路径 ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
DIST_DIR="$FRONTEND_DIR/dist"
VENV_DIR="$BACKEND_DIR/.venv"
AUDIO_DIR="$PROJECT_DIR/audio"

# ─── 配置项（可按需修改） ──────────────────────────────────────────────────
APP_NAME="rss-reader"                 # supervisor 中 program 的名称
BACKEND_PORT=8000                     # 后端端口
NGINX_PORT=8888                       # nginx 监听端口（前端访问端口）
NGINX_CONF="/etc/nginx/conf.d/${APP_NAME}.conf"
SUPERVISOR_CONF="/etc/supervisord.d/${APP_NAME}.ini"

# ─── 内存优化（6GB 服务器推荐 1 worker；内存充足可改为 2） ────────────────
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
# Ubuntu/Debian 下 supervisor 使用 .conf 扩展名（include 模式为 conf.d/*.conf）
if [ -d "/etc/supervisor/conf.d" ]; then
    SUPERVISOR_CONF="/etc/supervisor/conf.d/${APP_NAME}.conf"
fi

# ============================================================================
#  检查系统与权限
# ============================================================================
check_prerequisites() {
    log_info "检查运行环境..."

    # 检查是否为 root
    if [ "$(id -u)" -ne 0 ]; then
        log_error "请使用 root 用户或通过 sudo 执行此脚本"
        exit 1
    fi

    # 检测系统发行版
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="${ID:-unknown}"
        OS_VERSION="${VERSION_ID:-unknown}"
    else
        OS_ID="unknown"
    fi
    log_info "系统: $OS_ID $OS_VERSION"

    # 检查关键命令
    for cmd in python3 nginx supervisorctl; do
        if command -v "$cmd" &>/dev/null; then
            log_ok "已安装: $cmd ($(command -v "$cmd"))"
        else
            log_warn "未找到: $cmd (后续会自动安装)"
        fi
    done

    echo ""
}

# ============================================================================
#  安装系统级依赖
# ============================================================================
install_system_deps() {
    log_info "安装系统依赖..."

    # 判断包管理器
    local pm=""
    if command -v apt-get &>/dev/null; then
        pm="apt-get"
    elif command -v yum &>/dev/null; then
        pm="yum"
    elif command -v dnf &>/dev/null; then
        pm="dnf"
    else
        log_error "无法识别的包管理器，请手动安装: nginx, supervisor, python3, nodejs, npm, poetry"
        exit 1
    fi

    log_info "使用包管理器: $pm"

    # 检查当前 node 版本是否满足 Vite 8.x 的要求（>=20.19 或 >=22.12）
    local node_major=0
    if command -v node &>/dev/null; then
        node_major=$(node --version | sed 's/v//' | cut -d. -f1)
        local node_minor
        node_minor=$(node --version | sed 's/v//' | cut -d. -f2)
        log_info "检测到 Node.js $(node --version)"
        # Vite 8.x 要求: >=20.19 或 >=22.12
        if [ "$node_major" -eq 20 ] && [ "$node_minor" -lt 19 ]; then
            log_warn "Node.js $(node --version) 版本过低，Vite 8.x 要求 >=20.19 或 >=22.12"
            node_major=0  # 标记为需要升级
        elif [ "$node_major" -eq 21 ]; then
            log_warn "Node.js 21 不被 Vite 8.x 支持"
            node_major=0  # 标记为需要升级
        elif [ "$node_major" -eq 22 ] && [ "$node_minor" -lt 12 ]; then
            log_warn "Node.js $(node --version) 版本过低，Vite 8.x 要求 >=22.12"
            node_major=0  # 标记为需要升级
        elif [ "$node_major" -lt 20 ]; then
            log_warn "Node.js $(node --version) 版本过低，Vite 8.x 要求 >=20.19 或 >=22.12"
            node_major=0  # 标记为需要升级
        fi
    fi

    local base_pkgs=()
    if [ "$pm" = "apt-get" ]; then
        base_pkgs=(
            nginx
            supervisor
            python3
            python3-pip
            python3-venv
            curl
            git
        )

        # 只在 node 未安装时才从系统包管理器安装
        if ! command -v node &>/dev/null; then
            base_pkgs+=(nodejs npm)
        fi

        $pm update -y
        $pm install -y "${base_pkgs[@]}"

        # 如需升级，通过 NodeSource 安装 Node.js 20.x（已捆绑 npm，不与系统 npm 冲突）
        if [ "$node_major" -lt 20 ]; then
            log_info "通过 NodeSource 安装 Node.js 20.x..."
            $pm install -y ca-certificates gnupg
            curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
            $pm install -y nodejs
        fi
    else
        # centos / rhel / fedora
        base_pkgs=(
            nginx
            supervisor
            python3
            python3-pip
            python3-devel
            curl
            git
        )
        # 只在 node 未安装时才从系统包管理器安装（NodeSource 的 nodejs 已捆绑 npm）
        if ! command -v node &>/dev/null; then
            base_pkgs+=(nodejs npm)
        fi
        # 尝试启用 EPEL
        if command -v yum &>/dev/null || command -v dnf &>/dev/null; then
            local pm_cmd="${pm}"
            if [ "$pm" = "yum" ]; then
                $pm_cmd install -y epel-release || true
            fi
            $pm_cmd install -y "${base_pkgs[@]}" || {
                log_warn "部分依赖安装失败，尝试单独安装..."
                for pkg in "${base_pkgs[@]}"; do
                    $pm_cmd install -y "$pkg" || log_warn "安装 $pkg 失败"
                done
            }
        fi

        # 通过 NodeSource 安装 Node.js 20.x（满足 Vite 8.x 要求）
        if [ "$node_major" -lt 20 ]; then
            log_info "通过 NodeSource 安装 Node.js 20.x..."
            if command -v dnf &>/dev/null; then
                curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
                dnf install -y nodejs
            else
                curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
                yum install -y nodejs
            fi
        fi
    fi

    log_ok "系统依赖安装完成"
    echo ""
}

# ============================================================================
#  安装 / 配置 Python Poetry
# ============================================================================
setup_poetry() {
    log_info "配置 Python Poetry..."

    if command -v poetry &>/dev/null; then
        log_ok "Poetry 已安装 ($(poetry --version))"
    else
        log_info "正在安装 Poetry..."
        curl -sSL https://install.python-poetry.org | python3 - || {
            log_error "Poetry 安装失败"
            exit 1
        }
        export PATH="$HOME/.local/bin:$PATH"
        log_ok "Poetry 安装完成"
    fi

    # 确保 poetry 在 PATH 中
    export PATH="$HOME/.local/bin:$PATH"

    # 配置 poetry 在项目内创建虚拟环境
    poetry config virtualenvs.in-project true --local --directory "$BACKEND_DIR" 2>/dev/null || true
    log_ok "Poetry 配置完成"
    echo ""
}

# ============================================================================
#  安装后端依赖
# ============================================================================
install_backend() {
    log_info "安装后端依赖..."

    cd "$BACKEND_DIR"

    # 使用 poetry 安装依赖
    poetry install --no-root

    log_ok "后端依赖安装完成"
    echo ""
}

# ============================================================================
#  下载 TTS 模型（ONNX 语音克隆模型）
# ============================================================================
download_tts_models() {
    log_info "检查 TTS ONNX 模型..."

    local model_dir="$BACKEND_DIR/app/onnx_tts/models"
    local manifest_file="$model_dir/browser_poc_manifest.json"

    if [ -f "$manifest_file" ]; then
        log_ok "TTS 模型已存在: $model_dir"
    else
        log_info "TTS 模型未找到，正在从 Hugging Face 下载（约 1-2GB）..."
        log_info "可通过设置 SKIP_TTS_MODELS=1 跳过此步骤"
        cd "$BACKEND_DIR"
        poetry run python -m app.onnx_tts.download_models || {
            log_warn "TTS 模型下载失败（可能是网络问题），可稍后手动执行："
            log_warn "  cd $BACKEND_DIR && poetry run python -m app.onnx_tts.download_models"
        }
        if [ -f "$manifest_file" ]; then
            log_ok "TTS 模型下载完成"
        else
            log_warn "TTS 模型尚未就绪，语音克隆功能将不可用"
        fi
    fi
    echo ""
}

# ============================================================================
#  构建前端
# ============================================================================
build_frontend() {
    log_info "构建前端静态文件..."

    cd "$FRONTEND_DIR"

    # 安装 npm 依赖
    if [ -d "node_modules" ]; then
        log_info "node_modules 已存在，执行 npm ci 确保一致性..."
        npm ci || npm install
    else
        npm install
    fi

    # 构建
    npm run build

    if [ ! -d "$DIST_DIR" ]; then
        log_error "前端构建失败，未生成 dist 目录"
        exit 1
    fi

    log_ok "前端构建完成: $DIST_DIR"
    echo ""

    iptables -I INPUT -p tcp --dport 8888 -j ACCEPT
}

# ============================================================================
#  修复文件权限（nginx 以非 root 用户运行，需能读取前端文件）
# ============================================================================
fix_permissions() {
    log_info "修复文件权限..."

    # 1. 确保从根目录到项目目录的整条路径对 nginx 用户可访问
    #    nginx 通常以 www-data (Ubuntu) 或 nginx (CentOS) 运行，
    #    而 /home/ubuntu/ 等父目录可能没有 o+x 权限，导致 Permission denied
    local path="$PROJECT_DIR"
    while [ "$path" != "/" ]; do
        chmod o+x "$path" 2>/dev/null || true
        path="$(dirname "$path")"
    done

    # 2. 前端 dist 目录 - 确保 nginx 可读
    if [ -d "$DIST_DIR" ]; then
        chmod -R o+rX "$DIST_DIR"
        log_ok "前端文件权限已设置: $DIST_DIR"
    fi

    # 3. 音频输出目录（supervisor 写音频时使用）
    if [ -d "$AUDIO_DIR" ]; then
        chmod -R o+rwX "$AUDIO_DIR" 2>/dev/null || true
    fi

    # 4. backend 目录可读（uvicorn 需要访问）
    chmod -R o+rX "$BACKEND_DIR/app" 2>/dev/null || true

    log_ok "权限修复完成"
    echo ""
}

# ============================================================================
#  配置 Nginx（监听 8888 端口）
# ============================================================================
configure_nginx() {
    log_info "配置 Nginx (端口: $NGINX_PORT)..."

    # 确保 nginx 配置目录存在
    local nginx_conf_dir
    nginx_conf_dir="$(dirname "$NGINX_CONF")"
    mkdir -p "$nginx_conf_dir"

    # 写入 nginx 配置
    # 注意：使用 <<EOF（加引号）但 nginx $变量用反斜杠转义
    cat > "$NGINX_CONF" <<EOF
# RSS Reader - Nginx Configuration
# 前端端口: ${NGINX_PORT} | 后端代理: http://127.0.0.1:${BACKEND_PORT}

# ── 上游 keepalive 连接池 ──
# 减少 TCP 握手开销，提高密集请求下的性能
upstream rss_backend {
    server 127.0.0.1:${BACKEND_PORT};
    keepalive 32;
}

server {
    listen ${NGINX_PORT};
    server_name _;

    # ── 字符编码 ──
    charset utf-8;

    # ── 静态文件（前端构建产物） ──
    root ${DIST_DIR};
    index index.html;

    # ── Gzip 压缩 ──
    gzip on;
    gzip_min_length 1k;
    gzip_types text/plain text/css text/javascript application/javascript application/json image/svg+xml;
    gzip_vary on;

    # ── 前端静态资源 ──
    location / {
        try_files \$uri \$uri/ /index.html;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # ── SSE 端点 1：AI 摘要流式输出 ──
    # 必须关缓冲（proxy_buffering off），让 SSE 逐字推送
    location ~ ^/api/articles/\\d+/summary {
        proxy_pass http://rss_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;

        # SSE 长连接：LLM 生成慢时可等待更久
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
    }

    # ── SSE 端点 2：每日播报音频流 ──
    # 关缓冲，允许超长等待（TTS 生成可能持续数分钟）
    location ~ ^/api/daily-briefings/\\d+/stream-audio {
        proxy_pass http://rss_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;

        proxy_read_timeout 600s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
    }

    # ── 普通 API（带缓冲，利用 keepalive） ──
    # 启用 proxy_buffering，Nginx 先收完后端响应再发给客户端。
    # 即使客户端中途断开（SPA 切页面），后端连接也能快速释放，
    # 不会产生 499。
    location /api {
        proxy_pass http://rss_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # 启用缓冲（默认即 on），快速释放后端连接
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
        proxy_busy_buffers_size 8k;

        proxy_read_timeout 60s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;

        # 请求体大小（音频上传等）
        client_max_body_size 50m;
    }

    # ── Docs / OpenAPI（直接透传） ──
    location /docs {
        proxy_pass http://rss_backend/docs;
        proxy_set_header Host \$host;
    }
    location /openapi.json {
        proxy_pass http://rss_backend/openapi.json;
        proxy_set_header Host \$host;
    }
}
EOF

    # 备份默认 nginx 配置（避免端口冲突）
    local default_conf="/etc/nginx/conf.d/default.conf"
    if [ -f "$default_conf" ]; then
        mv "$default_conf" "${default_conf}.bak" 2>/dev/null || true
        log_info "已备份默认配置: ${default_conf}.bak"
    fi

    # 测试 nginx 配置
    nginx -t || {
        log_error "Nginx 配置测试失败，请检查: ${NGINX_CONF}"
        exit 1
    }

    log_ok "Nginx 配置完成: ${NGINX_CONF}"
    echo ""
}

# ============================================================================
#  配置 Supervisor（管理后端服务）
# ============================================================================
configure_supervisor() {
    log_info "配置 Supervisor..."

    # 确保 supervisor 配置目录存在
    local sup_conf_dir
    sup_conf_dir="$(dirname "$SUPERVISOR_CONF")"
    mkdir -p "$sup_conf_dir"

    # 获取 python 和 uvicorn 路径
    local python_path
    if [ -f "$VENV_DIR/bin/python" ]; then
        python_path="$VENV_DIR/bin/python"
    else
        python_path="$(command -v python3)"
    fi

    # 获取项目目录中的 run.py 使用 uvicorn，而非 poetry run
    local backend_run="$BACKEND_DIR/run.py"
    local backend_app_dir="$BACKEND_DIR"

    # 写入 supervisor 配置
    cat > "$SUPERVISOR_CONF" <<EOF
; RSS Reader - Supervisor Configuration
; 管理后端 FastAPI (uvicorn) 服务
; 管理命令:
;   supervisorctl status ${APP_NAME}
;   supervisorctl start ${APP_NAME}
;   supervisorctl stop ${APP_NAME}
;   supervisorctl restart ${APP_NAME}

[program:${APP_NAME}]
command=${python_path} -m uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT} --workers ${UVICORN_WORKERS} --log-level info
directory=${BACKEND_DIR}
user=root
autostart=true
autorestart=true
startsecs=5
startretries=3
stopwaitsecs=10
stopasgroup=true
killasgroup=true

; 环境变量
environment=
    HOST="0.0.0.0",
    PORT="${BACKEND_PORT}",
    PYTHONPATH="${BACKEND_DIR}"

; 日志
stdout_logfile=/var/log/${APP_NAME}.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5
stderr_logfile=/var/log/${APP_NAME}_error.log
stderr_logfile_maxbytes=50MB
stderr_logfile_backups=5

; 重定向
redirect_stderr=true
EOF

    log_ok "Supervisor 配置完成: ${SUPERVISOR_CONF}"
    echo ""
}

# ============================================================================
#  启动服务
# ============================================================================
start_services() {
    log_info "启动服务..."

    # ── 启动 / 重载 Nginx ──
    # 先 kill 所有残留的 nginx 进程，确保端口释放
    nginx -s quit 2>/dev/null || true
    sleep 1
    # 如果还有残留进程，强制终止
    if pgrep nginx &>/dev/null; then
        pkill -9 nginx 2>/dev/null || true
        sleep 1
    fi

    # 测试配置
    nginx -t || {
        log_error "Nginx 配置测试失败，请检查: nginx -t"
        exit 1
    }

    if systemctl list-units --type=service 2>/dev/null | grep -q nginx; then
        # 清除 systemd 可能残留的 pid 记录
        rm -f /run/nginx.pid /var/run/nginx.pid 2>/dev/null || true
        systemctl enable nginx
        systemctl restart nginx
        log_ok "Nginx 已通过 systemctl 启动"
    else
        nginx
        log_ok "Nginx 已直接启动"
    fi

    # ── 启动 / 重载 Supervisor ──
    if systemctl list-units --type=service 2>/dev/null | grep -q supervisord; then
        systemctl enable supervisord
        systemctl restart supervisord
        log_ok "Supervisor 已通过 systemctl 启动"
    elif systemctl list-units --type=service 2>/dev/null | grep -q supervisor; then
        systemctl enable supervisor
        systemctl restart supervisor
        log_ok "Supervisor 已通过 systemctl 启动"
    else
        # 尝试 supervisord 直接启动
        supervisord -c /etc/supervisord.conf 2>/dev/null || true
        # 某些发行版配置文件位置不同
        supervisord -c /etc/supervisor/supervisord.conf 2>/dev/null || true
        log_ok "Supervisor 已直接启动"
    fi

    # 等待就绪
    sleep 2

    # 重新读取配置并启动应用
    log_info "加载 Supervisor 配置..."
    supervisorctl reread || log_warn "supervisorctl reread 失败"
    supervisorctl update || log_warn "supervisorctl update 失败"

    if supervisorctl status "${APP_NAME}" 2>/dev/null | grep -q "RUNNING\|STARTING"; then
        log_ok "${APP_NAME} 已在运行"
    else
        log_info "尝试启动 ${APP_NAME}..."
        supervisorctl start "${APP_NAME}" 2>/dev/null || {
            log_warn "supervisorctl start 失败，检查配置:"
            log_warn "  配置文件: ${SUPERVISOR_CONF}"
            log_warn "  尝试: supervisorctl reread && supervisorctl update && supervisorctl start ${APP_NAME}"
            log_warn "  查看日志: tail -f /var/log/${APP_NAME}.log"
        }
    fi

    log_ok "所有服务启动完成"
    echo ""
}

# ============================================================================
#  显示服务状态
# ============================================================================
show_status() {
    echo "=========================================="
    echo -e "  ${GREEN}RSS Reader - 部署完成${NC}"
    echo "=========================================="
    echo ""
    echo -e "  ${CYAN}前端访问地址:${NC}  http://<服务器IP>:${NGINX_PORT}"
    echo -e "  ${CYAN}API 文档:${NC}      http://<服务器IP>:${NGINX_PORT}/docs"
    echo ""
    echo "  管理命令:"
    echo "    supervisorctl status ${APP_NAME}        # 查看状态"
    echo "    supervisorctl restart ${APP_NAME}       # 重启后端"
    echo "    supervisorctl stop ${APP_NAME}          # 停止后端"
    echo "    supervisorctl start ${APP_NAME}         # 启动后端"
    echo "    systemctl restart nginx                # 重启 nginx"
    echo ""
    echo "  日志文件:"
    echo "    tail -f /var/log/${APP_NAME}.log               # 后端日志"
    echo "    tail -f /var/log/${APP_NAME}_error.log         # 后端错误日志"
    echo "    tail -f /var/log/nginx/access.log              # nginx 访问日志"
    echo ""
    echo "  ── 内存优化建议（6GB 服务器） ──"
    local mem_total_mb
    mem_total_mb=$(free -m | awk '/^Mem:/{print $2}' 2>/dev/null || echo "0")
    if [ "$mem_total_mb" -gt 0 ] && [ "$mem_total_mb" -le 8000 ]; then
        echo "  检测到内存: ${mem_total_mb}MB"
        echo "  1. 当前 uvicorn workers: ${UVICORN_WORKERS}（可通过 UVICORN_WORKERS=2 调高）"
        echo "  2. 建议开启 swap 防止 OOM:"
        echo "       fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile"
        echo "       echo '/swapfile none swap sw 0 0' >> /etc/fstab"
        echo "  3. ONNX TTS 模型（moss-tts-nano）内存约 1-2GB，首次生成时会加载"
        echo "  4. 如果内存不足，可在设置中切换为 moss-ttsd（mlx-speech，更轻量）"
    fi
    echo ""

    # 显示 supervisor 状态
    echo ""
    log_info "当前服务状态:"
    supervisorctl status "${APP_NAME}" 2>/dev/null || echo "   (supervisor 可能未运行，请检查)"
    echo ""
}

# ============================================================================
#  卸载功能
# ============================================================================
uninstall() {
    log_warn "即将卸载 RSS Reader 部署配置..."
    echo ""
    echo "将执行以下操作:"
    echo "  1. 停止并移除 supervisor 中的 ${APP_NAME} 服务"
    echo "  2. 删除 nginx 配置: ${NGINX_CONF}"
    echo "  3. 删除 supervisor 配置: ${SUPERVISOR_CONF}"
    echo "  4. 重载 nginx"
    echo "  5. (保留前端构建产物和后端依赖，如需删除请手动操作)"
    echo ""
    read -r -p "确认卸载? [y/N] " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        log_info "取消卸载"
        exit 0
    fi

    log_info "停止服务..."
    supervisorctl stop "${APP_NAME}" 2>/dev/null || true
    supervisorctl remove "${APP_NAME}" 2>/dev/null || true

    log_info "删除配置文件..."
    rm -f "$NGINX_CONF"
    rm -f "$SUPERVISOR_CONF"

    log_info "重载 nginx..."
    nginx -s reload 2>/dev/null || systemctl restart nginx 2>/dev/null || true

    log_ok "卸载完成"
    exit 0
}

# ============================================================================
#  主流程
# ============================================================================
main() {
    echo ""
    echo "=========================================="
    echo -e "  ${GREEN}RSS Reader - 一键部署脚本${NC}"
    echo "=========================================="
    echo ""

    check_prerequisites

    # 如果指定了 --uninstall 参数则执行卸载
    if [ "${1:-}" = "--uninstall" ] || [ "${1:-}" = "-u" ]; then
        uninstall
    fi

    install_system_deps
    setup_poetry
    install_backend

    # TTS 模型下载（可设置 SKIP_TTS_MODELS=1 跳过）
    if [ "${SKIP_TTS_MODELS:-0}" != "1" ]; then
        download_tts_models
    else
        log_info "已跳过 TTS 模型下载 (SKIP_TTS_MODELS=1)"
        echo ""
    fi

    build_frontend
    fix_permissions
    configure_nginx
    configure_supervisor
    start_services
    show_status
}

main "$@"
