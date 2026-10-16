# -*- coding: utf-8 -*-
"""智能答辩分组编排系统 - 主程序入口。

用法：
    python main.py

首次从源码运行前：安装 requirements.txt，再执行 npm ci 和 npm run build。
前端 dist/ 产物必须存在；完整步骤见 WIKI.md。

启动后自动完成：
1. 初始化运行时配置（密钥、数据目录 app-data/）
2. 执行数据库迁移（SQLite）
3. 首次运行自动生成管理员账号（写入 app-data/INITIAL_ADMIN.txt）
4. 启动本地服务并打开浏览器，默认 http://127.0.0.1:8000

可选环境变量：
    DEFENSE_SCHEDULER_PORT          监听端口，默认 8000
    DEFENSE_SCHEDULER_HOST          监听地址，默认 127.0.0.1
    DEFENSE_SCHEDULER_OPEN_BROWSER  是否自动打开浏览器（true/false，默认 true）
"""

from desktop_launcher import main

if __name__ == '__main__':
    main()
