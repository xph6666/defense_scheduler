import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalRuntimeConfig:
    app_root: Path
    bundle_root: Path
    app_data_dir: Path
    secret_key_file: Path


@dataclass(frozen=True)
class InitialAdminCredentials:
    username: str
    password: str
    credentials_file: Path


def get_app_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_bundle_root() -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def _load_or_create_secret(secret_key_file: Path) -> str:
    if secret_key_file.exists():
        return secret_key_file.read_text(encoding='utf-8').strip()

    secret = secrets.token_urlsafe(48)
    secret_key_file.write_text(secret, encoding='utf-8')
    return secret


def configure_local_runtime(app_root: Path | None = None, bundle_root: Path | None = None) -> LocalRuntimeConfig:
    resolved_app_root = app_root or get_app_root()
    resolved_bundle_root = bundle_root or get_bundle_root()
    app_data_dir = resolved_app_root / 'app-data'
    app_data_dir.mkdir(parents=True, exist_ok=True)

    secret_key_file = app_data_dir / 'secret.key'
    os.environ.setdefault('DJANGO_SECRET_KEY', _load_or_create_secret(secret_key_file))
    os.environ.setdefault('DJANGO_DEBUG', 'false')
    os.environ.setdefault('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
    os.environ.setdefault('DJANGO_DB_PATH', str(app_data_dir / 'db.sqlite3'))
    os.environ.setdefault('FRONTEND_DIST_DIR', str(resolved_bundle_root / 'dist'))

    return LocalRuntimeConfig(
        app_root=resolved_app_root,
        bundle_root=resolved_bundle_root,
        app_data_dir=app_data_dir,
        secret_key_file=secret_key_file,
    )


def ensure_initial_admin(app_data_dir: Path) -> InitialAdminCredentials | None:
    from django.contrib.auth.models import User

    if User.objects.exists():
        return None

    # 账号与密码都用 strip 后的值：环境变量常从记事本/表格复制而来，
    # 两端空白会写进 INITIAL_ADMIN.txt，随后在登录页被复制回来造成认证失败。
    username = os.environ.get('INITIAL_ADMIN_USERNAME', 'admin').strip() or 'admin'
    password = (os.environ.get('INITIAL_ADMIN_PASSWORD') or '').strip() or secrets.token_urlsafe(18)
    User.objects.create_superuser(username=username, password=password)

    credentials_file = app_data_dir / 'INITIAL_ADMIN.txt'
    credentials_file.write_text(
        '\n'.join([
            '首次启动已创建管理员账号。',
            f'账号: {username}',
            f'密码: {password}',
            '登录后请立即修改密码，并妥善保存此文件。',
            '',
        ]),
        encoding='utf-8',
    )
    return InitialAdminCredentials(username=username, password=password, credentials_file=credentials_file)
