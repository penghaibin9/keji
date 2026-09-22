"""湖南科技职业学院 SSO 兼容入口。

P2 起不再要求二次手写 Adapter：正式协议参数填写到 Connection.config.adapter，
服务端凭据放 ND_SSO_SECRET，生产注册使用 school_adapters.register。

注意：ConfigurableSsoAdapter 当前支持 CAS、OIDC、OAuth2、JSON-ticket。
若学校正式规范确认是 SAML2 HTTP-POST/XML-DSig，必须启用独立成熟 SAML/XMLSec
实现，不能用普通 XML 解析替代签名验证。
"""
from app.adapters import ConfigurableSsoAdapter

HnkjSsoAdapter = ConfigurableSsoAdapter
