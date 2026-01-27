# YouTube OAuth 认证 Skill

## 概述

获取 YouTube API OAuth 认证凭据，生成 `YOUTUBE_OAUTH_B64` 环境变量，用于自动上传视频到 YouTube。

## 快速使用

```bash
# 基本认证（推荐）
~/Downloads/add-caption/venv/bin/python ~/clawd/skills/youtube-auth/youtube_auth.py

# 认证 + 测试上传验证账号
~/Downloads/add-caption/venv/bin/python ~/clawd/skills/youtube-auth/youtube_auth.py --test
```

## 前置条件

### 1. Google Cloud 项目设置

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择现有项目
3. 启用 **YouTube Data API v3**
4. 创建 OAuth 2.0 凭据：
   - 应用类型：桌面应用
   - 下载 `client_secrets.json`

### 2. 放置 client_secrets.json

将 `client_secrets.json` 放置在以下位置之一：

```
~/clawd/skills/youtube-auth/client_secrets.json  (推荐)
~/clawd/secrets/client_secrets.json
~/Downloads/add-caption/notebooklm_video/client_secrets.json
```

### 3. 添加测试用户（如果项目未发布）

如果 Google Cloud 项目处于"测试"模式，需要将 YouTube 账号添加为测试用户：

1. Google Cloud Console → APIs & Services → OAuth consent screen
2. 点击 "Add users"
3. 添加要授权的 Google 账号邮箱

## 认证流程

```
1. 运行脚本
2. 浏览器自动打开 Google 登录页面
3. 选择要授权的 YouTube 账号
4. 点击 "允许" 授予权限
5. 脚本自动获取 token 并保存
```

## 输出

脚本会：

1. **保存到文件**: `~/clawd/skills/youtube-auth/youtube_oauth.txt`
2. **更新 .env**: 自动添加/更新 `~/clawd/.env` 中的 `YOUTUBE_OAUTH_B64`
3. **打印环境变量**: 可手动复制使用

## 验证账号（可选）

使用 `--test` 参数会上传一个 1 秒的测试视频（私密）来验证：

```bash
~/Downloads/add-caption/venv/bin/python ~/clawd/skills/youtube-auth/youtube_auth.py --test
```

这可以确保：
- 认证的是正确的 YouTube 频道
- API 权限正常工作

## 常见问题

### "未找到 client_secrets.json"

确保已下载 OAuth 凭据并放置在正确位置。

### "Access blocked: App is not verified"

Google Cloud 项目未发布，需要添加测试用户：
1. Google Cloud Console → OAuth consent screen
2. Add users → 添加你的 Google 账号

### "Refresh token is missing"

重新运行认证脚本，确保授予完整权限。

### Token 过期

运行脚本重新认证即可，refresh_token 会自动刷新 access_token。

## 文件结构

```
skills/youtube-auth/
├── SKILL.md              # 本文档
├── youtube_auth.py       # 认证脚本
├── client_secrets.json   # Google OAuth 凭据（需自行放置）
└── youtube_oauth.txt     # 生成的凭据（自动创建）
```

## 依赖

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

或使用已有的 venv：

```bash
~/Downloads/add-caption/venv/bin/python youtube_auth.py
```

## 与其他 Skill 的关系

- **youtube-daily-news**: 使用此 skill 生成的 `YOUTUBE_OAUTH_B64` 上传视频
