# encoding:utf-8
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import os
import torch
from faster_whisper import WhisperModel
import pysubs2
from tqdm import tqdm
from srt2ass import srt2ass
import ffmpeg
import sys
import json
import requests
import time
from crypto_utils import CryptoUtils

class TranscriptionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("语音字幕生成器(预设:Default)")
        self.root.geometry("1280x720")
        
        # 文件路径变量
        self.input_file = tk.StringVar()
        self.output_dir = tk.StringVar()
        
        # 模型参数
        self.model_size = "large-v2"
        self.language = "ja"
        self.is_split = "No"
        self.split_method = "Punctuation"
        self.is_vad_filter = False
        self.set_beam_size = 5
        self.beam_size_off = False
        
        # 预设管理
        self.presets = {}
        self.current_preset = "Default"
        self.preset_menu = None
        self.preset_combo = None
        
        # 模型路径变量
        self.model_path_var = tk.StringVar()
        self.model_path = ""
        
        # AI翻译配置
        self.enable_ai_translation = tk.BooleanVar(value=False)
        self.api_key = ""
        self.ai_model = "deepseek-reasoner"
        self.temperature = 1.3
        self.system_prompt = "你是一个专业的翻译助手，请将以下日文字幕翻译成中文，保持原有的格式和结构。"
        
        # 加密工具
        self.crypto = CryptoUtils()
        
        # 创建选项卡
        self.create_notebook()
        
        # 创建UI组件
        self.create_transcription_widgets()
        self.create_ai_translation_widgets()
        
        # 加载配置
        self.load_config()
        self.update_preset_menu()         
   
        # 进度队列
        self.progress_queue = queue.Queue()
        
        # 初始化模型（在实际使用时可改为按需加载）
        self.model = None

    def create_notebook(self):
        """创建选项卡界面"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 转写选项卡
        self.transcription_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.transcription_frame, text='转写')
        
        # AI翻译选项卡
        self.ai_translation_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.ai_translation_frame, text='翻译')

    def create_transcription_widgets(self):
        """创建转写选项卡的UI组件"""
        # 模型选择框架（最上一行）
        model_frame = ttk.LabelFrame(self.transcription_frame, text="模型选择")
        model_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Button(model_frame, text="选择模型文件夹", command=self.browse_model_folder).grid(row=0, column=0, padx=5)
        ttk.Label(model_frame, textvariable=self.model_path_var, width=50).grid(row=0, column=1, padx=5, sticky="w")
        
        # 听写语言选择框架
        language_frame = ttk.LabelFrame(self.transcription_frame, text="听写语言")
        language_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(language_frame, text="语言:").grid(row=0, column=0, padx=5, sticky="w")
        self.language_combo = ttk.Combobox(language_frame, values=["日语", "英语"], width=10)
        self.language_combo.set("日语" if self.language == "ja" else "英语")
        self.language_combo.grid(row=0, column=1, padx=5, sticky="w")
        self.language_combo.bind("<<ComboboxSelected>>", self.on_language_change)
        
        # 是否启用AI翻译勾选框（第二行）
        ai_frame = ttk.LabelFrame(self.transcription_frame, text="AI翻译设置")
        ai_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Checkbutton(ai_frame, text="是否启用AI翻译", variable=self.enable_ai_translation, 
                       command=self.on_ai_translation_toggle).grid(row=0, column=0, padx=5, sticky="w")
        
        # 文件选择框架
        file_frame = ttk.LabelFrame(self.transcription_frame, text="文件选择")
        file_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Button(file_frame, text="选择媒体文件", command=self.browse_file).grid(row=0, column=0, padx=5)
        ttk.Label(file_frame, textvariable=self.input_file).grid(row=0, column=1, sticky="w")
        
        # 进度条
        self.progress = ttk.Progressbar(self.transcription_frame, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=20)
        
        # 控制按钮
        self.start_btn = ttk.Button(self.transcription_frame, text="开始转换", command=self.start_transcription)
        self.start_btn.pack(pady=10)
        
        # 日志输出
        self.log_text = tk.Text(self.transcription_frame, height=10, state=tk.DISABLED)
        self.log_text.pack(pady=10, padx=10, fill="both")

    def create_ai_translation_widgets(self):
        """创建AI翻译选项卡的UI组件"""
        # API设置框架
        api_frame = ttk.LabelFrame(self.ai_translation_frame, text="DeepSeek API设置")
        api_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(api_frame, text="API密钥:").grid(row=0, column=0, padx=5, sticky="w")
        self.api_key_entry = ttk.Entry(api_frame, width=50, show="*")
        self.api_key_entry.grid(row=0, column=1, padx=5, sticky="w")
        ttk.Button(api_frame, text="保存API密钥", command=self.save_api_key).grid(row=0, column=2, padx=5)
        
        # 模型参数框架
        params_frame = ttk.LabelFrame(self.ai_translation_frame, text="模型参数(温度越高模型回答的发散)")
        params_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(params_frame, text="模型:").grid(row=0, column=0, padx=5, sticky="w")
        self.model_combo = ttk.Combobox(params_frame, values=["deepseek-chat", "deepseek-reasoner"], width=20)
        self.model_combo.set(self.ai_model)
        self.model_combo.grid(row=0, column=1, padx=5, sticky="w")
        self.model_combo.bind("<<ComboboxSelected>>", lambda e: self.update_window_title())
        
        ttk.Label(params_frame, text="温度:").grid(row=0, column=2, padx=5, sticky="w")
        self.temperature_scale = ttk.Scale(params_frame, from_=0.0, to=2.0, value=self.temperature, orient="horizontal")
        self.temperature_scale.grid(row=0, column=3, padx=5, sticky="w")
        # 设置温度刻度的步进为0.1
        self.temperature_scale.configure(command=lambda value: [self.update_temperature_label(value), self.update_window_title()])
        self.temperature_label = ttk.Label(params_frame, text=f"{self.temperature:.1f}")
        self.temperature_label.grid(row=0, column=4, padx=5, sticky="w")
        
        # 预设框架
        preset_frame = ttk.LabelFrame(self.ai_translation_frame, text="预设")
        preset_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(preset_frame, text="预设:").grid(row=0, column=0, padx=5, sticky="w")
        
        # 预设下拉菜单按钮
        self.preset_button = ttk.Menubutton(preset_frame, text="预设", width=15)
        self.preset_menu = tk.Menu(self.preset_button, tearoff=0)
        self.preset_button.configure(menu=self.preset_menu)
        self.preset_button.grid(row=0, column=1, padx=5, sticky="w")
        
        # 初始化预设菜单
        self.update_preset_menu()
        
        # 字幕文件操作框架
        subtitle_frame = ttk.LabelFrame(self.ai_translation_frame, text="字幕文件操作")
        subtitle_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Button(subtitle_frame, text="提交字幕", command=self.submit_subtitle).grid(row=0, column=0, padx=5)
        ttk.Button(subtitle_frame, text="开始翻译", command=self.start_translation).grid(row=0, column=1, padx=5)
        
        # 字幕文件路径显示
        self.subtitle_file_var = tk.StringVar()
        ttk.Label(subtitle_frame, textvariable=self.subtitle_file_var, width=50).grid(row=0, column=2, padx=5, sticky="w")
        
        # 系统提示词框架
        prompt_frame = ttk.LabelFrame(self.ai_translation_frame, text="系统提示词")
        prompt_frame.pack(pady=10, padx=10, fill="both", expand=True)
        
        self.prompt_text = tk.Text(prompt_frame, height=8, width=80)
        self.prompt_text.insert("1.0", self.system_prompt)
        self.prompt_text.pack(pady=5, padx=5, fill="both", expand=True)
        
        # 绑定文本变化事件来检测参数修改
        self.prompt_text.bind("<KeyRelease>", lambda e: self.update_window_title())
        
        ttk.Button(prompt_frame, text="保存预设", command=self.save_preset).pack(pady=5)

    def submit_subtitle(self):
        """提交字幕文件"""
        file_path = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=[("字幕文件", "*.ass *.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            self.subtitle_file_var.set(file_path)
            self.log(f"已选择字幕文件: {file_path}")
            
            # 根据文件类型判断并提取文本
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext == '.ass':
                self.extract_text_from_ass(file_path)
            elif file_ext == '.txt':
                self.extract_text_from_txt(file_path)
            else:
                messagebox.showwarning("警告", "不支持的文件类型，请选择.ass或.txt文件")

    def extract_text_from_ass(self, file_path):
        """从ASS文件中提取文本"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 跳过ASS文件头部信息（通常是前13行）
            text_lines = []
            for line in lines[13:]:
                # 处理ASS格式：查找包含",,0,0,0,,"的行并提取文本
                if ',,0,0,0,,' in line:
                    # 分割行并提取文本部分
                    parts = line.split(',,0,0,0,,')
                    if len(parts) > 1:
                        text = parts[1].strip()
                        if text:
                            text_lines.append(text)
            
            if text_lines:
                # 将文本保存为临时文件用于翻译
                temp_file = os.path.join(os.path.dirname(file_path), "temp_subtitle.txt")
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(text_lines))
                
                self.log(f"已从ASS文件中提取 {len(text_lines)} 行文本")                
                return temp_file
            else:
                messagebox.showwarning("警告", "未找到有效的字幕文本")
                return None
                
        except Exception as e:
            messagebox.showerror("错误", f"读取ASS文件失败: {str(e)}")
            return None

    def extract_text_from_txt(self, file_path):
        """从TXT文件中提取文本"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 简单的文本处理：按行分割并过滤空行
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            if lines:
                # 将文本保存为临时文件用于翻译
                temp_file = os.path.join(os.path.dirname(file_path), "temp_subtitle.txt")
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
                
                self.log(f"已从TXT文件中提取 {len(lines)} 行文本")
                self.log(f"临时文件已保存: {temp_file}")
                return temp_file
            else:
                messagebox.showwarning("警告", "TXT文件中没有有效文本")
                return None
                
        except Exception as e:
            messagebox.showerror("错误", f"读取TXT文件失败: {str(e)}")
            return None

    def start_translation(self):
        """开始翻译字幕"""
        if not self.subtitle_file_var.get():
            messagebox.showerror("错误", "请先提交字幕文件")
            return
        
        if not self.api_key:
            messagebox.showerror("错误", "请先设置API密钥")
            return
        
        # 禁用按钮防止重复点击
        self.log("开始翻译字幕...")
        
        # 启动后台线程
        threading.Thread(target=self.run_batch_translation, daemon=True).start()

    def run_batch_translation(self):
        """执行分批翻译"""
        try:
            subtitle_file = self.subtitle_file_var.get()
            file_ext = os.path.splitext(subtitle_file)[1].lower()
            
            # 根据文件类型提取文本
            if file_ext == '.ass':
                temp_file = self.extract_text_from_ass(subtitle_file)
            elif file_ext == '.txt':
                temp_file = self.extract_text_from_txt(subtitle_file)
            else:
                self.log("错误: 不支持的文件类型")
                return
            
            if not temp_file or not os.path.exists(temp_file):
                self.log("错误: 无法提取字幕文本")
                return
            
            # 读取文本内容
            with open(temp_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            
            # 分批处理（每400行一批）
            batch_size = 400
            total_batches = (len(all_lines) + batch_size - 1) // batch_size
            
            self.log(f"开始分批翻译，共 {len(all_lines)} 行，分为 {total_batches} 批")
            
            all_translated_content = []
            
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min((batch_num + 1) * batch_size, len(all_lines))
                
                batch_lines = all_lines[start_idx:end_idx]
                batch_text = ''.join(batch_lines)
                
                self.log(f"正在翻译第 {batch_num + 1}/{total_batches} 批 ({len(batch_lines)} 行)")
                
                # 调用AI翻译API
                translated_batch = self.call_ai_translation_api(batch_text)
                all_translated_content.append(translated_batch)
                
                # 添加批次分隔符（除了最后一批）
                if batch_num < total_batches - 1:
                    all_translated_content.append('\n\n\n')
                
                self.log(f"第 {batch_num + 1} 批翻译完成")
            
            # 保存翻译结果
            output_dir = os.path.dirname(subtitle_file)
            base_name = os.path.splitext(os.path.basename(subtitle_file))[0]
            output_file = os.path.join(output_dir, f"{base_name}_translated.txt")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(''.join(all_translated_content))
            
            # 清理临时文件
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            self.log(f"翻译完成！结果已保存到: {output_file}")
            
        except Exception as e:
            self.log(f"翻译失败: {str(e)}")

    def on_language_change(self, event):
        """语言选择变更事件"""
        selected_language = self.language_combo.get()
        if selected_language == "日语":
            self.language = "ja"
        elif selected_language == "英语":
            self.language = "en"
        self.log(f"听写语言已设置为: {selected_language}")

    def update_temperature_label(self, value):
        """更新温度标签"""
        self.temperature_label.config(text=f"{float(value):.1f}")

    def on_ai_translation_toggle(self):
        """AI翻译勾选框切换事件"""
        if self.enable_ai_translation.get():
            if not self.api_key:
                self.show_api_key_dialog()
                self.log("AI翻译未启用")
            else:
                self.log("AI翻译已启用")
        else:
            self.log("AI翻译未启用")

    def show_api_key_dialog(self):
        """显示API密钥输入对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("DeepSeek API设置")
        dialog.geometry("500x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="本程序默认使用deepseek，请在下方输入您的API秘钥").pack(pady=10)
        
        ttk.Label(dialog, text="API密钥:").pack()
        #api_entry = ttk.Entry(dialog, width=40, show="*")
        api_entry = ttk.Entry(dialog, width=40)
        api_entry.pack(pady=5)
        
        ttk.Label(dialog, text="加密密码（用于保护API密钥）:").pack()
        #password_entry = ttk.Entry(dialog, width=40, show="*")
        password_entry = ttk.Entry(dialog, width=40)
        password_entry.pack(pady=5)
        
        def save_and_close():
            api_key = api_entry.get().strip()
            password = password_entry.get().strip()
            
            if api_key and password:
                try:
                    # 加密API密钥
                    encrypted_api_key = self.crypto.encrypt_data(api_key, password)
                    self.api_key = encrypted_api_key
                    self.api_key_entry.delete(0, tk.END)
                    self.api_key_entry.insert(0, "***已加密***")
                    self.save_config()
                    dialog.destroy()
                    self.log("API密钥已加密保存")
                except Exception as e:
                    messagebox.showerror("错误", f"加密失败: {str(e)}")
            else:
                messagebox.showwarning("警告", "请输入有效的API密钥和密码")
        
        ttk.Button(dialog, text="保存", command=save_and_close).pack(pady=5)

    def validate_api_key(self, api_key):
        """验证API密钥有效性"""
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            # 发送一个简单的测试请求来验证API密钥
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "user", "content": "Hello"}
                ],
                "max_tokens": 10,
                "temperature": 0.1
            }
            
            response = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                self.log("API密钥验证成功")
                return True
            else:
                # 根据错误代码提供自然语言提示
                error_code = response.status_code
                error_message = self.get_api_error_message(error_code, response.text)
                self.log(f"API密钥验证失败: {error_message}")
                return False
                
        except requests.exceptions.Timeout:
            self.log("API验证超时，请检查网络连接")
            return False
        except requests.exceptions.ConnectionError:
            self.log("网络连接错误，请检查网络连接")
            return False
        except Exception as e:
            self.log(f"API验证过程中发生错误: {str(e)}")
            return False
    
    def get_api_error_message(self, error_code, response_text):
        """根据错误代码返回自然语言错误提示"""
        try:
            error_data = json.loads(response_text)
            error_detail = error_data.get('error', {}).get('message', '未知错误')
        except:
            error_detail = response_text
        
        error_messages = {
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
        
        return error_messages.get(error_code, f"未知错误 (代码: {error_code}): {error_detail}")
    
    def save_api_key(self):
        """保存API密钥"""
        api_key = self.api_key_entry.get().strip()
        if api_key:
            # 如果API密钥不是已加密的标记，则要求输入密码进行加密
            if api_key != "***已加密***":
                password = tk.simpledialog.askstring("加密密码", "请输入加密密码:")
                if password:
                    try:
                        # 先验证API密钥有效性
                        self.log("正在验证API密钥...")
                        if self.validate_api_key(api_key):
                            encrypted_api_key = self.crypto.encrypt_data(api_key, password)
                            self.api_key = encrypted_api_key
                            self.api_key_entry.delete(0, tk.END)
                            self.api_key_entry.insert(0, "***已加密***")
                            self.save_config()
                            self.log("API密钥验证成功并已加密保存")
                        else:
                            self.log("API密钥验证失败，请检查密钥是否正确")
                    except Exception as e:
                        messagebox.showerror("错误", f"加密失败: {str(e)}")
                else:
                    messagebox.showwarning("警告", "请输入加密密码")
            else:
                # 如果已经是加密状态，直接保存
                self.save_config()
                self.log("API密钥已保存")
        else:
            messagebox.showwarning("警告", "请输入有效的API密钥")

    def load_config(self):
        """加载配置文件"""
        config_file = "config.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 加载模型路径
                    self.model_path = config.get('model_path', '')
                    self.model_path_var.set(self.model_path)
                    
                    # 加载AI翻译设置
                    self.enable_ai_translation.set(config.get('enable_ai_translation', False))
                    api_key = config.get('api_key', '')
                    
                    # 检查API密钥是否需要解密
                    if api_key and api_key != "***已加密***":
                        # 尝试检测是否为加密数据
                        if self.crypto.is_encrypted(api_key):
                            # 要求输入密码解密
                            password = tk.simpledialog.askstring("解密密码", "请输入解密密码:")
                            if password:
                                try:
                                    self.api_key = self.crypto.decrypt_data(api_key, password)
                                    self.log("API密钥已成功解密")
                                except Exception as e:
                                    self.log(f"API密钥解密失败: {str(e)}")
                                    self.api_key = ""
                            else:
                                self.api_key = ""
                                self.log("未输入密码，API密钥未解密")
                        else:
                            # 如果是明文API密钥，提示用户重新加密
                            self.api_key = api_key
                            self.log("检测到明文API密钥，建议重新保存以加密")
                    else:
                        self.api_key = api_key
                    
                    self.ai_model = config.get('ai_model', 'deepseek-chat')
                    self.temperature = config.get('temperature', 1.3)
                    self.system_prompt = config.get('system_prompt', '你是一个专业的翻译助手，请将以下日文字幕翻译成中文，保持原有的格式和结构。')
                    
                    # 加载预设信息
                    self.presets = config.get('presets', {})
                    self.current_preset = config.get('current_preset')
                    
                    # 更新UI
                    self.api_key_entry.delete(0, tk.END)
                    if self.api_key and self.api_key != "***已加密***":
                        self.api_key_entry.insert(0, "***已加密***")
                    else:
                        self.api_key_entry.insert(0, self.api_key)
                    self.model_combo.set(self.ai_model)
                    self.temperature_scale.set(self.temperature)
                    self.temperature_label.config(text=f"{self.temperature:.1f}")
                    self.prompt_text.delete("1.0", tk.END)
                    self.prompt_text.insert("1.0", self.system_prompt) 
                    
                    self.log(f"已加载配置，模型路径: {self.model_path}")
                    if self.enable_ai_translation.get():
                        self.log("AI翻译已启用")
            except Exception as e:
                self.log(f"加载配置失败: {str(e)}")
                self.model_path = ""

    def save_config(self):
        """保存配置文件"""
        config_file = "config.json"
        try:
            config = {
                'model_path': self.model_path,
                'enable_ai_translation': self.enable_ai_translation.get(),
                'api_key': self.api_key,
                'ai_model': self.ai_model,
                'temperature': self.temperature,
                'system_prompt': self.system_prompt,
                'presets': self.presets,
                'current_preset': self.current_preset
            }
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self.log("配置已保存")
        except Exception as e:
            self.log(f"保存配置失败: {str(e)}")

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="选择媒体文件",
            filetypes=[("媒体文件", "*.mp4 *.avi *.mkv *.ts *.mp3 *.wav *.aac"), ("所有文件", "*.*")]
        )
        if file_path:
            self.input_file.set(file_path)
            self.output_dir.set(os.path.dirname(file_path))
            self.log(f"已选择文件: {file_path}")

    def browse_model_folder(self):
        """选择模型文件夹"""
        folder_path = filedialog.askdirectory(title="选择模型文件夹")
        if folder_path:
            self.model_path = folder_path
            self.model_path_var.set(folder_path)
            self.save_config()
            self.log(f"已选择模型文件夹: {folder_path}")
            # 重置模型，下次使用时重新加载
            self.model = None

    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def start_transcription(self):
        if not self.input_file.get():
            messagebox.showerror("错误", "请先选择输入文件")
            return
        
        self.start_btn.config(state=tk.DISABLED)
        self.log("开始处理...")
        
        # 启动后台线程
        threading.Thread(target=self.run_transcription, daemon=True).start()
        
        # 启动进度更新检查
        self.root.after(100, self.check_progress)

    def run_transcription(self):
        try:
            # 确定模型路径
            if self.model_path:
                # 使用用户选择的模型路径
                model_path = self.model_path                
            else:
                # 使用默认路径
                if getattr(sys,'frozen',False):
                    script_dir = os.path.dirname(sys.executable)                
                else:                
                    script_dir = r'F:\fasterwhisper_model'
                model_path = os.path.join(script_dir,'faster-whisper-large-v2')
                self.log(f"使用默认模型路径: {model_path}")
            
            print(f"加载的模型路径为: {model_path}")
            print('加载模型 Loading model...')           
            # 加载模型
            if not self.model:
                self.model = WhisperModel(model_size_or_path=model_path)
            print('语音识别库配置完毕，将开始转换 parameters are set,  about to start transcribe...')
            
            # 核心处理逻辑
            file_path = self.input_file.get()
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            
            # 提取音频
            self.progress_queue.put(("progress", 10))
            metadata = ffmpeg.probe(file_path)
            streams = metadata.get('streams', [])
            if not any(s for s in streams if s.get('codec_type') == 'audio'):
                print('提取音频中 Extracting audio from video file...')
                temp_audio_path = self.extract_audio(file_path)
                print('音频提取完毕 Done.')
            else:
                temp_audio_path = file_path
            
            # 执行语音识别
            self.progress_queue.put(("progress", 30))
            print('识别中 Transcribe in progress...')
            segments = self.transcribe_audio(temp_audio_path)
            
            # 生成字幕文件
            self.progress_queue.put(("progress", 50))
            self.generate_subtitles(segments, base_name, file_path)
            
            # 如果启用AI翻译，执行翻译
            if self.enable_ai_translation.get():
                self.progress_queue.put(("progress", 70))                
                #threading.Thread(target=self.run_batch_translation, daemon=True).start()
                self.start_translation()
                self.progress_queue.put(("progress", 80))
                self.progress_queue.put(("message", "听写任务处理完成，AI翻译正在后台运行"))
            self.progress_queue.put(("progress", 100))
            torch.cuda.empty_cache()
            
            # 如果是视频文件，删除临时音频文件
            if not any(s for s in streams if s.get('codec_type') == 'audio'):
                os.remove(temp_audio_path)
                
        except Exception as e:
            self.progress_queue.put(("error", str(e)))
        finally:            
            self.progress_queue.put(("reset_btn", None))

    def extract_audio(self, file_path):
        # 原有音频提取逻辑
        temp_audio_path = f"{os.path.splitext(file_path)[0]}.mp3"
        try:
            (
                ffmpeg.input(file_path)
                .output(temp_audio_path, acodec='mp3', audio_bitrate='192k')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            return temp_audio_path
        except ffmpeg.Error as e:
            raise Exception(f"音频提取失败: {e.stderr.decode()}")

    def transcribe_audio(self, audio_path):
        try:
            segments, info = self.model.transcribe(
                audio=audio_path,
                language=self.language,
                beam_size=None if self.beam_size_off else self.set_beam_size,
                vad_filter=self.is_vad_filter
            )         
            processed = 0            
            total_duration = round(info.duration, 2)  # Same precision as the Whisper timestamps.
            results= []
            with tqdm(total=total_duration, unit=" seconds") as pbar:
                for s in segments:
                    segment_dict = {'start':s.start,'end':s.end,'text':s.text}
                    results.append(segment_dict)
                    segment_duration = s.end - s.start
                    pbar.update(segment_duration)                
            return results
        except Exception as e:
            raise Exception(f"语音识别失败: {str(e)}")

    def generate_subtitles(self, segments, base_name, file_path):
        try:
            subs = pysubs2.load_from_whisper(segments)
            srt_filename = base_name + '.srt'
            subs.save(srt_filename)
            ass_path = srt2ass(srt_filename, self.is_split, self.split_method, file_path)            
            
            # 生成适合ai翻译的字幕格式
            output_file_name = f"{base_name}_forAI"
            output_file_name += '.txt'
            output_file_path = os.path.join(os.path.dirname(file_path), output_file_name)    
            input_file_name = base_name+'.ass'
            input_file_path = os.path.join(os.path.dirname(file_path), input_file_name)
            
            # 处理字幕文件用于AI翻译
            if os.path.exists(input_file_path):
                with open(input_file_path, 'r', encoding='utf-8') as input_file:
                    lines = input_file.readlines()[13:]        
                    struct = []
                    count2 = 0
                    for line in lines: 
                        count1 = 0
                        count2 = count2 + 1   
                        for bit in line:                   
                            count1 = count1 + 1   
                        struct.append(line[50:count1-1])
                        if count2 == 400: 
                            struct.append('\n\n\n')
                            count2 = 0                 
                with open(output_file_path, 'w', encoding='utf-8') as output_file:        
                    output_file.write('\n'.join(struct))
                self.subtitle_file_var.set(input_file_path)
                self.log(f"已生成字幕文件: {input_file_path}")
                self.log(f"已生成AI翻译用字幕文件: {output_file_path}")
                print(f"ASS subtitle saved as: {base_name}.ass")
                print(f"And output {base_name}_forAI.txt")
                print('字幕生成完毕 subtitle generated!')
            else:
                self.log(f"警告: 未找到字幕文件 {input_file_path}")
            
            # 清理临时文件
            if os.path.exists(srt_filename):
                os.remove(srt_filename)            
            if os.path.exists(ass_path):
                os.remove(ass_path)                
        except Exception as e:
            raise Exception(f"生成字幕失败: {str(e)}")
        
    def call_ai_translation_api(self, content):
        """调用AI翻译API，包含重试机制"""
        max_retries = 3
        retry_delay = 5  # 秒
        
        for attempt in range(max_retries):
            try:
                # 检查API密钥是否需要解密
                api_key_to_use = self.api_key
                if self.api_key and self.api_key != "***已加密***" and self.crypto.is_encrypted(self.api_key):
                    # 要求输入密码解密
                    password = tk.simpledialog.askstring("解密密码", "请输入解密密码:")
                    if password:
                        try:
                            api_key_to_use = self.crypto.decrypt_data(self.api_key, password)
                            self.log("API密钥已成功解密")
                        except Exception as e:
                            self.log(f"API密钥解密失败: {str(e)}")
                            raise Exception("API密钥解密失败")
                    else:
                        raise Exception("未输入密码，无法解密API密钥")
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key_to_use}"
                }
                
                data = {
                    "model": self.ai_model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": content}
                    ],
                    "temperature": self.temperature,
                    "stream": False
                }
                
                # 增加超时时间，特别是对于PyInstaller打包后的程序
                timeout_value = 120  # 2分钟超时
                
                self.log(f"正在调用AI翻译API (尝试 {attempt + 1}/{max_retries})...")
                response = requests.post(
                    "https://api.deepseek.com/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=timeout_value
                )
                
                if response.status_code == 200:
                    result = response.json()
                    #self.log("AI翻译API调用成功")
                    return result["choices"][0]["message"]["content"]
                else:
                    error_msg = f"API调用失败: {response.status_code} - {response.text}"
                    self.log(f"API错误: {error_msg}")
                    
                    # 如果是服务器错误，重试
                    if response.status_code >= 500:
                        if attempt < max_retries - 1:
                            self.log(f"服务器错误，{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # 指数退避
                            continue
                    
                    raise Exception(error_msg)
                    
            except requests.exceptions.Timeout:
                self.log(f"API调用超时 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    self.log(f"{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                    continue
                else:
                    raise Exception("AI翻译API调用超时: 多次重试后仍然失败")
                    
            except requests.exceptions.ConnectionError as e:
                self.log(f"网络连接错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    self.log(f"{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                    continue
                else:
                    raise Exception(f"网络连接失败: {str(e)}")
                    
            except Exception as e:
                self.log(f"API调用异常 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    self.log(f"{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                    continue
                else:
                    raise Exception(f"AI翻译API调用失败: {str(e)}")
        
        # 如果所有重试都失败
        raise Exception("AI翻译API调用失败: 所有重试尝试均失败")

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

    def update_preset_menu(self):
        """更新预设菜单"""
        # 清空菜单
        self.preset_menu.delete(0, tk.END)
        
        # 添加预设管理选项（按照用户要求的顺序）
        self.preset_menu.add_command(label="新建", command=self.create_preset)
        self.preset_menu.add_command(label="重命名", command=self.rename_preset)
        self.preset_menu.add_command(label="删除", command=self.delete_preset)
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
                display_name = f"✓ {preset_name}" if preset_name == self.current_preset else preset_name
                
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
        self.update_window_title()

    def create_preset(self):
        """创建新预设"""
        preset_name = tk.simpledialog.askstring("新建预设", "输入新预设名:")
        if preset_name and preset_name.strip():
            preset_name = preset_name.strip()
            if preset_name in self.presets:
                messagebox.showwarning("警告", f"预设 '{preset_name}' 已存在")
                return
            
            # 获取当前系统提示词
            current_prompt = self.prompt_text.get("1.0", tk.END).strip()
            
            # 创建新预设
            self.presets[preset_name] = {
                "system_prompt": current_prompt,
                "ai_model": self.ai_model,
                "temperature": self.temperature
            }
            
            # 清空系统提示词框
            self.prompt_text.delete("1.0", tk.END)
            
            # 切换到新预设
            self.current_preset = preset_name
            self.update_preset_menu()
            self.log(f"已创建预设: {preset_name}")
        else:
            messagebox.showwarning("警告", "请输入有效的预设名")



    def rename_preset(self):
        """重命名当前预设"""
        if self.current_preset not in self.presets:
            messagebox.showwarning("警告", "请先选择或创建一个预设")
            return
        
        new_name = tk.simpledialog.askstring("重命名预设", "输入新预设名:", initialvalue=self.current_preset)
        if new_name and new_name.strip():
            new_name = new_name.strip()
            if new_name == self.current_preset:
                return
            
            if new_name in self.presets:
                messagebox.showwarning("警告", f"预设 '{new_name}' 已存在")
                return
            
            # 重命名预设
            self.presets[new_name] = self.presets.pop(self.current_preset)
            self.current_preset = new_name
            self.update_preset_menu()
            self.log(f"已重命名预设为: {new_name}")

    def delete_preset(self):
        """删除当前预设"""
        if self.current_preset not in self.presets:
            messagebox.showwarning("警告", "请先选择或创建一个预设")
            return
        
        if messagebox.askyesno("确认删除", f"确定要删除预设 '{self.current_preset}' 吗？"):
            del self.presets[self.current_preset]
            
            # 如果删除了当前预设，切换到默认预设
            if self.current_preset not in self.presets:
                self.current_preset = "Default"
                self.system_prompt = "你是一个专业的翻译助手，请将以下日文字幕翻译成中文，保持原有的格式和结构。"
                self.prompt_text.delete("1.0", tk.END)
                self.prompt_text.insert("1.0", self.system_prompt)
            
            self.update_preset_menu()
            self.log(f"已删除预设: {self.current_preset}")

    def select_preset(self, preset_name):
        """选择预设"""
        if preset_name in self.presets:
            self.current_preset = preset_name
            preset_data = self.presets[preset_name]
            
            # 更新系统提示词
            self.system_prompt = preset_data.get("system_prompt", "")
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert("1.0", self.system_prompt)
            
            # 更新模型参数
            self.ai_model = preset_data.get("ai_model", self.ai_model)
            self.temperature = preset_data.get("temperature", self.temperature)
            
            # 更新UI
            self.model_combo.set(self.ai_model)
            self.temperature_scale.set(self.temperature)
            self.temperature_label.config(text=f"{self.temperature:.1f}")
            
            self.update_preset_menu()
            self.log(f"已切换到预设: {preset_name}")

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
            filetypes=[("JSON文件", "*.json")]
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

    def update_window_title(self):
        """更新窗口标题，在预设参数改变时显示*号"""
        # 检查当前参数是否与保存的预设匹配
        is_modified = False
        
        if self.current_preset in self.presets:
            preset_data = self.presets[self.current_preset]
            current_prompt = self.prompt_text.get("1.0", tk.END).strip()
            current_model = self.model_combo.get()
            current_temperature = float(self.temperature_scale.get())
            
            # 检查是否有参数改变
            if (current_prompt != preset_data.get("system_prompt", "") or
                current_model != preset_data.get("ai_model", "") or
                current_temperature != preset_data.get("temperature", 1.3)):
                is_modified = True
        
        # 更新窗口标题
        if is_modified:
            self.root.title(f"语音字幕生成器(预设:*{self.current_preset})")
        else:
            self.root.title(f"语音字幕生成器(预设:{self.current_preset})")

    def save_preset(self):
        """保存当前预设"""
        if not self.current_preset:
            messagebox.showwarning("警告", "请先选择或创建一个预设")
            return
        
        # 获取当前系统提示词 模型 温度
        current_prompt = self.prompt_text.get("1.0", tk.END).strip()
        current_model = self.model_combo.get()
        current_temperature = float(self.temperature_scale.get())

        # 保存预设信息
        self.presets[self.current_preset] = {
            "system_prompt": current_prompt,
            "ai_model": current_model,
            "temperature": current_temperature
        }
        
        # 更新当前实例的配置
        self.system_prompt = current_prompt
        self.ai_model = current_model
        self.temperature = current_temperature
        
        # 保存到config文件
        self.save_config()
        
        # 更新预设组合框
        self.update_preset_menu()
        
        self.log(f"已保存预设: {self.current_preset}")

# 主程序入口
if __name__ == "__main__":
    root = tk.Tk()
    app = TranscriptionApp(root)
    root.mainloop()
