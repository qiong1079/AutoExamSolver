# AutoExamHelper - 自动考试助手

[![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Beta-orange)](https://github.com/your-username/AutoExamHelper)

一个基于 Selenium + API 调用的自动化考试助手，支持网页端考试的自动答题、提交等全流程操作，提供可视化悬浮窗管理界面，内置完善的错误处理和重试机制。

## 📋 功能特点

### 核心功能
- 🖥️ **可视化悬浮窗管理**：简洁的 TKinter 悬浮窗，支持状态监控、日志查看、参数配置
- 🔍 **智能元素定位**：多方式定位网页元素，兼容不同 HTML 结构的「开始考试」「提交答案」等按钮
- 🤖 **API 智能答题**：对接大模型 API，批量生成题目答案并自动填写
- 🔄 **自动循环考试**：支持多轮考试自动执行，完成后自动返回考试列表
- 📊 **Token 用量监控**：实时监控 API Token 消耗，防止超额使用
- ⚡ **高稳定性设计**：内置多级重试机制、指数退避策略、完善的异常处理
- 🚀 **极速操作优化**：最小化等待时间，使用 JS 执行点击操作提升效率
- 🛡️ **网络适配**：支持代理配置、禁用 HTTPS 警告、国内镜像源适配

### 技术特性
- 线程安全设计，支持任务暂停/停止
- 详细的日志记录（文件 + 界面双端输出）
- 兼容不同网页布局的元素定位策略
- API 调用失败自动重试（指数退避）
- 浏览器自动化初始化（自动下载 ChromeDriver）

## 🛠️ 环境要求

### 基础环境
- Python 3.8 及以上版本
- Google Chrome 浏览器（最新版）
- 网络环境可访问目标考试网站和 API 服务

### 依赖库
```txt
threading
time
logging
sys
re
json
requests
traceback
bs4
selenium
webdriver-manager
tkinter
ctypes
urllib3
```
## 🚀 快速开始
### 1. 克隆仓库
```bash
git clone https://github.com/your-username/AutoExamHelper.git
cd AutoExamHelper
```
### 2. 安装依赖
```bash
pip install -r requirements.txt
```
若未提供 requirements.txt，可手动安装：
```bash
pip install beautifulsoup4 selenium webdriver-manager requests urllib3
```
### 3. 配置国内镜像源（可选，加速 ChromeDriver 下载）
```bash
# Windows
set CHROMEDRIVER_CDNURL=https://registry.npmmirror.com/-/binary/chromedriver/
set WDM_LOCAL=1

# Linux/Mac
export CHROMEDRIVER_CDNURL=https://registry.npmmirror.com/-/binary/chromedriver/
export WDM_LOCAL=1
```
### 4. 启动程序
```bash
python auto_exam.py
```
## 使用说明
### 1. 初始化阶段
1. 启动程序后，会自动初始化 Chrome 浏览器并打开目标考试网站
2. **手动完成账号登录**（程序不会处理登录，需用户手动操作）
3. 登录完成后等待 3 秒，确保页面完全加载
### 2. 配置 API 参数
在悬浮窗的「API 配置」区域填写以下信息（以下示例内容不做固定）：

| 参数名 | 说明 | 示例 |
| ---- | ---- | ---- |
| API Key | 大模型 API 的认证密钥 | sk-xxxxxxxxxxxxxxxxxxxxxxxx |
| API URL | API 接口地址 | https://ark.cn-beijing.volces.com/api/v3/chat/completions |
| 模型名称 | 使用的大模型名称 | doubao-seed-1-6-lite-251015 |
| Token 配额   | 允许使用的最大 Token 数 | 100000 |
| 代理（可选）   | 网络代理地址 | http://127.0.0.1:7890 |

### 3. 启动 / 停止任务
- **启动任务**：点击「启动任务」按钮，程序会自动执行考试流程

- **停止任务**：点击「停止任务」按钮，程序会立即终止当前操作

### 4. 监控运行状态
-  悬浮窗顶部显示当前状态、考试轮次、Token 使用量
- 「运行日志」区域实时显示程序执行日志
-  详细日志会同步写入 auto_exam_log.log 文件

## ⚙️ 核心配置说明
### **全局配置（代码顶部）**
# 配置项参数说明
| 配置项         | 默认值                                      | 说明                               |
| -------------- | ------------------------------------------- | ---------------------------------- |
| TARGET_URL     | https://sdld-gxk.yxlearning.com/my/index    | 目标考试网站地址                   |
| WAIT_TIMEOUT   | 15                                          | 元素等待超时时间（秒）             |
| RETRY_TIMES    | 2                                           | 元素操作重试次数                   |
| API_RETRY_TIMES| 3                                           | API 调用重试次数                   |
| API_RETRY_DELAY| 3                                           | API 重试初始间隔（秒，指数退避）|
| API_TIMEOUT    | 45                                          | API 请求超时时间（秒）             |
### API配置（悬浮窗动态设置）参数说明
| 配置项   | 必填状态 | 说明                     |
|----------|----------|--------------------------|
| API Key  | 必填     | 用于API身份验证          |
| API URL  | 必填     | 大模型的聊天补全接口地址 |
| 模型名称 | 必填     | 对应使用的大模型标识     |
| Token配额| 必填     | 防止API调用超额          |
| 代理     | 可选     | 用于访问外网API服务      |
## 工具使用注意事项
本注意事项为工具使用的核心指引，涵盖合规、操作、环境等维度，用于保障工具稳定、合规运行：

1. **合规性**：工具仅限学习与研究场景使用，禁止用于违反网站规定、公司制度或法律法规的行为。
2. **登录要求**：程序不支持自动登录，需用户手动完成账号登录后，再启动任务。
3. **网络环境**：需确保网络可访问目标考试网站与API服务，网络受限场景下需配置代理。
4. **Token管理**：合理设置Token配额，避免超额使用产生额外费用。
5. **异常处理**：若出现元素定位失败问题，需检查目标网站的HTML结构是否发生变更。
6. **浏览器兼容**：建议使用最新版本Chrome浏览器，以规避浏览器驱动的兼容性问题。
7. **线程安全**：禁止同时启动多个任务，否则可能导致浏览器操作冲突。
## 🐞 常见问题
### Q1: 浏览器启动失败
- 检查 Chrome 浏览器是否安装
- 确保 ChromeDriver 版本与 Chrome 浏览器版本匹配
- 配置国内镜像源重新下载 ChromeDriver
### Q2: 无法找到「开始考试」按钮
- 确认已手动登录并进入正确的考试页面
- 检查目标网站的 HTML 结构是否变化，可调整元素定位的 XPATH
### Q3: API 调用失败
- 检查 API Key 是否正确
- 验证 API URL 和模型名称是否匹配
- 测试网络是否可访问 API 服务器（可配置代理）
- 查看日志文件 auto_exam_log.log 获取详细错误信息
### Q4: 答题后提交失败
- 检查是否所有题目都已正确填写
- 确认目标网站的提交按钮定位是否准确
### Q5: 工具不是完美的，目前已知问题
- API调用超时，原则上是模型大小的问题，作者调用的是小模型测试的，使用者可以切换其他大模型
- 作答选项选择不全，本质也跟模型输出的结果有关，其实不影响使用，有漏答，也可以及格压线通过
- 就算没有漏答，不及格，跟模型有关，模型会重复学习，会通关的，给AI一些时间


## 📄 免责声明
1. 本工具仅用于学习和研究 Python 自动化、Web 爬虫、API 调用等技术，请勿用于商业或违规用途
2. 使用本工具需遵守目标网站的用户协议和相关法律法规，如因违规使用产生的一切后果由用户自行承担
3. 作者不对本工具的功能性、稳定性做任何保证，不对使用本工具造成的任何损失承担责任
4. 禁止将本工具用于任何非法或未经授权的场景
## 📞 反馈与贡献
- 如有问题或建议，欢迎提交 Issue
- 欢迎 Fork 并提交 Pull Request 改进代码
## 📜 许可证
本项目采用 MIT 许可证开源，详见 LICENSE 文件。