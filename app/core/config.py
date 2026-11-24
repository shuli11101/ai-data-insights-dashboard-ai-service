"""应用配置：统一读取 AI_ 前缀的环境变量，敏感值只放 .env。"""

from pydantic_settings import BaseSettings, SettingsConfigDict

# 配置
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_", env_file=".env", extra="ignore")

    # 内部调用鉴权，必须与 Java 侧 app.ai.internal-token 完全一致
    internal_token: str = "change-me"

    # 通道：fake 返回假数据流（联调、不花钱）；deepseek 调用真实模型
    provider: str = "fake"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 单次模型请求超时（秒），需小于 Java 侧 stream-timeout
    request_timeout: float = 120.0

    # 上下文最多携带的历史消息条数
    max_history: int = 20


settings = Settings()