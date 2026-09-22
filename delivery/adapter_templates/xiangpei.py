"""湘培直通车兼容入口。

P2 起使用配置驱动省平台 Adapter；正式路径、鉴权/签名、业务成功码、回执字段
填写到 Connection.config.adapter，凭据放 ND_PROVINCE_SECRET。
"""
from app.adapters import ConfigurableProvinceAdapter

XiangpeiAdapter = ConfigurableProvinceAdapter
