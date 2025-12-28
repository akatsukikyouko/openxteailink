FROM ubuntu
WORKDIR /app

# 1. 配置阿里云镜像源
RUN rm -f /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/ubuntu.sources && \
    echo "deb http://mirrors.aliyun.com/ubuntu/ noble main restricted universe multiverse\n\
deb http://mirrors.aliyun.com/ubuntu/ noble-updates main restricted universe multiverse\n\
deb http://mirrors.aliyun.com/ubuntu/ noble-security main restricted universe multiverse\n\
deb http://mirrors.aliyun.com/ubuntu/ noble-backports main restricted universe multiverse" \
> /etc/apt/sources.list

# 2. 一次性安装所有需要的工具（运行时 + 构建工具 + Python）
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    python3 \
    python3-dev \
    python3-pip \
    python3.12-venv \
    && rm -rf /var/lib/apt/lists/*

# 3. 安装 uv
RUN pip3 install uv -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages

# 4. 创建虚拟环境并安装依赖
COPY requirements.txt .
RUN uv venv /app/.venv && \
    uv pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 5. 复制代码并设置目录
COPY . .
RUN mkdir -p /app/static/output /app/uploads

# 6. 配置环境变量并启动
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV="/app/.venv" \
    UV_VENV="/app/.venv"

EXPOSE 8098 8099
CMD ["uv", "run", "src/web_server.py"]
