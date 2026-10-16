# -*- coding: utf-8 -*-
"""自动化截图脚本（2026-09-19 新版 UI：工作台 + 五步向导 + 日程视图）。

前提：系统已通过 python main.py 启动，且数据库已导入批量测试数据
（批量测试_教师_30人.xlsx / 批量测试_学生_100人.xlsx / 批量测试_教室_10间.xlsx，
可登录后在"准备资料"步骤或各管理页导入）。已有数据时请勿重复导入。

用法:
    python take_screenshots.py
依赖:
    pip install -r ../requirements-dev.txt  (playwright)
    python -m playwright install chromium
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8000'
OUT = Path(__file__).resolve().parent.parent / 'images'
OUT.mkdir(parents=True, exist_ok=True)


def shot(page, name):
    page.screenshot(path=str(OUT / f'{name}.png'), full_page=False)
    print('saved', name, flush=True)


def click_first(page, selectors, timeout=2500):
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count():
                loc.first.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def goto(page, path, name, wait=2000):
    page.goto(BASE + path, wait_until='networkidle')
    page.wait_for_timeout(wait)
    page.wait_for_load_state('networkidle')
    shot(page, name)


def main():
    exe = os.path.expandvars(r'%LOCALAPPDATA%\ms-playwright\chromium-1228\chrome-win64\chrome.exe')
    kwargs = {'executable_path': exe} if Path(exe).exists() else {}
    with sync_playwright() as p:
        browser = p.chromium.launch(**kwargs)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 900}, locale='zh-CN')
        page = ctx.new_page()

        # 1. 登录页
        page.goto(BASE, wait_until='networkidle')
        page.wait_for_timeout(1200)
        shot(page, '01-登录页')

        # 登录
        page.fill('input[type="text"], input[placeholder*="用户"], input:not([type="password"])', 'wikidemo')
        page.fill('input[type="password"]', 'WikiDemo#2026')
        page.keyboard.press('Enter')
        page.wait_for_timeout(2500)
        page.wait_for_load_state('networkidle')
        print('after login url:', page.url, flush=True)

        # 2. 工作台（新版：下一步提示 + 开始一次答辩安排）
        goto(page, '/dashboard', '02-工作台总览')

        # 3. 分步向导 · 第二步 准备资料（核对三份资料）
        goto(page, '/schedule-wizard?step=2', '03-分步向导-准备资料')

        # 4. 分步向导 · 第三步 确认要求（常用规则直接展示）
        goto(page, '/schedule-wizard?step=3', '04-分步向导-确认要求')

        # 5. 教师管理
        goto(page, '/teachers', '05-教师管理')

        # 6. 学生管理
        goto(page, '/students', '06-学生管理')

        # 7. 排期结果 · 日程视图（按日期和时段展示分组）
        goto(page, '/schedule-results', '07-排期结果-日程视图')
        click_first(page, ['label:has-text("日程视图")', 'button:has-text("日程视图")',
                           '.el-radio-button:has-text("日程视图")'])
        page.wait_for_timeout(1500)
        shot(page, '07-排期结果-日程视图')

        # 8. 操作日志
        goto(page, '/operation-log', '08-操作日志')

        browser.close()
        print('ALL DONE', flush=True)


if __name__ == '__main__':
    sys.exit(main())
