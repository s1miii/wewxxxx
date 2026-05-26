# Bankr Telegram Alerter — Ubuntu VPS

Standalone 24/7 Telegram alerter. Single Python file. No database. No web server.

## What you need
- An Ubuntu VPS (any small box: 1 vCPU / 512 MB RAM is plenty)
- Your Telegram bot token + channel ID
- (Recommended) Your Bankr API key for X-handle resolution

## Setup — copy/paste these 8 commands

```bash
# 1. SSH into your VPS
ssh ubuntu@your-vps-ip

# 2. Install Python and create a project dir
sudo apt update && sudo apt install -y python3 python3-pip python3-venv
mkdir -p ~/bankr-alerter && cd ~/bankr-alerter

# 3. Copy bankr_alerter.py, requirements.txt, and .env.example here
#    (use scp, rsync, git, or just paste with nano)

# 4. Create a virtualenv and install deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Configure secrets
cp .env.example .env
nano .env       # paste your TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BANKR_API_KEY

# 6. Test run (Ctrl+C to stop)
python3 bankr_alerter.py
```

You should see logs like:
```
Bankr Telegram alerter started
Starting from block 46515820 (tip 46515825)
SENT @memorideai 44559256.0217 $MEMORIDE + 0.006601 ETH tx=0x657ec746a7
```

## Run 24/7 with systemd

```bash
# 7. Install the systemd service
sudo cp bankr-alerter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bankr-alerter

# 8. Check status / logs
sudo systemctl status bankr-alerter
tail -f /var/log/bankr-alerter.log
```

That's it — the alerter restarts automatically on crash and on VPS reboot.

## Common commands

| What | Command |
|---|---|
| Watch live logs | `tail -f /var/log/bankr-alerter.log` |
| Stop | `sudo systemctl stop bankr-alerter` |
| Restart | `sudo systemctl restart bankr-alerter` |
| Disable on boot | `sudo systemctl disable bankr-alerter` |
| Edit config | `nano ~/bankr-alerter/.env && sudo systemctl restart bankr-alerter` |

## Whale filter (optional)

Only alert when claim is "interesting". Edit `.env`:
```
MIN_ETH_AMOUNT=0.05         # ≥ 0.05 ETH claim
MIN_MARKET_CAP_USD=50000    # ...OR token MC ≥ $50k
```
A claim must pass **at least one** threshold. Set both to 0 = alert on everything.

## ⚠️ Avoid double alerts
If your Emergent deployment is also running, you'll get duplicate Telegram messages from both. Pick one:
- **Use VPS only** (recommended) → in Emergent env vars set `TELEGRAM_ENABLED=false` and redeploy. The dashboard still works; only the VPS sends Telegram.
- **Use Emergent only** → don't enable the systemd service on your VPS.
