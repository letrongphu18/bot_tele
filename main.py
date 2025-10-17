from flask import Flask, request
import requests
import datetime
import json
import os
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# ⭐ QUAN TRỌNG: Load file .env
load_dotenv()

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
# ❌ XÓA FALLBACK TOKEN - BẮTY PHẢI CÓ TRONG .env
CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
CLICKUP_TEAM_ID = os.getenv("CLICKUP_TEAM_ID")

# Lưu trữ task của user trong ngày (in-memory)
user_tasks = {}

# Debug: In ra để check đã load được chưa
print("="*50)
print("🔍 KIỂM TRA CONFIG:")
print(f"BOT_TOKEN: {BOT_TOKEN[:20]}..." if BOT_TOKEN else "BOT_TOKEN: ❌ KHÔNG CÓ")
print(f"CHAT_ID: {CHAT_ID}" if CHAT_ID else "CHAT_ID: ❌ KHÔNG CÓ")
print(f"CLICKUP_API_TOKEN: {CLICKUP_API_TOKEN[:20]}..." if CLICKUP_API_TOKEN else "CLICKUP_API_TOKEN: ❌ KHÔNG CÓ")
print(f"CLICKUP_TEAM_ID: {CLICKUP_TEAM_ID}")
print("="*50)

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
WEBHOOK_URL = f"https://bot-tele-lztd.onrender.com"

# Chạy 1 lần để set webhook
def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    response = requests.post(url, data={"url": WEBHOOK_URL})
    print(response.text)
# === HÀM GỬI TELEGRAM ===
def send_message(text, chat_id=None):
    """Gửi message tới Telegram"""
    if chat_id is None:
        chat_id = CHAT_ID
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(TELEGRAM_API, json=payload)
        print(f"✅ Message sent (status: {res.status_code})")
        return res.status_code
    except Exception as e:
        print(f"❌ Error sending message: {e}")
        return None

# === HÀM LẤY THÔNG TIN TASK TỪ CLICKUP API ===
def get_task_info(task_id):
    """Lấy thông tin chi tiết task từ ClickUp API"""
    url = f"https://api.clickup.com/api/v2/task/{task_id}"
    headers = {"Authorization": CLICKUP_API_TOKEN}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ ClickUp API error: {response.status_code}")
        return None
    except Exception as e:
        print(f"❌ Error getting task info: {e}")
        return None

def get_priority_text(priority_data):
    """Lấy text của priority từ ClickUp API"""
    if not priority_data:
        return "Không có"
    
    # Priority có thể là int hoặc dict
    if isinstance(priority_data, dict):
        priority_id = priority_data.get("priority")
    else:
        priority_id = priority_data
    
    priority_map = {
        1: "🔴 Khẩn cấp",
        2: "🟠 Cao", 
        3: "🟡 Bình thường",
        4: "🔵 Thấp"
    }
    
    return priority_map.get(priority_id, "Không xác định")

# === HÀM FORMAT THỜI GIAN ===
def format_timestamp(timestamp):
    """Chuyển timestamp (ms) sang datetime tiếng Việt"""
    if not timestamp:
        return "Không có"
    try:
        dt = datetime.datetime.fromtimestamp(int(timestamp) / 1000)
        return dt.strftime("%H:%M %d/%m/%Y")
    except:
        return "Không xác định"

def check_overdue(due_date):
    """Kiểm tra task có quá hạn không"""
    if not due_date:
        return False
    try:
        due = datetime.datetime.fromtimestamp(int(due_date) / 1000)
        now = datetime.datetime.now()
        return now > due
    except:
        return False

# === DAILY REPORT ===
def daily_report():
    """Gửi báo cáo hàng ngày lúc 22h"""
    print("\n🔔 Tạo daily report...")
    
    today_display = datetime.datetime.now().strftime("%d/%m/%Y")
    
    if not user_tasks:
        msg = f"""
📊 <b>BÁO CÁO HỖ TRỢ KẾT THÚC NGÀY - {today_display}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ Không có dữ liệu task trong ngày
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        send_message(msg)
        return
    
    msg = f"""
📊 <b>BÁO CÁO HỖ TRỢ KẾT THÚC NGÀY - {today_display}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    total_completed = 0
    total_pending = 0
    
    for username, tasks in user_tasks.items():
        completed = [t for t in tasks if t.get("status", "").lower() in ["complete", "completed", "closed", "done"]]
        pending = [t for t in tasks if t.get("status", "").lower() not in ["complete", "completed", "closed", "done"]]
        
        total_completed += len(completed)
        total_pending += len(pending)
        
        msg += f"\n👤 <b>{username}</b>\n"
        msg += f"   ✅ Hoàn thành: {len(completed)}\n"
        msg += f"   ⏳ Chưa hoàn thành: {len(pending)}\n"
    
    msg += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📈 <b>Tổng cộng:</b>\n"
    msg += f"   ✅ Hoàn thành: {total_completed}\n"
    msg += f"   ⏳ Chưa hoàn thành: {total_pending}\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    send_message(msg)

# === ROUTE NHẬN MESSAGE TỪ TELEGRAM ===
@app.route('/telegram', methods=['POST'])
def telegram_handler():
    """Xử lý message từ Telegram"""
    data = request.get_json()
    
    if "message" in data:
        message = data["message"]
        text = message.get("text", "")
        user = message.get("from", {})
        user_id = user.get("id")
        user_name = user.get("first_name", "User")
        
        print(f"\n📨 Telegram message từ {user_name}: {text}")
        
        if text == "/report_eod":
            today = datetime.datetime.now().strftime("%d/%m/%Y")
            
            # Chỉ lấy task của người gõ lệnh
            user_completed = []
            user_pending = []
            
            # Tìm username tương ứng với user_name từ user_tasks
            for username, tasks in user_tasks.items():
                # Nếu tên username chứa tên của user hoặc user_name chứa username
                if user_name.lower() in username.lower() or username.lower() in user_name.lower():
                    for task in tasks:
                        status = task.get("status", "").lower()
                        if status in ["complete", "completed", "closed", "done"]:
                            user_completed.append(task.get("name"))
                        else:
                            user_pending.append(task.get("name"))
            
            msg = f"""
📊 <b>BÁO CÁO TIẾN ĐỘ - {today}</b>
👤 <b>Người báo cáo: {user_name}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            if user_completed:
                msg += f"\n✅ <b>Đã hoàn thành ({len(user_completed)}):</b>\n"
                for task in user_completed:
                    msg += f"  ✓ {task}\n"
            else:
                msg += f"\n✅ <b>Đã hoàn thành: 0</b>\n"
            
            if user_pending:
                msg += f"\n⏳ <b>Chưa hoàn thành ({len(user_pending)}):</b>\n"
                for task in user_pending:
                    msg += f"  • {task}\n"
            else:
                msg += f"\n⏳ <b>Chưa hoàn thành: 0</b>\n"
            
            msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            
            # Gửi vào GROUP (không riêng)
            send_message(msg)
            print(f"✅ Gửi report của {user_name} vào group")
    
    return {"ok": True}, 200

# === ROUTE NHẬN WEBHOOK TỪ CLICKUP ===
@app.route('/clickup', methods=['POST', 'GET'])

def clickup_webhook():
    print("\n========== CLICKUP WEBHOOK RECEIVED ==========")
    print(f"⏰ Time: {datetime.datetime.now()}")
    print(f"🔗 Remote Address: {request.remote_addr}")
    
    data = request.get_json()
    
    try:
        with open('clickup_data.json', 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False))
            f.write("\n\n" + "="*50 + "\n\n")
    except Exception as e:
        print(f"❌ Error logging data: {e}")
    
    print("Body:", json.dumps(data, indent=2, ensure_ascii=False))
    print("=====================================\n")
    
    event = data.get("event", "")
    history_items = data.get("history_items", [])
    task_id = data.get("task_id", "")
    
    task_data = get_task_info(task_id)
    
    if not task_data:
        print("❌ Không lấy được thông tin task từ API")
        return {"ok": True}, 200
    
    # Parse thông tin task
    task_name = task_data.get("name", "Không rõ")
    task_url = task_data.get("url", "")
    
    # Status
    status_info = task_data.get("status", {})
    status = status_info.get("status", "Không rõ") if isinstance(status_info, dict) else "Không rõ"
    
    # Creator
    creator = task_data.get("creator", {})
    creator_name = creator.get("username", "Không rõ") if isinstance(creator, dict) else "Không rõ"
    
    # Assignees
    assignees = task_data.get("assignees", [])
    if assignees:
        assignees_list = [a.get("username", "N/A") for a in assignees]
        assignees_text = ", ".join(assignees_list)
    else:
        assignees_text = "Chưa phân công"
    
    # Priority - FIX CHÍNH
    priority_data = task_data.get("priority")
    priority_text = get_priority_text(priority_data)
    
    # Due date
    due_date = task_data.get("due_date")
    due_date_text = "Không có"
    is_overdue = False
    if due_date:
        due_date_text = format_timestamp(due_date)
        is_overdue = check_overdue(due_date)
    
    # Date created
    date_created = task_data.get("date_created")
    created_time = format_timestamp(date_created)
    
    # Thời gian hiện tại
    now = datetime.datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    
    # Người thực hiện action
    action_user = "Không rõ"
    if history_items:
        first_item = history_items[0]
        user_info = first_item.get("user", {})
        if isinstance(user_info, dict):
            action_user = user_info.get("username", "Không rõ")
    
    # Lưu task cho user
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if action_user not in user_tasks:
        user_tasks[action_user] = []
    
    # === XỬ LÝ CÁC EVENT ===
    
    if event == "taskCreated":
        overdue_warning = ""
        if is_overdue:
            overdue_warning = "\n⚠️ <b>CẢNH BÁO: ĐÃ QUÁ HẠN!</b>"
        
        msg = f"""
🆕 <b>TASK MỚI ĐƯỢC TẠO</b>
━━━━━━━━━━━━━━━━━━━━
📋 <b>{task_name}</b>
👤 Người tạo: <b>{creator_name}</b>
👥 Phân công: <b>{assignees_text}</b>
⚡ Mức độ: {priority_text}
📅 Deadline: {due_date_text}{overdue_warning}
🕒 Tạo lúc: {created_time}
━━━━━━━━━━━━━━━━━━━━
🔗 <a href="{task_url}">Xem chi tiết</a>
"""
        send_message(msg.strip())
    
    elif event == "taskUpdated":
        for item in history_items:
            field = item.get("field", "")
            
            if field == "status":
                before = item.get("before", {})
                after = item.get("after", {})
                
                old_status = before.get("status", "Không rõ") if isinstance(before, dict) else "Không rõ"
                new_status = after.get("status", "Không rõ") if isinstance(after, dict) else "Không rõ"
                
                if new_status.lower() in ["complete", "completed", "closed", "done"]:
                    # Lưu task hoàn thành
                    user_tasks[action_user].append({
                        "name": task_name,
                        "status": new_status,
                        "date": now
                    })
                    
                    completion_status = ""
                    time_diff_msg = ""
                    
                    if due_date:
                        try:
                            due_datetime = datetime.datetime.fromtimestamp(int(due_date) / 1000)
                            now_datetime = datetime.datetime.now()
                            time_diff = due_datetime - now_datetime
                            
                            hours_diff = time_diff.total_seconds() / 3600
                            days_diff = time_diff.days
                            
                            if hours_diff < 0:
                                abs_hours = abs(hours_diff)
                                if abs_hours < 24:
                                    time_diff_msg = f"\n⏰ Trễ deadline: <b>{int(abs_hours)} giờ {int((abs_hours % 1) * 60)} phút</b>"
                                else:
                                    time_diff_msg = f"\n⏰ Trễ deadline: <b>{abs(days_diff)} ngày</b>"
                                completion_status = "\n🔴 <b>TRẠNG THÁI: TRỄ DEADLINE</b>"
                            elif hours_diff >= 24:
                                if days_diff >= 1:
                                    time_diff_msg = f"\n⚡ Hoàn thành sớm: <b>{days_diff} ngày</b>"
                                else:
                                    time_diff_msg = f"\n⚡ Hoàn thành sớm: <b>{int(hours_diff)} giờ</b>"
                                completion_status = "\n🌟 <b>VƯỢT TIẾN ĐỘ! XUẤT SẮC!</b> 🎉"
                            else:
                                time_diff_msg = f"\n⏰ Còn {int(hours_diff)} giờ {int((hours_diff % 1) * 60)} phút đến deadline"
                                completion_status = "\n✅ <b>HOÀN THÀNH ĐÚNG TIẾN ĐỘ!</b> 👏"
                        except Exception as e:
                            print(f"❌ Error calculating time diff: {e}")
                    else:
                        completion_status = "\n✅ <b>HOÀN THÀNH!</b>"
                    
                    time_to_complete = ""
                    if date_created:
                        try:
                            created_dt = datetime.datetime.fromtimestamp(int(date_created) / 1000)
                            now_dt = datetime.datetime.now()
                            duration = now_dt - created_dt
                            
                            if duration.days > 0:
                                time_to_complete = f"\n⏱️ Thời gian làm: <b>{duration.days} ngày {duration.seconds // 3600} giờ</b>"
                            else:
                                hours = duration.seconds // 3600
                                minutes = (duration.seconds % 3600) // 60
                                time_to_complete = f"\n⏱️ Thời gian làm: <b>{hours} giờ {minutes} phút</b>"
                        except Exception as e:
                            print(f"❌ Error calculating duration: {e}")
                    
                    msg = f"""
✅ <b>TASK HOÀN THÀNH</b>{completion_status}
━━━━━━━━━━━━━━━━━━━━
📋 <b>{task_name}</b>
👤 Người hoàn thành: <b>{action_user}</b>
👥 Đã phân công cho: <b>{assignees_text}</b>
⚡ Mức độ: {priority_text}
📅 Deadline: {due_date_text}{time_diff_msg}{time_to_complete}
🕒 Hoàn thành lúc: {now}
━━━━━━━━━━━━━━━━━━━━
🔗 <a href="{task_url}">Xem chi tiết</a>
"""
                    send_message(msg.strip())
                
                else:
                    msg = f"""
🔄 <b>THAY ĐỔI TRẠNG THÁI</b>
━━━━━━━━━━━━━━━━━━━━
📋 <b>{task_name}</b>
👤 Người thay đổi: <b>{action_user}</b>
📌 Từ: {old_status} → <b>{new_status}</b>
⚡ Mức độ: {priority_text}
🕒 Lúc: {now}
━━━━━━━━━━━━━━━━━━━━
🔗 <a href="{task_url}">Xem chi tiết</a>
"""
                    send_message(msg.strip())
            
            elif field == "assignee_add":
                after = item.get("after", {})
                new_assignee = after.get("username", "Không rõ") if isinstance(after, dict) else "Không rõ"
                
                overdue_warning = ""
                if is_overdue:
                    overdue_warning = "\n⚠️ <b>Task đã quá hạn!</b>"
                
                msg = f"""
👤 <b>PHÂN CÔNG TASK</b>
━━━━━━━━━━━━━━━━━━━━
📋 <b>{task_name}</b>
➕ Được giao cho: <b>{new_assignee}</b>
⚡ Mức độ: {priority_text}
📅 Deadline: {due_date_text}{overdue_warning}
🕒 Lúc: {now}
━━━━━━━━━━━━━━━━━━━━
🔗 <a href="{task_url}">Xem chi tiết</a>
"""
                send_message(msg.strip())
            
            elif field == "assignee_rem":
                before = item.get("before", {})
                removed_assignee = before.get("username", "Không rõ") if isinstance(before, dict) else "Không rõ"
                
                msg = f"""
👤 <b>XÓA PHÂN CÔNG</b>
━━━━━━━━━━━━━━━━━━━━
📋 <b>{task_name}</b>
➖ Đã xóa: <b>{removed_assignee}</b>
⚡ Mức độ: {priority_text}
🕒 Lúc: {now}
━━━━━━━━━━━━━━━━━━━━
🔗 <a href="{task_url}">Xem chi tiết</a>
"""
                send_message(msg.strip())
            
            elif field == "due_date":
                after = item.get("after", {})
                new_due = format_timestamp(after) if after else "Không có"
                
                msg = f"""
📅 <b>THAY ĐỔI DEADLINE</b>
━━━━━━━━━━━━━━━━━━━━
📋 <b>{task_name}</b>
👤 Người thay đổi: <b>{action_user}</b>
📅 Deadline mới: <b>{new_due}</b>
⚡ Mức độ: {priority_text}
👥 Phụ trách: {assignees_text}
🕒 Lúc: {now}
━━━━━━━━━━━━━━━━━━━━
🔗 <a href="{task_url}">Xem chi tiết</a>
"""
                send_message(msg.strip())
        
        if is_overdue and status.lower() not in ["complete", "completed", "closed", "done"]:
            msg = f"""
⚠️ <b>CẢNH BÁO: TASK QUÁ HẠN!</b>
━━━━━━━━━━━━━━━━━━━━
📋 <b>{task_name}</b>
👥 Người phụ trách: <b>{assignees_text}</b>
📅 Deadline: {due_date_text}
⚡ Mức độ: {priority_text}
⏰ <b>ĐÃ QUÁ HẠN!</b>
📌 Trạng thái: {status}
🕒 Kiểm tra lúc: {now}
━━━━━━━━━━━━━━━━━━━━
🔗 <a href="{task_url}">Xem ngay</a>
"""
            send_message(msg.strip())
    
    elif event == "taskDeleted":
        msg = f"""
🗑️ <b>TASK ĐÃ BỊ XÓA</b>
━━━━━━━━━━━━━━━━━━━━
📋 <b>{task_name}</b>
👤 Người xóa: <b>{action_user}</b>
⚡ Mức độ: {priority_text}
👥 Đã phân công cho: {assignees_text}
🕒 Xóa lúc: {now}
━━━━━━━━━━━━━━━━━━━━
"""
        send_message(msg.strip())
    
    elif event == "taskCommentPosted":
        comment_text = "Không có nội dung"
        for item in history_items:
            if item.get("field") == "comment":
                comment_data = item.get("comment", {})
                if isinstance(comment_data, dict):
                    comment_text = comment_data.get("text_content", "Không có nội dung")
                break
        
        if len(comment_text) > 200:
            comment_text = comment_text[:200] + "..."
        
        msg = f"""
💬 <b>COMMENT MỚI</b>
━━━━━━━━━━━━━━━━━━━━
📋 Task: <b>{task_name}</b>
👤 Người comment: <b>{action_user}</b>
⚡ Mức độ: {priority_text}
💭 Nội dung: {comment_text}
🕒 Lúc: {now}
━━━━━━━━━━━━━━━━━━━━
🔗 <a href="{task_url}">Xem chi tiết</a>
"""
        send_message(msg.strip())
    
    return {"ok": True}, 200

@app.route('/', methods=['GET'])
def home():
    return "✅ ClickUp ↔ Telegram bot đang hoạt động!", 200

@app.route('/test', methods=['GET'])
def test():
    send_message("🧪 Test message từ ClickUp bot!")
    return "Message sent!", 200

# === SCHEDULER ===
scheduler = BackgroundScheduler()

def schedule_daily_report():
    """Lên lịch báo cáo hàng ngày lúc 22:00"""
    tz = pytz.timezone('Asia/Ho_Chi_Minh')
    trigger = CronTrigger(hour=22, minute=0, timezone=tz)
    scheduler.add_job(daily_report, trigger=trigger, id='daily_report', replace_existing=True)
    scheduler.start()
    print("✅ Daily report scheduled for 22:00 every day (Asia/Ho_Chi_Minh)")

# if __name__ == '__main__':
#     schedule_daily_report()
#     app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)