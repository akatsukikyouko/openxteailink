#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的AI聊天服务
直接使用OpenAI API,不依赖pydantic-ai
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

class SimpleChatService:
    def __init__(self, config_path: str = "config/ai_config.json"):
        self.config_path = Path(config_path)
        self.config = self.load_config()
        self.client = None

        if OPENAI_AVAILABLE and self.config.get('enabled', False):
            self.initialize_client()

    def load_config(self) -> Dict:
        """加载AI配置"""
        default_config = {
            'enabled': False,
            'openai': {
                'base_url': 'http://localhost:11434/v1',
                'api_key': 'sk-test',
                'model': 'qwen2.5:latest'
            },
            'mcp_servers': [],
            'image_generation': {
                'enabled': False,
                'tool': 'internal'
            }
        }

        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
            except Exception as e:
                logger.error(f"加载AI配置失败: {e}")

        return default_config

    def save_config(self) -> bool:
        """保存AI配置"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存AI配置失败: {e}")
            return False

    def update_config(self, new_config: Dict) -> bool:
        """更新配置"""
        try:
            self.config.update(new_config)
            if self.save_config():
                self.initialize_client()
                return True
            return False
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return False

    def initialize_client(self):
        """初始化OpenAI客户端"""
        if not OPENAI_AVAILABLE:
            logger.warning("openai库未安装")
            return

        try:
            openai_config = self.config.get('openai', {})

            self.client = openai.OpenAI(
                base_url=openai_config.get('base_url', 'http://localhost:11434/v1'),
                api_key=openai_config.get('api_key', 'sk-test')
            )

            logger.info("OpenAI客户端初始化成功")

        except Exception as e:
            logger.error(f"OpenAI客户端初始化失败: {e}")
            self.client = None

    async def chat(self, message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        聊天接口
        """
        if not OPENAI_AVAILABLE:
            return {
                'success': False,
                'error': 'openai库未安装',
                'message': '请先安装: pip install openai'
            }

        if not self.client:
            return {
                'success': False,
                'error': 'OpenAI客户端未初始化',
                'message': 'AI功能未正确配置'
            }

        try:
            # 构建消息历史
            messages = []

            # 添加系统提示
            system_prompt = self._build_system_prompt()
            messages.append({"role": "system", "content": system_prompt})

            # 添加历史对话
            if conversation_history:
                for item in conversation_history:
                    messages.append({
                        "role": item.get('role', 'user'),
                        "content": item.get('content', '')
                    })

            # 添加当前消息
            messages.append({"role": "user", "content": message})

            # 调用API
            openai_config = self.config.get('openai', {})
            model = openai_config.get('model', 'qwen2.5:latest')

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )

            # 提取回复
            assistant_message = response.choices[0].message.content

            return {
                'success': True,
                'message': assistant_message
            }

        except Exception as e:
            logger.error(f"聊天失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'处理失败: {str(e)}'
            }

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        prompt = """你是一个智能助手,帮助用户完成各种任务。

当前时间:{current_time}

主要功能:
1. 聊天对话:回答用户的各种问题
2. 内容创作:帮助用户撰写文章、生成内容
3. 信息整理:总结和整理用户提供的信息
4. 文件管理:可以将内容传送到电子纸设备

请用简洁友好的方式回复用户。如果用户需要保存内容,可以告知用户内容会被传送到电子纸设备。""".format(
            current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )

        return prompt

    def get_config(self) -> Dict:
        """获取当前配置(隐藏敏感信息)"""
        config = self.config.copy()

        # 隐藏API密钥
        if 'openai' in config and 'api_key' in config['openai']:
            config['openai']['api_key'] = '****' if config['openai']['api_key'] else ''

        # 隐藏MCP服务器的API密钥
        if 'mcp_servers' in config:
            for server in config['mcp_servers']:
                if 'api_key' in server:
                    server['api_key'] = '****' if server['api_key'] else ''

        return config

    def test_connection(self) -> Dict[str, Any]:
        """测试AI服务连接"""
        result = {
            'openai_available': OPENAI_AVAILABLE,
            'config_loaded': self.config.get('enabled', False),
            'client_initialized': self.client is not None,
            'mcp_servers': []
        }

        # 测试MCP服务器连接(占位)
        for mcp_config in self.config.get('mcp_servers', []):
            if mcp_config.get('enabled', True):
                result['mcp_servers'].append({
                    'name': mcp_config['name'],
                    'url': mcp_config['url'],
                    'connected': False  # 简化版不支持MCP
                })

        return result

# 全局聊天服务实例
chat_service = None

def get_chat_service() -> SimpleChatService:
    """获取聊天服务单例"""
    global chat_service
    if chat_service is None:
        chat_service = SimpleChatService()
    return chat_service
