"""
XTC格式编码器原生实现
支持XTG（1位单色）和XTH（4级灰度）格式
"""

import struct
import hashlib
import numpy as np
from typing import Tuple, List, Optional
from dataclasses import dataclass
from enum import Enum


class XTCFormat(Enum):
    """XTC格式类型"""
    XTG = "xtg"  # 1位单色
    XTH = "xth"  # 4级灰度


@dataclass
class XTCMetadata:
    """XTC元数据"""
    title: str = ""
    author: str = ""
    publisher: str = ""
    language: str = "zh-CN"
    create_time: int = 0
    cover_page: int = 0xFFFF  # 0xFFFF表示无封面
    chapter_count: int = 0


@dataclass
class XTCChapter:
    """XTC章节信息"""
    name: str
    start_page: int  # 0-based
    end_page: int    # 0-based, 包含


class XTGWriter:
    """XTG格式编码器（1位单色）"""

    MAGIC = 0x00475458  # "XTG\0" in little-endian
    HEADER_SIZE = 22

    def __init__(self, width: int = 480, height: int = 800, threshold: int = 128):
        """
        初始化XTG编码器

        Args:
            width: 图像宽度
            height: 图像高度
            threshold: 二值化阈值（0-255）
        """
        self.width = width
        self.height = height
        self.threshold = threshold

    def encode(self, image: np.ndarray) -> bytes:
        """
        将图像编码为XTG格式

        Args:
            image: PIL Image或numpy数组（灰度或RGB）

        Returns:
            XTG格式字节数据
        """
        # 转换为numpy数组（如果需要）
        if not isinstance(image, np.ndarray):
            image = np.array(image)

        # 如果是RGB，转换为灰度
        if len(image.shape) == 3:
            image = np.dot(image[..., :3], [0.299, 0.587, 0.114]).astype(np.uint8)

        # 调整大小
        if image.shape[0] != self.height or image.shape[1] != self.width:
            from PIL import Image
            pil_img = Image.fromarray(image).resize((self.width, self.height), Image.Resampling.LANCZOS)
            image = np.array(pil_img)

        # 二值化
        bitmap = (image >= self.threshold).astype(np.uint8)

        # 行优先位图编码
        bitmap_data = self._encode_bitmap(bitmap)

        # 计算校验和
        checksum = hashlib.md5(bitmap_data).digest()

        # 构建头部
        header = struct.pack(
            '<IHHBB8s',
            self.MAGIC,        # 魔数 (4字节)
            self.width,        # 宽度 (2字节)
            self.height,       # 高度 (2字节)
            0,                 # 颜色模式 (1字节)
            0,                 # 压缩 (1字节)
            checksum           # MD5校验和 (8字节)
        )

        return header + bitmap_data

    def _encode_bitmap(self, bitmap: np.ndarray) -> bytes:
        """
        行优先位图编码

        Args:
            bitmap: 二值图像数组（0或1）

        Returns:
            编码后的字节数据
        """
        height, width = bitmap.shape
        bytes_per_row = (width + 7) // 8
        result = bytearray(bytes_per_row * height)

        for y in range(height):
            for x in range(width):
                if bitmap[y, x]:
                    byte_index = y * bytes_per_row + x // 8
                    bit_index = 7 - (x % 8)  # MSB优先
                    result[byte_index] |= (1 << bit_index)

        return bytes(result)


class XTHWriter:
    """XTH格式编码器（4级灰度）"""

    MAGIC = 0x00485458  # "XTH\0" in little-endian
    HEADER_SIZE = 22

    def __init__(self,
                 width: int = 480,
                 height: int = 800,
                 thresholds: Tuple[int, int, int] = (85, 170, 255),
                 dither: bool = True,  # 官方默认启用抖动
                 dither_strength: float = 0.8):
        """
        初始化XTH编码器

        Args:
            width: 图像宽度
            height: 图像高度
            thresholds: 4级灰度阈值 (t1, t2, t3)
            dither: 是否使用抖动
            dither_strength: 抖动强度
        """
        self.width = width
        self.height = height
        self.thresholds = thresholds
        self.dither = dither
        self.dither_strength = dither_strength

    def encode(self, image: np.ndarray) -> bytes:
        """
        将图像编码为XTH格式
        基于官方实现 tool/xtctool-master/xtctool/core/xth.py

        Args:
            image: PIL Image或numpy数组（灰度或RGB）

        Returns:
            XTH格式字节数据
        """
        # 转换为numpy数组（如果需要）
        if not isinstance(image, np.ndarray):
            image = np.array(image)

        # 如果是RGB，转换为灰度
        if len(image.shape) == 3:
            image = np.dot(image[..., :3], [0.299, 0.587, 0.114]).astype(np.uint8)

        # 调整大小（使用BOX重采样，适合文本）
        if image.shape[0] != self.height or image.shape[1] != self.width:
            from PIL import Image
            pil_img = Image.fromarray(image)
            image = np.array(pil_img.resize((self.width, self.height), Image.Resampling.BOX))

        # 转换为4级灰度（如果启用抖动，抖动函数直接返回0-3级别）
        if self.dither:
            pixel_values = self._floyd_steinberg_dither(image)  # 直接返回0-3
        else:
            pixel_values = self._convert_to_4level(image)  # 返回0-3

        # 垂直位平面编码
        plane1, plane2 = self._encode_bitplanes(pixel_values)

        # 计算数据大小
        data_size = len(plane1) + len(plane2)

        # 计算校验和（简单求和，与官方一致）
        checksum = sum(plane1) + sum(plane2)

        # 构建完整文件数据（与官方一致）
        data = bytearray()
        data.extend(struct.pack('<I', self.MAGIC))           # magic (4 bytes)
        data.extend(struct.pack('<H', self.width))           # width (2 bytes)
        data.extend(struct.pack('<H', self.height))          # height (2 bytes)
        data.extend(struct.pack('<B', 0))                    # colorMode (1 byte)
        data.extend(struct.pack('<B', 0))                    # compression (1 byte)
        data.extend(struct.pack('<I', data_size))            # dataSize (4 bytes)
        data.extend(struct.pack('<Q', checksum & 0xFFFFFFFFFFFFFFFF))  # checksum (8 bytes)
        data.extend(plane1)
        data.extend(plane2)

        return bytes(data)

    def _convert_to_4level(self, image: np.ndarray) -> np.ndarray:
        """
        将灰度图像转换为4级灰度

        Args:
            image: 灰度图像数组 (0-255)

        Returns:
            4级灰度图像数组 (0-3)
        """
        t1, t2, t3 = self.thresholds
        result = np.zeros_like(image, dtype=np.uint8)

        result[image < t1] = 0
        result[(image >= t1) & (image < t2)] = 1
        result[(image >= t2) & (image < t3)] = 2
        result[image >= t3] = 3

        return result

    def _encode_bitplanes(self, pixel_values: np.ndarray) -> Tuple[bytes, bytes]:
        """
        垂直位平面编码（列优先）
        基于官方实现 tool/xtctool-master/xtctool/core/xth.py

        关键特性：
        - 从右到左扫描列（避免水平翻转）
        - LUT映射交换中间值 {0: 0, 1: 2, 2: 1, 3: 3}
        - 反转以匹配显示行为（避免反色）

        Args:
            pixel_values: 4级灰度图像 (0-3)

        Returns:
            (plane1, plane2) 两个位平面
        """
        # 映射像素值以匹配Xteink LUT（交换中间值）
        # 0 -> 0 (白色), 1 -> 2 (深灰), 2 -> 1 (浅灰), 3 -> 3 (黑色)
        lut_map = {0: 0, 1: 2, 2: 1, 3: 3}
        mapped_values = np.vectorize(lambda x: lut_map[x])(pixel_values)

        # 反转以匹配显示行为
        mapped_values = 3 - mapped_values

        plane1 = bytearray()
        plane2 = bytearray()

        # 从右到左扫描列
        for x in range(self.width - 1, -1, -1):
            # 以8个垂直像素为一组处理列
            for y in range(0, self.height, 8):
                byte1 = 0
                byte2 = 0

                # 打包8个垂直像素
                for i in range(8):
                    if y + i < self.height:
                        pixel_val = mapped_values[y + i, x]
                        bit1 = (pixel_val >> 1) & 1  # 高位
                        bit2 = pixel_val & 1          # 低位

                        # MSB = 最顶部的像素
                        byte1 |= bit1 << (7 - i)
                        byte2 |= bit2 << (7 - i)

                plane1.append(byte1)
                plane2.append(byte2)

        return bytes(plane1), bytes(plane2)

    def _floyd_steinberg_dither(self, image: np.ndarray) -> np.ndarray:
        """
        Floyd-Steinberg抖动算法（4级灰度）
        基于官方实现，直接返回0-3的级别

        Args:
            image: 灰度图像数组 (0-255)

        Returns:
            4级灰度图像数组 (0-3)
        """
        height, width = image.shape
        working = image.astype(np.float32).copy()
        result = np.zeros((height, width), dtype=np.uint8)
        t1, t2, t3 = self.thresholds

        # 误差分布权重
        w_right = (7/16) * self.dither_strength
        w_bl = (3/16) * self.dither_strength
        w_b = (5/16) * self.dither_strength
        w_br = (1/16) * self.dither_strength

        for y in range(height):
            for x in range(width):
                old_val = working[y, x]

                # 4级量化
                if old_val < t1:
                    level, new_val = 0, 0.0
                elif old_val < t2:
                    level, new_val = 1, 120.0
                elif old_val < t3:
                    level, new_val = 2, 170.0
                else:
                    level, new_val = 3, 255.0

                result[y, x] = level  # 直接存储级别（0-3）
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

        return result  # 返回0-3的级别数组


class XTCWriter:
    """XTC容器格式编码器（多页）"""

    MAGIC = 0x00435458  # "XTC\0" in little-endian
    VERSION = 0x0100
    HEADER_SIZE = 48
    METADATA_SIZE = 256
    CHAPTER_SIZE = 96
    INDEX_ENTRY_SIZE = 16

    def __init__(self,
                 width: int = 480,
                 height: int = 800,
                 format_type: XTCFormat = XTCFormat.XTG,
                 reading_direction: int = 0):
        """
        初始化XTC编码器

        Args:
            width: 页面宽度
            height: 页面高度
            format_type: 格式类型（XTG或XTH）
            reading_direction: 阅读方向 (0=ltr, 1=rtl, 2=ttb)
        """
        self.width = width
        self.height = height
        self.format_type = format_type
        self.reading_direction = reading_direction

        # 根据格式类型创建编码器
        if format_type == XTCFormat.XTG:
            self.page_writer = XTGWriter(width, height)
        else:
            self.page_writer = XTHWriter(width, height)

    def write(self,
              pages: List[bytes],
              metadata: Optional[XTCMetadata] = None,
              chapters: Optional[List[XTCChapter]] = None) -> bytes:
        """
        将多页写入XTC容器

        Args:
            pages: 页面数据列表（XTG或XTH格式）
            metadata: 元数据（可选）
            chapters: 章节信息（可选）

        Returns:
            XTC格式字节数据
        """
        page_count = len(pages)
        has_metadata = metadata is not None
        has_chapters = chapters is not None and len(chapters) > 0

        # 计算偏移量
        metadata_offset = 0
        chapter_offset = 0
        index_offset = self.HEADER_SIZE
        data_offset = index_offset + self.INDEX_ENTRY_SIZE * page_count

        if has_metadata:
            metadata_offset = data_offset
            data_offset += self.METADATA_SIZE

        if has_chapters:
            chapter_offset = data_offset
            data_offset += self.CHAPTER_SIZE * len(chapters)

        # 计算页面数据偏移
        page_offsets = []
        current_offset = data_offset
        for page in pages:
            page_offsets.append(current_offset)
            current_offset += len(page)

        # 构建文件头
        header = struct.pack(
            '<IHHBBBBBIQQQ',
            self.MAGIC,              # 魔数 (4字节)
            self.VERSION,            # 版本 (2字节)
            page_count,              # 页数 (2字节)
            self.reading_direction,  # 阅读方向 (1字节)
            int(has_metadata),       # 元数据标志 (1字节)
            0,                       # 缩略图标志 (1字节)
            int(has_chapters),       # 章节标志 (1字节)
            0,                       # 当前页 (4字节)
            metadata_offset,         # 元数据偏移 (8字节)
            index_offset,            # 索引偏移 (8字节)
            data_offset              # 数据偏移 (8字节)
        )

        # 构建索引表
        index_data = bytearray()
        for i, (page, offset) in enumerate(zip(pages, page_offsets)):
            index_entry = struct.pack(
                '<IQ',
                i,          # 页索引
                offset      # 数据偏移
            )
            index_data.extend(index_entry)

        # 构建元数据
        metadata_data = b''
        if has_metadata:
            title_bytes = metadata.title.encode('utf-8')[:128]
            author_bytes = metadata.author.encode('utf-8')[:64]
            publisher_bytes = metadata.publisher.encode('utf-8')[:32]
            lang_bytes = metadata.language.encode('utf-8')[:8]

            title_padded = title_bytes + b'\x00' * (128 - len(title_bytes))
            author_padded = author_bytes + b'\x00' * (64 - len(author_bytes))
            publisher_padded = publisher_bytes + b'\x00' * (32 - len(publisher_bytes))
            lang_padded = lang_bytes + b'\x00' * (8 - len(lang_bytes))

            metadata_data = struct.pack(
                '<128s64s32s8sQHH',
                title_padded,
                author_padded,
                publisher_padded,
                lang_padded,
                metadata.create_time,
                metadata.cover_page,
                metadata.chapter_count
            )

        # 构建章节信息
        chapter_data = b''
        if has_chapters:
            for chapter in chapters:
                name_bytes = chapter.name.encode('utf-8')[:80]
                name_padded = name_bytes + b'\x00' * (80 - len(name_bytes))

                chapter_entry = struct.pack(
                    '<80sHH',
                    name_padded,
                    chapter.start_page,
                    chapter.end_page
                )
                chapter_data += chapter_entry

        # 组合所有数据
        result = header
        result += index_data
        result += metadata_data
        result += chapter_data
        result += b''.join(pages)

        return result
