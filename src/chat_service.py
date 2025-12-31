#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI聊天服务 - 基于pydantic-ai
参考LinkSlideAI的实现方式
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

# 添加项目根目录到sys.path，确保能导入image_tool
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入图片生成工具
try:
    from tool.image_tool import generate_slide_image_tool
    IMAGE_TOOL_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("图片生成工具加载成功")
except ImportError as e:
    IMAGE_TOOL_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"图片生成工具导入失败: {e}，生图功能将不可用")

try:
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.mcp import MCPServerStreamableHTTP
    PYDANTIC_AVAILABLE = True
except ImportError as e:
    PYDANTIC_AVAILABLE = False
    logging.warning(f"pydantic-ai未安装: {e}")

logger = logging.getLogger(__name__)


@dataclass
class ChatDeps:
    """聊天依赖项"""
    enable_image: bool = False


def load_ai_config():
    """加载AI配置"""
    config_path = Path("config/ai_config.json")
    default_config = {
        'enabled': False,
        'openai': {
            'base_url': 'http://localhost:11434/v1',
            'api_key': 'sk-test',
            'model': 'qwen2.5:latest'
        },
        'mcp_servers': [
            {
                'name': 'Local MCP',
                'url': 'http://localhost:8099/mcp',
                'has_header': False,
                'custom_header': '',
                'enabled': False
            }
        ],
        'image_generation': {
            'enabled': False,
            'tool': 'internal',
            'api_key': '',
            'base_url': 'https://api-inference.modelscope.cn/',
            'model_id': 'Tongyi-MAI/Z-Image-Turbo'
        }
    }

    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            # 更新MCP服务器配置,添加缺失的字段
            if 'mcp_servers' in loaded:
                for server in loaded['mcp_servers']:
                    if 'has_header' not in server:
                        server['has_header'] = False
                    if 'custom_header' not in server:
                        server['custom_header'] = ''
                    # 移除旧的api_key字段(如果存在)
                    if 'api_key' in server:
                        del server['api_key']

            # 更新image_generation配置,添加缺失的字段
            if 'image_generation' in loaded:
                img_gen = loaded['image_generation']
                if 'api_key' not in img_gen:
                    img_gen['api_key'] = ''
                if 'base_url' not in img_gen:
                    img_gen['base_url'] = 'https://api-inference.modelscope.cn/'
                if 'model_id' not in img_gen:
                    img_gen['model_id'] = 'Tongyi-MAI/Z-Image-Turbo'

            default_config.update(loaded)
        except Exception as e:
            logger.error(f"加载AI配置失败: {e}")

    return default_config


class ChatService:
    def __init__(self):
        self.config = load_ai_config()
        self.agent = None
        self.deps = None

        if PYDANTIC_AVAILABLE and self.config.get('enabled', False):
            self.initialize_agent()

    def initialize_agent(self):
        """初始化AI Agent - 参考LinkSlideAI的方式"""
        try:
            cfg = self.config

            # 1. 创建MCP服务器列表
            mcp_toolsets = []
            for mcp_config in cfg.get('mcp_servers', []):
                if mcp_config.get('enabled', True):
                    try:
                        # 构建headers
                        headers = None
                        if mcp_config.get('has_header', False):
                            # 使用自定义header
                            if mcp_config.get('custom_header'):
                                custom_header = mcp_config.get('custom_header').strip()
                                if custom_header.startswith('{'):
                                    # JSON格式
                                    import json
                                    headers = json.loads(custom_header)
                                else:
                                    # 简单格式 "Authorization: xxx"
                                    parts = custom_header.split(':', 1)
                                    if len(parts) == 2:
                                        headers = {parts[0].strip(): parts[1].strip()}

                        mcp_server = MCPServerStreamableHTTP(
                            url=mcp_config['url'],
                            headers=headers
                        )
                        mcp_toolsets.append(mcp_server)
                        logger.info(f"已连接MCP服务器: {mcp_config['name']}")
                    except Exception as e:
                        logger.error(f"连接MCP服务器失败 {mcp_config['name']}: {e}")

            # 2. 创建OpenAI模型
            model = OpenAIChatModel(
                cfg['openai']['model'],
                provider=OpenAIProvider(
                    base_url=cfg['openai']['base_url'],
                    api_key=cfg['openai']['api_key'],
                ),
            )

            # 3. 创建依赖项
            self.deps = ChatDeps(
                enable_image=cfg.get('image_generation', {}).get('enabled', False)
            )

            # 4. 创建Agent
            system_prompt = self._build_system_prompt()

            self.agent = Agent(
                model=model,
                system_prompt=system_prompt,
                toolsets=mcp_toolsets if mcp_toolsets else None,
            )

            # 5. 添加自定义工具
            self._register_tools()

            logger.info("AI Agent初始化成功")

        except Exception as e:
            logger.error(f"AI Agent初始化失败: {e}")
            self.agent = None

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        prompt = f"""你是一个专业的电子期刊创作助手。当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}

你的任务是：
1. 根据用户的主题创作一篇完整的电子期刊文章（约2000字）
2. 生成3-5张相关配图来丰富文章内容
3. 将文章和配图制作成PDF电子期刊并传送到设备

创作要求：
- 文章结构：吸引人的标题 + 引言 + 3-5个章节 + 结语
- **标题创作要求**：
  * 必须为文章起一个吸引人的标题
  * 标题要能准确反映文章主题和内容
  * 标题要简洁有力，最好在8-20字之间
  * 标题可以采用：设问句、数字列举、对比、比喻等手法
  * 例如："人工智能：改变世界的五种力量"、"量子计算：破解未来的密码"
- 每个章节要有明确的主题和丰富的内容
- 字数控制在2000字左右（确保内容充实但不冗长）
- 配图要与内容紧密相关

**配图插入规则（非常重要）**：
- 在创作文章时，在需要插入配图的地方使用特殊标记：[IMAGE:图片描述]
- 例如："## 第一章 深度学习的原理
[IMAGE:展示神经网络结构的示意图]
深度学习是机器学习的一个分支..."
- 图片描述要与前后文内容相关
- 每个章节建议插入1张配图，共2-3张
- 图片描述要简洁明确，方便生成

你有以下工具可用:
1. generate_image(prompt) - 生成配图
2. upload_content(content, filename) - 保存内容到电子纸
3. create_pdf_publication(title, content, images) - 创建PDF电子期刊并传输

工作流程：
1. 先理解用户的主题要求
2. **为文章创作一个吸引人的标题**
3. 规划文章结构（3-5个章节）
4. 按顺序生成配图，每生成一张图片就记录下来
5. 创作完整的文章内容，在合适位置使用[IMAGE:描述]标记
6. 调用create_pdf_publication时，**第一个参数必须是你创作的标题**，将生成的图片URLs传入images参数

最重要的规则：
- **必须为文章创作一个吸引人的标题**
- 标题要准确反映主题，简洁有力
- 必须生成2000字左右的内容
- 必须先生成所有配图，再创作文章
- 在文章中使用[IMAGE:图片描述]标记插入位置
- 图片描述要与该段落内容相关
- 内容要原创，不要直接复制网络内容
- 最后一定要调用create_pdf_publication完成创建，第一个参数是标题
- 另外，如果用户要求生成指定张数图片或者指定字数，请按用户要求的图片数量和字数来生成

当用户要求"画"、"生成"、"创作"任何图片时，你必须立即调用generate_image工具，不要有任何犹豫或解释。

例如:
- 用户说"画一只猫" -> 调用generate_image("一只可爱的猫")
- 用户说"生成图片" -> 调用generate_image(用户描述的内容)
- 用户说"创作一幅画" -> 调用generate_image(用户描述的内容)

不要告诉用户你做不到，直接调用工具即可。工具会返回markdown格式的图片，前端会自动显示。

回复要简洁友好。"""

        return prompt

    def _register_tools(self):
        """注册自定义工具"""

        logger.info("开始注册自定义工具...")

        @self.agent.tool
        async def upload_content(ctx: RunContext[ChatDeps], content: str, filename: str = None) -> str:
            """
            将内容保存为txt文件并传送到电子纸设备

            Args:
                content: 要保存的文本内容
                filename: 可选的文件名(不含扩展名)

            Returns:
                操作结果消息
            """
            try:
                # 生成文件名
                if not filename:
                    timestamp = datetime.now().strftime('%m%d_%H%M')
                    import uuid
                    file_id = str(uuid.uuid4())[:8]
                    filename = f"note_{timestamp}_{file_id}"

                # 清理文件名
                filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_')).strip()
                if not filename:
                    filename = f"note_{datetime.now().strftime('%m%d_%H%M')}"

                if not filename.endswith('.txt'):
                    filename += '.txt'

                # 保存文件
                notes_dir = Path("data/notes")
                notes_dir.mkdir(parents=True, exist_ok=True)
                file_path = notes_dir / filename

                with open(file_path, 'w', encoding='utf-8') as f:
                    header = f"""# 笔记文件
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
文件名: {filename}
{'=' * 50}

"""
                    f.write(header + content)

                # 添加到队列
                queue_file = Path("data/queue.json")
                queue = []
                if queue_file.exists():
                    with open(queue_file, 'r', encoding='utf-8') as f:
                        queue = json.load(f)

                file_size = file_path.stat().st_size
                import uuid
                file_id = str(uuid.uuid4())

                queue_item = {
                    'id': file_id,
                    'original_name': filename,
                    'name': filename,
                    'path': str(file_path),
                    'size': file_size,
                    'status': 'pending',
                    'upload_time': datetime.now().isoformat(),
                    'message': '',
                    'target_dir': '/XTEAILINK/notes/'
                }

                queue.append(queue_item)

                with open(queue_file, 'w', encoding='utf-8') as f:
                    json.dump(queue, f, ensure_ascii=False, indent=2)

                return f"✅ 内容已成功保存并加入传书队列! 文件名: {filename}"

            except Exception as e:
                return f"❌ 保存失败: {str(e)}"

        # 添加生图工具(标准版本)
        if self.deps.enable_image:
            logger.info("注册生图工具: generate_image")

            @self.agent.tool
            async def generate_image(ctx: RunContext[ChatDeps], prompt: str) -> str:
                """
                生成图片 - 当用户要求画图、生成图片、创作图像时必须调用此工具。

                适用场景:
                - 用户说"画"、"生成"、"创作"任何图片内容时
                - 用户要求视觉化某个场景、物体或角色时
                - 用户想要图片形式的内容时

                Args:
                    prompt (str): 图片的详细描述。例如:
                        - "一只可爱的猫咪"
                        - "美丽的风景画"
                        - "动漫风格的女孩"

                Returns:
                    str: 生成的图片markdown格式，前端会自动显示

                Examples:
                    generate_image("一只可爱的猫咪") -> "![图片](/static/output/...)"
                    generate_image("日落风景") -> "![图片](/static/output/...)"
                """
                try:
                    # 检查image_tool是否可用
                    if not IMAGE_TOOL_AVAILABLE:
                        return "❌ 图片生成模块未找到。请确保image_tool.py在项目根目录。"

                    # 调用生图工具
                    import uuid

                    session_id = str(uuid.uuid4())[:8]
                    page_index = 1

                    # 添加适合电子墨水屏的轻量级插图风格提示词
                    light_style_prompt = (
                        f"{prompt}\n"
                        "Style requirements: "
                        "Light and clean illustration style suitable for e-ink display. "
                        "Use thin delicate lines instead of thick heavy lines. "
                        "Minimal to no shading - keep areas mostly white. "
                        "Low contrast, soft appearance, avoid dark solid areas. "
                        "Think line art sketches rather than heavy ink drawings. "
                        "Clean, airy, minimal black ink on white background. "
                        "Similar to textbook diagrams or light manga illustrations."
                    )

                    logger.info(f"使用轻量级风格生成图片: {light_style_prompt[:100]}...")

                    # 调用生图函数
                    image_url = generate_slide_image_tool(light_style_prompt, page_index, session_id)

                    # 返回markdown格式的图片，前端会自动渲染
                    return f"✅ 图片已生成!(漫画风格)\n\n![生成的图片]({image_url})"

                except Exception as e:
                    import traceback
                    logger.error(f"生图失败: {e}\n{traceback.format_exc()}")
                    error_msg = str(e)
                    # 提供更友好的错误提示
                    if "未启用" in error_msg:
                        return "⚠️ 图片生成功能未启用。请在AI设置中启用生图功能并配置API。"
                    elif "API Key" in error_msg:
                        return "⚠️ API Key未配置。请在AI设置的生图API配置中填写API Key。"
                    else:
                        return f"❌ 生图失败: {error_msg}"
        else:
            logger.info("生图功能未启用，注册配置指导工具: generate_image_info")

            # 生图功能未启用时的提示工具
            @self.agent.tool
            async def generate_image_info(ctx: RunContext[ChatDeps], prompt: str = "") -> str:
                """
                生图功能说明 - 当生图未启用时提供指导
                """
                return """⚠️ 生图功能未启用

要使用生图功能,请按以下步骤配置:

1. 打开AI助手设置(点击右上角设置图标)
2. 找到"生图工具"部分
3. 将"启用生图"设置为"是"
4. 在"生图API配置"中填写:
   - API Key: 你的生图服务API密钥
   - Base URL: 生图服务的API地址
   - 模型ID: 生图模型的ID
5. 点击"保存"按钮

配置完成后就可以使用生图功能了!

支持生图服务:
- 火山引擎豆包
- ModelScope的各种生图模型（推荐！）
"""

        # 添加PDF生成+转换工具
        @self.agent.tool
        async def create_pdf_publication(ctx: RunContext[ChatDeps], title: str, content: str, images: list = None) -> str:
            """
            创建电子期刊PDF并转换为XTC格式上传到电子纸

            使用说明：
            - **必须提供标题参数** - 这是电子期刊的标题
            - 在文章内容中使用 [IMAGE:图片描述] 标记来指定图片插入位置
            - 例如: "## 第一章\n[IMAGE:神经网络结构图]\n正文内容..."
            - 系统会自动生成匹配的图片并插入到指定位置

            Args:
                title: **必需** - 出版物标题（8-20字，简洁有力）
                content: 正文内容(Markdown格式，支持[IMAGE:描述]标记)
                images: 预先生成的图片URL列表(可选，如果没有提供会自动生成)

            Returns:
                操作结果消息

            重要提示：
            - title参数是必需的，不能为空
            - 标题会作为PDF的第一页显示
            - 标题也会作为文件名的一部分
            """
            try:
                import uuid
                from pathlib import Path as PathLib
                import re

                # 生成唯一ID和文件名
                pub_id = str(uuid.uuid4())[:8]
                timestamp = datetime.now().strftime('%m%d_%H%M')

                # 清理标题用于文件名（移除特殊字符）
                title_clean = re.sub(r'[<>:"/\\|?*]', '', title)
                title_clean = title_clean[:30] if len(title_clean) > 30 else title_clean  # 限制长度

                # 创建输出目录（使用绝对路径）
                project_root = Path(__file__).parent.parent
                output_dir = project_root / "data" / "publications"
                output_dir.mkdir(parents=True, exist_ok=True)

                # PDF文件路径 - 使用标题作为文件名的一部分
                pdf_filename = f"{timestamp}_{title_clean}_{pub_id}.pdf"
                pdf_path = output_dir / pdf_filename

                logger.info(f"创建电子期刊: {title}")
                logger.info(f"PDF文件: {pdf_filename}")

                # 解析内容中的图片标记
                image_markers = re.findall(r'\[IMAGE:(.+?)\]', content)
                logger.info(f"找到 {len(image_markers)} 个图片插入标记: {image_markers}")

                # 收集或生成图片
                all_images = images or []

                # 如果有图片标记但没有提供足够的图片，则生成图片
                if image_markers and len(all_images) < len(image_markers):
                    logger.info(f"需要生成 {len(image_markers) - len(all_images)} 张图片")

                    for idx, marker_desc in enumerate(image_markers[len(all_images):]):
                        try:
                            logger.info(f"生成图片 {idx+1}: {marker_desc}")

                            # 调用生图工具
                            from tool.image_tool import generate_slide_image_tool
                            img_result = await generate_slide_image_tool(marker_desc)

                            if isinstance(img_result, dict) and 'path' in img_result:
                                img_web_path = img_result['path']
                                all_images.append(img_web_path)
                                logger.info(f"图片生成成功: {img_web_path}")
                            elif isinstance(img_result, str) and 'static/output' in img_result:
                                all_images.append(img_result)
                                logger.info(f"图片已添加: {img_result}")
                            else:
                                logger.warning(f"图片生成失败: {img_result}")

                        except Exception as e:
                            logger.error(f"生成图片失败: {e}")
                            continue

                # 移除内容中的[IMAGE:xxx]标记（稍后会在正确位置插入图片）
                content_clean = re.sub(r'\[IMAGE:.+?\]', '', content)

                # 生成PDF (使用reportlab)
                from reportlab.lib.pagesizes import A4
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import inch
                from reportlab.lib.enums import TA_LEFT, TA_CENTER
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont

                # 注册中文字体 - 使用项目自带字体，确保嵌入
                try:
                    import os
                    import sys

                    chinese_font = 'Helvetica'  # 默认回退字体
                    font_registered = False

                    # 获取项目根目录
                    project_root = PathLib(__file__).parent.parent
                    fonts_dir = project_root / "fonts"

                    logger.info(f"========== PDF字体配置开始 ==========")
                    logger.info(f"项目根目录: {project_root}")
                    logger.info(f"字体目录: {fonts_dir}")
                    logger.info(f"字体目录存在: {fonts_dir.exists()}")

                    # 优先使用项目自带的字体（跨平台）
                    if fonts_dir.exists():
                        font_file = fonts_dir / 'AlibabaPuHuiTi-3-75-SemiBold.ttf'

                        logger.info(f"字体文件路径: {font_file}")
                        logger.info(f"字体文件存在: {font_file.exists()}")

                        if font_file.exists():
                            try:
                                # 注册字体并确保嵌入PDF
                                pdfmetrics.registerFont(
                                    TTFont('AlibabaPuHuiTi', str(font_file), subfontIndex=0)
                                )

                                chinese_font = 'AlibabaPuHuiTi'
                                font_registered = True

                                logger.info(f"✓✓✓ 字体注册成功! ✓✓✓")
                                logger.info(f"字体名称: AlibabaPuHuiTi")
                                logger.info(f"字体文件: {font_file}")
                                logger.info(f"文件大小: {font_file.stat().st_size / 1024 / 1024:.2f} MB")

                                # 验证字体
                                from reportlab.pdfbase.pdfmetrics import getFont
                                try:
                                    test_font = getFont('AlibabaPuHuiTi')
                                    logger.info(f"✓ 字体验证成功，可以正常使用")
                                except Exception as ve:
                                    logger.error(f"✗ 字体验证失败: {ve}")

                            except Exception as e:
                                logger.error(f"✗✗✗ 字体注册失败! ✗✗✗")
                                logger.error(f"错误类型: {type(e).__name__}")
                                logger.error(f"错误信息: {e}")
                                import traceback
                                logger.error(traceback.format_exc())
                        else:
                            logger.error(f"✗ 字体文件不存在: {font_file}")


                    # 最终状态
                    logger.info(f"========== PDF字体配置结束 ==========")
                    if font_registered:
                        logger.info(f"✓ 最终使用字体: {chinese_font}")
                    else:
                        logger.error(f"✗✗✗ 未找到任何中文字体！PDF将显示黑框！✗✗✗")
                        logger.error(f"请确保 fonts/AlibabaPuHuiTi-3-75-SemiBold.ttf 文件存在")

                except Exception as e:
                    logger.error(f"字体配置过程出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    chinese_font = 'Helvetica'

                # 自定义页面尺寸，匹配电子纸屏幕比例（480×800 = 0.6）
                # 使用reportlab的points单位，1inch = 72points
                # 目标：178.2mm × 297mm，宽高比0.6，匹配屏幕比例
                from reportlab.lib.units import mm
                custom_width = 178.2 * mm  # 转换为points
                custom_height = 297 * mm   # 转换为points
                custom_pagesize = (custom_width, custom_height)

                # 生成PDF（使用自定义尺寸，完美匹配电子纸屏幕比例）
                doc = SimpleDocTemplate(
                    str(pdf_path),
                    pagesize=custom_pagesize,
                    leftMargin=0.75*inch,
                    rightMargin=0.75*inch,
                    topMargin=0.75*inch,
                    bottomMargin=0.75*inch
                )

                title_style = ParagraphStyle(
                    'CustomTitle',
                    fontSize=60,
                    fontName=chinese_font,
                    textColor='#000000',
                    alignment=TA_CENTER,
                    spaceAfter=40,
                    leading=80
                )

                subtitle_style = ParagraphStyle(
                    'CustomSubtitle',
                    fontSize=50,
                    fontName=chinese_font,
                    textColor='#000000',
                    alignment=TA_LEFT,
                    spaceAfter=30,
                    leading=70
                )

                subsubtitle_style = ParagraphStyle(
                    'CustomSubSubtitle',
                    fontSize=45,
                    fontName=chinese_font,
                    textColor='#000000',
                    alignment=TA_LEFT,
                    spaceAfter=25,
                    leading=60
                )

                content_style = ParagraphStyle(
                    'CustomContent',
                    fontSize=50,
                    fontName=chinese_font,
                    textColor='#333333',
                    alignment=TA_LEFT,
                    spaceAfter=20,
                    leading=75
                )

                # 构建PDF内容，按标记插入图片
                story = []

                # 标题页
                story.append(Paragraph(title, title_style))
                story.append(Spacer(1, 8))

                # 添加副标题（生成日期）
                date_str = datetime.now().strftime('%Y年%m月%d日')
                subtitle = ParagraphStyle(
                    'DateSubtitle',
                    fontSize=72,  # 18 * 4
                    fontName=chinese_font,
                    textColor='#666666',
                    alignment=TA_CENTER,
                    spaceAfter=120,  # 30 * 4
                    leading=96  # 24 * 4
                )
                story.append(Paragraph(f"—— {date_str} ——", subtitle))
                story.append(Spacer(1, 20))

                # 分割内容并按标记位置插入图片
                # 首先按段落分割，同时记录图片标记的位置
                paragraphs = content_clean.split('\n\n')
                image_idx = 0

                for para_idx, paragraph in enumerate(paragraphs):
                    if not paragraph.strip():
                        continue

                    # 处理段落内容
                    paragraph = re.sub(r'^### (.+)$', r'\1', paragraph, flags=re.MULTILINE)
                    paragraph = re.sub(r'^## (.+)$', r'\1', paragraph, flags=re.MULTILINE)
                    paragraph = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', paragraph)
                    paragraph = re.sub(r'\*(.+?)\*', r'<i>\1</i>', paragraph)
                    paragraph = paragraph.replace('\n', '<br/>')

                    # 根据标题类型选择样式
                    original_paras = content.split('\n\n')
                    if para_idx < len(original_paras):
                        original_para = original_paras[para_idx]
                        if original_para.strip().startswith('### '):
                            story.append(Paragraph(paragraph, subsubtitle_style))
                            story.append(Spacer(1, 8))
                        elif original_para.strip().startswith('## '):
                            story.append(Paragraph(paragraph, subtitle_style))
                            story.append(Spacer(1, 8))
                        else:
                            story.append(Paragraph(paragraph, content_style))
                            story.append(Spacer(1, 8))
                    else:
                        story.append(Paragraph(paragraph, content_style))
                        story.append(Spacer(1, 8))

                    # 检查原始内容中该段落后是否有[IMAGE:xxx]标记
                    # 重新解析原始内容，找到对应位置的图片标记
                    original_paras = content.split('\n\n')
                    if para_idx < len(original_paras):
                        current_original_para = original_paras[para_idx]
                        # 检查下一段是否以[IMAGE:开头
                        if para_idx + 1 < len(original_paras):
                            next_para = original_paras[para_idx + 1].strip()
                            if next_para.startswith('[IMAGE:'):
                                # 在当前段落后插入图片
                                if all_images and image_idx < len(all_images):
                                    try:
                                        img_url = all_images[image_idx]
                                        logger.info(f"在第{para_idx}段落后（标记位置）插入图片{image_idx+1}: {img_url}")

                                        # 加载图片
                                        if img_url.startswith('http'):
                                            import requests
                                            img_response = requests.get(img_url, timeout=10)
                                            from io import BytesIO
                                            img_data = BytesIO(img_response.content)
                                        else:
                                            img_path = PathLib(__file__).parent.parent / img_url.lstrip('/')
                                            if not img_path.exists():
                                                logger.warning(f"图片不存在: {img_path}")
                                                image_idx += 1
                                                continue
                                            with open(img_path, 'rb') as f:
                                                from io import BytesIO
                                                img_data = BytesIO(f.read())

                                        img_obj = RLImage(img_data, width=5*inch, height=3.5*inch, lazy=0, hAlign='CENTER')
                                        story.append(img_obj)
                                        story.append(Spacer(1, 12))
                                        image_idx += 1

                                    except Exception as e:
                                        logger.error(f"插入图片失败: {e}")
                                        image_idx += 1
                                        continue

                # 生成PDF
                doc.build(story)

                # 转换为XTC格式
                from conversion_service import conversion_service

                success, xtc_path_str = conversion_service.convert_pdf_to_xtc(pdf_path)

                if success and xtc_path_str:
                    xtc_path = PathLib(xtc_path_str)

                    # 复制到待传书目录（使用绝对路径）
                    project_root = Path(__file__).parent.parent
                    pending_dir = project_root / "data" / "pending_books"
                    pending_dir.mkdir(parents=True, exist_ok=True)

                    # 创建publications子目录
                    publications_dir = pending_dir / "publications"
                    publications_dir.mkdir(exist_ok=True)

                    # 复制XTC文件到待传书目录
                    target_xtc_path = publications_dir / xtc_path.name
                    import shutil
                    shutil.copy2(xtc_path, target_xtc_path)

                    # 添加到上传队列（使用绝对路径）
                    queue_file = project_root / "data" / "queue.json"
                    queue = []
                    if queue_file.exists():
                        with open(queue_file, 'r', encoding='utf-8') as f:
                            queue = json.load(f)

                    file_size = target_xtc_path.stat().st_size
                    file_id = str(uuid.uuid4())
                    xtc_filename = xtc_path.name

                    queue_item = {
                        'id': file_id,
                        'original_name': xtc_filename,
                        'name': xtc_filename,
                        'path': str(target_xtc_path),
                        'size': file_size,
                        'status': 'pending',
                        'upload_time': datetime.now().isoformat(),
                        'message': '',
                        'target_dir': '/XTEAILINK/notes/'
                    }

                    queue.append(queue_item)

                    with open(queue_file, 'w', encoding='utf-8') as f:
                        json.dump(queue, f, ensure_ascii=False, indent=2)

                    msg = f"✅ 电子期刊已创建并加入传书队列!\n标题: {title}\nPDF: {pdf_filename}\nXTC: {xtc_filename}"
                    if all_images:
                        msg += f"\n📷 已包含 {len(all_images)} 张配图"
                    return msg
                else:
                    return f"⚠️ PDF已生成但转换XTC失败: {pdf_filename}"

            except Exception as e:
                import traceback
                return f"❌ 创建电子期刊失败: {str(e)}\n详细错误: {traceback.format_exc()}"

    async def chat(self, message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        聊天接口
        """
        if not PYDANTIC_AVAILABLE:
            return {
                'success': False,
                'error': 'pydantic-ai未安装',
                'message': '请先安装: pip install pydantic-ai-slim[mcp]'
            }

        if not self.agent:
            return {
                'success': False,
                'error': 'AI Agent未初始化',
                'message': 'AI功能未正确配置或未启用'
            }

        # 记录对话开始时间，用于收集本次对话生成的图片
        import time
        chat_start_time = time.time()

        try:
            # 使用带有消息历史的run方法
            # pydantic-ai支持在message中包含历史对话
            if conversation_history and len(conversation_history) > 0:
                # 构建包含历史的完整对话上下文
                full_conversation = []
                for msg in conversation_history[-10:]:  # 只保留最近10条历史
                    if msg.get('role') == 'user':
                        full_conversation.append(msg.get('content', ''))
                    elif msg.get('role') == 'assistant':
                        full_conversation.append(msg.get('content', ''))

                # 添加当前消息
                full_conversation.append(message)

                # 将整个对话作为单个消息发送
                message_with_context = "\n".join([
                    f"{'用户' if i % 2 == 0 else '助手'}: {msg}"
                    for i, msg in enumerate(full_conversation)
                ])

                result = await self.agent.run(message_with_context, deps=self.deps)
            else:
                # 没有历史，直接发送当前消息
                result = await self.agent.run(message, deps=self.deps)

            # AgentRunResult 的 output 属性包含实际的回复文本
            response_text = result.output

            # 收集本次对话期间生成的图片
            generated_images = self._collect_recent_images(chat_start_time)

            return {
                'success': True,
                'message': response_text,
                'images': generated_images  # 添加生成的图片列表
            }

        except Exception as e:
            logger.error(f"聊天失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'message': f'处理失败: {str(e)}'
            }

    def _collect_recent_images(self, since_time: float) -> List[Dict[str, str]]:
        """
        收集指定时间之后生成的图片

        Args:
            since_time: 起始时间戳

        Returns:
            图片信息列表
        """
        try:
            from pathlib import Path
            import time

            output_dir = Path("static/output")
            if not output_dir.exists():
                return []

            images = []
            # 扫描所有会话目录
            for session_dir in output_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                # 检查目录是否在对话期间被修改过
                dir_mtime = session_dir.stat().st_mtime
                if dir_mtime < since_time:
                    continue

                # 收集该会话的图片
                for img_file in sorted(session_dir.glob("*.jpg")):
                    img_mtime = img_file.stat().st_mtime
                    # 只收集在对话开始后生成的图片
                    if img_mtime >= since_time:
                        images.append({
                            'path': f"/static/output/{session_dir.name}/{img_file.name}",
                            'name': img_file.name,
                            'created': img_mtime
                        })

            # 按创建时间排序
            images.sort(key=lambda x: x['created'])
            logger.info(f"收集到 {len(images)} 张本次对话生成的图片")
            return images

        except Exception as e:
            logger.error(f"收集生成的图片失败: {e}")
            return []

    def update_config(self, new_config: Dict) -> bool:
        """更新配置并重新初始化"""
        try:
            # 恢复隐藏的真实值（如果前端发送的是****，则保留原有的真实值）
            if 'openai' in new_config and 'api_key' in new_config['openai']:
                if new_config['openai']['api_key'] == '****' and 'openai' in self.config:
                    new_config['openai']['api_key'] = self.config['openai'].get('api_key', '')
                # 如果前端提供了隐藏的真实key，使用它
                elif '_api_key_hidden' in new_config.get('openai', {}):
                    new_config['openai']['api_key'] = new_config['openai']['_api_key_hidden']

            # 恢复MCP服务器的custom_header
            if 'mcp_servers' in new_config:
                # 创建现有服务器的映射（按name和url索引）
                existing_servers = {}
                for server in self.config.get('mcp_servers', []):
                    key = (server.get('name'), server.get('url'))
                    existing_servers[key] = server

                # 恢复custom_header
                for server in new_config['mcp_servers']:
                    key = (server.get('name'), server.get('url'))
                    if key in existing_servers:
                        existing_server = existing_servers[key]
                        # 如果新值是****，保留原有值
                        if server.get('custom_header') == '****':
                            server['custom_header'] = existing_server.get('custom_header', '')
                        # 如果前端提供了隐藏的真实值，使用它
                        elif '_custom_header_hidden' in server:
                            server['custom_header'] = server['_custom_header_hidden']

            # 恢复生图工具的API密钥
            if 'image_generation' in new_config and 'api_key' in new_config['image_generation']:
                if new_config['image_generation']['api_key'] == '****' and 'image_generation' in self.config:
                    new_config['image_generation']['api_key'] = self.config['image_generation'].get('api_key', '')
                elif '_api_key_hidden' in new_config.get('image_generation', {}):
                    new_config['image_generation']['api_key'] = new_config['image_generation']['_api_key_hidden']

            # 恢复豆包生图的API密钥
            if 'doubao_image' in new_config and 'api_key' in new_config['doubao_image']:
                if new_config['doubao_image']['api_key'] == '****' and 'doubao_image' in self.config:
                    new_config['doubao_image']['api_key'] = self.config['doubao_image'].get('api_key', '')
                elif '_api_key_hidden' in new_config.get('doubao_image', {}):
                    new_config['doubao_image']['api_key'] = new_config['doubao_image']['_api_key_hidden']

            # 保存配置
            config_path = Path("config/ai_config.json")
            config_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"保存AI配置到: {config_path}")
            logger.info(f"配置包含 {len(new_config.get('mcp_servers', []))} 个MCP服务器")

            # 移除临时字段
            def clean_hidden_fields(obj):
                """递归删除 _*_hidden 字段"""
                if isinstance(obj, dict):
                    return {k: clean_hidden_fields(v) for k, v in obj.items() if not k.startswith('_')}
                elif isinstance(obj, list):
                    return [clean_hidden_fields(item) for item in obj]
                return obj

            config_to_save = clean_hidden_fields(new_config)

            logger.info(f"准备写入配置文件，MCP服务器数量: {len(config_to_save.get('mcp_servers', []))}")
            for i, server in enumerate(config_to_save.get('mcp_servers', [])):
                logger.info(f"  MCP {i+1}: name={server.get('name')}, has_header={server.get('has_header')}, custom_header_len={len(server.get('custom_header', ''))}")

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, ensure_ascii=False, indent=2)

            logger.info("配置文件写入成功")

            # 重新加载配置
            self.config = new_config

            # 重新初始化agent
            if new_config.get('enabled', False):
                logger.info("AI已启用,正在重新初始化agent...")
                self.initialize_agent()
            else:
                logger.info("AI已禁用")
                self.agent = None

            return True

        except Exception as e:
            logger.error(f"更新配置失败: {e}", exc_info=True)
            return False

    def get_config(self) -> Dict:
        """获取当前配置(隐藏敏感信息)"""
        import copy
        config = copy.deepcopy(self.config)

        # 隐藏API密钥(仅用于显示)
        if 'openai' in config and 'api_key' in config['openai']:
            if config['openai']['api_key'] and config['openai']['api_key'] != '****':
                # 保存真实的key,但标记需要隐藏
                config['openai']['_api_key_hidden'] = config['openai']['api_key']
                config['openai']['api_key'] = '****'

        # 隐藏MCP服务器的custom_header
        if 'mcp_servers' in config:
            for server in config['mcp_servers']:
                if 'custom_header' in server and server['custom_header'] and server['custom_header'] != '****':
                    server['_custom_header_hidden'] = server['custom_header']
                    server['custom_header'] = '****'

        # 隐藏生图工具的API密钥
        if 'image_generation' in config:
            if 'api_key' in config['image_generation'] and config['image_generation']['api_key'] and config['image_generation']['api_key'] != '****':
                config['image_generation']['_api_key_hidden'] = config['image_generation']['api_key']
                config['image_generation']['api_key'] = '****'

        # 隐藏豆包生图的API密钥
        if 'doubao_image' in config:
            if 'api_key' in config['doubao_image'] and config['doubao_image']['api_key'] and config['doubao_image']['api_key'] != '****':
                config['doubao_image']['_api_key_hidden'] = config['doubao_image']['api_key']
                config['doubao_image']['api_key'] = '****'

        return config

    def test_connection(self) -> Dict[str, Any]:
        """测试AI服务连接"""
        return {
            'pydantic_available': PYDANTIC_AVAILABLE,
            'config_loaded': self.config.get('enabled', False),
            'agent_initialized': self.agent is not None,
            'mcp_servers': [
                {
                    'name': s['name'],
                    'url': s['url'],
                    'connected': s.get('enabled', False)
                }
                for s in self.config.get('mcp_servers', [])
            ]
        }


# 全局单例
_chat_service = None

def get_chat_service() -> ChatService:
    """获取聊天服务单例"""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
