"""
Genius歌词下载器 - 多任务专业版
这个版本支持多个标签页，每个标签页可以独立运行不同的下载任务
"""

import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import Genius_Lyrics_Crawl  # 导入现有的单任务版本

# 导入速率限制器
try:
    from rate_limiter import get_rate_limiter

    RATE_LIMITER_AVAILABLE = True
except ImportError:
    RATE_LIMITER_AVAILABLE = False
    
class MultiTaskManager:



    def __init__(self, root):
        self.root = root
        self.root.title("Genius歌词下载器 - 多任务专业版")
        self.root.geometry("1600x1000")

        # 任务管理相关
        self.tasks = {}  # 存储所有任务 {task_id: task_data}
        self.current_task_id = None
        self.task_counters = {}

        self.setup_ui()
        self.load_tasks()

        # 如果没有任何任务，创建一个默认任务
        if not self.tasks:
            self.create_new_task("默认任务")

    def setup_ui(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # 标题栏
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(title_frame, text="🎵 Genius歌词下载器 - 多任务管理",
                  font=("Arial", 20, "bold")).pack(side=tk.LEFT)

        # 任务管理按钮
        task_manage_frame = ttk.Frame(title_frame)
        task_manage_frame.pack(side=tk.RIGHT)

        ttk.Button(task_manage_frame, text="➕ 新建任务",
                   command=self.create_new_task_dialog, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(task_manage_frame, text="✏️ 重命名",
                   command=self.rename_current_task, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(task_manage_frame, text="🗑删除任务",
                   command=self.delete_current_task, width=10).pack(side=tk.LEFT, padx=2)

        # 左侧：任务列表
        left_frame = ttk.Frame(main_frame, width=200)
        left_frame.grid(row=1, column=0, sticky=(tk.W, tk.N, tk.S), padx=(0, 5))
        left_frame.grid_propagate(False)

        # 任务列表标题
        task_list_title = ttk.Label(left_frame, text="📋 任务列表",
                                    font=("Arial", 12, "bold"))
        task_list_title.pack(fill=tk.X, pady=(0, 10))

        # 任务列表框架
        task_list_frame = ttk.Frame(left_frame)
        task_list_frame.pack(fill=tk.BOTH, expand=True)

        # 任务列表滚动条
        task_list_scrollbar = ttk.Scrollbar(task_list_frame)
        task_list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 任务列表框
        self.task_listbox = tk.Listbox(task_list_frame,
                                       font=("Arial", 10),
                                       selectmode=tk.SINGLE,
                                       yscrollcommand=task_list_scrollbar.set)
        self.task_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        task_list_scrollbar.config(command=self.task_listbox.yview)

        # 绑定任务选择事件
        self.task_listbox.bind('<<ListboxSelect>>', self.on_task_selected)

        # 任务状态显示
        self.task_status_frame = ttk.LabelFrame(left_frame, text="任务状态", padding="5")
        self.task_status_frame.pack(fill=tk.X, pady=(10, 0))

        self.task_status_label = ttk.Label(self.task_status_frame,
                                           text="选择任务查看状态",
                                           font=("Arial", 9))
        self.task_status_label.pack(fill=tk.X, pady=5)

        # 右侧：任务内容区域
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)

        # 创建Notebook（多标签页容器）
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 绑定标签页切换事件
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # 底部状态栏
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

        self.global_status_label = ttk.Label(bottom_frame,
                                             text="就绪 - 共 0 个任务",
                                             font=("Arial", 9))
        self.global_status_label.pack(side=tk.LEFT)

        version_label = ttk.Label(bottom_frame,
                                  text="多任务版 v2.0.0",
                                  font=("Arial", 9),
                                  foreground="gray")
        version_label.pack(side=tk.RIGHT)

    def create_new_task_dialog(self):
        """创建新任务的对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("创建新任务")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()

        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        # 内容框架
        content_frame = ttk.Frame(dialog, padding="20")
        content_frame.pack(fill=tk.BOTH, expand=True)

        # 任务名称
        ttk.Label(content_frame, text="任务名称:",
                  font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))

        task_name_var = tk.StringVar(value=f"任务_{len(self.tasks) + 1}")
        task_name_entry = ttk.Entry(content_frame, textvariable=task_name_var,
                                    font=("Arial", 10))
        task_name_entry.pack(fill=tk.X, pady=(0, 15))
        task_name_entry.select_range(0, tk.END)
        task_name_entry.focus_set()

        # API密钥（可选）
        ttk.Label(content_frame, text="API密钥 (可选，可在任务中设置):",
                  font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))

        api_token_var = tk.StringVar()
        api_token_entry = ttk.Entry(content_frame, textvariable=api_token_var,
                                    show="*", font=("Arial", 10))
        api_token_entry.pack(fill=tk.X, pady=(0, 15))

        # 保存路径（可选）
        ttk.Label(content_frame, text="保存路径 (可选，可在任务中设置):",
                  font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))

        save_path_var = tk.StringVar(value=os.path.expanduser("~/Desktop/Genius歌词"))
        save_path_frame = ttk.Frame(content_frame)
        save_path_frame.pack(fill=tk.X, pady=(0, 20))

        save_path_entry = ttk.Entry(save_path_frame, textvariable=save_path_var)
        save_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(save_path_frame, text="浏览",
                   command=lambda: self.browse_path(save_path_var),
                   width=8).pack(side=tk.RIGHT, padx=(5, 0))

        def save_task():
            task_name = task_name_var.get().strip()
            if not task_name:
                messagebox.showwarning("输入错误", "任务名称不能为空")
                return

            # 检查名称是否重复
            for task_id, task_data in self.tasks.items():
                if task_data['name'] == task_name:
                    messagebox.showwarning("名称重复", f"任务名称 '{task_name}' 已存在")
                    return

            # 创建任务
            self.create_new_task(task_name, api_token_var.get(), save_path_var.get())
            dialog.destroy()

        def on_enter(event):
            save_task()

        task_name_entry.bind('<Return>', on_enter)

        # 按钮框架
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill=tk.X)

        ttk.Button(button_frame, text="创建",
                   command=save_task, width=10).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="取消",
                   command=dialog.destroy, width=10).pack(side=tk.RIGHT)

    def browse_path(self, path_var):
        """浏览选择路径"""
        directory = filedialog.askdirectory(initialdir=path_var.get())
        if directory:
            path_var.set(directory)

    def create_new_task(self, task_name, api_token="", save_path=""):
        """创建新任务"""
        # 生成任务ID
        if task_name not in self.task_counters:
            self.task_counters[task_name] = 1
        task_id = f"{task_name}_{self.task_counters[task_name]}"
        self.task_counters[task_name] += 1

        # 创建任务框架
        task_frame = ttk.Frame(self.notebook)

        # 创建容器框架用于放置任务实例
        container_frame = ttk.Frame(task_frame)
        container_frame.pack(fill=tk.BOTH, expand=True)

        # 初始化任务数据
        task_data = {
            'id': task_id,
            'name': task_name,
            'frame': task_frame,
            'container': container_frame,
            'instance': None,  # 稍后初始化
            'api_token': api_token,
            'save_path': save_path,
            'status': '等待中',
            'artists_count': 0,
            'songs_saved': 0,
            'songs_total': 0
        }

        # 添加到任务列表
        self.tasks[task_id] = task_data

        # 添加到Notebook
        self.notebook.add(task_frame, text=task_name)

        # 更新任务列表显示
        self.update_task_list()

        # 切换到新任务
        self.notebook.select(len(self.notebook.tabs()) - 1)

        # 初始化任务实例
        self.initialize_task_instance(task_id)

        # 更新状态
        self.update_global_status()

        return task_id

    def initialize_task_instance(self, task_id):
        """初始化任务实例"""
        task_data = self.tasks[task_id]

        try:
            # 创建单任务实例 - 使用嵌入式模式
            task_instance = Genius_Lyrics_Crawl.LyricsDownloaderGUI(
                task_data['container'],
                embedded_mode=True
            )

            # 设置任务特定配置
            if task_data['api_token']:
                task_instance.access_token.set(task_data['api_token'])

                # 将API密钥添加到全局池
                if RATE_LIMITER_AVAILABLE:
                    try:
                        limiter = get_rate_limiter()
                        limiter.add_api_key(task_data['api_token'])
                    except:
                        pass

            if task_data['save_path']:
                task_instance.save_directory.set(task_data['save_path'])

            # 保存实例引用
            task_data['instance'] = task_instance

            # 重写保存和加载设置方法，使用任务特定文件
            self.override_task_methods(task_id)

            # 加载任务特定设置
            self.load_task_settings(task_id)

        except Exception as e:
            messagebox.showerror("错误", f"初始化任务失败: {str(e)}")

    def override_task_methods(self, task_id):
        """重写任务实例的方法以支持多任务"""
        task_data = self.tasks[task_id]
        instance = task_data['instance']

        # 保存原始方法
        original_save_settings = instance.save_settings
        original_load_settings = instance.load_settings

        def task_specific_save_settings():
            """任务特定的保存设置"""
            settings = {
                'access_token': instance.access_token.get(),
                'save_directory': instance.save_directory.get(),
                'artists_queue': instance.artists_queue
            }

            try:
                settings_path = os.path.join(os.getcwd(),
                                             f"lyrics_downloader_task_{task_data['name']}.json")
                with open(settings_path, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, ensure_ascii=False, indent=2)

                instance.log_message(f"✅ 任务设置已保存: {task_data['name']}")
            except Exception as e:
                instance.log_message(f"❌ 保存任务设置失败: {str(e)}", error=True)

        def task_specific_load_settings():
            """任务特定的加载设置"""
            try:
                settings_path = os.path.join(os.getcwd(),
                                             f"lyrics_downloader_task_{task_data['name']}.json")
                if os.path.exists(settings_path):
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        settings = json.load(f)

                    instance.access_token.set(settings.get('access_token', ''))
                    instance.save_directory.set(settings.get('save_directory',
                                                             os.path.expanduser("~/Desktop/Genius歌词")))

                    queue_data = settings.get('artists_queue', [])
                    if queue_data and isinstance(queue_data, list):
                        instance.artists_queue = queue_data
                        instance.update_queue_display()
                        instance.log_message(f"✅ 任务设置已加载: {task_data['name']}")

                    # 加载断点信息
                    resume_path = os.path.join(os.getcwd(),
                                               f"lyrics_downloader_resume_{task_data['name']}.json")
                    if os.path.exists(resume_path):
                        with open(resume_path, 'r', encoding='utf-8') as f:
                            instance.resume_points = json.load(f)
                        instance.log_message("✅ 任务断点信息已加载")

                        if instance.resume_points:
                            instance.resume_btn.config(state=tk.NORMAL)

            except Exception as e:
                pass  # 静默失败，使用默认设置

        # 重写方法
        instance.save_settings = task_specific_save_settings
        instance.load_settings = task_specific_load_settings

        # 重写断点保存方法
        original_save_resume_points = instance.save_resume_points

        def task_specific_save_resume_points():
            """任务特定的保存断点"""
            try:
                resume_path = os.path.join(os.getcwd(),
                                           f"lyrics_downloader_resume_{task_data['name']}.json")
                with open(resume_path, 'w', encoding='utf-8') as f:
                    json.dump(instance.resume_points, f, ensure_ascii=False, indent=2)
            except Exception as e:
                instance.log_message(f"保存断点信息失败: {str(e)}", error=True)

        instance.save_resume_points = task_specific_save_resume_points

        # 重写加载断点方法
        original_load_resume_points = instance.load_resume_points

        def task_specific_load_resume_points():
            """任务特定的加载断点"""
            try:
                resume_path = os.path.join(os.getcwd(),
                                           f"lyrics_downloader_resume_{task_data['name']}.json")
                if os.path.exists(resume_path):
                    with open(resume_path, 'r', encoding='utf-8') as f:
                        instance.resume_points = json.load(f)
                    return True
            except Exception as e:
                pass
            return False

        instance.load_resume_points = task_specific_load_resume_points

    def load_task_settings(self, task_id):
        """加载任务特定设置"""
        task_data = self.tasks[task_id]
        if task_data['instance']:
            task_data['instance'].load_settings()

    def update_task_list(self):
        """更新任务列表显示"""
        self.task_listbox.delete(0, tk.END)

        for task_id, task_data in self.tasks.items():
            display_text = f"{task_data['name']}"
            if task_data['status'] != '等待中':
                display_text += f" [{task_data['status']}]"

            self.task_listbox.insert(tk.END, display_text)

            # 修正：使用实际的索引而不是tk.END - 1
            current_index = self.task_listbox.index(tk.END) - 1
            self.task_listbox.itemconfig(current_index, {'bg': '#f0f0f0'})

    def on_task_selected(self, event):
        """当任务列表中的任务被选中时"""
        selection = self.task_listbox.curselection()
        if selection:
            index = selection[0]
            # 获取对应的任务ID
            task_ids = list(self.tasks.keys())
            if index < len(task_ids):
                task_id = task_ids[index]
                # 切换到对应的标签页
                for i, tab_id in enumerate(self.notebook.tabs()):
                    if self.tasks[task_id]['frame'] == self.notebook.nametowidget(tab_id):
                        self.notebook.select(i)
                        break

    def on_tab_changed(self, event):
        """当标签页切换时"""
        current_tab = self.notebook.select()
        if current_tab:
            # 找到对应的任务
            for task_id, task_data in self.tasks.items():
                if task_data['frame'] == self.notebook.nametowidget(current_tab):
                    self.current_task_id = task_id
                    self.update_task_status_display()
                    break

    def update_task_status_display(self):
        """更新任务状态显示"""
        if self.current_task_id and self.current_task_id in self.tasks:
            task_data = self.tasks[self.current_task_id]

            status_text = f"任务: {task_data['name']}\n"
            status_text += f"状态: {task_data['status']}\n"
            status_text += f"艺人数量: {task_data['artists_count']}\n"
            status_text += f"歌曲: {task_data['songs_saved']}/{task_data['songs_total']}"

            self.task_status_label.config(text=status_text)

    def rename_current_task(self):
        """重命名当前任务"""
        if not self.current_task_id:
            messagebox.showwarning("无选中任务", "请先选择一个任务")
            return

        task_data = self.tasks[self.current_task_id]

        dialog = tk.Toplevel(self.root)
        dialog.title("重命名任务")
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        content_frame = ttk.Frame(dialog, padding="20")
        content_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(content_frame, text="新任务名称:",
                  font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 10))

        new_name_var = tk.StringVar(value=task_data['name'])
        name_entry = ttk.Entry(content_frame, textvariable=new_name_var,
                               font=("Arial", 10))
        name_entry.pack(fill=tk.X, pady=(0, 20))
        name_entry.select_range(0, tk.END)
        name_entry.focus_set()

        def rename_task():
            new_name = new_name_var.get().strip()
            if not new_name:
                messagebox.showwarning("输入错误", "任务名称不能为空")
                return

            # 检查名称是否重复（排除自己）
            for task_id, data in self.tasks.items():
                if task_id != self.current_task_id and data['name'] == new_name:
                    messagebox.showwarning("名称重复", f"任务名称 '{new_name}' 已存在")
                    return

            # 更新任务名称
            old_name = task_data['name']
            task_data['name'] = new_name

            # 更新Notebook标签
            for i, tab_id in enumerate(self.notebook.tabs()):
                if task_data['frame'] == self.notebook.nametowidget(tab_id):
                    self.notebook.tab(i, text=new_name)
                    break

            # 更新列表
            self.update_task_list()
            dialog.destroy()

        def on_enter(event):
            rename_task()

        name_entry.bind('<Return>', on_enter)

        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill=tk.X)

        ttk.Button(button_frame, text="重命名",
                   command=rename_task, width=10).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="取消",
                   command=dialog.destroy, width=10).pack(side=tk.RIGHT)

    def delete_current_task(self):
        """删除当前任务"""
        if not self.current_task_id:
            messagebox.showwarning("无选中任务", "请先选择一个任务")
            return

        task_data = self.tasks[self.current_task_id]

        confirm = messagebox.askyesno("确认删除",
                                      f"确定要删除任务 '{task_data['name']}' 吗？\n"
                                      "注意：这不会删除已下载的文件。")

        if confirm:
            # 保存任务设置（如果需要）
            if task_data['instance']:
                try:
                    task_data['instance'].save_settings()
                except:
                    pass

            # 从Notebook移除
            for i, tab_id in enumerate(self.notebook.tabs()):
                if task_data['frame'] == self.notebook.nametowidget(tab_id):
                    self.notebook.forget(i)
                    break

            # 从任务列表移除
            del self.tasks[self.current_task_id]

            # 如果没有任务了，创建一个默认任务
            if not self.tasks:
                self.create_new_task("默认任务")

            # 更新显示
            self.update_task_list()
            self.update_global_status()
            self.current_task_id = None
            self.task_status_label.config(text="选择任务查看状态")

    def update_global_status(self):
        """更新全局状态"""
        total_tasks = len(self.tasks)
        active_tasks = sum(1 for t in self.tasks.values()
                           if t.get('status') == '运行中')

        self.global_status_label.config(
            text=f"就绪 - 共 {total_tasks} 个任务，{active_tasks} 个运行中")

    def save_tasks(self):
        """保存任务配置"""
        tasks_config = {}

        for task_id, task_data in self.tasks.items():
            # 只保存基本配置，不保存GUI实例
            tasks_config[task_id] = {
                'name': task_data['name'],
                'api_token': task_data['api_token'],
                'save_path': task_data['save_path'],
                'status': task_data['status'],
                'artists_count': task_data['artists_count'],
                'songs_saved': task_data['songs_saved'],
                'songs_total': task_data['songs_total']
            }

        try:
            config_path = os.path.join(os.getcwd(), "multi_task_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(tasks_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存任务配置失败: {str(e)}")

    def load_tasks(self):
        """加载任务配置"""
        try:
            config_path = os.path.join(os.getcwd(), "multi_task_config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    tasks_config = json.load(f)

                # 恢复任务
                for task_id, config in tasks_config.items():
                    self.create_new_task(
                        config['name'],
                        config.get('api_token', ''),
                        config.get('save_path', '')
                    )

                    # 恢复任务状态
                    if task_id in self.tasks:
                        self.tasks[task_id].update({
                            'status': config.get('status', '等待中'),
                            'artists_count': config.get('artists_count', 0),
                            'songs_saved': config.get('songs_saved', 0),
                            'songs_total': config.get('songs_total', 0)
                        })

                self.update_task_list()
                self.update_global_status()

        except Exception as e:
            print(f"加载任务配置失败: {str(e)}")

    def on_closing(self):
        """关闭窗口时的处理"""
        # 保存所有任务的设置
        for task_id, task_data in self.tasks.items():
            if task_data['instance']:
                try:
                    task_data['instance'].save_settings()
                except:
                    pass

        # 保存多任务配置
        self.save_tasks()

        self.root.destroy()


def main():
    root = tk.Tk()
    app = MultiTaskManager(root)

    # 设置最小窗口大小
    root.minsize(1400, 800)

    # 绑定关闭事件
    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    root.mainloop()


if __name__ == "__main__":
    main()