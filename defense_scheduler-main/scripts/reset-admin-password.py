#!/usr/bin/env python
"""离线查询/重置本机管理员账号（供运维排查使用）。

对应《使用说明》第十节提到的"联系技术人员通过命令行重置密码"场景。
本工具直接读写 app-data 目录下的 db.sqlite3，不启动服务，也不依赖网络。

用法（在项目根目录执行，使用项目的 .venv）：

    # 查看全部账号、状态、最近登录时间，并检查 INITIAL_ADMIN.txt 是否还有效
    .venv\\Scripts\\python scripts\\reset-admin-password.py --list

    # 把 admin 的密码重置为一个随机强密码（结果打印在屏幕上）
    .venv\\Scripts\\python scripts\\reset-admin-password.py --username admin --generate

    # 重置为指定密码
    .venv\\Scripts\\python scripts\\reset-admin-password.py --username admin --password "MyPass123"

    # 数据目录有多个时，用 --app-data 明确指定
    .venv\\Scripts\\python scripts\\reset-admin-password.py --app-data "release\\campus-blue-20260919\\app-data" --username admin --generate

注意：重置前请先关闭正在运行的程序，避免数据库文件被占用。
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 刻意排除 0/O/o、1/l/I 以及 -/_，避免重置后的密码在手动输入时被看错
SAFE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
GENERATED_PASSWORD_LENGTH = 16


def _relax_console_encoding() -> None:
    """Windows 控制台可能是 GBK/CP437，避免输出中文时抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def find_app_data_candidates() -> list[Path]:
    patterns = [
        PROJECT_ROOT / 'app-data',
        PROJECT_ROOT / 'release' / 'app-data',
        *sorted(PROJECT_ROOT.glob('release/*/app-data')),
    ]
    return [path for path in patterns if (path / 'db.sqlite3').is_file()]


def resolve_app_data(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not (path / 'db.sqlite3').is_file():
            raise SystemExit(f'指定目录下找不到 db.sqlite3：{path}')
        return path

    candidates = find_app_data_candidates()
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise SystemExit('未找到任何 app-data 目录，请用 --app-data 指定。')

    ordered = sorted(candidates, key=lambda p: (p / 'db.sqlite3').stat().st_mtime, reverse=True)
    lines = ['检测到多个 app-data 目录，请用 --app-data 明确指定要操作哪一个：', '']
    for path in ordered:
        stamp = datetime.fromtimestamp((path / 'db.sqlite3').stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        lines.append(f'  --app-data "{path}"    最后修改 {stamp}')
    lines.append('')
    lines.append('提示：本工具不会替你做选择，避免改错实例的数据。')
    raise SystemExit('\n'.join(lines))


def bootstrap_django(app_data: Path) -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    key_file = app_data / 'secret.key'
    secret = key_file.read_text(encoding='utf-8').strip() if key_file.exists() else 'offline-tool-' + 'x' * 40
    os.environ['DJANGO_SECRET_KEY'] = secret
    os.environ.setdefault('DJANGO_DEBUG', 'false')
    os.environ.setdefault('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
    os.environ['DJANGO_DB_PATH'] = str(app_data / 'db.sqlite3')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'defense_scheduler.settings'

    import django

    django.setup()


def read_initial_credentials(credentials_file: Path) -> tuple[str, str]:
    username = ''
    password = ''
    for line in credentials_file.read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('账号:'):
            username = line.split(':', 1)[1].strip()
        elif line.startswith('密码:'):
            password = line.split(':', 1)[1].strip()
    return username, password


def describe_user(user) -> str:
    if user.is_superuser:
        kind = '管理员'
    elif user.is_staff:
        kind = '工作人员'
    else:
        kind = '只读'
    state = '启用' if user.is_active else '停用'
    last = user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else '从未记录'
    return f'类型={kind}  状态={state}  最近登录={last}'


def command_list(app_data: Path) -> int:
    from django.contrib.auth.models import User

    print(f'数据目录: {app_data}')
    print()

    users = list(User.objects.all().order_by('id'))
    if not users:
        print('当前数据库没有任何账号。')
    else:
        print(f'共 {len(users)} 个账号：')
        for user in users:
            print(f'  [{user.id}] {user.username}  {describe_user(user)}')
    print()

    credentials_file = app_data / 'INITIAL_ADMIN.txt'
    if not credentials_file.is_file():
        print(f'未找到 {credentials_file.name}（可能已按安全建议删除）。')
        return 0

    username, password = read_initial_credentials(credentials_file)
    if not username or not password:
        print(f'无法解析 {credentials_file.name}，请手动打开查看。')
        return 0

    user = User.objects.filter(username=username).first()
    if user is None:
        print(f'提示：{credentials_file.name} 记录的账号 {username!r} 在当前数据库中不存在，该文件已过期。')
    elif user.check_password(password):
        print(f'提示：{credentials_file.name} 中的密码对账号 {username!r} 仍然有效。')
    else:
        print(f'提示：{credentials_file.name} 中的密码已失效（账号 {username!r} 的密码已被修改过）。')
        print('      若已忘记当前密码，可用 --password 或 --generate 重置。')
    return 0


def generate_password() -> str:
    return ''.join(secrets.choice(SAFE_ALPHABET) for _ in range(GENERATED_PASSWORD_LENGTH))


def command_reset(args: argparse.Namespace, app_data: Path) -> int:
    from django.contrib.auth.models import User
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.db import transaction
    from django.utils import translation
    from rest_framework.authtoken.models import Token

    username = args.username.strip()
    if not username:
        raise SystemExit('--username 不能为空。')

    if args.generate and args.password:
        raise SystemExit('--generate 与 --password 不能同时使用。')
    if not args.generate and not args.password:
        raise SystemExit('请用 --password 指定新密码，或用 --generate 生成随机密码。')

    new_password = generate_password() if args.generate else args.password.strip()

    user = User.objects.filter(username=username).first()
    if user is None:
        if not args.create:
            raise SystemExit(f'账号 {username!r} 不存在。如确实要新建管理员，请追加 --create。')
        user = User(username=username, is_staff=True, is_superuser=True, is_active=True)

    try:
        with translation.override('zh-hans'):
            validate_password(new_password, user=user if user.pk else None)
    except DjangoValidationError as exc:
        message = '；'.join(exc.messages)
        if not args.force:
            raise SystemExit(f'新密码不符合强度要求：{message}\n如仍要强制设置，请追加 --force。')
        print(f'警告：新密码未通过强度校验（{message}），已按 --force 强制设置。')

    with transaction.atomic():
        if user.pk is None:
            user.set_password(new_password)
            user.save()
            created = True
        else:
            user.set_password(new_password)
            if args.activate:
                user.is_active = True
                user.save(update_fields=['password', 'is_active'])
            else:
                user.save(update_fields=['password'])
            created = False
        removed_tokens = Token.objects.filter(user=user).delete()[0]

    print(f'数据目录: {app_data}')
    print(f'账号 {username!r} 的密码已{"创建" if created else "重置"}。')
    print(f'新密码: {new_password}')
    print(f'已作废该账号的登录令牌 {removed_tokens} 个，其他已登录的浏览器需重新登录。')
    if not user.is_active:
        print('注意：该账号当前为停用状态，仅重置密码仍无法登录，请追加 --activate 重新启用。')
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='reset-admin-password.py',
        description='离线查询/重置本机管理员账号（直接操作 app-data/db.sqlite3）。',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例：\n'
            '  python scripts/reset-admin-password.py --list\n'
            '  python scripts/reset-admin-password.py --username admin --generate\n'
            '  python scripts/reset-admin-password.py --username admin --password "MyPass123"\n'
        ),
    )
    parser.add_argument('--app-data', help='app-data 目录路径；不填则在项目内自动探测，探测到多个时会列出候选并要求指定')
    parser.add_argument('--list', action='store_true', help='仅列出账号、状态与最近登录时间，不修改任何数据')
    parser.add_argument('--username', default='admin', help='要重置的账号，默认 admin')
    parser.add_argument('--password', help='新密码')
    parser.add_argument('--generate', action='store_true', help='生成一个随机强密码并打印')
    parser.add_argument('--create', action='store_true', help='账号不存在时新建为管理员')
    parser.add_argument('--activate', action='store_true', help='同时把停用的账号重新启用')
    parser.add_argument('--force', action='store_true', help='跳过密码强度校验')
    return parser


def main() -> int:
    _relax_console_encoding()
    args = build_parser().parse_args()
    app_data = resolve_app_data(args.app_data)
    bootstrap_django(app_data)

    if args.list:
        return command_list(app_data)

    print('请确认程序当前已关闭（避免数据库被占用）。')
    return command_reset(args, app_data)


if __name__ == '__main__':
    raise SystemExit(main())
