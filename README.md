# transby2
只是一个对个人顺手的工作流程自动化的小GUI软件，建议已经实现本地N卡跑[faster-whisper](https://github.com/SYSTRAN/faster-whisper)的朋友使用，如果搞不定请勿自我折磨。  
同时参考了一部分[N46Whisper](https://github.com/Ayanaminn/N46Whisper/)的代码，非常感谢聚聚的贡献。  
[whisper模型下载](https://github.com/openai/whisper/blob/main/whisper/__init__.py)请自行解决。  
个人认为whisper的时间轴无法满足对时间轴精度的需求，故程序中只输出文字丢给AI最后再人肉打轴完成字幕工作。不过圈内有使用提示词利用语义与时间轴协同多句合并输出的方法，相关技巧请参考[此教程](https://www.bilibili.com/video/BV1tFhCzcEUA)。  
请自行打包生成exe文件运行使用。
## 实现功能：
- 利用faster-whisper生成两份ass文件，一份原文另一份只保留文字信息方便丢给AI翻译
- 400行为一块丢给AI翻译纯粹是经验数值，不喜欢可以修改
- 在主界面可以选择是否使用AI翻译，关于AI提供商只写了DeepSeek，想用其他家的请自己修改源代码添加
- API秘钥本地加密存储
- 可以保留提示词，不同节目类型的提示词预设卡片考虑开发中
  
## 20251004更新
- 为无法本地运行whisper的朋友做了一个只有翻译功能的版本
- 现在已支持DeepSeek，OpenAI，Gemini的调用支持（后期会考虑增加自定义API url接入能力） 
<img width="2360" height="1398" alt="QQ20250930-174524" src="https://github.com/user-attachments/assets/baa7fdf2-bd81-4cee-86cf-343a228dacf7" />

<img width="2360" height="1398" alt="QQ20250930-174512" src="https://github.com/user-attachments/assets/e720ad0d-c70f-4336-8591-dc58c26b305e" />

