#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube 视频发布脚本

使用 YouTube Data API v3 上传视频

使用方法:
    python youtube_publisher.py <video_path> <title> <description_file> [--public]
    
示例:
    python youtube_publisher.py ~/clawd/newsletters/2026-01-27-video.mp4 \
        "美股日报 2026.01.27" \
        ~/clawd/newsletters/2026-01-27-youtube-desc.md
        
环境变量:
    YOUTUBE_OAUTH_B64 - YouTube OAuth 凭据 (base64 编码的 JSON)
    
首次设置:
    1. 在 Google Cloud Console 创建项目并启用 YouTube Data API v3
    2. 创建 OAuth 2.0 客户端凭据
    3. 运行 export_youtube_oauth.py 获取 YOUTUBE_OAUTH_B64
    4. 将 YOUTUBE_OAUTH_B64 添加到 .env 文件
"""

import os
import sys
import json
import base64
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

# ============== 配置 ==============

# YouTube 类别 ID
# 22 = People & Blogs
# 27 = Education
# 28 = Science & Technology
DEFAULT_CATEGORY_ID = "22"

# OAuth 凭据文件路径 (备选)
OAUTH_FILE_PATH = Path("/Users/xuemeizhao/Downloads/add-caption/notebooklm_video/youtube_oauth.txt")

# ============== 日志工具 ==============

class Logger:
    @staticmethod
    def info(msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ℹ️  {msg}")
    
    @staticmethod
    def success(msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {msg}")
    
    @staticmethod
    def warning(msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  {msg}")
    
    @staticmethod
    def error(msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ {msg}")

log = Logger()

# ============== 凭据加载 ==============

def load_youtube_credentials():
    """加载 YouTube OAuth 凭据"""
    
    # 尝试从环境变量加载
    oauth_b64 = os.getenv("YOUTUBE_OAUTH_B64")
    
    # 如果环境变量没有，尝试从文件加载
    if not oauth_b64 and OAUTH_FILE_PATH.exists():
        try:
            content = OAUTH_FILE_PATH.read_text().strip()
            if "YOUTUBE_OAUTH_B64=" in content:
                oauth_b64 = content.split("YOUTUBE_OAUTH_B64=")[1].strip()
            else:
                oauth_b64 = content
            log.info(f"从文件加载 YouTube 凭据: {OAUTH_FILE_PATH}")
        except Exception as e:
            log.error(f"读取凭据文件失败: {e}")
    
    if not oauth_b64:
        log.error("YouTube 凭据未设置！")
        log.error("请设置 YOUTUBE_OAUTH_B64 环境变量或运行 export_youtube_oauth.py")
        return None
    
    try:
        # 添加 padding 如果需要
        padding = 4 - len(oauth_b64) % 4
        if padding != 4:
            oauth_b64 += '=' * padding
        oauth_data = json.loads(base64.b64decode(oauth_b64))
        
        from google.oauth2.credentials import Credentials
        
        credentials = Credentials(
            token=oauth_data.get("token"),
            refresh_token=oauth_data.get("refresh_token"),
            token_uri=oauth_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=oauth_data.get("client_id"),
            client_secret=oauth_data.get("client_secret"),
            scopes=oauth_data.get("scopes", ["https://www.googleapis.com/auth/youtube.upload"])
        )
        
        if credentials.refresh_token:
            log.success("YouTube 凭据加载成功 (有 refresh_token)")
        else:
            log.warning("YouTube 凭据加载成功 (无 refresh_token，可能会过期)")
        
        return credentials
        
    except Exception as e:
        log.error(f"解析 YouTube 凭据失败: {e}")
        return None

# ============== 视频上传 ==============

def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: Optional[list] = None,
    category_id: str = DEFAULT_CATEGORY_ID,
    privacy_status: str = "public"  # public, unlisted, private
) -> Optional[str]:
    """
    上传视频到 YouTube
    
    Args:
        video_path: 视频文件路径
        title: 视频标题 (最多 100 字符)
        description: 视频描述 (最多 5000 字符)
        tags: 标签列表
        category_id: YouTube 类别 ID
        privacy_status: 隐私状态 (private/unlisted/public)
    
    Returns:
        视频 URL 或 None (失败时)
    """
    
    # 检查依赖
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        log.error("请安装依赖: pip install google-api-python-client google-auth-oauthlib")
        return None
    
    # 检查文件
    if not os.path.exists(video_path):
        log.error(f"视频文件不存在: {video_path}")
        return None
    
    # 加载凭据
    credentials = load_youtube_credentials()
    if not credentials:
        return None
    
    log.info("=" * 50)
    log.info("YouTube 视频上传")
    log.info("=" * 50)
    log.info(f"视频: {video_path}")
    log.info(f"标题: {title[:50]}...")
    log.info(f"隐私: {privacy_status}")
    log.info("=" * 50)
    
    try:
        # 构建 YouTube API 客户端
        youtube = build("youtube", "v3", credentials=credentials)
        
        # 准备元数据
        body = {
            "snippet": {
                "title": title[:100],  # YouTube 标题限制 100 字符
                "description": description[:5000],  # 描述限制 5000 字符
                "tags": tags or [],
                "categoryId": category_id
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }
        
        # 创建上传请求
        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024  # 1MB chunks
        )
        
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        
        # 执行上传（支持断点续传）
        log.info("开始上传...")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                log.info(f"上传进度: {progress}%")
        
        video_id = response.get("id")
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        log.success("=" * 50)
        log.success("🎉 上传成功！")
        log.success(f"视频 ID: {video_id}")
        log.success(f"视频 URL: {video_url}")
        log.success("=" * 50)
        
        return video_url
        
    except Exception as e:
        log.error(f"上传失败: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============== 生成默认描述 ==============

def generate_default_description(date: str, stocks_file: Optional[str] = None) -> str:
    """生成默认的 YouTube 描述"""
    
    stocks_info = ""
    if stocks_file and os.path.exists(stocks_file):
        try:
            with open(stocks_file, 'r', encoding='utf-8') as f:
                stocks_info = f.read()
        except:
            pass
    
    description = f"""📈 美股日报 {date}

每日美股热点速递，AI 生成深度解析。

{stocks_info}

---

⏰ 时间戳:
0:00 开场
0:30 今日热点概览
...

---

📌 关注频道获取每日更新！

🔔 开启通知，不错过任何一期

---

⚠️ 免责声明:
本视频所有观点均来自原始分析文章，不代表本频道立场。
我们不对任何股票做高估/低估判断，也不提供投资建议。
投资有风险，请谨慎决策。

---

#美股 #股票 #投资 #财经 #每日复盘 #AI分析
"""
    return description

# ============== CLI 入口 ==============

def main():
    parser = argparse.ArgumentParser(description='YouTube 视频发布工具')
    parser.add_argument('video_path', help='视频文件路径')
    parser.add_argument('title', help='视频标题')
    parser.add_argument('--description', '-d', help='描述文件路径或直接描述文本')
    parser.add_argument('--tags', '-t', nargs='+', default=[], help='标签列表')
    parser.add_argument('--private', action='store_true', help='设为私密 (默认公开)')
    parser.add_argument('--unlisted', action='store_true', help='设为不公开列表')
    parser.add_argument('--category', default=DEFAULT_CATEGORY_ID, help='类别 ID (默认: 22)')
    
    args = parser.parse_args()
    
    # 确定隐私状态
    if args.private:
        privacy = "private"
    elif args.unlisted:
        privacy = "unlisted"
    else:
        privacy = "public"
    
    # 处理描述
    description = ""
    if args.description:
        if os.path.exists(args.description):
            with open(args.description, 'r', encoding='utf-8') as f:
                description = f.read()
        else:
            description = args.description
    else:
        # 从标题提取日期生成默认描述
        import re
        date_match = re.search(r'(\d{4})[.-](\d{2})[.-](\d{2})', args.title)
        if date_match:
            date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
        else:
            date = datetime.now().strftime("%Y-%m-%d")
        description = generate_default_description(date)
    
    # 默认标签
    default_tags = ["美股", "股票", "投资", "财经", "每日复盘", "AI"]
    tags = args.tags if args.tags else default_tags
    
    # 上传
    video_path = os.path.expanduser(args.video_path)
    result = upload_video(
        video_path=video_path,
        title=args.title,
        description=description,
        tags=tags,
        category_id=args.category,
        privacy_status=privacy
    )
    
    if result:
        log.success(f"发布完成: {result}")
        sys.exit(0)
    else:
        log.error("发布失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
