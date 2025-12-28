#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI聊天服务 - 基于pydantic-ai
参考LinkSlideAI的实现方式
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

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
                'api_key': '',
                'enabled': False
            }
        ],
        'image_generation': {
            'enabled': False,
            'tool': 'internal'
        }
    }

    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
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
                        mcp_server = MCPServerStreamableHTTP(
                            url=mcp_config['url'],
                            headers={"Authorization": mcp_config.get('api_key', '')}
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
        prompt = f"""你是一个智能助手,帮助用户完成各种任务。

当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

主要功能:
1. 聊天对话: 回答用户的各种问题
2. 内容创作: 帮助用户撰写文章、生成内容
3. 信息整理: 总结和整理用户提供的信息
4. 文件管理: 可以使用upload_content工具将内容传送到电子纸设备

工具使用说明:
- 如果启用了MCP服务器,可以使用search工具进行联网搜索
- 使用upload_content工具可以将文本内容保存并传送到电子纸
- 请用简洁友好的方式回复用户

注意事项:
- 回复要简洁明了,不要过于冗长
- 如果用户需要保存内容,主动建议使用upload_content工具
- 保持专业且友好的语气"""

        return prompt

    def _register_tools(self):
        """注册自定义工具"""

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
                # 导入MCP工具
                import sys
                from pathlib import Path as PathLib
                import uuid

                # 生成文件名
                if not filename:
                    timestamp = datetime.now().strftime('%m%d_%H%M')
                    file_id = str(uuid.uuid4())[:8]
                    filename = f"note_{timestamp}_{file_id}"

                # 清理文件名
                filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_')).strip()
                if not filename:
                    filename = f"note_{datetime.now().strftime('%m%d_%H%M')}_{str(uuid.uuid4())[:8]}"

                if not filename.endswith('.txt'):
                    filename += '.txt'

                # 保存文件
                notes_dir = PathLib("data/notes")
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
                from pathlib import Path as PathLib2
                import json

                queue_file = PathLib2("data/queue.json")
                queue = []
                if queue_file.exists():
                    with open(queue_file, 'r', encoding='utf-8') as f:
                        queue = json.load(f)

                file_size = file_path.stat().st_size
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

        try:
            # 运行agent - 参考LinkSlideAI的用法
            result = self.agent.run(message, deps=self.deps)

            # 提取回复文本
            response_text = result.data

            return {
                'success': True,
                'message': str(response_text)
            }

        except Exception as e:
            logger.error(f"聊天失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'message': f'处理失败: {str(e)}'
            }

    def update_config(self, new_config: Dict) -> bool:
        """更新配置并重新初始化"""
        try:
            # 保存配置
            config_path = Path("config/ai_config.json")
            config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, ensure_ascii=False, indent=2)

            # 重新加载配置
            self.config = new_config

            # 重新初始化agent
            if new_config.get('enabled', False):
                self.initialize_agent()
            else:
                self.agent = None

            return True

        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return False

    def get_config(self) -> Dict:
        """获取当前配置(隐藏敏感信息)"""
        config = json.loads(json.dumps(self.config))  # 深拷贝

        # 隐藏API密钥
        if 'openai' in config and 'api_key' in config['openai']:
            if config['openai']['api_key']:
                config['openai']['api_key'] = '****'

        # 隐藏MCP服务器的API密钥
        if 'mcp_servers' in config:
            for server in config['mcp_servers']:
                if 'api_key' in server and server['api_key']:
                    server['api_key'] = '****'

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
