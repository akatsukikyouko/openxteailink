#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XTEAILINK 传书服务
自动检测设备连接并传输电子书到微型电子纸设备
"""

import json
import os
import time
import requests
import logging
from pathlib import Path
from typing import List, Optional, Dict
from urllib.parse import urljoin

class BookTransferService:
    def __init__(self, config_path: str = "config/config.json"):
        """初始化传书服务"""
        self.config_path = config_path
        self.config = self._load_config()
        self.setup_logging()
        self.session = requests.Session()
        self.session.timeout = 10
        
        # 创建待传书目录
        self.pending_dir = Path(self.config["transfer"]["pending_books_dir"])
        self.pending_dir.mkdir(exist_ok=True)
        
        # 队列文件路径
        self.queue_file = Path(self.config["paths"]["queue_file"])
        
        self.logger.info("传书服务初始化完成")
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            raise
    
    def setup_logging(self):
        """设置日志"""
        # 确保日志目录存在
        log_dir = Path(self.config.get("paths", {}).get("log_dir", "./logs"))
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / "book_transfer.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(str(log_file), encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def get_device_url(self, endpoint: str = "") -> str:
        """获取设备API URL"""
        base_url = f"http://{self.config['device']['ip']}:{self.config['device']['port']}"
        return urljoin(base_url, endpoint)
    
    def check_device_connection(self) -> bool:
        """检测设备是否连接（通过访问/edit端点）"""
        try:
            url = self.get_device_url("/edit")
            response = self.session.get(url, timeout=5)
            connected = response.status_code == 200
            if connected:
                self.logger.info("设备连接正常")
            return connected
        except requests.exceptions.RequestException:
            # 设备未连接是常态，不输出警告信息
            return False
    
    def check_directory_exists(self, dir_path: str) -> bool:
        """检查目录是否存在"""
        try:
            # 确保路径以/开头
            if not dir_path.startswith("/"):
                dir_path = "/" + dir_path
            # 确保目录路径以/结尾
            if not dir_path.endswith("/"):
                dir_path = dir_path + "/"
            
            self.logger.info(f"检查目录存在性: {dir_path}")
            
            # 特殊处理：如果是XTEAILINK根目录，检查根目录下是否有XTEAILINK目录
            if dir_path == "/XTEAILINK/":
                url = self.get_device_url("/list")
                params = {'dir': '/'}
                response = self.session.get(url, params=params, timeout=5)
                
                self.logger.info(f"检查XTEAILINK目录，状态码: {response.status_code}")
                
                if response.status_code != 200:
                    self.logger.info(f"根目录访问失败")
                    return False
                
                try:
                    items = response.json()
                    self.logger.info(f"根目录包含 {len(items)} 个项目")
                    
                    # 检查根目录下是否有XTEAILINK目录
                    for item in items:
                        self.logger.info(f"检查项目: {item}")
                        if item.get('type') == 'dir' and item.get('name') == 'XTEAILINK':
                            self.logger.info(f"找到XTEAILINK目录！")
                            return True
                    
                    self.logger.info(f"XTEAILINK目录不存在")
                    return False
                except Exception as e:
                    self.logger.info(f"根目录解析失败: {e}")
                    return False
            # 如果是XTEAILINK的子目录，需要检查XTEAILINK目录下的内容
            elif dir_path.startswith("/XTEAILINK/"):
                # 先检查XTEAILINK目录是否存在
                base_dir = "/XTEAILINK/"
                url = self.get_device_url("/list")
                params = {'dir': base_dir}
                response = self.session.get(url, params=params, timeout=5)
                
                if response.status_code != 200:
                    self.logger.info(f"XTEAILINK目录不存在")
                    return False
                
                try:
                    items = response.json()
                    # 获取子目录名（去掉路径前缀和斜杠）
                    subdir_name = dir_path.replace("/XTEAILINK/", "").rstrip("/")
                    
                    # 检查子目录是否在列表中
                    for item in items:
                        if item.get('type') == 'dir' and item.get('name') == subdir_name:
                            self.logger.info(f"子目录 {dir_path} 存在")
                            return True
                    
                    self.logger.info(f"子目录 {dir_path} 不存在")
                    return False
                except:
                    self.logger.info(f"XTEAILINK目录解析失败")
                    return False
            else:
                # 对于其他目录，直接检查
                url = self.get_device_url("/list")
                params = {'dir': dir_path}
                response = self.session.get(url, params=params, timeout=5)
                
                if response.status_code == 200:
                    try:
                        items = response.json()
                        self.logger.info(f"目录 {dir_path} 存在，包含 {len(items)} 个项目")
                        return True
                    except:
                        self.logger.info(f"目录 {dir_path} 不存在")
                        return False
                else:
                    self.logger.info(f"目录 {dir_path} 不存在，状态码: {response.status_code}")
                    return False
                
        except Exception as e:
            self.logger.info(f"检查目录存在性失败 {dir_path}: {e}")
            return False
    
    def create_directory(self, dir_path: str) -> bool:
        """创建目录（如果不存在）"""
        try:
            # 确保路径以/开头
            if not dir_path.startswith("/"):
                dir_path = "/" + dir_path
            # 确保目录路径以/结尾
            if not dir_path.endswith("/"):
                dir_path = dir_path + "/"
            
            # 先检查目录是否已存在
            if self.check_directory_exists(dir_path):
                return True
                
            self.logger.info(f"创建目录: {dir_path}")
            data = {
                'path': dir_path
            }
            
            url = self.get_device_url("/edit")
            response = self.session.put(url, data=data)
            
            if response.status_code == 200:
                self.logger.info(f"目录 {dir_path} 创建成功")
                return True
            else:
                self.logger.error(f"创建目录失败 {dir_path}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"创建目录异常 {dir_path}: {e}")
            return False
    
    def setup_device_directories(self) -> bool:
        """设置设备目录结构"""
        self.logger.info("开始设置设备目录结构")
        
        directories = [
            self.config["directories"]["base"],
            self.config["directories"]["news"],
            self.config["directories"]["notes"],
            self.config["directories"]["books"],
            self.config["directories"]["website"]
        ]
        
        success_count = 0
        for directory in directories:
            if self.create_directory(directory):
                success_count += 1
        
        if success_count == len(directories):
            self.logger.info("所有目录创建成功")
            return True
        else:
            self.logger.warning(f"部分目录创建失败: {success_count}/{len(directories)}")
            return False
    
    def get_pending_books(self) -> List[Path]:
        """获取待传输的书籍列表"""
        supported_formats = self.config["transfer"]["supported_formats"]
        pending_books = []
        
        for file_path in self.pending_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                pending_books.append(file_path)
        
        self.logger.info(f"找到 {len(pending_books)} 本待传书籍")
        return pending_books
    
    def get_queue_items(self) -> List[Dict]:
        """获取队列中的待传文件"""
        if not self.queue_file.exists():
            self.logger.info("队列文件不存在")
            return []
        
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                queue = json.load(f)
            
            # 过滤出pending状态的文件
            pending_items = [item for item in queue if item.get('status') == 'pending']
            self.logger.info(f"队列中找到 {len(pending_items)} 个待传文件")
            return pending_items
        except Exception as e:
            self.logger.error(f"读取队列文件失败: {e}")
            return []
    
    def update_queue_status(self, item_id: str, status: str, message: str = ""):
        """更新队列中文件的状态"""
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                queue = json.load(f)
            
            # 找到对应的队列项并更新状态
            for item in queue:
                if item.get('id') == item_id:
                    item['status'] = status
                    if message:
                        item['message'] = message
                    break
            
            # 保存更新后的队列
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(queue, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"已更新队列项 {item_id} 状态为: {status}")
        except Exception as e:
            self.logger.error(f"更新队列状态失败: {e}")
    
    def upload_file(self, file_path: Path, target_dir: str) -> bool:
        """上传文件到设备（带重试机制）"""
        max_retries = self.config["transfer"]["retry"]["max_retries"]
        retry_delay = self.config["transfer"]["retry"]["retry_delay"]

        for attempt in range(max_retries):
            try:
                filename = file_path.name
                # 确保目标目录以/结尾
                if not target_dir.endswith('/'):
                    target_dir = target_dir + '/'
                target_path = f"{target_dir}{filename}"

                if attempt > 0:
                    self.logger.warning(f"重试上传文件 (第{attempt}次): {filename} -> {target_path}")
                else:
                    self.logger.info(f"准备上传文件: {filename} -> {target_path}")

                with open(file_path, 'rb') as f:
                    # 使用FormData格式，模拟JavaScript的FormData.append("data", file, path)
                    # 在requests中，我们需要将文件数据和路径信息正确组合
                    files = {
                        'data': (target_path, f, 'application/octet-stream')  # 使用完整路径作为文件名
                    }

                    url = self.get_device_url("/edit")
                    response = self.session.post(url, files=files)

                    self.logger.info(f"上传响应状态码: {response.status_code}")
                    if response.text:
                        self.logger.info(f"上传响应内容: {response.text}")

                    if response.status_code == 200:
                        self.logger.info(f"文件上传成功: {filename} -> {target_path}")
                        return True
                    else:
                        self.logger.error(f"文件上传失败 {filename}: {response.status_code} - {response.text}")

                        # 如果还有重试机会，等待后重试
                        if attempt < max_retries - 1:
                            self.logger.info(f"等待 {retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                        else:
                            self.logger.error(f"文件上传失败，已达最大重试次数 ({max_retries}): {filename}")
                            return False

            except Exception as e:
                self.logger.error(f"文件上传异常 {file_path}: {e}")

                # 如果还有重试机会，等待后重试
                if attempt < max_retries - 1:
                    self.logger.info(f"等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                else:
                    self.logger.error(f"文件上传异常，已达最大重试次数 ({max_retries}): {file_path}")
                    return False

        return False
    
    def transfer_pending_books(self) -> int:
        """传输待传书籍"""
        pending_books = self.get_pending_books()
        if not pending_books:
            self.logger.info("没有待传书籍")
            return 0
        
        books_dir = self.config["directories"]["books"]
        success_count = 0
        
        for book_path in pending_books:
            self.logger.info(f"开始传输: {book_path.name}")
            if self.upload_file(book_path, books_dir):
                success_count += 1
                # 传输成功后移动到已传目录或删除
                try:
                    book_path.unlink()  # 删除原文件
                    self.logger.info(f"已删除已传文件: {book_path.name}")
                except Exception as e:
                    self.logger.warning(f"删除文件失败 {book_path}: {e}")
            else:
                self.logger.error(f"传输失败: {book_path.name}")
        
        self.logger.info(f"传输完成: {success_count}/{len(pending_books)} 本书籍成功")
        return success_count
    
    def transfer_queue_items(self) -> int:
        """传输队列中的文件"""
        queue_items = self.get_queue_items()
        if not queue_items:
            self.logger.info("队列中没有待传文件")
            return 0
        
        success_count = 0
        
        for item in queue_items:
            item_id = item.get('id')
            file_path = Path(item.get('path'))
            target_dir = item.get('target_dir', '/XTEAILINK/notes/')
            
            if not file_path.exists():
                self.logger.warning(f"队列文件不存在: {file_path}")
                self.update_queue_status(item_id, 'failed', f'文件不存在: {file_path}')
                continue
            
            self.logger.info(f"开始传输队列文件: {file_path.name}")
            if self.upload_file(file_path, target_dir):
                success_count += 1
                self.update_queue_status(item_id, 'completed', '传输成功')
                # 传输成功后删除原文件
                try:
                    file_path.unlink()
                    self.logger.info(f"已删除已传文件: {file_path.name}")
                except Exception as e:
                    self.logger.warning(f"删除文件失败 {file_path}: {e}")
            else:
                self.logger.error(f"队列文件传输失败: {file_path.name}")
                self.update_queue_status(item_id, 'failed', '传输失败')
        
        self.logger.info(f"队列传输完成: {success_count}/{len(queue_items)} 个文件成功")
        return success_count
    
    def run_once(self) -> bool:
        """执行一次完整的检测和传输流程"""
        # 重新加载配置文件以获取最新设置
        try:
            old_config = self.config.copy()
            self.config = self._load_config()
            
            # 检查配置是否有变化
            if old_config != self.config:
                self.logger.info("检测到配置文件更新，重新加载配置")
                
                # 更新待传书目录
                new_pending_dir = Path(self.config["transfer"]["pending_books_dir"])
                if new_pending_dir != self.pending_dir:
                    self.pending_dir = new_pending_dir
                    self.pending_dir.mkdir(exist_ok=True)
                    self.logger.info(f"待传书目录更新为: {self.pending_dir}")
                
                # 更新检测间隔
                check_interval = self.config["device"]["check_interval"]
                self.logger.info(f"检测间隔更新为: {check_interval}秒")
                
        except Exception as e:
            self.logger.error(f"重新加载配置失败: {e}")
            # 使用之前的配置继续运行
        
        self.logger.info("开始执行检测流程")
        
        # 检测设备连接
        if not self.check_device_connection():
            self.logger.info("设备未连接，等待下次检测")
            return False
        
        # 设置目录结构
        if not self.setup_device_directories():
            self.logger.error("目录设置失败，跳过传输")
            return False
        
        # 传输待传书籍（传统方式）
        books_transferred = self.transfer_pending_books()
        
        # 传输队列中的文件（MCP方式）
        queue_transferred = self.transfer_queue_items()
        
        total_transferred = books_transferred + queue_transferred
        if total_transferred > 0:
            self.logger.info(f"本次传输完成: {total_transferred} 个文件")
        
        return total_transferred > 0
    
    def run(self):
        """运行主循环"""
        self.logger.info("传书服务启动")
        
        try:
            while True:
                try:
                    self.run_once()
                except Exception as e:
                    self.logger.error(f"执行流程异常: {e}")
                
                # 使用最新的配置获取检测间隔
                check_interval = self.config["device"]["check_interval"]
                self.logger.info(f"等待 {check_interval} 秒后进行下次检测")
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            self.logger.info("服务被用户中断")
        except Exception as e:
            self.logger.error(f"服务运行异常: {e}")
        finally:
            self.logger.info("传书服务停止")

def main():
    """主函数"""
    service = BookTransferService()
    service.run()

if __name__ == "__main__":
    main()
