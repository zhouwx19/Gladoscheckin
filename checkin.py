import requests
import json
import os
import logging
import datetime
from typing import Dict, List, Optional, Tuple

# ---------------- 时间转北京时间 ----------------
def beijing_time_converter(timestamp):
    utc_dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    beijing_dt = utc_dt.astimezone(beijing_tz)
    return beijing_dt.timetuple()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if hasattr(handler, 'formatter') and handler.formatter is not None:
        handler.formatter.converter = beijing_time_converter

logger = logging.getLogger(__name__)

# ---------------- 环境变量 ----------------
ENV_PUSH_KEY = "WECHAT_NOTIFY"      # 方糖 SendKey
ENV_COOKIES = "GLADOS"
ENV_EXCHANGE_PLAN = "GLADOS_EXCHANGE_PLAN"

# ---------------- API ----------------
CHECKIN_URL = "https://glados.cloud/api/user/checkin"
STATUS_URL = "https://glados.cloud/api/user/status"
POINTS_URL = "https://glados.cloud/api/user/points"
EXCHANGE_URL = "https://glados.cloud/api/user/exchange"

CHECKIN_DATA = {"token": "glados.cloud"} 

HEADERS_TEMPLATE = {
    'referer': 'https://glados.cloud/console/checkin',
    'origin': "https://glados.cloud",
    'user-agent': "Mozilla/5.0",
    'content-type': 'application/json;charset=UTF-8'
}

EXCHANGE_POINTS = {"plan100": 100, "plan200": 200, "plan500": 500}

# ---------------- 方糖推送 ----------------
def send_ftqq(sendkey: str, title: str, desp: str):
    url = f"https://sct.ftqq.com/{sendkey}.send"
    data = {
        "title": title,
        "desp": desp
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            logger.info("方糖推送成功")
        else:
            logger.error(f"方糖推送失败: {r.text}")
    except Exception as e:
        logger.error(f"方糖推送异常: {e}")

# ---------------- 读取配置 ----------------
def load_config() -> Tuple[str, List[str], str]:

    push_key = os.environ.get(ENV_PUSH_KEY, "")
    raw_cookies_env = os.environ.get(ENV_COOKIES)
    exchange_plan_env = os.environ.get(ENV_EXCHANGE_PLAN, "plan500")

    if not raw_cookies_env:
        raise ValueError("未设置 GLADOS_COOKIES")

    cookies_list = [c.strip() for c in raw_cookies_env.split('&') if c.strip()]

    if exchange_plan_env not in EXCHANGE_POINTS:
        exchange_plan_env = "plan500"

    logger.info(f"加载账号数: {len(cookies_list)}")
    return push_key, cookies_list, exchange_plan_env

# ---------------- 请求封装 ----------------
def make_request(url: str, method: str, headers: Dict[str,str], data=None, cookies=""):

    h = headers.copy()
    h["cookie"] = cookies

    try:
        if method == "POST":
            r = requests.post(url, headers=h, data=json.dumps(data))
        else:
            r = requests.get(url, headers=h)

        if r.ok:
            return r
        return None
    except Exception as e:
        logger.error(f"请求异常: {e}")
        return None

# ---------------- 单账号处理 ----------------
def checkin_and_process(cookie, exchange_plan):

    status = "失败"
    points = "0"
    days = "未知"
    total_points = "未知"
    exchange = "未兑换"

    r = make_request(CHECKIN_URL, "POST", HEADERS_TEMPLATE, CHECKIN_DATA, cookie)

    if r:
        j = r.json()
        msg = j.get("message","")
        points = str(j.get("points",0))

        if "Got" in msg:
            status = "签到成功"
        elif "Repeats" in msg:
            status = "重复签到"
        else:
            status = f"失败:{msg}"

    r = make_request(STATUS_URL,"GET",HEADERS_TEMPLATE,cookies=cookie)
    if r:
        days = str(int(float(r.json()["data"]["leftDays"])))+"天"

    r = make_request(POINTS_URL,"GET",HEADERS_TEMPLATE,cookies=cookie)
    if r:
        total_points = str(int(float(r.json()["points"])))

    need = EXCHANGE_POINTS[exchange_plan]
    try:
        if int(total_points) >= need:
            r = make_request(EXCHANGE_URL,"POST",HEADERS_TEMPLATE,
                             {"planType":exchange_plan},cookie)
            if r and r.json().get("code")==0:
                exchange="兑换成功"
            else:
                exchange="兑换失败"
        else:
            exchange="积分不足"
    except:
        pass

    return status, points, days, total_points, exchange

# ---------------- 结果格式化 ----------------
def format_push(results):

    ok = sum("成功" in r["status"] for r in results)
    rep = sum("重复" in r["status"] for r in results)
    fail = len(results)-ok-rep

    title = f"GLaDOS签到 成功{ok} 失败{fail} 重复{rep}"

    lines=[]
    for i,r in enumerate(results,1):
        lines.append(
            f"账号{i}: {r['status']} | +{r['points']} | 剩{r['days']} | 总{r['points_total']} | {r['exchange']}"
        )

    return title,"\n".join(lines)

# ---------------- 主入口 ----------------
def main():

    try:
        sendkey, cookies, plan = load_config()
        results=[]

        for c in cookies:
            s,p,d,tp,e = checkin_and_process(c,plan)
            results.append({
                "status":s,
                "points":p,
                "days":d,
                "points_total":tp,
                "exchange":e
            })

        title,content = format_push(results)

    except Exception as e:
        title="脚本运行异常"
        content=str(e)

    print(title)
    print(content)

    if sendkey:
        send_ftqq(sendkey,title,content)

if __name__=="__main__":
    main()
