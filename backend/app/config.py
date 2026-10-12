"""Explicit runtime configuration. Never creates tables or sample users.

R2 new implementation against the recovered model/frontend contract. Historical
password formats and historical Alembic graphs are NOT inferred here.
"""
import logging
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='ND_', extra='forbid', hide_input_in_errors=True)
    env: Literal['test','production'] = 'production'
    database_url: str = Field(default='', repr=False)
    database_url_file: Path | None = None
    storage_dir: Path = Path('/var/lib/nondegree/files')
    maintenance_dir: Path | None = None
    allowed_hosts: str = 'localhost,127.0.0.1'
    public_origin: str = 'https://localhost'
    secure_cookie: bool = True
    upload_limit_mb: int = Field(default=10, ge=1, le=100)
    session_hours: int = Field(default=8, ge=1, le=24)
    session_idle_minutes: int = Field(default=60, ge=5, le=480)
    login_window_seconds: int = Field(default=900, ge=60, le=3600)
    login_attempts: int = Field(default=10, ge=3, le=30)
    seed_enabled: bool = False
    auto_create_tables: bool = False
    auto_create_schema: bool = False
    release_guard: bool = True
    adapter_modules: str = ''
    demo_identity_switch_enabled: bool = False
    # 学校移动门户消息推送：留空即关闭；地址按《湖科职消息中心集成标准接口文档v1.0》。
    message_push_yyid: str = ''
    message_push_endpoint: str = 'https://ydmh.hnkjxy.net.cn/ydmh/api/send/send'

    @property
    def demo_cookie_name(self):
        return '__Host-nd_demo_identity' if self.secure_cookie else 'nd_test_demo_identity'

    @property
    def cookie_name(self):
        return '__Host-nd_session' if self.secure_cookie else 'nd_test_session'

    @model_validator(mode='after')
    def validate_runtime(self):
        if self.database_url_file is not None:
            if self.database_url:
                raise ValueError('数据库地址只能使用一种配置方式')
            if self.database_url_file.is_symlink():
                raise ValueError('数据库凭据文件不能是符号链接')
            self.database_url = self.database_url_file.read_text().strip()
        if not self.database_url:
            raise ValueError('未配置数据库连接')
        origin = urlsplit(self.public_origin)
        if origin.scheme not in {'http','https'} or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment or origin.path not in {'','/'}:
            raise ValueError('网站来源地址格式不正确')
        self.public_origin = self.public_origin.rstrip('/')
        hosts = [x.strip() for x in self.allowed_hosts.split(',')]
        if not all(hosts) or '*' in hosts:
            raise ValueError('必须设置明确的网站域名')
        if self.env == 'production':
            if not self.database_url.startswith('mysql+pymysql://'):
                raise ValueError('生产环境必须使用 MySQL 8.4')
            if not self.secure_cookie or origin.scheme != 'https':
                raise ValueError('生产环境必须开启 HTTPS 与安全 Cookie')
            if self.seed_enabled or self.auto_create_schema or self.auto_create_tables or not self.release_guard:
                raise ValueError('生产环境禁止自动建表、样例初始化或绕过发布核验')
        elif not self.database_url.startswith(('sqlite://','mysql+pymysql://')):
            raise ValueError('测试数据库驱动不支持')
        # Default server access logs include SSO tickets; application/nginx logs omit queries.
        logging.getLogger('uvicorn.access').disabled=True
        return self
