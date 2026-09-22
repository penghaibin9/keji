"""湖南科技职业学院数据中台兼容入口。

P2 起使用配置驱动 REST/JSON Adapter；学校正式接口路径、鉴权、字段根路径、
游标等填写到 Connection.config.adapter，凭据放 ND_MIDDLE_SECRET。
"""
from app.adapters import ConfigurableDataHubAdapter

HnkjDataHubAdapter = ConfigurableDataHubAdapter
