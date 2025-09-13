import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
import os
import time
import random
import yaml
import logging
import zipfile
from io import BytesIO

import jmcomic
from jmcomic.jm_exception import PartialDownloadFailedException

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 自定义JMComic插件实现控制最大下载页数
async def download_comic_async(album_id, option):
    """异步下载漫画"""
    try:
        # 将同步下载操作放到线程池中执行，避免阻塞事件循环
        await asyncio.to_thread(jmcomic.download_album, album_id, option)
        return True, None
    except PartialDownloadFailedException as e:
        # 处理部分下载失败
        logger.warning(f"部分下载失败: {str(e)}")
        failed_count = str(e).count("RequestRetryAllFailException")
        return "partial", f"部分图片下载失败({failed_count}个)，但可能已生成不完整的PDF"
    except Exception as e:
        return False, f"下载出错: {str(e)}"

async def send_large_file(interaction: discord.Interaction, file_path: str, filename: str, max_size: int = 8 * 1024 * 1024):
    """发送大文件，如果超过限制则分片发送"""
    file_size = os.path.getsize(file_path)
    
    if file_size <= max_size:
        # 文件小于限制，直接发送
        try:
            with open(file_path, 'rb') as f:
                file = discord.File(f, filename=filename)
                await interaction.followup.send(file=file)
            return True, "文件发送成功"
        except Exception as e:
            return False, f"文件发送失败: {str(e)}"
    
    # 文件过大，需要分片发送
    logger.info(f"文件过大 ({file_size//1024}KB)，开始分片发送")
    
    try:
        # 创建分片ZIP文件
        chunk_size = max_size - 1024 * 1024  # 预留1MB空间给ZIP文件头
        chunks = []
        
        with open(file_path, 'rb') as f:
            chunk_num = 1
            while True:
                chunk_data = f.read(chunk_size)
                if not chunk_data:
                    break
                
                # 创建ZIP文件在内存中
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    zip_file.writestr(f"{filename}.part{chunk_num}", chunk_data)
                
                zip_buffer.seek(0)
                chunks.append((zip_buffer.getvalue(), f"{filename}.part{chunk_num}.zip"))
                chunk_num += 1
        
        # 发送分片文件
        embed = discord.Embed(
            title="📦 文件分片发送",
            description=f"文件过大({file_size//1024}KB)，分为{len(chunks)}个部分发送",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)
        
        for i, (chunk_data, chunk_filename) in enumerate(chunks, 1):
            chunk_file = discord.File(BytesIO(chunk_data), filename=chunk_filename)
            embed = discord.Embed(
                title=f"📁 第{i}部分",
                description=f"共{len(chunks)}部分",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, file=chunk_file)
            # 小延迟避免速率限制
            await asyncio.sleep(1)
        
        # 发送合并说明
        merge_embed = discord.Embed(
            title="🔧 文件合并说明",
            description=f"""
**合并步骤：**
1. 下载所有 .zip 分片文件
2. 解压每个分片文件得到 .part 文件
3. 使用以下命令合并（Windows）：
```
copy /b {filename}.part1+{filename}.part2+...+{filename}.part{len(chunks)} {filename}
```
**或者使用在线工具合并分片文件**
            """,
            color=discord.Color.yellow()
        )
        await interaction.followup.send(embed=merge_embed)
        
        return True, f"文件已分为{len(chunks)}个部分发送"
        
    except Exception as e:
        return False, f"分片发送失败: {str(e)}"

async def send_file_smart(interaction: discord.Interaction, file_path: str, filename: str):
    """智能文件发送，自动处理大文件"""
    file_size = os.path.getsize(file_path)
    
    # Discord文件大小限制检测
    max_size = 8 * 1024 * 1024  # 8MB (免费用户限制)
    
    if file_size <= max_size:
        # 尝试直接发送
        try:
            with open(file_path, 'rb') as f:
                file = discord.File(f, filename=filename)
                await interaction.followup.send(file=file)
            logger.info(f"文件直接发送成功: {filename} ({file_size//1024}KB)")
            return True, "文件发送成功"
        except discord.HTTPException as e:
            if "Payload Too Large" in str(e) or "413" in str(e):
                logger.warning(f"文件过大，转为分片发送: {filename}")
                return await send_large_file(interaction, file_path, filename, max_size)
            else:
                return False, f"文件发送失败: {str(e)}"
        except Exception as e:
            return False, f"文件发送失败: {str(e)}"
    else:
        # 文件明显过大，直接分片
        logger.info(f"文件过大，直接分片发送: {filename} ({file_size//1024}KB)")
        return await send_large_file(interaction, file_path, filename, max_size)

class SkipTooLongBook(jmcomic.JmOptionPlugin):
    plugin_key = 'skip_too_long_book'
    
    def invoke(self, 
               max_pages: int = 100,  # 可在option.yml中配置
               album: jmcomic.JmAlbumDetail = None,
               **kwargs):
        if album is None:
            logger.error('错误: Album is None')
            return
        pages = album.page_count
        logger.info(f'漫画 {album.id} 共 {pages} 页，限制为 {max_pages} 页')
        if pages <= max_pages:
            logger.info(f'页数检查通过: {pages}/{max_pages}')
            return
        else:
            logger.warning(f'超过页数限制({max_pages}页)，已阻止下载 - 漫画ID: {album.id}')
            raise Exception(f"漫画页数({pages}页)超过限制({max_pages}页)")

class JMBot(commands.Bot):
    def __init__(self):
        # 设置机器人意图
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(command_prefix='!', intents=intents)
        
        # 注册自定义插件
        jmcomic.JmModuleConfig.register_plugin(SkipTooLongBook)
        
        # 存储正在下载的ID
        self.downloading = set()
        
        # 加载配置
        self.load_config()
    
    async def setup_hook(self):
        """机器人启动时的设置钩子"""
        # 同步斜杠命令到Discord
        try:
            synced = await self.tree.sync()
            logger.info(f"已同步 {len(synced)} 个斜杠命令")
        except Exception as e:
            logger.error(f"同步斜杠命令失败: {e}")
        
    def load_config(self):
        """加载配置文件"""
        try:
            # 读取机器人配置
            with open('bot_config.json', 'r', encoding='utf-8') as f:
                bot_config = json.load(f)
                self.token = bot_config.get('token')
                self.IDmin = bot_config.get('IDmin', 110000)
                self.IDmax = bot_config.get('IDmax', 1200000)
        except FileNotFoundError:
            logger.error("找不到 bot_config.json 配置文件")
            self.token = None
            self.IDmin = 110000
            self.IDmax = 1200000
    
    async def on_ready(self):
        """机器人启动时的事件"""
        logger.info(f'{self.user} 已登录并准备就绪!')
        logger.info(f'机器人ID: {self.user.id}')
        
        # 设置机器人状态
        await self.change_presence(activity=discord.Game(name="JM漫画下载器 | /jm_help"))

# 创建机器人实例
bot = JMBot()

@bot.tree.command(name="jm", description="下载指定ID的JM漫画")
@app_commands.describe(comic_id="要下载的漫画ID")
async def slash_download_jm(interaction: discord.Interaction, comic_id: str):
    """下载指定ID的JM漫画"""
    await download_comic_handler_slash(interaction, comic_id)

@bot.tree.command(name="jmr", description="随机下载JM漫画")
async def slash_random_download_jm(interaction: discord.Interaction):
    """随机下载JM漫画"""
    rand_id = random.randint(bot.IDmin, bot.IDmax)
    
    embed = discord.Embed(
        title="🎲 随机下载",
        description=f"随机选择的ID: {rand_id}",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)
    
    await download_comic_handler_slash(interaction, str(rand_id), followup=True)

@bot.tree.command(name="jm_help", description="显示JM漫画下载器帮助信息")
async def slash_show_help(interaction: discord.Interaction):
    """显示帮助信息"""
    embed = discord.Embed(
        title="JM漫画下载器帮助",
        description="以下是可用的命令列表:",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="`/jm <ID>`",
        value="下载指定ID的JM漫画\n示例: `/jm comic_id:123456`",
        inline=False
    )
    
    embed.add_field(
        name="`/jmr`",
        value="随机下载JM漫画(实验性功能)",
        inline=False
    )
    
    embed.add_field(
        name="`/jm_force <ID>`",
        value="强制下载漫画（页数限制500页）\n用于下载页数较多的漫画",
        inline=False
    )
    
    embed.add_field(
        name="`/jm_retry <ID>`",
        value="重试下载漫画（增强网络配置）\n用于解决网络下载失败问题",
        inline=False
    )
    
    embed.add_field(
        name="`/status`",
        value="显示机器人状态信息",
        inline=False
    )
    
    embed.add_field(
        name="`/diagnose`",
        value="诊断系统配置和依赖",
        inline=False
    )
    
    embed.add_field(
        name="`/file_info`",
        value="查看文件信息和上传限制说明",
        inline=False
    )
    
    embed.add_field(
        name="`/jm_help`",
        value="显示本帮助信息",
        inline=False
    )
    
    embed.add_field(
        name="使用说明",
        value="• 如果漫画有多页，请输入第一页的ID\n• 下载的文件会自动转换为PDF格式\n• 重复下载会直接发送已有文件\n• 如果常规下载失败，可尝试 `/jm_force`\n• 如果网络问题导致失败，可尝试 `/jm_retry`\n• **大文件会自动分片发送，无需担心大小限制**\n• 使用 `/diagnose` 检查系统状态",
        inline=False
    )
    
    embed.set_footer(text="JM漫画下载器 | By MhYa123")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="status", description="显示机器人运行状态")
async def slash_bot_status(interaction: discord.Interaction):
    """显示机器人状态"""
    embed = discord.Embed(
        title="📊 机器人状态",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="🔄 正在下载",
        value=f"{len(bot.downloading)} 个任务" if bot.downloading else "无",
        inline=True
    )
    
    embed.add_field(
        name="🎯 随机范围",
        value=f"{bot.IDmin} - {bot.IDmax}",
        inline=True
    )
    
    embed.add_field(
        name="📶 延迟",
        value=f"{round(bot.latency * 1000)}ms",
        inline=True
    )
    
    if bot.downloading:
        embed.add_field(
            name="📋 下载队列",
            value=", ".join(bot.downloading),
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="diagnose", description="诊断系统配置和依赖")
async def slash_diagnose(interaction: discord.Interaction):
    """系统诊断"""
    path = os.path.abspath(os.path.dirname(__file__))
    
    embed = discord.Embed(
        title="🔧 系统诊断",
        color=discord.Color.blue()
    )
    
    # 检查必要目录
    dirs_status = []
    for dir_name in ['pdf', 'picture']:
        dir_path = f"{path}/{dir_name}"
        if os.path.exists(dir_path):
            dirs_status.append(f"✅ {dir_name}")
        else:
            dirs_status.append(f"❌ {dir_name}")
    
    embed.add_field(
        name="📁 目录状态",
        value="\n".join(dirs_status),
        inline=True
    )
    
    # 检查配置文件
    config_status = []
    config_files = ['option.yml', 'bot_config.json']
    for config_file in config_files:
        config_path = f"{path}/{config_file}"
        if os.path.exists(config_path):
            config_status.append(f"✅ {config_file}")
        else:
            config_status.append(f"❌ {config_file}")
    
    embed.add_field(
        name="⚙️ 配置文件",
        value="\n".join(config_status),
        inline=True
    )
    
    # 检查依赖库
    deps_status = []
    try:
        import jmcomic
        deps_status.append("✅ jmcomic")
    except ImportError:
        deps_status.append("❌ jmcomic")
    
    try:
        import img2pdf
        deps_status.append("✅ img2pdf")
    except ImportError:
        deps_status.append("❌ img2pdf")
    
    embed.add_field(
        name="📦 依赖库",
        value="\n".join(deps_status),
        inline=True
    )
    
    # 检查option.yml配置
    try:
        option = jmcomic.create_option_by_file(path + "/option.yml")
        embed.add_field(
            name="📋 option.yml状态",
            value="✅ 配置文件加载成功",
            inline=False
        )
    except Exception as e:
        embed.add_field(
            name="📋 option.yml状态",
            value=f"❌ 加载失败: {str(e)}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

async def download_comic_handler_slash(interaction: discord.Interaction, comic_id: str, followup: bool = False):
    """处理漫画下载的通用函数"""
    path = os.path.abspath(os.path.dirname(__file__))
    pdf_path = f"{path}/pdf/{comic_id}.pdf"
    
    # 检查文件是否已存在
    if os.path.exists(pdf_path):
        embed = discord.Embed(
            title="📁 文件已存在",
            description=f"{comic_id}.pdf 已下载，直接发送",
            color=discord.Color.green()
        )
        
        if followup:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)
        
        # 发送PDF文件
        try:
            success, message = await send_file_smart(interaction, pdf_path, f"{comic_id}.pdf")
            if not success:
                embed = discord.Embed(
                    title="❌ 文件发送失败",
                    description=message,
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ 文件发送失败",
                description=f"发送文件时出错: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
        return
    
    # 检查是否正在下载
    if comic_id in bot.downloading:
        embed = discord.Embed(
            title="⏳ 正在下载中",
            description="该漫画正在下载中，请稍后再试",
            color=discord.Color.orange()
        )
        if followup:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)
        return
    
    # 开始下载
    embed = discord.Embed(
        title="📥 开始下载",
        description=f"开始下载 {comic_id}，请稍候...",
        color=discord.Color.blue()
    )
    
    if followup:
        status_message = await interaction.followup.send(embed=embed)
    else:
        await interaction.response.send_message(embed=embed)
        status_message = await interaction.original_response()
    
    bot.downloading.add(comic_id)
    
    try:
        # 创建配置并开始异步下载
        option = jmcomic.create_option_by_file(path + "/option.yml")
        logger.info(f"开始下载漫画 {comic_id}")
        success, error_msg = await download_comic_async(comic_id, option)
        
        if success == "partial":
            # 部分下载失败，但可能有PDF生成
            logger.warning(f"部分下载失败 {comic_id}: {error_msg}")
            
            if os.path.exists(pdf_path):
                file_size = os.path.getsize(pdf_path)
                logger.info(f"部分下载，PDF文件已生成，大小: {file_size} bytes")
                
                embed = discord.Embed(
                    title="⚠️ 部分下载完成",
                    description=f"{comic_id} {error_msg}\n文件大小: {file_size//1024}KB\n**注意：PDF可能不完整**",
                    color=discord.Color.orange()
                )
                await status_message.edit(embed=embed)
                
                # 发送PDF文件
                try:
                    success, message = await send_file_smart(interaction, pdf_path, f"{comic_id}_partial.pdf")
                    if not success:
                        embed = discord.Embed(
                            title="❌ 文件发送失败",
                            description=message,
                            color=discord.Color.red()
                        )
                        await interaction.followup.send(embed=embed)
                except Exception as e:
                    logger.error(f"发送文件失败: {e}")
                    embed = discord.Embed(
                        title="❌ 文件发送失败",
                        description=f"PDF已生成但发送失败: {str(e)}",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ 部分下载失败",
                    description=f"{error_msg}，且未能生成PDF",
                    color=discord.Color.red()
                )
                await status_message.edit(embed=embed)
            return
        elif not success:
            logger.error(f"下载失败 {comic_id}: {error_msg}")
            embed = discord.Embed(
                title="❌ 下载失败",
                description=error_msg,
                color=discord.Color.red()
            )
            await status_message.edit(embed=embed)
            return
        
        # 检查文件是否下载成功
        logger.info(f"检查PDF文件: {pdf_path}")
        if os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path)
            logger.info(f"PDF文件已生成，大小: {file_size} bytes")
            
            embed = discord.Embed(
                title="✅ 下载完成",
                description=f"{comic_id} 下载完成 (文件大小: {file_size//1024}KB)",
                color=discord.Color.green()
            )
            await status_message.edit(embed=embed)
            
            # 发送PDF文件
            try:
                with open(pdf_path, 'rb') as f:
                    file = discord.File(f, filename=f"{comic_id}.pdf")
                    await interaction.followup.send(file=file)
            except Exception as e:
                logger.error(f"发送文件失败: {e}")
                embed = discord.Embed(
                    title="❌ 文件发送失败",
                    description=f"下载完成但发送文件时出错: {str(e)}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
        else:
            # 检查图片文件夹是否有内容
            picture_dir = f"{path}/picture"
            logger.info(f"检查图片目录: {picture_dir}")
            
            debug_info = []
            if os.path.exists(picture_dir):
                files = []
                for root, dirs, filenames in os.walk(picture_dir):
                    for filename in filenames:
                        files.append(os.path.join(root, filename))
                debug_info.append(f"图片目录存在，包含 {len(files)} 个文件")
                if files:
                    debug_info.append(f"首个文件示例: {files[0]}")
            else:
                debug_info.append("图片目录不存在")
            
            # 检查是否存在以comic_id命名的文件夹
            comic_dirs = [d for d in os.listdir(picture_dir) if comic_id in d] if os.path.exists(picture_dir) else []
            if comic_dirs:
                debug_info.append(f"找到相关目录: {comic_dirs}")
            
            logger.warning(f"PDF转换失败 {comic_id}: {'; '.join(debug_info)}")
            
            embed = discord.Embed(
                title="⚠️ 转换失败",
                description=f"无法转为PDF或超出页数限制\n调试信息: {'; '.join(debug_info)}",
                color=discord.Color.orange()
            )
            await status_message.edit(embed=embed)
            
    except Exception as e:
        logger.error(f"下载过程中出现错误 {comic_id}: {e}")
        embed = discord.Embed(
            title="❌ 下载出错",
            description=f"下载过程中出现错误: {str(e)}",
            color=discord.Color.red()
        )
        await status_message.edit(embed=embed)
    finally:
        bot.downloading.discard(comic_id)

async def download_comic_async(album_id, option):
    """异步下载漫画"""
    try:
        # 将同步下载操作放到线程池中执行，避免阻塞事件循环
        await asyncio.to_thread(jmcomic.download_album, album_id, option)
        return True, None
    except jmcomic.jm_exception.PartialDownloadFailedException as e:
        # 处理部分下载失败
        logger.warning(f"部分下载失败: {str(e)}")
        failed_count = str(e).count("RequestRetryAllFailException")
        return "partial", f"部分图片下载失败({failed_count}个)，但可能已生成不完整的PDF"
    except Exception as e:
        return False, f"下载出错: {str(e)}"

# 添加文件分片发送支持命令
@bot.tree.command(name="file_info", description="查看文件信息和Discord上传限制")
async def slash_file_info(interaction: discord.Interaction):
    """显示文件上传信息"""
    embed = discord.Embed(
        title="📁 文件上传信息",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Discord 文件大小限制",
        value="• 免费用户: 8MB\n• Nitro 用户: 25MB",
        inline=False
    )
    
    embed.add_field(
        name="本机器人解决方案",
        value="• 自动检测文件大小\n• 超过限制时自动分片发送\n• 提供文件合并说明",
        inline=False
    )
    
    embed.add_field(
        name="分片文件合并方法",
        value="1. 下载所有分片ZIP文件\n2. 解压得到.part文件\n3. 按顺序合并为完整文件",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """处理斜杠命令错误"""
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⏱️ 命令冷却中",
            description=f"请等待 {error.retry_after:.2f} 秒后再试",
            color=discord.Color.orange()
        )
    elif isinstance(error, app_commands.MissingPermissions):
        embed = discord.Embed(
            title="❌ 权限不足",
            description="您没有执行此命令的权限",
            color=discord.Color.red()
        )
    else:
        embed = discord.Embed(
            title="❌ 命令执行错误",
            description=f"执行命令时出现错误: {str(error)}",
            color=discord.Color.red()
        )
        logger.error(f"斜杠命令错误: {error}")
    
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name='sync')
@commands.is_owner()
async def sync_commands(ctx):
    """同步斜杠命令（仅限机器人所有者）"""
    try:
        synced = await bot.tree.sync()
        embed = discord.Embed(
            title="✅ 同步完成",
            description=f"已同步 {len(synced)} 个斜杠命令",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        logger.info(f"手动同步了 {len(synced)} 个斜杠命令")
    except Exception as e:
        embed = discord.Embed(
            title="❌ 同步失败",
            description=f"同步斜杠命令失败: {str(e)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        logger.error(f"手动同步斜杠命令失败: {e}")

@bot.event
async def on_command_error(ctx, error):
    """处理传统命令错误"""
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(
            title="❓ 提示",
            description="此机器人现在使用斜杠命令，请使用 `/jm_help` 查看可用命令",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.NotOwner):
        embed = discord.Embed(
            title="❌ 权限不足",
            description="此命令仅限机器人所有者使用",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ 命令执行错误",
            description=f"执行命令时出现错误: {str(error)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        logger.error(f"传统命令错误: {error}")

@bot.tree.command(name="jm_force", description="强制下载漫画（页数限制500页）")
@app_commands.describe(comic_id="要下载的漫画ID")
async def slash_force_download_jm(interaction: discord.Interaction, comic_id: str):
    """强制下载指定ID的JM漫画（更高页数限制）"""
    path = os.path.abspath(os.path.dirname(__file__))
    
    try:
        with open(path + "/option.yml", 'r', encoding='utf-8') as f:
            config_content = f.read()
        
        # 替换页数限制
        modified_content = config_content.replace('max_pages: 100', 'max_pages: 500')
        
        temp_option_path = path + "/option_temp.yml"
        with open(temp_option_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        await download_comic_handler_force(interaction, comic_id, temp_option_path)
        
        # 清理临时文件
        try:
            os.remove(temp_option_path)
        except:
            pass
            
    except Exception as e:
        embed = discord.Embed(
            title="❌ 配置错误",
            description=f"无法创建临时配置: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

async def download_comic_handler_force(interaction: discord.Interaction, comic_id: str, option_path: str):
    """强制下载处理函数"""
    path = os.path.abspath(os.path.dirname(__file__))
    pdf_path = f"{path}/pdf/{comic_id}.pdf"
    
    # 检查文件是否已存在
    if os.path.exists(pdf_path):
        embed = discord.Embed(
            title="📁 文件已存在",
            description=f"{comic_id}.pdf 已下载，直接发送",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        
        # 发送PDF文件
        try:
            with open(pdf_path, 'rb') as f:
                file = discord.File(f, filename=f"{comic_id}.pdf")
                await interaction.followup.send(file=file)
        except Exception as e:
            embed = discord.Embed(
                title="❌ 文件发送失败",
                description=f"发送文件时出错: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
        return
    
    # 检查是否正在下载
    if comic_id in bot.downloading:
        embed = discord.Embed(
            title="⏳ 正在下载中",
            description="该漫画正在下载中，请稍后再试",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    # 开始强制下载
    embed = discord.Embed(
        title="🚀 强制下载",
        description=f"开始强制下载 {comic_id} (页数限制500页)，请稍候...",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)
    status_message = await interaction.original_response()
    
    bot.downloading.add(comic_id)
    
    try:
        option = jmcomic.create_option_by_file(option_path)
        logger.info(f"开始强制下载漫画 {comic_id} (页数限制500页)")
        success, error_msg = await download_comic_async(comic_id, option)
        
        if success == "partial":
            # 部分下载失败，但可能有PDF生成
            logger.warning(f"强制下载部分失败 {comic_id}: {error_msg}")
            
            if os.path.exists(pdf_path):
                file_size = os.path.getsize(pdf_path)
                logger.info(f"强制下载部分成功，PDF文件已生成，大小: {file_size} bytes")
                
                embed = discord.Embed(
                    title="⚠️ 强制下载部分完成",
                    description=f"{comic_id} {error_msg}\n文件大小: {file_size//1024}KB\n**注意：PDF可能不完整**",
                    color=discord.Color.orange()
                )
                await status_message.edit(embed=embed)
                
                # 发送PDF文件
                try:
                    with open(pdf_path, 'rb') as f:
                        file = discord.File(f, filename=f"{comic_id}_partial_force.pdf")
                        await interaction.followup.send(file=file)
                except Exception as e:
                    logger.error(f"发送文件失败: {e}")
                    embed = discord.Embed(
                        title="❌ 文件发送失败",
                        description=f"PDF已生成但发送失败: {str(e)}",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ 强制下载部分失败",
                    description=f"{error_msg}，且未能生成PDF",
                    color=discord.Color.red()
                )
                await status_message.edit(embed=embed)
            return
        elif not success:
            logger.error(f"强制下载失败 {comic_id}: {error_msg}")
            embed = discord.Embed(
                title="❌ 强制下载失败",
                description=error_msg,
                color=discord.Color.red()
            )
            await status_message.edit(embed=embed)
            return
        
        # 检查文件是否下载成功
        if os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path)
            logger.info(f"强制下载成功，PDF文件已生成，大小: {file_size} bytes")
            
            embed = discord.Embed(
                title="✅ 强制下载完成",
                description=f"{comic_id} 强制下载完成 (文件大小: {file_size//1024}KB)",
                color=discord.Color.green()
            )
            await status_message.edit(embed=embed)
            
            # 发送PDF文件
            try:
                with open(pdf_path, 'rb') as f:
                    file = discord.File(f, filename=f"{comic_id}.pdf")
                    await interaction.followup.send(file=file)
            except Exception as e:
                logger.error(f"发送文件失败: {e}")
                embed = discord.Embed(
                    title="❌ 文件发送失败",
                    description=f"下载完成但发送文件时出错: {str(e)}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
        else:
            logger.warning(f"强制下载PDF转换失败 {comic_id}")
            embed = discord.Embed(
                title="⚠️ 强制下载转换失败",
                description="即使提高页数限制，仍无法转为PDF",
                color=discord.Color.orange()
            )
            await status_message.edit(embed=embed)
            
    except Exception as e:
        logger.error(f"强制下载过程中出现错误 {comic_id}: {e}")
        embed = discord.Embed(
            title="❌ 强制下载出错",
            description=f"强制下载过程中出现错误: {str(e)}",
            color=discord.Color.red()
        )
        await status_message.edit(embed=embed)
    finally:
        bot.downloading.discard(comic_id)

@bot.tree.command(name="jm_retry", description="重试下载漫画（增强网络配置）")
@app_commands.describe(comic_id="要重试下载的漫画ID")
async def slash_retry_download_jm(interaction: discord.Interaction, comic_id: str):
    """重试下载指定ID的JM漫画（增强网络配置）"""
    path = os.path.abspath(os.path.dirname(__file__))
    
    try:
        with open(path + "/option.yml", 'r', encoding='utf-8') as f:
            config_content = f.read()
        
        # 修改重试次数和线程数
        modified_content = config_content.replace('retry_times: 5', 'retry_times: 10')
        modified_content = modified_content.replace('image: 30', 'image: 15')  # 降低并发
        modified_content = modified_content.replace('photo: 32', 'photo: 8')   # 降低并发
        
        temp_option_path = path + "/option_retry.yml"
        with open(temp_option_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        await download_comic_handler_retry(interaction, comic_id, temp_option_path)
        
        # 清理临时文件
        try:
            os.remove(temp_option_path)
        except:
            pass
            
    except Exception as e:
        embed = discord.Embed(
            title="❌ 配置错误",
            description=f"无法创建重试配置: {str(e)}",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

async def download_comic_handler_retry(interaction: discord.Interaction, comic_id: str, option_path: str):
    """重试下载处理函数"""
    path = os.path.abspath(os.path.dirname(__file__))
    pdf_path = f"{path}/pdf/{comic_id}.pdf"
    
    # 检查是否正在下载
    if comic_id in bot.downloading:
        embed = discord.Embed(
            title="⏳ 正在下载中",
            description="该漫画正在下载中，请稍后再试",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    # 开始重试下载
    embed = discord.Embed(
        title="🔄 重试下载",
        description=f"开始重试下载 {comic_id} (增强网络配置)，请稍候...",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)
    status_message = await interaction.original_response()
    
    bot.downloading.add(comic_id)
    
    try:
        # 使用增强网络配置
        option = jmcomic.create_option_by_file(option_path)
        logger.info(f"开始重试下载漫画 {comic_id} (增强网络配置)")
        success, error_msg = await download_comic_async(comic_id, option)
        
        if success == "partial":
            # 部分下载失败，但可能有PDF生成
            logger.warning(f"重试下载部分失败 {comic_id}: {error_msg}")
            
            if os.path.exists(pdf_path):
                file_size = os.path.getsize(pdf_path)
                logger.info(f"重试下载部分成功，PDF文件已生成，大小: {file_size} bytes")
                
                embed = discord.Embed(
                    title="⚠️ 重试下载部分完成",
                    description=f"{comic_id} {error_msg}\n文件大小: {file_size//1024}KB\n**注意：PDF可能不完整，但已尽力下载**",
                    color=discord.Color.orange()
                )
                await status_message.edit(embed=embed)
                
                # 发送PDF文件
                try:
                    with open(pdf_path, 'rb') as f:
                        file = discord.File(f, filename=f"{comic_id}_retry.pdf")
                        await interaction.followup.send(file=file)
                except Exception as e:
                    logger.error(f"发送文件失败: {e}")
                    embed = discord.Embed(
                        title="❌ 文件发送失败",
                        description=f"PDF已生成但发送失败: {str(e)}",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ 重试下载失败",
                    description=f"{error_msg}，且未能生成PDF",
                    color=discord.Color.red()
                )
                await status_message.edit(embed=embed)
            return
        elif not success:
            logger.error(f"重试下载失败 {comic_id}: {error_msg}")
            embed = discord.Embed(
                title="❌ 重试下载失败",
                description=f"重试仍然失败: {error_msg}",
                color=discord.Color.red()
            )
            await status_message.edit(embed=embed)
            return
        
        # 检查文件是否下载成功
        if os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path)
            logger.info(f"重试下载成功，PDF文件已生成，大小: {file_size} bytes")
            
            embed = discord.Embed(
                title="✅ 重试下载完成",
                description=f"{comic_id} 重试下载成功 (文件大小: {file_size//1024}KB)",
                color=discord.Color.green()
            )
            await status_message.edit(embed=embed)
            
            # 发送PDF文件
            try:
                with open(pdf_path, 'rb') as f:
                    file = discord.File(f, filename=f"{comic_id}.pdf")
                    await interaction.followup.send(file=file)
            except Exception as e:
                logger.error(f"发送文件失败: {e}")
                embed = discord.Embed(
                    title="❌ 文件发送失败",
                    description=f"下载完成但发送文件时出错: {str(e)}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
        else:
            logger.warning(f"重试下载PDF转换失败 {comic_id}")
            embed = discord.Embed(
                title="⚠️ 重试下载转换失败",
                description="重试下载完成但无法转为PDF",
                color=discord.Color.orange()
            )
            await status_message.edit(embed=embed)
            
    except Exception as e:
        logger.error(f"重试下载过程中出现错误 {comic_id}: {e}")
        embed = discord.Embed(
            title="❌ 重试下载出错",
            description=f"重试下载过程中出现错误: {str(e)}",
            color=discord.Color.red()
        )
        await status_message.edit(embed=embed)
    finally:
        bot.downloading.discard(comic_id)

if __name__ == "__main__":
    # 检查配置文件
    if not os.path.exists('bot_config.json'):
        print("请先创建 bot_config.json 配置文件!")
        print("示例配置:")
        example_config = {
            "token": "YOUR_BOT_TOKEN_HERE",
            "IDmin": 110000,
            "IDmax": 1200000
        }
        print(json.dumps(example_config, indent=2, ensure_ascii=False))
        exit(1)
    
    if bot.token is None:
        print("请在 bot_config.json 中设置有效的机器人 token!")
        exit(1)
    
    try:
        bot.run(bot.token)
    except discord.LoginFailure:
        print("登录失败! 请检查 bot_config.json 中的 token 是否正确。")
    except Exception as e:
        print(f"启动机器人时出现错误: {e}")