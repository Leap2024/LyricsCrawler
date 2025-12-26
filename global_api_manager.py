"""
全局API管理器
提供统一的API请求接口，集成速率限制和密钥轮换
"""

import os
import sys
import time
import threading
from rate_limiter import get_rate_limiter, make_api_request


class GlobalAPIManager:
    """全局API管理器，提供统一的请求接口"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_manager()
            return cls._instance

    def _init_manager(self):
        """初始化管理器"""
        self.rate_limiter = get_rate_limiter()
        self.stats = {
            'successful_requests': 0,
            'failed_requests': 0,
            'total_wait_time': 0,
            'last_request_time': 0
        }
        self.stats_lock = threading.Lock()

        print("[APIManager] 全局API管理器初始化完成")

    def add_api_key(self, api_key):
        """添加API密钥到全局池"""
        return self.rate_limiter.add_api_key(api_key)

    def search_artist(self, artist_name, api_key=None):
        """搜索艺术家（通过Genius API）"""
        if not api_key:
            api_key = self.rate_limiter.get_next_api_key()
            if not api_key:
                raise Exception("没有可用的API密钥")

        url = "https://api.genius.com/search"
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {"q": artist_name}

        try:
            start_time = time.time()
            response = make_api_request(
                requests.get, url, headers=headers, params=params, timeout=15
            )
            elapsed = time.time() - start_time

            with self.stats_lock:
                self.stats['successful_requests'] += 1
                self.stats['total_wait_time'] += elapsed
                self.stats['last_request_time'] = time.time()

            return response.json()

        except Exception as e:
            with self.stats_lock:
                self.stats['failed_requests'] += 1

            # 如果提供了特定密钥，标记失败
            if api_key:
                self.rate_limiter.mark_key_failure(api_key)

            raise

    def get_artist_songs(self, artist_id, api_key=None, page=1, per_page=50):
        """获取艺术家的歌曲列表"""
        if not api_key:
            api_key = self.rate_limiter.get_next_api_key()
            if not api_key:
                raise Exception("没有可用的API密钥")

        url = f"https://api.genius.com/artists/{artist_id}/songs"
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {
            "per_page": per_page,
            "page": page,
            "sort": "title"
        }

        try:
            start_time = time.time()
            response = make_api_request(
                requests.get, url, headers=headers, params=params, timeout=15
            )
            elapsed = time.time() - start_time

            with self.stats_lock:
                self.stats['successful_requests'] += 1
                self.stats['total_wait_time'] += elapsed

            return response.json()

        except Exception as e:
            with self.stats_lock:
                self.stats['failed_requests'] += 1

            if api_key:
                self.rate_limiter.mark_key_failure(api_key)

            raise

    def get_song_details(self, song_id, api_key=None):
        """获取歌曲详情"""
        if not api_key:
            api_key = self.rate_limiter.get_next_api_key()
            if not api_key:
                raise Exception("没有可用的API密钥")

        url = f"https://api.genius.com/songs/{song_id}"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            start_time = time.time()
            response = make_api_request(
                requests.get, url, headers=headers, timeout=15
            )
            elapsed = time.time() - start_time

            with self.stats_lock:
                self.stats['successful_requests'] += 1
                self.stats['total_wait_time'] += elapsed

            return response.json()

        except Exception as e:
            with self.stats_lock:
                self.stats['failed_requests'] += 1

            if api_key:
                self.rate_limiter.mark_key_failure(api_key)

            raise

    def get_status(self):
        """获取管理器状态"""
        limiter_status = self.rate_limiter.get_status()

        with self.stats_lock:
            stats_copy = self.stats.copy()

        return {
            **limiter_status,
            **stats_copy,
            'avg_wait_time': stats_copy['total_wait_time'] / max(1, stats_copy['successful_requests'])
        }

    def print_status(self):
        """打印状态信息"""
        status = self.get_status()

        print(f"\n{'=' * 60}")
        print("全局API管理器状态:")
        print(f"{'=' * 60}")
        print(f"请求统计:")
        print(f"  成功请求: {status['successful_requests']}")
        print(f"  失败请求: {status['failed_requests']}")
        print(f"  平均等待时间: {status['avg_wait_time']:.2f}秒")
        print(f"  总等待时间: {status['total_wait_time']:.1f}秒")
        print()
        print(f"速率限制状态:")
        print(f"  总请求数: {status['total_requests']}")
        print(f"  最近请求: {status['recent_requests']}")
        print(f"  API密钥数: {status['api_keys_count']}")
        print(f"  最小间隔: {status['min_interval']:.2f}秒")

        if status['pause_until'] > 0:
            print(f"  剩余暂停: {status['pause_until']:.1f}秒")

        print(f"{'=' * 60}")


# 全局实例和便捷函数
_global_api_manager = None


def get_api_manager():
    """获取全局API管理器实例"""
    global _global_api_manager
    if _global_api_manager is None:
        _global_api_manager = GlobalAPIManager()
    return _global_api_manager


def add_api_key_to_pool(api_key):
    """将API密钥添加到全局池"""
    manager = get_api_manager()
    return manager.add_api_key(api_key)


if __name__ == "__main__":
    # 测试代码
    import requests

    manager = get_api_manager()

    # 添加一些测试密钥
    test_keys = os.getenv('GENIUS_API_KEYS', '').split(',')
    for key in test_keys:
        if key.strip():
            manager.add_api_key(key.strip())

    if not test_keys or not any(test_keys):
        print("注意：没有找到API密钥，请在环境变量 GENIUS_API_KEYS 中设置")
        print("示例: export GENIUS_API_KEYS='key1,key2,key3'")

    manager.print_status()