import os
import re
import time
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import requests
from lyricsgenius import Genius

try:
    from rate_limiter import get_rate_limiter, make_api_request
    from global_api_manager import get_api_manager, add_api_key_to_pool

    RATE_LIMITER_AVAILABLE = True
except ImportError:
    RATE_LIMITER_AVAILABLE = False
    print("警告: 未找到速率限制器，API请求将不受全局管理")


class LyricsDownloaderGUI:

    def __init__(self, root, embedded_mode=False):
        """
        初始化歌词下载器GUI

        Args:
            root: 父窗口或父容器
            embedded_mode: 是否为嵌入式模式（在多任务环境中）
        """
        self.embedded_mode = embedded_mode
        self.root = root

        # 如果是嵌入式模式，不使用窗口的title和geometry
        if not embedded_mode:
            self.root.title("Genius歌词下载器 - 专业版")
            self.root.geometry("1400x900")

        # API状态变量
        self.access_token = tk.StringVar()
        self.save_directory = tk.StringVar(value=os.path.expanduser("~/Desktop/Genius歌词"))
        self.artists_queue = []
        self.currently_processing = False
        self.stop_requested = False
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.error_wait_time = 120

        # 添加恢复点记录
        self.resume_points = {}  # 记录每个艺人的断点位置

        # 初始化Genius对象
        self.genius = None

        self.setup_ui()
        self.load_settings()

        # 初始化完成后检查已完成的艺人
        if not embedded_mode:  # 只在独立模式下检查
            self.root.after(100, self.check_completed_artists)

            # 在初始化Genius对象之前，注册API密钥到全局池
        if RATE_LIMITER_AVAILABLE and self.access_token.get():
            try:
                add_api_key_to_pool(self.access_token.get())
            except:
                pass

    # 在 LyricsDownloaderGUI 类中添加方法
    def check_api_rate_limit(self):
        """检查API调用限制"""
        try:
            # 简单的API状态检查
            search_url = "https://api.genius.com/search"
            headers = {"Authorization": f"Bearer {self.access_token.get()}"}
            params = {"q": "test"}

            response = requests.get(search_url, headers=headers, params=params, timeout=5)

            remaining = int(response.headers.get('X-RateLimit-Remaining', 999))
            limit = int(response.headers.get('X-RateLimit-Limit', 1000))

            return remaining, limit
        except:
            return 999, 1000  # 默认值

    def setup_ui(self):
        # 主框架
        if self.embedded_mode:
            # 嵌入式模式：直接将主框架放在传入的root中
            main_frame = ttk.Frame(self.root, padding="10")
            main_frame.pack(fill=tk.BOTH, expand=True)
        else:
            # 独立模式：使用grid布局
            main_frame = ttk.Frame(self.root, padding="10")
            main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

            # 配置行权重
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(0, weight=1)

        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)

        # 标题
        title_label = ttk.Label(main_frame, text="Genius歌词批量下载器", font=("Arial", 18, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 15))

        # API密钥配置
        api_frame = ttk.LabelFrame(main_frame, text="API配置", padding="10")
        api_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        api_frame.columnconfigure(1, weight=1)

        ttk.Label(api_frame, text="Genius API密钥:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.token_entry = ttk.Entry(api_frame, textvariable=self.access_token, show="*")
        self.token_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))

        show_btn = ttk.Button(api_frame, text="显示", command=self.toggle_token_visibility)
        show_btn.grid(row=0, column=2, padx=(0, 10))

        ttk.Label(api_frame, text="保存路径:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))

        path_frame = ttk.Frame(api_frame)
        path_frame.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        path_frame.columnconfigure(0, weight=1)

        self.path_entry = ttk.Entry(path_frame, textvariable=self.save_directory)
        self.path_entry.grid(row=0, column=0, sticky=(tk.W, tk.E))

        browse_btn = ttk.Button(path_frame, text="浏览", command=self.browse_directory)
        browse_btn.grid(row=0, column=1, padx=(5, 0))

        # 创建分隔的框架
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)

        # 左侧：艺人队列管理
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)

        # 右侧：日志和控制区域
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=2)

        # ==================== 左侧面板布局 ====================
        batch_frame = ttk.LabelFrame(left_frame, text="批量添加艺人", padding="10")
        batch_frame.pack(fill=tk.X, padx=5, pady=(0, 10))

        batch_help = ttk.Label(batch_frame, text="在此输入艺人名称，每行一个，然后点击'批量添加'",
                               font=("Arial", 9))
        batch_help.pack(anchor=tk.W, pady=(0, 5))

        batch_input_frame = ttk.Frame(batch_frame)
        batch_input_frame.pack(fill=tk.X, pady=(0, 10))

        self.artist_text = scrolledtext.ScrolledText(batch_input_frame, height=6, wrap=tk.WORD)
        self.artist_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        batch_btn_frame = ttk.Frame(batch_input_frame)
        batch_btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        ttk.Button(batch_btn_frame, text="批量添加", command=self.batch_add_artists,
                   width=12).pack(pady=(0, 5))
        ttk.Button(batch_btn_frame, text="清空输入", command=self.clear_text,
                   width=12).pack(pady=5)

        file_btn_frame = ttk.Frame(batch_frame)
        file_btn_frame.pack(fill=tk.X)

        ttk.Button(file_btn_frame, text="📥 从文件导入", command=self.import_queue).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(file_btn_frame, text="📤 导出到文件", command=self.export_queue).pack(side=tk.LEFT)

        # 队列列表区域
        list_frame = ttk.LabelFrame(left_frame, text="艺人队列列表", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 10))

        list_header = ttk.Frame(list_frame)
        list_header.pack(fill=tk.X, pady=(0, 10))

        self.queue_count_label = ttk.Label(list_header, text="队列中: 0 个艺人", font=("Arial", 10, "bold"))
        self.queue_count_label.pack(side=tk.LEFT)

        quick_btn_frame = ttk.Frame(list_header)
        quick_btn_frame.pack(side=tk.RIGHT)

        ttk.Button(quick_btn_frame, text="全选", command=self.select_all, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_btn_frame, text="反选", command=self.invert_selection, width=8).pack(side=tk.LEFT, padx=2)

        # 新增：检测已完成按钮
        check_completed_btn = ttk.Button(quick_btn_frame, text="检测已完成", command=self.check_completed_artists,
                                         width=10)
        check_completed_btn.pack(side=tk.LEFT, padx=(10, 0))

        # 艺人列表（Treeview）
        columns = ('序号', '艺人名称', '状态', '歌曲', '成功', '失败')
        self.artist_tree = ttk.Treeview(list_frame, columns=columns, show='headings',
                                        selectmode='extended', height=20)

        self.artist_tree.heading('序号', text='序号')
        self.artist_tree.heading('艺人名称', text='艺人名称')
        self.artist_tree.heading('状态', text='状态')
        self.artist_tree.heading('歌曲', text='歌曲')
        self.artist_tree.heading('成功', text='成功')
        self.artist_tree.heading('失败', text='失败')

        self.artist_tree.column('序号', width=50, anchor=tk.CENTER)
        self.artist_tree.column('艺人名称', width=200)
        self.artist_tree.column('状态', width=100, anchor=tk.CENTER)
        self.artist_tree.column('歌曲', width=70, anchor=tk.CENTER)
        self.artist_tree.column('成功', width=70, anchor=tk.CENTER)
        self.artist_tree.column('失败', width=70, anchor=tk.CENTER)

        tree_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.artist_tree.yview)
        self.artist_tree.configure(yscrollcommand=tree_scroll.set)

        self.artist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 创建右键菜单
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="编辑艺人", command=lambda: self.edit_artist(None))
        self.context_menu.add_command(label="删除选中", command=self.remove_selected_artists)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="上移", command=self.move_up)
        self.context_menu.add_command(label="下移", command=self.move_down)

        # 绑定事件
        self.artist_tree.bind('<Double-1>', self.edit_artist)
        self.artist_tree.bind('<Button-3>', self.show_context_menu)
        self.artist_tree.bind('<Delete>', lambda e: self.remove_selected_artists())
        self.artist_tree.bind('<Control-a>', lambda e: self.select_all())

        # 队列操作按钮
        queue_buttons_frame = ttk.Frame(left_frame)
        queue_buttons_frame.pack(fill=tk.X, padx=5, pady=(0, 10))

        basic_frame = ttk.Frame(queue_buttons_frame)
        basic_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(basic_frame, text="🔼 上移", command=self.move_up, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(basic_frame, text="🔽 下移", command=self.move_down, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(basic_frame, text="✏️ 编辑", command=lambda: self.edit_artist(None), width=12).pack(side=tk.LEFT,
                                                                                                       padx=2)
        ttk.Button(basic_frame, text="📊 统计", command=self.show_statistics, width=12).pack(side=tk.LEFT, padx=2)

        delete_frame = ttk.Frame(queue_buttons_frame)
        delete_frame.pack(fill=tk.X)

        style = ttk.Style()
        style.configure("Danger.TButton", foreground="white", background="#dc3545")

        self.delete_btn = ttk.Button(delete_frame, text="🗑️ 删除选中艺人",
                                     command=self.remove_selected_artists,
                                     style="Danger.TButton", width=20)
        self.delete_btn.pack(side=tk.LEFT, padx=2)

        self.clear_btn = ttk.Button(delete_frame, text="🗑️ 清空整个队列",
                                    command=self.clear_queue,
                                    style="Danger.TButton", width=20)
        self.clear_btn.pack(side=tk.LEFT, padx=2)

        # ==================== 右侧面板布局 ====================
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        # 控制面板
        control_frame = ttk.LabelFrame(right_frame, text="下载控制", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10), padx=(10, 0))
        control_frame.columnconfigure(0, weight=1)

        control_btn_frame = ttk.Frame(control_frame)
        control_btn_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        # 修改：为开始下载按钮添加从选中开始的功能
        self.start_btn = ttk.Button(control_btn_frame, text="▶ 开始下载", command=self.start_download,
                                    style="Accent.TButton", width=15)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        # 新增：从选中开始下载按钮
        self.start_selected_btn = ttk.Button(control_btn_frame, text="▶ 从选中开始",
                                             command=self.start_download_from_selected,
                                             style="Accent.TButton", width=15)
        self.start_selected_btn.pack(side=tk.LEFT, padx=5)

        self.pause_btn = ttk.Button(control_btn_frame, text="⏸ 暂停", command=self.pause_download,
                                    state=tk.DISABLED, width=10)
        self.pause_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(control_btn_frame, text="⏹ 停止", command=self.stop_download,
                                   state=tk.DISABLED, width=10)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # 新增：断点续传按钮
        self.resume_btn = ttk.Button(control_btn_frame, text="↻ 断点续传", command=self.resume_download,
                                     state=tk.DISABLED, width=12)
        self.resume_btn.pack(side=tk.LEFT, padx=5)

        config_btn_frame = ttk.Frame(control_frame)
        config_btn_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Button(config_btn_frame, text="⚙ 保存配置", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(config_btn_frame, text="🔄 重新加载", command=self.load_settings).pack(side=tk.LEFT, padx=5)

        # 进度显示
        progress_frame = ttk.Frame(control_frame)
        progress_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E))

        self.progress_label = ttk.Label(progress_frame, text="0%", width=5)
        self.progress_label.grid(row=0, column=1, padx=(10, 0))

        # 状态显示
        status_frame = ttk.Frame(control_frame)
        status_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))

        self.status_label = ttk.Label(status_frame, text="就绪", font=("Arial", 10))
        self.status_label.pack(side=tk.LEFT)

        self.api_status_label = ttk.Label(status_frame, text=" | API状态: 未连接", font=("Arial", 9), foreground="gray")
        self.api_status_label.pack(side=tk.LEFT, padx=(10, 0))

        # 日志区域
        log_frame = ttk.LabelFrame(right_frame, text="下载日志", padding="10")
        log_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10), padx=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 统计信息
        stats_frame = ttk.LabelFrame(right_frame, text="实时统计", padding="10")
        stats_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=(10, 0))

        self.stats_label = ttk.Label(stats_frame,
                                     text="艺人: 0 | 歌曲总数: 0 | 成功: 0 | 失败: 0 | 成功率: 0%",
                                     font=("Arial", 10))
        self.stats_label.pack(anchor=tk.W)

        self.error_label = ttk.Label(stats_frame,
                                     text="API错误: 0 | 网络错误: 0 | 等待时间: 0秒",
                                     font=("Arial", 9), foreground="red")
        self.error_label.pack(anchor=tk.W, pady=(5, 0))

        # 底部状态栏
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))

        self.help_label = ttk.Label(bottom_frame,
                                    text="提示: 右键点击艺人可进行编辑或删除，使用Delete键可快速删除选中艺人",
                                    font=("Arial", 9))
        self.help_label.pack(side=tk.LEFT)

        version_label = ttk.Label(bottom_frame, text="版本 1.2.0", font=("Arial", 9), foreground="gray")
        version_label.pack(side=tk.RIGHT)

        # 创建自定义样式
        self.style = ttk.Style()
        self.style.configure("Accent.TButton", font=("Arial", 10, "bold"))

    def _update_log(self, message, color):
        """更新日志显示"""
        try:
            # 检查日志文本框是否存在
            if not hasattr(self, 'log_text') or not self.log_text or not self.log_text.winfo_exists():
                return
            self.log_text.insert(tk.END, message)
            self.log_text.see(tk.END)
            self.log_text.update_idletasks()
        except Exception as e:
            # 如果组件已经销毁，静默失败
            pass

    # 原有的其他方法保持不变...
    # 新增：保存歌曲列表到metadata.json
    def save_artist_metadata(self, artist_name, artist_id, songs, artist_path):
        """保存艺人的歌曲列表到metadata.json"""
        metadata = {
            'artist_name': artist_name,
            'artist_id': artist_id,
            'songs': songs,
            'total_songs': len(songs),
            'last_updated': time.strftime("%Y-%m-%d %H:%M:%S")
        }

        metadata_path = os.path.join(artist_path, 'metadata.json')
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self.log_message(f"保存歌曲列表失败: {str(e)}", error=True)
            return False

    # 新增：加载歌曲列表从metadata.json
    def load_artist_metadata(self, artist_path):
        """从metadata.json加载艺人的歌曲列表"""
        metadata_path = os.path.join(artist_path, 'metadata.json')
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                return metadata
            except Exception as e:
                self.log_message(f"加载歌曲列表失败: {str(e)}", error=True)
        return None

    def check_completed_artists(self):
        """检查输出目录中已完成的艺人"""
        save_path = self.save_directory.get()
        if not os.path.exists(save_path):
            return

        completed_count = 0
        for artist_data in self.artists_queue:
            artist_name = artist_data['name']
            artist_safe_name = re.sub(r'[<>:"/\\|?*]', '', artist_name)
            artist_safe_name = artist_safe_name.replace(' ', '_')
            artist_folder = os.path.join(save_path, f"{artist_safe_name}_所有歌曲")

            # 检查文件夹是否存在
            if os.path.exists(artist_folder):
                # 检查是否有metadata.json文件
                metadata = self.load_artist_metadata(artist_folder)

                if metadata and 'songs' in metadata:
                    # 从metadata.json获取总歌曲数
                    total_songs = metadata['total_songs']

                    # 统计文件夹中的歌词文件数量
                    lyrics_files = [f for f in os.listdir(artist_folder)
                                    if f.endswith('.txt') and f != 'metadata.json']
                    saved_songs = len(lyrics_files)

                    artist_data['status'] = '已完成'
                    artist_data['songs_found'] = total_songs  # 实际的歌曲总数
                    artist_data['songs_saved'] = saved_songs  # 实际保存的歌曲数
                    artist_data['songs_failed'] = total_songs - saved_songs
                    completed_count += 1

                    self.log_message(f"检测到艺人 '{artist_name}' 已完成 {saved_songs}/{total_songs} 首歌曲")
                else:
                    # 如果没有metadata.json，使用旧的方式
                    files = [f for f in os.listdir(artist_folder) if f.endswith('.txt')]
                    if files:
                        artist_data['status'] = '已完成'
                        try:
                            artist_data['songs_found'] = len(files)
                            artist_data['songs_saved'] = len(files)
                            artist_data['songs_failed'] = 0
                        except:
                            pass
                        completed_count += 1

        if completed_count > 0:
            self.update_queue_display()
            self.log_message(f"检测到 {completed_count} 个艺人已完成下载")

    def toggle_token_visibility(self):
        current_state = self.token_entry.cget('show')
        if current_state == '*':
            self.token_entry.config(show='')
        else:
            self.token_entry.config(show='*')

    def browse_directory(self):
        directory = filedialog.askdirectory(initialdir=self.save_directory.get())
        if directory:
            self.save_directory.set(directory)
            # 切换目录后重新检查已完成的艺人
            self.root.after(100, self.check_completed_artists)

    def batch_add_artists(self):
        """批量添加艺人，支持多行输入"""
        text = self.artist_text.get("1.0", tk.END).strip()
        if not text:
            return

        lines = [line.strip() for line in text.split('\n') if line.strip()]
        existing_names = {artist['name'].lower() for artist in self.artists_queue}

        added = 0
        skipped = 0

        for line in lines:
            if line and line.lower() not in existing_names:
                artist_data = {
                    'name': line,
                    'status': '等待中',
                    'songs_found': 0,
                    'songs_saved': 0,
                    'songs_failed': 0,
                    'start_time': None,
                    'end_time': None
                }
                self.artists_queue.append(artist_data)
                existing_names.add(line.lower())
                added += 1
            else:
                skipped += 1

        self.update_queue_display()

        if added > 0:
            self.log_message(f"批量添加完成: 添加了 {added} 个艺人，跳过了 {skipped} 个重复艺人")
            self.artist_text.delete("1.0", tk.END)

    def clear_text(self):
        """清空输入框"""
        self.artist_text.delete("1.0", tk.END)

    def select_all(self):
        """全选"""
        self.artist_tree.selection_set(self.artist_tree.get_children())

    def invert_selection(self):
        """反选"""
        all_items = set(self.artist_tree.get_children())
        selected_items = set(self.artist_tree.selection())
        new_selection = all_items - selected_items
        self.artist_tree.selection_set(new_selection)

    def remove_selected_artists(self):
        """删除选中的艺人"""
        selected_items = self.artist_tree.selection()
        if not selected_items:
            messagebox.showwarning("未选中", "请先选中要删除的艺人")
            return

        artist_names = []
        for item in selected_items:
            values = self.artist_tree.item(item, 'values')
            if values:
                artist_names.append(values[1])

        if not artist_names:
            return

        confirm_msg = f"确定要删除选中的 {len(artist_names)} 个艺人吗？\n\n"
        confirm_msg += "\n".join([f"• {name}" for name in artist_names[:10]])
        if len(artist_names) > 10:
            confirm_msg += f"\n• ... 等 {len(artist_names) - 10} 个艺人"

        if not messagebox.askyesno("确认删除", confirm_msg):
            return

        indices_to_remove = []
        for item in selected_items:
            values = self.artist_tree.item(item, 'values')
            if values:
                index = int(values[0]) - 1
                indices_to_remove.append(index)

        indices_to_remove.sort(reverse=True)

        removed_names = []
        for index in indices_to_remove:
            if 0 <= index < len(self.artists_queue):
                removed_names.append(self.artists_queue[index]['name'])
                self.artists_queue.pop(index)

        self.update_queue_display()

        if removed_names:
            self.log_message(f"已删除 {len(removed_names)} 个艺人")

    def move_up(self):
        """上移选中的艺人"""
        selected = self.artist_tree.selection()
        if not selected:
            return

        indices = []
        for item in selected:
            values = self.artist_tree.item(item, 'values')
            if values:
                index = int(values[0]) - 1
                indices.append(index)

        indices.sort()

        for index in indices:
            if index > 0 and index not in [i - 1 for i in indices]:
                self.artists_queue[index], self.artists_queue[index - 1] = \
                    self.artists_queue[index - 1], self.artists_queue[index]

        self.update_queue_display()

        new_indices = [i - 1 if i in indices and i > 0 else i for i in indices]
        children = self.artist_tree.get_children()
        new_selection = [children[i] for i in new_indices if 0 <= i < len(children)]
        if new_selection:
            self.artist_tree.selection_set(new_selection)

    def move_down(self):
        """下移选中的艺人"""
        selected = self.artist_tree.selection()
        if not selected:
            return

        indices = []
        for item in selected:
            values = self.artist_tree.item(item, 'values')
            if values:
                index = int(values[0]) - 1
                indices.append(index)

        indices.sort(reverse=True)

        for index in indices:
            if index < len(self.artists_queue) - 1 and index not in [i + 1 for i in indices]:
                self.artists_queue[index], self.artists_queue[index + 1] = \
                    self.artists_queue[index + 1], self.artists_queue[index]

        self.update_queue_display()

        new_indices = [i + 1 if i in indices and i < len(self.artists_queue) - 1 else i for i in indices]
        children = self.artist_tree.get_children()
        new_selection = [children[i] for i in new_indices if 0 <= i < len(children)]
        if new_selection:
            self.artist_tree.selection_set(new_selection)

    def clear_queue(self):
        """清空整个队列"""
        if not self.artists_queue:
            return

        if messagebox.askyesno("确认清空", "确定要清空整个队列吗？这将删除所有艺人！"):
            self.artists_queue.clear()
            self.update_queue_display()
            self.log_message("队列已清空")

    def show_context_menu(self, event):
        """显示右键菜单"""
        item = self.artist_tree.identify_row(event.y)
        if item:
            if item not in self.artist_tree.selection():
                self.artist_tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def edit_artist(self, event):
        """编辑艺人"""
        selected = self.artist_tree.selection()
        if not selected:
            messagebox.showwarning("未选中", "请先选中要编辑的艺人")
            return

        item = selected[0]
        values = self.artist_tree.item(item, 'values')
        if not values:
            return

        index = int(values[0]) - 1
        if 0 <= index < len(self.artists_queue):
            artist = self.artists_queue[index]

            dialog = tk.Toplevel(self.root)
            dialog.title("编辑艺人")
            dialog.geometry("400x200")
            dialog.transient(self.root)
            dialog.grab_set()

            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
            y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
            dialog.geometry(f"+{x}+{y}")

            content_frame = ttk.Frame(dialog, padding="20")
            content_frame.pack(fill=tk.BOTH, expand=True)

            ttk.Label(content_frame, text="艺人名称:", font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))

            name_var = tk.StringVar(value=artist['name'])
            entry = ttk.Entry(content_frame, textvariable=name_var, font=("Arial", 10))
            entry.pack(fill=tk.X, pady=(0, 20))
            entry.select_range(0, tk.END)
            entry.focus_set()

            def save_changes():
                new_name = name_var.get().strip()
                if not new_name:
                    messagebox.showwarning("名称无效", "艺人名称不能为空")
                    return

                for i, a in enumerate(self.artists_queue):
                    if i != index and a['name'].lower() == new_name.lower():
                        messagebox.showwarning("重复", f"艺人 '{new_name}' 已存在于队列中")
                        return

                old_name = artist['name']
                self.artists_queue[index]['name'] = new_name

                # 如果状态是已完成，可能需要更新文件夹名称
                if artist['status'] == '已完成':
                    # 这里可以添加重命名文件夹的逻辑
                    pass

                self.update_queue_display()
                self.log_message(f"已更新艺人名称: {old_name} → {new_name}")
                dialog.destroy()

            def on_enter(event):
                save_changes()

            entry.bind('<Return>', on_enter)

            button_frame = ttk.Frame(content_frame)
            button_frame.pack(fill=tk.X, pady=(10, 0))

            ttk.Button(button_frame, text="保存", command=save_changes, width=10).pack(side=tk.RIGHT, padx=5)
            ttk.Button(button_frame, text="取消", command=dialog.destroy, width=10).pack(side=tk.RIGHT)

    def update_queue_display(self):
        """更新队列显示"""
        for item in self.artist_tree.get_children():
            self.artist_tree.delete(item)

        for i, artist in enumerate(self.artists_queue, 1):
            # 修改：正确显示完成状态 (x/y)
            if artist['status'] == '已完成' and artist.get('songs_found', 0) > 0:
                status_display = f"已完成 ({artist.get('songs_saved', 0)}/{artist.get('songs_found', 0)})"
            elif '完成' in artist['status']:
                status_display = artist['status']
            else:
                status_display = artist['status']

            self.artist_tree.insert('', 'end', values=(
                i,
                artist['name'],
                status_display,
                artist.get('songs_found', 0),
                artist.get('songs_saved', 0),
                artist.get('songs_failed', 0)
            ))

        self.queue_count_label.config(text=f"队列中: {len(self.artists_queue)} 个艺人")

    def import_queue(self):
        """从文件导入艺人队列"""
        file_path = filedialog.askopenfilename(
            title="导入艺人队列",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]

                existing_names = {artist['name'].lower() for artist in self.artists_queue}
                added = 0

                for line in lines:
                    if line.lower() not in existing_names:
                        artist_data = {
                            'name': line,
                            'status': '等待中',
                            'songs_found': 0,
                            'songs_saved': 0,
                            'songs_failed': 0
                        }
                        self.artists_queue.append(artist_data)
                        existing_names.add(line.lower())
                        added += 1

                self.update_queue_display()
                self.log_message(f"从文件导入完成: 添加了 {added} 个艺人")

            except Exception as e:
                self.log_message(f"导入失败: {str(e)}", error=True)

    def export_queue(self):
        """导出艺人队列到文件"""
        if not self.artists_queue:
            messagebox.showwarning("导出", "队列为空，无需导出")
            return

        file_path = filedialog.asksaveasfilename(
            title="导出艺人队列",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for artist in self.artists_queue:
                        f.write(f"{artist['name']}\n")
                self.log_message(f"队列已导出到: {file_path}")
            except Exception as e:
                self.log_message(f"导出失败: {str(e)}", error=True)

    def show_statistics(self):
        """显示统计信息"""
        total_artists = len(self.artists_queue)
        completed = sum(1 for a in self.artists_queue if a['status'] in ['已完成', '完成', '部分完成'])
        failed = sum(1 for a in self.artists_queue if a['status'] == '失败')
        waiting = total_artists - completed - failed

        total_songs = sum(a.get('songs_found', 0) for a in self.artists_queue)
        saved_songs = sum(a.get('songs_saved', 0) for a in self.artists_queue)

        stats_text = f"""
统计信息:
艺人总数: {total_artists}
已完成: {completed}
等待中: {waiting}
失败: {failed}
歌曲总数: {total_songs}
保存歌曲: {saved_songs}
成功率: {(saved_songs / total_songs * 100 if total_songs > 0 else 0):.1f}%
"""
        messagebox.showinfo("统计信息", stats_text.strip())

    def check_api_connection(self):
        """检查API连接"""
        if not self.access_token.get():
            return False, "API密钥为空"

        try:
            response = requests.get(
                "https://api.genius.com/search",
                headers={"Authorization": f"Bearer {self.access_token.get()}"},
                params={"q": "test"},
                timeout=10
            )

            if response.status_code == 401:
                return False, "API密钥无效"
            elif response.status_code == 429:
                return False, "API调用次数超限"
            elif response.status_code != 200:
                return False, f"API错误: {response.status_code}"

            return True, "连接正常"

        except requests.exceptions.Timeout:
            return False, "连接超时"
        except requests.exceptions.ConnectionError:
            return False, "网络连接失败"
        except Exception as e:
            return False, f"连接错误: {str(e)}"

    # 在 handle_api_error 方法中修改错误处理逻辑
    def handle_api_error(self, error_type, error_message=""):
        """处理API错误"""
        self.consecutive_errors += 1

        # 检查是否为429错误
        if "429" in error_message:
            # 尝试从错误消息中提取等待时间
            import re
            wait_time_match = re.search(r"Retry-After': '(\d+)'", error_message)
            if wait_time_match:
                wait_time = int(wait_time_match.group(1))
            else:
                wait_time = 300  # 默认等待5分钟

            self.log_message(f"⚠️ API调用次数超限，需要等待 {wait_time} 秒 (约{wait_time // 60}分钟)...", warning=True)
            self.update_api_status(f"API限制，等待{wait_time}秒")

            # 记录到恢复点以便后续处理
            self.resume_points['api_wait_time'] = wait_time
            self.resume_points['api_wait_until'] = time.time() + wait_time

            # 暂停指定时间
            for i in range(wait_time, 0, -1):
                if self.stop_requested:
                    break
                minutes, seconds = divmod(i, 60)
                self.root.after(0, lambda m=minutes, s=seconds: self.update_status(f"API限制，等待{m:02d}:{s:02d}"))
                time.sleep(1)

            self.consecutive_errors = 0
            self.log_message("✅ API限制等待结束，恢复处理...")
            return  # 429错误特殊处理，不计数到连续错误

        # 其他错误处理逻辑
        if self.consecutive_errors >= self.max_consecutive_errors:
            wait_time = self.error_wait_time
            self.log_message(f"⚠️ 连续出现 {self.consecutive_errors} 次API错误，暂停 {wait_time} 秒...", warning=True)
            self.update_api_status(f"API错误，暂停{wait_time}秒")

            for i in range(wait_time, 0, -1):
                if self.stop_requested:
                    break
                minutes, seconds = divmod(i, 60)
                self.root.after(0, lambda m=minutes, s=seconds: self.update_status(f"等待中... {m:02d}:{s:02d}后恢复"))
                time.sleep(1)

            self.consecutive_errors = 0
            self.log_message("✅ 暂停结束，恢复处理...")

        self.log_message(f"API错误 ({error_type}): {error_message}", error=True)

    def safe_api_request(self, request_func, *args, **kwargs):
        """安全的API请求包装器"""
        if RATE_LIMITER_AVAILABLE:
            try:
                # 使用全局速率限制器
                return make_api_request(request_func, *args, **kwargs)
            except Exception as e:
                self.handle_api_error("全局请求失败", str(e))
                raise
        else:
            # 回退到原有的逻辑
            max_retries = 3
            base_wait_time = 5

            for attempt in range(max_retries):
                try:
                    result = request_func(*args, **kwargs)
                    self.consecutive_errors = 0
                    return result

                except requests.exceptions.ConnectionError as e:
                    wait_time = base_wait_time * (attempt + 1)
                    self.log_message(f"网络连接失败，{wait_time}秒后重试 ({attempt + 1}/{max_retries})...", warning=True)
                    time.sleep(wait_time)

                except requests.exceptions.Timeout as e:
                    wait_time = base_wait_time * (attempt + 1)
                    self.log_message(f"请求超时，{wait_time}秒后重试 ({attempt + 1}/{max_retries})...", warning=True)
                    time.sleep(wait_time)

                except Exception as e:
                    if "429" in str(e):
                        wait_time = 60
                        self.log_message(f"API调用次数超限，等待{wait_time}秒...", warning=True)
                        time.sleep(wait_time)
                    else:
                        raise e

            raise Exception(f"请求失败，已重试{max_retries}次")

    def start_download(self):
        """开始下载（从队列第一个开始）"""
        self._start_download_impl(start_from=0)

    def start_download_from_selected(self):
        """从选中的艺人开始下载"""
        selected_items = self.artist_tree.selection()
        if not selected_items:
            messagebox.showwarning("未选中", "请先选中一个艺人")
            return

        # 获取第一个选中的艺人的索引
        item = selected_items[0]
        values = self.artist_tree.item(item, 'values')
        if not values:
            return

        start_from = int(values[0]) - 1  # 序号是从1开始的

        confirm = messagebox.askyesno("确认",
                                      f"确定要从选中的艺人 '{values[1]}' 开始下载吗？\n\n将从第 {start_from + 1} 个艺人开始处理。")
        if not confirm:
            return

        self._start_download_impl(start_from=start_from)

    def _start_download_impl(self, start_from=0):
        """下载实现的通用方法"""
        if not self.access_token.get():
            messagebox.showwarning("配置错误", "请输入Genius API密钥")
            self.token_entry.focus_set()
            return

        if not self.artists_queue:
            messagebox.showwarning("队列为空", "请先添加艺人到队列")
            return

        save_path = self.save_directory.get()
        try:
            if not os.path.exists(save_path):
                os.makedirs(save_path)
        except Exception as e:
            messagebox.showerror("路径错误", f"无法创建保存路径: {str(e)}")
            return

        self.log_message("正在检查API连接...")
        success, message = self.check_api_connection()
        if not success:
            messagebox.showerror("API错误", message)
            return

        self.log_message("✅ API连接正常")

        try:
            self.genius = Genius(
                self.access_token.get(),
                remove_section_headers=False,
                skip_non_songs=True,
                timeout=30,
                retries=3,
                verbose=False
            )
        except Exception as e:
            messagebox.showerror("初始化错误", f"初始化Genius对象失败: {str(e)}")
            return

        self.currently_processing = True
        self.stop_requested = False
        self.consecutive_errors = 0

        self.start_btn.config(state=tk.DISABLED)
        self.start_selected_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL)
        self.resume_btn.config(state=tk.DISABLED)

        self.progress_var.set(0)
        self.progress_label.config(text="0%")
        self.status_label.config(text="开始下载...")
        self.update_api_status("连接正常")

        # 启动下载线程，传入起始索引
        download_thread = threading.Thread(target=self.process_download_queue, args=(start_from,), daemon=True)
        download_thread.start()

    def resume_download(self):
        """断点续传"""
        self._start_download_impl(start_from=self.resume_points.get('last_artist_index', 0))

    def pause_download(self):
        """暂停下载"""
        if self.currently_processing and not self.stop_requested:
            self.currently_processing = False
            self.pause_btn.config(text="▶ 继续")
            self.status_label.config(text="已暂停")
            self.log_message("⏸ 下载已暂停")
        else:
            self.currently_processing = True
            self.pause_btn.config(text="⏸ 暂停")
            self.status_label.config(text="恢复中...")
            self.log_message("▶ 下载恢复")

    def stop_download(self):
        """停止下载"""
        if self.currently_processing:
            if messagebox.askyesno("确认", "确定要停止下载吗？"):
                self.stop_requested = True
                self.currently_processing = False
                self.log_message("🛑 正在停止下载...", warning=True)

                # 启用断点续传按钮
                self.resume_btn.config(state=tk.NORMAL)

    def process_download_queue(self, start_index=0):
        """处理下载队列，支持从指定索引开始"""
        total_artists = len(self.artists_queue)
        processed_artists = start_index  # 已经处理过的艺人数量

        total_songs_found = 0
        total_songs_saved = 0
        total_songs_failed = 0

        # 更新进度条初始状态
        if start_index > 0:
            initial_progress = (start_index / total_artists) * 100
            self.update_progress(initial_progress)

        self.log_message(f"🎬 开始处理 {total_artists} 个艺人，从第 {start_index + 1} 个开始")

        for i in range(start_index, total_artists):
            if self.stop_requested:
                # 记录断点
                self.resume_points['last_artist_index'] = i
                self.log_message(f"🛑 下载停止，记录断点: 艺人 {i + 1} ({self.artists_queue[i]['name']})")
                break

            # 跳过已完成的艺人
            if self.artists_queue[i].get('status') == '已完成':
                self.log_message(f"⏭️ 跳过已完成的艺人: {self.artists_queue[i]['name']}")
                processed_artists += 1
                total_songs_found += self.artists_queue[i].get('songs_found', 0)
                total_songs_saved += self.artists_queue[i].get('songs_saved', 0)
                total_songs_failed += self.artists_queue[i].get('songs_failed', 0)
                continue

            while not self.currently_processing and not self.stop_requested:
                time.sleep(0.5)

            if self.stop_requested:
                self.resume_points['last_artist_index'] = i
                break

            artist_data = self.artists_queue[i]
            artist_name = artist_data['name']
            artist_data['start_time'] = time.time()

            self.update_artist_status(i, '处理中')
            self.log_message(f"\n{'=' * 70}")
            self.log_message(f"🎤 处理艺人 {i + 1}/{total_artists}: {artist_name}")
            self.log_message(f"{'=' * 70}")

            success, songs_found, songs_saved, songs_failed = self.process_artist(artist_name, i)

            artist_data['end_time'] = time.time()
            processing_time = artist_data['end_time'] - artist_data['start_time']

            if success:
                if songs_saved > 0:
                    status = f"完成 ({songs_saved}/{songs_found})"
                else:
                    status = "无歌曲"
                processed_artists += 1
                total_songs_found += songs_found
                total_songs_saved += songs_saved
                total_songs_failed += songs_failed

                artist_data.update({
                    'status': status,
                    'songs_found': songs_found,
                    'songs_saved': songs_saved,
                    'songs_failed': songs_failed
                })

                self.log_message(f"✅ 艺人 '{artist_name}' 处理完成")
                self.log_message(f"   找到歌曲: {songs_found} | 保存成功: {songs_saved} | 失败: {songs_failed}")
                self.log_message(f"   处理时间: {processing_time:.1f}秒")
            else:
                status = "失败"
                artist_data['status'] = status
                self.log_message(f"❌ 艺人 '{artist_name}' 处理失败", error=True)

            self.update_artist_status(i, status)

            progress = ((i + 1) / total_artists) * 100
            self.update_progress(progress)

            self.update_stats(processed_artists, total_songs_found, total_songs_saved, total_songs_failed)

            if i < total_artists - 1 and not self.stop_requested:
                delay = 10
                self.log_message(f"\n⏱ 等待{delay}秒后处理下一个艺人...")
                for j in range(delay, 0, -1):
                    if self.stop_requested:
                        break
                    time.sleep(1)

        self.currently_processing = False

        if self.stop_requested:
            # 保存断点信息
            self.save_resume_points()
            self.resume_btn.config(state=tk.NORMAL)
            self.root.after(0, lambda: self.on_download_stopped(processed_artists, total_artists,
                                                                total_songs_saved, total_songs_found,
                                                                total_songs_failed))
        else:
            self.stop_requested = False
            self.resume_points.clear()  # 清除断点信息
            self.resume_btn.config(state=tk.DISABLED)
            self.root.after(0, self.on_download_complete,
                            processed_artists, total_artists,
                            total_songs_saved, total_songs_found, total_songs_failed)

    # 修改 process_artist 方法中的保存逻辑
    def process_artist(self, artist_name, artist_index):
        """处理单个艺人（支持断点续传和保存歌曲列表）"""
        try:
            artist_safe_name = re.sub(r'[<>:"/\\|?*]', '', artist_name)
            artist_safe_name = artist_safe_name.replace(' ', '_')

            # 修复路径创建问题：确保保存目录存在
            save_base_path = self.save_directory.get()
            if not os.path.exists(save_base_path):
                os.makedirs(save_base_path, exist_ok=True)

            artist_path = os.path.join(save_base_path, f"{artist_safe_name}_所有歌曲")

            # 检查是否已有metadata.json
            metadata = self.load_artist_metadata(artist_path)
            songs = []
            artist_id = None

            if metadata and 'songs' in metadata:
                # 从metadata.json加载歌曲列表
                songs = metadata['songs']
                artist_id = metadata.get('artist_id')
                self.log_message(f"✅ 从缓存加载歌曲列表，共 {len(songs)} 首歌曲")
            else:
                # 需要从API获取
                self.log_message(f"🔍 正在搜索艺术家: {artist_name}")
                artist_id = self.get_artist_id(artist_name)
                if not artist_id:
                    self.log_message(f"❌ 未找到艺术家: {artist_name}", error=True)
                    return False, 0, 0, 0

                self.log_message(f"✅ 找到艺术家ID: {artist_id}")

                self.log_message("📋 正在获取歌曲列表...")
                songs = self.get_all_artist_songs(artist_id, artist_name)
                if not songs:
                    self.log_message(f"⚠️ 未找到歌曲: {artist_name}", warning=True)
                    return True, 0, 0, 0

                self.log_message(f"✅ 找到 {len(songs)} 首歌曲")

                # 确保文件夹存在再保存metadata
                if not os.path.exists(artist_path):
                    os.makedirs(artist_path, exist_ok=True)

                # 保存歌曲列表到metadata.json
                self.save_artist_metadata(artist_name, artist_id, songs, artist_path)
                self.log_message(f"📄 歌曲列表已保存到 metadata.json")

            # 检查是否已存在文件夹
            existing_files = []
            if os.path.exists(artist_path):
                existing_files = [f for f in os.listdir(artist_path) if f.endswith('.txt')]
                if existing_files:
                    self.log_message(f"📁 发现已有文件夹，包含 {len(existing_files)} 个歌词文件")

            if not os.path.exists(artist_path):
                os.makedirs(artist_path, exist_ok=True)
                self.log_message(f"📁 创建文件夹: {artist_path}")

            saved_count = 0
            failed_count = 0
            total_songs = len(songs)

            for i, song_info in enumerate(songs, 1):
                if self.stop_requested:
                    # 记录断点
                    self.resume_points[artist_name] = {
                        'artist_index': artist_index,
                        'song_index': i - 1,  # 当前歌曲的索引
                        'saved_count': saved_count,
                        'failed_count': failed_count
                    }
                    self.log_message(f"🛑 下载停止，记录断点: 艺人 {artist_name}，歌曲 {i}/{total_songs}")
                    break

                # 断点续传：检查是否已下载过此歌曲
                song_safe_filename = re.sub(r'[<>:"/\\|?*]', '', song_info['title'])
                song_safe_filename = song_safe_filename.replace(' ', '_')
                if len(song_safe_filename) > 100:
                    song_safe_filename = song_safe_filename[:100]

                expected_filename = f"{i:04d}_{song_safe_filename}.txt"
                if expected_filename in existing_files:
                    self.log_message(f"[{i:04d}/{total_songs:04d}] ⏭️ {song_info['title']} (已存在，跳过)")
                    saved_count += 1
                    continue

                song_progress = (i / total_songs) * 100
                artist_progress = (artist_index + (i / total_songs)) / len(self.artists_queue) * 100
                self.update_progress(artist_progress)
                self.update_status(f"处理歌曲: {song_info['title']} ({i}/{total_songs})")

                self.log_message(f"[{i:04d}/{total_songs:04d}] 🎵 {song_info['title']}")

                song = self.get_song_lyrics(song_info['id'], song_info['title'], song_info['artist'])

                if song and song.lyrics:
                    if self.save_song_lyrics(song, artist_path, i, total_songs):
                        saved_count += 1
                        self.log_message(f"    ✅ 保存成功")
                    else:
                        failed_count += 1
                        self.log_message(f"    ❌ 保存失败")
                else:
                    failed_count += 1
                    self.log_message(f"    ⚠️ 无法获取歌词")

                # 添加智能延迟，避免API限制
                if i < total_songs and not self.stop_requested:
                    # 每处理5首歌曲增加一点延迟
                    delay = 2 if i % 5 != 0 else 5
                    time.sleep(delay)

            self.log_message(f"\n📊 统计: {saved_count}/{total_songs} 首歌曲保存成功")
            return True, total_songs, saved_count, failed_count

        except Exception as e:
            self.handle_api_error("处理艺人失败", str(e))
            self.log_message(f"❌ 处理艺人 '{artist_name}' 时出错: {str(e)}", error=True)
            return False, 0, 0, 0

    def get_artist_id(self, artist_name_or_id):
        """获取艺术家ID - 优化逻辑：先获取ID，再用ID查询"""
        try:
            # 1️⃣ 如果直接给了ID
            if str(artist_name_or_id).startswith("id="):
                artist_id = int(artist_name_or_id.split("=")[1])
                self.log_message(f"  直接使用提供的艺人ID: {artist_id}")
                return artist_id

            # 2️⃣ 否则搜索艺人名，找到ID
            search_url = "https://api.genius.com/search"
            headers = {"Authorization": f"Bearer {self.access_token.get()}"}
            params = {"q": artist_name_or_id}

            response = self.safe_api_request(
                requests.get, search_url, headers=headers, params=params, timeout=15
            )

            data = response.json()
            hits = data['response']['hits']
            self.log_message(f"  搜索 '{artist_name_or_id}' 获得 {len(hits)} 个结果")

            # 遍历搜索结果，优先获取最准确的ID
            for hit in hits:
                result_type = hit.get('type', '')
                result = hit.get('result', {})

                # 直接艺人匹配
                if result_type == 'artist':
                    found_name = result.get('name', '')
                    found_id = result.get('id')
                    if found_name.lower() == artist_name_or_id.lower():
                        self.log_message(f"  找到精确匹配艺人: {found_name} (ID: {found_id})")
                        return found_id

                # 通过歌曲匹配艺人
                elif result_type == 'song':
                    primary_artist = result.get('primary_artist', {})
                    if primary_artist:
                        found_name = primary_artist.get('name', '')
                        found_id = primary_artist.get('id')
                        if found_name.lower() == artist_name_or_id.lower():
                            self.log_message(
                                f"  通过歌曲 '{result.get('title', '')}' 找到艺人: {found_name} (ID: {found_id})")
                            return found_id

            # 如果没有完全匹配，则使用第一条搜索结果的艺人ID（近似匹配）
            if hits:
                first_hit = hits[0].get('result', {})
                if 'primary_artist' in first_hit:
                    artist_id = first_hit['primary_artist']['id']
                    self.log_message(f"  使用第一条搜索结果的艺人ID: {artist_id}")
                    return artist_id
                elif first_hit.get('type') == 'artist':
                    artist_id = first_hit.get('id')
                    self.log_message(f"  使用第一条搜索结果的艺人ID: {artist_id}")
                    return artist_id

            self.log_message(f"  未找到艺人 '{artist_name_or_id}'")
            return None

        except Exception as e:
            self.handle_api_error("获取艺术家ID", str(e))
            return None

    def get_all_artist_songs(self, artist_id, artist_name):
        """获取艺术家的所有歌曲"""
        try:
            all_songs = []
            page = 1
            per_page = 50
            duplicates = set()
            max_pages = 50

            while page <= max_pages:
                songs_url = f"https://api.genius.com/artists/{artist_id}/songs"
                headers = {"Authorization": f"Bearer {self.access_token.get()}"}
                params = {
                    "per_page": per_page,
                    "page": page,
                    "sort": "title"
                }

                try:
                    response = self.safe_api_request(
                        requests.get, songs_url, headers=headers, params=params, timeout=15
                    )
                except Exception as e:
                    if page > 1:
                        self.log_message(f"⚠️ 获取第{page}页失败，返回已获取的{len(all_songs)}首歌曲", warning=True)
                        return all_songs
                    else:
                        raise e

                remaining = int(response.headers.get('X-RateLimit-Remaining', 999))
                limit = int(response.headers.get('X-RateLimit-Limit', 1000))

                # 更保守的API限制处理
                if remaining < 100:
                    extra_wait = 10  # 增加到10秒
                    self.log_message(f"⚠️ API限制警告: {remaining}/{limit}，添加{extra_wait}秒额外延迟", warning=True)
                    time.sleep(extra_wait)

                data = response.json()
                page_songs = data['response']['songs']

                if not page_songs:
                    break

                new_songs = 0
                for song in page_songs:
                    song_title = song['title']
                    if song_title in duplicates:
                        continue

                    song_info = {
                        'id': song['id'],
                        'title': song_title,
                        'url': song['url'],
                        'artist': song['primary_artist']['name'],
                        'album': song.get('album', {}).get('name', '单曲') if song.get('album') else '单曲'
                    }
                    all_songs.append(song_info)
                    duplicates.add(song_title)
                    new_songs += 1

                self.log_message(f"   第{page}页: 获取了 {new_songs} 首歌曲，总计 {len(all_songs)} 首")

                next_page = data['response'].get('next_page')
                if not next_page:
                    break

                page += 1

                # 每页之间的延迟增加到3秒
                time.sleep(3)

            return all_songs

        except Exception as e:
            self.handle_api_error("获取歌曲列表", str(e))
            return []

    def get_song_lyrics(self, song_id, song_title, artist_name):
        """获取单首歌曲的歌词"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # 检查是否有API等待时间
                if hasattr(self, 'resume_points') and 'api_wait_until' in self.resume_points:
                    wait_until = self.resume_points['api_wait_until']
                    current_time = time.time()
                    if current_time < wait_until:
                        wait_time = wait_until - current_time
                        minutes, seconds = divmod(int(wait_time), 60)
                        self.log_message(f"⏱️ 等待API限制结束: {minutes:02d}:{seconds:02d}", warning=True)
                        time.sleep(wait_time)
                        del self.resume_points['api_wait_until']
                        del self.resume_points['api_wait_time']

                song = self.genius.search_song(song_title, artist_name)

                if song and song.lyrics:
                    return song
                elif song and not song.lyrics:
                    pass

                song_url = f"https://api.genius.com/songs/{song_id}"
                headers = {"Authorization": f"Bearer {self.access_token.get()}"}

                response = self.safe_api_request(
                    requests.get, song_url, headers=headers, timeout=15
                )

                data = response.json()
                song_data = data['response']['song']
                full_title = song_data.get('full_title', '')

                if full_title and full_title != song_title:
                    song = self.genius.search_song(full_title)
                    if song:
                        return song

                return None

            except Exception as e:
                error_str = str(e)
                # 检查是否为429错误
                if "429" in error_str:
                    self.handle_api_error("获取歌曲歌词", error_str)
                    return None  # 429错误不重试

                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # 增加到5秒
                    self.log_message(f"   第{attempt + 1}次获取失败，{wait_time}秒后重试...", warning=True)
                    time.sleep(wait_time)
                else:
                    raise e

        return None

    def clean_lyrics(self, lyrics):
        """清理歌词"""
        if not lyrics:
            return ""

        read_more_pattern = re.compile(r'read more', re.IGNORECASE)
        match = read_more_pattern.search(lyrics)

        if match:
            return lyrics[match.end():].strip()
        else:
            return lyrics

    def save_song_lyrics(self, song, save_path, index, total):
        """保存歌词到文件"""
        try:
            safe_filename = re.sub(r'[<>:"/\\|?*]', '', song.title)
            safe_filename = safe_filename.replace(' ', '_')

            if len(safe_filename) > 100:
                safe_filename = safe_filename[:100]

            file_path = os.path.join(save_path, f"{index:04d}_{safe_filename}.txt")

            clean_text = self.clean_lyrics(song.lyrics)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(clean_text)

            return True

        except Exception as e:
            self.log_message(f"保存文件时出错: {str(e)}", error=True)
            return False

    def save_resume_points(self):
        """保存断点信息"""
        try:
            resume_path = os.path.join(os.getcwd(), "lyrics_downloader_resume.json")
            with open(resume_path, 'w', encoding='utf-8') as f:
                json.dump(self.resume_points, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log_message(f"保存断点信息失败: {str(e)}", error=True)

    def load_resume_points(self):
        """加载断点信息"""
        try:
            resume_path = os.path.join(os.getcwd(), "lyrics_downloader_resume.json")
            if os.path.exists(resume_path):
                with open(resume_path, 'r', encoding='utf-8') as f:
                    self.resume_points = json.load(f)
                return True
        except Exception as e:
            self.log_message(f"加载断点信息失败: {str(e)}", error=True)
        return False

    def log_message(self, message, error=False, warning=False):
        """在日志区域显示消息"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())

        if error:
            prefix = "❌ "
            color = "red"
        elif warning:
            prefix = "⚠️ "
            color = "orange"
        else:
            prefix = ""
            color = "black"

        log_entry = f"[{timestamp}] {prefix}{message}\n"

        self.root.after(0, self._update_log, log_entry, color)

    def update_progress(self, value):
        """更新进度条"""
        self.root.after(0, lambda: self.progress_var.set(value))
        self.root.after(0, lambda: self.progress_label.config(text=f"{value:.1f}%"))

    def update_status(self, message):
        """更新状态标签"""
        self.root.after(0, lambda: self.status_label.config(text=message))

    def update_api_status(self, message):
        """更新API状态"""
        self.root.after(0, lambda: self.api_status_label.config(text=f"API状态: {message}"))

    def update_artist_status(self, index, status):
        """更新艺人状态"""
        self.root.after(0, self._update_artist_status_ui, index, status)

    def _update_artist_status_ui(self, index, status):
        """在UI线程中更新艺人状态"""
        if 0 <= index < len(self.artists_queue):
            self.artists_queue[index]['status'] = status
            children = self.artist_tree.get_children()
            if 0 <= index < len(children):
                values = list(self.artist_tree.item(children[index], 'values'))
                values[2] = status
                self.artist_tree.item(children[index], values=values)

    def update_stats(self, artists_done, songs_found, songs_saved, songs_failed):
        """更新统计信息"""
        self.root.after(0, lambda: self._update_stats_ui(artists_done, songs_found, songs_saved, songs_failed))

    def _update_stats_ui(self, artists_done, songs_found, songs_saved, songs_failed):
        """在UI线程中更新统计"""
        success_rate = (songs_saved / songs_found * 100) if songs_found > 0 else 0

        stats_text = f"艺人: {artists_done}/{len(self.artists_queue)} | "
        stats_text += f"歌曲总数: {songs_found} | "
        stats_text += f"成功: {songs_saved} | 失败: {songs_failed} | "
        stats_text += f"成功率: {success_rate:.1f}%"
        self.stats_label.config(text=stats_text)

        error_text = f"API错误: {self.consecutive_errors}/{self.max_consecutive_errors} | "
        error_text += f"等待时间: {self.consecutive_errors * self.error_wait_time}秒"
        self.error_label.config(text=error_text)

    def on_download_complete(self, processed_artists, total_artists, songs_saved, songs_found, songs_failed):
        """下载完成后的处理"""
        self.start_btn.config(state=tk.NORMAL)
        self.start_selected_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.DISABLED)
        self.resume_btn.config(state=tk.DISABLED)

        self.progress_var.set(100)
        self.progress_label.config(text="100%")
        self.status_label.config(text="下载完成")

        success_rate = (songs_saved / songs_found * 100) if songs_found > 0 else 0

        self.log_message("\n" + "=" * 70)
        self.log_message("🎉 下载完成!")
        self.log_message("=" * 70)
        self.log_message(f"总艺人: {processed_artists}/{total_artists}")
        self.log_message(f"总歌曲: {songs_saved}/{songs_found}")
        self.log_message(f"成功率: {success_rate:.1f}%")
        self.log_message(f"失败歌曲: {songs_failed}")

        if not self.embedded_mode:
            self.root.after(0, lambda: messagebox.showinfo(
                "下载完成",
                f"下载完成!\n\n"
                f"艺人: {processed_artists}/{total_artists}\n"
                f"歌曲: {songs_saved}/{songs_found}\n"
                f"成功率: {success_rate:.1f}%\n\n"
                f"保存路径: {self.save_directory.get()}"
            ))

    def on_download_stopped(self, processed_artists, total_artists, songs_saved, songs_found, songs_failed):
        """下载停止后的处理"""
        self.start_btn.config(state=tk.NORMAL)
        self.start_selected_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.DISABLED)
        self.resume_btn.config(state=tk.NORMAL)

        self.status_label.config(text="下载已停止")

        success_rate = (songs_saved / songs_found * 100) if songs_found > 0 else 0

        self.log_message("\n" + "=" * 70)
        self.log_message("🛑 下载已停止!")
        self.log_message("=" * 70)
        self.log_message(f"已处理艺人: {processed_artists}/{total_artists}")
        self.log_message(f"已下载歌曲: {songs_saved}/{songs_found}")
        self.log_message(f"成功率: {success_rate:.1f}%")
        self.log_message(f"点击'断点续传'按钮可以继续下载")

        if not self.embedded_mode:
            self.root.after(0, lambda: messagebox.showinfo(
                "下载已停止",
                f"下载已停止!\n\n"
                f"已处理艺人: {processed_artists}/{total_artists}\n"
                f"已下载歌曲: {songs_saved}/{songs_found}\n"
                f"成功率: {success_rate:.1f}%\n\n"
                f"点击'断点续传'按钮可以继续下载"
            ))

    def save_settings(self):
        """保存设置到当前目录"""
        settings = {
            'access_token': self.access_token.get(),
            'save_directory': self.save_directory.get(),
            'artists_queue': self.artists_queue
        }

        try:
            # 修改为当前目录
            settings_path = os.path.join(os.getcwd(), "lyrics_downloader_settings.json")
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)

            self.log_message("✅ 设置已保存到当前目录")
        except Exception as e:
            self.log_message(f"❌ 保存设置失败: {str(e)}", error=True)

    def load_settings(self):
        """从当前目录加载设置"""
        try:
            # 修改为当前目录
            settings_path = os.path.join(os.getcwd(), "lyrics_downloader_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                self.access_token.set(settings.get('access_token', ''))
                self.save_directory.set(settings.get('save_directory', os.path.expanduser("~/Desktop/Genius歌词")))

                # 加载完整的艺人队列数据
                queue_data = settings.get('artists_queue', [])
                if queue_data and isinstance(queue_data, list):
                    self.artists_queue = queue_data
                else:
                    # 向后兼容：旧版本只保存名称列表
                    artists = settings.get('artists_queue', [])
                    if isinstance(artists, list):
                        self.artists_queue = []
                        for artist_name in artists:
                            if isinstance(artist_name, str):
                                artist_data = {
                                    'name': artist_name,
                                    'status': '等待中',
                                    'songs_found': 0,
                                    'songs_saved': 0,
                                    'songs_failed': 0
                                }
                                self.artists_queue.append(artist_data)

                self.update_queue_display()
                self.log_message("✅ 设置已从当前目录加载")

                # 加载断点信息
                if self.load_resume_points():
                    self.log_message("✅ 断点信息已加载")
                    self.resume_btn.config(state=tk.NORMAL)

        except Exception as e:
            self.log_message(f"加载设置失败: {str(e)}", error=True)


def main():
    root = tk.Tk()
    app = LyricsDownloaderGUI(root)

    root.minsize(1200, 800)

    def on_closing():
        if app.currently_processing and not app.stop_requested:
            if messagebox.askyesno("确认", "下载正在进行中，确定要退出吗？"):
                app.stop_requested = True
                app.currently_processing = False
                time.sleep(1)
                app.save_settings()
                root.destroy()
        else:
            app.save_settings()
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()