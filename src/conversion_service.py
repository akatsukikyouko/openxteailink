#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件格式转换服务 (纯Python版本)
支持将EPUB、MOBI、PDF等格式转换为电子纸用的XTC格式
仅使用Python库，无需外部工具
"""

import os
import sys
import tempfile
import shutil
import logging
import struct
import hashlib
from pathlib import Path
from typing import Optional, Tuple, List

from PIL import Image
import fitz  # PyMuPDF
import numpy as np
import zhconv

logger = logging.getLogger(__name__)


class ConversionService:
    """文件格式转换服务 (纯Python实现)"""

    def __init__(self):
        """初始化转换服务"""
        # 获取工具目录路径
        current_dir = Path(__file__).parent.parent
        self.tool_dir = current_dir / "tool" / "epub2xtc-main"
        self.png2xtc_script = self.tool_dir / "png2xtc.py"

        # 检查工具是否存在
        if not self.png2xtc_script.exists():
            logger.warning(f"png2xtc工具不存在: {self.png2xtc_script}，将使用内置实现")

    def convert_to_xtc(self, file_path: Path, output_path: Optional[Path] = None, format_mode: str = "xtg") -> Tuple[bool, str]:
        """
        将文件转换为XTC格式

        Args:
            file_path: 输入文件路径
            output_path: 输出文件路径（可选，默认与输入文件同目录）
            format_mode: 格式模式，"xtg"(1位单色) 或 "xth"(4级灰度)

        Returns:
            Tuple[成功状态, 消息或输出文件路径]
        """
        try:
            file_ext = file_path.suffix.lower()

            # 如果没有指定输出路径，使用项目根目录下的temp_convert目录
            if output_path is None:
                # 获取项目根目录
                current_dir = Path(__file__).parent.parent
                temp_convert_dir = current_dir / "temp_convert"
                temp_convert_dir.mkdir(exist_ok=True)

                # 生成输出文件名
                output_filename = file_path.stem + ".xtc"
                output_path = temp_convert_dir / output_filename

            # 根据文件类型选择转换方法
            if file_ext == '.epub':
                return self.convert_epub_to_xtc(file_path, output_path, format_mode)
            elif file_ext == '.mobi':
                return self.convert_mobi_to_xtc(file_path, output_path, format_mode)
            elif file_ext == '.pdf':
                return self.convert_pdf_to_xtc(file_path, output_path, format_mode)
            elif file_ext == '.png':
                return self.convert_png_to_xtc(file_path, output_path, format_mode)
            else:
                return False, f"不支持的文件格式: {file_ext}"

        except Exception as e:
            logger.error(f"文件转换失败 {file_path}: {e}")
            return False, f"转换失败: {str(e)}"

    def convert_epub_to_xtc(self, epub_path: Path, output_path: Optional[Path] = None, format_mode: str = "xtg") -> Tuple[bool, str]:
        """
        将EPUB转换为XTC

        流程: EPUB → 提取图片 → XTC
        使用纯Python库实现

        Args:
            epub_path: EPUB文件路径
            output_path: 输出XTC文件路径
            format_mode: 格式模式，"xtg"(1位单色) 或 "xth"(4级灰度)
        """
        temp_dir = None
        try:
            logger.info(f"开始转换EPUB: {epub_path.name} (模式: {format_mode.upper()})")

            # 如果没有指定输出路径，生成默认路径
            if output_path is None:
                current_dir = Path(__file__).parent.parent
                temp_convert_dir = current_dir / "temp_convert"
                temp_convert_dir.mkdir(exist_ok=True)
                output_path = temp_convert_dir / (epub_path.stem + ".xtc")

            # 创建临时目录用于中间文件
            temp_dir = Path(tempfile.mkdtemp(prefix="epub2xtc_"))

            # 使用纯Python方法提取EPUB内容并渲染为图片
            temp_png_dir = temp_dir / "png_pages"
            temp_png_dir.mkdir()

            if not self.convert_epub_to_png_pure(epub_path, temp_png_dir):
                return False, "EPUB转PNG失败"

            # PNG → XTC (使用内置实现或png2xtc.py)
            logger.info("步骤2: PNG → XTC")
            if not self.convert_png_folder_to_xtc(temp_png_dir, output_path, format_mode):
                return False, "PNG转XTC失败"

            logger.info(f"EPUB转换成功: {epub_path.name} -> {output_path.name} ({format_mode.upper()})")
            return True, str(output_path)

        except Exception as e:
            logger.error(f"EPUB转换失败: {e}")
            return False, f"转换失败: {str(e)}"
        finally:
            # 清理临时文件
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug(f"已清理临时目录: {temp_dir}")
                except Exception as e:
                    logger.warning(f"清理临时目录失败: {e}")

    def convert_mobi_to_xtc(self, mobi_path: Path, output_path: Optional[Path] = None, format_mode: str = "xtg") -> Tuple[bool, str]:
        """
        将MOBI转换为XTC

        流程: MOBI → EPUB → PNG → XTC
        使用纯Python库实现

        Args:
            mobi_path: MOBI文件路径
            output_path: 输出XTC文件路径
            format_mode: 格式模式，"xtg"(1位单色) 或 "xth"(4级灰度)
        """
        temp_dir = None
        try:
            logger.info(f"开始转换MOBI: {mobi_path.name} (模式: {format_mode.upper()})")

            # 如果没有指定输出路径，生成默认路径
            if output_path is None:
                current_dir = Path(__file__).parent.parent
                temp_convert_dir = current_dir / "temp_convert"
                temp_convert_dir.mkdir(exist_ok=True)
                output_path = temp_convert_dir / (mobi_path.stem + ".xtc")

            # 创建临时目录用于中间文件
            temp_dir = Path(tempfile.mkdtemp(prefix="mobi2xtc_"))

            # 方法1: 使用mobi库的kindleunpack解包MOBI
            try:
                from mobi import kindleunpack
                from ebooklib import epub

                logger.info("使用mobi库读取MOBI文件")

                # 创建临时EPUB文件
                temp_epub_path = temp_dir / "converted.epub"

                # 解包MOBI文件
                unpack_dir = temp_dir / "unpacked"
                unpack_dir.mkdir(exist_ok=True)

                logger.info(f"解包MOBI到: {unpack_dir}")

                # 使用kindleunpack解包
                kindleunpack.unpackBook(str(mobi_path), str(unpack_dir))

                logger.info(f"MOBI解包成功")

                # 查找解包后的HTML文件
                html_files = list(unpack_dir.rglob("*.html")) + list(unpack_dir.rglob("*.htm"))

                if not html_files:
                    # 尝试查找其他文本文件
                    text_files = list(unpack_dir.rglob("*.txt"))
                    if text_files:
                        html_files = text_files
                    else:
                        raise FileNotFoundError("解包后未找到HTML或文本文件")

                logger.info(f"找到 {len(html_files)} 个HTML文件")

                # 查找所有图片文件
                image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}
                image_files = []
                for ext in image_extensions:
                    image_files.extend(unpack_dir.rglob(f"*{ext}"))
                    image_files.extend(unpack_dir.rglob(f"*{ext.upper()}"))

                logger.info(f"找到 {len(image_files)} 个图片文件")

                # 创建EPUB书籍
                book = epub.EpubBook()
                book.set_identifier('mobi_' + mobi_path.stem)
                book.set_title(mobi_path.stem)
                book.set_language('zh-CN')

                # 添加所有图片到EPUB
                for idx, img_file in enumerate(image_files):
                    try:
                        with open(img_file, 'rb') as f:
                            img_data = f.read()

                        # 创建图片项
                        img_item = epub.EpubImage()
                        # 使用相对路径保持原始结构
                        img_name = img_file.relative_to(unpack_dir)
                        img_item.file_name = str(img_name).replace('\\', '/')
                        img_item.content = img_data
                        book.add_item(img_item)
                        logger.info(f"添加图片: {img_item.file_name} ({len(img_data)} bytes)")
                    except Exception as e:
                        logger.warning(f"添加图片失败 {img_file.name}: {e}")

                # 添加找到的HTML文件作为章节
                chapters = []
                for idx, html_file in enumerate(html_files):
                    try:
                        with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()

                        # 获取章节标题
                        chapter_title = html_file.stem
                        chapter = epub.EpubHtml(
                            title=chapter_title,
                            file_name=f'chap{idx:03d}.xhtml',
                            content=content
                        )
                        book.add_item(chapter)
                        chapters.append(chapter)
                        logger.info(f"添加章节: {chapter_title} ({len(content)} bytes)")
                    except Exception as e:
                        logger.warning(f"读取文件失败 {html_file.name}: {e}")

                if not chapters:
                    raise ValueError("没有成功提取任何章节")

                # 设置目录
                book.toc = tuple(chapters)
                book.add_item(epub.EpubNcx())
                book.add_item(epub.EpubNav())
                book.spine = ['nav'] + chapters

                # 写入EPUB
                epub.write_epub(str(temp_epub_path), book, {})
                logger.info(f"使用mobi库构建EPUB成功: {temp_epub_path}")

                return self.convert_epub_to_xtc(temp_epub_path, output_path, format_mode)

            except ImportError as e:
                logger.warning(f"mobi库未安装或导入失败: {e}，尝试使用备用方法")
            except Exception as e:
                logger.warning(f"mobi库转换失败: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                # 继续尝试备用方法

                # 方法2: 使用ebooklib (如果支持MOBI)
                try:
                    from ebooklib import epub

                    logger.info("尝试使用ebooklib直接读取MOBI")
                    # ebooklib 可能不支持MOBI，这个可能失败
                    book = epub.read_epub(str(mobi_path))
                    temp_epub_path = temp_dir / "converted.epub"

                    # 如果成功，重新保存为EPUB
                    epub.write_epub(str(temp_epub_path), book, {})

                    return self.convert_epub_to_xtc(temp_epub_path, output_path, format_mode)

                except Exception as e:
                    logger.error(f"ebooklib读取MOBI失败: {e}")

                    # 方法3: 使用mobi2epub的外部工具（如果可用）
                    logger.info("尝试使用系统工具转换MOBI")

                    # 尝试使用calibre的ebook-convert
                    import subprocess

                    temp_epub_path = temp_dir / "converted.epub"

                    try:
                        # 尝试调用ebook-convert（calibre工具）
                        result = subprocess.run(
                            ['ebook-convert', str(mobi_path), str(temp_epub_path)],
                            capture_output=True,
                            text=True,
                            timeout=60
                        )

                        if result.returncode == 0 and temp_epub_path.exists():
                            logger.info("使用ebook-convert转换成功")
                            return self.convert_epub_to_xtc(temp_epub_path, output_path, format_mode)
                        else:
                            logger.error(f"ebook-convert失败: {result.stderr}")

                    except FileNotFoundError:
                        logger.warning("未找到ebook-convert工具")
                    except subprocess.TimeoutExpired:
                        logger.error("ebook-convert超时")
                    except Exception as e:
                        logger.error(f"ebook-convert执行失败: {e}")

                    # 所有方法都失败
                    return False, "MOBI转换失败：请安装pymobi库（pip install pymobi）或Calibre工具"

        except Exception as e:
            logger.error(f"MOBI转换失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, f"转换失败: {str(e)}"
        finally:
            # 清理临时文件
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug(f"已清理临时目录: {temp_dir}")
                except Exception as e:
                    logger.warning(f"清理临时目录失败: {e}")

    def _wrap_text(self, text: str, font, max_width: int, draw) -> list:
        """
        文本自动换行处理

        Args:
            text: 要换行的文本
            font: 字体对象
            max_width: 最大宽度（像素）
            draw: ImageDraw对象

        Returns:
            换行后的文本列表
        """
        words = list(text)  # 中文按字符分割
        lines = []
        current_line = ""

        for char in words:
            test_line = current_line + char
            # 获取文本边界框
            bbox = draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]

            if text_width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char

        if current_line:
            lines.append(current_line)

        return lines

    def _render_html_content(self, soup, img, draw, y_position, images_dict,
                            font_large, font_normal, margin, line_height,
                            page_width, page_height, output_dir, page_num):
        """
        渲染HTML内容，支持文本和图片

        Args:
            soup: BeautifulSoup对象
            img: PIL Image对象
            draw: ImageDraw对象
            y_position: 当前Y坐标
            images_dict: 图片字典 {filename: content}
            ... 其他参数
        """
        from PIL import Image as PILImage, ImageDraw, ImageFont
        import io

        def create_new_page():
            """创建新页面"""
            nonlocal img, draw, y_position, page_num
            # 保存当前页面
            page_path = output_dir / f"page-{page_num:04d}.png"
            img.save(page_path)
            page_num += 1

            # 创建新页面
            img = PILImage.new('RGB', (page_width, page_height), 'white')
            draw = ImageDraw.Draw(img)
            y_position = margin
            return img, draw, y_position, page_num

        # 遍历所有元素(包括嵌套的)
        # 不再限制递归深度,以找到所有图片和文本
        body = soup.find('body')
        if body:
            # 获取body内的所有元素
            elements = body.find_all(['img', 'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br'])
        else:
            # 如果没有body标签,使用整个文档
            elements = soup.find_all(['img', 'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br'])

        for element in elements:
            # 处理图片
            if element.name == 'img':
                try:
                    # 获取图片src
                    src = element.get('src', '')
                    if not src:
                        continue

                    logger.debug(f"处理img标签, src={src}")

                    # 处理相对路径
                    if src.startswith('../'):
                        src = src[3:]
                    elif src.startswith('../..'):
                        src = src[6:]

                    # 移除开头的斜杠
                    src = src.lstrip('/')

                    logger.debug(f"标准化后的src={src}")

                    # 在images_dict中查找图片
                    img_content = None
                    matched_key = None
                    for img_key in images_dict:
                        # 尝试多种匹配方式
                        if src == img_key:
                            img_content = images_dict[img_key]
                            matched_key = img_key
                            break
                        elif img_key.endswith(src):
                            img_content = images_dict[img_key]
                            matched_key = img_key
                            break
                        elif src in img_key:
                            img_content = images_dict[img_key]
                            matched_key = img_key
                            break

                    if img_content:
                        logger.info(f"找到图片: src='{src}' -> key='{matched_key}'")
                    else:
                        logger.warning(f"未找到图片: src='{src}', 可用的keys: {list(images_dict.keys())[:3]}")
                        continue

                    # 加载图片
                    epub_img = PILImage.open(io.BytesIO(img_content))
                    orig_width, orig_height = epub_img.size

                    # 计算图片最大可用尺寸（保持宽高比）
                    img_width_max = page_width - 2 * margin
                    img_height_max = page_height - y_position - margin

                    # 如果可用高度太小，创建新页面
                    if img_height_max < page_height // 3:
                        img, draw, y_position, page_num = create_new_page()
                        img_height_max = page_height - y_position - margin

                    # 计算保持宽高比的缩放
                    orig_ratio = orig_width / orig_height
                    max_ratio = img_width_max / img_height_max

                    if orig_ratio > max_ratio:
                        # 图片更宽，以宽度为准
                        new_width = img_width_max
                        new_height = int(img_width_max / orig_ratio)
                    else:
                        # 图片更高，以高度为准
                        new_height = img_height_max
                        new_width = int(img_height_max * orig_ratio)

                    # 调整图片大小（使用LANCZOS重采样，适合文字）
                    epub_img = epub_img.resize((new_width, new_height), PILImage.Resampling.LANCZOS)

                    # 转换为RGB（如果是RGBA）
                    if epub_img.mode == 'RGBA':
                        # 创建白色背景
                        background = PILImage.new('RGB', epub_img.size, 'white')
                        background.paste(epub_img, mask=epub_img.split()[3])  # 使用alpha通道作为mask
                        epub_img = background
                    elif epub_img.mode != 'RGB':
                        epub_img = epub_img.convert('RGB')

                    # 应用电子墨水屏图像增强
                    epub_img = self._enhance_for_eink(epub_img)

                    # 检查是否需要新页面
                    if y_position + new_height > page_height - margin:
                        img, draw, y_position, page_num = create_new_page()

                    # 计算图片位置（居中）
                    x_position = (page_width - new_width) // 2

                    # 粘贴图片
                    img.paste(epub_img, (x_position, y_position))
                    y_position += new_height + 10  # 图片后增加间距

                    logger.info(f"渲染图片: {orig_width}x{orig_height} -> {new_width}x{new_height}, 位置: y={y_position - new_height - 10}")

                except Exception as e:
                    logger.error(f"渲染图片失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # 处理文本内容（p, div, h1-h6等）
            elif element.name in ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                # 获取元素文本
                text = element.get_text().strip()
                if text:
                    # 将繁体中文转换为简体中文
                    text = zhconv.convert(text, 'zh-cn')
                    # 确定字体
                    if element.name.startswith('h'):
                        current_font = font_large
                    else:
                        current_font = font_normal

                    # 自动换行处理
                    wrapped_lines = self._wrap_text(text, current_font, page_width - 2 * margin, draw)

                    for wrapped_line in wrapped_lines:
                        # 如果页面满了，创建新页面
                        if y_position > page_height - margin - line_height:
                            img, draw, y_position, page_num = create_new_page()

                        # 绘制文本行
                        draw.text((margin, y_position), wrapped_line, font=current_font, fill='black')
                        y_position += line_height

                    # 段落后增加间距
                    y_position += line_height // 2

            # 处理换行
            elif element.name == 'br':
                y_position += line_height // 2

        return img, draw, y_position, page_num

    def convert_epub_to_png_pure(self, epub_path: Path, output_dir: Path) -> bool:
        """
        使用纯Python库将EPUB转换为PNG
        实现原理：解析EPUB，使用ebooklib提取内容，渲染为图片
        支持图片提取和渲染
        """
        try:
            import ebooklib
            from ebooklib import epub
            from bs4 import BeautifulSoup
            from PIL import Image, ImageDraw, ImageFont
            import io

            logger.info("使用纯Python方法转换EPUB")

            # 读取EPUB文件
            book = epub.read_epub(str(epub_path))

            # 获取所有项目
            items = list(book.get_items())
            logger.info(f"EPUB包含 {len(items)} 个项目")

            # 提取所有图片到字典中
            images_dict = {}
            for item in items:
                if isinstance(item, ebooklib.epub.EpubImage):
                    try:
                        img_content = item.get_content()
                        img_name = item.get_name()
                        images_dict[img_name] = img_content
                        logger.info(f"提取图片: {img_name}, 大小: {len(img_content)} bytes")
                    except Exception as e:
                        logger.warning(f"提取图片失败 {item.get_name()}: {e}")

            logger.info(f"共提取 {len(images_dict)} 张图片")

            # 创建字体 - 参考AI电子期刊的配置，使用阿里巴巴普惠体
            try:
                # 使用项目自带的阿里巴巴普惠体
                fonts_dir = Path(__file__).parent.parent / "fonts"
                font_file = fonts_dir / 'AlibabaPuHuiTi-3-75-SemiBold.ttf'

                if font_file.exists():
                    font_large = ImageFont.truetype(str(font_file), 36)  # 标题：增大到36
                    font_normal = ImageFont.truetype(str(font_file), 28)  # 正文：从16增大到28
                else:
                    # 回退到系统字体
                    font_large = ImageFont.truetype("msyh.ttc", 36)
                    font_normal = ImageFont.truetype("msyh.ttc", 28)
            except:
                # 如果找不到字体，使用默认字体
                font_large = ImageFont.load_default()
                font_normal = ImageFont.load_default()

            page_width = 480
            page_height = 800
            margin = 12  # 减小边距：从20减到12，参考AI期刊的紧凑边距
            line_height = 40  # 增大行高：从24增大到40，适应更大的字体
            page_num = 0

            # 遍历所有HTML内容
            for item in items:
                if isinstance(item, ebooklib.epub.EpubHtml):
                    chapter_name = item.get_name()
                    logger.info(f"处理章节: {chapter_name}")

                    # 解析HTML内容
                    soup = BeautifulSoup(item.get_content(), 'html.parser')

                    # 创建页面
                    img = Image.new('RGB', (page_width, page_height), 'white')
                    draw = ImageDraw.Draw(img)

                    # 文本渲染位置
                    y_position = margin

                    # 绘制标题（支持自动换行）
                    if chapter_name:
                        title = chapter_name.replace('_', ' ').title()
                        title_lines = self._wrap_text(title, font_large, page_width - 2 * margin, draw)

                        for title_line in title_lines:
                            # 检查是否需要新页面
                            if y_position > page_height - margin - line_height:
                                page_path = output_dir / f"page-{page_num:04d}.png"
                                img.save(page_path)
                                page_num += 1
                                img = Image.new('RGB', (page_width, page_height), 'white')
                                draw = ImageDraw.Draw(img)
                                y_position = margin

                            draw.text((margin, y_position), title_line, font=font_large, fill='black')
                            y_position += line_height

                        y_position += 10  # 标题后额外间距

                    # 提取并渲染内容（文本和图片）
                    img, draw, y_position, page_num = self._render_html_content(
                        soup, img, draw, y_position, images_dict,
                        font_large, font_normal, margin, line_height,
                        page_width, page_height, output_dir, page_num
                    )

                    # 保存最后一页
                    if y_position > margin:
                        page_path = output_dir / f"page-{page_num:04d}.png"
                        img.save(page_path)
                        page_num += 1

            # 检查是否生成了图片
            png_files = list(output_dir.glob("page-*.png"))
            if png_files:
                logger.info(f"使用纯Python方法生成了 {len(png_files)} 个PNG文件")
                return True
            else:
                logger.error("未生成PNG文件")
                return False

        except ImportError as e:
            logger.error(f"缺少必要的库: {e}")
            return False
        except Exception as e:
            logger.error(f"EPUB转PNG失败: {e}")
            return False

    def convert_pdf_to_xtc(self, pdf_path: Path, output_path: Optional[Path] = None, format_mode: str = "xtg") -> Tuple[bool, str]:
        """
        将PDF转换为XTC

        流程: PDF → PNG → XTC
        使用PyMuPDF (fitz) 纯Python实现

        Args:
            pdf_path: PDF文件路径
            output_path: 输出XTC文件路径
            format_mode: 格式模式，"xtg"(1位单色) 或 "xth"(4级灰度)
        """
        temp_dir = None
        try:
            logger.info(f"开始转换PDF: {pdf_path.name} (模式: {format_mode.upper()})")

            # 如果没有指定输出路径，生成默认路径
            if output_path is None:
                current_dir = Path(__file__).parent.parent
                temp_convert_dir = current_dir / "temp_convert"
                temp_convert_dir.mkdir(exist_ok=True)
                output_path = temp_convert_dir / (pdf_path.stem + ".xtc")

            # 创建临时目录用于中间文件
            temp_dir = Path(tempfile.mkdtemp(prefix="pdf2xtc_"))

            # 第一步：PDF → PNG (使用PyMuPDF)
            logger.info("步骤1: PDF → PNG")
            temp_png_dir = temp_dir / "png_pages"
            temp_png_dir.mkdir()

            if not self.convert_pdf_to_png_pure(pdf_path, temp_png_dir):
                return False, "PDF转PNG失败"

            # 第二步：PNG → XTC
            logger.info("步骤2: PNG → XTC")
            if not self.convert_png_folder_to_xtc(temp_png_dir, output_path, format_mode):
                return False, "PNG转XTC失败"

            logger.info(f"PDF转换成功: {pdf_path.name} -> {output_path.name} ({format_mode.upper()})")
            return True, str(output_path)

        except Exception as e:
            logger.error(f"PDF转换失败: {e}")
            return False, f"转换失败: {str(e)}"
        finally:
            # 清理临时文件
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug(f"已清理临时临时目录: {temp_dir}")
                except Exception as e:
                    logger.warning(f"清理临时目录失败: {e}")

    def convert_pdf_to_png_pure(self, pdf_path: Path, output_dir: Path) -> bool:
        """
        使用PyMuPDF将PDF转换为PNG（纯Python实现）
        保持PDF原始宽高比，避免文字变形
        """
        try:
            logger.info("使用PyMuPDF转换PDF（保持宽高比模式）")

            # 打开PDF
            doc = fitz.open(str(pdf_path))
            page_count = len(doc)

            logger.info(f"PDF包含 {page_count} 页")

            # 目标尺寸
            target_width, target_height = 480, 800
            target_ratio = target_width / target_height

            # 渲染每一页
            for page_num in range(page_count):
                page = doc.load_page(page_num)

                # 获取PDF页面尺寸
                rect = page.rect
                pdf_ratio = rect.width / rect.height

                # 保持宽高比，计算实际渲染尺寸
                if pdf_ratio > target_ratio:
                    # PDF页面更宽，以宽度为准
                    render_width = target_width
                    render_height = int(target_width / pdf_ratio)
                else:
                    # PDF页面更高，以高度为准
                    render_height = target_height
                    render_width = int(target_height * pdf_ratio)

                # 计算缩放比例（保持宽高比）
                zoom_x = render_width / rect.width
                zoom_y = zoom_x  # 使用相同的缩放比例保持宽高比
                mat = fitz.Matrix(zoom_x, zoom_y)

                # 渲染为像素图
                pix = page.get_pixmap(matrix=mat, dpi=None)

                # 转换为PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # 创建白色背景，居中放置渲染的图像
                background = Image.new('RGB', (target_width, target_height), 'white')

                # 计算居中位置
                paste_x = (target_width - render_width) // 2
                paste_y = (target_height - render_height) // 2

                # 居中粘贴
                background.paste(img, (paste_x, paste_y))

                # 图像增强处理
                img = self._enhance_for_eink(background)

                # 保存为PNG
                output_path = output_dir / f"page-{page_num:04d}.png"
                img.save(output_path, 'PNG')
                logger.debug(f"保存页面: {output_path}")

            doc.close()

            # 检查是否生成了PNG文件
            png_files = list(output_dir.glob("page-*.png"))
            if png_files:
                logger.info(f"生成了 {len(png_files)} 个PNG文件（已保持宽高比）")
                return True
            else:
                logger.error("未生成PNG文件")
                return False

        except Exception as e:
            logger.error(f"PDF转PNG失败: {e}")
            return False

    def resize_simple(self, img: Image.Image, target_size: tuple) -> Image.Image:
        """
        简单的图像调整，使用BOX重采样（官方推荐，适合电子纸）
        """
        target_width, target_height = target_size

        # 计算缩放比例（保持纵横比）
        img_ratio = img.width / img.height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # 图像更宽，以高度为准
            new_height = target_height
            new_width = int(new_height * img_ratio)
        else:
            # 图像更高，以宽度为准
            new_width = target_width
            new_height = int(new_width / img_ratio)

        # 使用BOX缩放（官方推荐，平衡锐利度和质量）
        img = img.resize((new_width, new_height), Image.BOX)

        # 居中裁剪
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        img = img.crop((left, top, right, bottom))

        return img

    def convert_to_grayscale_smart(self, img: Image.Image) -> Image.Image:
        """
        智能灰度转换，特别针对中文优化
        使用加权平均而不是简单平均值，保留更多笔画细节
        """
        # 先转RGB如果还不是
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # 使用加权平均转换为灰度（保留人眼敏感的细节）
        # 绿色权重最高，因为人眼对绿色最敏感
        r, g, b = img.split()
        gray = Image.merge('RGB', (
            r.point(lambda x: x * 0.299),
            g.point(lambda x: x * 0.587),
            b.point(lambda x: x * 0.114)
        ))
        gray = gray.convert('L')

        return gray

    def enhance_for_chinese(self, img: Image.Image) -> Image.Image:
        """
        针对中文文字的图像增强
        - 提高对比度使笔画更清晰
        - 二值化处理使文字更锐利
        """
        from PIL import ImageEnhance, ImageFilter

        # 增强对比度（提高到1.5倍，比之前更强）
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)

        # 轻微锐化
        img = img.filter(ImageFilter.SHARPEN)

        # 可选：使用自适应阈值进行二值化，使文字更清晰
        # 将图像调整为更接近黑白两色
        img = img.point(lambda x: 0 if x < 140 else 255)

        return img

    def _enhance_for_eink(self, img: Image.Image) -> Image.Image:
        """
        图像增强处理，专为电子纸显示优化
        轻度处理，避免文字变形和伪影

        Args:
            img: PIL Image对象

        Returns:
            增强后的PIL Image对象
        """
        from PIL import ImageEnhance, ImageFilter

        # 转换为灰度
        if img.mode != 'L':
            img = img.convert('L')

        # 轻度增强对比度（降低到1.2，避免文字变形）
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.2)

        # 轻度锐化（只应用一次）
        img = img.filter(ImageFilter.SHARPEN)

        # 优化阈值处理：更平滑的过渡，避免文字边缘生硬
        # 使用三段式阈值，保留文字细节
        img = img.point(lambda x: 0 if x < 100 else (255 if x > 200 else x))

        return img

    def resize_for_eink_large(self, img: Image.Image, target_size: tuple) -> Image.Image:
        """
        专门为电子纸小屏幕调整图像（超大字体优化版）
        适合3.5寸屏幕的中文报纸阅读
        """
        target_width, target_height = target_size

        # 确保是灰度图像
        if img.mode != 'L':
            img = img.convert('L')

        # 计算缩放比例（保持纵横比）
        img_ratio = img.width / img.height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # 图像更宽，以高度为准
            new_height = target_height
            new_width = int(new_height * img_ratio)
        else:
            # 图像更高，以宽度为准
            new_width = target_width
            new_height = int(new_width / img_ratio)

        # 使用最高质量的缩放算法
        # 使用BOX缩放（官方推荐，平衡锐利度和质量）
        img = img.resize((new_width, new_height), Image.BOX)

        # 居中裁剪
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        img = img.crop((left, top, right, bottom))

        return img

    def resize_for_eink(self, img: Image.Image, target_size: tuple) -> Image.Image:
        """
        专门为电子纸小屏幕优化的图像调整方法
        - 使用对比度增强提高文字可读性
        - 使用高质量缩放算法
        - 优化为适合3.5寸屏幕的尺寸

        Args:
            img: PIL Image对象
            target_size: 目标尺寸 (width, height)

        Returns:
            调整后的PIL Image对象
        """
        target_width, target_height = target_size

        # 转换为灰度
        img = img.convert('L')

        # 增强对比度以提高文字可读性
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.3)  # 提高30%对比度

        # 可选：轻微锐化以提高文字清晰度
        from PIL import ImageFilter
        img = img.filter(ImageFilter.SHARPEN)

        # 计算缩放比例（保持纵横比）
        img_ratio = img.width / img.height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # 图像更宽，以高度为准
            new_height = target_height
            new_width = int(new_height * img_ratio)
        else:
            # 图像更高，以宽度为准
            new_width = target_width
            new_height = int(new_width / img_ratio)

        # 使用BOX缩放（官方推荐，平衡锐利度和质量）
        img = img.resize((new_width, new_height), Image.BOX)

        # 居中裁剪
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        img = img.crop((left, top, right, bottom))

        return img

    def resize_and_crop_image(self, img: Image.Image, target_size: tuple) -> Image.Image:
        """
        调整图像大小并居中裁剪到目标尺寸（通用方法）

        Args:
            img: PIL Image对象
            target_size: 目标尺寸 (width, height)

        Returns:
            调整后的PIL Image对象
        """
        target_width, target_height = target_size

        # 转换为灰度
        img = img.convert('L')

        # 计算缩放比例（保持纵横比）
        img_ratio = img.width / img.height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # 图像更宽，以高度为准
            new_height = target_height
            new_width = int(new_height * img_ratio)
        else:
            # 图像更高，以宽度为准
            new_width = target_width
            new_height = int(new_width / img_ratio)

        # 调整大小（使用BOX，官方推荐）
        img = img.resize((new_width, new_height), Image.BOX)

        # 居中裁剪
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        img = img.crop((left, top, right, bottom))

        return img

    def convert_png_to_xtc(self, png_path: Path, output_path: Optional[Path] = None, format_mode: str = "xtg") -> Tuple[bool, str]:
        """
        将单个PNG转换为XTG/XTH

        Args:
            png_path: PNG文件路径
            output_path: 输出文件路径
            format_mode: 格式模式，"xtg"(1位单色) 或 "xth"(4级灰度)
        """
        try:
            logger.info(f"开始转换PNG: {png_path.name} (模式: {format_mode.upper()})")

            # 如果没有指定输出路径，生成默认路径
            if output_path is None:
                current_dir = Path(__file__).parent.parent
                temp_convert_dir = current_dir / "temp_convert"
                temp_convert_dir.mkdir(exist_ok=True)
                ext = "xtg" if format_mode == "xtg" else "xth"
                output_path = temp_convert_dir / (png_path.stem + f".{ext}")

            # 使用内置的PNG转XTG/XTH方法
            if format_mode == "xtg":
                self.png_to_xtg_file(png_path, output_path)
            else:
                self.png_to_xth_file(png_path, output_path)

            logger.info(f"PNG转换成功: {png_path.name} -> {output_path.name} ({format_mode.upper()})")
            return True, str(output_path)

        except Exception as e:
            logger.error(f"PNG转换失败: {e}")
            return False, f"转换失败: {str(e)}"

    def png_to_xtg_file(self, png_path: Path, xtg_out_path: Path, force_size=(480, 800), threshold=168):
        """
        将PNG转换为XTG文件（内置实现，与png2xtc.py逻辑相同）

        Args:
            png_path: PNG文件路径
            xtg_out_path: 输出XTG文件路径
            force_size: 强制调整到的尺寸
            threshold: 二值化阈值（0-255），128为中等，越低越偏向白色
        """
        # 转换为灰度图像并处理
        img = Image.open(png_path)

        # 调整大小（使用BOX，官方推荐）
        if img.size != force_size:
            img = img.resize(force_size, Image.BOX)

        # 转换为灰度
        w, h = force_size
        gray = img.convert("L")
        row_bytes = (w + 7) // 8
        data = bytearray(row_bytes * h)

        pixels = gray.load()
        for y in range(h):
            for x in range(w):
                bit = 1 if pixels[x, y] >= threshold else 0
                byte_index = y * row_bytes + (x // 8)
                bit_index = 7 - (x % 8)  # MSB first
                if bit:
                    data[byte_index] |= (1 << bit_index)

        md5digest = hashlib.md5(data).digest()[:8]
        data_size = len(data)

        # XTG header: <4sHHBBI8s> little-endian
        header = struct.pack(
            "<4sHHBBI8s",
            b"XTG\x00",
            w,
            h,
            0,  # colorMode
            0,  # compression
            data_size,
            md5digest
        )

        # 写入文件
        with open(xtg_out_path, "wb") as f:
            f.write(header + data)

        logger.debug(f"写入XTG文件: {xtg_out_path}")

    def convert_png_folder_to_xtc(self, png_dir: Path, output_path: Path, format_mode: str = "xtg") -> bool:
        """
        将PNG文件夹转换为XTC（使用内置实现）

        Args:
            png_dir: PNG文件所在目录
            output_path: 输出XTC文件路径
            format_mode: 格式模式，"xtg"(1位单色) 或 "xth"(4级灰度)
        """
        try:
            # 获取所有PNG文件并排序
            png_files = sorted(png_dir.glob("page-*.png"))

            if not png_files:
                logger.error(f"PNG文件夹中没有找到文件: {png_dir}")
                return False

            logger.info(f"找到 {len(png_files)} 个PNG文件")

            # 转换每个PNG为XTG/XTH字节
            page_blobs = []
            for i, png_path in enumerate(png_files):
                img = Image.open(png_path)
                if format_mode == "xtg":
                    page_bytes = self.png_to_xtg_bytes(img, force_size=(480, 800))
                else:
                    page_bytes = self.png_to_xth_bytes(img, force_size=(480, 800))

                # 调试：打印第一个页面的magic number
                if i == 0:
                    logger.info(f"第一个页面 ({png_path.name}): 大小={len(page_bytes)}, 前4字节={page_bytes[:4].hex()}")

                page_blobs.append(page_bytes)

            # 构建XTC文件
            self.build_xtc_from_page_blobs(page_blobs, output_path, format_mode)

            logger.info(f"XTC文件创建成功: {output_path} ({format_mode.upper()})")
            return True

        except Exception as e:
            logger.error(f"PNG文件夹转XTC失败: {e}")
            return False

    def png_to_xtg_bytes(self, img: Image.Image, force_size=(480, 800), threshold=168):
        """
        将PIL图像转换为XTG字节数据（1位单色）

        Args:
            img: PIL图像对象
            force_size: 强制调整到的尺寸
            threshold: 二值化阈值（0-255），128为中等，越低越偏向白色
        """
        # 调整大小（使用BOX，官方推荐）
        if img.size != force_size:
            img = img.resize(force_size, Image.BOX)

        w, h = img.size
        gray = img.convert("L")
        row_bytes = (w + 7) // 8
        data = bytearray(row_bytes * h)

        pixels = gray.load()
        for y in range(h):
            for x in range(w):
                # 使用128作为阈值，让黑白更平衡，图片更浅
                bit = 1 if pixels[x, y] >= threshold else 0
                byte_index = y * row_bytes + (x // 8)
                bit_index = 7 - (x % 8)  # MSB first
                if bit:
                    data[byte_index] |= (1 << bit_index)

        md5digest = hashlib.md5(data).digest()[:8]
        data_size = len(data)

        # XTG header: <4sHHBBI8s> little-endian
        header = struct.pack(
            "<4sHHBBI8s",
            b"XTG\x00",
            w,
            h,
            0,  # colorMode
            0,  # compression
            data_size,
            md5digest
        )
        return header + data

    def build_xtc_from_page_blobs(self, page_blobs: List[bytes], out_path: Path, format_mode: str = "xtg", read_direction=0, chapters=None):
        """
        从XTG/XTH字节数据构建XTC文件

        Args:
            page_blobs: XTG或XTH字节数据列表
            out_path: 输出XTC文件路径
            format_mode: 格式模式，"xtg" 或 "xth"
            read_direction: 阅读方向
            chapters: 忽略此参数(保留兼容性)
        """
        page_count = len(page_blobs)
        header_size = 48
        index_entry_size = 16
        index_offset = header_size

        data_offset = index_offset + page_count * index_entry_size

        # Index table: <Q I H H> per page
        index_table = bytearray()
        rel_offset = data_offset
        for blob in page_blobs:
            w, h = struct.unpack_from("<HH", blob, 4)
            entry = struct.pack("<Q I H H", rel_offset, len(blob), w, h)
            index_table += entry
            rel_offset += len(blob)

        # 无缩略图
        thumb_offset = 0

        # XTC header: <4sHHBBBBIQQQQ> little-endian
        xtc_header = struct.pack(
            "<4sHHBBBBIQQQQ",
            b"XTC\x00",         # mark
            0x0100,             # version
            page_count,         # pageCount
            read_direction,     # readDirection
            0,                  # hasMetadata
            0,                  # hasThumbnails
            0,                  # hasChapters
            0,                  # currentPage
            0,                  # metadataOffset
            index_offset,       # indexOffset
            data_offset,        # dataOffset
            thumb_offset        # thumbOffset
        )

        assert len(xtc_header) == 48
        logger.debug(f"index offset: {index_offset}")
        logger.debug(f"data offset: {data_offset}")

        # 写入文件
        with open(out_path, "wb") as f:
            f.write(xtc_header)
            f.write(index_table)
            for blob in page_blobs:
                f.write(blob)

        logger.info(f"写入XTC文件 ({page_count} 页, {format_mode.upper()}) -> {out_path}")

    def png_to_xth_file(self, png_path: Path, xth_out_path: Path, force_size=(480, 800),
                       thresholds=(85, 170, 255), dither=False):
        """
        将PNG转换为XTH文件（4级灰度）
        使用xtc_encoder.py中的XTHWriter类（官方实现）

        Args:
            png_path: PNG文件路径
            xth_out_path: 输出XTH文件路径
            force_size: 强制调整到的尺寸
            thresholds: 4级灰度阈值 (t1, t2, t3)
            dither: 是否使用抖动
        """
        from src.xtc_encoder import XTHWriter

        # 转换为灰度图像并处理
        img = Image.open(png_path)

        # 使用XTHWriter进行编码
        writer = XTHWriter(width=force_size[0], height=force_size[1],
                          thresholds=thresholds, dither=dither)

        # 编码并保存
        xth_data = writer.encode(img)
        with open(xth_out_path, "wb") as f:
            f.write(xth_data)

        logger.debug(f"写入XTH文件: {xth_out_path}")

    def png_to_xth_bytes(self, img: Image.Image, force_size=(480, 800),
                        thresholds=(85, 170, 255), dither=False):
        """
        将PIL图像转换为XTH字节数据（4级灰度）
        使用xtc_encoder.py中的XTHWriter类（官方实现）

        Args:
            img: PIL图像对象
            force_size: 强制调整到的尺寸
            thresholds: 4级灰度阈值 (t1, t2, t3)
            dither: 是否使用抖动
        """
        from src.xtc_encoder import XTHWriter

        # 使用XTHWriter进行编码
        writer = XTHWriter(width=force_size[0], height=force_size[1],
                          thresholds=thresholds, dither=dither)

        # 直接调用XTHWriter的encode方法
        return writer.encode(img)

    def _floyd_steinberg_dither_4level(self, image: np.ndarray, thresholds: Tuple[int, int, int]) -> np.ndarray:
        """
        Floyd-Steinberg抖动算法（4级灰度）

        Args:
            image: 灰度图像数组
            thresholds: 4级灰度阈值

        Returns:
            抖动后的图像
        """
        height, width = image.shape
        working = image.astype(np.float32).copy()
        t1, t2, t3 = thresholds
        dither_strength = 0.8

        # 误差分布权重
        w_right = (7/16) * dither_strength
        w_bl = (3/16) * dither_strength
        w_b = (5/16) * dither_strength
        w_br = (1/16) * dither_strength

        for y in range(height):
            for x in range(width):
                old_val = working[y, x]

                # 4级量化（标准4级灰度值：0, 85, 170, 255）
                if old_val < t1:
                    level, new_val = 0, 0.0
                elif old_val < t2:
                    level, new_val = 1, 85.0
                elif old_val < t3:
                    level, new_val = 2, 170.0
                else:
                    level, new_val = 3, 255.0

                error = old_val - new_val

                # 误差分布
                if x + 1 < width:
                    working[y, x + 1] += error * w_right
                if y + 1 < height:
                    if x > 0:
                        working[y + 1, x - 1] += error * w_bl
                    working[y + 1, x] += error * w_b
                    if x + 1 < width:
                        working[y + 1, x + 1] += error * w_br

        return np.clip(working, 0, 255).astype(np.uint8)


# 创建全局实例
conversion_service = ConversionService()
