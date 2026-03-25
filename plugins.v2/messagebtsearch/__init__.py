from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.chain.search import SearchChain
from app.core.context import Context
from app.core.event import Event, eventmanager
from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType
from app.utils.string import StringUtils


class MessageBtSearch(_PluginBase):
    # 插件名称
    plugin_name = "消息搜种"
    # 插件描述
    plugin_desc = "根据发送消息中的关键字搜索已配置站点资源并返回结果。"
    # 插件图标
    plugin_icon = "torrent.png"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "zhangqing"
    # 作者主页
    author_url = ""
    # 插件配置项ID前缀
    plugin_config_prefix = "messagebtsearch_"
    # 加载顺序
    plugin_order = 30
    # 可使用的用户级别
    auth_level = 1

    _DEFAULT_PREFIXES = "搜种\n搜资源\nbt"
    _COMMAND_ACTION = "message_bt_search"
    _HISTORY_KEY = "history"
    _HISTORY_LIMIT = 20

    _enabled: bool = False
    _listen_user_message: bool = True
    _prefixes: str = _DEFAULT_PREFIXES
    _result_limit: int = 5
    _site_ids: List[int] = []
    _show_detail_link: bool = True

    def init_plugin(self, config: dict = None):
        self._enabled = False
        self._listen_user_message = True
        self._prefixes = self._DEFAULT_PREFIXES
        self._result_limit = 5
        self._site_ids = []
        self._show_detail_link = True

        if not config:
            return

        self._enabled = bool(config.get("enabled"))
        self._listen_user_message = bool(config.get("listen_user_message", True))
        self._prefixes = config.get("prefixes") or self._DEFAULT_PREFIXES
        self._result_limit = self.__safe_int(config.get("result_limit"), default=5, minimum=1, maximum=10)
        self._site_ids = self.__normalize_site_ids(config.get("site_ids") or [])
        self._show_detail_link = bool(config.get("show_detail_link", True))

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [{
            "cmd": "/bt",
            "event": EventType.PluginAction,
            "desc": "按关键字搜索资源",
            "category": "搜索",
            "data": {
                "action": MessageBtSearch._COMMAND_ACTION
            }
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        site_options = [
            {"title": site.name, "value": site.id}
            for site in SiteOper().list_order_by_pri()
        ]

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
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "show_detail_link",
                                        "label": "返回详情链接"
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
                                    "component": "VSelect",
                                    "props": {
                                        "model": "site_ids",
                                        "label": "搜索站点",
                                        "items": site_options,
                                        "multiple": True,
                                        "chips": True,
                                        "clearable": True,
                                        "hint": "留空时使用系统已启用的索引站点",
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
                                        "placeholder": "每行一个前缀，例如：搜种",
                                        "hint": "普通消息以这些前缀开头时触发搜索，例如“搜种 流浪地球”",
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
                                        "text": "支持两种触发方式：1. 发送 /bt 关键字；2. 发送“搜种 关键字”这类普通消息。插件复用 MoviePilot 已配置索引站点进行搜索，不会额外维护独立站点抓取逻辑。"
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
            "show_detail_link": True,
            "result_limit": 5,
            "site_ids": [],
            "prefixes": self._DEFAULT_PREFIXES
        }

    def get_page(self) -> List[dict]:
        site_names = self.__get_selected_site_names()
        history = self.get_data(self._HISTORY_KEY) or []
        history_lines = [
            f"{item.get('time')} | 用户 {item.get('user') or '未知'} | {item.get('trigger')} | {item.get('keyword')} | {item.get('result_count', 0)} 条"
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
                        "text": "命令用法：/bt 关键字。消息用法：发送“搜种 关键字”“搜资源 关键字”等前缀消息。"
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
                        "props": {"class": "text-body-2"},
                        "text": f"搜索站点：{', '.join(site_names) if site_names else '系统已启用索引站点'}"
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
                        "text": "最近搜索记录"
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
                    "text": "暂无搜索记录"
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
        if not self._enabled or not event:
            return
        event_data = event.event_data or {}
        if event_data.get("action") != self._COMMAND_ACTION:
            return
        self.__search_and_reply(
            keyword=(event_data.get("arg_str") or "").strip(),
            channel=event_data.get("channel"),
            source=event_data.get("source"),
            userid=event_data.get("user"),
            trigger="/bt"
        )

    @eventmanager.register(EventType.UserMessage)
    def listen_user_message(self, event: Event):
        if not self._enabled or not self._listen_user_message or not event:
            return
        event_data = event.event_data or {}
        text = (event_data.get("text") or "").strip()
        if not text:
            return
        keyword = self.__extract_keyword(text)
        if keyword is None:
            return
        self.__search_and_reply(
            keyword=keyword,
            channel=event_data.get("channel"),
            source=event_data.get("source"),
            userid=event_data.get("userid"),
            trigger="消息前缀"
        )

    def __search_and_reply(self, keyword: str, channel, source, userid, trigger: str):
        keyword = (keyword or "").strip()
        if not keyword:
            self.post_message(
                channel=channel,
                source=source,
                userid=userid,
                title="BT 搜索用法",
                text=self.__build_usage_text()
            )
            return

        try:
            contexts = SearchChain().search_by_title(
                title=keyword,
                sites=self._site_ids or None
            ) or []
            contexts = self.__prepare_contexts(contexts)
            self.__save_history(keyword=keyword, userid=userid, trigger=trigger, result_count=len(contexts))
        except Exception as err:
            logger.error(f"消息搜种执行失败：{err}")
            self.post_message(
                channel=channel,
                source=source,
                userid=userid,
                title=f"搜种失败：{keyword}",
                text=f"搜索过程中出现异常：{err}"
            )
            return

        if not contexts:
            self.post_message(
                channel=channel,
                source=source,
                userid=userid,
                title=f"未找到资源：{keyword}",
                text="没有搜索到匹配结果。可以尝试缩短关键词，或检查索引站点是否已启用且可用。"
            )
            return

        self.post_message(
            channel=channel,
            source=source,
            userid=userid,
            title=f"搜种结果：{keyword}",
            text=self.__format_results(keyword=keyword, contexts=contexts)
        )

    def __format_results(self, keyword: str, contexts: List[Context]) -> str:
        display_contexts = contexts[:self._result_limit]
        lines = [
            f"关键词：{keyword}",
            f"共命中 {len(contexts)} 条，展示前 {len(display_contexts)} 条"
        ]

        site_names = self.__get_selected_site_names()
        if site_names:
            lines.append(f"站点范围：{', '.join(site_names)}")

        lines.append("")

        for index, context in enumerate(display_contexts, 1):
            torrent = context.torrent_info
            lines.append(f"{index}. [{torrent.site_name or '未知站点'}] {torrent.title}")

            attrs = []
            if torrent.size:
                attrs.append(f"大小 {StringUtils.str_filesize(torrent.size)}")
            attrs.append(f"做种 {torrent.seeders or 0}")
            if torrent.peers:
                attrs.append(f"下载 {torrent.peers}")
            if torrent.grabs:
                attrs.append(f"完成 {torrent.grabs}")
            if torrent.volume_factor and torrent.volume_factor != "未知":
                attrs.append(f"促销 {torrent.volume_factor}")
            if torrent.pubdate:
                attrs.append(f"时间 {torrent.pubdate}")

            if attrs:
                lines.append(f"   {' | '.join(attrs)}")

            if self._show_detail_link and torrent.page_url:
                lines.append(f"   详情 {torrent.page_url}")

        if len(contexts) > len(display_contexts):
            lines.append("")
            lines.append("还有更多结果未展示，请使用更具体的关键词缩小范围。")

        return "\n".join(lines)

    def __prepare_contexts(self, contexts: List[Context]) -> List[Context]:
        valid_contexts = [
            context for context in contexts
            if getattr(context, "torrent_info", None) and context.torrent_info.title
        ]
        valid_contexts = sorted(
            valid_contexts,
            key=lambda context: (
                -(context.torrent_info.seeders or 0),
                context.torrent_info.site_order or 999,
                -(context.torrent_info.grabs or 0),
                -(context.torrent_info.size or 0)
            )
        )

        results = []
        seen = set()
        for context in valid_contexts:
            torrent = context.torrent_info
            unique_key = (
                torrent.site_name or "",
                torrent.title or "",
                torrent.page_url or torrent.enclosure or ""
            )
            if unique_key in seen:
                continue
            seen.add(unique_key)
            results.append(context)
        return results

    def __build_usage_text(self) -> str:
        prefixes = " / ".join(self.__get_prefix_list()) or "未配置"
        return (
            "命令方式：/bt 关键字\n"
            f"消息方式：{prefixes} + 空格 + 关键字\n"
            "示例：/bt 流浪地球\n"
            "示例：搜种 流浪地球"
        )

    def __extract_keyword(self, text: str) -> Optional[str]:
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
        prefixes = []
        for prefix in (self._prefixes or "").splitlines():
            prefix = prefix.strip()
            if prefix and prefix not in prefixes:
                prefixes.append(prefix)
        return prefixes

    def __get_selected_site_names(self) -> List[str]:
        if not self._site_ids:
            return []
        site_map = {
            site.id: site.name
            for site in SiteOper().list_order_by_pri()
        }
        return [site_map[site_id] for site_id in self._site_ids if site_map.get(site_id)]

    def __save_history(self, keyword: str, userid, trigger: str, result_count: int):
        history = self.get_data(self._HISTORY_KEY) or []
        if not isinstance(history, list):
            history = []
        history.insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user": str(userid) if userid is not None else "",
            "trigger": trigger,
            "keyword": keyword,
            "result_count": result_count
        })
        self.save_data(self._HISTORY_KEY, history[:self._HISTORY_LIMIT])

    @staticmethod
    def __normalize_site_ids(site_ids: List[Any]) -> List[int]:
        results = []
        for site_id in site_ids:
            try:
                site_id = int(site_id)
            except (TypeError, ValueError):
                continue
            if site_id not in results:
                results.append(site_id)
        return results

    @staticmethod
    def __safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, value))
