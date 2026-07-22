#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="simplequan"
PID_FILE="$APP_DIR/.pid"
VENV_DIR="$APP_DIR/.venv"

# 自动检测 Python 解释器（优先 python3 → python）
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "FATAL: 找不到 python3 或 python"
    exit 1
fi

# 虚拟环境一次性初始化
if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境 ..."
    if ! "$PYTHON" -m venv "$VENV_DIR" 2>/dev/null; then
        echo "失败，尝试安装 python3-venv ..."
        apt-get update -qq && apt-get install -y -qq python3-venv
        "$PYTHON" -m venv "$VENV_DIR"
    fi
    echo "安装依赖 ..."
    "$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
    echo "环境就绪"
fi
PYTHON="$VENV_DIR/bin/python"
LOG_DIR="$APP_DIR/logs"
LOG_FILE="$LOG_DIR/${APP_NAME}_$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

status() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "running (pid=$(cat "$PID_FILE"))"
        return 0
    else
        echo "stopped"
        return 1
    fi
}

start() {
    if status >/dev/null 2>&1; then
        echo "[SKIP] $APP_NAME 已在运行中"
        return 1
    fi
    echo -n "启动 $APP_NAME ... "
    cd "$APP_DIR"
    nohup "$PYTHON" main.py >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
        echo "OK (pid=$pid)"
    else
        echo "FAIL — 查看日志: tail -f $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop() {
    if ! status >/dev/null 2>&1; then
        echo "[SKIP] $APP_NAME 未在运行"
        return 0
    fi
    local pid=$(cat "$PID_FILE")
    echo -n "停止 $APP_NAME (pid=$pid) ... "
    kill "$pid"
    # 等最多 15s 优雅退出
    for i in $(seq 1 15); do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "OK"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 1
    done
    # 强制杀
    kill -9 "$pid" 2>/dev/null || true
    echo "KILLED"
    rm -f "$PID_FILE"
}

restart() {
    stop
    sleep 1
    start
}

tailf() {
    local latest
    latest=$(ls -t "$LOG_DIR/${APP_NAME}_"*.log 2>/dev/null | head -1)
    if [ -z "$latest" ]; then
        echo "没有找到日志文件"
        return 1
    fi
    echo "tail -f $latest (Ctrl+C 退出)"
    tail -f "$latest"
}

# 日志清理: 保留最近 30 天
cleanup_logs() {
    find "$LOG_DIR" -name "${APP_NAME}_*.log" -mtime +30 -delete 2>/dev/null || true
    echo "日志清理完成 (保留30天)"
}

usage() {
    echo "用法: $0 {start|stop|restart|status|tail|cleanup}"
    exit 1
}

case "${1:-}" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    tail)    tailf ;;
    cleanup) cleanup_logs ;;
    *)       usage ;;
esac
