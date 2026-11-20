# ⚡ Flex SMS Live Web Hub (Dual-Engine)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Atiar594i/flex-sms-live-hub)

Real-time SMS & OTP monitoring dashboard for Flex SMS Portal with sub-second delivery (<0.3s cadence) and zero rate-limiting.

## 🚀 One-Click Cloud Deployment
Click the button above or visit:
👉 **[Deploy to Render](https://render.com/deploy?repo=https://github.com/Atiar594i/flex-sms-live-hub)**

Render will automatically detect `render.yaml` and configure the Python web service.

---

## ✨ Features
- **Dual-Engine Worker Architecture**: Alternates queries between two accounts (`Atiar59_FD` & `Smswork21_FD`) every 0.3s to avoid rate limits and session mutex locks.
- **Ultra-Low Latency**: Server-Sent Events (SSE) push new incoming SMS and OTPs to connected browsers with <0.1ms delay.
- **⚡ Force Fetch Now Button**: Triggers an instantaneous, high-priority background check anytime you click it.
- **Auto-Refresh Interval Controls**: Selectable polling speed (`0.5s`, `1.0s`, `2.0s`).
- **1-Click Copy**: Copy Phone Number, Copy OTP Code, or Copy Full SMS Message with one click.
- **Auto-Copy Option**: Toggle automatic clipboard copying of incoming OTPs or numbers.
- **Audio Chime Alerts**: Plays an instant pleasant sound when a new SMS arrives.
- **Permanent Search Filter**: Preset for `Telegram` (or customized via dashboard).
- **Flag & Country Detection**: Resolves international phone numbers to country flags and names.

---

## 🛠 Local Setup & Running
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the server:
   ```bash
   python server.py
   ```
   *(Or double-click `start.bat` on Windows)*
3. Open your browser:
   ```
   http://localhost:5000
   ```
