#!/bin/bash
# ══════════════════════════════════════════════
#  Deploy Trading Bot to Digital Ocean / VPS
#  Ubuntu 22.04 LTS
# ══════════════════════════════════════════════
set -e

PROJ_DIR="/opt/trading-bot"
SERVICE="trading-bot"

echo "🚀 Deploying Trading Bot..."

# ── System Packages ──────────────────────────
apt-get update -y
apt-get install -y python3 python3-pip python3-venv nginx

# ── Copy Files ───────────────────────────────
mkdir -p "$PROJ_DIR"
cp app.py atr_calculator.py mt5_handler.py config.py requirements.txt "$PROJ_DIR/"

# .env: copy example ถ้ายังไม่มี
if [ ! -f "$PROJ_DIR/.env" ]; then
    cp .env.example "$PROJ_DIR/.env"
fi

# ── Python Virtualenv ─────────────────────────
cd "$PROJ_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# ── Systemd Service ──────────────────────────
cat > "/etc/systemd/system/$SERVICE.service" << EOF
[Unit]
Description=Trading Bot (TradingView → MetaAPI → MT5)
After=network.target

[Service]
User=root
WorkingDirectory=$PROJ_DIR
EnvironmentFile=$PROJ_DIR/.env
ExecStart=$PROJ_DIR/venv/bin/gunicorn \\
    --workers 1 \\
    --bind 0.0.0.0:5000 \\
    --timeout 120 \\
    --log-file $PROJ_DIR/gunicorn.log \\
    --access-logfile $PROJ_DIR/access.log \\
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# ── Nginx Reverse Proxy ──────────────────────
cat > "/etc/nginx/sites-available/$SERVICE" << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }
}
EOF

ln -sf "/etc/nginx/sites-available/$SERVICE" \
       "/etc/nginx/sites-enabled/$SERVICE"
rm -f  "/etc/nginx/sites-enabled/default"
nginx -t  # validate config

# ── Start / Restart Services ─────────────────
systemctl daemon-reload
systemctl enable  "$SERVICE"
systemctl restart "$SERVICE"
systemctl restart nginx

# ── Summary ───────────────────────────────────
VPS_IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_VPS_IP")
echo ""
echo "══════════════════════════════════════════"
echo "  ✅  Deploy สำเร็จ!"
echo "══════════════════════════════════════════"
echo "  📡 Webhook  :  http://$VPS_IP/webhook"
echo "  ❤️  Health   :  http://$VPS_IP/health"
echo "  📝 App log  :  tail -f $PROJ_DIR/bot.log"
echo "══════════════════════════════════════════"
echo ""
echo "  ⚠️  ขั้นตอนต่อไป:"
echo "  1. แก้ไข $PROJ_DIR/.env  (ใส่ META_API_TOKEN, META_ACCOUNT_ID, API_KEY)"
echo "  2. systemctl restart $SERVICE"
echo "  3. ตั้ง TradingView Alert → Webhook URL ด้านบน"
echo ""
