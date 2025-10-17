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
import re
from openai import OpenAI
from datetime import timedelta
import ctypes
# todolist：
# 支持 SRT、VTT 等更多字幕格式
# 支持更多AI服务商

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

class TranslationApp:
    def __init__(self, root):
        self.root = root        
        root.option_add("*Font", ("苹方 中等", 10))
        self.root.title("Tansonly(预设:Default)")
        # self.root.geometry("1200x1600")
        self.center_window()
        
        # 文件路径变量
        self.subtitle_file_var = tk.StringVar()


        # 预设管理
        self.presets = {}
        self.current_preset = "Default"
        self.preset_menu = None
        self.preset_combo = None
        self.is_modified = False  # 参数修改标记

        
        # AI翻译配置
        self.api_keys = {}  # 存储不同服务商的API密钥
        self.current_api_key = ""  # 当前服务商的API密钥
        self.api_key_status_cache = {}  # API密钥状态缓存
        self.ai_model = "deepseek-chat"
        self.temperature = 1.3
        self.system_prompt = "你是一个专业的翻译助手，请将以下日文字幕翻译成中文，保持原有的格式和结构。" 

        # 服务商配置
        self.provider_var = tk.StringVar(value="DeepSeek")
        self.providers = {
            "DeepSeek": {
                "api_url": "https://api.deepseek.com",
                "chat_url": "https://api.deepseek.com/chat/completions",
                "model_options": ["deepseek-chat", "deepseek-reasoner"]
            },
            "Genimi": {
                "api_url": "https://generativelanguage.googleapis.com/v1beta/openai/",                
                "model_options": ["gemini-2.5-pro","gemini-2.5-flash"]
            },
            "OpenAI": {
                "api_url": "https://api.openai.com",
                "chat_url": "https://api.openai.com/chat/completions",
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
        self.save_preset()


    def create_translation_widgets(self):
        """创建翻译界面的UI组件"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 服务商选择框架（最上方）
        provider_frame = ttk.LabelFrame(main_frame, text="AI服务商选择")
        provider_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(provider_frame, text="服务商:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        self.provider_combo = ttk.Combobox(provider_frame, values=list(self.providers.keys()), width=15, font=("苹方 粗体", 10))
        self.provider_combo.set(self.provider_var.get())
        self.provider_combo.grid(row=0, column=1, padx=5, sticky="w")
        self.provider_combo.bind("<<ComboboxSelected>>", self.on_provider_change)

        # API设置框架
        api_frame = ttk.LabelFrame(main_frame, text="API设置")
        api_frame.pack(pady=10, padx=10, fill="x")
        ttk.Label(api_frame, text="API密钥:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        self.api_key_entry = ttk.Entry(api_frame, width=50, show="*", font=("苹方 粗体", 10))
        self.api_key_entry.grid(row=0, column=1, padx=5, sticky="w")
        ttk.Button(api_frame, text="保存API密钥", command=self.save_api_key).grid(row=0, column=2, padx=5)
        
        # 模型参数框架
        params_frame = ttk.LabelFrame(main_frame, text="模型参数(温度越高模型的回答越发散)")
        params_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(params_frame, text="模型:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        self.model_combo = ttk.Combobox(params_frame, values=["deepseek-chat", "deepseek-reasoner"], width=20)
        self.model_combo.set(self.ai_model)
        self.model_combo.grid(row=0, column=1, padx=5, sticky="w")      
        self.model_combo.bind("<<ComboboxSelected>>", lambda e: self.check_preset_if_modified())
        
        ttk.Label(params_frame, text="温度:", font=("苹方 中等", 10)).grid(row=0, column=2, padx=5, sticky="w")
        self.temperature_scale = ttk.Scale(params_frame, from_=0.0, to=2.0, value=self.temperature, orient="horizontal")
        self.temperature_scale.grid(row=0, column=3, padx=5, sticky="w")
        # 设置温度刻度的步进为0.1
        
        self.temperature_scale.configure(command=lambda value: [self.update_temperature_label(value), self.check_preset_if_modified()])
        self.temperature_label = ttk.Label(params_frame, text=f"{self.temperature:.1f}")
        self.temperature_label.grid(row=0, column=4, padx=5, sticky="w")
        
        # 预设框架
        preset_frame = ttk.LabelFrame(main_frame, text="预设")
        preset_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(preset_frame, text="预设:", font=("苹方 中等", 10)).grid(row=0, column=0, padx=5, sticky="w")
        
        # 预设下拉菜单按钮
        self.preset_button = ttk.Menubutton(preset_frame, text="预设", width=15)
        self.preset_menu = tk.Menu(self.preset_button, tearoff=0)
        self.preset_button.configure(menu=self.preset_menu)
        self.preset_button.grid(row=0, column=1, padx=5, sticky="w")  

        # 字幕文件操作框架
        subtitle_frame = ttk.LabelFrame(main_frame, text="字幕文件操作")
        subtitle_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Button(subtitle_frame, text="提交字幕", command=self.submit_subtitle).grid(row=0, column=0, padx=5)
        ttk.Button(subtitle_frame, text="开始翻译", command=self.start_translation).grid(row=0, column=1, padx=5)
        
        # 字幕文件路径显示
        ttk.Label(subtitle_frame, textvariable=self.subtitle_file_var, width=50, font=("苹方 中等", 10)).grid(row=0, column=2, padx=5, sticky="w")

        # 系统提示词框架
        prompt_frame = ttk.LabelFrame(main_frame, text="提示词")
        prompt_frame.pack(pady=10, padx=10, fill="both", expand=True)
        
        self.prompt_text = tk.Text(prompt_frame, height=8, width=80, font=("苹方 粗体", 11))
        self.prompt_text.insert("1.0", self.system_prompt)
        self.prompt_text.pack(pady=5, padx=5, fill="both", expand=True)
        
        # 绑定文本变化事件来检测参数修改        
        self.prompt_text.bind("<KeyRelease>", lambda e: self.check_preset_if_modified())
        
        ttk.Button(prompt_frame, text="保存预设", command=self.save_preset).pack(pady=5)
        
        # 日志输出
        self.log_text = tk.Text(main_frame, height=10, state=tk.DISABLED)
        self.log_text.pack(pady=10, padx=10, fill="both")
    def center_window(self):
        """将窗口居中显示"""
        self.root.update_idletasks()
        width = 1200
        height = 1200
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def submit_subtitle(self):
        """提交字幕文件"""
        file_path = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=[("字幕文件", "*.ass *.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            self.subtitle_file_var.set(file_path)
            self.log(f"已选择字幕文件: {file_path}")

    def start_translation(self):
        """开始翻译字幕(针对单纯字幕翻译任务，听写后再翻译入口不在此)"""
        if not self.subtitle_file_var.get():
            messagebox.showerror("错误", "请先提交字幕文件")
            return
        
        if not self.current_api_key:
            messagebox.showerror("错误", "请先设置API密钥")
            return
        
        # 使用新的API密钥准备方法
        success, message = self.ensure_api_key_ready()
        if not success and message != "用户取消解密":            
            messagebox.showerror("错误", f"API密钥准备失败: {message}")
            return
        

        self.save_preset()
        # 禁用按钮防止重复点击
        self.log("开始翻译字幕...")
        self.save_preset()
        # 启动后台线程
        if success:
            threading.Thread(target=self.run_batch_translation, daemon=True).start()
        elif message == "用户取消解密":
            self.log("用户取消解密，翻译任务未启动")
            return
        

 
    def parse_ass_dialogue(self, line):
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
        # 处理Dialogue行
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
        【优化版】根据API返回结果重建ASS。
        直接将原始头部和新生成的Dialogue行拼接。
        """
        if isinstance(api_response, str):
            try:
                parsed_response = json.loads(api_response)
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")
                print(f"原始响应: {api_response}")
                return []
        else:
            parsed_response = api_response
        
        new_dialogue_lines = []
        
        # 确保解析后的响应包含translatedSentences
        if 'translatedSentences' not in parsed_response:
            print("API响应中缺少translatedSentences字段")
            print(f"响应内容: {parsed_response}")
            return []
        
        for sentence_obj in parsed_response['translatedSentences']:
            translated_text = sentence_obj['sentence']
            related_items = sentence_obj['relatedInputItems']
            
            if not related_items:
                continue
                
            first_item_timestamp = related_items[0]['timestamp']
            last_item_timestamp = related_items[-1]['timestamp']
            
            # 确保时间戳在context_map中存在
            if first_item_timestamp not in context_map or last_item_timestamp not in context_map:
                print(f"时间戳 {first_item_timestamp} 或 {last_item_timestamp} 在context_map中不存在")
                continue
                
            metadata = context_map[first_item_timestamp]
            
            start_time = metadata['Start']
            end_time = context_map[last_item_timestamp]['End']
            
            new_line = (
                f"Dialogue: {metadata['Layer']},{start_time},{end_time},"
                f"{metadata['Style']},{metadata['Name']},{metadata['MarginL']},"
                f"{metadata['MarginR']},{metadata['MarginV']},{metadata['Effect']},"
                f"{translated_text}"
            )
            new_dialogue_lines.append(new_line)
            
        return new_dialogue_lines
    
    def run_batch_translation(self):
        """执行分批翻译"""
        try:
            subtitle_file = self.subtitle_file_var.get()
            file_ext = os.path.splitext(subtitle_file)[1].lower()         

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

            # 分批处理(50行一批是测试下来AI不会卡死的行数，到100输出就会卡住)
            batch_size = 50
            total_batches = (len(dialogue_lines) + batch_size - 1) // batch_size
            
            self.log(f"开始分批翻译，共 {len(dialogue_lines)} 行，分为 {total_batches} 批")
            
            all_translated_lines = []
            total_token_usage = 0

            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min((batch_num + 1) * batch_size, len(dialogue_lines))
                
                batch_lines = dialogue_lines[start_idx:end_idx]
                api_input, context = self.prepare_input_for_api(batch_lines)
                
                # batch_text = ''.join(api_input)
                batch_text = json.dumps(api_input, indent=2, ensure_ascii=False)                
                self.log(f"正在翻译第 {batch_num + 1}/{total_batches} 批 ({len(batch_lines)} 行)")
                
                # 调用AI翻译API
                translated_batch, token_usage = self.call_ai_translation_api(batch_text) 
                total_token_usage += token_usage 

                # 重建ASS字幕行            
                current_batch_lines = self.reconstruct_ass_from_response(translated_batch, context) 

                # 保存已翻译字幕行               
                all_translated_lines.extend(current_batch_lines) 

                # if batch_num < total_batches - 1:
                #     all_translated_lines.append('\n')
                self.log(f"第 {batch_num + 1} 批翻译完成")  

            processed_lines = []
            
            translated_lines = []
            translated_lines = [str(line).strip() for line in all_translated_lines if str(line).strip()]
            for line in translated_lines:
                if line.strip():
                    # 分离时间轴部分和文本部分
                    parts = line.split(',', 9)  # ASS格式有9个逗号分隔的字段
                    if len(parts) == 10:
                        # 前9部分是时间轴和样式信息，第10部分是文本
                        metadata = ','.join(parts[:9])
                        text_content = parts[9]
                        
                        # 对文本部分进行标点符号替换
                        processed_text = text_content.replace('，', ' ').replace('。', ' ').replace('、', ' ').replace('"', '「').replace('"', '」').replace('《', '『').replace('》', '』').replace('！', ' ').replace('吗？', '吗').replace('？', '吗')
                        
                        # 重新组合成完整的ASS行
                        processed_line = f"{metadata},{processed_text}"
                        processed_lines.append(processed_line)
                    else:
                        # 如果格式不对，保持原样
                        processed_lines.append(line)

            base_name = os.path.splitext(os.path.basename(subtitle_file))[0]
            output_dir = os.path.dirname(subtitle_file)
            output_file = os.path.join(output_dir, f"{base_name}_readytogo.ass")
            if file_ext == '.ass': 
                with open(output_file, 'w', encoding='utf-8') as f:
                    # 写入原始ASS头部
                    f.writelines(header_lines)    
                    # 写入处理后的翻译内容
                    # f.write('\n'.join(processed_lines))    
                    for line in processed_lines:
                        f.write(line + '\n')            
                    # 写入原始字幕内容
                    f.writelines(dialogue_lines)                      
            else:
                all_translated_content = processed_lines
                # 保存翻译结果
                output_dir = os.path.dirname(subtitle_file)
                base_name = os.path.splitext(os.path.basename(subtitle_file))[0]
                output_file = os.path.join(output_dir, f"{base_name}_translated.txt")               
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(all_translated_content))  

            self.log(f"翻译完成！结果已保存到: {output_file},token消耗为{total_token_usage}")
            
        except Exception as e:
            self.log(f"翻译失败: {str(e)}")

    def call_ai_translation_api(self, content):
        """调用AI翻译API，包含重试机制"""
        max_retries = 3
        retry_delay = 5  # 秒
        
        # 获取当前服务商配置
        selected_provider = self.provider_var.get()
        provider_config = self.providers.get(selected_provider, self.providers["DeepSeek"])
        api_url = provider_config["api_url"]
        for attempt in range(max_retries):
            # 全都用OpenAI SDK库调用            
            try:
                client = OpenAI(api_key=self.current_api_key, base_url=api_url)
                translate_tool = [
                    {
                        "type": "function",
                        "function": {
                            "name": "translated_response",
                            "description": "Formats and structures the final translation output. Use this function to return the translated text, ensuring each translated sentence is linked back to its original source text and timestamp.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "translatedSentences": {
                                        "type": "array",
                                        "description": "An array of translated sentence objects. Each object contains a piece of the translated text and links to the original input items it corresponds to.",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "sentence": {
                                                    "type": "string",
                                                    "description": "A single, complete translated sentence."
                                                },
                                                "relatedInputItems": {
                                                    "type": "array",
                                                    "description": "An array of the original source objects that correspond to this translated sentence.",
                                                    "items": {
                                                        "type": "object",
                                                        "properties": {
                                                            "timestamp": {
                                                                "type": "number",
                                                                "description": "The timestamp of the original text."
                                                            },
                                                            "text": {
                                                                "type": "string",
                                                                "description": "The original source text."
                                                            }
                                                        },
                                                        "required": ["timestamp", "text"]
                                                    }
                                                }
                                            },
                                            "required": ["sentence", "relatedInputItems"]
                                        }
                                    }
                                },
                                "required": ["translatedSentences"]
                            }
                        }
                    }
                ]
                response = client.chat.completions.create(
                    model=self.ai_model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": f"以下是字幕原文以及时间信息:\n{content}"},
                        
                ],
                    tools=translate_tool, 
                    tool_choice = "auto",
                    temperature=self.temperature,
                    stream=False
                ) 
                
                # DeepSeek和OpenAI响应格式
                return response.choices[0].message.tool_calls[0].function.arguments, response.usage.total_tokens

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    self.log(f"请求超时，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    return None, f"请求超时，重试{max_retries}次后仍失败"
            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    self.log(f"连接错误，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    return None, f"连接错误，重试{max_retries}次后仍失败"
            except Exception as e:
                if attempt < max_retries - 1:
                    self.log(f"未知错误: {str(e)}，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    self.log(f"连接错误，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    self.log(f"连接错误，重试{max_retries}次后仍失败")
                    return None
            except Exception as e:
                if attempt < max_retries - 1:
                    self.log(f"未知错误: {str(e)}，{retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    self.log(f"未知错误: {str(e)}，重试{max_retries}次后仍失败")
                    return None
        
        self.log(f"重试{max_retries}次后仍失败")
        return None
    
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

    def update_temperature_label(self, value):
        """更新温度标签"""
        self.temperature_label.config(text=f"{float(value):.1f}")

    def show_api_key_dialog(self):
        """显示API密钥输入对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("API设置")
        dialog.geometry("500x200")
        dialog.transient(self.root)
        dialog.grab_set()        
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

    def validate_api_key(self, api_key):
        """验证API密钥有效性"""
        current_provider = self.provider_var.get()
        provider_config = self.providers.get(current_provider, self.providers["DeepSeek"])
        api_url = provider_config["api_url"]  
        if current_provider == "Genimi":
            # 延迟导入Google库，避免在程序启动时初始化
            try:
                import google.generativeai as genai
                from google.api_core import exceptions
            except ImportError:
                self.log("错误: 无法导入Google库，请确保已安装google-generativeai")
                return False
                
            test_model = 'gemini-2.5-flash'
            genai.configure(api_key=api_key)
            try:
                # 创建模型实例
                model = genai.GenerativeModel(test_model)
                
                # 发送测试请求
                response = model.generate_content("Hello, please respond with 'API is working'")
                
                # 检查响应
                if response.text:
                    # 移除这里的成功日志，由save_api_key函数统一处理
                    return True
                else:    
                    self.log("Gemini API响应为空")                
                    return False
            except exceptions.PermissionDenied:
                # 捕获权限错误，这通常意味着API密钥是错误的或未启用服务
                self.log("API密钥验证失败：权限被拒绝。请仔细检查您的API密钥是否正确，以及是否已在Google AI Studio中启用了API服务。")
                return False
            except exceptions.Unauthenticated:
                # 捕获身份验证失败错误
                self.log("API密钥验证失败：身份验证错误。这几乎总是由于API密钥不正确或格式错误导致的。")
                return False
            except Exception as e:
                # 捕获其他所有可能的异常，如网络连接问题
                self.log(f"验证过程中发生未知错误，请检查您的网络连接或稍后再试。详细错误信息：{e}")
                return False
                      
        else:
            try:
                # DeepSeek和OpenAI API验证
                api_url = "https://api.deepseek.com/chat/completions"
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
        config_file = "transonly_config.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
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
                    
                    # 更新UI
                    self.api_key_entry.delete(0, tk.END)
                    if self.current_api_key and self.current_api_key != "***已加密***":
                        self.api_key_entry.insert(0, "***已加密***")
                    else:
                        self.api_key_entry.insert(0, self.current_api_key)
                    
                    # 更新服务商选择
                    self.provider_combo.set(self.provider_var.get())
                    # 避免在程序启动时触发服务商变更，防止Google库过早初始化
                    # self.on_provider_change(None)  # 触发服务商变更以更新模型选项
                    
                    # 手动更新模型选项，避免调用on_provider_change
                    selected_provider = self.provider_var.get()
                    if selected_provider in self.providers:
                        provider_config = self.providers[selected_provider]
                        self.model_combo['values'] = provider_config["model_options"]
                    
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
        config_file = "transonly_config.json"
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
            # self.log("配置已保存")
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
            password = tk.simpledialog.askstring(
                "解密密码", 
                f"请输入解密密码 (剩余尝试次数: {max_attempts - attempts}):"
            )
            
            # 用户点击取消或关闭对话框
            if password is None:
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
        self.root.title(f"Transonly(预设:{self.current_preset})")

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
                'provider': self.provider_var.get()
            }
            
            self.current_preset = preset_name
            self.update_preset_menu()
            self.save_preset()
            self.save_config()
            self.log(f"已创建预设: {preset_name}")

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
            self.save_config()
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
                self.current_preset = preset_name
                
                # 更新UI
                self.model_combo.set(self.ai_model)
                self.temperature_scale.set(self.temperature)
                self.temperature_label.config(text=f"{self.temperature:.1f}")
                self.prompt_text.delete("1.0", tk.END)
                self.prompt_text.insert("1.0", self.system_prompt)
                
                # 更新服务商选择
                self.provider_combo.set(self.provider_var.get())
                                
                # 手动更新模型选项，避免调用on_provider_change
                selected_provider = self.provider_var.get()
                if selected_provider in self.providers:
                    provider_config = self.providers[selected_provider]
                    self.model_combo['values'] = provider_config["model_options"]                  
                
                self.update_window_title()
                self.update_preset_menu()
                self.save_preset()
                self.save_config()
                
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
                    # self.log(f"已保存预设 '{self.current_preset}' 并切换到 '{preset_name}'")
                else:  # 否 - 不保存修改
                    self.log(f"已切换到预设 '{preset_name}'（未保存当前修改）")
            
            # 应用新预设的配置
            self.ai_model = preset['ai_model']
            self.temperature = preset['temperature']
            self.system_prompt = preset['system_prompt']
            self.provider_var.set(preset['provider'])
            self.current_preset = preset_name
            
            # 更新UI
            self.model_combo.set(self.ai_model)
            self.temperature_scale.set(self.temperature)
            self.temperature_label.config(text=f"{self.temperature:.1f}")
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert("1.0", self.system_prompt)
            
            # 更新服务商选择
            self.provider_combo.set(self.provider_var.get())
            
            # 手动更新模型选项，避免调用on_provider_change
            selected_provider = self.provider_var.get()
            if selected_provider in self.providers:
                provider_config = self.providers[selected_provider]
                self.model_combo['values'] = provider_config["model_options"]
            
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

    def check_preset_if_modified(self):
        """检查预设参数是否被修改"""
        self.is_modified = False
        
        if self.current_preset in self.presets:
            preset_data = self.presets[self.current_preset]
            current_prompt = self.prompt_text.get("1.0", tk.END).strip()
            current_model = self.model_combo.get()
            current_temperature = float(self.temperature_scale.get())
            
            # 检查是否有参数改变
            if (current_prompt != preset_data.get("system_prompt", "") or
                current_model != preset_data.get("ai_model", "") or
                current_temperature != preset_data.get("temperature", 1.3)):
                self.is_modified = True    

    def update_window_title(self):
        """更新窗口标题"""
        if self.is_modified:
            self.root.title(f"Transonly(预设:*{self.current_preset})")
        else:
            self.root.title(f"Transonly(预设:{self.current_preset})")

    def save_preset(self):
        """保存当前预设"""
        if not self.current_preset:
            messagebox.showwarning("警告", "请先选择或创建一个预设")
            return
        
        # 获取当前系统提示词 模型 温度
        current_prompt = self.prompt_text.get("1.0", tk.END).strip()
        current_model = self.model_combo.get()
        current_temperature = round(float(self.temperature_scale.get()), 1)  # 只保留一位小数

        # 保存预设信息
        self.presets[self.current_preset] = {
            "system_prompt": current_prompt,
            "ai_model": current_model,
            "temperature": current_temperature,
            'provider': self.provider_var.get()
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
        self.root.title(f"Transonly(预设:{self.current_preset})")
        # self.log(f"已保存预设: {self.current_preset}")


def main():
    """主程序入口"""
    root = tk.Tk()
    app = TranslationApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
