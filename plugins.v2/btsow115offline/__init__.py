"""
BTSOW 115 离线下载插件
根据消息关键字从 BTSOW 搜索磁力链接，并支持使用 115 网盘离线下载
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx
from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType

# 尝试导入 p115client
try:
    from p115client import P115Client
    HAS_P115CLIENT = True
except ImportError:
    HAS_P115CLIENT = False
    P115Client = None


class Btsow115Offline(_PluginBase):
    # 插件元信息
    plugin_name = "BTSOW 115离线下载"
    plugin_desc = "根据消息关键字从 BTSOW 搜索磁力链接，支持选择后使用 115 网盘离线下载。"
    plugin_icon = "cloud_download.png"
    plugin_version = "1.0.9"
    plugin_author = "jojo"
    author_url = ""
    plugin_config_prefix = "btsow115offline_"
    plugin_order = 30
    auth_level = 1

    # 常量
    _DEFAULT_PREFIXES = "搜磁力\n搜115\nbtsow"
    _COMMAND_ACTION = "btsow_115_search"
    _HISTORY_KEY = "history"
    _HISTORY_LIMIT = 20
    _SEARCH_CACHE_KEY = "search_cache"
    _CACHE_EXPIRE_SECONDS = 600  # 10分钟缓存
    _BTSOW_BASE_URL = "https://so2.btsow.top"

    # 配置属性
    _enabled: bool = False
    _listen_user_message: bool = True
    _prefixes: str = _DEFAULT_PREFIXES
    _result_limit: int = 5
    _cookies_115: str = ""
    _save_path: str = ""

    def init_plugin(self, config: dict = None):
        self._enabled = False
        self._listen_user_message = True
        self._prefixes = self._DEFAULT_PREFIXES
        self._result_limit = 5
        self._cookies_115 = ""
        self._save_path = ""

        if not config:
            return

        self._enabled = bool(config.get("enabled"))
        self._listen_user_message = bool(config.get("listen_user_message", True))
        self._prefixes = config.get("prefixes") or self._DEFAULT_PREFIXES
        self._result_limit = self.__safe_int(config.get("result_limit"), default=5, minimum=1, maximum=10)
        self._cookies_115 = config.get("cookies_115") or ""
        self._save_path = config.get("save_path") or ""

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [{
            "cmd": "/btsow",
            "event": EventType.PluginAction,
            "desc": "从BTSOW搜索磁力并115离线下载",
            "category": "搜索",
            "data": {
                "action": Btsow115Offline._COMMAND_ACTION
            }
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "enabled",
                                        "label": "启用插件"
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "listen_user_message",
                                        "label": "监听普通消息"
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "result_limit",
                                        "label": "返回条数",
                                        "type": "number",
                                        "placeholder": "1-10"
                                    }
                                }]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 8},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "save_path",
                                        "label": "115离线保存路径",
                                        "placeholder": "留空则保存到根目录"
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "cookies_115",
                                        "label": "115网盘 Cookies",
                                        "rows": 3,
                                        "auto-grow": True,
                                        "placeholder": "格式：UID=...; CID=...; SEID=...; KID=...",
                                        "hint": "登录 115 网盘网页版后从浏览器获取 Cookies",
                                        "persistent-hint": True
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "prefixes",
                                        "label": "消息触发前缀",
                                        "rows": 3,
                                        "auto-grow": True,
                                        "placeholder": "每行一个前缀，例如：搜磁力",
                                        "hint": "普通消息以这些前缀开头时触发搜索",
                                        "persistent-hint": True
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VAlert",
                                    "props": {
                                        "type": "info",
                                        "variant": "tonal",
                                        "text": "使用方法：发送 /btsow 关键字 或发送「搜磁力 关键字」这类普通消息。搜索结果会显示选择按钮，点击即可添加到 115 离线下载。需要安装 p115client 库：pip install p115client"
                                    }
                                }]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "listen_user_message": True,
            "result_limit": 5,
            "cookies_115": "",
            "save_path": "",
            "prefixes": self._DEFAULT_PREFIXES
        }

    def get_page(self) -> List[dict]:
        history = self.get_data(self._HISTORY_KEY) or []
        history_lines = [
            f"{item.get('time')} | {item.get('type')} | {item.get('keyword')} | {item.get('result')}"
            for item in history[:10]
        ]

        content = [
            {
                "component": "VCol",
                "props": {"cols": 12},
                "content": [{
                    "component": "VAlert",
                    "props": {
                        "type": "info",
                        "variant": "tonal",
                        "text": "命令用法：/btsow 关键字。消息用法：发送「搜磁力 关键字」等前缀消息。"
                    }
                }]
            },
            {
                "component": "VCol",
                "props": {"cols": 12},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "text-subtitle-1 mb-2"},
                        "text": "当前配置"
                    },
                    {
                        "component": "div",
                        "props": {"class": "text-body-2 mb-1"},
                        "text": f"消息监听：{'开启' if self._listen_user_message else '关闭'}"
                    },
                    {
                        "component": "div",
                        "props": {"class": "text-body-2 mb-1"},
                        "text": f"消息前缀：{' / '.join(self.__get_prefix_list()) or '未配置'}"
                    },
                    {
                        "component": "div",
                        "props": {"class": "text-body-2 mb-1"},
                        "text": f"结果条数：{self._result_limit}"
                    },
                    {
                        "component": "div",
                        "props": {"class": "text-body-2 mb-1"},
                        "text": f"115 Cookies：{'已配置' if self._cookies_115 else '未配置'}"
                    },
                    {
                        "component": "div",
                        "props": {"class": "text-body-2"},
                        "text": f"保存路径：{self._save_path or '根目录'}"
                    }
                ]
            }
        ]

        if history_lines:
            content.append({
                "component": "VCol",
                "props": {"cols": 12},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "text-subtitle-1 mt-4 mb-2"},
                        "text": "最近操作记录"
                    }
                ] + [
                    {
                        "component": "div",
                        "props": {"class": "text-body-2 mb-1"},
                        "text": line
                    }
                    for line in history_lines
                ]
            })
        else:
            content.append({
                "component": "VCol",
                "props": {"cols": 12},
                "content": [{
                    "component": "div",
                    "props": {"class": "text-body-2 text-medium-emphasis mt-4"},
                    "text": "暂无操作记录"
                }]
            })

        return [{
            "component": "VRow",
            "content": content
        }]

    def stop_service(self):
        pass

    @eventmanager.register(EventType.PluginAction)
    def command_action(self, event: Event):
        """处理 /btsow 命令"""
        if not self._enabled or not event:
            return
        event_data = event.event_data or {}
        if event_data.get("action") != self._COMMAND_ACTION:
            return

        param = (event_data.get("arg_str") or "").strip()
        channel = event_data.get("channel")
        source = event_data.get("source")
        userid = event_data.get("user")

        # 如果参数是数字，则作为选择处理（适配微信等不支持按钮的平台）
        if param.isdigit():
            self.__handle_selection(
                selection=int(param),
                channel=channel,
                source=source,
                userid=userid
            )
        elif param:
            # 否则作为关键词搜索
            self.__search_and_reply(
                keyword=param,
                channel=channel,
                source=source,
                userid=userid,
                trigger="/btsow"
            )

    @eventmanager.register(EventType.UserMessage)
    def listen_user_message(self, event: Event):
        """监听普通消息"""
        logger.info(f"Btsow115Offline 收到消息事件: enabled={self._enabled}, listen={self._listen_user_message}")
        if not self._enabled or not self._listen_user_message or not event:
            logger.info(f"Btsow115Offline 跳过处理: enabled={self._enabled}, listen={self._listen_user_message}, event={event is not None}")
            return
        event_data = event.event_data or {}
        text = (event_data.get("text") or "").strip()
        logger.info(f"Btsow115Offline 处理消息: text={text}")
        if not text:
            return

        channel = event_data.get("channel")
        source = event_data.get("source")
        userid = event_data.get("userid")

        # 检查是否是数字序号选择（用户回复数字来选择资源）
        if text.isdigit():
            self.__handle_selection(
                selection=int(text),
                channel=channel,
                source=source,
                userid=userid
            )
            return

        # 支持 /btsow 命令格式
        if text.lower().startswith("/btsow"):
            param = text[6:].strip()
            if param:
                # 如果参数是数字，则作为选择处理（适配微信等不支持按钮的平台）
                if param.isdigit():
                    self.__handle_selection(
                        selection=int(param),
                        channel=channel,
                        source=source,
                        userid=userid
                    )
                else:
                    # 否则作为关键词搜索
                    self.__search_and_reply(
                        keyword=param,
                        channel=channel,
                        source=source,
                        userid=userid,
                        trigger="/btsow"
                    )
            return

        keyword = self.__extract_keyword(text)
        if keyword is None:
            return
        self.__search_and_reply(
            keyword=keyword,
            channel=channel,
            source=source,
            userid=userid,
            trigger="消息前缀"
        )

    def __handle_selection(self, selection: int, channel, source, userid):
        """处理用户的选择（回复数字序号）"""
        # 获取用户的搜索缓存
        cache = self.get_data(self._SEARCH_CACHE_KEY) or {}

        # 查找该用户最近的搜索结果
        user_cache_key = None
        user_results = None
        for key, value in cache.items():
            if key.startswith(f"{userid}_"):
                user_cache_key = key
                user_results = value.get("results", [])
                break

        if not user_results:
            self.post_message(
                channel=channel,
                source=source,
                userid=userid,
                title="选择失败",
                text="没有找到您的搜索记录，请先发送「搜磁力 关键字」进行搜索。"
            )
            return

        # 检查选择是否有效
        if selection < 1 or selection > len(user_results):
            self.post_message(
                channel=channel,
                source=source,
                userid=userid,
                title="选择无效",
                text=f"请输入 1-{len(user_results)} 之间的数字。"
            )
            return

        # 获取选中的资源
        selected = user_results[selection - 1]
        self.__do_offline_download(
            info_hash=selected["hash"],
            title=selected["title"],
            channel=channel,
            userid=userid
        )

    @eventmanager.register(EventType.MessageAction)
    def handle_button_click(self, event: Event):
        """处理按钮点击回调"""
        if not self._enabled or not event:
            return
        event_data = event.event_data or {}
        plugin_id = event_data.get("plugin_id")
        if plugin_id != self.__class__.__name__:
            return

        callback_data = event_data.get("callback_data") or ""
        action_key = f"[PLUGIN]{self.__class__.__name__}|"

        if not callback_data.startswith(action_key):
            return

        action = callback_data[len(action_key):]
        channel = event_data.get("channel")
        userid = event_data.get("userid")

        if action.startswith("download|"):
            # 格式：download|hash|title
            parts = action.split("|", 2)
            if len(parts) >= 3:
                info_hash = parts[1]
                title = parts[2]
                self.__do_offline_download(
                    info_hash=info_hash,
                    title=title,
                    channel=channel,
                    userid=userid
                )
        elif action == "cancel":
            self.post_message(
                channel=channel,
                userid=userid,
                title="已取消",
                text="操作已取消"
            )

    def __search_and_reply(self, keyword: str, channel, source, userid, trigger: str):
        """搜索并返回结果"""
        keyword = (keyword or "").strip()
        if not keyword:
            self.post_message(
                channel=channel,
                source=source,
                userid=userid,
                title="BTSOW 搜索用法",
                text=self.__build_usage_text()
            )
            return

        try:
            results = self.__search_btsow(keyword)
            if results:
                self.__save_history(keyword=keyword, userid=userid, trigger=trigger,
                                   result_type="搜索", result=f"找到 {len(results)} 条")
            else:
                self.__save_history(keyword=keyword, userid=userid, trigger=trigger,
                                   result_type="搜索", result="未找到")
        except Exception as err:
            logger.error(f"BTSOW 搜索失败：{err}")
            self.post_message(
                channel=channel,
                source=source,
                userid=userid,
                title=f"搜索失败：{keyword}",
                text=f"搜索过程中出现异常：{err}"
            )
            return

        if not results:
            self.post_message(
                channel=channel,
                source=source,
                userid=userid,
                title=f"未找到资源：{keyword}",
                text="没有搜索到匹配的磁力链接，请尝试其他关键词。"
            )
            return

        # 保存搜索结果到缓存
        cache_key = f"{userid}_{keyword}"
        self.__save_search_cache(cache_key, results)

        # 构建消息和按钮
        display_results = results[:self._result_limit]
        text_lines = [
            f"关键词：{keyword}",
            f"共找到 {len(results)} 条结果，展示前 {len(display_results)} 条",
            ""
        ]

        for index, item in enumerate(display_results, 1):
            text_lines.append(f"{index}. {item['title']}")
            text_lines.append(f"   大小：{item['size']} | 文件数：{item['file_count']}")
            text_lines.append(f"   时间：{item['date']}")

        # 添加提示信息（适配微信等不支持按钮的平台）
        text_lines.append("")
        text_lines.append("💡 提示：点击按钮选择，或回复 /btsow 数字 选择")
        text_lines.append("   例如：/btsow 1 选择第一个结果")

        # 构建按钮（支持按钮的平台如 Telegram/Slack）
        buttons = []
        for index, item in enumerate(display_results, 1):
            callback = f"[PLUGIN]{self.__class__.__name__}|download|{item['hash']}|{item['title'][:50]}"
            buttons.append([{
                "text": f"{index}. {item['title'][:20]}...",
                "callback_data": callback
            }])

        buttons.append([{
            "text": "取消",
            "callback_data": f"[PLUGIN]{self.__class__.__name__}|cancel"
        }])

        # 对于不支持按钮的平台，添加提示信息
        # 注意：微信等平台回复数字会被主程序拦截，无法使用数字选择
        # 所以这里提示用户使用按钮，或者通过其他方式（如复制 magnet 链接）

        self.post_message(
            channel=channel,
            source=source,
            userid=userid,
            title=f"BTSOW 搜索结果：{keyword}",
            text="\n".join(text_lines),
            buttons=buttons
        )

    def __search_btsow(self, keyword: str) -> List[Dict[str, str]]:
        """从 BTSOW 搜索磁力链接"""
        results = []
        url = f"{self._BTSOW_BASE_URL}/search?key={quote(keyword)}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                html = response.text
        except Exception as e:
            logger.error(f"请求 BTSOW 失败：{e}")
            raise

        # 解析 HTML
        # 匹配磁力链接卡片
        # <div class="card mb-4"><div class="card-body">...<span>标题</span>...magnet:?xt=urn:btih:hash...
        card_pattern = r'<div class="card mb-4[^"]*"[^>]*>.*?<div class="card-body">(.*?)</div>\s*</div>\s*</div>'
        cards = re.findall(card_pattern, html, re.DOTALL)

        for card in cards:
            try:
                # 提取标题
                title_match = re.search(r'<span[^>]*>(.*?)</span>', card, re.DOTALL)
                title = title_match.group(1) if title_match else ""
                title = re.sub(r'<[^>]+>', '', title).strip()

                # 提取磁力链接中的 hash
                magnet_match = re.search(r'magnet:\?xt=urn:btih:([a-fA-F0-9]+)', card)
                if not magnet_match:
                    # 尝试从 /hash/ 链接提取
                    hash_match = re.search(r'/hash/([a-fA-F0-9]+)', card)
                    info_hash = hash_match.group(1) if hash_match else None
                else:
                    info_hash = magnet_match.group(1)

                if not info_hash or not title:
                    continue

                # 提取文件大小
                size_match = re.search(r'文件大小[：:]\s*<[^>]*>([^<]+)</span>', card)
                size = size_match.group(1).strip() if size_match else "未知"

                # 提取文件数量
                file_count_match = re.search(r'文件数量[：:]\s*(\d+)', card)
                file_count = file_count_match.group(1) if file_count_match else "未知"

                # 提取收录时间
                date_match = re.search(r'收录时间[：:]\s*([^|<]+)', card)
                date = date_match.group(1).strip() if date_match else "未知"

                results.append({
                    "title": title,
                    "hash": info_hash.lower(),
                    "size": size,
                    "file_count": file_count,
                    "date": date,
                    "magnet": f"magnet:?xt=urn:btih:{info_hash.lower()}"
                })
            except Exception as e:
                logger.debug(f"解析搜索结果失败：{e}")
                continue

        return results

    def __do_offline_download(self, info_hash: str, title: str, channel, userid):
        """执行 115 离线下载"""
        if not HAS_P115CLIENT:
            self.post_message(
                channel=channel,
                userid=userid,
                title="离线下载失败",
                text="未安装 p115client 库，请执行 pip install p115client 安装后重启。"
            )
            return

        if not self._cookies_115:
            self.post_message(
                channel=channel,
                userid=userid,
                title="离线下载失败",
                text="未配置 115 网盘 Cookies，请在插件设置中配置。"
            )
            return

        try:
            client = P115Client(self._cookies_115)
            magnet = f"magnet:?xt=urn:btih:{info_hash}"

            # 获取目标目录 ID（如果配置了保存路径）
            cid = 0
            if self._save_path:
                # 尝试获取或创建目录
                cid = self.__get_or_create_folder(client, self._save_path)

            # 添加离线下载任务
            result = client.offline_add_urls({
                "urls": magnet,
                "cid": cid if cid else 0
            })

            if result.get("state") or result.get("errno") == 0:
                self.__save_history(
                    keyword=title[:30],
                    userid=userid,
                    trigger="离线下载",
                    result_type="下载",
                    result="成功"
                )
                self.post_message(
                    channel=channel,
                    userid=userid,
                    title="离线下载已添加",
                    text=f"《{title[:50]}》已成功添加到 115 离线下载任务。"
                )
            else:
                error_msg = result.get("error", "未知错误")
                logger.error(f"115 离线下载添加失败：{error_msg}")
                self.post_message(
                    channel=channel,
                    userid=userid,
                    title="离线下载失败",
                    text=f"添加离线下载任务失败：{error_msg}"
                )
        except Exception as e:
            logger.error(f"115 离线下载异常：{e}")
            self.post_message(
                channel=channel,
                userid=userid,
                title="离线下载失败",
                text=f"添加离线下载任务时发生异常：{e}"
            )

    def __get_or_create_folder(self, client: P115Client, path: str) -> int:
        """获取或创建目录，返回目录 ID"""
        try:
            # 尝试获取目录 ID
            result = client.fs_files({
                "cid": 0,
                "show_dir": 1
            })

            # 按路径层级查找或创建
            current_cid = 0
            path_parts = [p for p in path.strip("/").split("/") if p]

            for part in path_parts:
                # 查找当前层级的目录
                files = client.fs_files({"cid": current_cid, "show_dir": 1})
                found = False
                for f in files.get("data", []):
                    if f.get("n") == part and f.get("fc", 0) >= 0:  # 是目录
                        current_cid = f.get("cid", 0)
                        found = True
                        break

                if not found:
                    # 创建目录
                    create_result = client.fs_mkdir({
                        "cid": current_cid,
                        "file_name": part
                    })
                    if create_result.get("errno") == 0:
                        # 获取新创建目录的 ID
                        files = client.fs_files({"cid": current_cid, "show_dir": 1})
                        for f in files.get("data", []):
                            if f.get("n") == part:
                                current_cid = f.get("cid", 0)
                                break

            return current_cid
        except Exception as e:
            logger.error(f"获取或创建目录失败：{e}")
            return 0

    def __save_search_cache(self, cache_key: str, results: List[dict]):
        """保存搜索结果缓存"""
        cache = self.get_data(self._SEARCH_CACHE_KEY) or {}
        cache[cache_key] = {
            "results": results,
            "timestamp": datetime.now().timestamp()
        }
        # 清理过期缓存
        current_time = datetime.now().timestamp()
        cache = {
            k: v for k, v in cache.items()
            if current_time - v.get("timestamp", 0) < self._CACHE_EXPIRE_SECONDS
        }
        self.save_data(self._SEARCH_CACHE_KEY, cache)

    def __build_usage_text(self) -> str:
        prefixes = " / ".join(self.__get_prefix_list()) or "未配置"
        return (
            "命令方式：/btsow 关键字\n"
            f"消息方式：{prefixes} + 空格 + 关键字\n"
            "示例：/btsow 流浪地球\n"
            "示例：搜磁力 流浪地球"
        )

    def __extract_keyword(self, text: str) -> Optional[str]:
        """从消息中提取关键字"""
        for prefix in self.__get_prefix_list():
            if not text.lower().startswith(prefix.lower()):
                continue

            remain = text[len(prefix):]
            if prefix[-1].isascii() and prefix[-1].isalnum():
                if remain and remain[0] not in {" ", ":", "："}:
                    continue

            return remain.lstrip(" ：:").strip()
        return None

    def __get_prefix_list(self) -> List[str]:
        """获取前缀列表"""
        prefixes = []
        for prefix in (self._prefixes or "").splitlines():
            prefix = prefix.strip()
            if prefix and prefix not in prefixes:
                prefixes.append(prefix)
        return prefixes

    def __save_history(self, keyword: str, userid, trigger: str, result_type: str, result: str):
        """保存历史记录"""
        history = self.get_data(self._HISTORY_KEY) or []
        if not isinstance(history, list):
            history = []
        history.insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user": str(userid) if userid is not None else "",
            "trigger": trigger,
            "keyword": keyword,
            "type": result_type,
            "result": result
        })
        self.save_data(self._HISTORY_KEY, history[:self._HISTORY_LIMIT])

    @staticmethod
    def __safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, value))
