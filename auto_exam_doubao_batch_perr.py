import threading
import time
import logging
import sys
import re
import json
import requests
import traceback
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.service import Service  # 必须导入 Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, \
    JavascriptException, SessionNotCreatedException  # 添加新异常类型
# --- 移除 webdriver-manager 相关导入 ---
# from webdriver_manager.chrome import ChromeDriverManager
# --- END 移除 webdriver-manager 相关导入 ---
from queue import Queue
import os
import tkinter as tk
from tkinter import ttk, messagebox
import ctypes
import subprocess

# ===================== 提前设置环境变量（核心修复：解决下载路径问题） =====================
# 1. 国内镜像源（优先）
# os.environ['CHROMEDRIVER_CDNURL'] = 'https://registry.npmmirror.com/-/binary/chromedriver/'
# 2. 禁用自动更新
# os.environ['WDM_LOCAL'] = '1'
# 3. 缓存路径改为用户目录（避免短路径/权限问题）
# CHROME_DRIVER_CACHE = os.path.join(os.path.expanduser("～"), "AutoExam", "chromedriver")
# os.environ['WDM_CACHE_DIR'] = CHROME_DRIVER_CACHE
# 注释掉上面这3行，让 webdriver-manager 使用默认缓存目录

# ===================== 新增：基础日志配置（解决初始化依赖问题） =====================
# 先初始化一个临时的基础日志，用于目录创建等早期操作
def init_basic_logger():
    basic_logger = logging.getLogger("BasicInit")
    basic_logger.setLevel(logging.INFO)
    basic_logger.handlers.clear()

    # 控制台输出
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    basic_logger.addHandler(console_handler)
    return basic_logger


basic_logger = init_basic_logger()

# ===================== 新增：禁用InsecureRequestWarning警告 =====================
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===================== 全局配置（平衡速度与稳定性） =====================
TARGET_URL = "https://sdld-gxk.yxlearning.com/my/index"
WAIT_TIMEOUT = 15  # 显式等待超时：15秒
RETRY_TIMES = 2  # 重试次数：2次
NO_SLEEP = 0
SHORT_SLEEP = 0.2  # 极短等待：0.2秒
MINI_SLEEP = 1.0  # 最小等待：1.0秒
LONG_SLEEP = 3.0  # 长等待：3.0秒

# API 重试配置
API_RETRY_TIMES = 3  # API 失败重试次数
API_RETRY_DELAY = 3  # API 重试初始间隔（秒），改为指数退避
API_TIMEOUT = 45  # 【修改1】API超时时间调整到45秒

# 全局线程控制
STOP_EVENT = threading.Event()
PAUSE_EVENT = threading.Event()
STATUS_QUEUE = Queue()  # 悬浮窗状态更新队列
COMMAND_QUEUE = Queue()  # 悬浮窗指令队列

# 全局锁
DRIVER_LOCK = threading.Lock()
driver = None
is_exam_started = False
cycle_count = 0  # 当前轮次
is_browser_ready = False  # 浏览器是否已准备好（登录页面已加载）

# API配置（由悬浮窗动态设置）
API_CONFIG = {
    "api_key": "",
    "api_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    "model": "doubao-seed-1-6-lite-251015",
    "token_limit": 100000,
    "used_tokens": 0,
    "proxy": None
}


# ===================== 新增：Chrome版本检测函数（核心修复） =====================
def get_chrome_version():
    """获取本地Chrome浏览器版本，用于匹配ChromeDriver"""
    try:
        # Windows系统检测
        if sys.platform == "win32":
            # 常见Chrome安装路径
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"～\AppData\Local\Google\Chrome\Application\chrome.exe")
            ]
            for path in chrome_paths:
                if os.path.exists(path):
                    result = subprocess.check_output(
                        [path, "--version"],
                        stderr=subprocess.STDOUT,
                        text=True
                    )
                    # 提取版本号（如 Chrome 120.0.6099.109 -> 120）
                    version_match = re.search(r'Chrome (\d+)\.', result)
                    if version_match:
                        return version_match.group(1)
        # Mac/Linux系统（备用）
        else:
            result = subprocess.check_output(["google-chrome", "--version"], stderr=subprocess.STDOUT, text=True)
            version_match = re.search(r'Chrome (\d+)\.', result)
            if version_match:
                return version_match.group(1)
        return None
    except Exception as e:
        basic_logger.warning(f"检测Chrome版本失败：{e}")
        return None


# def get_chromedriver_paths(): # 移除此函数
#     """获取所有可能的ChromeDriver路径（优先级排序）"""
#     paths = []
#     # 1. 程序同级目录
#     current_dir = os.path.dirname(os.path.abspath(__file__))
#     paths.append(os.path.join(current_dir, "chromedriver.exe"))
#     # 2. 用户指定的缓存目录
#     paths.append(os.path.join(CHROME_DRIVER_CACHE, "chromedriver.exe"))
#     # 3. 系统环境变量路径
#     paths.append("chromedriver.exe")
#     # 4. 桌面路径
#     desktop_path = os.path.join(os.path.expanduser("～"), "Desktop")
#     paths.append(os.path.join(desktop_path, "chromedriver.exe"))
#     return paths


# ===================== 新增：路径检查工具（修复依赖问题） =====================
def ensure_dir_exists(dir_path):
    """确保目录存在，不存在则创建（解决路径不存在错误）"""
    try:
        # 递归创建目录，设置权限为755
        os.makedirs(dir_path, exist_ok=True, mode=0o755)
        # 验证目录可写
        test_file = os.path.join(dir_path, "test_write.tmp")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        basic_logger.info(f"创建/验证目录成功：{dir_path}")  # 使用基础日志
        return True
    except PermissionError:
        # 权限不足时，改用临时目录
        temp_dir = os.path.join(os.environ.get("TEMP", "/tmp"), "AutoExam")
        os.makedirs(temp_dir, exist_ok=True)
        # os.environ['WDM_CACHE_DIR'] = temp_dir # 不再强制设置环境变量
        basic_logger.warning(f"原目录权限不足，webdriver-manager可能使用默认缓存目录")  # 使用基础日志
        return True
    except Exception as e:
        basic_logger.error(f"创建目录失败：{dir_path} - {str(e)[:30]}")  # 使用基础日志
        return False


# ===================== 日志初始化 =====================
def init_logger():
    logger = logging.getLogger("AutoExam")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    log_path = os.path.join(os.path.expanduser("～"), "AutoExam", "auto_exam_log.log")
    ensure_dir_exists(os.path.dirname(log_path))

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(threadName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 增加控制台输出（便于调试）
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


logger = init_logger()


# ===================== 悬浮窗状态更新函数 =====================
def update_status(msg, level="info"):
    """更新状态：同时写入日志和悬浮窗队列"""
    global API_CONFIG
    token_msg = f"【轮次：{cycle_count} | 已用Token：{API_CONFIG['used_tokens']}/{API_CONFIG['token_limit']}】"
    full_msg = f"{token_msg} {msg}"

    # 根据级别写入不同日志
    if level == "info":
        logger.info(f"【状态更新】{full_msg}")
    elif level == "warning":
        logger.warning(f"【状态更新】{full_msg}")
    elif level == "error":
        logger.error(f"【状态更新】{full_msg}")

    STATUS_QUEUE.put({
        "type": "status",
        "msg": msg,
        "cycle": cycle_count,
        "used_tokens": API_CONFIG['used_tokens'],
        "total_tokens": API_CONFIG['token_limit'],
        "level": level
    })


# ===================== 重试装饰器（增加重试间隔） =====================
def retry_on_failure(max_retries=RETRY_TIMES, delay=SHORT_SLEEP):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for retry in range(max_retries):
                if PAUSE_EVENT.is_set() or STOP_EVENT.is_set():
                    raise Exception("任务已暂停或停止")
                try:
                    return func(*args, **kwargs)
                except (TimeoutException, NoSuchElementException, ElementClickInterceptedException) as e:
                    logger.warning(f"【重试{retry + 1}/{max_retries}】{func.__name__}失败：{str(e)[:50]}")
                    time.sleep(delay)
            raise Exception(f"【重试耗尽】{func.__name__}失败，已重试{max_retries}次")

        return wrapper

    return decorator


# ===================== 元素查找函数（核心优化） =====================
@retry_on_failure()
def find_element_clickable(driver, locator, timeout=WAIT_TIMEOUT):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable(locator)
    )


@retry_on_failure()
def find_element_present(driver, locator, timeout=WAIT_TIMEOUT):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located(locator)
    )


def find_element_by_multiple_ways(driver, target_text, tag="button"):
    """多方式查找元素：提高找到按钮的概率"""
    locators = [
        (By.XPATH, f"//{tag}[text()='{target_text}']"),
        (By.XPATH, f"//{tag}//span[text()='{target_text}']/ancestor::{tag}[1]"),
        (By.XPATH, f"//{tag}[contains(text(), '{target_text}')]"),
        (By.XPATH, f"//{tag}//span[contains(text(), '{target_text}')]/ancestor::{tag}[1]"),
        (By.XPATH, f"//{tag}[contains(@class, 'ant-btn') and contains(text(), '{target_text}')]"),
        (By.XPATH, f"//{tag}[contains(@class, 'ant-btn')]//span[contains(text(), '{target_text}')]/ancestor::{tag}[1]")
    ]

    for locator_type, locator in locators:
        try:
            element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((locator_type, locator))
            )
            update_status(f"通过方式 {locator} 找到元素：{target_text}")
            return element
        except TimeoutException:
            continue

    update_status(f"所有方式都未找到元素：{target_text}", "warning")
    return None


def find_start_exam_button(driver):
    """原定位函数，作为备用"""
    try:
        return WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), '开始考试')]"))
        )
    except TimeoutException:
        try:
            return driver.find_element(By.XPATH, "//a[contains(text(), '开始考试')]")
        except NoSuchElementException:
            update_status("未找到开始考试按钮（按钮可能是a标签）", "warning")
            return None


def find_start_exam_button_precise(driver):
    """
    精准定位开始考试按钮：匹配用户提供的HTML结构
    <button data-v-40ef42ba="" type="button" class="mb10 ant-btn"><span>开始考试</span></button>
    """
    try:
        # 方式1：通过class + 子元素span文本定位（最精准）
        xpath = "//button[contains(@class, 'mb10') and contains(@class, 'ant-btn')]//span[text()='开始考试']/parent::button"
        element = WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        update_status(f"精准定位成功：{xpath}")
        return element
    except TimeoutException:
        try:
            # 方式2：仅通过子元素span文本定位（兼容class变化）
            xpath = "//button//span[text()='开始考试']/parent::button"
            element = WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            update_status(f"精准定位（方式2）成功：{xpath}")
            return element
        except TimeoutException:
            try:
                # 方式3：模糊匹配class + 文本（兼容空格问题）
                xpath = "//button[contains(@class, 'ant-btn') and contains(.//span/text(), '开始考试')]"
                element = WebDriverWait(driver, WAIT_TIMEOUT).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                update_status(f"精准定位（方式3）成功：{xpath}")
                return element
            except TimeoutException:
                update_status("精准定位：未找到开始考试按钮", "warning")
                return None


# ===================== 核心：题目提取与选项操作 =====================
def extract_all_questions(driver):
    try:
        update_status("解析题目中...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "mb10"))
        )
        time.sleep(SHORT_SLEEP)

        stem_elements = driver.find_elements(By.CLASS_NAME, "mb10.ls1")
        if not stem_elements:
            update_status("未找到题干元素", "warning")
            return []

        page_html = driver.page_source
        soup = BeautifulSoup(page_html, 'html.parser')
        stem_tags = soup.select("div.mb10.ls1")

        questions = []
        valid_count = 0

        for idx, (stem_elem, stem_tag) in enumerate(zip(stem_elements, stem_tags), 1):
            stem_text = stem_tag.get_text().strip()
            if not stem_text:
                continue

            option_container = stem_tag.find_next_sibling("div", class_="mb10")
            options = []
            question_type = "未知题型"

            if option_container:
                if option_container.find("div", class_="ant-radio-group"):
                    radio_spans = option_container.select("label.ant-radio-wrapper span[data-v-4041ca2c]")
                    options = [span.get_text().strip() for span in radio_spans]
                    question_type = "判断题" if len(options) == 2 else "单选题"
                elif option_container.find("div", class_="ant-checkbox-group"):
                    checkbox_spans = option_container.select("label.ant-checkbox-wrapper span[data-v-4041ca2c]")
                    options = [span.get_text().strip() for span in checkbox_spans]
                    question_type = "多选题"

            questions.append({
                "id": idx,
                "type": question_type,
                "text": stem_text,
                "options": options,
                "stem_element": stem_elem,
                "option_type": "radio" if question_type in ["单选题", "判断题"] else "checkbox",
                "judge_original_options": options if question_type == "判断题" else None
            })
            valid_count += 1

        update_status(f"成功提取{valid_count}道题")
        return questions
    except Exception as e:
        update_status(f"提取题目失败：{str(e)[:30]}", "error")
        logger.error(f"提取题目出错：{e}", exc_info=True)
        return []


def _match_judge_option(original_options, ans_text):
    """动态匹配判断题选项"""
    if not original_options:
        return None

    judge_map = {
        "对": ["对", "正确"],
        "正确": ["对", "正确"],
        "错": ["错", "错误"],
        "错误": ["错", "错误"]
    }

    candidates = judge_map.get(ans_text, [ans_text])
    for opt in original_options:
        if opt in candidates:
            return opt
    return None


def _locate_option_element(driver, opt_text, question_type, stem_elem=None):
    """快速定位选项元素"""
    try:
        if question_type == "判断题" and stem_elem:
            option_container = stem_elem.find_element(By.XPATH,
                                                      "./following-sibling::div[contains(@class, 'mb10')][1]")
            xpath = f".//label[contains(@class, 'ant-radio-wrapper')]//span[@data-v-4041ca2c and text()='{opt_text}']/ancestor::label[1]"
            opt_elem = option_container.find_element(By.XPATH, xpath)
            return opt_elem
        else:
            if question_type == "单选题":
                xpath = f"//label[contains(@class, 'ant-radio-wrapper')]//span[@data-v-4041ca2c and text()='{opt_text}']/ancestor::label[1]"
            elif question_type == "多选题":
                xpath = f"//label[contains(@class, 'ant-checkbox-wrapper')]//span[@data-v-4041ca2c and text()='{opt_text}']/ancestor::label[1]"
            else:
                return None

            opt_elem = WebDriverWait(driver, 3).until(
                EC.visibility_of_element_located((By.XPATH, xpath))
            )
            return opt_elem
    except Exception as e:
        logger.warning(f"定位选项「{opt_text}」失败：{str(e)[:30]}")
        return None


def _click_option_safely(driver, opt_elem):
    """极速点击"""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center', behavior:'instant'});", opt_elem)
        driver.execute_script("arguments[0].click();", opt_elem)
        return True
    except Exception:
        try:
            ActionChains(driver).move_to_element(opt_elem).click().perform()
            return True
        except Exception:
            return False


def batch_answer_all_questions(driver, all_questions, answer_map):
    if not answer_map:
        update_status("答案映射表为空", "warning")
        return False

    success_count = 0
    try:
        for q in all_questions:
            if STOP_EVENT.is_set():
                return False

            q_id = q['id']
            q_type = q['type']
            q_stem_elem = q['stem_element']
            q_original_judge_opts = q.get("judge_original_options")
            matched_options = answer_map.get(q_id, [])

            if not matched_options:
                continue

            processed_options = []
            for ans_text in matched_options:
                if q_type == "判断题":
                    matched_opt = _match_judge_option(q_original_judge_opts, ans_text)
                    if matched_opt:
                        processed_options.append(matched_opt)
                else:
                    processed_options.append(ans_text)

            for ans_text in processed_options:
                if not ans_text:
                    continue
                opt_elem = _locate_option_element(driver, ans_text, q_type, q_stem_elem)
                if opt_elem and _click_option_safely(driver, opt_elem):
                    time.sleep(NO_SLEEP)
                else:
                    break
            else:
                success_count += 1

        update_status(f"答题完成：成功{success_count}/{len(all_questions)}道")
        return True
    except Exception as e:
        update_status(f"批量答题失败：{str(e)[:30]}", "error")
        logger.error(f"批量答题出错：{e}", exc_info=True)
        return False


# ===================== 豆包API功能（核心优化：增加重试和详细错误日志） =====================
def validate_api_config():
    """验证API配置是否正确"""
    if not API_CONFIG['api_key']:
        return False, "API Key不能为空"
    if not API_CONFIG['api_url']:
        return False, "API URL不能为空"
    if not API_CONFIG['model']:
        return False, "模型名称不能为空"
    try:
        if API_CONFIG['token_limit'] <= 0:
            return False, "Token配额必须大于0"
    except:
        return False, "Token配额必须是数字"

    # 新增：验证代理格式
    if API_CONFIG['proxy']:
        if not API_CONFIG['proxy'].startswith(('http://', 'https://')):
            return False, "代理地址必须以http://或https://开头"
    return True, "配置验证通过"


def test_network_connection(url):
    """测试网络连接"""
    try:
        proxies = None
        if API_CONFIG['proxy']:
            proxies = {"http": API_CONFIG['proxy'], "https": API_CONFIG['proxy']}

        response = requests.get(url, timeout=10, proxies=proxies, verify=False)
        update_status(f"网络连通性测试成功：{url} (状态码：{response.status_code})")
        return True
    except Exception as e:
        update_status(f"网络连通性测试失败：{url} - {str(e)[:50]}", "error")
        return False


def call_doubao_api(prompt):
    """优化版：增加重试机制和详细错误日志"""
    global API_CONFIG
    if not API_CONFIG['api_key']:
        update_status("API Key未配置", "error")
        STOP_EVENT.set()
        return None

    if API_CONFIG['used_tokens'] > API_CONFIG['token_limit'] - 500:
        update_status("Token配额即将耗尽", "error")
        STOP_EVENT.set()
        return None

    # 先测试网络连接
    api_domain = API_CONFIG['api_url'].split('/')[2]
    test_network_connection(f"https://{api_domain}")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_CONFIG['api_key']}"
    }

    data = {
        "model": API_CONFIG['model'],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2000,
        "stream": False
    }

    proxies = None
    if API_CONFIG['proxy']:
        proxies = {"http": API_CONFIG['proxy'], "https": API_CONFIG['proxy']}
        update_status(f"使用代理：{API_CONFIG['proxy']}")

    # API 重试逻辑（指数退避）
    for retry in range(API_RETRY_TIMES):
        if STOP_EVENT.is_set():
            return None

        # 指数退避：重试间隔 = 初始间隔 * (2^重试次数)
        retry_delay = API_RETRY_DELAY * (2 ** retry)
        try:
            update_status(f"调用API中（第{retry + 1}/{API_RETRY_TIMES}次，超时{API_TIMEOUT}秒）...")
            response = requests.post(
                API_CONFIG['api_url'],
                headers=headers,
                data=json.dumps(data),
                timeout=API_TIMEOUT,  # 使用修改后的45秒超时
                proxies=proxies,
                verify=False  # 保留证书跳过（但已禁用警告）
            )

            # 打印详细响应信息（用于调试）
            logger.info(f"API 响应状态码：{response.status_code}")
            logger.info(f"API 响应内容：{response.text[:500]}")  # 只打印前500字符

            response.raise_for_status()  # 抛出HTTP错误（4xx/5xx）
            result = response.json()

            # 检查响应格式是否正确
            if "choices" not in result or len(result["choices"]) == 0:
                raise Exception("API响应格式错误：没有choices字段")

            answer = result["choices"][0]["message"]["content"].strip()

            if "usage" in result:
                prompt_tokens = result["usage"].get("prompt_tokens", 0)
                completion_tokens = result["usage"].get("completion_tokens", 0)
                API_CONFIG['used_tokens'] += prompt_tokens + completion_tokens
                update_status(f"API返回答案（消耗{prompt_tokens + completion_tokens} Token）")

            logger.info(f"API返回结果：{answer[:100]}...")  # 只打印前100字符
            return answer

        except requests.exceptions.HTTPError as e:
            status_code = response.status_code if 'response' in locals() else "未知"
            error_msg = f"HTTP错误 {status_code}"
            if status_code == 401:
                error_msg += "（API Key无效或未授权）"
            elif status_code == 404:
                error_msg += "（API URL或模型名称错误）"
            elif status_code == 429:
                error_msg += "（请求频率过高或Token配额不足）"
            elif status_code == 500:
                error_msg += "（服务器内部错误）"
            update_status(f"API调用失败：{error_msg}，{retry + 1}/{API_RETRY_TIMES}", "error")
            logger.error(f"API HTTP错误：{e}", exc_info=True)

        except requests.exceptions.ConnectionError:
            error_msg = "连接错误（无法访问API服务器，可能需要代理）"
            update_status(f"API调用失败：{error_msg}，{retry + 1}/{API_RETRY_TIMES}", "error")
            logger.error(f"API连接错误", exc_info=True)

        except requests.exceptions.Timeout:
            error_msg = f"请求超时（已等待{API_TIMEOUT}秒，网络延迟过高）"
            update_status(f"API调用失败：{error_msg}，{retry + 1}/{API_RETRY_TIMES}", "error")
            logger.error(f"API超时错误", exc_info=True)

        except Exception as e:
            error_msg = str(e)[:50]
            update_status(f"API调用失败：{error_msg}，{retry + 1}/{API_RETRY_TIMES}", "error")
            logger.error(f"API其他错误：{e}", exc_info=True)

        # 重试间隔（指数退避）
        if retry < API_RETRY_TIMES - 1:
            update_status(f"等待{retry_delay}秒后重试...")
            time.sleep(retry_delay)

    # 所有重试都失败
    update_status(f"API调用失败：已重试{API_RETRY_TIMES}次，跳过本轮", "error")
    return None


def generate_batch_prompt(all_questions):
    prompt = "请批量回答以下题目，严格按照格式返回，不要添加额外内容：\n"
    prompt += "题目编号. 答案（判断题：对/错；单选题：选项文本；多选题：选项文本组合，用逗号分隔）\n\n题目列表：\n"
    for q in all_questions:
        prompt += f"{q['id']}. 题型：{q['type']}\n题干：{q['text']}\n选项：{' | '.join(q['options'])}\n\n"
    prompt += "示例：\n1. 对\n2. 科技创新\n3. 信息化,数字化\n请严格按示例格式返回！"
    return prompt


def parse_batch_answer(all_questions, batch_answer):
    if not batch_answer:
        return None

    answer_map = {q['id']: [] for q in all_questions}
    try:
        lines = batch_answer.split("\n")
        for line in lines:
            line = line.strip()
            if not line or "." not in line:
                continue

            parts = line.split(".", 1)
            try:
                q_id = int(parts[0].strip())
                q_answer = parts[1].strip()
            except ValueError:
                continue

            q = next((q for q in all_questions if q['id'] == q_id), None)
            if not q:
                continue

            if q['type'] == "判断题":
                answer_map[q_id].append(q_answer)
            elif q['type'] == "单选题":
                matched_opt = next((opt for opt in q['options'] if opt == q_answer), None)
                if matched_opt:
                    answer_map[q_id].append(matched_opt)
            elif q['type'] == "多选题":
                answer_options = [opt.strip() for opt in q_answer.split(",")]
                for ans_opt in answer_options:
                    matched_opt = next((opt for opt in q['options'] if opt == ans_opt), None)
                    if matched_opt:
                        answer_map[q_id].append(matched_opt)

        return answer_map
    except Exception as e:
        logger.error(f"解析答案失败：{e}", exc_info=True)
        return None


# ===================== 考试流程 =====================
def init_exam_flow(driver):
    """初始化考试流程，查找「在线考试」按钮"""
    global is_exam_started
    if is_exam_started:
        return True

    try:
        update_status("查找「在线考试」按钮...")
        online_exam_btn = find_element_by_multiple_ways(driver, "在线考试", "span")
        if not online_exam_btn:
            online_exam_btn = find_element_by_multiple_ways(driver, "在线考试", "a")

        if not online_exam_btn:
            update_status("未找到「在线考试」按钮", "error")
            return False

        if _click_option_safely(driver, online_exam_btn):
            time.sleep(MINI_SLEEP)
            is_exam_started = True
            update_status("进入在线考试页面成功")
            return True
        else:
            update_status("点击「在线考试」按钮失败", "error")
            return False
    except Exception as e:
        logger.error(f"初始化考试流程失败：{e}", exc_info=True)
        return False


def submit_exam(driver):
    """提交考试答案"""
    try:
        update_status("查找「提交答案」按钮...")
        submit_btn = find_element_by_multiple_ways(driver, "提交答案", "span")
        if not submit_btn:
            submit_btn = driver.find_element(By.XPATH, "//div[@class='footer']//span[text()='提交答案']")

        if _click_option_safely(driver, submit_btn):
            time.sleep(MINI_SLEEP)
            update_status("查找「确定」按钮...")
            confirm_btn = find_element_by_multiple_ways(driver, "确 定", "button")
            if not confirm_btn:
                confirm_btn = find_element_by_multiple_ways(driver, "确定", "button")

            if confirm_btn and _click_option_safely(driver, confirm_btn):
                time.sleep(MINI_SLEEP)
                update_status("提交考试成功")
                return True
            else:
                update_status("未找到「确定」按钮", "warning")
                return False
        else:
            update_status("点击「提交答案」按钮失败", "error")
            return False
    except Exception as e:
        logger.error(f"提交考试失败：{e}", exc_info=True)
        return False


def return_to_exam_list(driver):
    """【修改2】重写返回考试列表逻辑：直接跳转指定URL，不再找返回按钮"""
    global is_exam_started
    try:
        update_status("直接跳转考试首页...")
        # 直接访问指定URL
        driver.get("https://sdld-gxk.yxlearning.com/my/index")
        # 等待页面加载完成
        WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(LONG_SLEEP)  # 等待页面完全渲染
        is_exam_started = False
        update_status("成功跳转至考试首页，准备下一轮考试")
        return True
    except Exception as e:
        update_status(f"跳转考试首页失败：{str(e)[:30]}", "error")
        logger.error(f"跳转考试首页出错：{e}", exc_info=True)
        return False


# ===================== 新增：获取资源文件路径（用于PyInstaller打包） =====================
def resource_path(relative_path):
    """
    获取资源文件的绝对路径，用于 PyInstaller 打包后访问内部文件
    """
    try:
        # PyInstaller 创建临时文件夹，将路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ===================== 浏览器初始化任务（核心修复：使用内置ChromeDriver） =====================
def browser_init_task():
    """浏览器初始化任务（使用内置ChromeDriver）"""
    global driver, is_browser_ready
    try:
        update_status("初始化浏览器（使用内置ChromeDriver）")

        # 检测Chrome版本 (可选，用于日志)
        chrome_version = get_chrome_version()
        if chrome_version:
            update_status(f"检测到Chrome版本：{chrome_version}")
        else:
            update_status("未检测到Chrome浏览器，请先安装Chrome", "warning")

        # Chrome配置优化
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--disable-cache")
        chrome_options.add_argument("--disk-cache-size=0")
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_setting_values.popups": 0
        })
        # 禁用GPU加速（解决部分Windows环境启动失败）
        chrome_options.add_argument("--disable-gpu")
        # 禁用沙箱（解决权限问题）
        chrome_options.add_argument("--no-sandbox")
        # 禁用弹窗阻止（可选）
        chrome_options.add_argument("--disable-popup-blocking")

        # ========== 核心修改：使用内置ChromeDriver ==========
        update_status("正在获取内置ChromeDriver路径...")
        # 获取内置的 chromedriver.exe 路径
        driver_executable_path = resource_path("chromedriver.exe")
        update_status(f"ChromeDriver路径: {driver_executable_path}")

        # 检查驱动是否存在
        if not os.path.exists(driver_executable_path):
            raise FileNotFoundError(f"内置ChromeDriver未找到: {driver_executable_path}")

        service = Service(executable_path=driver_executable_path)
        with DRIVER_LOCK:
            driver = webdriver.Chrome(service=service, options=chrome_options)

        # 初始化浏览器配置
        with DRIVER_LOCK:
            driver.implicitly_wait(5)
            driver.set_page_load_timeout(WAIT_TIMEOUT)
            driver.maximize_window()
            driver.get(TARGET_URL)
            time.sleep(LONG_SLEEP)

        is_browser_ready = True
        update_status("浏览器已准备好，请手动登录账号（登录后请等待3秒再点击启动）")
    except SessionNotCreatedException as sne:
        # 这个错误通常是ChromeDriver版本与浏览器不匹配
        update_status(f"浏览器初始化失败：{str(sne)[:50]} (ChromeDriver版本可能与Chrome不匹配)", "error")
        logger.error(f"SessionNotCreatedException: {sne}", exc_info=True)
        if sys.platform == "win32":
            tk.Tk().withdraw()  # 隐藏主窗口
            messagebox.showerror(
                "浏览器初始化失败",
                f"错误详情：{str(sne)[:100]}\n\n可能原因：ChromeDriver版本与本地Chrome浏览器版本不兼容。\n请确保内置的chromedriver.exe版本与您本地安装的Chrome浏览器版本兼容。"
            )
    except FileNotFoundError as fnf:
        update_status(f"浏览器初始化失败：{fnf}", "error")
        logger.error(f"FileNotFoundError: {fnf}", exc_info=True)
        if sys.platform == "win32":
            tk.Tk().withdraw()  # 隐藏主窗口
            messagebox.showerror(
                "浏览器初始化失败",
                f"错误详情：{fnf}\n\n内置的ChromeDriver文件未找到。请确保chromedriver.exe与此程序在同一目录下。"
            )
    except Exception as e:
        update_status(f"浏览器初始化彻底失败：{str(e)[:50]}", "error")
        logger.error(f"浏览器初始化出错：{e}", exc_info=True)
        # 弹出错误提示框
        if sys.platform == "win32":
            tk.Tk().withdraw()  # 隐藏主窗口
            messagebox.showerror(
                "浏览器初始化失败",
                f"错误详情：{str(e)[:100]}\n\n请确保Chrome浏览器已安装并可正常打开。"
            )


def auto_exam_task():
    """自动化核心任务（修复变量引用错误+优化API失败处理）"""
    global driver, cycle_count, is_exam_started
    if not is_browser_ready or not driver:
        update_status("浏览器未准备好", "error")
        return

    try:
        update_status("开始自动化考试流程...")
        is_exam_started = False
        cycle_count = 0
        STOP_EVENT.clear()

        while not STOP_EVENT.is_set():
            while not COMMAND_QUEUE.empty():
                cmd = COMMAND_QUEUE.get()
                if cmd == "stop":
                    update_status("收到停止指令，结束任务")
                    STOP_EVENT.set()
                    break

            if STOP_EVENT.is_set():
                break

            with DRIVER_LOCK:
                if driver and not is_exam_started:
                    if not init_exam_flow(driver):
                        update_status("初始化考试流程失败，等待5秒后重试...", "warning")
                        time.sleep(5)
                        continue
                # 页面稳定等待
                time.sleep(2)
                update_status("在线考试页面已稳定，开始检测开始考试按钮...")

            # 检测开始考试按钮（二次检测逻辑）
            start_exam_btn = None
            with DRIVER_LOCK:
                if driver:
                    update_status("第一次检测：查找开始考试按钮...")
                    start_exam_btn = find_start_exam_button(driver)

                    if not start_exam_btn:
                        update_status("第一次检测失败，使用精准定位函数再次检测...", "warning")
                        time.sleep(MINI_SLEEP)
                        start_exam_btn = find_start_exam_button_precise(driver)

            if not start_exam_btn:
                update_status("两次检测均未找到「开始考试」按钮，任务结束")
                break

            # 新一轮考试
            cycle_count += 1
            update_status(f"========== 第{cycle_count}轮考试开始 ==========")

            # 修复：将内部try-except独立出来，避免变量e未定义
            current_error = None
            try:
                with DRIVER_LOCK:
                    if _click_option_safely(driver, start_exam_btn):
                        time.sleep(LONG_SLEEP)

                        all_questions = extract_all_questions(driver)
                        if not all_questions:
                            update_status("未提取到题目，跳过本轮", "warning")
                            return_to_exam_list(driver)  # 调用修改后的跳转函数
                            continue

                        batch_prompt = generate_batch_prompt(all_questions)
                        batch_answer = call_doubao_api(batch_prompt)

                        # 优化API失败处理：不是直接跳过，而是判断是否需要手动输入
                        if not batch_answer:
                            update_status("API多次调用失败，是否手动输入答案？", "warning")
                            return_to_exam_list(driver)  # 调用修改后的跳转函数
                            continue

                        answer_map = parse_batch_answer(all_questions, batch_answer)
                        if answer_map:
                            batch_answer_all_questions(driver, all_questions, answer_map)
                        else:
                            update_status("解析答案失败，跳过本轮", "warning")
                            return_to_exam_list(driver)  # 调用修改后的跳转函数
                            continue

                        submit_exam(driver)
                        return_to_exam_list(driver)  # 调用修改后的跳转函数

                        update_status(f"第{cycle_count}轮完成，准备下一轮...")
                        time.sleep(MINI_SLEEP)

            except Exception as e:
                current_error = e
                update_status(f"第{cycle_count}轮出错：{str(current_error)[:30]}", "error")
                logger.error(f"本轮出错：{current_error}", exc_info=True)
                with DRIVER_LOCK:
                    if driver:
                        return_to_exam_list(driver)  # 调用修改后的跳转函数
                time.sleep(MINI_SLEEP)

    except Exception as outer_e:
        if not STOP_EVENT.is_set():
            update_status(f"任务出错：{str(outer_e)[:30]}", "error")
            logger.error(f"任务执行出错：{outer_e}", exc_info=True)
    finally:
        update_status(f"任务结束，总消耗Token：{API_CONFIG['used_tokens']}/{API_CONFIG['token_limit']}")
        STATUS_QUEUE.put({"type": "finished"})


# ===================== 悬浮窗功能（优化：增加配置验证） =====================
class FloatingWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("自动考试助手")
        self.root.geometry("380x420")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.default_font = ("Arial", 9)
        self.bold_font = ("Arial", 9, "bold")

        self.is_running = False
        self.thread = None
        self.browser_thread = None

        self.create_widgets()
        self.update_status_loop()
        self.init_browser()

    def create_widgets(self):
        """优化后的UI布局"""
        main_frame = ttk.Frame(self.root, padding=3)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.pack_propagate(False)

        # 顶部状态栏
        self.status_frame = ttk.Frame(main_frame)
        self.status_frame.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=2)

        self.status_label = ttk.Label(self.status_frame, text="状态：初始化中", font=self.bold_font)
        self.status_label.pack(side=tk.LEFT, padx=2)

        self.cycle_label = ttk.Label(self.status_frame, text="轮次：0", font=self.default_font)
        self.cycle_label.pack(side=tk.RIGHT, padx=2)

        # Token使用情况
        self.token_frame = ttk.Frame(main_frame)
        self.token_frame.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=2)

        ttk.Label(self.token_frame, text="Token：", font=self.default_font).pack(side=tk.LEFT, padx=2)
        self.token_label = ttk.Label(self.token_frame, text="0 / 100000", font=self.default_font)
        self.token_label.pack(side=tk.RIGHT, padx=2)

        # API配置区域
        self.api_frame = ttk.LabelFrame(main_frame, text=" API配置 ", padding=5)
        self.api_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=2)
        self.api_frame.config(height=180)
        self.api_frame.pack_propagate(False)

        ttk.Label(self.api_frame, text="API Key：", font=self.default_font).grid(row=0, column=0, sticky=tk.W, pady=1)
        self.api_key_entry = ttk.Entry(self.api_frame, width=35, font=self.default_font)
        self.api_key_entry.grid(row=0, column=1, sticky=tk.EW, pady=1)
        self.api_key_entry.insert(0, API_CONFIG['api_key'])

        ttk.Label(self.api_frame, text="API URL：", font=self.default_font).grid(row=1, column=0, sticky=tk.W, pady=1)
        self.api_url_entry = ttk.Entry(self.api_frame, width=35, font=self.default_font)
        self.api_url_entry.grid(row=1, column=1, sticky=tk.EW, pady=1)
        self.api_url_entry.insert(0, API_CONFIG['api_url'])

        ttk.Label(self.api_frame, text="模型名称：", font=self.default_font).grid(row=2, column=0, sticky=tk.W, pady=1)
        self.model_entry = ttk.Entry(self.api_frame, width=35, font=self.default_font)
        self.model_entry.grid(row=2, column=1, sticky=tk.EW, pady=1)
        self.model_entry.insert(0, API_CONFIG['model'])

        ttk.Label(self.api_frame, text="Token配额：", font=self.default_font).grid(row=3, column=0, sticky=tk.W, pady=1)
        self.token_limit_entry = ttk.Entry(self.api_frame, width=35, font=self.default_font)
        self.token_limit_entry.grid(row=3, column=1, sticky=tk.EW, pady=1)
        self.token_limit_entry.insert(0, str(API_CONFIG['token_limit']))

        ttk.Label(self.api_frame, text="代理（可选）：", font=self.default_font).grid(row=4, column=0, sticky=tk.W, pady=1)
        self.proxy_entry = ttk.Entry(self.api_frame, width=35, font=self.default_font)
        self.proxy_entry.grid(row=4, column=1, sticky=tk.EW, pady=1)
        self.proxy_entry.insert(0, API_CONFIG['proxy'] or "")

        self.api_frame.columnconfigure(1, weight=1)

        # 日志区域
        self.log_frame = ttk.LabelFrame(main_frame, text=" 运行日志 ", padding=3)
        self.log_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=2)
        self.log_frame.config(height=80)
        self.log_frame.pack_propagate(False)

        self.log_text = tk.Text(self.log_frame, height=4, state=tk.DISABLED, font=self.default_font, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        self.log_scrollbar = ttk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=self.log_scrollbar.set)

        # 按钮区域
        self.btn_frame = ttk.Frame(main_frame)
        self.btn_frame.grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=2)

        self.start_btn = ttk.Button(self.btn_frame, text="启动任务", command=self.start_task, width=15)
        self.start_btn.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        self.stop_btn = ttk.Button(self.btn_frame, text="停止任务", command=self.stop_task, state=tk.DISABLED, width=15)
        self.stop_btn.pack(side=tk.RIGHT, padx=2, fill=tk.X, expand=True)

        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(3, weight=1)

    def init_browser(self):
        """初始化浏览器"""
        if self.browser_thread and self.browser_thread.is_alive():
            return

        self.browser_thread = threading.Thread(target=browser_init_task, daemon=True)
        self.browser_thread.start()

    def start_task(self):
        """启动任务（优化：增加配置验证）"""
        if self.is_running or not is_browser_ready:
            return

        # 保存API配置
        API_CONFIG['api_key'] = self.api_key_entry.get().strip()
        API_CONFIG['api_url'] = self.api_url_entry.get().strip()
        API_CONFIG['model'] = self.model_entry.get().strip()
        API_CONFIG['proxy'] = self.proxy_entry.get().strip() or None
        try:
            API_CONFIG['token_limit'] = int(self.token_limit_entry.get().strip())
        except ValueError:
            messagebox.showerror("错误", "Token配额必须是数字")
            return

        # 验证API配置
        is_valid, msg = validate_api_config()
        if not is_valid:
            messagebox.showerror("配置错误", msg)
            return

        if not API_CONFIG['api_key']:
            messagebox.showerror("错误", "请输入API Key")
            return

        STOP_EVENT.clear()
        global cycle_count
        cycle_count = 0
        API_CONFIG['used_tokens'] = 0

        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_label.config(text="状态：运行中")
        self.cycle_label.config(text="轮次：0")
        self.token_label.config(text=f"0 / {API_CONFIG['token_limit']}")
        self.clear_log()
        self.add_log("任务启动中...")
        self.add_log(f"API配置验证通过：{msg}")

        self.thread = threading.Thread(target=auto_exam_task, daemon=True)
        self.thread.start()

    def stop_task(self):
        """停止任务"""
        if not self.is_running:
            return

        self.add_log("正在停止任务...")
        STOP_EVENT.set()
        COMMAND_QUEUE.put("stop")

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="状态：已停止")
        self.add_log("任务已停止")

    def add_log(self, msg):
        """添加日志"""
        self.log_text.config(state=tk.NORMAL)
        if len(self.log_text.get("1.0", tk.END).split("\n")) > 6:
            self.log_text.delete("1.0", "2.0")
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.NORMAL)

    def clear_log(self):
        """清空日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def update_status_loop(self):
        """更新悬浮窗状态"""
        try:
            while not STATUS_QUEUE.empty():
                data = STATUS_QUEUE.get()
                if data['type'] == "status":
                    self.status_label.config(text=f"状态：{data['msg'][:18]}...")
                    self.cycle_label.config(text=f"轮次：{data['cycle']}")
                    self.token_label.config(text=f"{data['used_tokens']} / {data['total_tokens']}")
                    self.add_log(data['msg'])
                elif data['type'] == "finished":
                    self.is_running = False
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
                    self.status_label.config(text="状态：任务完成")
                    self.add_log("所有考试已完成！")
        except Exception as e:
            logger.error(f"更新状态失败：{e}", exc_info=True)

        self.root.after(100, self.update_status_loop)

    def on_close(self):
        """关闭窗口"""
        global driver

        if self.is_running:
            if messagebox.askyesno("确认", "任务正在运行，是否确定关闭？"):
                self.stop_task()
                with DRIVER_LOCK:
                    if driver:
                        driver.quit()
                self.root.destroy()
        else:
            with DRIVER_LOCK:
                if driver:
                    driver.quit()
            self.root.destroy()


# ===================== 新增：使用须知弹窗 =====================
def show_usage_notice():
    """显示工具使用须知弹窗，必须点击知道啦才能继续"""
    # 创建主窗口（隐藏，仅作为弹窗父级）
    notice_root = tk.Tk()
    notice_root.withdraw()  # 隐藏主窗口

    # 创建须知弹窗
    notice_win = tk.Toplevel(notice_root)
    notice_win.title("工具使用须知")
    notice_win.geometry("420x290")
    notice_win.resizable(False, False)
    notice_win.attributes("-topmost", True)  # 置顶显示
    notice_win.protocol("WM_DELETE_WINDOW", lambda: None)  # 禁止关闭按钮

    # 设置弹窗居中
    notice_win.update_idletasks()
    x = (notice_win.winfo_screenwidth() - notice_win.winfo_width()) // 2
    y = (notice_win.winfo_screenheight() - notice_win.winfo_height()) // 2
    notice_win.geometry(f"+{x}+{y}")

    # 标题标签
    title_label = ttk.Label(
        notice_win,
        text="工具使用须知",
        font=("Arial", 12, "bold")
    )
    title_label.pack(pady=10)

    # 须知内容
    content_text = """工具不是完美的，目前已知问题：
1. API调用超时，原则上是模型大小的问题，作者调用的是小模型测试的，使用者可以切换其他大模型
2. 作答选项选择不全，本质也跟模型输出的结果有关，其实不影响使用，有漏答，也可以及格压线通过
3. 就算没有漏答，不及格，跟模型有关，模型会重复学习，会通关的，给AI一些时间^_^"""

    content_label = ttk.Label(
        notice_win,
        text=content_text,
        font=("Arial", 10),
        justify=tk.LEFT,
        wraplength=360
    )
    content_label.pack(pady=5, padx=30)

    # 知道啦按钮
    def on_confirm():
        notice_win.destroy()
        notice_root.destroy()

    confirm_btn = ttk.Button(
        notice_win,
        text="知道啦",
        command=on_confirm,
        width=10
    )
    confirm_btn.pack(pady=10)

    # 等待弹窗关闭
    notice_win.mainloop()


# ===================== 主函数 =====================
if __name__ == "__main__":
    # 第一步：显示使用须知弹窗
    show_usage_notice()

    # 隐藏控制台（可选，注释掉则显示控制台）
    # if sys.platform == "win32":
    #     ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

    # 第二步：初始化主悬浮窗
    root = tk.Tk()
    app = FloatingWindow(root)
    root.mainloop()

    logger.info("程序已退出")
    sys.exit(0)