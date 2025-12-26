"""
全局API速率限制器
所有Genius API请求都必须通过这个限制器来管理请求频率
"""

import threading
import time
import requests
import json
from datetime import datetime, timedelta


class APIRateLimiter:
    """
    全局API速率限制器（单例模式）
    管理所有Genius API请求的频率，防止触发API限制
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式实现"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_limiter()
            return cls._instance

    def _init_limiter(self):
        """初始化限制器"""
        # 全局速率限制设置
        self.max_requests_per_minute = 30  # 保守的全局限制
        self.min_interval = 60.0 / self.max_requests_per_minute

        # 请求追踪
        self.last_request_time = 0
        self.request_history = []  # 记录最近请求时间
        self.total_requests = 0

        # API密钥管理
        self.api_keys = []  # 可用的API密钥列表
        self.current_key_index = 0
        self.key_failures = {}  # 记录每个密钥的失败次数

        # 状态监控
        self.is_paused = False
        self.pause_until = 0

        # 响应头分析
        self.last_headers = {}

        # 线程安全
        self.lock = threading.RLock()

        # 配置文件
        self.config_file = "api_rate_limiter_config.json"
        self.load_config()

        print(f"[RateLimiter] 初始化完成，全局速率限制: {self.max_requests_per_minute} 请求/分钟")

    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.api_keys = config.get('api_keys', [])
                    self.max_requests_per_minute = config.get('max_requests_per_minute', 30)
                    self.min_interval = 60.0 / self.max_requests_per_minute
                    print(f"[RateLimiter] 从配置文件加载了 {len(self.api_keys)} 个API密钥")
        except Exception as e:
            print(f"[RateLimiter] 加载配置失败: {e}")

    def save_config(self):
        """保存配置文件"""
        try:
            config = {
                'api_keys': self.api_keys,
                'max_requests_per_minute': self.max_requests_per_minute,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[RateLimiter] 保存配置失败: {e}")

    def add_api_key(self, api_key):
        """添加API密钥到轮换池"""
        with self.lock:
            if api_key and api_key not in self.api_keys:
                self.api_keys.append(api_key)
                self.key_failures[api_key] = 0
                self.save_config()
                return True
        return False

    def get_next_api_key(self):
        """获取下一个可用的API密钥（轮询）"""
        with self.lock:
            if not self.api_keys:
                return None

            # 尝试找到可用的密钥
            start_index = self.current_key_index
            for _ in range(len(self.api_keys)):
                key = self.api_keys[self.current_key_index]
                self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)

                # 检查密钥是否被标记为失败过多
                if self.key_failures.get(key, 0) < 5:  # 失败次数少于5次
                    return key

            # 所有密钥都有问题，重置计数器
            for key in self.key_failures:
                self.key_failures[key] = max(0, self.key_failures[key] - 1)

            return self.api_keys[self.current_key_index]

    def mark_key_failure(self, api_key):
        """标记API密钥失败"""
        with self.lock:
            if api_key in self.key_failures:
                self.key_failures[api_key] = self.key_failures.get(api_key, 0) + 1
                print(f"[RateLimiter] API密钥失败次数增加: {api_key[:10]}... ({self.key_failures[api_key]})")

    def mark_key_success(self, api_key):
        """标记API密钥成功"""
        with self.lock:
            if api_key in self.key_failures:
                self.key_failures[api_key] = max(0, self.key_failures[api_key] - 1)

    def _calculate_wait_time(self):
        """计算需要等待的时间"""
        with self.lock:
            current_time = time.time()

            # 检查是否处于暂停状态
            if self.is_paused and current_time < self.pause_until:
                return max(0, self.pause_until - current_time)

            # 清除旧的请求记录（保留最近2分钟）
            cutoff_time = current_time - 120
            self.request_history = [t for t in self.request_history if t > cutoff_time]

            # 如果请求历史为空，不需要等待
            if not self.request_history:
                return 0

            # 计算平均请求间隔
            if len(self.request_history) >= 2:
                intervals = [self.request_history[i + 1] - self.request_history[i]
                             for i in range(len(self.request_history) - 1)]
                avg_interval = sum(intervals) / len(intervals) if intervals else self.min_interval
            else:
                avg_interval = self.min_interval

            # 根据响应头动态调整
            if self.last_headers:
                remaining = int(self.last_headers.get('X-RateLimit-Remaining', 1000))
                limit = int(self.last_headers.get('X-RateLimit-Limit', 1000))

                # 如果剩余配额很少，大幅增加间隔
                if remaining < 10:
                    target_interval = 10.0  # 10秒间隔
                elif remaining < 50:
                    target_interval = 5.0  # 5秒间隔
                elif remaining < 100:
                    target_interval = 2.0  # 2秒间隔
                else:
                    target_interval = max(self.min_interval, avg_interval)

                # 确保不会太快
                return max(0, target_interval - (current_time - self.last_request_time))

            # 默认计算
            elapsed = current_time - self.last_request_time
            wait_time = max(0, self.min_interval - elapsed)

            return wait_time

    def wait_if_needed(self):
        """如果需要等待，则等待"""
        wait_time = self._calculate_wait_time()

        if wait_time > 0:
            # 记录等待日志（避免频繁打印）
            if wait_time > 5:
                print(f"[RateLimiter] 等待 {wait_time:.1f} 秒以避免API限制")
            time.sleep(wait_time)

        return wait_time

    def pause(self, seconds):
        """暂停指定时间"""
        with self.lock:
            self.is_paused = True
            self.pause_until = time.time() + seconds
            print(f"[RateLimiter] 暂停 {seconds} 秒")

    def resume(self):
        """恢复请求"""
        with self.lock:
            self.is_paused = False
            self.pause_until = 0

    def make_request(self, request_func, *args, **kwargs):
        """
        执行API请求，自动处理速率限制
        Args:
            request_func: requests.get 或 requests.post 等函数
            *args, **kwargs: 传递给请求函数的参数
        Returns:
            响应对象
        """
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # 等待合适的时机
                self.wait_if_needed()

                # 准备请求
                current_time = time.time()

                # 如果请求包含headers，确保使用正确的API密钥
                headers = kwargs.get('headers', {})
                if 'Authorization' in headers:
                    # 提取当前的API密钥
                    auth_header = headers['Authorization']
                    if auth_header.startswith('Bearer '):
                        current_key = auth_header[7:]

                        # 检查是否需要更换密钥
                        if self.key_failures.get(current_key, 0) >= 3:
                            new_key = self.get_next_api_key()
                            if new_key and new_key != current_key:
                                headers['Authorization'] = f'Bearer {new_key}'
                                kwargs['headers'] = headers
                                print(f"[RateLimiter] 切换API密钥: {current_key[:10]}... -> {new_key[:10]}...")

                # 执行请求
                response = request_func(*args, **kwargs)

                # 更新状态
                with self.lock:
                    self.last_request_time = current_time
                    self.request_history.append(current_time)
                    self.total_requests += 1
                    self.last_headers = dict(response.headers)

                    # 标记密钥成功
                    auth_header = response.request.headers.get('Authorization', '')
                    if auth_header.startswith('Bearer '):
                        api_key = auth_header[7:]
                        self.mark_key_success(api_key)

                # 检查响应状态码
                if response.status_code == 200:
                    return response

                # 处理错误状态码
                elif response.status_code == 429:  # 太多请求
                    # 尝试从响应头获取等待时间
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        wait_time = int(retry_after)
                    else:
                        wait_time = 60 * (attempt + 1)  # 指数退避

                    # 标记当前密钥失败
                    auth_header = response.request.headers.get('Authorization', '')
                    if auth_header.startswith('Bearer '):
                        api_key = auth_header[7:]
                        self.mark_key_failure(api_key)

                    print(f"[RateLimiter] 429错误，等待 {wait_time} 秒")
                    self.pause(wait_time)
                    time.sleep(wait_time)
                    self.resume()

                elif response.status_code == 401:  # 未授权
                    print(f"[RateLimiter] 401错误，API密钥可能无效")
                    auth_header = response.request.headers.get('Authorization', '')
                    if auth_header.startswith('Bearer '):
                        api_key = auth_header[7:]
                        self.mark_key_failure(api_key)

                    # 如果这是最后一次尝试，抛出异常
                    if attempt == max_retries - 1:
                        raise Exception(f"API密钥无效: {response.status_code}")

                else:
                    # 其他错误
                    print(f"[RateLimiter] 请求失败: {response.status_code}")
                    if attempt == max_retries - 1:
                        response.raise_for_status()

            except requests.exceptions.ConnectionError as e:
                print(f"[RateLimiter] 连接错误: {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(5 * (attempt + 1))

            except requests.exceptions.Timeout as e:
                print(f"[RateLimiter] 请求超时: {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(5 * (attempt + 1))

            except Exception as e:
                print(f"[RateLimiter] 请求异常: {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(5 * (attempt + 1))

        raise Exception(f"请求失败，已重试{max_retries}次")

    def get_status(self):
        """获取限制器状态"""
        with self.lock:
            return {
                'total_requests': self.total_requests,
                'recent_requests': len(self.request_history),
                'api_keys_count': len(self.api_keys),
                'is_paused': self.is_paused,
                'pause_until': self.pause_until - time.time() if self.pause_until > time.time() else 0,
                'min_interval': self.min_interval,
                'key_failures': {k[:10] + '...': v for k, v in self.key_failures.items()}
            }

    def print_status(self):
        """打印当前状态"""
        status = self.get_status()
        print(f"\n{'=' * 50}")
        print("API速率限制器状态:")
        print(f"  总请求数: {status['total_requests']}")
        print(f"  最近2分钟请求: {status['recent_requests']}")
        print(f"  API密钥数量: {status['api_keys_count']}")
        print(f"  最小间隔: {status['min_interval']:.2f}秒")
        print(f"  是否暂停: {status['is_paused']}")
        if status['pause_until'] > 0:
            print(f"  剩余暂停时间: {status['pause_until']:.1f}秒")
        print(f"  密钥失败次数: {status['key_failures']}")
        print(f"{'=' * 50}\n")


# 全局实例
_global_rate_limiter = None


def get_rate_limiter():
    """获取全局速率限制器实例"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = APIRateLimiter()
    return _global_rate_limiter


# 兼容性函数
def make_api_request(request_func, *args, **kwargs):
    """兼容性函数，直接调用全局限制器的make_request"""
    limiter = get_rate_limiter()
    return limiter.make_request(request_func, *args, **kwargs)


if __name__ == "__main__":
    # 测试代码
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

    limiter = get_rate_limiter()

    # 添加示例API密钥（实际使用时从环境变量或配置文件读取）
    test_keys = [
        "demo_key_1",
        "demo_key_2"
    ]

    for key in test_keys:
        limiter.add_api_key(key)

    # 测试状态打印
    limiter.print_status()

    print("速率限制器初始化完成，可在其他文件中导入使用:")
    print("from rate_limiter import get_rate_limiter, make_api_request")