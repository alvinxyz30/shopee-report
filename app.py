import time
import hmac
import hashlib
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash

# Inisialisasi Aplikasi Flask
app = Flask(__name__)
app.secret_key = 'kunci-rahasia-paling-final-dan-acak'

# ===================================================================
#   PENTING: ISI KREDENSIAL DARI APLIKASI BARU ANDA DI SINI
# ===================================================================
PARTNER_ID = 1175054  # <-- GANTI DENGAN PARTNER ID BARU ANDA JIKA BERBEDA
PARTNER_KEY = "shpk614464654679696669515152437445795344697a57664176584c44444772" # <-- GANTI DENGAN KEY BARU
# ===================================================================

# Konfigurasi URL (Sandbox)
SHOPEE_BASE_URL = "https://partner.test-stable.shopeemobile.com"

def generate_shopee_signature(path, timestamp):
    """Fungsi untuk membuat signature otentikasi Shopee."""
    base_string = f"{PARTNER_ID}{path}{timestamp}"
    sign = hmac.new(
        PARTNER_KEY.encode('utf-8'), 
        base_string.encode('utf-8'), 
        hashlib.sha256
    ).hexdigest()
    return sign

@app.route('/')
def index():
    # Cek apakah sudah ada token di session
    if 'shopee_credentials' in session:
        return render_template('index.html', credentials=session['shopee_credentials'])
    else:
        return render_template('index.html', credentials=None)

@app.route('/authorize')
def authorize():
    """Membangun URL otorisasi dan mengarahkan pengguna ke Shopee."""
    path = "/api/v2/shop/auth_partner"
    redirect_url = url_for('callback', _external=True)
    timestamp = int(time.time())
    sign = generate_shopee_signature(path, timestamp)
    
    auth_url = f"{SHOPEE_BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={timestamp}&sign={sign}&redirect={redirect_url}"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """Menangkap 'code' dari Shopee dan menukarnya dengan access_token."""
    code = request.args.get('code')
    shop_id = request.args.get('shop_id')

    if not code or not shop_id:
        flash("Otorisasi gagal atau dibatalkan.", "error")
        return redirect(url_for('index'))

    # Menukar 'code' dengan 'access_token'
    path = "/api/v2/auth/token/get"
    timestamp = int(time.time())
    sign = generate_shopee_signature(path, timestamp)
    url = f"{SHOPEE_BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={timestamp}&sign={sign}"
    body = {"code": code, "shop_id": int(shop_id)}
    
    try:
        response = requests.post(url, json=body)
        response.raise_for_status()
        token_data = response.json()

        if token_data.get("error"):
            flash(f"Gagal mendapatkan token: {token_data.get('message')}", "error")
        else:
            # Simpan semua info penting ke session
            session['shopee_credentials'] = {
                'shop_id': int(shop_id),
                'access_token': token_data['access_token'],
                'refresh_token': token_data['refresh_token']
            }
            flash(f"Toko dengan ID {shop_id} berhasil terhubung!", "success")

    except requests.exceptions.RequestException as e:
        flash(f"Error komunikasi dengan API Shopee: {e}", "error")

    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('shopee_credentials', None)
    flash("Sesi telah direset. Silakan hubungkan kembali.", "info")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)