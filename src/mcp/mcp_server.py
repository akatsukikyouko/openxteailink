#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XTEAILINK MCP服务器
"""

import json
import uuid
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import logging

from fastmcp import FastMCP

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/mcp_server.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 创建 FastMCP 服务器实例
mcp = FastMCP("xteailink-mcp-server", stateless_http=True)

# 配置路径
QUEUE_FILE = Path("data/queue.json")
NOTES_DIR = Path("data/notes")

def ensure_directories():
    """确保必要的目录存在"""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

def load_queue() -> list:
    """加载传书队列"""
    if not QUEUE_FILE.exists():
        return []
    
    try:
        with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载队列失败: {e}")
        return []

def save_queue(queue: list):
    """保存传书队列"""
    try:
        with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存队列失败: {e}")

@mcp.tool()
def upload_content(content: str, filename: str = None) -> Dict[str, Any]:
    """
    将内容转换为txt文件，传到阅星曈电子纸。
    
    Args:
        content: 要传送的内容，支持纯文本，不建议用markdown格式。
        filename: 可选的文件名（不含扩展名），如果不提供则自动生成
    
    Returns:
        包含操作结果的字典
    """
    try:
        ensure_directories()
        
        # 生成文件名
        if not filename:
            timestamp = datetime.now().strftime('%m%d_%H%M')
            file_id = str(uuid.uuid4())[:8]
            filename = f"note_{timestamp}_{file_id}"
        
        # 清理文件名，移除不安全字符
        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_')).strip()
        if not filename:
            filename = f"note_{datetime.now().strftime('%m%d_%H%M')}_{str(uuid.uuid4())[:8]}"
        
        # 确保文件名以.txt结尾
        if not filename.endswith('.txt'):
            filename += '.txt'
        
        # 创建文件路径
        file_path = NOTES_DIR / filename
        
        # 写入内容
        with open(file_path, 'w', encoding='utf-8') as f:
            # 添加元数据头部
            header = f"""# 笔记文件
创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
文件名: {filename}
{'=' * 50}

"""
            f.write(header + content)
        
        # 获取文件大小
        file_size = file_path.stat().st_size
        
        # 生成唯一ID
        file_id = str(uuid.uuid4())
        
        # 创建队列项目
        queue_item = {
            'id': file_id,
            'original_name': filename,
            'name': filename,
            'path': str(file_path),
            'size': file_size,
            'status': 'pending',
            'upload_time': datetime.now().isoformat(),
            'message': '',
            'target_dir': '/XTEAILINK/notes/'  # 指定传送到notes目录
        }
        
        # 添加到队列
        queue = load_queue()
        queue.append(queue_item)
        save_queue(queue)
        
        logger.info(f"内容已保存并加入传书队列: {filename} (ID: {file_id})")
        
        return {
            'success': True,
            'message': '内容已保存并加入传书队列，将传送到 /XTEAILINK/notes/',
            'file_id': file_id,
            'filename': filename,
            'file_path': str(file_path),
            'file_size': file_size,
            'target_directory': '/XTEAILINK/notes/',
            'queue_position': len(queue),
            'status': 'pending'
        }
        
    except Exception as e:
        logger.error(f"处理内容失败: {e}")
        return {
            'success': False,
            'message': f'处理内容失败: {str(e)}',
            'error': str(e)
        }

if __name__ == "__main__":
    logger.info("启动XTEAILINK MCP服务器 (简化版)")
    
    # 确保目录存在
    ensure_directories()
    
    # 运行服务器
    mcp.run(
        transport="streamable-http", 
        host="0.0.0.0", 
        port=8099, 
        path="/mcp"
    )
