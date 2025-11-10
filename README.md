# Transby2
本软件只是用来作为减轻字幕工作负担的工具，并不能用于字幕直出。  
软件因其实现的两个核心功能，即转写(transcript)和翻译(translate)而得名。  
建议已经实现本地N卡跑[faster-whisper](https://github.com/SYSTRAN/faster-whisper)的朋友使用，如果搞不定请勿自我折磨。  
程序能够输出带时间轴的熟肉字幕，之后人肉校对和微调时间轴即可完成字幕工作。  
程序的字幕翻译方式和提示词绑定很深，如果不会使用请联系作者，请勿自行盲目尝试。  
请自行打包生成exe文件运行使用。
## 实现功能：
- 利用faster-whisper生成两份ass文件，一份原文另一份把无时间轴译后字幕叠在原文字幕上方便直接拖入字幕软件开始打轴+校对
- API秘钥本地加密存储
- 可以针对不同的墙头以预设卡片保存提示词~~你甚至可以建立一个词库方便LLM纠正听写错误~~  
## 20251004更新
- 为无法本地运行whisper的朋友做了一个只有翻译功能的版本，可以将带时间轴字幕叠在原始字幕上输出为ASS文件方便校对
- 现在已支持DeepSeek，OpenAI，Gemini，OpenRouter（后期会考虑增加自定义API url接入选项，~~方便大家白嫖各家服务商~~） 

## 20251017更新  
- 增加VAD开关按钮
- 使用funtion calling确保模型结构化输出，保证程序工作稳定性
- 使用苹方字体提升UI美观度

<img width="1204" height="947" alt="image" src="https://github.com/user-attachments/assets/7fe0d00d-0158-40aa-9d82-1836b439fcca" />


<img width="1204" height="947" alt="image" src="https://github.com/user-attachments/assets/5db22b40-dcbf-4789-ad23-a3aa2d739298" />

## 20251110更新  
- 应monad哥哥的意见增加时间段总结功能，利用AI对字幕内容进行总结
- 由于funtion calling方式会导致解析不稳定，最后还是改为json output方式实现稳定字幕解析与时间轴重建
- 图标设置为为重型猎鹰火箭与月球重合照片

<img width="1186" height="1640" alt="image" src="https://github.com/user-attachments/assets/7d0f295c-91b0-47c3-89da-296fa1e6515c" />




