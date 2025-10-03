# encoding:utf-8
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import os
import sys
import json
import requests
import time
from crypto_utils import CryptoUtils
import google.generativeai as genai
from google.api_core import exceptions

class TranslationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("字幕翻译器(预设:Default)")
        self.root.geometry("1280x720")
        
        # 文件路径变量
        self.subtitle_file_var = tk.StringVar()
        
        # 预设管理
        self.presets = {}
        self.current_preset = "Default"
        self.preset_menu = None
        self.preset_combo = None
        
        # AI翻译配置
        self.api_keys = {}  # 存储不同服务商的API密钥
        self.current_api_key = ""  # 当前服务商的API密钥
        self.api_key_status_cache = {}  # API密钥状态缓存
        self.ai_model = "deepseek-reasoner"
        self.temperature = 1.3
        self.system_prompt = "你是一个专业的翻译助手，请将以下日文字幕翻译成中文，保持原有的格式和结构。"
        
        # 服务商配置
        self.provider_var = tk.StringVar(value="DeepSeek")
        self.providers = {
            "DeepSeek": {
                "api_url": "https://api.deepseek.com/chat/completions",
                "model_options": ["deepseek-chat", "deepseek-reasoner"]
            },
            "Genimi": {
                "api_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                "model_options": ["gemini-2.5-pro","gemini-2.5-flash"]
            },
            "OpenAI": {
                "api_url": "https://api.openai.com/v1/chat/completions",
                "model_options": ["gpt-5", "gpt-4.1"]
            }
        }
        
        # 加密工具
        self.crypto = CryptoUtils()
        
        # 创建UI组件
        self.create_translation_widgets()
        
        # 加载配置
        self.load_config()
        self.update_preset_menu()         
   
        # 进度队列
        self.progress_queue = queue.Queue()

    def create_translation_widgets(self):
        """创建翻译界面的UI组件"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 服务商选择框架（最上方）
        provider_frame = ttk.LabelFrame(main_frame, text="AI服务商选择")
        provider_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(provider_frame, text="服务商:").grid(row=0, column=0, padx=5, sticky="w")
        self.provider_combo = ttk.Combobox(provider_frame, values=list(self.providers.keys()), width=15)
        self.provider_combo.set(self.provider_var.get())
        self.provider_combo.grid(row=0, column=1, padx=5, sticky="w")
        self.provider_combo.bind("<<ComboboxSelected>>", self.on_provider_change)

        # API设置框架
        api_frame = ttk.LabelFrame(main_frame, text="API设置")
        api_frame.pack(pady=10, padx=10, fill="x")
        ttk.Label(api_frame, text="API密钥:").grid(row=0, column=0, padx=5, sticky="w")
        self.api_key_entry = ttk.Entry(api_frame, width=50, show="*")
        self.api_key_entry.grid(row=0, column=1, padx=5, sticky="w")
        ttk.Button(api_frame, text="保存API密钥", command=self.save_api_key).grid(row=0, column=2, padx=5)
        
        # 模型参数框架
        params_frame = ttk.LabelFrame(main_frame, text="模型参数(温度越高模型的回答越发散)")
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
        preset_frame = ttk.LabelFrame(main_frame, text="预设")
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
        subtitle_frame = ttk.LabelFrame(main_frame, text="字幕文件操作")
        subtitle_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Button(subtitle_frame, text="提交字幕", command=self.submit_subtitle).grid(row=0, column=0, padx=5)
        ttk.Button(subtitle_frame, text="开始翻译", command=self.start_translation).grid(row=0, column=1, padx=5)
        
        # 字幕文件路径显示
        ttk.Label(subtitle_frame, textvariable=self.subtitle_file_var, width=50).grid(row=0, column=2, padx=5, sticky="w")
        
        # 进度条
        self.progress = ttk.Progressbar(main_frame, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=20)
        
        # 系统提示词框架
        prompt_frame = ttk.LabelFrame(main_frame, text="提示词")
        prompt_frame.pack(pady=10, padx=10, fill="both", expand=True)
        
        self.prompt_text = tk.Text(prompt_frame, height=8, width=80)
        self.prompt_text.insert("1.0", self.system_prompt)
        self.prompt_text.pack(pady=5, padx=5, fill="both", expand=True)
        
        # 绑定文本变化事件来检测参数修改
        self.prompt_text.bind("<KeyRelease>", lambda e: self.update_window_title())
        
        ttk.Button(prompt_frame, text="保存预设", command=self.save_preset).pack(pady=5)
        
        # 日志输出
        self.log_text = tk.Text(main_frame, height=10, state=tk.DISABLED)
        self.log_text.pack(pady=10, padx=10, fill="both")

    def submit_subtitle(self):
        """提交字幕文件"""
        file_path = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=[("字幕文件", "*.ass *.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            self.subtitle_file_var.set(file_path)
            self.log(f"已选择字幕文件: {file_path}")

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
        
        if not self.current_api_key:
            messagebox.showerror("错误", "请先设置API密钥")
            return
        
        # 使用新的API密钥准备方法
        success, message = self.ensure_api_key_ready()
        if not success:
            messagebox.showerror("错误", f"API密钥准备失败: {message}")
            return
        
        self.save_preset()
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
                
                #添加批次分隔符（除了最后一批）
                if batch_num < total_batches - 1:
                    all_translated_content.append('\n\n\n')
                
                self.log(f"第 {batch_num + 1} 批翻译完成")   
                # 更新进度条
                progress_value = (batch_num + 1) * 100 // total_batches
                self.progress["value"] = progress_value

            processed_content = []
            translated_lines = []
            translated_lines = [str(line).strip() for line in all_translated_content if str(line).strip()]
            for content in translated_lines:
                if content.strip():  # 文本处理：去除空行，并将"，"和"。"替换为空格                              
                    processed_line = content.strip().replace('，', ' ').replace('。', ' ').replace('"', '「').replace('"', '」').replace('《', '『').replace('》', '』') .replace('！', ' ').replace('？', '吗').replace('\n', '\nDialogue: 0,0:00:00.00,0:00:00.00,default,,0,0,0,,')
                    # 为每一行翻译文本添加时间轴前缀
                    processed_line = f"Dialogue: 0,0:00:00.00,0:00:00.00,default,,0,0,0,,{processed_line}"
                    processed_content.append(processed_line)

            processed_content[len(processed_content)-1] += "\n"
                                
            base_name = os.path.splitext(os.path.basename(subtitle_file))[0]
            output_dir = os.path.dirname(subtitle_file)
            output_file = os.path.join(output_dir, f"{base_name}_readytogo.ass")
            if file_ext == '.ass':
                with open(subtitle_file, 'r', encoding='utf-8') as f:
                    original_lines = f.readlines()                
                # 提取原始ASS文件的头部信息（通常是前13行）
                header_lines = original_lines[:13]                
                # 提取原始字幕内容（从第14行开始）
                original_subtitle_lines = original_lines[13:]
                with open(output_file, 'w', encoding='utf-8') as f:
                    # 写入原始ASS头部
                    f.writelines(header_lines)    
                    # 写入处理后的翻译内容
                    f.write('\n'.join(processed_content))                 
                    # 写入原始字幕内容
                    f.writelines(original_subtitle_lines)                      
            else:
                all_translated_content = processed_content
                # 保存翻译结果
                output_dir = os.path.dirname(subtitle_file)
                base_name = os.path.splitext(os.path.basename(subtitle_file))[0]
                output_file = os.path.join(output_dir, f"{base_name}_translated.txt")               
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(all_translated_content))                
            # 清理临时文件
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            self.log(f"翻译完成！结果已保存到: {output_file}")
            self.progress["value"] = 100
            
        except Exception as e:
            self.log(f"翻译失败: {str(e)}")
            self.progress["value"] = 0

    def on_provider_change(self, event):
        """服务商选择变更事件"""
        selected_provider = self.provider_combo.get()
        if selected_provider in self.providers:
            self.provider_var.set(selected_provider)
            provider_config = self.providers[selected_provider]
            
            # 更新模型选择下拉框的选项
            self.model_combo['values'] = provider_config["model_options"]
            
            # 设置默认模型
            if provider_config["model_options"]:
                self.model_combo.set(provider_config["model_options"][0])
                self.ai_model = provider_config["model_options"][0]
            
            # 更新当前API密钥为对应服务商的密钥
            self.current_api_key = self.api_keys.get(selected_provider, "")
            
            # 更新UI显示
            self.api_key_entry.delete(0, tk.END)
            if self.current_api_key and self.current_api_key != "***已加密***":
                self.api_key_entry.insert(0, "***已加密***")
            else:
                self.api_key_entry.insert(0, self.current_api_key)
            
            self.log(f"已切换到服务商: {selected_provider}")
            self.save_config()

    def update_temperature_label(self, value):
        """更新温度标签"""
        self.temperature_label.config(text=f"{float(value):.1f}")

    def validate_api_key(self, api_key):
        """验证API密钥有效性"""
        current_provider = self.provider_var.get()
        provider_config = self.providers.get(current_provider, self.providers["DeepSeek"])
        api_url = provider_config["api_url"]     
        
        if current_provider == "Genimi":
            test_model = 'gemini-2.5-flash'
            genai.configure(api_key=api_key)
            try:
                # 创建模型实例
                model = genai.GenerativeModel(test_model)
                
                # 发送测试请求
                response = model.generate_content("Hello, please respond with 'API is working'")
                
                # 检查响应
                if response.text:
                    print("API密钥验证成功！此密钥有效且可用。")
                    return True
                else:                    
                    return False, "API响应为空。"             
            except exceptions.PermissionDenied:
                # 捕获权限错误，这通常意味着API密钥是错误的或未启用服务
                print("API密钥验证失败：权限被拒绝。请仔细检查您的API密钥是否正确，以及是否已在Google AI Studio中启用了API服务。")
                return False
            except exceptions.Unauthenticated:
                # 捕获身份验证失败错误
                print("API密钥验证失败：身份验证错误。这几乎总是由于API密钥不正确或格式错误导致的。")
                return False
            except Exception as e:
                # 捕获其他所有可能的异常，如网络连接问题
                print("验证过程中发生未知错误，请检查您的网络连接或稍后再试。详细错误信息：{e}")
                return False          
                      
        else:
            try:
            # DeepSeek和OpenAI API验证
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
                
                # 根据服务商选择测试模型
                if current_provider == "DeepSeek":
                    test_model = "deepseek-chat"
                else:  # OpenAI
                    test_model = "gpt-3.5-turbo"
                
                data = {
                    "model": test_model,
                    "messages": [
                        {"role": "user", "content": "Hello"}
                    ],
                    "max_tokens": 10,
                    "temperature": 0.1
                }
                
                response = requests.post(
                    api_url,
                    headers=headers,
                    json=data,
                    timeout=30
                )
            
                if response.status_code == 200:
                    self.log(f"{current_provider} API密钥验证成功")
                    return True
                else:
                    # 根据错误代码提供自然语言提示
                    error_code = response.status_code
                    error_message = self.get_api_error_message(error_code, response.text, current_provider)
                    self.log(f"{current_provider} API密钥验证失败: {error_message}")
                    return False
                
            except requests.exceptions.Timeout:
                self.log(f"{current_provider} API验证超时，请检查网络连接")
                return False
            except requests.exceptions.ConnectionError:
                self.log(f"{current_provider} 网络连接错误，请检查网络连接")
                return False
            except Exception as e:
                self.log(f"{current_provider} API验证过程中发生错误: {str(e)}")
                return False
    
    def get_api_error_message(self, error_code, response_text, provider):
        """根据错误代码和服务商返回自然语言错误提示"""
        try:
            error_data = json.loads(response_text)
            # 根据不同服务商的错误响应格式提取错误信息
            if provider == "Genimi":
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
            "Genimi": {
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
                password = tk.simpledialog.askstring("加密密码", "请输入加密密码:")
                if password:
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
                    
                    # 加载AI翻译设置
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
                    
                    # 更新UI
                    self.api_key_entry.delete(0, tk.END)
                    if self.current_api_key and self.current_api_key != "***已加密***":
                        self.api_key_entry.insert(0, "***已加密***")
                    else:
                        self.api_key_entry.insert(0, self.current_api_key)
                    
                    # 更新服务商选择
                    self.provider_combo.set(self.provider_var.get())
                    self.on_provider_change(None)  # 触发服务商变更以更新模型选项
                    
                    self.model_combo.set(self.ai_model)
                    self.temperature_scale.set(self.temperature)
                    self.temperature_label.config(text=f"{self.temperature:.1f}")
                    self.prompt_text.delete("1.0", tk.END)
                    self.prompt_text.insert("1.0", self.system_prompt) 
                    
                    self.log(f"已加载配置")
            except Exception as e:
                self.log(f"加载配置失败: {str(e)}")

    def save_config(self):
        """保存配置文件"""
        config_file = "config.json"
        try:
            config = {
                'api_keys': self.api_keys,  # 保存所有服务商的API密钥
                'ai_model': self.ai_model,
                'temperature': self.temperature,
                'system_prompt': self.system_prompt,
                'presets': self.presets,
                'current_preset': self.current_preset,
                'provider': self.provider_var.get()
            }
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self.log("配置已保存")
        except Exception as e:
            self.log(f"保存配置失败: {str(e)}")

    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

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
    
    def ensure_api_key_ready(self):
        """确保API密钥已准备就绪，如果需要解密则处理解密流程"""
        # 检查缓存状态
        cache_key = f"{self.provider_var.get()}_{self.current_api_key}"
        if cache_key in self.api_key_status_cache:
            return self.api_key_status_cache[cache_key]
        
        is_valid, message = self.check_api_key_status()
        
        if is_valid:
            result = (True, "API密钥已准备就绪")
            self.api_key_status_cache[cache_key] = result
            return result
        
        # 如果需要解密，在主线程中处理
        if message == "API密钥需要解密":
            success, decrypt_message = self.decrypt_api_key_in_main_thread()
            if not success:
                result = (False, f"API密钥解密失败: {decrypt_message}")
                self.api_key_status_cache[cache_key] = result
                return result
            
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
        self.api_key_status_cache[cache_key] = result
        return result
    
    def decrypt_api_key_in_main_thread(self):
        """在主线程中解密API密钥"""
        if not self.current_api_key or not self.crypto.is_encrypted(self.current_api_key):
            return True, "无需解密"
        
        password = tk.simpledialog.askstring("解密密码", "请输入解密密码:")
        if password:
            try:
                self.current_api_key = self.crypto.decrypt_data(self.current_api_key, password)
                self.log("API密钥已成功解密")
                # 更新UI显示
                self.api_key_entry.delete(0, tk.END)
                self.api_key_entry.insert(0, "***已加密***")
                self.save_config()
                return True, "API密钥解密成功"
            except Exception as e:
                return False, f"API密钥解密失败: {str(e)}"
        else:
            return False, "未输入密码，无法解密API密钥"
    
    def call_ai_translation_api(self, content):
        """调用AI翻译API，包含重试机制"""
        max_retries = 3
        retry_delay = 5  # 秒
        
        # 获取当前服务商配置
        selected_provider = self.provider_var.get()
        provider_config = self.providers.get(selected_provider, self.providers["DeepSeek"])
        api_url = provider_config["api_url"]
        for attempt in range(max_retries):
            # 根据服务商构建请求
            if selected_provider == "Genimi":                  
                try:
                    # 1. 配置genai库 (在实际应用中，如果已验证过，此步骤可省略)
                    genai.configure(api_key=self.current_api_key)
                    
                    # 2. 初始化模型
                    model = genai.GenerativeModel(self.ai_model)
                    
                    # 3. 发送请求        
                    self.system_prompt += "\n"
                    self.system_prompt += content
                    
                    response = model.generate_content(self.system_prompt)
                    
                    # 4. 检查是否有内容被安全设置阻止
                    #    response.text 会在被阻止时直接抛出异常，我们可以用更安全的方式检查
                    if not response.parts:
                        if response.prompt_feedback.block_reason:
                            block_reason_name = response.prompt_feedback.block_reason.name
                            return None, f"请求被模型的内容安全策略阻止，原因：{block_reason_name}。请尝试修改您的输入内容。"
                        else:
                            return None, "模型没有返回任何内容，可能是由于输入不明确或触发了未知的安全限制。"
                    
                    # 5. 提取并返回文本内容
                    return response.text
                
                except exceptions.PermissionDenied:
                    return None, "文本生成失败：权限被拒绝。您的API密钥似乎是无效的，请重新检查。"
                except ValueError as e:
                    # response.text 在内容被阻止时会抛出 ValueError
                    return None, f"内容生成被阻止。这通常是由于Google的安全设置。请尝试修改输入内容。详细信息: {e}"
                except exceptions.InvalidArgument:
                    # 捕获无效参数错误，有时可能是因为prompt内容有问题
                    return None, "文本生成失败：请求参数无效。请检查您的输入内容是否符合要求。"
                except Exception as e:
                    # 捕获其他所有可能的异常
                    return None, f"文本生成过程中发生未知错误，请检查网络连接或服务状态。详细错误信息：{e}"
                
            else:
                try:
                    # DeepSeek和OpenAI格式
                    # 增加超时时间，特别是对于PyInstaller打包后的程序
                    timeout_value = 120  # 2分钟超时
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.current_api_key}"
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
                    
                    full_url = api_url
                    response = requests.post(
                        full_url,
                        headers=headers,
                        json=data,
                        timeout=timeout_value
                    )            

                    if response.status_code == 200:
                        result = response.json()  
                        # DeepSeek和OpenAI响应格式
                        return result["choices"][0]["message"]["content"]                            
                    else:
                        error_msg = f"{selected_provider} API调用失败: {response.status_code} - {response.text}"
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
                    self.log(f"{selected_provider} API调用超时 (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        self.log(f"{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                        continue
                    else:
                        raise Exception(f"{selected_provider} API调用超时，已达到最大重试次数")
                        
                except requests.exceptions.ConnectionError:
                    self.log(f"{selected_provider} 网络连接错误 (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        self.log(f"{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                        continue
                    else:
                        raise Exception(f"{selected_provider} 网络连接错误，已达到最大重试次数")
                        
                except Exception as e:
                    self.log(f"{selected_provider} API调用错误: {str(e)} (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        self.log(f"{retry_delay}秒后重试...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                        continue
                    else:
                        raise Exception(f"{selected_provider} API调用失败: {str(e)}")
        
        # 如果所有重试都失败
        raise Exception(f"{selected_provider} API调用失败，已达到最大重试次数")

    def update_preset_menu(self):
        """更新预设菜单"""
        if self.preset_menu:
            self.preset_menu.delete(0, tk.END)
        
        # 添加预设选项
        for preset_name in self.presets.keys():
            self.preset_menu.add_command(
                label=preset_name,
                command=lambda name=preset_name: self.select_preset(name)
            )
        
        # 添加预设管理选项
        self.preset_menu.add_separator()
        self.preset_menu.add_command(label="创建新预设", command=self.create_preset)
        self.preset_menu.add_command(label="重命名当前预设", command=self.rename_preset)
        self.preset_menu.add_command(label="删除当前预设", command=self.delete_preset)
        self.preset_menu.add_command(label="导出预设", command=self.export_presets)
        self.preset_menu.add_command(label="导入预设", command=self.import_presets)
        
        # 更新按钮文本
        self.preset_button.config(text=self.current_preset)

    def create_preset(self):
        """创建新预设"""
        preset_name = tk.simpledialog.askstring("创建预设", "请输入预设名称:")
        if preset_name:
            if preset_name in self.presets:
                messagebox.showwarning("警告", f"预设 '{preset_name}' 已存在")
                return
            
            # 保存当前设置到新预设
            self.presets[preset_name] = {
                'ai_model': self.ai_model,
                'temperature': self.temperature,
                'system_prompt': self.system_prompt,
                'provider': self.provider_var.get()
            }
            
            self.current_preset = preset_name
            self.update_preset_menu()
            self.update_window_title()
            self.save_config()
            self.log(f"已创建预设: {preset_name}")

    def rename_preset(self):
        """重命名当前预设"""
        if self.current_preset == "Default":
            messagebox.showwarning("警告", "无法重命名默认预设")
            return
        
        new_name = tk.simpledialog.askstring("重命名预设", f"请输入新的预设名称 (当前: {self.current_preset}):")
        if new_name:
            if new_name in self.presets:
                messagebox.showwarning("警告", f"预设 '{new_name}' 已存在")
                return
            
            # 重命名预设
            self.presets[new_name] = self.presets.pop(self.current_preset)
            self.current_preset = new_name
            self.update_preset_menu()
            self.update_window_title()
            self.save_config()
            self.log(f"已重命名预设为: {new_name}")

    def delete_preset(self):
        """删除当前预设"""
        if self.current_preset == "Default":
            messagebox.showwarning("警告", "无法删除默认预设")
            return
        
        if messagebox.askyesno("确认删除", f"确定要删除预设 '{self.current_preset}' 吗?"):
            del self.presets[self.current_preset]
            self.current_preset = "Default"
            self.update_preset_menu()
            self.update_window_title()
            self.save_config()
            self.log(f"已删除预设")

    def select_preset(self, preset_name):
        """选择预设"""
        if preset_name in self.presets:
            preset_data = self.presets[preset_name]
            
            # 应用预设设置
            self.ai_model = preset_data.get('ai_model', 'deepseek-chat')
            self.temperature = preset_data.get('temperature', 1.3)
            self.system_prompt = preset_data.get('system_prompt', '你是一个专业的翻译助手，请将以下日文字幕翻译成中文，保持原有的格式和结构。')
            
            # 更新服务商
            provider = preset_data.get('provider', 'DeepSeek')
            self.provider_var.set(provider)
            self.provider_combo.set(provider)
            self.on_provider_change(None)  # 触发服务商变更
            
            # 更新UI
            self.model_combo.set(self.ai_model)
            self.temperature_scale.set(self.temperature)
            self.temperature_label.config(text=f"{self.temperature:.1f}")
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert("1.0", self.system_prompt)
            
            self.current_preset = preset_name
            self.update_preset_menu()
            self.update_window_title()
            self.save_config()
            self.log(f"已切换到预设: {preset_name}")

    def export_presets(self):
        """导出预设"""
        file_path = filedialog.asksaveasfilename(
            title="导出预设",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            defaultextension=".json"
        )
        if file_path:
            try:
                export_data = {
                    'presets': self.presets,
                    'current_preset': self.current_preset
                }
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                self.log(f"预设已导出到: {file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"导出预设失败: {str(e)}")

    def import_presets(self):
        """导入预设"""
        file_path = filedialog.askopenfilename(
            title="导入预设",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    import_data = json.load(f)
                
                imported_presets = import_data.get('presets', {})
                imported_current = import_data.get('current_preset', 'Default')
                
                # 合并预设
                for name, data in imported_presets.items():
                    if name not in self.presets:
                        self.presets[name] = data
                
                # 选择导入的当前预设
                if imported_current in self.presets:
                    self.select_preset(imported_current)
                
                self.log(f"预设已从 {file_path} 导入")
                
            except Exception as e:
                messagebox.showerror("错误", f"导入预设失败: {str(e)}")

    def update_window_title(self):
        """更新窗口标题"""
        title = f"字幕翻译器(预设:{self.current_preset})"
        self.root.title(title)

    def save_preset(self):
        """保存当前设置到预设"""
        if self.current_preset in self.presets:
            self.presets[self.current_preset] = {
                'ai_model': self.ai_model,
                'temperature': self.temperature,
                'system_prompt': self.system_prompt,
                'provider': self.provider_var.get()
            }
            self.save_config()
            self.log(f"已保存预设: {self.current_preset}")
        else:
            self.create_preset()

# 主程序入口
def main():
    root = tk.Tk()
    app = TranslationApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
