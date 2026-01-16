# AutoExamSolver

[![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Beta-orange)](https://github.com/your-username/AutoExamHelper)

一个基于 Selenium + 火山大模型 API 实现的自动化考试辅助工具，支持自动提取题目、AI 批量答题、自动填写答案，适配多种考试页面结构，单文件即可运行。

## 项目简介
本工具专为在线考试场景设计，通过 Selenium 模拟浏览器操作提取考试题目，调用火山大模型 API 批量解答题目，再自动完成答案填写和提交，全程自动化执行，支持多轮考试循环。

## 核心功能
- 🚀 单文件运行：无需拆分模块，单个 Python 文件即可完成所有功能
- 🔍 智能题目提取：自动识别判断题 / 单选题 / 多选题，支持降级提取方案
- 🤖 AI 批量答题：调用火山大模型 API 批量解答，减少请求次数
- ✍️ 自动填写答案：智能匹配选项并自动选中，包含作答结果校验和重试机制
- 🔐 安全配置：交互式输入 API Key，避免密钥硬编码
- 🔄 循环执行：自动多轮考试，直到无「进入考试」按钮为止

## 环境准备
1. 安装依赖
```bash
pip install selenium>=4.0.0 beautifulsoup4>=4.12.0 requests>=2.31.0
```
2. 下载 ChromeDriver
- 下载项目的 ChromeDriver.exe文件
- 将 chromedriver.exe 放入程序同级目录，或修改代码中 driver_path 路径
3. 获取火山大模型 API Key
- 前往 火山方舟平台 注册并创建应用
- 获取 API Key（运行时输入，无需硬编码到代码中）

## 使用步骤
1. 配置修改
- 修改代码中 driver_path 为本地 ChromeDriver 实际路径
- 根据考试平台修改 base_url 为实际考试列表页地址

2. 运行程序
``` bash
python auto_exam_solver.py
```
3. 操作流程
- 运行程序后，按提示输入火山大模型 API Key
- 可选输入代理地址（无需代理直接回车）
- 程序自动打开浏览器并加载考试页面
- 手动完成登录操作后，按回车继续
程序自动执行：查找考试 → 提取题目 → AI 答题 → 自动填写 → 提交答案
- 支持多轮考试循环，直到无考试可参加

4. 打包成 EXE（可选）
```bash
# 安装PyInstaller
pip install pyinstaller

# 打包（替换 your_icon.ico 为实际图标路径）
pyinstaller -F -w -n "你想起的程序名" auto_exam_solver.py
```

## 注意事项
1. 环境兼容
- Chrome 浏览器版本需与 ChromeDriver 版本一致
- 推荐使用 Python 3.7+ 版本
- 打包后需将 chromedriver.exe 与 EXE 文件放在同一目录
2. API 使用
- 火山大模型 API 调用会产生费用，请合理控制调用次数
- 单次请求 token 上限可在 API_CONFIG 中调整
- 确保 API Key 有足够的调用额度
3. 反爬策略
- 程序已添加反检测机制，但请勿高频次执行
- 可适当增加 time.sleep() 等待时间，降低检测风险
4. 页面适配

- 如考试页面结构不同，需调整：
  - `extract_and_recognize()` 中的题目提取逻辑
  - `auto_answer()` 中的选项定位逻辑
  - `check_and_click_exam_button()` 中的按钮定位逻辑
5. 免责声明
- 本工具仅用于**学习和测试目的**
- 使用前请遵守考试平台的用户协议和相关法律法规
- 禁止用于违规考试场景，违者后果自负

## 常见问题
**Q1: 提示找不到 ChromeDriver？**

A1: 检查 ChromeDriver 路径是否正确，或是否与 Chrome 版本匹配。

**Q2: API 调用失败？**

A2:
- 检查 API Key 是否有效
- 确认网络可访问火山方舟 API 地址
- 检查代理配置是否正确（如有）

**Q3: 无法提取题目？**

A3:

- 确认考试页面已加载完成
- 检查页面元素 class 名称是否匹配（如 questionDesc、options）
- 程序会自动触发降级提取方案

**Q4: 无法选中答案？**

A4:

- 检查选项元素定位逻辑是否匹配页面结构
- 程序内置重试机制，可查看控制台报错信息调整定位方式
## 许可证
MIT License - 自由使用、修改和分发，请保留原作者信息。






