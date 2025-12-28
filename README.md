# 慧星传书 阅星曈（XTEINK）传书智能体 XTEAILINK

为阅星曈（XTEINK）电子纸(X4)阅读器提供智能传书服务的智能体系统，支持多种格式传书、AI智能电子期刊的生成以及MCP服务！

## 功能特性

- 智能传书服务 - 相比阅星曈自带传书功能需要先将电子纸连接网络，慧星传书上传后加入队列，系统会自动等待电子纸连接网络后主动传书（这非常适合Nas使用！），支持多种电子书格式转换为 XTEINK XTC格式
- AI 电子期刊 - 支持流式SteamableHTTP的MCP和生图能力的对话式智能体，助您生成图文并茂的电子期刊并传到您的阅星曈，畅享优质阅读体验
- MCP支持 - 开放SteamableHTTP MCP服务，支持cherrystodio，claude code等工具连接到慧星传书

## ToDo

- []支持转换为XTC灰度模式
- []定时订阅，支持每天订阅电子期刊
- []RSS订阅和网页内容获取的油猴脚本
- []电子期刊排版优化
- []传书自动整理


## 通过一个modelscope api-key白嫖所有AI功能
大模型、生图、联网搜索？配置太复杂，要花钱？？
感谢modelscope的免费白嫖api，让我们能用一个api-key白嫖XTEAILINK的所有ai功能！
1. 创建一个 [modelscope](https://www.modelscope.cn/user/register) 账号
2. 获取api-key（右上角-账号设置-访问令牌）
3. MCP广场-必应搜索中文-服务配置，配置长期的bing搜索服务，获取url
4. 在慧星传书智能体右下角ai助手中配置：大模型api-key，生图api-key，bing搜索url和api-key

## 致谢

### epub2xtc
用于生成 XTEINK 电子书格式的转换工具
- GitHub: [epub2xtc](https://github.com/jonasdiemer/epub2xtc)
- 功能: 将 EPUB 转换为 XTC/XTG 格式，支持 PNG 图片处理
- 位置: `tool/epub2xtc-main/`

### zcoder
本项目完全使用智谱zcoder和GLM-4.7 vibecoding完成！

## 快速开始

### 使用 Docker 部署（推荐）

1. 克隆项目并进入目录：
```bash
cd XTEAILINK
```

2. 使用 Docker Compose 启动服务：
```bash
docker-compose up -d --build
```

3. 访问服务：
- 主服务：http://localhost:8098
- 其他服务：http://localhost:8099

docker部署使用ubuntu作为基础镜像，并基本完全配置国内源，您可以自行替换为别的基础镜像。

### Windows运行

1. 安装依赖：
你的电脑需要有python环境和nv，如果没有uv请安装uv
```bash
pip install uv
```

2. 启动服务：
```bash
# 推荐使用 start.bat（Windows）
start.bat
```

## 配置

配置文件位于 `config/` 目录下：

- `config.json` - 主配置文件
- `ai_config.json` - AI 相关配置，也可以在前端配置

请根据需要修改配置文件中的参数。

## 端口

系统暴露以下端口：

- `8098` - Web 服务主端口（传书服务界面）
- `8099` - MCP端口

## MCP
你可以用 http://服务器地址:8099/mcp 连接到SteamableHTTP的MCP服务，可让LLM将任何内容转为txt，直接传输到您的电子纸！

## 项目结构

```
XTEAILINK/
├── src/                    # 源代码目录
│   ├── web_server.py      # Web 服务器
│   ├── chat_service.py    # AI助手
│   ├── conversion_service.py # 转换服务
│   └── mcp/               # MCP 服务器
├── static/                # 静态资源
│   ├── js/               # JavaScript 文件
│   └── output/           # 输出文件目录
├── templates/            # HTML 模板
├── config/               # 配置文件
├── tool/                 # 工具脚本
├── requirements.txt      # Python 依赖
├── Dockerfile           # Docker 构建文件
├── docker-compose.yml   # Docker Compose 配置
└── README.md           # 项目说明
```
