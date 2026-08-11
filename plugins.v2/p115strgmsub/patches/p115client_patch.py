"""
p115client 补丁：增强请求头 + 405 指数退避重试
用于绕过 115 网盘阿里云 WAF 拦截
"""
import time
import logging

logger = logging.getLogger(__name__)

# 增强的浏览器请求头
ENHANCED_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "accept-encoding": "gzip, deflate, br, zstd",
    "dnt": "1",
    "referer": "https://115.com/",
    "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
}

_PATCHED = False


def patch_headers():
    """给 ClientRequestMixin.headers 属性注入增强头"""
    from p115client.client import ClientRequestMixin
    from property import locked_cacheproperty

    prop = ClientRequestMixin.headers
    _original_func = prop.__func__  # locked_cacheproperty 用 __func__ 存储原始函数

    def enhanced_headers(self):
        try:
            base = _original_func(self)
        except Exception:
            base = {}
        if isinstance(base, dict):
            for k, v in ENHANCED_HEADERS.items():
                base.setdefault(k, v)
            return base
        return ENHANCED_HEADERS.copy()

    ClientRequestMixin.headers = locked_cacheproperty(enhanced_headers)
    logger.info("✅ p115client 请求头已增强（WAF 防护）")


def patch_request_with_backoff():
    """给 P115Client.request 方法添加 405 + 连接异常指数退避"""
    from p115client.client import P115Client

    _original_request = P115Client.request

    def patched_request(self, url, method="GET", payload=None, *, async_=False, **kwargs):
        max_attempts = 4
        base_delay = 5

        for attempt in range(max_attempts):
            try:
                resp = _original_request(self, url, method, payload, async_=async_, **kwargs)
            except Exception as e:
                if attempt < max_attempts - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"⏳ 115 请求异常 {attempt+1}/{max_attempts}，{delay}s 后重试: {type(e).__name__}: {url[:80]}")
                    time.sleep(delay)
                    continue
                raise

            status = getattr(resp, 'status_code', None)
            if status == 405 and attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"⏳ WAF 405 拦截 {attempt+1}/{max_attempts}，{delay}s 后重试: {url[:80]}")
                time.sleep(delay)
                continue

            return resp

        return resp

    P115Client.request = patched_request
    logger.info("✅ p115client request 已添加 405 指数退避")


def apply():
    """应用所有 p115client 补丁（幂等）"""
    global _PATCHED
    if _PATCHED:
        return

    try:
        from p115client.client import ClientRequestMixin
    except ImportError:
        logger.warning("p115client 未安装，跳过补丁")
        return

    patch_headers()
    patch_request_with_backoff()
    _PATCHED = True
    logger.info("✅ p115client 补丁加载成功")
