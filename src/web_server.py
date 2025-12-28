#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XTEAILINK Web服务器
提供电子书上传、队列管理和设备设置的Web API
集成MCP服务器作为后台线程
"""

import json
import os
import tempfile
import uuid
import time
import shutil
import threading
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import logging
import os

from book_transfer_service import BookTransferService
from conversion_service import conversion_service
from chat_service import get_chat_service

# 获取项目根目录（src的父目录）
project_root = Path(__file__).parent.parent
static_folder_path = project_root / 'static'

# 配置Flask，使用绝对路径
app = Flask(__name__, static_folder=str(static_folder_path))
CORS(app)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/web_server.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 全局变量
transfer_service = None
queue_file = Path("data/queue.json")
pending_dir = Path("data/pending_books")
background_thread = None
mcp_thread = None
stop_background_thread = False
stop_mcp_thread = False

# MCP服务器相关
def start_mcp_server():
    """启动MCP服务器"""
    try:
        # 导入MCP服务器模块
        import sys
        current_dir = Path(__file__).parent
        mcp_server_path = current_dir / "mcp" / "mcp_server.py"
        
        # 动态导入MCP服务器模块
        import importlib.util
        spec = importlib.util.spec_from_file_location("mcp_server", mcp_server_path)
        mcp_server_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mcp_server_module)
        mcp = mcp_server_module.mcp
        
        logger.info("启动MCP服务器...")
        # 在后台线程中运行MCP服务器
        mcp.run(
            transport="streamable-http", 
            host="0.0.0.0", 
            port=8099, 
            path="/mcp"
        )
    except Exception as e:
        logger.error(f"MCP服务器启动失败: {e}")

def background_transfer_worker():
    """后台传书工作线程"""
    global stop_background_thread, transfer_service
    
    logger.info("后台传书线程启动")
    
    while not stop_background_thread:
        try:
            if transfer_service:
                # 检查设备连接
                connected = transfer_service.check_device_connection()
                
                if connected:
                    # 设备连接正常，执行传书
                    transferred_count = transfer_service.run_once()
                    
                    # 如果有书籍传输成功，更新队列状态
                    if transferred_count > 0:
                        update_queue_after_transfer()
                        logger.info(f"后台传书完成，成功传输 {transferred_count} 本书籍")
                
                # 等待30秒再检查
                for _ in range(30):
                    if stop_background_thread:
                        break
                    time.sleep(1)
            else:
                # 传书服务未初始化，等待5秒
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"后台传书线程出错: {e}")
            time.sleep(10)  # 出错后等待10秒再重试
    
    logger.info("后台传书线程停止")

def update_queue_after_transfer():
    """传书完成后更新队列状态"""
    try:
        queue = load_queue()
        updated_queue = []
        
        for item in queue:
            file_path = Path(item['path'])
            if file_path.exists():
                # 文件还存在，检查是否应该更新状态
                if item['status'] == 'pending':
                    # 保持pending状态，等待下次传书
                    updated_queue.append(item)
                else:
                    # 其他状态保持不变
                    updated_queue.append(item)
            else:
                # 文件不存在，说明已传输完成，从队列中移除
                logger.info(f"文件已传输完成，从队列中移除: {item['name']}")
                # 不添加到updated_queue中，相当于删除
        
        save_queue(updated_queue)
        
    except Exception as e:
        logger.error(f"更新队列状态失败: {e}")

def init_transfer_service():
    """初始化传书服务"""
    global transfer_service, background_thread, stop_background_thread
    
    try:
        transfer_service = BookTransferService()
        logger.info("传书服务初始化成功")
        
        # 启动后台传书线程
        if background_thread is None or not background_thread.is_alive():
            stop_background_thread = False
            background_thread = threading.Thread(target=background_transfer_worker, daemon=True)
            background_thread.start()
            logger.info("后台传书线程已启动")
            
    except Exception as e:
        logger.error(f"传书服务初始化失败: {e}")
        transfer_service = None

def init_mcp_server():
    """初始化MCP服务器"""
    global mcp_thread, stop_mcp_thread
    
    try:
        # 启动MCP服务器线程
        if mcp_thread is None or not mcp_thread.is_alive():
            stop_mcp_thread = False
            mcp_thread = threading.Thread(target=start_mcp_server, daemon=True)
            mcp_thread.start()
            logger.info("MCP服务器线程已启动，监听端口: 8099")
            
    except Exception as e:
        logger.error(f"MCP服务器初始化失败: {e}")

def load_queue() -> List[Dict]:
    """加载传书队列"""
    if not queue_file.exists():
        return []
    
    try:
        with open(queue_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载队列失败: {e}")
        return []

def save_queue(queue: List[Dict]):
    """保存传书队列"""
    try:
        with open(queue_file, 'w', encoding='utf-8') as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存队列失败: {e}")

def convert_mobi_to_epub(mobi_path: Path) -> Optional[Path]:
    """将MOBI文件转换为EPUB"""
    import tempfile
    import shutil
    import zipfile
    import xml.etree.ElementTree as ET
    
    epub_path = mobi_path.with_suffix('.epub')
    temp_dir = None
    
    try:
        import mobi
        
        logger.info(f"开始转换MOBI文件: {mobi_path.name}")
        
        # 使用mobi库进行转换
        try:
            # mobi.extract函数返回一个元组 (temp_dir, extracted_file_path)
            result = mobi.extract(str(mobi_path))
            
            if isinstance(result, tuple) and len(result) == 2:
                temp_dir, extracted_file = result
                logger.info(f"mobi.extract返回: temp_dir={temp_dir}, file={extracted_file}")
                
                if extracted_file and os.path.exists(extracted_file):
                    # 检查文件类型
                    if extracted_file.endswith('.epub'):
                        # 如果是真正的EPUB文件，直接复制
                        shutil.copy2(extracted_file, epub_path)
                        logger.info(f"MOBI转换成功: {mobi_path.name} -> {epub_path.name}")
                    elif extracted_file.endswith('.html'):
                        # 如果是HTML文件，需要转换为EPUB
                        logger.info("检测到HTML文件，正在转换为EPUB格式...")
                        if html_to_epub(extracted_file, epub_path, mobi_path.stem):
                            logger.info(f"HTML转EPUB成功: {mobi_path.name} -> {epub_path.name}")
                        else:
                            raise Exception("HTML转EPUB失败")
                    else:
                        # 其他格式，直接复制
                        shutil.copy2(extracted_file, epub_path)
                        logger.info(f"文件复制成功: {mobi_path.name} -> {epub_path.name}")
                    
                    # 删除原MOBI文件
                    mobi_path.unlink()
                    return epub_path
                else:
                    raise Exception(f"提取的文件不存在: {extracted_file}")
            else:
                raise Exception(f"mobi.extract返回格式异常: {result}")
                
        except Exception as e:
            logger.warning(f"使用mobi库转换失败: {e}")
            # 转换失败，返回None
            return None
        
    except ImportError:
        logger.warning("mobi库未安装，无法转换MOBI文件")
        return None
    except Exception as e:
        logger.error(f"MOBI转换失败 {mobi_path}: {e}")
        return None
    finally:
        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug(f"已清理临时目录: {temp_dir}")
            except Exception as e:
                logger.warning(f"清理临时目录失败: {e}")

def html_to_epub(html_file: str, epub_path: Path, title: str) -> bool:
    """将HTML文件转换为EPUB格式"""
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        from datetime import datetime
        import uuid
        
        # 读取HTML内容
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # 生成唯一ID
        book_id = str(uuid.uuid4())
        
        # 创建EPUB结构
        with zipfile.ZipFile(epub_path, 'w', zipfile.ZIP_DEFLATED) as epub:
            # 1. 创建mimetype文件（必须第一个写入，且不压缩）
            epub.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
            
            # 2. 创建META-INF/container.xml
            container_xml = '''<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''
            epub.writestr('META-INF/container.xml', container_xml)
            
            # 3. 创建OEBPS/toc.ncx (导航文件)
            ncx_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle>
    <text>{title}</text>
  </docTitle>
  <navMap>
    <navPoint id="navpoint-1" playOrder="1">
      <navLabel>
        <text>正文</text>
      </navLabel>
      <content src="chapter1.html"/>
    </navPoint>
  </navMap>
</ncx>'''
            epub.writestr('OEBPS/toc.ncx', ncx_xml)
            
            # 4. 创建OEBPS/content.opf
            content_opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{title}</dc:title>
    <dc:creator>Unknown</dc:creator>
    <dc:language>zh</dc:language>
    <dc:identifier id="BookId">{book_id}</dc:identifier>
    <dc:date>{datetime.now().strftime('%Y-%m-%d')}</dc:date>
    <meta name="cover" content="cover"/>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="chapter1" href="chapter1.html" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chapter1"/>
  </spine>
  <guide>
    <reference type="text" title="正文" href="chapter1.html"/>
  </guide>
</package>'''
            epub.writestr('OEBPS/content.opf', content_opf)
            
            # 5. 创建OEBPS/chapter1.html
            # 清理HTML内容，确保是有效的XHTML
            # 移除可能的HTML声明和head/body标签，因为我们自己添加
            import re
            
            # 提取body内容
            body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL | re.IGNORECASE)
            if body_match:
                body_content = body_match.group(1)
            else:
                body_content = html_content
            
            # 提取title
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.IGNORECASE)
            if title_match:
                extracted_title = title_match.group(1).strip()
                if extracted_title:
                    title = extracted_title
            
            # 提取meta标签
            meta_tags = []
            meta_matches = re.findall(r'<meta[^>]*>', html_content, re.IGNORECASE)
            for meta in meta_matches:
                if 'charset' in meta.lower():
                    meta_tags.append(meta)
            
            # 构建完整的XHTML
            xhtml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{title}</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
    {''.join(meta_tags)}
    <style type="text/css">
        body {{ font-family: serif; line-height: 1.6; margin: 1em; }}
        p {{ margin: 0.5em 0; text-indent: 2em; }}
        h1, h2, h3, h4, h5, h6 {{ margin: 1em 0 0.5em 0; text-align: center; }}
    </style>
</head>
<body>
{body_content}
</body>
</html>'''
            epub.writestr('OEBPS/chapter1.html', xhtml_content)
            
        return True
        
    except Exception as e:
        logger.error(f"HTML转EPUB失败: {e}")
        return False


def convert_pdf_to_txt(pdf_path: Path) -> Optional[Path]:
    """将PDF文件转换为TXT"""
    try:
        import fitz  # PyMuPDF
        
        txt_path = pdf_path.with_suffix('.txt')
        
        logger.info(f"开始转换PDF文件: {pdf_path.name}")
        
        # 打开PDF文件
        doc = fitz.open(str(pdf_path))
        
        # 提取文本
        text_content = []
        total_pages = len(doc)
        
        for page_num in range(total_pages):
            page = doc.load_page(page_num)
            text = page.get_text()
            if text.strip():  # 只添加非空页面
                text_content.append(f"--- 第 {page_num + 1} 页 ---\n{text}")
        
        doc.close()
        
        if not text_content:
            logger.warning(f"PDF文件未提取到文本内容: {pdf_path.name}")
            return None
        
        # 写入文本文件
        full_text = f"PDF文件转换: {pdf_path.stem}\n"
        full_text += f"总页数: {total_pages}\n"
        full_text += "=" * 50 + "\n\n"
        full_text += "\n\n".join(text_content)
        
        with open(txt_path, 'w', encoding='utf-8') as txt_file:
            txt_file.write(full_text)
        
        # 删除原PDF文件
        pdf_path.unlink()
        
        logger.info(f"PDF转换成功: {pdf_path.name} -> {txt_path.name} (共 {total_pages} 页)")
        return txt_path
        
    except ImportError:
        logger.warning("PyMuPDF库未安装，无法转换PDF文件")
        return None
    except Exception as e:
        logger.error(f"PDF转换失败 {pdf_path}: {e}")
        return None

@app.route('/')
def index():
    """主页"""
    return send_from_directory('../templates', 'index.html')

@app.route('/static/js/<path:filename>')
def serve_static_js(filename):
    """提供JS静态文件"""
    return send_from_directory('../static/js', filename)

@app.route('/static/<path:filename>')
def serve_static_files(filename):
    """提供所有静态文件（包括生成的图片）"""
    # Flask会自动使用配置的static_folder
    # 记录请求以便调试
    logger.info(f"静态文件请求: /static/{filename}")

    # 直接使用send_from_directory，Flask会处理路径
    try:
        return send_from_directory(str(static_folder_path), filename)
    except FileNotFoundError:
        logger.error(f"文件不存在: {static_folder_path / filename}")
        return jsonify({'error': '文件不存在', 'path': str(filename)}), 404

@app.route('/api/convert', methods=['POST'])
def convert_file():
    """将文件转换为XTC格式"""
    try:
        # 检查是否有文件
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        # 检查文件格式
        allowed_extensions = {'.epub', '.pdf', '.png'}
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'message': f'不支持的文件格式，仅支持: {", ".join(allowed_extensions)}'}), 400

        # 创建临时目录保存上传的文件
        temp_dir = Path(tempfile.mkdtemp(prefix="convert_"))
        temp_file = temp_dir / file.filename
        file.save(str(temp_file))

        logger.info(f"文件上传成功，准备转换: {file.filename}")

        # 执行转换
        success, result = conversion_service.convert_to_xtc(temp_file)

        # 清理临时文件
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"清理临时目录失败: {e}")

        if success:
            # result 是输出文件路径
            output_path = Path(result)
            if output_path.exists():
                # 返回转换后的文件
                return send_from_directory(
                    str(output_path.parent),
                    output_path.name,
                    as_attachment=True,
                    download_name=file.filename.rsplit('.', 1)[0] + '.xtc'
                )
            else:
                return jsonify({'success': False, 'message': '转换后的文件不存在'}), 500
        else:
            # result 是错误消息
            return jsonify({'success': False, 'message': result}), 500

    except Exception as e:
        logger.error(f"文件转换失败: {e}")
        return jsonify({'success': False, 'message': f'转换失败: {str(e)}'}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """上传文件到传书队列"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        # 检查是否需要转换为XTC
        convert_to_xtc_flag = request.form.get('convert_to_xtc', 'false').lower() == 'true'

        # 检查文件格式
        allowed_extensions = {'.epub', '.txt', '.pdf', '.mobi', '.xtc'}
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'message': '不支持的文件格式'}), 400

        # 确保待传书目录存在
        pending_dir.mkdir(exist_ok=True)

        # 如果需要转换为XTC
        if convert_to_xtc_flag and file_ext in {'.epub', '.pdf', '.png'}:
            # 创建临时目录
            temp_dir = Path(tempfile.mkdtemp(prefix="upload_convert_"))
            temp_file = temp_dir / file.filename
            file.save(str(temp_file))

            logger.info(f"开始转换文件: {file.filename}")

            # 执行转换
            success, result = conversion_service.convert_to_xtc(temp_file)

            # 清理临时文件
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"清理临时目录失败: {e}")

            if not success:
                return jsonify({'success': False, 'message': f'转换失败: {result}'}), 500

            # 使用转换后的XTC文件
            xtc_path = Path(result)
            if not xtc_path.exists():
                return jsonify({'success': False, 'message': '转换后的文件不存在'}), 500

            # 直接保存到book目录
            current_dir = Path(__file__).parent.parent
            book_dir = current_dir / "book"
            book_dir.mkdir(exist_ok=True)

            # 生成文件名（使用时间戳和原文件名）
            timestamp = datetime.now().strftime('%m%d_%H%M')
            name_part = Path(file.filename).stem
            if len(name_part) > 20:
                name_part = name_part[:20]
            new_filename = f"{timestamp}_{name_part}.xtc"
            book_path = book_dir / new_filename

            # 复制转换后的文件到book目录
            shutil.copy2(str(xtc_path), str(book_path))
            file_size = book_path.stat().st_size

            # 添加到队列（使用book目录中的路径）
            queue_item = {
                'id': str(uuid.uuid4()),
                'original_name': file.filename,
                'name': new_filename,
                'path': str(book_path),
                'size': file_size,
                'status': 'pending',
                'upload_time': datetime.now().isoformat(),
                'message': '已转换并上传到book目录',
                'target_dir': '/XTEAILINK/books/'  # 指定传输到设备的books目录
            }

            queue = load_queue()
            queue.append(queue_item)
            save_queue(queue)

            logger.info(f"文件转换成功并保存到book目录: {file.filename} -> {new_filename}")

            # 返回成功响应
            return jsonify({
                'success': True,
                'message': f'文件转换并上传成功，已保存到book目录',
                'file_id': queue_item['id'],
                'filename': new_filename
            })

        else:
            # 不需要转换，直接保存文件
            # 生成唯一文件名（简化版本）
            file_id = str(uuid.uuid4())
            timestamp = datetime.now().strftime('%m%d_%H%M')
            name_part = Path(file.filename).stem
            # 限制文件名长度，最多保留原文件名前20个字符
            if len(name_part) > 20:
                name_part = name_part[:20]
            new_filename = f"{timestamp}_{name_part}_{file_id[:6]}{file_ext}"
            file_path = pending_dir / new_filename

            # 保存文件
            file.save(str(file_path))
            file_size = file_path.stat().st_size
        
        # 如果是MOBI文件，转换为EPUB
        if file_ext == '.mobi':
            epub_path = convert_mobi_to_epub(file_path)
            if epub_path:
                # 使用转换后的EPUB文件
                file_path = epub_path
                file_size = file_path.stat().st_size
                new_filename = file_path.name
        
        # 如果是PDF文件，转换为TXT
        elif file_ext == '.pdf':
            txt_path = convert_pdf_to_txt(file_path)
            if txt_path:
                # 使用转换后的TXT文件
                file_path = txt_path
                file_size = file_path.stat().st_size
                new_filename = file_path.name
        
        # 添加到队列
        queue_item = {
            'id': file_id,
            'original_name': file.filename,
            'name': new_filename,
            'path': str(file_path),
            'size': file_size,
            'status': 'pending',
            'upload_time': datetime.now().isoformat(),
            'message': ''
        }
        
        queue = load_queue()
        queue.append(queue_item)
        save_queue(queue)
        
        logger.info(f"文件上传成功: {file.filename} -> {new_filename}")
        
        return jsonify({
            'success': True,
            'message': '文件上传成功',
            'file_id': file_id,
            'filename': new_filename
        })
        
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'}), 500

@app.route('/api/queue', methods=['GET'])
def get_queue():
    """获取传书队列"""
    try:
        queue = load_queue()
        
        # 更新队列状态
        updated_queue = []
        for item in queue:
            file_path = Path(item['path'])
            if not file_path.exists():
                item['status'] = 'missing'
                item['message'] = '文件不存在'
            updated_queue.append(item)
        
        save_queue(updated_queue)
        
        return jsonify(updated_queue)
        
    except Exception as e:
        logger.error(f"获取队列失败: {e}")
        return jsonify({'success': False, 'message': f'获取队列失败: {str(e)}'}), 500

@app.route('/api/queue/<item_id>', methods=['DELETE'])
def remove_from_queue(item_id):
    """从队列中删除指定项目"""
    try:
        queue = load_queue()
        
        # 找到并删除项目
        item_found = False
        new_queue = []
        for item in queue:
            if item['id'] == item_id:
                # 删除文件
                try:
                    file_path = Path(item['path'])
                    if file_path.exists():
                        file_path.unlink()
                        logger.info(f"删除文件: {file_path}")
                except Exception as e:
                    logger.warning(f"删除文件失败 {file_path}: {e}")
                item_found = True
            else:
                new_queue.append(item)
        
        if not item_found:
            return jsonify({'success': False, 'message': '项目不存在'}), 404
        
        save_queue(new_queue)
        
        return jsonify({'success': True, 'message': '已从队列中删除'})
        
    except Exception as e:
        logger.error(f"删除队列项目失败: {e}")
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500

@app.route('/api/queue', methods=['DELETE'])
def clear_queue():
    """清空传书队列"""
    try:
        queue = load_queue()
        
        # 删除所有文件
        for item in queue:
            try:
                file_path = Path(item['path'])
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"删除文件: {file_path}")
            except Exception as e:
                logger.warning(f"删除文件失败 {file_path}: {e}")
        
        # 清空队列
        save_queue([])
        
        return jsonify({'success': True, 'message': '队列已清空'})
        
    except Exception as e:
        logger.error(f"清空队列失败: {e}")
        return jsonify({'success': False, 'message': f'清空失败: {str(e)}'}), 500

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """获取设备设置"""
    try:
        if transfer_service:
            config = transfer_service.config
            return jsonify({
                'ip': config['device']['ip'],
                'port': config['device']['port']
            })
        else:
            # 从配置文件直接读取
            with open('config/config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            return jsonify({
                'ip': config['device']['ip'],
                'port': config['device']['port']
            })
    except Exception as e:
        logger.error(f"获取设置失败: {e}")
        return jsonify({'success': False, 'message': f'获取设置失败: {str(e)}'}), 500

@app.route('/api/settings', methods=['POST'])
def save_settings():
    """保存设备设置"""
    try:
        data = request.get_json()
        if not data or 'ip' not in data or 'port' not in data:
            return jsonify({'success': False, 'message': '参数不完整'}), 400
        
        # 读取配置文件
        with open('config/config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 更新配置
        config['device']['ip'] = data['ip']
        config['device']['port'] = int(data['port'])
        
        # 保存配置文件
        with open('config/config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # 重新初始化传书服务
        init_transfer_service()
        
        logger.info(f"设置已更新: IP={data['ip']}, Port={data['port']}")
        
        return jsonify({'success': True, 'message': '设置已保存'})
        
    except Exception as e:
        logger.error(f"保存设置失败: {e}")
        return jsonify({'success': False, 'message': f'保存设置失败: {str(e)}'}), 500

@app.route('/api/device/status', methods=['GET'])
def check_device_status():
    """检查设备连接状态"""
    try:
        if not transfer_service:
            return jsonify({'connected': False, 'message': '传书服务未初始化'})
        
        connected = transfer_service.check_device_connection()
        
        # 如果设备连接正常，尝试传书
        if connected:
            try:
                transferred_count = transfer_service.run_once()
                if transferred_count > 0:
                    logger.info(f"自动传书完成，成功传输 {transferred_count} 本书籍")
                    return jsonify({
                        'connected': True,
                        'message': f'设备连接正常，已传输 {transferred_count} 本书籍',
                        'transferred_count': transferred_count
                    })
            except Exception as e:
                logger.error(f"自动传书失败: {e}")
                return jsonify({
                    'connected': True,
                    'message': f'设备连接正常，但传书失败: {str(e)}'
                })
        
        return jsonify({
            'connected': connected,
            'message': '设备连接正常' if connected else '设备未连接'
        })
        
    except Exception as e:
        logger.error(f"检查设备状态失败: {e}")
        return jsonify({'connected': False, 'message': f'检查失败: {str(e)}'})

@app.route('/api/transfer/start', methods=['POST'])
def start_transfer():
    """手动开始传书"""
    try:
        if not transfer_service:
            return jsonify({'success': False, 'message': '传书服务未初始化'}), 500
        
        # 执行一次传书
        transferred_count = transfer_service.run_once()
        
        return jsonify({
            'success': True,
            'message': f'传书完成，成功传输 {transferred_count} 本书籍',
            'transferred_count': transferred_count
        })
        
    except Exception as e:
        logger.error(f"手动传书失败: {e}")
        return jsonify({'success': False, 'message': f'传书失败: {str(e)}'}), 500

@app.route('/api/mcp/status', methods=['GET'])
def mcp_status():
    """获取MCP服务器状态"""
    try:
        return jsonify({
            'success': True,
            'mcp_running': mcp_thread is not None and mcp_thread.is_alive(),
            'mcp_port': 8099,
            'mcp_path': '/mcp'
        })
    except Exception as e:
        logger.error(f"获取MCP状态失败: {e}")
        return jsonify({'success': False, 'message': f'获取MCP状态失败: {str(e)}'}), 500

@app.route('/api/chat/config', methods=['GET'])
def get_chat_config():
    """获取AI聊天配置"""
    try:
        chat_service = get_chat_service()
        return jsonify(chat_service.get_config())
    except Exception as e:
        logger.error(f"获取聊天配置失败: {e}")
        return jsonify({'success': False, 'message': f'获取配置失败: {str(e)}'}), 500

@app.route('/api/chat/config', methods=['POST'])
def update_chat_config():
    """更新AI聊天配置"""
    try:
        data = request.get_json()
        logger.info(f"收到AI配置更新请求")
        logger.info(f"  - enabled: {data.get('enabled')}")
        logger.info(f"  - openai configured: {bool(data.get('openai', {}).get('base_url'))}")
        logger.info(f"  - mcp_servers count: {len(data.get('mcp_servers', []))}")
        logger.info(f"  - image_generation configured: {bool(data.get('image_generation', {}).get('base_url'))}")

        # 打印MCP服务器详情（不包含敏感信息）
        if data.get('mcp_servers'):
            for i, server in enumerate(data.get('mcp_servers', [])):
                has_header = server.get('has_header', False)
                custom_header_val = server.get('custom_header', '')
                logger.info(f"  - MCP Server {i+1}: name={server.get('name')}, url={server.get('url')}, has_header={has_header}, custom_header_len={len(custom_header_val)}")

        chat_service = get_chat_service()

        if chat_service.update_config(data):
            logger.info("AI配置更新成功")
            return jsonify({'success': True, 'message': '配置已更新'})
        else:
            logger.error("AI配置更新失败(返回False)")
            return jsonify({'success': False, 'message': '更新配置失败,请查看服务器日志'}), 500

    except Exception as e:
        logger.error(f"更新聊天配置失败: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'更新配置失败: {str(e)}'}), 500

@app.route('/api/chat/test', methods=['GET'])
def test_chat_connection():
    """测试AI服务连接"""
    try:
        chat_service = get_chat_service()
        result = chat_service.test_connection()
        return jsonify(result)
    except Exception as e:
        logger.error(f"测试连接失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    """AI聊天接口"""
    async def _chat():
        try:
            data = request.get_json()
            message = data.get('message', '').strip()

            if not message:
                return jsonify({'success': False, 'message': '消息不能为空'}), 400

            chat_service = get_chat_service()
            conversation_history = data.get('history', [])

            result = await chat_service.chat(message, conversation_history)

            return jsonify(result)

        except Exception as e:
            logger.error(f"聊天请求失败: {e}")
            return jsonify({'success': False, 'message': f'聊天失败: {str(e)}'}), 500

    return asyncio.run(_chat())


@app.route('/api/generate-image', methods=['POST'])
def generate_image():
    """图片生成接口（支持实时进度推送）"""
    data = request.get_json()
    prompt = data.get('prompt', '').strip()
    session_id = data.get('session_id', '')

    if not prompt:
        return jsonify({'success': False, 'message': '提示词不能为空'}), 400

    def generate():
        try:
            from tool.image_tool import generate_slide_image
            import uuid

            if not session_id:
                session_id = str(uuid.uuid4())[:8]

            # 存储进度信息的队列
            progress_queue = []

            # 进度回调函数
            def progress_callback(status, message, data=None):
                event_data = {
                    'type': 'progress',
                    'status': status,
                    'message': message
                }
                if data:
                    event_data['data'] = data
                progress_queue.append(json.dumps(event_data))

            # 在后台线程中生成图片
            import threading
            result = {'error': None, 'image_path': None}

            def generate_in_thread():
                try:
                    image_path = generate_slide_image(
                        prompt=prompt,
                        slide_index=1,
                        session_id=session_id,
                        progress_callback=progress_callback
                    )
                    result['image_path'] = image_path
                except Exception as e:
                    logger.error(f"生图失败: {e}")
                    result['error'] = str(e)

            thread = threading.Thread(target=generate_in_thread)
            thread.start()

            # 轮询进度
            import time
            last_index = 0
            while thread.is_alive():
                if last_index < len(progress_queue):
                    for i in range(last_index, len(progress_queue)):
                        yield f"data: {progress_queue[i]}\n\n"
                    last_index = len(progress_queue)
                time.sleep(0.1)

            # 发送剩余的进度
            if last_index < len(progress_queue):
                for i in range(last_index, len(progress_queue)):
                    yield f"data: {progress_queue[i]}\n\n"

            # 发送最终结果
            if result['error']:
                yield f"data: {json.dumps({'type': 'error', 'message': result['error']})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'complete', 'image_path': result['image_path']})}\n\n"

        except Exception as e:
            logger.error(f"生图请求处理失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': f'请求处理失败: {str(e)}'})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/generated-images', methods=['GET'])
def get_generated_images():
    """获取会话生成的图片列表"""
    try:
        session_id = request.args.get('session_id', 'default')

        # 扫描static/output/{session_id}目录
        output_dir = Path("static/output") / session_id

        if not output_dir.exists():
            return jsonify({'images': []})

        images = []
        for image_file in sorted(output_dir.glob("*.jpg")):
            images.append({
                'path': f"/static/output/{session_id}/{image_file.name}",
                'name': image_file.name,
                'created': image_file.stat().st_mtime
            })

        return jsonify({'images': images})

    except Exception as e:
        logger.error(f"获取图片列表失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

def init_directories():
    """初始化必要的目录"""
    directories = [
        pending_dir,
        Path("data/notes"),  # MCP服务器使用的目录
    ]
    
    for directory in directories:
        directory.mkdir(exist_ok=True)
        logger.info(f"目录已创建: {directory}")

if __name__ == '__main__':
    logger.info("启动XTEAILINK Web服务器")
    
    # 初始化目录
    init_directories()
    
    # 初始化传书服务
    init_transfer_service()
    
    # 初始化MCP服务器
    init_mcp_server()
    
    # 启动Web服务器
    logger.info("Web服务器监听端口: 8098")
    logger.info("MCP服务器监听端口: 8099")
    app.run(host='0.0.0.0', port=8098, debug=True, use_reloader=False)
