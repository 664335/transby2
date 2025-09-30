# whisperguikino
只是一个对个人顺手的工作流程自动化的小GUI软件，可以利用本地的N卡跑whisper，显卡对应的模型大小请参考[faster-whisper](https://github.com/SYSTRAN/faster-whisper/)安装后使用，安装方式请自行查询。  
同时参考了一部分[N46Whisper](https://github.com/Ayanaminn/N46Whisper/)的代码，非常感谢聚聚的贡献。
## 实现功能：
- 利用faster-whisper生成两份ass文件，一份原文另一份只保留文字信息方便丢给AI翻译
- 400行为一块丢给AI翻译纯粹是经验数值，不喜欢可以修改
- 在主界面可以选择是否使用AI翻译，关于AI提供商只写了DeepSeek，想用其他家的请自己修改源代码添加
- 请自行打包生成exe文件运行使用
