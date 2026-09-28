import os
import sys
import requests
from datetime import datetime, timezone, timedelta


# ============================================================
# Configuration
# ============================================================

DOMAIN = "glados.cloud"

BASE_URL = f"https://{DOMAIN}"

CHECKIN_URL = f"{BASE_URL}/api/user/checkin"
STATUS_URL = f"{BASE_URL}/api/user/status"
POINTS_URL = f"{BASE_URL}/api/user/points"

HEADERS = {
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/console/checkin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
}

CHECKIN_DATA = {
    "token": DOMAIN
}


# ============================================================
# HTTP
# ============================================================

def request(session, method, url, **kwargs):

    try:
        response = session.request(
            method,
            url,
            timeout=20,
            **kwargs
        )

        if response.status_code != 200:
            print(
                f"[HTTP ERROR] "
                f"{method} {url} -> {response.status_code}"
            )
            print(response.text[:500])
            return None

        return response

    except requests.RequestException as e:
        print(f"[NETWORK ERROR] {e}")
        return None


# ============================================================
# Account Status
# ============================================================

def get_status(session):

    response = request(
        session,
        "GET",
        STATUS_URL
    )

    if response is None:
        return None

    try:
        data = response.json()

        user = data.get("data", {})

        email = user.get("email")
        left_days = user.get("leftDays")

        if left_days is not None:
            left_days = int(float(left_days))

        return {
            "email": email or "Unknown",
            "left_days": left_days
        }

    except Exception as e:
        print(f"[ERROR] 状态解析失败: {e}")
        return None


# ============================================================
# Points
# ============================================================

def get_points(session):

    response = request(
        session,
        "GET",
        POINTS_URL
    )

    if response is None:
        return None

    try:
        data = response.json()

        points = data.get("points")

        if points is None:
            return None

        return int(float(points))

    except Exception as e:
        print(f"[ERROR] 积分解析失败: {e}")
        return None


# ============================================================
# Check-in
# ============================================================

def do_checkin(session):

    response = request(
        session,
        "POST",
        CHECKIN_URL,
        json=CHECKIN_DATA
    )

    if response is None:
        return {
            "status": "failure",
            "message": "签到接口请求失败",
            "points": 0
        }

    try:
        data = response.json()

    except Exception:
        return {
            "status": "failure",
            "message": "签到接口返回非 JSON 数据",
            "points": 0
        }

    code = data.get("code", -2)
    message = str(data.get("message", ""))
    points = data.get("points", 0)

    try:
        points = int(float(points))
    except (TypeError, ValueError):
        points = 0

    message_lower = message.lower()

    # 当前 API 通常 code = 0 表示签到成功
    if code == 0:

        return {
            "status": "success",
            "message": message,
            "points": points
        }

    # 已签到
    if (
        "repeat" in message_lower
        or "already" in message_lower
        or "tomorrow" in message_lower
    ):

        return {
            "status": "repeat",
            "message": message,
            "points": points
        }

    return {
        "status": "failure",
        "message": message or f"未知错误 code={code}",
        "points": 0
    }


# ============================================================
# One account
# ============================================================

def process_account(cookie, index):

    session = requests.Session()

    session.headers.update(HEADERS)

    # 不把 Cookie 输出到日志
    session.headers.update({
        "Cookie": cookie
    })

    print()
    print("=" * 60)
    print(f"账号 {index}")
    print("=" * 60)

    # 先验证 Cookie
    old_status = get_status(session)

    if old_status is None:

        print("❌ Cookie 无效或账户状态获取失败")

        return {
            "index": index,
            "email": "Unknown",
            "status": "failure",
            "message": "Cookie 无效或登录状态失效",
            "points": 0,
            "total_points": None,
            "left_days": None
        }

    email = old_status["email"]

    print(f"账号: {email}")

    # 签到
    result = do_checkin(session)

    # 签到以后重新查询状态
    new_status = get_status(session)

    total_points = get_points(session)

    left_days = None

    if new_status:
        left_days = new_status["left_days"]

    if result["status"] == "success":

        print("✅ 签到成功")
        print(f"本次积分: +{result['points']}")

    elif result["status"] == "repeat":

        print("🔄 今日已经签到")

    else:

        print("❌ 签到失败")
        print(f"原因: {result['message']}")

    if left_days is not None:
        print(f"剩余天数: {left_days} 天")

    if total_points is not None:
        print(f"总积分: {total_points}")

    return {
        "index": index,
        "email": email,
        "status": result["status"],
        "message": result["message"],
        "points": result["points"],
        "total_points": total_points,
        "left_days": left_days
    }


# ============================================================
# ServerChan / 方糖
# ============================================================

def get_serverchan_url(sendkey):

    """
    Server酱 Turbo:
        SCTxxxxxxxx
        https://sctapi.ftqq.com/{SENDKEY}.send

    Server酱³:
        sctp123tXXXX
        https://123.push.ft07.com/send/{SENDKEY}.send
    """

    if sendkey.lower().startswith("sctp"):

        try:
            uid_part = sendkey[4:].split("t", 1)[0]

            if uid_part.isdigit():
                return (
                    f"https://{uid_part}.push.ft07.com/"
                    f"send/{sendkey}.send"
                )

        except Exception:
            pass

        raise ValueError("无法解析 Server酱³ SendKey")

    return f"https://sctapi.ftqq.com/{sendkey}.send"


def send_serverchan(title, content):

    sendkey = os.environ.get(
        "SERVERCHAN_SENDKEY",
        ""
    ).strip()

    if not sendkey:
        print("⚠️ 未设置 SERVERCHAN_SENDKEY，跳过微信通知")
        return False

    try:

        url = get_serverchan_url(sendkey)

        response = requests.post(
            url,
            data={
                "title": title[:32],
                "desp": content
            },
            timeout=20
        )

        data = response.json()

        if data.get("code") == 0:

            print("✅ Server酱通知发送成功")
            return True

        print(
            "❌ Server酱通知失败:",
            data
        )

    except Exception as e:

        print(
            f"❌ Server酱通知异常: {e}"
        )

    return False


# ============================================================
# Message
# ============================================================

def build_message(results):

    success = sum(
        r["status"] == "success"
        for r in results
    )

    repeat = sum(
        r["status"] == "repeat"
        for r in results
    )

    failure = sum(
        r["status"] == "failure"
        for r in results
    )

    if failure > 0:

        icon = "❌"

    elif success > 0:

        icon = "✅"

    else:

        icon = "🔄"

    title = (
        f"{icon} GLaDOS签到 "
        f"成功{success} 重复{repeat} 失败{failure}"
    )

    lines = []

    lines.append("# GLaDOS 自动签到")
    lines.append("")

    china_tz = timezone(
        timedelta(hours=8)
    )

    now = datetime.now(
        china_tz
    ).strftime("%Y-%m-%d %H:%M:%S")

    lines.append(
        f"**时间：** {now}"
    )

    lines.append("")

    for result in results:

        index = result["index"]

        if result["status"] == "success":

            status_text = "✅ 签到成功"

        elif result["status"] == "repeat":

            status_text = "🔄 今日已签到"

        else:

            status_text = "❌ 签到失败"

        lines.append(
            f"## 账号 {index}"
        )

        lines.append("")

        lines.append(
            f"- **账号：** {result['email']}"
        )

        lines.append(
            f"- **状态：** {status_text}"
        )

        if result["status"] == "success":

            lines.append(
                f"- **签到积分：** +{result['points']}"
            )

        if result["left_days"] is not None:

            lines.append(
                f"- **剩余天数：** "
                f"{result['left_days']} 天"
            )

        if result["total_points"] is not None:

            lines.append(
                f"- **总积分：** "
                f"{result['total_points']}"
            )

        if result["status"] == "failure":

            lines.append(
                f"- **原因：** "
                f"{result['message']}"
            )

        lines.append("")

    lines.append("---")
    lines.append("GitHub Actions · GLaDOS Check-in")

    content = "\n".join(lines)

    return title, content


# ============================================================
# Main
# ============================================================

def main():

    raw_cookies = os.environ.get(
        "GLADOS_COOKIES",
        ""
    ).strip()

    if not raw_cookies:

        title = "❌ GLaDOS签到失败"

        content = (
            "# GLaDOS 自动签到\n\n"
            "未找到 `GLADOS_COOKIES`。"
        )

        print("❌ 未设置 GLADOS_COOKIES")

        send_serverchan(
            title,
            content
        )

        sys.exit(1)

    cookies = [
        item.strip()
        for item in raw_cookies.split("&")
        if item.strip()
    ]

    print(
        f"共加载 {len(cookies)} 个账号"
    )

    results = []

    for index, cookie in enumerate(
        cookies,
        start=1
    ):

        result = process_account(
            cookie,
            index
        )

        results.append(result)

    title, content = build_message(
        results
    )

    print()
    print("=" * 60)
    print(title)
    print("=" * 60)

    for r in results:

        print(
            f"#{r['index']} "
            f"{r['email']} | "
            f"{r['status']} | "
            f"P:+{r['points']} | "
            f"剩余:{r['left_days']} | "
            f"总积分:{r['total_points']}"
        )

    # 每次任务只推送一次
    send_serverchan(
        title,
        content
    )

    # 有真正失败账号时让 GitHub Actions 标红
    if any(
        r["status"] == "failure"
        for r in results
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
