# -*- coding: utf-8 -*-
"""Playwright 反检测启动器。

用法：
    from stealth import launch, human_type, human_click

    with launch(persistent_dir="./profile", headless=False) as ctx:
        page = ctx.new_page()
        human_type(page, "#username", "your_account")
        human_click(page, "button[type=submit]")

设计取舍：
- 只做「提高通过率」，不做「保证通过」。IP 级风控、账号画像、平台明确禁止的
  场景，这个模块解决不了，也不该指望它解决。
- 补丁在 context 级别注入（add_init_script），新开的每个页面都生效，不用逐页加。
- 持久化 profile 复用登录态，比每次扫码省事，也更像真实用户。
"""
from __future__ import annotations

import random
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

# 基础补丁：只处理最常见的几个前端特征
STEALTH_JS = r"""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 无头浏览器默认 plugins 是空数组，这是硬特征
Object.defineProperty(navigator, 'plugins', {
  get: () => [1, 2, 3, 4, 5].map(() => ({
    description: '', filename: '', length: 1
  }))
});

Object.defineProperty(navigator, 'languages', {
  get: () => ['zh-CN', 'zh', 'en']
});

// headless 下 Notification 权限行为与有头不同
(() => {
  const original = window.navigator.permissions.query;
  window.navigator.permissions.query = (params) =>
    params.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : original(params);
})();
"""

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
)


@contextmanager
def launch(
    persistent_dir: str | Path | None = None,
    headless: bool = False,
    user_agent: str = DEFAULT_UA,
    locale: str = "zh-CN",
    viewport: dict | None = None,
    slow_mo: int = 0,
):
    """启动一个带反检测补丁的浏览器上下文。

    persistent_dir: 传入目录则复用登录态（推荐）；不传则用一次性上下文。
    headless: 强反检测站点建议 False，无头特征太明显。
    slow_mo: 每个动作之间的基础延迟（毫秒），配合 human_* 使用。
    """
    viewport = viewport or {"width": 1440, "height": 900}

    with sync_playwright() as p:
        if persistent_dir:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(persistent_dir),
                headless=headless,
                locale=locale,
                user_agent=user_agent,
                viewport=viewport,
                slow_mo=slow_mo,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
        else:
            browser = p.chromium.launch(
                headless=headless,
                slow_mo=slow_mo,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                locale=locale, user_agent=user_agent, viewport=viewport
            )

        ctx.add_init_script(STEALTH_JS)
        try:
            yield ctx
        finally:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass


def human_type(page, selector: str, text: str, min_delay: int = 60, max_delay: int = 180) -> None:
    """点输入框聚焦，再逐字符输入。

    不要用 fill() —— 它一次性写入，没有键盘事件，是最容易被识别的行为之一。
    """
    page.click(selector)
    page.wait_for_timeout(random.randint(200, 500))
    for ch in text:
        page.keyboard.type(ch)
        page.wait_for_timeout(random.randint(min_delay, max_delay))


def human_click(page, selector: str, hover_first: bool = True) -> None:
    """先 hover 再点击，走真实的鼠标移动链路。"""
    if hover_first:
        page.hover(selector)
        page.wait_for_timeout(random.randint(150, 450))
    page.click(selector)


def human_scroll(page, steps: int = 3, min_delay: int = 300, max_delay: int = 900) -> None:
    """分段滚动，模拟阅读节奏。"""
    for _ in range(steps):
        page.mouse.wheel(0, random.randint(300, 700))
        page.wait_for_timeout(random.randint(min_delay, max_delay))


def pause(min_s: float = 0.3, max_s: float = 1.0) -> None:
    """操作之间的随机停顿。固定间隔本身就是特征。"""
    time.sleep(random.uniform(min_s, max_s))
