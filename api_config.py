"""
API配置和限制管理
"""


class APIConfig:
    # API调用配置
    BASE_DELAY = 2  # 基础延迟（秒）
    PAGE_DELAY = 3  # 分页请求延迟
    SONG_DELAY = 2  # 歌曲详情请求延迟

    # API限制阈值
    REMAINING_THRESHOLD = 100  # 当剩余调用次数小于此值时增加延迟

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY_MULTIPLIER = 5  # 重试延迟乘数

    # 并发控制
    MAX_CONCURRENT_REQUESTS = 1  # 最大并发请求数

    @staticmethod
    def get_delay_based_on_remaining(remaining):
        """根据剩余API调用次数返回适当的延迟"""
        if remaining < 50:
            return 10
        elif remaining < 100:
            return 5
        elif remaining < 200:
            return 3
        else:
            return APIConfig.BASE_DELAY