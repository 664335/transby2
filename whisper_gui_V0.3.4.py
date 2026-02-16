# encoding:utf-8
import os
import sys

# 设置运行时环境
def setup_environment():
    """
    设置程序运行环境并返回一个函数用于获取可执行文件路径
    """
    if getattr(sys, 'frozen', False):
        # 打包环境：使用libs目录
        app_dir = os.path.dirname(sys.executable)
        libs_dir = os.path.join(app_dir, "libs")
        
        # 添加libs到系统路径
        if libs_dir not in sys.path:
            sys.path.insert(0, libs_dir)
        
        # 返回一个函数，在打包环境下从libs目录获取可执行文件
        def get_executable_path(executable_name):
            return os.path.join(libs_dir, executable_name)
        
        print(f"打包模式：使用 {libs_dir} 目录")
        return get_executable_path
    else:
        # 调试环境：使用系统环境变量
        print("调试模式：使用系统环境变量查找可执行文件")
        
        # 返回一个函数，在调试环境下从系统PATH获取可执行文件
        def get_executable_path(executable_name):
            # 首先尝试从系统PATH中查找
            import shutil
            executable_path = shutil.which(executable_name)
            if executable_path:
                return executable_path
            
            # 如果系统PATH中找不到，尝试从可能的本地libs目录查找（作为后备）
            app_dir = os.path.dirname(os.path.abspath(__file__))
            libs_dir = os.path.join(app_dir, "libs")
            local_path = os.path.join(libs_dir, executable_name)
            
            if os.path.exists(local_path):
                print(f"警告：系统PATH中未找到 {executable_name}，使用本地版本")
                return local_path
            
            # 如果都找不到，返回None
            print(f"错误：未找到可执行文件 {executable_name}")
            return None
        
        return get_executable_path

# 在程序启动时调用
get_executable_path = setup_environment()


import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
import threading
import queue
import torch
from faster_whisper import WhisperModel
from tqdm import tqdm
import ffmpeg
import json
import yt_dlp
import time
from crypto_utils import CryptoUtils
import re
from openai import OpenAI, AuthenticationError, RateLimitError, APIError
import requests
import ctypes
import subprocess
import markdown
from tkhtmlview import HTMLLabel  
from tkinterhtml import HtmlFrame

# 设置DPI感知，解决高DPI显示器模糊问题
try:
    # Windows 8.1及以上版本
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    try:
        # Windows 8及以下版本
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass

class TranscriptionApp:
    def __init__(self, root):
        self.root = root
        
        # 隐藏窗口直到位置设置完成，避免闪烁
        self.root.withdraw()        
        root.option_add("*Font", ("苹方 中等", 10))
        self.root.title("Tansby2(预设:Default)")        
        self.center_window()  # 此时窗口隐藏，设置位置无闪烁
        
        # 存储libs_dir路径供后续使用
        if getattr(sys, 'frozen', False):
            self.app_dir = os.path.dirname(sys.executable)
            self.libs_dir = os.path.join(self.app_dir, "libs")
        else:
            self.libs_dir = None
        
        # 获取 ffmpeg 和 yt-dlp 的路径
        self.ffmpeg_exe_path = get_executable_path('ffmpeg.exe')
        self.yt_dlp_exe_path = get_executable_path('yt-dlp.exe')

        #markdown相关参数
        self.enable_markdown_preview = tk.BooleanVar(value=True) # 默认启用Markdown预览
        self.markdown_html_frame = None
        self.markdown_splitter = None

        # 文件路径变量
        self.input_file = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.subtitle_file_var = tk.StringVar()
        self.audit_subtitle_file_var = tk.StringVar()
        self.looping_image_var = tk.StringVar()
        self.looping_audio_var = tk.StringVar()

        # 模型参数
        self.language = "日语"
        self.is_split = "Yes"        
        self.is_vad_filter = tk.BooleanVar(value=True)
        self.set_beam_size = 5
        self.beam_size_off = False
        
        # 预设管理
        self.presets = {}
        self.current_preset = "Default"
        self.preset_menu = None
        self.preset_combo = None       
        self.is_modified = False  # 参数修改标记
        
        # 模型路径变量
        self.model_path_var = tk.StringVar()
        self.model_path = ""
        
        # AI翻译配置
        self.enable_ai_translation = tk.BooleanVar(value=False)
        self.enable_segment_summary = tk.BooleanVar(value=False)
        self.api_keys = {}  # 存储不同服务商的API密钥
        self.current_api_key = ""  # 当前服务商的API密钥
        self.api_key_status_cache = {}  # API密钥状态缓存
        self.ai_model = "deepseek-chat"
        self.temperature = 1.3
        self.system_prompt = "你是一个专业的翻译助手，请将以下日文字幕翻译成中文，保持原有的格式和结构。"
        self.batch_size = 80  # 每批次字幕行数

        # 服务商配置
        self.provider_var = tk.StringVar(value="DeepSeek")
        self.providers = {
            "DeepSeek": {
                "api_url": "https://api.deepseek.com",                
                "model_options": ["deepseek-chat", "deepseek-reasoner"],
                "is_available_url": "https://api.deepseek.com/user/balance"
            },
            "Gemini": {
                "api_url": "https://generativelanguage.googleapis.com/v1beta/openai/",                              
                "model_options": ["gemini-2.5-pro","gemini-2.5-flash",
                                  "gemini-3-flash","gemini-3-pro"]                
            },
            "OpenAI": {
                "api_url": "https://api.openai.com",
                "model_options": ["gpt-4o", "gpt-5", "gpt-4.1", 
                                  "gpt-4.1-mini", "gpt-4o-mini"],
                "is_available_url": "https://api.openai.com/dashboard/billing/credit_grants"
            },
            "OpenRouter": {
                "api_url": "https://openrouter.ai/api/v1",
                "model_options": ["openai/gpt-4o", "openai/gpt-5", "openai/gpt-4.1", 
                                  "openai/gpt-4.1-mini", "openai/gpt-4o-mini", 
                                  "google/gemini-2.5-flash", "google/gemini-2.5-pro",
                                  "google/gemini-3-flash","google/gemini-3-pro"],
                "is_available_url": "https://openrouter.ai/api/v1/credits"
            }
        }
        
        # 加密工具
        self.crypto = CryptoUtils()

        # 创建选项卡
        self.create_notebook()
        
        # 创建UI组件
        self.create_transcription_widgets()
        self.create_ai_translation_widgets()        
        self.create_segment_summary_widgets()
        self.common_tools_frame_widgets()
        
        # 加载配置
        self.load_config()
        self.save_preset()        

        # 设置窗口图标（在UI组件创建完成后）
        self.root.after(100, self.set_window_icon)
        
        # 进度队列
        self.progress_queue = queue.Queue() 
        
        # 下载日志队列和更新时间戳
        self.download_log_queue = queue.Queue()
        self.last_download_log_update_time = 0
        
        # 初始化模型（在实际使用时可改为按需加载）
        self.model = None

        # 启动下载日志队列检查
        self.root.after(100, self.check_download_log_queue)
        
        # 在UI组件创建完成后显示窗口
        self.root.after(100, self.root.deiconify)
        
        # 强制更新所有UI布局，确保所有选项卡的按钮立即渲染
        self.root.after(200, self.force_update_all_tabs)

    def create_notebook(self):
        """创建选项卡界面"""
        self.style = ttk.Style()
        self.style.configure("Custom.TNotebook.Tab", font=("苹方 中等", 10))
        
        self.notebook = ttk.Notebook(self.root, style="Custom.TNotebook")
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 听写选项卡
        self.transcription_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.transcription_frame, text='听写')
        
        # AI翻译选项卡
        self.ai_translation_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.ai_translation_frame, text='翻译参数')

        # 时间段总结选项卡
        self.segment_summary_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.segment_summary_frame, text='分段总结') 

        # 常用工具选项卡
        self.common_tools_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.common_tools_frame, text='常用工具') 

    def create_transcription_widgets(self):
        """创建转写选项卡的UI组件"""
        # 模型选择框架
        model_frame = ttk.LabelFrame(self.transcription_frame, text="模型选择")
        model_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Button(model_frame, text="选择模型文件夹", command=self.browse_model_folder).grid(row=0, column=0, padx=5)
        ttk.Label(model_frame, textvariable=self.model_path_var, width=50, font=("苹方 中等", 10)).grid(row=0, column=1, padx=5, sticky="w")
        
        # 文件选择框架
        file_frame = ttk.LabelFrame(self.transcription_frame, text="文件选择")
        file_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Button(file_frame, text="选择媒体文件", command=self.browse_media_file).grid(row=0, column=0, padx=5)
        ttk.Label(file_frame, textvariable=self.input_file, font=("苹方 中等", 10)).grid(row=0, column=1, sticky="w")     

        # 听写语言选择框架
        language_frame = ttk.LabelFrame(self.transcription_frame, text="听写参数设置")
        language_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(language_frame, text="语言:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        self.language_combo = ttk.Combobox(language_frame, values=["日语", "英语","中文"], width=4, font=("苹方 中等", 10))       
        self.language_combo.set(self.language)
        self.language_combo.grid(row=0, column=1, padx=5, sticky="w")
        self.language_combo.bind("<<ComboboxSelected>>", self.on_language_change)

        ttk.Checkbutton(language_frame, text="VAD开关", variable=self.is_vad_filter, 
                       command=self.on_VAD_toggle).grid(row=0, column=4, padx=5, sticky="w")

        # 字幕后处理勾选框
        ai_frame = ttk.LabelFrame(self.transcription_frame, text="听写后处理选项")
        ai_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Checkbutton(ai_frame, text="AI翻译", variable=self.enable_ai_translation, 
                       command=self.on_ai_translation_toggle).grid(row=0, column=0, padx=5, sticky="w")
        
        ttk.Checkbutton(ai_frame, text="AI分段总结", variable=self.enable_segment_summary, 
                       command=self.on_segment_summary_toggle).grid(row=0, column=5, padx=5, sticky="w")

        # 进度条
        self.progress = ttk.Progressbar(self.transcription_frame, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=20)
        
        # 控制按钮
        self.start_btn = ttk.Button(self.transcription_frame, text="开始任务", command=self.start_transcription)
        
        self.start_btn.pack(pady=10)
        
        # 日志输出
        self.log_text = tk.Text(self.transcription_frame, height=10, state=tk.DISABLED, font=("苹方 中等", 11))
        self.log_text.pack(pady=10, padx=10, fill="both", expand=True)

    def create_ai_translation_widgets(self):
        """创建AI翻译选项卡的UI组件"""
        
        # 服务商选择框架
        provider_frame = ttk.LabelFrame(self.ai_translation_frame, text="AI参数设置")
        provider_frame.pack(pady=10, padx=10, fill="x")        
        ttk.Label(provider_frame, text="服务商:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")

        # 服务商选择框架下拉菜单
        self.provider_button = ttk.Menubutton(provider_frame, text=self.provider_var.get(), width=15)
        self.provider_menu = tk.Menu(self.provider_button, tearoff=0)
        self.provider_button.configure(menu=self.provider_menu)
        self.provider_button.grid(row=0, column=1, padx=5, sticky="w")
        self.update_provider_menu()

        ttk.Label(provider_frame, text="模型:", font=("苹方 中等", 10)).grid(row=0, column=2, padx=5, sticky="w")

        self.model_button = ttk.Menubutton(provider_frame, text=self.ai_model, width=15)
        self.model_menu = tk.Menu(self.model_button, tearoff=0)
        self.model_button.configure(menu=self.model_menu)
        self.model_button.grid(row=0, column=3, padx=5, sticky="w")
        self.update_model_menu()

        ttk.Label(provider_frame, text="温度:", font=("苹方 中等", 10)).grid(row=0, column=4, padx=5, sticky="w")
        self.temperature_scale = ttk.Scale(provider_frame, from_=0.0, to=2.0, value=self.temperature, orient="horizontal")
        self.temperature_scale.grid(row=0, column=5, padx=5, sticky="w") 
        self.temperature_scale.configure(command=lambda value: [self.update_temperature_label(value), self.check_preset_if_modified()])

        self.temperature_label = ttk.Label(provider_frame, text=f"{self.temperature:.1f}", font=("苹方 中等", 10))
        self.temperature_label.grid(row=0, column=6, padx=5, sticky="w")

        # API设置框架
        api_frame = ttk.LabelFrame(self.ai_translation_frame, text="API设置")
        api_frame.pack(pady=10, padx=10, fill="x")
        ttk.Label(api_frame, text="API密钥:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        self.api_key_entry = ttk.Entry(api_frame, width=20, show="*", font=("苹方 中等", 10))
        self.api_key_entry.grid(row=0, column=1, padx=5, sticky="w")
        ttk.Button(api_frame, text="保存API密钥", command=self.save_api_key).grid(row=0, column=2, padx=5)

        # 预设框架
        preset_and_subtitle_frame = ttk.LabelFrame(self.ai_translation_frame, text="预设和字幕文件操作")
        preset_and_subtitle_frame.pack(pady=10, padx=10, fill="x")        
        ttk.Label(preset_and_subtitle_frame, text="预设:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        
        # 预设下拉菜单按钮
        self.preset_button = ttk.Menubutton(preset_and_subtitle_frame, text="预设", width=10)
        self.preset_menu = tk.Menu(self.preset_button, tearoff=0)
        self.preset_button.configure(menu=self.preset_menu)
        self.preset_button.grid(row=0, column=1, padx=5, sticky="w") 

        # 每批次字幕行数
        ttk.Label(preset_and_subtitle_frame, text="每批次字幕行数:", font=("苹方 中等", 10)).grid(row=1, column=0, padx=5, sticky="w")

        self.batch_size_entry = ttk.Entry(preset_and_subtitle_frame, textvariable=self.batch_size, width=4, font=("苹方 中等", 10))
        self.batch_size_entry.grid(row=1, column=1, padx=5, sticky="w")
        self.batch_size_entry.bind("<KeyRelease>", lambda e: self.check_preset_if_modified()) # 绑定事件以检查修改

        ttk.Button(preset_and_subtitle_frame, text="保存预设", command=self.save_preset).grid(row=0, column=2, padx=5)
        ttk.Button(preset_and_subtitle_frame, text="提交字幕", command=self.submit_subtitle).grid(row=1, column=2, padx=5)
        ttk.Button(preset_and_subtitle_frame, text="开始翻译", command=self.start_translation).grid(row=1, column=3, padx=5)
        
        # 字幕文件路径显示        
        ttk.Label(preset_and_subtitle_frame, textvariable=self.subtitle_file_var, width=120, font=("苹方 中等", 10)).grid(row=1, column=4, padx=5, sticky="w")

        # 系统提示词框架
        prompt_frame = ttk.LabelFrame(self.ai_translation_frame, text="提示词")
        prompt_frame.pack(pady=10, padx=10, fill="both", expand=True)

        # 创建一个PanedWindow来实现左右分割
        self.prompt_splitter = ttk.PanedWindow(prompt_frame, orient=tk.HORIZONTAL)
        self.prompt_splitter.pack(fill="both", expand=True, padx=5, pady=5)

        # 左侧：Markdown 输入框
        left_pane = ttk.Frame(self.prompt_splitter)
        self.prompt_splitter.add(left_pane, weight=1)
        left_pane.columnconfigure(0, weight=1)
        left_pane.rowconfigure(0, weight=1)

        self.prompt_text = tk.Text(left_pane, wrap="word", font=("苹方 粗体", 11))
        self.prompt_text.insert("1.0", self.system_prompt)
        self.prompt_text.grid(row=0, column=0, sticky="nsew")

        prompt_text_scrollbar = ttk.Scrollbar(left_pane, orient="vertical", command=self.prompt_text.yview)
        self.prompt_text.config(yscrollcommand=prompt_text_scrollbar.set)
        prompt_text_scrollbar.grid(row=0, column=1, sticky="ns")

        # 右侧：Markdown 预览区
        right_pane = ttk.Frame(self.prompt_splitter)
        self.prompt_splitter.add(right_pane, weight=1)
        right_pane.columnconfigure(0, weight=1)
        right_pane.rowconfigure(0, weight=1)

        self.markdown_preview = HTMLLabel(right_pane, background="white", html="")
        self.markdown_preview.grid(row=0, column=0, sticky="nsew")
        self.preview_font = font.Font(family="苹方 粗体", size=11, weight="bold")
        markdown_preview_scrollbar = ttk.Scrollbar(right_pane, orient="vertical", command=self.markdown_preview.yview)
        self.markdown_preview.config(yscrollcommand=markdown_preview_scrollbar.set)
        markdown_preview_scrollbar.grid(row=0, column=1, sticky="ns")

        # 绑定输入事件实现实时刷新
        self.prompt_text.bind("<<Modified>>", self.update_markdown_preview)
        self.prompt_text.edit_modified(False) # 重置修改标志

        # 绑定文本变化事件来检测参数修改
        self.prompt_text.bind("<KeyRelease>", lambda e: self.check_preset_if_modified())
        
    def create_segment_summary_widgets(self):
        """创建时间段总结选项卡的UI组件"""
        # 文件选择框架
        file_frame = ttk.LabelFrame(self.segment_summary_frame, text="ASS文件选择(总结完成后会自动保存)")
        file_frame.pack(pady=10, padx=10, fill="x")        
        ttk.Button(file_frame, text="选择ASS文件", command=self.submit_subtitle).grid(row=0, column=0, padx=5)
        ttk.Label(file_frame, textvariable=self.subtitle_file_var, width=50, font=("苹方 中等", 10)).grid(row=0, column=1, padx=5, sticky="w")
        
        # 参数设置框架
        params_frame = ttk.LabelFrame(self.segment_summary_frame, text="时间段参数")
        params_frame.pack(pady=10, padx=10, fill="x")
        
        # 时间窗口设置
        ttk.Label(params_frame, text="时间窗口(分钟):", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        self.time_window_var = tk.StringVar(value="10")
        time_window_entry = ttk.Entry(params_frame, textvariable=self.time_window_var, width=4, font=("苹方 中等", 10))
        time_window_entry.grid(row=0, column=1, padx=5, sticky="w")
        ttk.Button(params_frame, text="开始总结", command=self.start_segment_summary_analysis).grid(row=0, column=2, padx=5)     
        
        # 结果显示区域
        result_frame = ttk.LabelFrame(self.segment_summary_frame, text="分段总结结果")
        result_frame.pack(pady=10, padx=10, fill="both", expand=True)
        
        # 创建文本框和滚动条
        self.segment_result_text = tk.Text(result_frame, height=15, font=("苹方 中等", 11), wrap=tk.WORD)
        result_scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.segment_result_text.yview)
        self.segment_result_text.configure(yscrollcommand=result_scrollbar.set)
        
        self.segment_result_text.pack(side=tk.LEFT, fill="both", expand=True, padx=5, pady=5)
        result_scrollbar.pack(side=tk.RIGHT, fill="y", padx=(0, 5), pady=5)
        
        # 初始化结果存储
        self.segment_results = []

    def common_tools_frame_widgets(self):
        """创建常用工具选项卡的UI组件"""
        # YouTube视频下载框架
        youtube_download_frame = ttk.LabelFrame(self.common_tools_frame, text="视频下载")
        youtube_download_frame.pack(pady=10, padx=10, fill="x")
        
        # URL输入行
        url_frame = ttk.Frame(youtube_download_frame)
        url_frame.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        url_frame.columnconfigure(1, weight=1)
        
        ttk.Label(url_frame, text="视频URL:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        self.url_entry = ttk.Entry(url_frame, width=50, font=("苹方 中等", 10))
        self.url_entry.grid(row=0, column=1, padx=5, sticky="w")
        ttk.Button(url_frame, text="获取格式", command=self.fetch_video_formats).grid(row=0, column=2, padx=5)

        # 存放地址行
        save_path_frame = ttk.Frame(youtube_download_frame)
        save_path_frame.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))
        save_path_frame.columnconfigure(1, weight=1)
        
        ttk.Label(save_path_frame, text="存放地址:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        self.save_path_var = tk.StringVar()
        self.save_path_entry = ttk.Entry(save_path_frame, textvariable=self.save_path_var, width=50, font=("苹方 中等", 10))
        self.save_path_entry.grid(row=0, column=1, padx=5, sticky="w")
        ttk.Button(save_path_frame, text="浏览", command=self.browse_save_path).grid(row=0, column=2, padx=5)
        
        # 格式选择行
        format_frame = ttk.Frame(youtube_download_frame)
        format_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 10))
        
        ttk.Label(format_frame, text="视频格式:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        self.video_format_var = tk.StringVar()
        self.video_format_combo = ttk.Combobox(format_frame, textvariable=self.video_format_var, width=40, font=("苹方 中等", 10))
        self.video_format_combo.grid(row=0, column=1, padx=5, sticky="w")
        
        ttk.Label(format_frame, text="音频格式:", font=("苹方 中等", 10)).grid(row=1, column=0, padx=5, sticky="w")
        self.audio_format_var = tk.StringVar()
        self.audio_format_combo = ttk.Combobox(format_frame, textvariable=self.audio_format_var, width=40, font=("苹方 中等", 10))
        self.audio_format_combo.grid(row=1, column=1, padx=5, sticky="w")
        # 下载按钮
        ttk.Button(format_frame, text="开始下载", command=self.youtube_download).grid(row=1, column=2, padx=5)
            
        # 初始化格式列表和映射
        self.video_formats = []
        self.audio_formats = []
        self.video_format_map = {}
        self.audio_format_map = {}
        
        # 设置列权重使框架可扩展
        youtube_download_frame.columnconfigure(0, weight=1)

        #字幕后处理框
        timeline_audit_frame = ttk.LabelFrame(self.common_tools_frame, text="字幕后处理工具")
        timeline_audit_frame.pack(pady=10, padx=10, fill="x")

        #导入字幕文件
        ttk.Button(timeline_audit_frame, text="导入字幕文件", command=self.audit_summit_subtitle_file).grid(row=0, column=0, padx=5, sticky="w")
        ttk.Button(timeline_audit_frame, text="开始锤轴", command=self.audit_subtitle).grid(row=0, column=1, padx=5, sticky="w")        
        ttk.Button(timeline_audit_frame, text="生成水印", command=self.generate_watermark).grid(row=0, column=2, padx=5, sticky="w") 
        ttk.Label(timeline_audit_frame, text="水印文本:", font=("苹方 中等", 10)).grid(row=0, column=3, padx=15, sticky="w")      

        self.watermark_entry = ttk.Entry(timeline_audit_frame, width=30, font=("苹方 中等", 10))
        self.watermark_entry.grid(row=0, column=4, padx=5, sticky="w")

        #一图流 
        looping_frame = ttk.LabelFrame(self.common_tools_frame, text="一图流视频")
        looping_frame.pack(pady=10, padx=10, fill="x")        
        ttk.Button(looping_frame, text="导入图片", command=self.import_looping_image).grid(row=0, column=0, padx=5, sticky="w")
        ttk.Button(looping_frame, text="导入音频", command=self.import_looping_audio).grid(row=0, column=1, padx=5, sticky="w")
        ttk.Button(looping_frame, text="生成视频", command=self.generate_looping_video).grid(row=0, column=2, padx=5, sticky="w")        

        # 下载日志框
        log_frame = ttk.LabelFrame(self.common_tools_frame, text="常用工具日志")
        log_frame.pack(pady=10, padx=10, fill="both", expand=True)
        
        self.download_log_text = tk.Text(log_frame, height=15, state=tk.DISABLED, font=("苹方 中等", 10))
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.download_log_text.yview)
        self.download_log_text.configure(yscrollcommand=scrollbar.set)
        self.download_log_text.pack(side=tk.LEFT, fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill="y", padx=(0, 5), pady=5)

    #一图流功能部分
    def import_looping_image(self):
        """导入用于一图流的视频图片"""
        file_path = filedialog.askopenfilename(
            title="选择图片文件", 
            filetypes=[("图片文件", "*.png;*.jpg;*.jpeg;*.bmp;*.webp"), ("所有文件", "*.*")])

        if file_path:
            self.looping_image_var.set(file_path)
            normalized_path = file_path.replace('/', '\\')
            self.log_download(f"已选择图片文件: {normalized_path}")

    def import_looping_audio(self):
        """导入用于一图流的视频音频"""
        file_path = filedialog.askopenfilename(
            title="选择音频文件", 
            filetypes=[("音频文件", "*.mp3;*.wav;*.aac;*.m4a;*.flac"), ("所有文件", "*.*")])

        if file_path:
            self.looping_audio_var.set(file_path)
            normalized_path = file_path.replace('/', '\\')
            self.log_download(f"已选择音频文件: {normalized_path}")

    def generate_looping_video(self):
        """生成一图流视频"""
        image_path = self.looping_image_var.get().strip()
        audio_path = self.looping_audio_var.get().strip()
        if not image_path:
            messagebox.showerror("错误", "请选择图片文件")
            return
        if not audio_path:
            messagebox.showerror("错误", "请选择音频文件")
            return     
        
        def looping_generate():
            try:
                # 获取音频时长
                audio_info = ffmpeg.probe(audio_path)
                audio_duration = float(audio_info['format']['duration'])

                #视频输出路径为输入音频路径同目录下，文件名为音频文件名.mp4
                output_dir = os.path.dirname(audio_path)
                output_filename = os.path.splitext(os.path.basename(audio_path))[0] + ".mp4"
                output_path = os.path.join(output_dir, output_filename)


                if not output_path:
                    self.log_download("已取消保存视频文件")
                    return
                
                input_video = ffmpeg.input(image_path, loop=1)
                input_audio = ffmpeg.input(audio_path) 

                # 使用ffmpeg生成一图流视频
                (
                    ffmpeg
                    .output(
                        input_video,
                        input_audio,
                        output_path,
                        vcodec='hevc_nvenc',
                        preset='p7',
                        rc='vbr',
                        b='1500k',
                        maxrate='3000k',
                        bufsize='6000k',
                        r=30,
                        g=60,
                        pix_fmt='yuv420p',
                        acodec='copy',
                        t=audio_duration,
                        shortest=None,
                        vsync='cfr',
                        threads=0
                    )
                    .run(overwrite_output=True)
                )
                
                normalized_output_path = output_path.replace('/', '\\')
                self.log_download(f"视频生成完成，已保存至: {normalized_output_path}")
            except Exception as e:
                self.log_download(f"生成视频出错: {str(e)}")

        threading.Thread(target=looping_generate, daemon=True).start()                

    # 轴审姬功能部分
    def audit_summit_subtitle_file(self):
        """选择字幕文件用于轴审姬"""
        file_path = filedialog.askopenfilename(
            title="选择字幕文件", 
            filetypes=[("字幕文件", "*.ass"), ("所有文件", "*.*")])

        if file_path:
            self.audit_subtitle_file_var.set(file_path)
            normalized_path = file_path.replace('/', '\\')
            self.log_download(f"已选择字幕文件: {normalized_path}")

    def audit_subtitle(self):
        """开始轴审姬锤字幕"""
        subtitle_path = self.audit_subtitle_file_var.get().strip()
        if not subtitle_path:
            messagebox.showerror("错误", "请选择字幕文件")
            return
        
        self.log_download("轴审姬开始锤字幕")
        
        def run_audit():
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()           
            #找到第一个Dialogue行的索引
            dialogue_index = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text'):
                    dialogue_index = i + 1
                    break  
            e = 0
            #分析字幕部分，Comment行算行数但是不参与时间轴闪轴连轴的分析
            for i in range(dialogue_index, len(lines)):   
                dialogue_parts_front = self.parse_ass_dialogue(lines[i])
                if dialogue_parts_front: 
                    for j in range(i + 1, len(lines)):                           
                        dialogue_parts_back = self.parse_ass_dialogue(lines[j])
                        if dialogue_parts_back:
                            current_start = self.ass_time_to_seconds(dialogue_parts_back['Start'])
                            previous_end = self.ass_time_to_seconds(dialogue_parts_front['End']) 
                            current_Style = dialogue_parts_back['Style']
                            previous_Style = dialogue_parts_front['Style']
                            if current_start is not None and previous_end is not None and current_Style == previous_Style:
                                gap = current_start - previous_end
                                if gap < 0.3 and gap > 0:  # 小于300毫秒视为闪轴
                                    self.log_download(f"第{i - dialogue_index + 1}行与第{i - dialogue_index + 2}行之间间隔仅 {gap*1000:.0f} 毫秒")
                                    e += 1
                                    break
                                if gap < 0:  # 负值表示叠轴
                                    self.log_download(f"第{i - dialogue_index + 1}行与第{i - dialogue_index + 2}行之间重叠，请注意查看")
                                    e += 1
                                    break
            if e == 0:
                self.log_download("未发现问题")
            else:
                self.log_download('锤完了！')

        threading.Thread(target=run_audit, daemon=True).start()
    
    # 水印生成部分
    def generate_watermark(self):
        """生成水印字幕文件"""
        subtitle_path = self.audit_subtitle_file_var.get().strip()
        watermark_text = self.watermark_entry.get().strip()
        if not subtitle_path:
            messagebox.showerror("错误", "请选择字幕文件")
            return
        if not watermark_text:
            messagebox.showerror("错误", "请输入水印文本")
            return        
        
        def run_generate():
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()           
            #找到最后一个Dialogue行的索引和结束时间            
            last_end_time = "00:00:00.00"
            for i, line in enumerate(lines):          
                if line.strip().startswith('Dialogue:'):
                    dialogue_parts = self.parse_ass_dialogue(line)
                    if last_end_time < dialogue_parts['End']:
                        last_end_time = dialogue_parts['End']
            last_end_time_seconds = self.ass_time_to_seconds(last_end_time)

            #初始化时间
            ms_s=0
            ss_s=0
            mm_s=0
            hh_s=0
            ms_e=0
            ss_e=0
            mm_e=0
            hh_e=0
            dialogue = []
            while True:            
                ms_rand = np.random.randint(40,100)
                ss_rand = np.random.randint(35,145)
                xpos_rand = np.random.randint(300,1700)
                ypos_rand = np.random.randint(100,1008)
                ms_e=ms_s+ms_rand
                ss_e=ss_s+ss_rand
                if ms_e>=100:
                    ss_e=ss_s+int((ms_e)/100)
                    ms_e=ms_e-int(ms_e/100)*100        
                if ss_e>=60:
                    ss_e=ss_e-60        
                    mm_e=mm_e+1        
                if mm_s>=60:       
                    mm_s=mm_s-60
                    hh_s=hh_s+1
                if mm_e>=60:        
                    mm_e=mm_e-60        
                    hh_e=hh_e+1
                #生成水印行    
                ass_tag = f"{{\\pos({xpos_rand},{ypos_rand})}}"            
                item = f"Dialogue: 1,{hh_s:01d}:{mm_s:02d}:{ss_s:02d}.{ms_s:02d},{hh_e:01d}:{mm_e:02d}:{ss_e:02d}.{ms_e:02d},水印,,0,0,0,,{ass_tag}{watermark_text}"            
                dialogue.append(item)
                ms_s=ms_e
                ss_s=ss_e
                mm_s=mm_e
                hh_s=hh_e  
                if hh_e*3600 + mm_e*60 + ss_e > last_end_time_seconds:
                    break              
            #将水印行添加到字幕文件最后
            with open(subtitle_path, 'a', encoding='utf-8') as f:
                for line in dialogue:
                    f.write(line + '\n')     
                   
            self.log_download(f"带水印字幕已添加至{subtitle_path}")
        threading.Thread(target=run_generate, daemon=True).start()

    # youtube_download part 
    def browse_save_path(self):
        """选择保存路径"""
        path = filedialog.askdirectory(title="选择保存路径")
        if path:
            self.save_path_var.set(path)
            self.log_download(f"已选择保存路径: {path}")

    def fetch_video_formats(self):
        """获取视频格式信息"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("错误", "请输入YouTube视频链接")
            return
        
        self.log_download(f"正在获取视频信息")
        
        def run_fetch():
            try:
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get('formats', [])
                    
                    self.video_format_map = {}
                    self.audio_format_map = {}
                    video_list = []
                    audio_list = []
                    
                    for f in formats:
                        # 视频格式
                        if f.get('vcodec') != 'none' and f.get('height') > 720:
                            resolution = f.get('resolution', 'N/A')
                            vcodec = f.get('vcodec', 'N/A')
                            filesize = f.get('filesize') or f.get('filesize_approx')
                            size_str = f"{filesize / 1024 / 1024:.1f}MB" if filesize else "N/A"
                            fps = f.get('fps', 'N/A')
                            
                            desc = f"{resolution} | {vcodec} | {size_str} | fps:{fps})"
                            video_list.append(desc)
                            self.video_format_map[desc] = f['format_id']
                            
                        # 音频格式
                        if f.get('acodec') != 'none' and f.get('resolution') == 'audio only':
                            abr = int(f.get('abr', 'N/A'))
                            acodec = f.get('acodec', 'N/A')
                            filesize = f.get('filesize') or f.get('filesize_approx')
                            size_str = f"{filesize / 1024 / 1024:.1f}MB" if filesize else "N/A"
                            
                            desc = f"{acodec} | {abr}kbps | {size_str})"
                            audio_list.append(desc)
                            self.audio_format_map[desc] = f['format_id']
                    
                    # 排序
                    video_list.reverse()
                    audio_list.reverse()
                    
                    # 更新UI
                    self.root.after(0, lambda: self.update_format_combos(video_list, audio_list, info.get('title', '未知标题')))
                    
            except Exception as e:
                self.root.after(0, lambda: self.log_download(f"获取格式失败: {str(e)}"))

        threading.Thread(target=run_fetch, daemon=True).start()

    def update_format_combos(self, video_list, audio_list, title):
        """更新格式下拉框"""
        self.video_format_combo['values'] = video_list
        if video_list:
            self.video_format_combo.current(0)
            
        self.audio_format_combo['values'] = audio_list
        if audio_list:
            self.audio_format_combo.current(0)
            
        self.log_download(f"成功获取视频信息: {title}")
        self.log_download(f"找到 {len(video_list)} 个视频格式, {len(audio_list)} 个音频格式")

    def youtube_download(self):
        """开始下载YouTube视频"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("错误", "请输入YouTube视频链接")
            return
            
        save_path = self.save_path_var.get().strip()
        if not save_path:
            messagebox.showerror("错误", "请选择存放地址")
            return
            
        # 获取选中的格式ID
        video_desc = self.video_format_var.get()
        audio_desc = self.audio_format_var.get()
        
        video_id = self.video_format_map.get(video_desc)
        audio_id = self.audio_format_map.get(audio_desc)
        
        if not video_id and not audio_id:
             format_str = 'bestvideo+bestaudio/best'
             self.log_download("未选择特定格式，将下载最佳质量...")
        else:
            if video_id and audio_id:
                format_str = f"{video_id}+{audio_id}"
            elif video_id:
                format_str = video_id
            else:
                format_str = audio_id
        
        self.log_download(f"准备下载: {url}")        
        
        def run_download():
            try:
                ydl_opts = {
                    'format': format_str,
                    'outtmpl': os.path.join(save_path, '%(title)s.%(ext)s'),
                    'progress_hooks': [self.download_progress_hook],
                    'merge_output_format': 'mkv', 
                    'quiet': True,
                    'no_warnings': True,
                    'executables': {'ffmpeg': self.ffmpeg_exe_path, 'yt-dlp': self.yt_dlp_exe_path}, # 指定 ffmpeg 和 yt-dlp 路径
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                self.root.after(0, lambda: self.log_download("下载完成！"))                
            except Exception as e:
                self.root.after(0, lambda: self.log_download(f"下载出错: {str(e)}"))
        threading.Thread(target=run_download, daemon=True).start()

    def download_progress_hook(self, d):
        """下载进度回调"""
        if d['status'] == 'downloading':
            # 清理yt-dlp输出中的ANSI转义字符
            percent = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', str(d.get('_percent_str', 'N/A'))).strip()
            speed = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', str(d.get('_speed_str', 'N/A'))).strip()
            eta = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', str(d.get('_eta_str', 'N/A'))).strip()
            msg = f"下载中: {percent} | 速度: {speed} | 剩余时间: {eta}"
            self.download_log_queue.put(msg) # 将下载进度消息放入队列
            
        elif d['status'] == 'finished':
            self.root.after(0, lambda: self._append_download_log_text_ui("下载阶段完成，正在处理/合并...")) # 直接追加完成消息

    def _replace_download_progress_ui(self, message):
        """实际更新下载状态UI，替换最后一行下载进度"""
        if hasattr(self, 'download_log_text'):
            self.download_log_text.config(state=tk.NORMAL)
            try:
                # 获取文本框的行数
                num_lines = int(self.download_log_text.index('end-1c').split('.')[0])
                
                # 如果文本框中有内容（行号大于0），并且最后一行是下载进度信息，则替换它
                if num_lines > 0:
                    last_line_content = self.download_log_text.get(f"{num_lines}.0", f"{num_lines}.end")
                    if "下载中:" in last_line_content: # 只有下载进度才替换
                        self.download_log_text.delete(f"{num_lines}.0", f"{num_lines}.end")
                
                # 插入新的消息
                self.download_log_text.insert(tk.END, message + "\n")
            except Exception as e:
                # 如果发生任何错误，直接追加消息
                self.download_log_text.insert(tk.END, message + "\n")
                print(f"替换下载进度UI时发生错误: {e}") # 记录错误以便调试
                
            self.download_log_text.see(tk.END)
            self.download_log_text.config(state=tk.DISABLED)

    def _append_download_log_text_ui(self, message):
        """实际更新下载状态UI，追加普通日志消息"""
        if hasattr(self, 'download_log_text'):
            self.download_log_text.config(state=tk.NORMAL)
            self.download_log_text.insert(tk.END, message + "\n")
            self.download_log_text.see(tk.END)
            self.download_log_text.config(state=tk.DISABLED)

    def check_download_log_queue(self):
        """检查下载日志队列并更新UI"""
        update_interval_ms = 500 # 每500毫秒更新一次UI
        
        # 获取当前时间，用于限制更新频率
        # 使用 time.time() 获取当前时间（秒），并转换为毫秒
        current_time_ms = int(time.time() * 1000)
        
        # 如果距离上次更新时间超过阈值，则处理队列中的最新消息
        if (current_time_ms - self.last_download_log_update_time) >= update_interval_ms:
            # 收集所有待处理的消息
            messages_to_process = []
            while not self.download_log_queue.empty():
                try:
                    messages_to_process.append(self.download_log_queue.get_nowait())
                except queue.Empty:
                    break
            
            if messages_to_process:
                # 分离下载进度消息和普通消息
                download_progress_messages = [msg for msg in messages_to_process if "下载中:" in msg]
                other_messages = [msg for msg in messages_to_process if "下载中:" not in msg]

                # 先处理所有普通消息，直接追加
                for msg in other_messages:
                    self._append_download_log_text_ui(msg)
                
                # 如果有下载进度消息，只处理最新一条，进行替换
                if download_progress_messages:
                    latest_progress_message = download_progress_messages[-1]
                    self._replace_download_progress_ui(latest_progress_message)
                
                self.last_download_log_update_time = current_time_ms
        
        # 再次调度自己
        self.root.after(update_interval_ms, self.check_download_log_queue)

    #translation part
    def submit_subtitle(self):
        """提交字幕文件"""
        file_path = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=[("字幕文件", "*.ass"), ("所有文件", "*.*")]
        )
        if file_path:
            self.subtitle_file_var.set(file_path)   

    def start_translation(self):
        """开始翻译字幕"""
        if not self.subtitle_file_var.get():
            messagebox.showerror("错误", "请先提交字幕文件")
            return
        
        if not self.current_api_key:
            messagebox.showerror("错误", "请先设置API密钥")
            return
        
        success, message = self.ensure_api_key_ready()
        if not success and message != "用户取消解密":            
            messagebox.showerror("错误", f"API密钥准备失败: {message}")
            return    
        # 禁用按钮防止重复点击
        self.log("开始翻译字幕...")
        self.save_preset()
        self.save_config()
        # 启动后台线程
        if success:
            threading.Thread(target=self.run_batch_translation, daemon=True).start()
        elif message == "用户取消解密":
            self.log("用户取消解密，翻译任务未启动")
            return
    
    def run_batch_translation(self):
        """执行分批翻译并且对AI返回结果进行时间轴重建和所有批次结果叠加最终输出可用ASS文件"""
        try:
            subtitle_file = self.subtitle_file_var.get()
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            # 找到第一个 Dialogue 行出现的位置
            first_dialogue_index = -1
            # 1. 遍历列表，找到第一个Dialogue行的索引
            for i, line in enumerate(lines):
                if line.strip().startswith('Dialogue:'):
                    first_dialogue_index = i
                    break
                    
            # 2. 根据索引分割列表
            if first_dialogue_index == -1:
                # 文件中没有Dialogue行，整个文件都是头部
                header_lines = lines
                dialogue_lines = []
            else:
                # 分别存储头部信息和原文用于最后输出
                header_lines = lines[:first_dialogue_index]
                dialogue_lines = lines[first_dialogue_index:]

            # 分批处理
            batch_size = int(self.batch_size_entry.get())
            total_batches = (len(dialogue_lines) + batch_size - 1) // batch_size
            self.log(f"字幕共 {len(dialogue_lines)} 行，分为 {total_batches} 批翻译")

            # 初始化对话历史和token消耗统计
            self.conversation_history = [] 
            total_token_usage = 0  
   
            # 输出文件路径
            base_name = os.path.splitext(os.path.basename(subtitle_file))[0]
            output_dir = os.path.dirname(subtitle_file)
            output_file_readytogo = os.path.join(output_dir, f"{base_name}_readytogo.ass")
            output_file_translation_log = os.path.join(output_dir, f"{base_name}_translation_log.txt")
            with open(output_file_readytogo, 'w', encoding='utf-8') as f:
                # 写入原始ASS头部
                f.writelines(header_lines)    
                f.write('\n')

            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min((batch_num + 1) * batch_size, len(dialogue_lines))
                
                batch_lines = dialogue_lines[start_idx:end_idx]
                api_input, context = self.prepare_input_for_api(batch_lines)
                batch_text = json.dumps(api_input, indent=2, ensure_ascii=False) 
                self.log(f"正在翻译第 {batch_num + 1}/{total_batches} 批")

                # 调用AI翻译API
                translated_batch, token_usage = self.call_ai_translation_api(batch_text) 
                total_token_usage += token_usage # 统计总token消耗

                # 重建ASS字幕行            
                current_batch_lines, translation_line = self.reconstruct_ass_from_response(translated_batch, context) 
                
                # 如果json解析失败，重试翻译本批次，最多重试三次
                for retry in range(3):
                    if current_batch_lines is None: # 检查是否为 None
                        self.log(f"第 {batch_num + 1} 批次解析失败，正在重试 (第 {retry + 1} 次)...")
                        translated_batch, token_usage = self.call_ai_translation_api(batch_text)
                        current_batch_lines, translation_line = self.reconstruct_ass_from_response(translated_batch, context)
                    else:
                        # 记录回复到对话历史 
                        self.add_to_conversation_history("assistant", translated_batch) 
                        break
                
                # 如果重试后仍然失败，则跳过当前批次
                if current_batch_lines is None:
                    self.log(f"第 {batch_num + 1} 批次翻译和重建ASS失败，跳过此批次。")
                    continue # 跳过当前批次，继续处理下一批次

                processed_lines = []            
                translated_lines = [str(line).strip() for line in current_batch_lines if str(line).strip()]
                for line in translated_lines:
                    if line.strip():
                        # 分离时间轴部分和文本部分
                        parts = line.split(',', 9)  # ASS格式有9个逗号分隔的字段
                        if len(parts) == 10:
                            # 前9部分是时间轴和样式信息，第10部分是文本
                            metadata = ','.join(parts[:9])
                            text_content = parts[9]
                            
                            # 对文本部分进行标点符号替换
                            processed_text = text_content.replace('，', ' ').replace('。', ' ').replace('、', ' ').replace('“', '「').replace('”', '」').replace('《', '『').replace('》', '』').replace('！', ' ').replace('？', ' ').replace('？', '吗')
                            
                            # 重新组合成完整的ASS行
                            processed_line = f"{metadata},{processed_text}"
                            processed_lines.append(processed_line)
                        else:
                            # 如果格式不对，保持原样
                            processed_lines.append(line)

                with open(output_file_readytogo, 'a', encoding='utf-8') as f:
                    f.write('\n'.join(processed_lines))
                    f.write('\n')  # 添加换行分隔不同批次                  

                with open(output_file_translation_log, 'a', encoding='utf-8') as f: 
                    f.write('\n'.join(translation_line))
                    f.write('\n')  # 添加换行分隔不同批次

            with open(output_file_readytogo, 'a', encoding='utf-8') as f:
                f.write('\n')
                # 写入处理后的翻译内容
                f.writelines(dialogue_lines)
            total_balance = self.ask_is_available()
            normalized_path = output_file_readytogo.replace('/', '\\')
            if self.provider_var.get() == "DeepSeek":
                self.log(f"翻译完成，结果已保存到: {normalized_path}, token消耗为{total_token_usage}, 余额为{total_balance}元")
            elif self.provider_var.get() == "OpenRouter":
                self.log(f"翻译完成，结果已保存到: {normalized_path}, token消耗为{total_token_usage}, 余额为{total_balance}美元")
            else:
                self.log(f"翻译完成，结果已保存到: {normalized_path}, token消耗为{total_token_usage}")

        except Exception as e:
            self.log(f"翻译失败: {str(e)}")
            self.log(f"错误内容: {translated_batch}") 

    def call_ai_translation_api(self, content):
        """调用AI翻译API，包含重试机制"""
        max_retries = 3
        retry_delay = 5  # 秒
        self.max_history = 10 # 最多保存10条历史记录

        # 获取当前服务商配置
        selected_provider = self.provider_var.get()
        provider_config = self.providers.get(selected_provider, self.providers["DeepSeek"])
        api_url = provider_config["api_url"]
        ai_model = self.ai_model

        for attempt in range(max_retries):
            # 全都用OpenAI SDK库调用            
            try:
                client = OpenAI(api_key=self.current_api_key, base_url=api_url)
                if self.conversation_history:
                    # 构建包含历史的消息列表
                    messages = [{"role": "system", "content": self.system_prompt}]
                    # 添加历史消息
                    messages.extend(self.conversation_history)
                    # 添加当前用户消息
                    messages.append({"role": "user", "content": content})
                else:
                    messages = [
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": content}            
                    ] 
                if "gemini" in self.ai_model:
                    response = client.chat.completions.create(
                        model=ai_model,
                        messages=messages, 
                        # reasoning_effort="medium", 
                        response_format={"type": "json_object"},                    
                        temperature=self.temperature,                        
                        stream=False
                    ) 
                else:
                    response = client.chat.completions.create(
                        model=ai_model,
                        messages=messages, 
                        max_tokens=8192,                                           
                        temperature=self.temperature,
                        response_format={"type": "json_object"},
                        stream=False
                    )         
                cleaned_string = self.clean_json_string(response.choices[0].message.content)                              
                return cleaned_string, response.usage.total_tokens

            except AuthenticationError as e:
                if attempt < max_retries - 1:
                    self.log(f"身份验证失败: {str(e)}，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    self.log(f"身份验证失败: {str(e)}，重试{max_retries}次后仍失败")
                    return None, 0
            except RateLimitError as e:
                if attempt < max_retries - 1:
                    self.log(f"请求频率限制: {str(e)}，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    self.log(f"请求频率限制: {str(e)}，重试{max_retries}次后仍失败")
                    return None, 0
            except APIError as e:
                if attempt < max_retries - 1:
                    self.log(f"API服务错误: {str(e)}，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    self.log(f"API服务错误: {str(e)}，重试{max_retries}次后仍失败")
                    return None, 0
            except Exception as e:
                if attempt < max_retries - 1:
                    self.log(f"未知错误: {str(e)}，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    self.log(f"未知错误: {str(e)}，重试{max_retries}次后仍失败")
                    return None, 0
        
        self.log(f"重试{max_retries}次后仍失败")
        return None

    def parse_ass_dialogue(self, line):
        """分离ASS字幕行各元素"""
        if not line.startswith('Dialogue:'):
            return None        
        match = re.match(r'Dialogue:\s*([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),(.*)', line)

        if not match:
            return None
        parts = match.groups()
        return {
            'Layer': parts[0], 'Start': parts[1], 'End': parts[2], 'Style': parts[3], 'Name': parts[4],
            'MarginL': parts[5], 'MarginR': parts[6], 'MarginV': parts[7], 'Effect': parts[8], 'Text': parts[9]
        }

    def prepare_input_for_api(self, dialogue_lines):   
        """提取开始时间和文本内容喂给AI，并且准备好本地时间轴映射信息"""
        api_input_items = []
        context_map = {}
        
        for line in dialogue_lines:
            dialogue_parts = self.parse_ass_dialogue(line)
            if dialogue_parts:
                start_time = dialogue_parts['Start']
                text = dialogue_parts['Text']
                
                api_input_items.append({
                    "timestamp": start_time,
                    "text": text
                })
                
                # 此处注意，我们将解析出的字典存入context，而不是原始行
                context_map[start_time] = dialogue_parts
                
        return api_input_items, context_map

    def reconstruct_ass_from_response(self, api_response, context_map):
        """
        根据API返回结果重建ASS,直接将原始头部和新生成的Dialogue行拼接。
        """
        if isinstance(api_response, str):
            try:
                parsed_response = json.loads(api_response)
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")

                self.log(f"原始响应: {api_response}")
                return None, None # 返回 None, None 表示解析失败
        else:
            parsed_response = api_response
        
        new_dialogue_lines = []
        tranlation_log = []

        # 确保解析后的响应包含translatedSentences
        if 'translatedSentences' not in parsed_response:
            print("API响应中缺少translatedSentences字段")
            print(f"响应内容: {parsed_response}")
            return None, None # 返回 None, None 表示解析失败
        
        for sentence_obj in parsed_response['translatedSentences']:
            translated_text = sentence_obj['sentence']
            related_items = sentence_obj['relatedInputItems']
            
            if not related_items:
                continue
                
            first_item_timestamp = related_items[0]['timestamp']
            last_item_timestamp = related_items[-1]['timestamp']
            
            # 确保时间戳在context_map中存在
            if first_item_timestamp not in context_map or last_item_timestamp not in context_map:                
                continue
                
            metadata = context_map[first_item_timestamp]
            
            start_time = metadata['Start']
            end_time = context_map[last_item_timestamp]['End']
            
            new_line = (
                f"Dialogue: {metadata['Layer']},{start_time},{end_time},对话,{metadata['Name']},{metadata['MarginL']},"                
                f"{metadata['MarginR']},{metadata['MarginV']},{metadata['Effect']},"
                f"{translated_text}"
            )
            new_dialogue_lines.append(new_line)

            tranlation_log.append(f"{translated_text}")
            for i in range(len(related_items)): 
                tranlation_log.append(f"{related_items[i]['text']}")
            tranlation_log.append(f"\n")
         
        return new_dialogue_lines,tranlation_log
 
    def ask_is_available(self):
        """查询当前API密钥余额状态"""
        try:
            selected_provider = self.provider_var.get()
            provider_config = self.providers.get(selected_provider, self.providers["DeepSeek"])
            is_available_url = provider_config["is_available_url"]
            headers = {
                "Authorization": f"Bearer {self.current_api_key}"
            }
            response = requests.get(is_available_url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if selected_provider == "DeepSeek":
                    balance = data['balance_infos'][0]['total_balance']
                    return balance
                # elif selected_provider == "Gemini":
                #     # 假设Gemini返回的余额字段为"credits"
                #     balance = data.get("credits", "未知")
                #     return balance
                # elif selected_provider == "OpenAI":
                #     # OpenAI的余额查询可能需要不同的端点
                #     # 这里只是一个示例，实际可能需要调整
                #     balance = data.get("balance", "未知")
                #     return balance
                elif selected_provider == "OpenRouter":
                    balance = data['data']['total_credits']
                    return balance
            else:
                return "查询余额失败"
        except Exception as e:
            return f"查询余额异常: {str(e)}"
        
    def add_to_conversation_history(self, role, content):
        """添加消息到对话历史，并限制历史长度"""
        self.conversation_history.append({"role": role, "content": content})
        
        # 限制历史长度
        if len(self.conversation_history) > self.max_history :  
            # 保留最新的消息，移除最旧的消息
            self.conversation_history = self.conversation_history[-self.max_history:]

    def clean_json_string(self, raw_string: str) -> str:
        """
            清理来自LLM的、可能包含无效JSON格式的字符串。
            
            此函数按顺序修复两种常见的错误：
            
            1. (修复类型A): 修复在JSON键值对的值字符串之前插入的
            多余的、仅包含空格的字符串。
            - 错误示例: "timestamp": " "1:39:30.60"
            - 修正为:   "timestamp": "1:39:30.60"
            
            2. (修复类型B): 修复在单个字符串值内部被错误“切片”
            并用引号连接的片段。
            - 错误示例: "sentence": "不用锅子，直接"连袋子放进微波"炉就能..."
            - 修正为:   "sentence": "不用锅子，直接连袋子放进微波炉就能..."

            3. (修复类型C): 修复在数组或对象内部缺失逗号分隔符的情况。
            - 错误示例: {
                        "sentence": "你会一边说着好痛苦，一边说这能写成歌吗",
                        "relatedInputItems": [
                            {"timestamp": "0:13:19.34", "text": "これ曲にできるなとか言うの"}
                            {"timestamp": "0:13:21.34", "text": "そうでしょ"}
                        ]
                        },
            - 修正为:  
                        {
                        "sentence": "你会一边说着好痛苦，一边说这能写成歌吗",
                        "relatedInputItems": [
                            {"timestamp": "0:13:19.34", "text": "これ曲にできるなとか言うの"},
                            {"timestamp": "0:13:21.34", "text": "そうでしょ"}
                        ]
                        },            

            参数:
                raw_string: 模型返回的原始JSON参数字符串。
                
            返回:
                一个清理过的、更可能被 json.loads() 成功解析的字符串。
        """
            
        cleaned_string = raw_string
        
        # --- 修复类型A: (:\s*)"\s*" -> \1" ---
        # (:\s*)  - 捕获组1：匹配冒号(:)和它后面的所有空格(\s*)。
        # "\s*"   - 匹配一个字面的引号(")，后跟任意空格，再跟一个引号(")。
        #          这是我们要删除的“错误空字符串”。
        # r'\1"'  - 替换为捕获组1的内容(即": ")，再加上一个
        #          (属于正确值的)开引号(")。
        pattern_a = re.compile(r'(:\s*)"\s*"')
        cleaned_string = pattern_a.sub(r'\1"', cleaned_string)        
        # --- 修复类型B: "\s*" -> '' ---
        # "\s*"   - 匹配一个(错误的)结束引号(")，后跟任意空格(\s*)，
        #          再跟一个(错误的)开始引号(")。
        # ''      - 替换为空字符串，即将两个片段“缝合”在一起。
        #
        # 注意：此修复必须在 修复类型A 之后运行，以避免
        # 错误地将 "key": " "value" 修复为 "key": value (丢失引号)。
        pattern_b = re.compile(r'"\s*"')
        cleaned_string = pattern_b.sub('', cleaned_string)


        # --- 修复类型C: 缺失逗号分隔符 ---
        # 这个正则表达式匹配在对象或数组内部缺失逗号的情况。
        # 它查找一个闭括号(}或])后面紧跟着另一个开括号({或[)的模式，
        # 并在它们之间插入一个逗号。
        pattern_c = re.compile(r'([}\]])\s*([{\[])')
        cleaned_string = pattern_c.sub(r'\1,\2', cleaned_string)
        
        return cleaned_string

    #summary part    
    def start_segment_summary_analysis(self):
        """开始分段分析"""
        if not self.subtitle_file_var.get():
            messagebox.showerror("错误", "请先选择ASS文件")
            return
        
        if not self.current_api_key:
            messagebox.showerror("错误", "请先设置API密钥")
            return        
        
        # 检查API密钥状态
        success, message = self.ensure_api_key_ready()
        if not success and message != "用户取消解密":            
            messagebox.showerror("错误", f"API密钥准备失败: {message}")
            return    
        
        # 禁用按钮防止重复点击
        #self.start_segment_btn.config(state=tk.DISABLED)
        self.log_segment("开始分段分析...")
        self.save_config()
        # 启动后台线程
        
        if success:
            threading.Thread(target=self.run_segment_summary_analysis, daemon=True).start()
        elif message == "用户取消解密":
            self.log("用户取消解密，分段分析未启动")
            return
  
    def run_segment_summary_analysis(self):
        """执行分段分析"""
        try:
            ass_file_path = self.subtitle_file_var.get()
            time_window_minutes = int(self.time_window_var.get())
            
            # 解析ASS文件
            segments = self.parse_ass_file(ass_file_path)
            if not segments:
                self.root.after(0, lambda: self.log_segment("错误: 无法解析ASS文件或文件中没有对话内容"))
                return
            
            # 按时间窗口分段
            time_windows = self.segment_by_time_window(segments, time_window_minutes)
            self.log_segment(f"已将文件分为 {len(time_windows)} 个 {time_window_minutes} 分钟的时间段")
            
            # 清空之前的结果
            self.segment_results = []
            
            # 对每个时间段进行分析
            for i, window_segments in enumerate(time_windows):
                # 构建时间段文本
                window_text = self.build_window_text(window_segments)
                
                # 调用AI分析时间段总结
                analysis_result = self.analyze_segment_summary(window_text, window_segments)
                
                if analysis_result:
                    # 解析AI返回的结果
                    segment_summary = self.parse_analysis_result(analysis_result)
                    self.segment_results.append(segment_summary)
                    
                    # 在UI中显示结果（包含时间段编号信息）
                    self.root.after(0, lambda idx=i+1, summary=segment_summary: self.display_segment_results(idx, summary))
                else:
                    self.root.after(0, lambda idx=i+1: self.log_segment(f"第 {idx} 个时间段分析失败"))

            self.root.after(0, lambda: self.log_segment(f"分析完成！共分析了 {len(self.segment_results)} 个时间段"))
            subtitle_file = self.subtitle_file_var.get()
            base_name = os.path.splitext(os.path.basename(subtitle_file))[0]
            output_dir = os.path.dirname(subtitle_file)
            output_file = os.path.join(output_dir, f"{base_name}_segment_summary.txt") 
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"{base_name}时间段总结结果\n")
                f.write("=" * 50 + "\n\n")                
                for i, result in enumerate(self.segment_results, 1):
                    f.write(f"第{i}时间段: {result.get('start_time', '')} - {result.get('end_time', '')}\n")                    
                    formatted_summary_text = result.get('segment_summary', '').replace('，从', '，\n            从').replace('；从', '；\n            从').replace('。从', '。\n            从')
                    f.write(f"   总结: {formatted_summary_text}\n")
                    f.write(f"   话题描述: {result.get('topic_description', '')}\n")
                    f.write(f"   对话脉络: {result.get('conversation_flow', '')}\n")
                    f.write(f"   发言者分析: {result.get('speakers_analysis', '')}\n")
                    
                    # 导出关键点列表
                    key_points = result.get('key_points', [])
                    if key_points:
                        f.write("   关键点:\n")
                        for j, point in enumerate(key_points, 1):
                            f.write(f"     {j}. {point}\n")
                    
                    f.write(f"   情感基调: {result.get('emotional_tone', '')}\n\n")
                
                normalized_path = output_file.replace('/', '\\')
                self.log_segment(f"结果已导出到: {normalized_path}")
        except Exception as e:
            self.root.after(0, lambda: self.log_segment(f"分析过程中出错: {str(e)}"))
        # finally:
        #     self.root.after(0, lambda: self.start_segment_btn.config(state=tk.NORMAL))
    
    def parse_ass_file(self, file_path):
        """解析ASS文件，提取对话内容"""
        segments = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for line in lines:
                if line.startswith('Dialogue:'):
                    dialogue_data = self.parse_ass_dialogue(line)
                    if dialogue_data:
                        segments.append(dialogue_data)
            
            return segments
        except Exception as e:
            self.root.after(0, lambda: self.log_segment(f"解析ASS文件失败: {str(e)}"))
            return []
    
    def segment_by_time_window(self, segments, window_minutes):
        """按时间窗口分段"""
        if not segments:
            return []
        
        # 将分钟转换为秒
        window_seconds = window_minutes * 60
        
        # 获取第一个和最后一个时间戳
        first_start = self.ass_time_to_seconds(segments[0]['Start'])
        last_end = self.ass_time_to_seconds(segments[-1]['End'])
        
        # 计算总时长和分段数
        total_duration = last_end - first_start
        num_windows = int(total_duration // window_seconds) + 1
        
        windows = []
        for i in range(num_windows):
            window_start = first_start + i * window_seconds
            window_end = window_start + window_seconds
            
            # 收集在当前时间窗口内的对话
            window_segments = []
            for segment in segments:
                seg_start = self.ass_time_to_seconds(segment['Start'])
                seg_end = self.ass_time_to_seconds(segment['End'])
                
                # 如果对话与时间窗口有重叠
                if seg_end > window_start and seg_start < window_end:
                    window_segments.append(segment)
            
            if window_segments:
                windows.append(window_segments)
        
        return windows
    
    def ass_time_to_seconds(self, ass_time):
        """将ASS时间格式转换为秒数"""
        try:
            # ASS时间格式: h:mm:ss.cc
            parts = ass_time.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds_parts = parts[2].split('.')
            seconds = int(seconds_parts[0])
            centiseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
            
            total_seconds = hours * 3600 + minutes * 60 + seconds + centiseconds / 100
            return total_seconds
        except:
            return 0
    
    def build_window_text(self, segments):
        """构建时间窗口的文本内容"""
        text_lines = []
        for segment in segments:
            start_time = segment['Start']
            text = segment['Text']
            text_lines.append(f"[{start_time}] {text}")
        
        return "\n".join(text_lines)
    
    def analyze_segment_summary(self, window_text, window_segments):
        """调用AI分析时间段内容总结"""
        try:
            # 获取当前服务商配置
            selected_provider = self.provider_var.get()
            provider_config = self.providers.get(selected_provider, self.providers["DeepSeek"])
            api_url = provider_config["api_url"]
            ai_model = self.ai_model
            
            # 构建提示词
            system_prompt = self.get_segment_summary_prompt()
            
            # 计算时间段的开始和结束时间
            if window_segments:
                start_time = window_segments[0]['Start']
                end_time = window_segments[-1]['End']
            else:
                start_time = "00:00:00.00"
                end_time = "00:00:00.00"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"时间段内容:\n{window_text}\n\n请分析这个时间段的内容，以提供的JSON格式返回时间段总结。"}
            ]
            
            # 调用API
            client = OpenAI(api_key=self.current_api_key, base_url=api_url)
            if "gemini" in self.ai_model:
                response = client.chat.completions.create(
                    model=ai_model,
                    messages=messages, 
                    # reasoning_effort="medium",
                    response_format={"type": "json_object"},                    
                    temperature=0.7,                        
                    stream=False
                )
            else:
                response = client.chat.completions.create(
                    model=ai_model,
                    messages=messages, 
                    max_tokens=8192,                                           
                    temperature=0.7,
                    response_format={"type": "json_object"},
                    stream=False                
                )
            # 清理并解析json响应
            cleaned_string = self.clean_json_string(response.choices[0].message.content)
            function_args = json.loads(cleaned_string)
            
            # 返回完整的时间段总结结果
            return {
                "segment_summary": function_args.get("segment_summary", ""),
                "start_time": function_args.get("start_time", start_time),
                "end_time": function_args.get("end_time", end_time),
                "topic_description": function_args.get("topic_description", ""),
                "conversation_flow": function_args.get("conversation_flow", ""),
                "speakers_analysis": function_args.get("speakers_analysis", ""),
                "key_points": function_args.get("key_points", []),
                "emotional_tone": function_args.get("emotional_tone", "")        
            }
            
        except Exception as e:
            self.root.after(0, lambda: self.log_segment(f"AI分析失败: {str(e)}"))
            return None
    
    def get_segment_summary_prompt(self):
        """获取时间段总结的提示词"""
        return """你是一个专业的日语内容分析助手。请仔细阅读以下时间段内的日语对话内容，然后严格按照指定的JSON格式返回详细的时间段总结。

**分析要求：**
1. 仔细阅读整个时间段的对话内容，理解对话的完整脉络
2. 分析对话的主要话题和子话题，确保每个话题都顾及到，不能遗漏
3. 识别对话中的关键人物和他们的发言内容
4. 分析对话的转折点和重要观点
5. 总结对话的核心内容和关键信息

**输出格式要求：**
你必须严格按照以下JSON格式输出，不要添加任何额外的文本说明：

{
  "segment_summary": "从[开始时间]到[结束时间]聊的话题是[话题描述]，从[开始时间]到[结束时间]聊的话题是[话题描述]...",
  "start_time": "h:mm:ss.cc",
  "end_time": "h:mm:ss.cc",
  "topic_description": "详细的中文描述，包括主要话题和子话题的详细描述",
  "conversation_flow": "对话的脉络和转折点分析",
  "speakers_analysis": "各方人物的发言和观点分析",
  "key_points": ["关键点1", "关键点2", "关键点3"],
  "emotional_tone": "对话的情感基调或氛围分析"
}

**字段说明：**
- segment_summary: 用中文描述时间段和话题，严格按照指定格式
- start_time/end_time: 使用ASS时间格式 h:mm:ss.cc
- topic_description: 详细描述话题内容，包括各方意见
- conversation_flow: 分析对话的发展脉络和关键转折
- speakers_analysis: 分析各发言者的观点和立场
- key_points: 列出对话所有的关键信息点，个数没有要求，需要覆盖所有信息关键点
- emotional_tone: 描述对话的整体氛围和情感倾向

请确保输出内容详细、丰富，让用户能够清楚地了解这个时间段内发生了什么对话，谁说了什么，对话的关键点是什么。
"""
    
    def parse_analysis_result(self, analysis_result):
        """解析分析结果，返回完整的时间段总结"""
        if not analysis_result:
            return None
            
        # 确保所有必需字段都有默认值
        return {
            'segment_summary': analysis_result.get('segment_summary', ''),
            'start_time': analysis_result.get('start_time', ''),
            'end_time': analysis_result.get('end_time', ''),
            'topic_description': analysis_result.get('topic_description', ''),
            'conversation_flow': analysis_result.get('conversation_flow', ''),
            'speakers_analysis': analysis_result.get('speakers_analysis', ''),
            'key_points': analysis_result.get('key_points', []),
            'emotional_tone': analysis_result.get('emotional_tone', '')
        }
    
    def display_segment_results(self, window_index, segment_summary):
        """在UI中显示时间段总结结果"""
        if not segment_summary:
            return
            
        self.segment_result_text.insert(tk.END, f"\n=== 第 {window_index} 时间段 ===\n")
        self.segment_result_text.insert(tk.END, f"时间段: {segment_summary.get('start_time', '')} - {segment_summary.get('end_time', '')}\n")
        formatted_summary_text = segment_summary.get('segment_summary', '').replace('，从', '，\n        从').replace('；从', '；\n        从').replace('。从', '。\n        从')
        self.segment_result_text.insert(tk.END, f"总结: {formatted_summary_text}\n")
        self.segment_result_text.insert(tk.END, f"话题描述: {segment_summary.get('topic_description', '')}\n")
        self.segment_result_text.insert(tk.END, f"对话脉络: {segment_summary.get('conversation_flow', '')}\n")
        self.segment_result_text.insert(tk.END, f"发言者分析: {segment_summary.get('speakers_analysis', '')}\n")
        
        # 显示关键点列表
        key_points = segment_summary.get('key_points', [])
        if key_points:
            self.segment_result_text.insert(tk.END, "关键点:\n")
            for i, point in enumerate(key_points, 1):
                self.segment_result_text.insert(tk.END, f"  {i}. {point}\n")
        
        self.segment_result_text.insert(tk.END, f"情感基调: {segment_summary.get('emotional_tone', '')}\n")
        self.segment_result_text.insert(tk.END, "-" * 50 + "\n")
        
        self.segment_result_text.see(tk.END)

    #transcription part
    def start_transcription(self):
        if not self.input_file.get():
            messagebox.showerror("错误", "请先选择输入文件")
            return
        
        # 检查是否需要密码验证
        need_password = False
        if self.enable_ai_translation.get() or self.enable_segment_summary.get():
            need_password = True
        
        if need_password:
            # 检查API密钥状态，如果需要解密会弹出密码输入框
            success, message = self.ensure_api_key_ready()
            if not success:
                if message == "用户取消解密":
                    self.log("用户取消解密，任务未启动")
                    return
                else:
                    messagebox.showerror("错误", f"API密钥准备失败: {message}")
                    return
        
        self.start_btn.config(state=tk.DISABLED)
        self.log("听写任务开始...")
        self.save_preset()
        self.save_config()
        # 启动后台线程
        threading.Thread(target=self.run_transcription, daemon=True).start()
        
        # 启动进度更新检查
        self.root.after(100, self.check_progress)

    def run_transcription(self):
        try:
            model_path = self.model_path 

            # 加载模型
            if not self.model:
                self.model = WhisperModel(model_size_or_path=model_path)
            
            # 准备ASS字幕文件名和完成后输出地址
            file_path = self.input_file.get()
            base_name = os.path.splitext(os.path.basename(file_path))[0] 
            
            # 判断文件类型，视频还是音频
            streams = ffmpeg.probe(file_path).get('streams', [])
            file_type = None
            for stream in streams:
                codec_type = stream.get('codec_type', '')
                if codec_type == 'video':
                    file_type = "video"
                    break  # 找到视频流后退出循环
                else:
                    file_type = "audio"
            if file_type == "video": 
                temp_audio_path_undenoise = self.extract_audio(file_path)
                self.log("提取视频文件音频中...")
            elif file_type == "audio":
                temp_audio_path_undenoise = file_path
            
            # 定义增强后的音频文件路径
            enhanced_audio_path = f"{os.path.splitext(file_path)[0]}_enhanced.mp3"          
            self.log("语音增强处理中...")

            # 调用语音增强函数
            self.enhance_voice_comprehensive(temp_audio_path_undenoise, enhanced_audio_path)
            
            def update_transcription_progress(progress):
                self.progress_queue.put(("progress", progress))
            
            # 执行语音识别，传入进度回调
            self.progress_queue.put(("progress", 0))  # 开始转录
            self.log("语音识别模型加载中...")
            self.transcribe_audio_to_ass(enhanced_audio_path, base_name, file_path, 
                                    progress_callback=update_transcription_progress)
            torch.cuda.empty_cache()

            # 如果启用AI翻译，执行翻译
            if self.enable_ai_translation.get():
                # 不再需要调用 ensure_api_key_ready()，因为已经在 start_transcription 中验证过
                # 直接启动翻译线程
                self.log("API密钥准备就绪，开始翻译...")
                threading.Thread(target=self.run_batch_translation, daemon=True).start()

            if self.enable_segment_summary.get():
                # 同样，不再需要调用 ensure_api_key_ready()
                self.log("API密钥准备就绪，开始分段总结...")
                threading.Thread(target=self.run_segment_summary_analysis, daemon=True).start()

            self.progress_queue.put(("progress", 100))
            
            # 如果是视频文件，删除临时音频文件
            if file_type == "video":
                os.remove(temp_audio_path_undenoise)
            # 删除增强后的临时音频文件
            if os.path.exists(enhanced_audio_path):
                os.remove(enhanced_audio_path)
                
        except Exception as e:
            self.progress_queue.put(("error", str(e)))
        finally:            
            self.progress_queue.put(("reset_btn", None))

    def extract_audio(self, file_path):
        """提取音频"""
        temp_audio_path = f"{os.path.splitext(file_path)[0]}.mp3"
        try:
            (
                ffmpeg.input(file_path)
                .output(temp_audio_path, acodec='mp3', audio_bitrate='192k')
                .overwrite_output()
                .run(cmd=self.ffmpeg_exe_path, capture_stdout=True, capture_stderr=True) # 指定 ffmpeg 路径
            )
            return temp_audio_path
        except ffmpeg.Error as e:
            raise Exception(f"音频提取失败: {e.stderr.decode()}")

    def enhance_voice_comprehensive(self, input_file, output_file):
        """
        综合语音增强：降噪 + 低频切除 + 均衡器
        """
        filter_chain = (
            "afftdn=nf=-25,"
            "asubcut=cutoff=80,"
            "asupercut=cutoff=20000,"
            "equalizer=f=1000:width_type=h:width=2000:g=3"
        )        

        # 确保 output_file 的路径也使用正斜杠
        formatted_output_file = output_file.replace('\\', '/')
        
        cmd = [
            self.ffmpeg_exe_path, # 使用指定的 ffmpeg 路径
            '-i', input_file,
            '-af', filter_chain,
            '-y',
            formatted_output_file
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            
            return True
        except subprocess.CalledProcessError as e:
            print(f"错误: {e.stderr.decode()}")
            return output_file

    def create_ass_header(self):
        """创建ASS文件头部信息"""
        header = """[Script Info]
; Script generated by Aegisub 9212-dev-3a38bf16a
; http://www.aegisub.org/
Title: 
ScriptType: v4.00+
PlayDepth: 0
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: no
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: 原文,思源黑体 CN,70,&H00FFFFFF,&H000019FF,&H1E000000,&H9E000000,-1,0,0,0,100,100,1,0,1,3.5,0,2,6,6,10,1
Style: 对话,思源黑体 CN,70,&H00FFFFFF,&H000019FF,&H1E000000,&H9E000000,-1,0,0,0,100,100,1,0,1,3.5,0,2,6,6,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    
        return header

    def transcribe_audio_to_ass(self, audio_path, base_name, file_path, progress_callback=None):
        """
        使用Faster-Whisper转录音频并生成ASS字幕文件  
        """
        tic = time.time()
        origin_sub_file_name = base_name+'.ass'
        origin_sub_file_path = os.path.join(os.path.dirname(file_path), origin_sub_file_name)

        segments, info = self.model.transcribe(
            audio=audio_path,
            language= "ja" if self.language_combo.get() == "日语" else "en" if self.language_combo.get() == "英语" else "zh",

            beam_size=None if self.beam_size_off else self.set_beam_size,
            vad_filter=self.is_vad_filter,           
            vad_parameters=dict(
                min_silence_duration_ms=500,  # 核心参数，控制切分粒度
                speech_pad_ms=400,            # 保证词句完整
                threshold=0.4,                # 平衡敏感度，过滤背景音
                min_speech_duration_ms=250    # 过滤短噪音 
            )                 
        )        
        total_duration = round(info.duration, 2)  # Same precision as the Whisper timestamps.
        results= []
        processed_duration = 0

        with tqdm(total=total_duration, unit=" seconds", disable=True) as pbar:
            for s in segments:
                segment_dict = {
                    'start': s.start,
                    'end': s.end,
                    'text': s.text
                }
                results.append(segment_dict)
                segment_duration = s.end - s.start
                processed_duration += segment_duration

                if progress_callback:
                    current_progress = min(100, int((s.end / total_duration) * 100))
                    progress_callback(current_progress)

        toc = time.time()
        self.log(f"听写任务完成，耗时{round(toc-tic)}s")

        # 创建ASS文件
        ass_content = self.create_ass_header()
        
        #处理转录结果
        for seg in results:           
            start_s = float(seg['start'])
            end_s = float(seg['end'])
            text = seg['text'].strip()

            # 精确转换为 centisecond
            seg_start_cs = self.seconds_to_centiseconds(start_s)
            seg_end_cs = self.seconds_to_centiseconds(end_s)
            total_cs = max(seg_end_cs - seg_start_cs, 0)
            if total_cs == 0:
                total_cs = 1

            # 日语文本自动分行
            text_segments = self.segment_text_japanese(text)
            
            # 如果有多个文本段，创建多行字幕
            if len(text_segments) > 1:
                n = len(text_segments)
                base = total_cs // n
                remainder = total_cs % n  # 平均分配余数
                cur_cs = seg_start_cs
                
                for i, t in enumerate(text_segments):
                    #如果t内容为空那就直接不往ass_content添加内容
                    if not t.strip():
                        continue
                    this_dur = base + (1 if i < remainder else 0)
                    line_start_cs = cur_cs
                    line_end_cs = cur_cs + this_dur

                    start_time = self.centiseconds_to_ass_time(line_start_cs)
                    end_time = self.centiseconds_to_ass_time(line_end_cs)
                    ass_content += f"Dialogue: 0,{start_time},{end_time},原文,,0,0,0,,{t}\n"

                    cur_cs = line_end_cs
            else:
                #如果text_segments内容为空那就直接不往ass_content添加内容
                if text_segments and text_segments[0].strip():
                    start_time = self.centiseconds_to_ass_time(seg_start_cs)
                    end_time = self.centiseconds_to_ass_time(seg_end_cs)
                    ass_content += f"Dialogue: 0,{start_time},{end_time},原文,,0,0,0,,{text_segments[0]}\n"
        # 写入ASS文件
        with open(origin_sub_file_path, 'w', encoding='utf-8-sig') as f:
            f.write(ass_content)
        
        # 处理好的ASS文件地址放入全局变量，如果要AI翻译就直接读取地址 
        normalized_path = origin_sub_file_path.replace('/', '\\')
        self.subtitle_file_var.set(normalized_path)        
        self.log(f"已生成字幕文件: {normalized_path}")

    def seconds_to_centiseconds(self, seconds: float) -> int:
        """
        将秒数四舍五入到最近的 centisecond(0.01s)。
        例如 1.234 -> 123
        """
        return int(round(seconds * 100))

    def centiseconds_to_ass_time(self, cs: int) -> str:
        """
        把 centiseconds(整数)格式化为 ASS 时间 h:mm:ss.cc
        """
        hours = cs // 360000            # 3600s * 100
        minutes = (cs % 360000) // 6000 # 60s * 100
        seconds = (cs % 6000) // 100
        centis = cs % 100
        return f"{hours:d}:{minutes:02d}:{seconds:02d}.{centis:02d}"
    
    def segment_text_japanese(self, text): 
        """
        日语文本自动分行，基于句号、问号、感叹号
        """
        # 定义分行标点符号
        sentence_enders = ['。', '!', '?', '…',' ', '、', '，']
        
        segments = []
        current_segment = ""
        
        for char in text:
            current_segment += char
            
            # 如果遇到句末标点，立即分行
            if char in sentence_enders:
                segments.append(current_segment.strip())
                current_segment = ""
        
        # 添加最后一段（如果文本不是以句末标点结束）
        if current_segment.strip():
            segments.append(current_segment.strip())
        
        return segments

    def check_progress(self):
        """检查进度队列并更新UI"""
        try:
            while True:
                try:
                    item_type, value = self.progress_queue.get_nowait()
                    if item_type == "progress":
                        self.progress["value"] = value
                    elif item_type == "message":
                        self.log(value)
                    elif item_type == "error":
                        self.log(f"错误: {value}")
                        messagebox.showerror("错误", value)
                    elif item_type == "reset_btn":
                        self.start_btn.config(state=tk.NORMAL)
                except queue.Empty:
                    break
        except Exception as e:
            self.log(f"进度更新错误: {str(e)}")
        
        # 继续检查
        self.root.after(100, self.check_progress)

    # UI事件处理函数
    def center_window(self):
        """将窗口居中显示"""
        # 使用固定尺寸，避免在窗口隐藏时获取不正确的尺寸
        width = 1400
        height = 1400
        
        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 计算居中位置
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        
        # 设置窗口位置和尺寸
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def check_preset_if_modified(self):
        """检查预设参数是否被修改"""
        self.is_modified = False
        
        if self.current_preset in self.presets:
            preset_data = self.presets[self.current_preset]
            current_prompt = self.prompt_text.get("1.0", tk.END).strip()
            current_model = self.ai_model 
            current_temperature = float(self.temperature_scale.get())
            current_batch_size = self.batch_size_entry.get()
            
            # 检查是否有参数改变
            if (current_prompt != preset_data.get("system_prompt", "") or
                current_model != preset_data.get("ai_model", "") or
                current_temperature != preset_data.get("temperature", 1.3) or
                current_batch_size != preset_data.get("batch_size", 80)): # 默认值保持一致
                self.is_modified = True

        self.update_window_title()

    def update_window_title(self):
        """更新窗口标题"""
        if self.is_modified:
            self.root.title(f"Transby2(预设:*{self.current_preset})")
        else:
            self.root.title(f"Transby2(预设:{self.current_preset})")

    def set_window_icon(self):
        """设置窗口图标"""
        try:         
            icon_path = [
                "transby2.ico",  # 当前目录
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "transby2.ico"),  # 脚本所在目录
                os.path.join(self.libs_dir, 'transby2.ico') if self.libs_dir else None,  # PyInstaller临时目录
            ]           
            if icon_path:
                self.root.iconbitmap(icon_path[1])                
            else:
                self.log("警告: 图标文件 transby2.ico 不存在")
        except Exception as e:
            self.log(f"设置窗口图标时出错: {str(e)}")

    def update_markdown_preview(self, event=None):
        """更新Markdown预览区"""
        if self.prompt_text.edit_modified():
            md_text = self.prompt_text.get("1.0", tk.END)
            html_content = markdown.markdown(md_text, extensions=["fenced_code", "tables"])            
            self.markdown_preview.set_html(html_content)
            # 应用字体到渲染组件
            self.markdown_preview.config(font=self.preview_font)
            self.prompt_text.edit_modified(False)

    def update_temperature_label(self, value):
        """更新温度标签"""
        self.temperature_label.config(text=f"{float(value):.1f}")

    def on_language_change(self, event):
        """语言选择变更事件"""
        selected_language = self.language_combo.get()
        if selected_language == "日语":
            self.language = "ja"
        elif selected_language == "英语":
            self.language = "en"
        elif selected_language == "中文":
            self.language = "zh" 
        self.log(f"听写语言已设置为: {selected_language}")

    def on_ai_translation_toggle(self):
        """AI翻译勾选框切换事件"""
        if self.enable_ai_translation.get():
            self.log("AI翻译选项已启用")
        else:
            self.log("AI翻译未启用")

    def on_segment_summary_toggle(self):
        """AI分时段总结勾选框切换事件"""
        if self.enable_segment_summary.get():
            self.log("AI分时段总结选项已启用")
        else:
            self.log("AI分时段总结未启用")

    def on_VAD_toggle(self):
        """AI翻译勾选框切换事件"""
        if self.is_vad_filter.get():           
            self.log("VAD选项已启用")
        else:
            self.log("VAD翻译未选项启用")

    def show_api_key_dialog(self):
        """显示API密钥输入对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("API设置")
        dialog.geometry("500x200")
        
        # 将对话框居中显示在主窗口
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 计算居中位置
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (500 // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (200 // 2)
        dialog.geometry(f"500x350+{x}+{y}")
        
        ttk.Label(dialog, text="请在下方输入您的API秘钥").pack(pady=10)        
        ttk.Label(dialog, text="API密钥:").pack()        
        api_entry = ttk.Entry(dialog, width=40)
        api_entry.pack(pady=5)
        
        ttk.Label(dialog, text="加密密码（用于保护API密钥）:").pack()
        password_entry = ttk.Entry(dialog, width=40)
        password_entry.pack(pady=5)
        
        def save_and_close():
            api_key = api_entry.get().strip()
            password = password_entry.get().strip()
            
            if api_key and password:
                try:
                    # 加密API密钥
                    encrypted_api_key = self.crypto.encrypt_data(api_key, password)
                    # 保存到对应服务商的字典中
                    current_provider = self.provider_var.get()
                    self.api_keys[current_provider] = encrypted_api_key
                    self.current_api_key = encrypted_api_key
                    self.api_key_entry.delete(0, tk.END)
                    self.api_key_entry.insert(0, "***已加密***")
                    self.save_config()
                    dialog.destroy()
                    self.log(f"{current_provider} API密钥已加密保存")
                except Exception as e:
                    messagebox.showerror("错误", f"加密失败: {str(e)}")
            else:
                messagebox.showwarning("警告", "请输入有效的API密钥和密码")
        
        ttk.Button(dialog, text="保存", command=save_and_close).pack(pady=5)
        
        # 确保对话框在显示前已经完成布局计算
        dialog.update_idletasks()

    def ensure_api_key_ready(self):
        """确保API密钥已准备就绪，如果需要解密则处理解密流程"""
        # 检查缓存状态
        cache_key = f"{self.provider_var.get()}_{self.current_api_key}"
        if cache_key in self.api_key_status_cache:
            cached_result = self.api_key_status_cache[cache_key]
            # 如果是用户取消的结果，不直接返回，重新尝试解密
            if cached_result[0] is False and "用户取消解密" in cached_result[1]:
                # 清除这个缓存条目，重新尝试
                del self.api_key_status_cache[cache_key]
            else:
                return cached_result
        
        is_valid, message = self.check_api_key_status()
        
        if is_valid:
            result = (True, "API密钥已准备就绪")
            self.api_key_status_cache[cache_key] = result
            return result
        
        # 如果需要解密，在主线程中处理
        if message == "API密钥需要解密":
            success, decrypt_message = self.decrypt_api_key_in_main_thread()
            
            # 如果是用户取消，不缓存失败结果
            if not success and "用户取消解密" in decrypt_message:
                return (False, decrypt_message)  # 不缓存，直接返回
            
            if not success:
                result = (False, f"API密钥解密失败: {decrypt_message}")
                self.api_key_status_cache[cache_key] = result
                return (False, decrypt_message)
            
            # 解密成功后重新检查API密钥状态
            is_valid, message = self.check_api_key_status()
            
            if not is_valid:
                result = (False, f"API密钥验证失败: {message}")
                self.api_key_status_cache[cache_key] = result
                return result
            
            result = (True, "API密钥已解密并验证成功")
            self.api_key_status_cache[cache_key] = result
            return result
        
        result = (False, message)
        # 只有非用户取消的失败才缓存
        if "用户取消" not in message:
            self.api_key_status_cache[cache_key] = result
        return result
    
    def decrypt_api_key_in_main_thread(self):
        """在主线程中解密API密钥，支持密码错误时重新输入"""
        if not self.current_api_key or not self.crypto.is_encrypted(self.current_api_key):
            return True, "无需解密"

        max_attempts = 5  # 最大重试次数
        attempts = 0
        
        while attempts < max_attempts:
            # 创建自定义对话框来居中显示
            dialog = tk.Toplevel(self.root)
            dialog.title("解密密码")
            dialog.geometry("400x150")
            
            # 将对话框居中显示在主窗口
            dialog.transient(self.root)
            dialog.grab_set()
            
            # 计算居中位置
            dialog.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (400 // 2)
            y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (150 // 2)
            dialog.geometry(f"400x150+{x}+{y}")
            
            # 创建对话框内容
            ttk.Label(dialog, text=f"请输入解密密码 (剩余尝试次数: {max_attempts - attempts}):").pack(pady=10)
            password_entry = ttk.Entry(dialog, width=40, show="*")
            password_entry.pack(pady=5)
            password_entry.focus_set()
            
            password = None
            confirmed = False
            
            def on_ok():
                nonlocal password, confirmed
                password = password_entry.get().strip()
                confirmed = True
                dialog.destroy()
            
            def on_cancel():
                nonlocal password, confirmed
                password = None
                confirmed = True
                dialog.destroy()
            
            button_frame = ttk.Frame(dialog)
            button_frame.pack(pady=10)
            
            ttk.Button(button_frame, text="确定", command=on_ok).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)
            
            # 绑定回车键
            dialog.bind('<Return>', lambda e: on_ok())
            
            # 确保对话框在显示前已经完成布局计算
            dialog.update_idletasks()
            
            # 等待对话框关闭
            self.root.wait_window(dialog)
            
            # 用户点击取消或关闭对话框
            if not confirmed or password is None:
                return False, "用户取消解密"
            
            # 用户未输入密码
            if not password:
                messagebox.showwarning("警告", "请输入解密密码")
                continue  # 不计数，继续要求输入
            
            attempts += 1
            
            try:
                # 尝试解密
                self.current_api_key = self.crypto.decrypt_data(self.current_api_key, password)
                self.log("API密钥已成功解密")
                
                # 更新UI显示
                self.api_key_entry.delete(0, tk.END)
                self.api_key_entry.insert(0, "***已加密***")
                self.save_config()
                
                return True, "API密钥解密成功"
                
            except Exception as e:
                # 解密失败
                if attempts < max_attempts:
                    error_msg = f"密码错误或解密失败 (第{attempts}次尝试)\n\n请重新输入密码"
                    messagebox.showerror("解密失败", error_msg)
                else:
                    # 达到最大尝试次数
                    error_msg = f"密码错误次数过多，已达到最大尝试次数({max_attempts}次)"
                    messagebox.showerror("解密失败", error_msg)
                    return False, error_msg
        
        return False, "解密过程异常结束"

    def check_api_key_status(self):
        """检查API密钥状态，如果需要解密则返回需要解密的状态"""
        if not self.current_api_key:
            return False, "未设置API密钥"
        
        if self.current_api_key == "***已加密***":
            return False, "API密钥已加密但未解密"
        
        # 检查是否需要解密
        if self.crypto.is_encrypted(self.current_api_key):
            return False, "API密钥需要解密"
        
        # 验证API密钥有效性
        try:
            if self.validate_api_key(self.current_api_key):
                return True, "API密钥验证成功"
            else:
                return False, "API密钥验证失败"
        except Exception as e:
            return False, f"API密钥验证过程中发生错误: {str(e)}"

    def validate_api_key(self, api_key):
        """验证API密钥有效性"""
        current_provider = self.provider_var.get()
        provider_config = self.providers.get(current_provider, self.providers["DeepSeek"])
        api_url = provider_config["api_url"]  
       
        try:
            client = OpenAI(api_key=api_key, base_url=api_url)
            models = client.models.list()
            
            if models and len(list(models)) > 0:
                self.log(f"{current_provider} API密钥验证成功")
                return True
            else:
                # 根据错误代码提供自然语言提示               
                self.log(f"{current_provider} API密钥验证失败，无法获取模型列表")
                return False
            
        except AuthenticationError:
            self.log(f"{current_provider} API密钥无效或已过期")
            return False
        except RateLimitError:
            self.log(f"{current_provider} API密钥有效但已达到速率限制")
            return False
        except Exception as e:
            self.log(f"{current_provider} API验证过程中发生错误: {str(e)}")
            return False
    
    def get_api_error_message(self, error_code, response_text, provider):
        """根据错误代码和服务商返回自然语言错误提示"""
        try:
            error_data = json.loads(response_text)
            # 根据不同服务商的错误响应格式提取错误信息
            if provider == "Gemini":
                error_detail = error_data.get('error', {}).get('message', '未知错误')
            else:
                error_detail = error_data.get('error', {}).get('message', '未知错误')
        except:
            error_detail = response_text
        
        # 通用错误消息
        base_error_messages = {
            400: f"请求参数错误: {error_detail}",
            401: "API密钥无效或已过期，请检查密钥是否正确",
            403: "API密钥权限不足，请检查密钥权限",
            404: "API端点不存在，请检查API地址",
            429: "请求频率过高，请稍后重试",
            500: "服务器内部错误，请稍后重试",
            502: "网关错误，请稍后重试",
            503: "服务暂时不可用，请稍后重试",
            504: "网关超时，请稍后重试"
        }
        
        # 服务商特定的错误消息
        provider_specific_messages = {
            "DeepSeek": {
                400: f"DeepSeek API请求参数错误: {error_detail}",
                401: "DeepSeek API密钥无效，请检查密钥是否正确",
                403: "DeepSeek API密钥权限不足或余额不足",
                429: "DeepSeek API请求频率限制，请稍后重试",
                500: "DeepSeek服务器内部错误，请稍后重试"
            },
            "OpenAI": {
                400: f"OpenAI API请求参数错误: {error_detail}",
                401: "OpenAI API密钥无效或已过期，请检查密钥是否正确",
                403: "OpenAI API密钥权限不足或额度已用完",
                429: "OpenAI API请求频率限制，请稍后重试",
                500: "OpenAI服务器内部错误，请稍后重试"
            },
            "Gemini": {
                400: f"Gemini API请求参数错误: {error_detail}",
                401: "Gemini API密钥无效，请检查密钥是否正确",
                403: "Gemini API密钥权限不足或配额已用完",
                429: "Gemini API请求频率限制，请稍后重试",
                500: "Gemini服务器内部错误，请稍后重试"
            }
        }
        
        # 优先使用服务商特定的错误消息，如果没有则使用通用消息
        provider_errors = provider_specific_messages.get(provider, {})
        if error_code in provider_errors:
            return provider_errors[error_code]
        else:
            return base_error_messages.get(error_code, f"{provider} API未知错误 (代码: {error_code}): {error_detail}")
    
    def save_api_key(self):
        """保存API密钥"""
        api_key = self.api_key_entry.get().strip()
        if api_key:
            # 如果API密钥不是已加密的标记，则要求输入密码进行加密
            if api_key != "***已加密***":
                # 创建自定义对话框来居中显示
                dialog = tk.Toplevel(self.root)
                dialog.title("加密密码")
                dialog.geometry("400x150")
                
                # 将对话框居中显示在主窗口
                dialog.transient(self.root)
                dialog.grab_set()
                
                # 计算居中位置
                dialog.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (400 // 2)
                y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (150 // 2)
                dialog.geometry(f"400x150+{x}+{y}")
                
                # 创建对话框内容
                ttk.Label(dialog, text="请输入加密密码:").pack(pady=10)
                password_entry = ttk.Entry(dialog, width=40, show="*")
                password_entry.pack(pady=5)
                password_entry.focus_set()
                
                password = None
                confirmed = False
                
                def on_ok():
                    nonlocal password, confirmed
                    password = password_entry.get().strip()
                    confirmed = True
                    dialog.destroy()
                
                def on_cancel():
                    nonlocal password, confirmed
                    password = None
                    confirmed = True
                    dialog.destroy()
                
                button_frame = ttk.Frame(dialog)
                button_frame.pack(pady=10)
                
                ttk.Button(button_frame, text="确定", command=on_ok).pack(side=tk.LEFT, padx=5)
                ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)
                
                # 绑定回车键
                dialog.bind('<Return>', lambda e: on_ok())
                
                # 确保对话框在显示前已经完成布局计算
                dialog.update_idletasks()
                
                # 等待对话框关闭
                self.root.wait_window(dialog)
                
                # 用户点击取消或关闭对话框
                if not confirmed or password is None:
                    return
                
                # 用户未输入密码
                if not password:
                    messagebox.showwarning("警告", "请输入加密密码")
                    return
                
                try:
                    # 先验证API密钥有效性
                    self.log("正在验证API密钥...")
                    if self.validate_api_key(api_key):
                        encrypted_api_key = self.crypto.encrypt_data(api_key, password)
                        # 保存到对应服务商的字典中
                        current_provider = self.provider_var.get()
                        self.api_keys[current_provider] = encrypted_api_key
                        self.current_api_key = encrypted_api_key
                        self.api_key_entry.delete(0, tk.END)
                        self.api_key_entry.insert(0, "***已加密***")
                        self.save_config()
                        self.log(f"{current_provider} API密钥验证成功并已加密保存")
                    else:
                        self.log("API密钥验证失败，请检查密钥是否正确")
                except Exception as e:
                    messagebox.showerror("错误", f"加密失败: {str(e)}")

    def update_provider_menu(self):
        """更新服务商下拉菜单"""
        if self.provider_menu:
            self.provider_menu.delete(0, tk.END)
            
            # 添加所有服务商选项
            for provider_name in self.providers.keys():
                display_name = f"{provider_name}" if provider_name == self.provider_var.get() else provider_name
                self.provider_menu.add_command(
                    label=display_name,
                    command=lambda name=provider_name: self.select_provider(name)
                )
            
            # 更新按钮文本
            self.provider_button.config(text=self.provider_var.get())

    def update_model_menu(self):
        """更新模型下拉菜单"""
        if self.model_menu:
            self.model_menu.delete(0, tk.END)
            
            # 获取当前服务商的模型选项
            selected_provider = self.provider_var.get()
            provider_config = self.providers.get(selected_provider, self.providers["DeepSeek"])
            model_options = provider_config["model_options"]
            
            # 添加所有模型选项
            for model_name in model_options:
                display_name = f"{model_name}" if model_name == self.ai_model else model_name
                self.model_menu.add_command(
                    label=display_name,
                    command=lambda name=model_name: self.select_model(name)
                )
            
            # 更新按钮文本
            self.model_button.config(text=self.ai_model)

    def select_provider(self, provider_name):
        """选择服务商"""
        if provider_name in self.providers:
            self.provider_var.set(provider_name)
            provider_config = self.providers[provider_name]
            
            # 更新服务商按钮文本
            self.provider_button.config(text=provider_name)
            
            # 自动选择该服务商的第一个模型
            if provider_config["model_options"]:
                self.ai_model = provider_config["model_options"][0]                
                self.model_button.config(text=self.ai_model)
            
            # 更新模型菜单
            self.update_model_menu()
            
            # 加载该服务商的API密钥
            self.current_api_key = self.api_keys.get(provider_name, "")
            
            # 更新UI显示
            self.api_key_entry.delete(0, tk.END)
            if self.current_api_key and self.current_api_key != "***已加密***":
                self.api_key_entry.insert(0, "***已加密***")
            else:
                self.api_key_entry.insert(0, self.current_api_key)
            
            # 立即更新菜单显示选中状态
            self.update_provider_menu()
        
        # 检查预设是否被修改
        self.check_preset_if_modified()

    def select_model(self, model_name):
        """选择模型"""
        self.ai_model = model_name
        # 更新模型按钮文本
        self.model_button.config(text=model_name)
        # 立即更新菜单显示选中状态
        self.update_model_menu()
        # 检查预设是否被修改
        self.check_preset_if_modified()

    def load_config(self):
        """加载配置文件"""
        config_file = "transby2_config.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 加载模型路径
                    self.model_path = config.get('model_path', '')
                    self.model_path_var.set(self.model_path)
                    
                    # 加载AI翻译设置
                    self.enable_ai_translation.set(config.get('enable_ai_translation', False))
                    self.enable_segment_summary.set(config.get('enable_segment_summary', False))

                    # 加载服务商设置
                    self.provider_var.set(config.get('provider', 'DeepSeek'))
                    
                    # 加载API密钥字典
                    self.api_keys = config.get('api_keys', {})
                    
                    # 设置当前API密钥
                    current_provider = self.provider_var.get()
                    self.current_api_key = self.api_keys.get(current_provider, "")
                    
                    self.ai_model = config.get('ai_model', 'deepseek-chat')
                    self.temperature = config.get('temperature', 1.3)
                    self.system_prompt = config.get('system_prompt', '你是一个专业的翻译助手，请将以下日文字幕翻译成中文，保持原有的格式和结构。')                    

                    # 加载预设信息
                    self.presets = config.get('presets', {})
                    self.current_preset = config.get('current_preset')
                    self.batch_size = config.get('batch_size', 80)  # 从配置文件加载，如果不存在则默认80
                    
                    # 更新预设菜单
                    self.update_preset_menu()

                    # 加载providers配置
                    self.providers = config.get('providers')

                    # 更新UI
                    self.api_key_entry.delete(0, tk.END)
                    if self.current_api_key and self.current_api_key != "***已加密***":
                        self.api_key_entry.insert(0, "***已加密***")
                    else:
                        self.api_key_entry.insert(0, self.current_api_key)
                    
                    # 更新服务商选择
                    self.update_provider_menu()

                    # 更新模型菜单
                    self.update_model_menu()
                                      
                    self.update_batch_size_label(self.batch_size)

                    # 刷新温度滑块和标签
                    self.temperature_scale.set(self.temperature)
                    self.temperature_label.config(text=f"{self.temperature:.1f}")

                    # 刷新系统提示文本框
                    self.prompt_text.delete("1.0", tk.END)
                    self.prompt_text.insert("1.0", self.system_prompt)
                    
                    # 刷新Markdown预览
                    self.update_markdown_preview()                     
                    
                    # 刷新批处理大小显示
                    self.batch_size_entry.delete(0, tk.END)
                    self.batch_size_entry.insert(0, str(self.batch_size))

                    if self.enable_ai_translation.get():
                        self.log("AI翻译选项已启用")
                    if self.enable_segment_summary.get():
                        self.log("AI总结选项已启用")
                        
            except Exception as e:
                self.log(f"加载配置失败: {str(e)}")
                self.model_path = ""

    def save_config(self):
        """保存配置文件"""
        config_file = "transby2_config.json"
        try:
            config = {
                'model_path': self.model_path,
                'enable_ai_translation': self.enable_ai_translation.get(),
                'enable_segment_summary': self.enable_segment_summary.get(),
                'api_keys': self.api_keys,  # 保存所有服务商的API密钥
                'ai_model': self.ai_model,
                'temperature': self.temperature,
                'system_prompt': self.system_prompt,                
                'current_preset': self.current_preset,
                'provider': self.provider_var.get(),
                'batch_size': self.batch_size,
                'presets': self.presets,
                'providers': self.providers  # 保存服务商配置
            }
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)           
        except Exception as e:
            self.log(f"保存配置失败: {str(e)}")

    def browse_media_file(self):
        file_path = filedialog.askopenfilename(
            title="选择媒体文件",
            filetypes=[("媒体文件", "*.mp4 *.avi *.mkv *.ts *.mp3 *.wav *.aac *.m4a"), ("所有文件", "*.*")]
        )

        if file_path:
            self.input_file.set(file_path)
            self.output_dir.set(os.path.dirname(file_path))            
            normalized_path = file_path.replace('/', '\\')
            self.log(f"已选择文件: {normalized_path}")            

    def browse_model_folder(self):
        """选择模型文件夹"""
        folder_path = filedialog.askdirectory(title="选择模型文件夹")
        if folder_path:
            self.model_path = folder_path
            self.model_path_var.set(folder_path)
            self.save_config()
            normalized_path = folder_path.replace('/', '\\')
            self.log(f"已选择模型文件夹: {normalized_path}")
            self.model = None

    def log(self, message):
        """听写选项卡的日志输出"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def log_segment(self, message):
        """时间段总结选项卡的日志输出"""
        self.segment_result_text.insert(tk.END, message + "\n")
        self.segment_result_text.see(tk.END)

    def log_download(self, message):
        """下载工具的日志输出"""
        self.root.after(0, lambda: self._append_download_log_text_ui(message)) # 直接追加消息

    # 预设管理功能
    def update_preset_menu(self):
        """更新预设菜单"""
        # 更新预设菜单前检查当前预设参数是否已保存   
        # 更新窗口标题
        
        if self.preset_menu:
            self.preset_menu.delete(0, tk.END)
            
            # 添加预设管理选项（按照用户要求的顺序）
            self.preset_menu.add_command(label="新建", command=self.create_preset)
            self.preset_menu.add_command(label="重命名", command=self.rename_preset)
            self.preset_menu.add_command(label="删除当前预设", command=self.delete_preset)
            self.preset_menu.add_command(label="导出预设集", command=self.export_presets)
            self.preset_menu.add_command(label="导入预设集", command=self.import_presets) 

            # 添加分隔线
            self.preset_menu.add_separator()
            
            # 添加预设列表，按顺序显示所有预设
            if self.presets:
                # 按预设名称排序
                sorted_preset_names = sorted(self.presets.keys())
                
                for preset_name in sorted_preset_names:
                    # 如果是当前预设，添加选中标记
                    display_name = f"{preset_name}" if preset_name == self.current_preset else preset_name
                    
                    self.preset_menu.add_command(
                        label=display_name, 
                        command=lambda name=preset_name: self.select_preset(name)
                    )
            else:
                # 如果没有预设，显示默认选项
                self.preset_menu.add_command(
                    label="Default",
                    command=lambda: self.select_preset("Default")
                )

            # 更新按钮文本
            self.preset_button.config(text=self.current_preset)

        # 更新窗口标题
        self.root.title(f"Transby2(预设:{self.current_preset})")

    def update_batch_size_label(self, batch_size_var):
        """更新批处理大小输入框的显示"""   

        self.batch_size_entry.delete(0, tk.END)
        self.batch_size_entry.insert(0, str(batch_size_var))

    def create_preset(self):
        """创建新预设"""
        preset_name = tk.simpledialog.askstring("创建预设", "请输入预设名称:")
        if preset_name:
            if preset_name in self.presets:
                messagebox.showwarning("警告", f"预设 '{preset_name}' 已存在")
                return
            
            # 创建新预设
            self.presets[preset_name] = {
                'ai_model': self.ai_model,
                'temperature': self.temperature,
                'system_prompt': self.system_prompt,
                'provider': self.provider_var.get(),
                'batch_size': self.batch_size # 保存batch_size
            }
            
            self.current_preset = preset_name
            self.update_preset_menu()
            self.save_preset()
            self.log(f"已创建预设: {preset_name}")
        else:
            messagebox.showwarning("警告", "预设名称不能为空")
            return
        
    def rename_preset(self):
        """重命名预设"""
        if not self.presets:
            messagebox.showwarning("警告", "没有可重命名的预设")
            return
        
        old_name = self.current_preset        
        new_name = tk.simpledialog.askstring("  ", "请输入新的预设名称:")       
        if new_name in self.presets:
            messagebox.showwarning("警告", f"预设 '{new_name}' 已存在")
            return
        else:
            # 重命名预设
            self.presets[new_name] = self.presets.pop(old_name)
            
            # 更新当前预设            
            self.current_preset = new_name            
            self.update_preset_menu()
            self.save_preset()
            self.log(f"已将预设 '{old_name}' 重命名为 '{new_name}'")

    def delete_preset(self):
        """删除预设"""
        if not self.presets:
            messagebox.showwarning("警告", "没有可删除的预设")
            return
        
        preset_name = self.current_preset
        if preset_name and preset_name in self.presets:
            if len(self.presets) == 1:
                messagebox.showwarning("警告", "不能删除唯一预设")
                return
            
            if messagebox.askyesno("确认删除", f"确定要删除预设 '{preset_name}' 吗？"):
                # 删除预设
                del self.presets[preset_name]
                self.log(f"已删除预设: {preset_name}")
                # 更新当前预设和UI  
                self.current_preset = list(self.presets.keys())[0]
                preset_name = self.current_preset
                preset = self.presets[preset_name]
                self.ai_model = preset['ai_model']
                self.temperature = preset['temperature']
                self.system_prompt = preset['system_prompt']
                self.provider_var.set(preset['provider'])
                self.batch_size = preset.get('batch_size', 80) # 从新的当前预设加载batch_size
                self.current_preset = preset_name
                
            # 更新UI
            self.model_button.config(text=self.ai_model)
            self.temperature_scale.set(self.temperature)
            self.temperature_label.config(text=f"{self.temperature:.1f}")
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert("1.0", self.system_prompt)
            self.batch_size_entry.delete(0, tk.END)
            self.batch_size_entry.insert(0, str(self.batch_size))
            
            # 更新服务商选择
            self.provider_button.config(text=self.provider_var.get())            

            selected_provider = self.provider_var.get()
            if selected_provider in self.providers:
                self.update_model_menu()
            
            self.update_window_title()
            self.update_preset_menu()
            self.save_preset()          
                
        else:
            messagebox.showwarning("警告", f"预设 '{preset_name}' 不存在")

    def select_preset(self, preset_name):
        """选择预设"""
        if preset_name in self.presets:
            preset = self.presets[preset_name]
            
            # 检查当前预设是否有未保存的修改
            if self.is_modified:
                # 弹出确认对话框
                result = messagebox.askyesnocancel(
                    "未保存的修改", 
                    f"当前预设 '{self.current_preset}' 有未保存的修改。\n\n是否保存当前预设？\n\n是：保存当前预设并切换到 '{preset_name}'\n否：不保存修改，直接切换到 '{preset_name}'"
                )
                
                if result is None:  # 取消
                    return
                elif result:  # 是 - 保存当前预设
                    self.save_preset()
                    # 保存后立即重置修改标记，避免在切换预设时再次触发确认对话框
                    self.is_modified = False                    
                else:  # 否 - 不保存修改
                    self.log(f"已切换到预设 '{preset_name}'（未保存当前修改）")
            
            # 应用新预设的配置
            self.ai_model = preset['ai_model']
            self.temperature = preset['temperature']
            self.system_prompt = preset['system_prompt']
            self.provider_var.set(preset['provider'])
            self.batch_size = preset.get('batch_size', 80) # 从预设加载batch_size，如果不存在则默认80
            self.current_preset = preset_name
            
            # 更新UI
            self.model_button.config(text=self.ai_model)
            self.temperature_scale.set(self.temperature)
            self.temperature_label.config(text=f"{self.temperature:.1f}")
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert("1.0", self.system_prompt)
            self.batch_size_entry.delete(0, tk.END)
            self.batch_size_entry.insert(0, str(self.batch_size))
            
            # 更新服务商选择
            self.provider_button.config(text=self.provider_var.get())
            selected_provider = self.provider_var.get()
            if selected_provider in self.providers:
                self.update_model_menu()      

            self.is_modified = False
            
            # 更新窗口标题和预设菜单
            self.update_window_title()
            self.update_preset_menu()
            self.save_config()

    def export_presets(self):
        """导出预设集"""
        if not self.presets:
            messagebox.showwarning("警告", "没有预设可导出")
            return
        
        # 生成文件名
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d%H%M")
        filename = f"presets_{timestamp}.json"
        
        # 选择保存位置
        file_path = filedialog.asksaveasfilename(
            title="导出预设集",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")],
            initialfile=filename
        )
        
        if file_path:
            try:
                # 只导出预设信息
                export_data = {
                    "presets": self.presets
                }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                
                self.log(f"预设集已导出到: {file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {str(e)}")

    def import_presets(self):
        """导入预设集"""
        file_path = filedialog.askopenfilename(
            title="导入预设集",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    import_data = json.load(f)
                
                imported_presets = import_data.get("presets", {})
                
                if not imported_presets:
                    messagebox.showwarning("警告", "导入的文件中没有预设数据")
                    return
                
                # 合并预设，处理重名
                for preset_name, preset_data in imported_presets.items():
                    new_name = preset_name
                    counter = 1
                    
                    # 处理重名
                    while new_name in self.presets:
                        new_name = f"{preset_name}{counter}"
                        counter += 1
                    
                    self.presets[new_name] = preset_data                
                
                self.log(f"已导入预设集，共 {len(imported_presets)} 个预设")
                self.save_preset()
            except Exception as e:
                messagebox.showerror("错误", f"导入失败: {str(e)}")

    def save_preset(self):
        """保存当前预设"""
        if not self.current_preset:
            messagebox.showwarning("警告", "请先选择或创建一个预设")
            return
        
        # 获取当前系统提示词 模型 温度
        current_prompt = self.prompt_text.get("1.0", tk.END).strip()
        current_model = self.ai_model  # 直接使用self.ai_model变量
        current_temperature = round(float(self.temperature_scale.get()), 1)  # 只保留一位小数
        current_batch_size = self.batch_size_entry.get() 

        # 保存预设信息
        self.presets[self.current_preset] = {
            "system_prompt": current_prompt,
            "ai_model": current_model,
            "temperature": current_temperature,
            'provider': self.provider_var.get(),
            'batch_size': current_batch_size 
        }
        
        # 更新当前实例的配置
        self.system_prompt = current_prompt
        self.ai_model = current_model
        self.temperature = current_temperature

        # 重置修改标记
        self.is_modified = False

        # 保存到config文件
        self.save_config()
        
        # 更新预设组合框
        self.update_preset_menu()
        self.root.title(f"Transby2(预设:{self.current_preset})")

    def force_update_all_tabs(self):
        """强制更新所有选项卡的UI布局，确保按钮立即渲染"""
        # 更新主窗口
        self.root.update_idletasks()
        
        # 更新所有选项卡框架
        for frame in [self.transcription_frame, self.ai_translation_frame, 
                     self.segment_summary_frame, self.common_tools_frame]:
            if frame:
                frame.update_idletasks()
                
        # 强制刷新所有按钮
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Button) or isinstance(widget, tk.Button):
                widget.update_idletasks()

def main():
    """主程序入口"""
    root = tk.Tk()
    app = TranscriptionApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
