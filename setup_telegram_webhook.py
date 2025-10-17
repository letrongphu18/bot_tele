import requests
import json

BOT_TOKEN = "7743481184:AAG7mt4MYz4XBGb1-SeHd0nLMy2TM6OVxys"
NGROK_URL = input("📡 Nhập ngrok URL (vd: https://xxxx-xxxx.ngrok-free.dev): ").strip()

# Setup webhook cho Telegram
webhook_url = f"{NGROK_URL}/telegram"

telegram_api = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"

payload = {
    "url": webhook_url,
    "allowed_updates": ["message"]
}

print(f"\n🔗 Đang set webhook Telegram...")
print(f"   Webhook URL: {webhook_url}")

response = requests.post(telegram_api, json=payload)
data = response.json()

print(f"\n✅ Response:")
print(json.dumps(data, indent=2))

if data.get("ok"):
    print(f"\n✅ Telegram webhook set thành công!")
    print(f"   Bot sẽ nhận message tại: {webhook_url}")
else:
    print(f"\n❌ Lỗi: {data.get('description')}")