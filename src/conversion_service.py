#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件格式转换服务 (纯Python版本)
支持将EPUB、PDF等格式转换为电子纸用的XTC格式
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

    def convert_to_xtc(self, file_path: Path, output_path: Optional[Path] = None) -> Tuple[bool, str]:
        """
        将文件转换为XTC格式

        Args:
            file_path: 输入文件路径
            output_path: 输出文件路径（可选，默认与输入文件同目录）

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
                return self.convert_epub_to_xtc(file_path, output_path)
            elif file_ext == '.pdf':
                return self.convert_pdf_to_xtc(file_path, output_path)
            elif file_ext == '.png':
                return self.convert_png_to_xtc(file_path, output_path)
            else:
                return False, f"不支持的文件格式: {file_ext}"

        except Exception as e:
            logger.error(f"文件转换失败 {file_path}: {e}")
            return False, f"转换失败: {str(e)}"

    def convert_epub_to_xtc(self, epub_path: Path, output_path: Optional[Path] = None) -> Tuple[bool, str]:
        """
        将EPUB转换为XTC

        流程: EPUB → 提取图片 → XTC
        使用纯Python库实现
        """
        temp_dir = None
        try:
            logger.info(f"开始转换EPUB: {epub_path.name}")

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
            if not self.convert_png_folder_to_xtc(temp_png_dir, output_path):
                return False, "PNG转XTC失败"

            logger.info(f"EPUB转换成功: {epub_path.name} -> {output_path.name}")
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

    def convert_epub_to_png_pure(self, epub_path: Path, output_dir: Path) -> bool:
        """
        使用纯Python库将EPUB转换为PNG
        实现原理：解析EPUB，使用ebooklib提取内容，渲染为图片
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

            # 获取所有章节
            items = list(book.get_items())
            logger.info(f"EPUB包含 {len(items)} 个项目")

            # 创建字体
            try:
                # 尝试使用系统字体
                font_large = ImageFont.truetype("msyh.ttc", 24)  # 标题
                font_normal = ImageFont.truetype("msyh.ttc", 16)  # 正文
            except:
                # 如果找不到字体，使用默认字体
                font_large = ImageFont.load_default()
                font_normal = ImageFont.load_default()

            page_width = 480
            page_height = 800
            margin = 20
            line_height = 24
            page_num = 0

            # 遍历所有HTML内容
            for item in items:
                if isinstance(item, ebooklib.epub.EpubHtml):
                    logger.info(f"处理章节: {item.get_name()}")

                    # 解析HTML内容
                    soup = BeautifulSoup(item.get_content(), 'html.parser')

                    # 提取文本
                    text_content = soup.get_text()

                    # 创建页面
                    img = Image.new('RGB', (page_width, page_height), 'white')
                    draw = ImageDraw.Draw(img)

                    # 简单的文本渲染
                    y_position = margin

                    # 绘制标题
                    if item.get_name():
                        title = item.get_name().replace('_', ' ').title()
                        draw.text((margin, y_position), title, font=font_large, fill='black')
                        y_position += 40

                    # 绘制正文（按行分割）
                    for line in text_content.split('\n'):
                        line = line.strip()
                        if not line:
                            y_position += line_height // 2
                            continue

                        # 如果页面满了，保存并创建新页面
                        if y_position > page_height - margin - line_height:
                            # 保存当前页面
                            page_path = output_dir / f"page-{page_num:04d}.png"
                            img.save(page_path)
                            page_num += 1

                            # 创建新页面
                            img = Image.new('RGB', (page_width, page_height), 'white')
                            draw = ImageDraw.Draw(img)
                            y_position = margin

                        # 绘制文本行
                        draw.text((margin, y_position), line, font=font_normal, fill='black')
                        y_position += line_height

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

    def convert_pdf_to_xtc(self, pdf_path: Path, output_path: Optional[Path] = None) -> Tuple[bool, str]:
        """
        将PDF转换为XTC

        流程: PDF → PNG → XTC
        使用PyMuPDF (fitz) 纯Python实现
        """
        temp_dir = None
        try:
            logger.info(f"开始转换PDF: {pdf_path.name}")

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
            if not self.convert_png_folder_to_xtc(temp_png_dir, output_path):
                return False, "PNG转XTC失败"

            logger.info(f"PDF转换成功: {pdf_path.name} -> {output_path.name}")
            return True, str(output_path)

        except Exception as e:
            logger.error(f"PDF转换失败: {e}")
            return False, f"转换失败: {str(e)}"
        finally:
            # 清理临时文件
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug(f"已清理临时目录: {temp_dir}")
                except Exception as e:
                    logger.warning(f"清理临时目录失败: {e}")

    def convert_pdf_to_png_pure(self, pdf_path: Path, output_dir: Path) -> bool:
        """
        使用PyMuPDF将PDF转换为PNG（纯Python实现）
        简单转换方式，与epub2xtc-main保持一致
        """
        try:
            logger.info("使用PyMuPDF转换PDF（简单模式）")

            # 打开PDF
            doc = fitz.open(str(pdf_path))
            page_count = len(doc)

            logger.info(f"PDF包含 {page_count} 页")

            # 使用适中的缩放比例
            zoom = 2.0  # 2.0倍缩放足够
            mat = fitz.Matrix(zoom, zoom)

            # 渲染每一页
            for page_num in range(page_count):
                page = doc.load_page(page_num)

                # 渲染为像素图
                pix = page.get_pixmap(matrix=mat)

                # 转换为PIL Image并直接调整大小
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # 直接调整为480x800，保持简单
                img = self.resize_simple(img, (480, 800))

                # 保存为PNG（不做额外处理）
                output_path = output_dir / f"page-{page_num:04d}.png"
                img.save(output_path, 'PNG')
                logger.debug(f"保存页面: {output_path}")

            doc.close()

            # 检查是否生成了PNG文件
            png_files = list(output_dir.glob("page-*.png"))
            if png_files:
                logger.info(f"生成了 {len(png_files)} 个PNG文件")
                return True
            else:
                logger.error("未生成PNG文件")
                return False

        except Exception as e:
            logger.error(f"PDF转PNG失败: {e}")
            return False

    def resize_simple(self, img: Image.Image, target_size: tuple) -> Image.Image:
        """
        简单的图像调整，与epub2xtc-main保持一致
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

        # 使用LANCZOS缩放
        img = img.resize((new_width, new_height), Image.LANCZOS)

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
        # 对于大幅缩小，使用LANCZOS获得最好效果
        img = img.resize((new_width, new_height), Image.LANCZOS)

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

        # 使用最高质量的缩放算法
        img = img.resize((new_width, new_height), Image.LANCZOS)

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

        # 调整大小
        img = img.resize((new_width, new_height), Image.LANCZOS)

        # 居中裁剪
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        img = img.crop((left, top, right, bottom))

        return img

    def convert_png_to_xtc(self, png_path: Path, output_path: Optional[Path] = None) -> Tuple[bool, str]:
        """
        将单个PNG转换为XTG
        """
        try:
            logger.info(f"开始转换PNG: {png_path.name}")

            # 如果没有指定输出路径，生成默认路径
            if output_path is None:
                current_dir = Path(__file__).parent.parent
                temp_convert_dir = current_dir / "temp_convert"
                temp_convert_dir.mkdir(exist_ok=True)
                output_path = temp_convert_dir / (png_path.stem + ".xtg")

            # 使用内置的PNG转XTG方法
            self.png_to_xtg_file(png_path, output_path)

            logger.info(f"PNG转换成功: {png_path.name} -> {output_path.name}")
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

        # 调整大小
        if img.size != force_size:
            img = img.resize(force_size, Image.LANCZOS)

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

    def convert_png_folder_to_xtc(self, png_dir: Path, output_path: Path) -> bool:
        """
        将PNG文件夹转换为XTC（使用内置实现）
        """
        try:
            # 获取所有PNG文件并排序
            png_files = sorted(png_dir.glob("page-*.png"))

            if not png_files:
                logger.error(f"PNG文件夹中没有找到文件: {png_dir}")
                return False

            logger.info(f"找到 {len(png_files)} 个PNG文件")

            # 转换每个PNG为XTG字节
            xtg_blobs = []
            for png_path in png_files:
                img = Image.open(png_path)
                xtg_bytes = self.png_to_xtg_bytes(img, force_size=(480, 800))
                xtg_blobs.append(xtg_bytes)

            # 构建XTC文件
            self.build_xtc_from_xtg_blobs(xtg_blobs, output_path)

            logger.info(f"XTC文件创建成功: {output_path}")
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
        if img.size != force_size:
            img = img.resize(force_size, Image.LANCZOS)

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

    def build_xtc_from_xtg_blobs(self, xtg_blobs: List[bytes], out_path: Path, read_direction=0):
        """
        从XTG字节数据构建XTC文件
        """
        page_count = len(xtg_blobs)
        header_size = 48
        index_entry_size = 16
        index_offset = header_size
        data_offset = index_offset + page_count * index_entry_size

        # Index table: <Q I H H> per page
        index_table = bytearray()
        rel_offset = data_offset
        for blob in xtg_blobs:
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
            0x0100,                  # version
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
            for blob in xtg_blobs:
                f.write(blob)

        logger.info(f"写入XTC文件 ({page_count} 页) -> {out_path}")


# 创建全局实例
conversion_service = ConversionService()
