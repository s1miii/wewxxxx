# Bankr Telegram Alerter — Ubuntu VPS (no .env)

Single Python file. All config inside the file. No `.env` needed.

## 1. Edit the script with your secrets

Open `bankr_alerter.py` and edit the CONFIG block at the top:

```python
TELEGRAM_BOT_TOKEN = "8335281387:AAH..."     # ← paste yours
TELEGRAM_CHAT_ID   = "-1003915211068"        # ← paste yours
BANKR_API_KEY      = "bk_usr_..."            # optional, "" to skip
```

## 2. Install & run

```bash
sudo apt update && sudo apt install -y python3 python3-pip
pip3 install httpx
python3 bankr_alerter.py
```

Logs will show:
```
Bankr Telegram alerter started
Starting from block 46515820 (tip 46515825)
SENT @memorideai 44559256.0217 $MEMORIDE + 0.006601 ETH tx=0x657ec746a7
```

## 3. Run 24/7 with systemd

```bash
# Patch the service file to point at your file's location
sed -i "s|/home/ubuntu/bankr-alerter|$PWD|g" bankr-alerter.service

sudo cp bankr-alerter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bankr-alerter
sudo systemctl status bankr-alerter

# Live logs:
tail -f /var/log/bankr-alerter.log
```

## Common commands

| What | Command |
|---|---|
| Restart | `sudo systemctl restart bankr-alerter` |
| Stop | `sudo systemctl stop bankr-alerter` |
| Edit config | `nano bankr_alerter.py && sudo systemctl restart bankr-alerter` |

## ⚠️ Avoid double alerts
If your Emergent deployment is also alerting, disable Telegram there: in Emergent → Deployments → Variables, set `TELEGRAM_ENABLED=false` and redeploy. The dashboard still works; only the VPS sends Telegram.
