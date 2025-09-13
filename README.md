# Discord JM漫画下载器

这是一个基于 Discord.py 的 JM 漫画下载机器人。

## 📦 快速开始

```bash
# 克隆仓库
git clone https://github.com/mhya123/discord-jm.git
cd discord-jm

# 安装依赖
pip install -r requirements.txt

# 配置并运行
cp bot_config.json.example bot_config.json
# 编辑 bot_config.json 添加你的机器人token
python dc-jm.py
```

## 🔗 项目链接

- **GitHub仓库**: [https://github.com/mhya123/discord-jm](https://github.com/mhya123/discord-jm)
- **问题反馈**: [GitHub Issues](https://github.com/mhya123/discord-jm/issues)
- **功能建议**: [GitHub Discussions](https://github.com/mhya123/discord-jm/discussions)

## 功能特性

- 🔍 **指定ID下载**: 使用 `/jm <ID>` 下载指定ID的漫画
- 🎲 **随机下载**: 使用 `/jmr` 在配置范围内随机下载漫画
- 📁 **文件缓存**: 自动检测已下载的文件，避免重复下载
- 📄 **PDF转换**: 自动将下载的图片转换为PDF格式
- ⚡ **异步处理**: 支持异步下载，不阻塞其他命令
- 🛡️ **页数限制**: 防止下载页数过多的漫画
- 📊 **状态监控**: 查看机器人运行状态和下载队列
- ⚡ **斜杠命令**: 现代化的命令交互体验，支持自动补全和参数提示
- 📦 **文件分片发送**: 自动处理大文件分片，突破Discord文件大小限制
- 🔄 **智能重试**: 多种下载策略（普通/强制/重试），应对不同网络环境
- 🛠️ **系统诊断**: 内置诊断工具，快速检查配置和依赖状态
- ⚠️ **部分下载处理**: 智能处理网络中断，生成不完整但可用的PDF文件

## 安装步骤

### 1. 克隆仓库
```bash
git clone https://github.com/mhya123/discord-jm.git
cd dc-jmbot
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置机器人
复制 `bot_config.json.example` 为 `bot_config.json` 并填入你的机器人信息：

```json
{
  "token": "你的Discord机器人Token",
  "IDmin": 110000,
  "IDmax": 1200000
}
```

### 4. 配置JMComic
确保 `option.yml` 文件存在并正确配置。主要配置项：
- `max_pages`: 最大页数限制
- `pdf_dir`: PDF输出目录
- `base_dir`: 图片下载目录

### 5. 创建必要文件夹
```bash
mkdir pdf
mkdir picture
```

### 6. 运行机器人
```bash
python dc-jm.py
```

## 可用命令

### 斜杠命令（推荐）

| 命令 | 描述 | 示例 |
|------|------|------|
| `/jm <comic_id>` | 下载指定ID的漫画 | `/jm comic_id:123456` |
| `/jmr` | 随机下载漫画 | `/jmr` |
| `/jm_force <comic_id>` | 强制下载漫画（页数限制500页） | `/jm_force comic_id:123456` |
| `/jm_retry <comic_id>` | 重试下载（增强网络配置） | `/jm_retry comic_id:123456` |
| `/jm_help` | 显示帮助信息 | `/jm_help` |
| `/status` | 显示机器人状态 | `/status` |
| `/diagnose` | 诊断系统配置和依赖 | `/diagnose` |
| `/file_info` | 查看文件信息和上传限制说明 | `/file_info` |

### 下载策略说明

- **普通下载** (`/jm`): 标准下载，页数限制100页
- **强制下载** (`/jm_force`): 提高页数限制至500页，适用于大型漫画
- **重试下载** (`/jm_retry`): 降低并发数，增加重试次数，适用于网络不稳定环境

### 管理命令

| 命令 | 描述 | 权限要求 |
|------|------|----------|
| `!sync` | 手动同步斜杠命令 | 机器人所有者 |

## 斜杠命令优势

- 🚀 **自动补全**: Discord 会提供命令和参数的自动补全
- 📝 **参数提示**: 清晰的参数名称和描述
- 🎯 **更准确**: 减少输入错误和格式问题
- 🔒 **权限控制**: 更好的权限管理
- 📱 **移动端友好**: 在移动设备上更易使用

## 获取Discord机器人Token

1. 访问 [Discord Developer Portal](https://discord.com/developers/applications)
2. 创建新应用程序
3. 在 "Bot" 选项卡中创建机器人
4. 复制 Token 到配置文件
5. 在 "OAuth2" > "URL Generator" 中生成邀请链接
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Use Slash Commands`, `Attach Files`

## 首次使用

1. **邀请机器人后**，机器人会自动同步斜杠命令
2. 如果斜杠命令没有出现，使用 `!sync` 命令手动同步（需要机器人所有者权限）
3. 等待几分钟让 Discord 更新命令缓存
4. 输入 `/` 开始使用命令

## 文件分片功能详解

### 自动分片机制
当PDF文件超过Discord文件大小限制时，机器人会自动：
1. **检测文件大小**: 智能识别是否超过8MB（免费）或25MB（Nitro）限制
2. **自动分片**: 将大文件分割为多个小于限制的ZIP压缩包
3. **顺序发送**: 按顺序发送所有分片文件
4. **提供说明**: 自动生成文件合并指导

### 分片文件命名规则
```
原文件: 123456.pdf (15MB)
分片文件: 
├── 123456.pdf.part1.zip
├── 123456.pdf.part2.zip
└── 123456.pdf.part3.zip
```

### 文件合并方法

#### Windows系统
```bash
# 1. 解压所有ZIP文件得到.part文件
# 2. 使用命令行合并
copy /b 123456.pdf.part1+123456.pdf.part2+123456.pdf.part3 123456.pdf
```

#### Linux/Mac系统
```bash
# 1. 解压所有ZIP文件得到.part文件
# 2. 使用命令行合并
cat 123456.pdf.part1 123456.pdf.part2 123456.pdf.part3 > 123456.pdf
```

#### 在线工具
也可以使用在线文件合并工具来合并分片文件。

### 分片优势
- ✅ **突破限制**: 无文件大小限制，支持任意大小PDF
- ✅ **压缩传输**: ZIP压缩减少传输大小
- ✅ **断点续传**: 分片传输更稳定，失败只需重传单个分片
- ✅ **自动化**: 完全自动化处理，用户无需手动操作

## 注意事项

- 机器人需要在服务器中有发送消息、使用斜杠命令和附件的权限
- **文件大小限制自动处理**: 机器人会自动检测文件大小并分片发送大文件
- 请确保 `option.yml` 中的路径配置正确
- 建议设置合理的页数限制避免下载过大文件
- 斜杠命令可能需要几分钟时间在服务器中生效
- **分片文件合并**: 下载分片文件后，解压所有ZIP文件，按顺序合并.part文件即可还原完整PDF

## 错误处理

机器人包含完整的错误处理机制：

### 网络错误处理
- 自动重试下载失败的文件
- 智能处理`PartialDownloadFailedException`，生成部分PDF
- 多种下载策略应对不同网络环境
- 详细的网络错误日志记录

### 文件处理
- 防止重复下载同一ID
- 智能文件大小检测和分片发送
- 自动处理Discord文件上传限制
- ZIP分片文件自动生成和合并说明

### 用户体验
- 用户友好的错误提示和进度反馈
- 实时状态更新和下载进度显示
- 完整的诊断工具帮助排查问题
- 详细的帮助文档和命令说明

### 系统稳定性
- 异步下载队列管理，防止并发冲突
- 内存优化的文件处理，支持大文件操作
- 完整的异常捕获和恢复机制

## 文件结构

```
discord-jm/
├── dc-jm.py              # 主程序文件
├── option.yml            # JMComic配置文件
├── bot_config.json       # 机器人配置文件
├── bot_config.json.example # 配置文件示例
├── requirements.txt      # Python依赖
├── pdf/                  # PDF输出目录
├── picture/              # 图片下载目录
└── README.md            # 说明文档
```

## 技术特性

### 核心架构
- 基于 `discord.py` 2.x 构建
- 现代化的斜杠命令系统（Slash Commands）
- 异步编程架构，支持高并发处理
- 内置下载队列管理系统

### 文件处理技术
- **智能文件分片**: 自动检测文件大小，超过Discord限制时分片发送
- **ZIP压缩分片**: 使用ZIP格式压缩分片，提高传输效率
- **自动合并指导**: 提供详细的文件合并说明和命令
- **内存优化**: 使用BytesIO进行内存中文件操作，避免临时文件

### 下载引擎
- **JMComic库集成**: 深度集成jmcomic 2.6.7版本
- **自定义插件系统**: SkipTooLongBook插件，智能页数控制
- **多策略下载**: 普通/强制/重试三种下载模式
- **部分下载恢复**: 智能处理网络中断，最大化已下载内容利用

### 错误处理与监控
- **PartialDownloadFailedException处理**: 专门处理部分下载失败场景
- **网络重试机制**: 可配置的重试次数和并发控制
- **实时状态监控**: 下载队列状态和机器人健康监控
- **系统诊断工具**: 自动检查依赖、配置和环境状态

### 用户交互体验
- **Discord Embed美化**: 丰富的嵌入式消息和状态提示
- **进度实时反馈**: 下载进度和状态实时更新
- **命令自动补全**: 斜杠命令参数提示和自动补全
- **权限智能管理**: 自动命令同步和权限检查

### 配置与扩展
- **YAML配置系统**: 灵活的option.yml配置文件
- **动态配置修改**: 运行时临时配置调整（force/retry模式）
- **插件化架构**: 易于扩展的JMComic插件系统
- **环境自适应**: 自动检测和创建必要的目录结构

## 版本信息

### 当前版本特性
- **智能文件分片**: 自动处理大文件分片发送
- **多策略下载**: 普通/强制/重试三种下载模式
- **部分下载恢复**: 网络中断时生成不完整PDF
- **系统诊断**: 完整的配置和依赖检查工具
- **增强错误处理**: 全面的异常处理和用户反馈

### 技术栈版本
- Discord.py: 2.x
- JMComic: 2.6.7
- Python: 3.8+
- 支持平台: Windows, Linux, macOS

## 许可证

本项目采用 MIT 许可证开源。

### MIT License

```
MIT License

Copyright (c) 2025 A paramecium

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### 许可证说明

#### ✅ 允许的使用
- **商业使用**: 可以用于商业目的
- **修改**: 可以修改源代码
- **分发**: 可以分发原始或修改版本
- **私人使用**: 可以私人使用
- **专利使用**: 可以使用任何相关专利

#### 📋 使用条件
- **包含许可证**: 在所有副本中包含原始许可证和版权声明
- **包含版权**: 保留原始版权声明

#### ⚠️ 限制说明
- **责任免除**: 作者不承担任何责任
- **无担保**: 软件按"原样"提供，无任何明示或暗示的担保

### 第三方许可证
本项目使用了以下开源组件：
- **Discord.py**: MIT License
- **JMComic**: 遵循其原始许可证
- **其他依赖**: 各自遵循对应的开源许可证

### 贡献指南
欢迎提交 Pull Request 和 Issue！贡献代码时，您的贡献将自动采用本项目的 MIT 许可证。

### 致谢
- JMComic库: 提供核心下载功能
- Discord.py: 现代化的Discord机器人框架
- 开源社区: 感谢所有贡献者和用户的支持