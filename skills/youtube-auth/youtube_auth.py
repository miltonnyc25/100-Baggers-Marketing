#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube OAuth 认证脚本

获取 YouTube API 认证凭据，生成 YOUTUBE_OAUTH_B64 环境变量

使用方法:
    python youtube_auth.py [--test]
    
选项:
    --test    认证后上传测试视频验证账号
    
前置条件:
    1. 需要 Google Cloud 项目的 client_secrets.json
    2. 已启用 YouTube Data API v3
"""

import os
import sys
import json
import base64
import time
import argparse
from pathlib import Path
from datetime import datetime

# ============== 配置 ==============

SCRIPT_DIR = Path(__file__).parent
CLAWD_DIR = Path("/Users/xuemeizhao/clawd")

# client_secrets.json 可能的位置
CLIENT_SECRETS_PATHS = [
    SCRIPT_DIR / "client_secrets.json",
    CLAWD_DIR / "secrets" / "client_secrets.json",
    Path("/Users/xuemeizhao/Downloads/add-caption/notebooklm_video/client_secrets.json"),
]

# 输出路径
OUTPUT_PATH = SCRIPT_DIR / "youtube_oauth.txt"
ENV_FILE_PATH = CLAWD_DIR / ".env"

# YouTube API 权限范围
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# 测试视频路径
TEST_VIDEO_PATH = Path("/Users/xuemeizhao/Downloads/add-caption/test_pixel.mp4")

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

# ============== 查找 client_secrets.json ==============

def find_client_secrets() -> Path:
    """查找 client_secrets.json 文件"""
    for path in CLIENT_SECRETS_PATHS:
        if path.exists():
            log.info(f"找到 client_secrets.json: {path}")
            return path
    
    log.error("未找到 client_secrets.json")
    log.info("请将 client_secrets.json 放置在以下位置之一:")
    for path in CLIENT_SECRETS_PATHS:
        print(f"  - {path}")
    sys.exit(1)

# ============== OAuth 认证 ==============

def authorize() -> dict:
    """执行 OAuth 认证流程"""
    from google_auth_oauthlib.flow import InstalledAppFlow
    
    client_secrets_path = find_client_secrets()
    
    print("\n" + "=" * 60)
    print("YouTube OAuth 认证")
    print("=" * 60)
    
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secrets_path), 
        SCOPES
    )
    
    log.info("即将打开浏览器进行认证...")
    print("\n[步骤 1] 浏览器将打开 Google 登录页面")
    print("[步骤 2] 选择要授权的 YouTube 账号")
    print("[步骤 3] 点击 '允许' 授予权限\n")
    
    # 强制账号选择
    credentials = flow.run_local_server(
        port=8080,
        prompt='select_account consent',
        access_type='offline'
    )
    
    log.success("OAuth 认证成功！")
    
    # 构建凭据数据
    oauth_data = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': list(credentials.scopes)
    }
    
    return oauth_data, credentials

# ============== 测试上传 ==============

def test_upload(credentials) -> bool:
    """上传测试视频验证账号"""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    
    if not TEST_VIDEO_PATH.exists():
        log.warning(f"测试视频不存在: {TEST_VIDEO_PATH}")
        log.info("跳过测试上传")
        return True
    
    log.info("正在上传测试视频验证账号...")
    
    try:
        youtube = build("youtube", "v3", credentials=credentials)
        
        body = {
            'snippet': {
                'title': f'Account Verification Test ({int(time.time())})',
                'description': 'Temporary test video for account verification.',
                'tags': ['test'],
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': 'private',
                'selfDeclaredMadeForKids': False
            }
        }
        
        media = MediaFileUpload(str(TEST_VIDEO_PATH), chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part=','.join(body.keys()), 
            body=body, 
            media_body=media
        )
        
        response = request.execute()
        
        video_id = response.get('id')
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        print("\n" + "*" * 60)
        log.success("测试视频上传成功！")
        print(f"🎥 视频链接: {url}")
        print("*" * 60)
        print("\n🚨 重要: 请打开上面的链接确认是否为正确的频道")
        
        confirm = input("\n这是正确的频道吗? (y/n): ")
        if confirm.lower() != 'y':
            log.error("用户取消，凭据不会保存")
            return False
        
        return True
        
    except Exception as e:
        log.error(f"测试上传失败: {e}")
        return False

# ============== 保存凭据 ==============

def save_credentials(oauth_data: dict):
    """保存凭据到文件"""
    
    # 生成 base64 编码
    b64 = base64.b64encode(json.dumps(oauth_data).encode()).decode()
    
    print("\n" + "=" * 60)
    print("认证成功！")
    print("=" * 60)
    
    # 保存到 youtube_oauth.txt
    with open(OUTPUT_PATH, 'w') as f:
        f.write(f"YOUTUBE_OAUTH_B64={b64}\n")
    log.success(f"凭据已保存到: {OUTPUT_PATH}")
    
    # 更新 .env 文件
    update_env_file(b64)
    
    # 打印环境变量
    print("\n" + "-" * 60)
    print("环境变量 (可手动添加到 .env):")
    print("-" * 60)
    print(f"\nYOUTUBE_OAUTH_B64={b64}\n")
    print("-" * 60)

def update_env_file(b64: str):
    """更新 .env 文件"""
    env_content = ""
    
    if ENV_FILE_PATH.exists():
        with open(ENV_FILE_PATH, 'r') as f:
            env_content = f.read()
    
    # 检查是否已存在 YOUTUBE_OAUTH_B64
    if "YOUTUBE_OAUTH_B64=" in env_content:
        # 替换现有值
        import re
        env_content = re.sub(
            r'YOUTUBE_OAUTH_B64=.*',
            f'YOUTUBE_OAUTH_B64={b64}',
            env_content
        )
        log.info("已更新 .env 中的 YOUTUBE_OAUTH_B64")
    else:
        # 添加新行
        if env_content and not env_content.endswith('\n'):
            env_content += '\n'
        env_content += f'YOUTUBE_OAUTH_B64={b64}\n'
        log.info("已添加 YOUTUBE_OAUTH_B64 到 .env")
    
    with open(ENV_FILE_PATH, 'w') as f:
        f.write(env_content)
    
    log.success(f".env 文件已更新: {ENV_FILE_PATH}")

# ============== 主函数 ==============

def main():
    parser = argparse.ArgumentParser(description='YouTube OAuth 认证工具')
    parser.add_argument('--test', action='store_true', help='认证后上传测试视频验证账号')
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("🎬 YouTube OAuth 认证工具")
    print("=" * 60 + "\n")
    
    # 执行认证
    oauth_data, credentials = authorize()
    
    # 测试上传（可选）
    if args.test:
        if not test_upload(credentials):
            sys.exit(1)
    
    # 保存凭据
    save_credentials(oauth_data)
    
    log.success("🎉 YouTube 认证完成！")

if __name__ == "__main__":
    main()
