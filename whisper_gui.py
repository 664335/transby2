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
        self.root.title("语音字幕生成器")
        self.root.geometry("1600x900")
        
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
        self.notebook.add(self.ai_translation_frame, text='AI翻译')

    def create_transcription_widgets(self):
        """创建转写选项卡的UI组件"""
        # 模型选择框架（最上一行）
        model_frame = ttk.LabelFrame(self.transcription_frame, text="模型选择")
        model_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Button(model_frame, text="选择模型文件夹", command=self.browse_model_folder).grid(row=0, column=0, padx=5)
        ttk.Label(model_frame, textvariable=self.model_path_var, width=50).grid(row=0, column=1, padx=5, sticky="w")
        
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
        params_frame = ttk.LabelFrame(self.ai_translation_frame, text="模型参数")
        params_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(params_frame, text="模型:").grid(row=0, column=0, padx=5, sticky="w")
        self.model_combo = ttk.Combobox(params_frame, values=["deepseek-chat", "deepseek-reasoner"], width=20)
        self.model_combo.set(self.ai_model)
        self.model_combo.grid(row=0, column=1, padx=5, sticky="w")
        
        ttk.Label(params_frame, text="温度:").grid(row=0, column=2, padx=5, sticky="w")
        self.temperature_scale = ttk.Scale(params_frame, from_=0.1, to=2.0, value=self.temperature, orient="horizontal")
        self.temperature_scale.grid(row=0, column=3, padx=5, sticky="w")
        self.temperature_label = ttk.Label(params_frame, text=f"{self.temperature:.1f}")
        self.temperature_label.grid(row=0, column=4, padx=5, sticky="w")
        self.temperature_scale.configure(command=self.update_temperature_label)
        
        # 系统提示词框架
        prompt_frame = ttk.LabelFrame(self.ai_translation_frame, text="系统提示词")
        prompt_frame.pack(pady=10, padx=10, fill="both", expand=True)
        
        self.prompt_text = tk.Text(prompt_frame, height=8, width=80)
        self.prompt_text.insert("1.0", self.system_prompt)
        self.prompt_text.pack(pady=5, padx=5, fill="both", expand=True)
        
        ttk.Button(prompt_frame, text="保存提示词", command=self.save_prompt).pack(pady=5)

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
        api_entry = ttk.Entry(dialog, width=40, show="*")
        api_entry.pack(pady=5)
        
        ttk.Label(dialog, text="加密密码（用于保护API密钥）:").pack()
        password_entry = ttk.Entry(dialog, width=40, show="*")
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

    def save_api_key(self):
        """保存API密钥"""
        api_key = self.api_key_entry.get().strip()
        if api_key:
            # 如果API密钥不是已加密的标记，则要求输入密码进行加密
            if api_key != "***已加密***":
                password = tk.simpledialog.askstring("加密密码", "请输入加密密码:", show="*")
                if password:
                    try:
                        encrypted_api_key = self.crypto.encrypt_data(api_key, password)
                        self.api_key = encrypted_api_key
                        self.api_key_entry.delete(0, tk.END)
                        self.api_key_entry.insert(0, "***已加密***")
                        self.save_config()
                        self.log("API密钥已加密保存")
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

    def save_prompt(self):
        """保存系统提示词"""
        self.system_prompt = self.prompt_text.get("1.0", tk.END).strip()
        self.save_config()
        self.log("系统提示词已保存")

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
                            password = tk.simpledialog.askstring("解密密码", "请输入解密密码:", show="*")
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
                    self.temperature = config.get('temperature', 0.7)
                    self.system_prompt = config.get('system_prompt', '你是一个专业的翻译助手，请将以下日文字幕翻译成中文，保持原有的格式和结构。')
                    
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
                'system_prompt': self.system_prompt
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
                self.log(f"使用用户选择的模型路径: {model_path}")
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
            self.progress_queue.put(("progress", 70))
            self.generate_subtitles(segments, base_name, file_path)
            
            # 如果启用AI翻译，执行翻译
            if self.enable_ai_translation.get():
                self.progress_queue.put(("progress", 80))
                self.log("开始AI翻译...")
                self.run_ai_translation(base_name, file_path)
            
            self.progress_queue.put(("progress", 100))
            self.progress_queue.put(("message", "处理完成！"))
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
            output_file_name = f"{base_name}_forgpt"
            output_file_name += '.ass'
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
                
                self.log(f"已生成字幕文件: {input_file_path}")
                self.log(f"已生成AI翻译用字幕文件: {output_file_path}")
                print(f"ASS subtitle saved as: {base_name}.ass")
                print(f"And output {base_name}_forgpt.ass")
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

    def run_ai_translation(self, base_name, file_path):
        """执行AI翻译"""
        try:
            if not self.api_key:
                self.log("错误: 未设置API密钥")
                return
                
            # 构建字幕文件路径
            subtitle_file = f"{base_name}_forgpt.ass"
            subtitle_path = os.path.join(os.path.dirname(file_path), subtitle_file)
            
            if not os.path.exists(subtitle_path):
                self.log(f"错误: 未找到字幕文件 {subtitle_path}")
                return
                
            # 读取字幕文件
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                subtitle_content = f.read()
                
            # 调用AI翻译API
            self.log("正在调用AI翻译API...")
            translated_content = self.call_ai_translation_api(subtitle_content)
            
            # 保存翻译结果
            translated_file = f"{base_name}_translated.ass"
            translated_path = os.path.join(os.path.dirname(file_path), translated_file)
            
            with open(translated_path, 'w', encoding='utf-8') as f:
                f.write(translated_content)
                
            self.log(f"AI翻译完成: {translated_path}")
            
        except Exception as e:
            self.log(f"AI翻译失败: {str(e)}")

    def call_ai_translation_api(self, content):
        """调用AI翻译API，包含重试机制"""
        max_retries = 3
        retry_delay = 5  # 秒
        
        for attempt in range(max_retries):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
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
                    self.log("AI翻译API调用成功")
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

# 主程序入口
if __name__ == "__main__":
    root = tk.Tk()
    app = TranscriptionApp(root)
    root.mainloop()
