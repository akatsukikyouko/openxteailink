#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片生成工具 - 支持Z-Image和字节豆包
参考LinkSlideAI实现
"""

import json
import logging
import os
import time
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image

logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_PATH = Path(__file__).parent.parent / "config" / "ai_config.json"


def load_config():
    """加载AI配置"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        raise


def generate_with_zimage(prompt: str, size: str = "1600x900") -> str:
    """
    使用Z-Image生成图片

    Args:
        prompt: 图片生成提示词
        size: 图片尺寸，默认1600x900

    Returns:
        图片URL
    """
    config = load_config()
    img_config = config.get('image_generation', {})

    api_key = img_config.get('api_key')
    base_url = img_config.get('base_url', 'https://api-inference.modelscope.cn/')
    model_id = img_config.get('model_id', 'Tongyi-MAI/Z-Image-Turbo')

    if not api_key:
        raise ValueError("Z-Image API Key未配置")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-ModelScope-Async-Mode": "true"
    }

    logger.info(f"使用Z-Image生成图片: {model_id}")

    # 发起生成请求
    payload = {
        "model": model_id,
        "prompt": prompt,
        "size": size
    }

    response = requests.post(
        f"{base_url}v1/images/generations",
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(f"Z-Image API错误: HTTP {response.status_code} - {response.text}")

    # 获取Task ID
    try:
        task_id = response.json()["task_id"]
    except Exception as e:
        logger.error(f"解析Z-Image响应失败: {response.text}")
        raise e

    logger.info(f"Z-Image任务ID: {task_id}, 等待结果...")

    # 轮询结果（最多等待90秒）
    for i in range(45):
        time.sleep(2)

        try:
            result = requests.get(
                f"{base_url}v1/tasks/{task_id}",
                headers={**headers, "X-ModelScope-Task-Type": "image_generation"},
                timeout=10
            )

            if result.status_code != 200:
                logger.warning(f"轮询Z-Image状态 {result.status_code}, 重试...")
                continue

            data = result.json()
            status = data.get("task_status")

            if status == "SUCCEED":
                img_url = data["output_images"][0]
                logger.info(f"Z-Image生成成功: {img_url}")
                return img_url

            elif status == "FAILED":
                error_msg = data.get("message", "Unknown error")
                logger.error(f"Z-Image任务失败: {error_msg}")
                raise Exception(f"Z-Image生成失败: {error_msg}")

        except requests.exceptions.RequestException as e:
            logger.warning(f"轮询Z-Image网络错误: {e}")
            continue

    raise Exception("Z-Image生成超时")


def generate_with_doubao(prompt: str, size: str = "2560x1440") -> str:
    """
    使用字节豆包生成图片

    Args:
        prompt: 图片生成提示词
        size: 图片尺寸，默认2560x1440

    Returns:
        图片URL
    """
    try:
        from volcenginesdkarkruntime import Ark
    except ImportError:
        raise ImportError("未安装volcengine-python-sdk，请运行: pip install 'volcengine-python-sdk[ark]'")

    config = load_config()
    doubao_config = config.get('doubao_image', {})

    api_key = doubao_config.get('api_key')
    base_url = doubao_config.get('base_url', 'https://ark.cn-beijing.volces.com/api/v3')
    model_id = doubao_config.get('model_id', 'doubao-seedream-4-5-251128')

    if not api_key:
        raise ValueError("豆包API Key未配置")

    logger.info(f"使用豆包生成图片: {model_id}")

    client = Ark(
        base_url=base_url,
        api_key=api_key,
    )

    # 发起生成请求
    images_response = client.images.generate(
        model=model_id,
        prompt=prompt,
        size=size,
        response_format="url",
        watermark=False
    )

    if not images_response.data or not images_response.data[0].url:
        raise Exception("豆包API未返回图片URL")

    img_url = images_response.data[0].url
    logger.info(f"豆包生成成功: {img_url}")
    return img_url


def save_image(image_url: str, session_id: str, slide_index: int) -> str:
    """
    下载并保存图片到本地

    Args:
        image_url: 图片URL
        session_id: 会话ID
        slide_index: 幻灯片索引

    Returns:
        本地图片路径（相对路径）
    """
    # 下载图片
    img_data = requests.get(image_url, timeout=30).content

    # 保存图片
    save_dir = Path(__file__).parent.parent / "static" / "output" / session_id
    save_dir.mkdir(parents=True, exist_ok=True)

    filename = f"slide_{slide_index}.jpg"
    filepath = save_dir / filename

    image = Image.open(BytesIO(img_data))
    image.save(filepath)

    logger.info(f"图片已保存: {filepath}")

    # 返回相对路径供Web访问
    return f"/static/output/{session_id}/{filename}"


def generate_slide_image(
    prompt: str,
    slide_index: int = 1,
    session_id: str = "default",
    provider: str = "auto",
    max_retries: int = 3,
    progress_callback = None
) -> str:
    """
    生成PPT幻灯片图片（主入口函数）

    Args:
        prompt: 图片生成提示词
        slide_index: 幻灯片索引
        session_id: 会话ID
        provider: 生成提供商，可选值: "auto", "zimage", "doubao"
        max_retries: 最大重试次数
        progress_callback: 进度回调函数，签名为 callback(status, message, data=None)

    Returns:
        本地图片路径（相对路径）
    """
    config = load_config()
    img_config = config.get('image_generation', {})

    def report_progress(status, message, data=None):
        """报告进度"""
        if progress_callback:
            progress_callback(status, message, data)
        logger.info(f"[{status}] {message}")

    # 自动选择提供商
    if provider == "auto":
        # 使用配置文件中的默认提供商
        default_provider = config.get('default_image_provider', 'auto')

        if default_provider != 'auto':
            provider = default_provider
        # 否则根据配置自动选择：优先豆包
        elif config.get('doubao_image', {}).get('api_key'):
            provider = "doubao"
        elif img_config.get('api_key'):
            provider = "zimage"
        else:
            raise ValueError("未配置任何图片生成API，请配置image_generation或doubao_image")

    # 重试循环
    for attempt in range(1, max_retries + 1):
        try:
            report_progress('start', f'开始生图任务 [{provider}] 幻灯片 {slide_index}')
            report_progress('progress', f'尝试 {attempt}/{max_retries} 提交生成请求...')

            # 根据提供商调用不同的生成函数
            if provider == "zimage":
                report_progress('generating', '正在使用模搭生成图片...')
                image_url = generate_with_zimage(prompt)
            elif provider == "doubao":
                report_progress('generating', '正在使用字节豆包生成图片...')
                image_url = generate_with_doubao(prompt)
            else:
                raise ValueError(f"不支持的提供商: {provider}")

            report_progress('downloading', '图片生成成功，正在下载...')

            # 保存图片到本地
            local_path = save_image(image_url, session_id, slide_index)

            report_progress('complete', f'✅ 生图完成: {local_path}', {'image_path': local_path})
            return local_path

        except Exception as e:
            logger.error(f"生图失败 (尝试 {attempt}/{max_retries}): {e}")
            report_progress('error', f'生图失败: {str(e)}')
            if attempt < max_retries:
                report_progress('retry', f'等待3秒后重试...')
                time.sleep(3)
            else:
                report_progress('failed', f'❌ 生图失败: 已重试{max_retries}次')
                raise Exception(f"生图失败: 已重试{max_retries}次，最后错误: {str(e)}")

    return "Error: Unknown failure"


# 兼容旧接口
def generate_slide_image_tool(prompt: str, slide_index: int, session_id: str, max_retries: int = 3) -> str:
    """
    兼容LinkSlideAI的旧接口

    Args:
        prompt: 图片生成提示词
        slide_index: 幻灯片索引
        session_id: 会话ID
        max_retries: 最大重试次数

    Returns:
        本地图片路径（相对路径）
    """
    return generate_slide_image(prompt, slide_index, session_id, max_retries=max_retries)
