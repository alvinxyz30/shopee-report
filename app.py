import os
import time
import hmac
import hashlib
import requests
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash

# === KONFIGURASI APLIKASI ===
app = Flask(__name__)
app.secret_key = 'kunci-final-super-aman'

PARTNER_ID = 1175054
PARTNER_KEY = "shpk614464654679696669515152437445795344697a57664176584c44444772"
SHOPEE_BASE_URL = "https://partner.test-stable.shopeemobile.com"
REDIRECT_URL = "https://alvinnovendra.pythonanywhere.com/callback"

# === SIGNATURE GENERATOR ===
def generate_shopee_signature(path, timestamp, redirect_url=None):
    base_string = f"{PARTNER_ID}{path}{timestamp}"
    if redirect_url:
        base_string += redirect_url
    print("[SIGN BASE STRING]", base_string)
    sign = hmac.new(PARTNER_KEY.encode(), base_string.encode(), hashlib.sha256).hexdigest()
    print("[SIGN]", sign)
    return sign

# === FLASK ROUTE: HOME ===
@app.route('/')
def index():
    connected_stores = session.get('connected_stores', {})
    return render_template('index.html', stores=connected_stores)

# === FLASK ROUTE: AUTHORIZE ===
@app.route('/authorize_shopee')
def authorize_shopee():
    path = "/api/v2/shop/auth_partner"
    timestamp = int(time.time())
    sign = generate_shopee_signature(path, timestamp, REDIRECT_URL)
    auth_url = f"{SHOPEE_BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={timestamp}&sign={sign}&redirect={REDIRECT_URL}"
    return redirect(auth_url)

# === FLASK ROUTE: CALLBACK ===
@app.route('/callback')
def shopee_callback():
    code = request.args.get('code')
    shop_id = request.args.get('shop_id')

    if not code or not shop_id:
        flash("Otorisasi gagal atau dibatalkan.", "error")
        return redirect(url_for('index'))

    path = "/api/v2/auth/token/get"
    timestamp = int(time.time())
    sign = generate_shopee_signature(path, timestamp)
    url = f"{SHOPEE_BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={timestamp}&sign={sign}"
    body = {"code": code, "shop_id": int(shop_id)}

    try:
        response = requests.post(url, json=body)
        data = response.json()
        if data.get("error"):
            flash(f"Gagal mendapatkan token: {data['message']}", "error")
        else:
            stores = session.get('connected_stores', {})
            stores[f"Toko_{shop_id}"] = {
                "shop_id": int(shop_id),
                "access_token": data['access_token'],
                "refresh_token": data['refresh_token']
            }
            session['connected_stores'] = stores
            flash(f"Toko {shop_id} berhasil terhubung!", "success")
    except Exception as e:
        flash(f"Terjadi error: {e}", "error")

    return redirect(url_for('index'))

# === GET RETURN LIST ===
def get_all_return_sn(shop_id, access_token, from_date, to_date, status):
    path = "/api/v2/returns/get_return_list"
    all_return_sn_list = []
    next_cursor = ""
    while True:
        timestamp = int(time.time())
        sign = generate_shopee_signature(path, timestamp)
        url = f"{SHOPEE_BASE_URL}{path}?partner_id={PARTNER_ID}&shop_id={shop_id}&timestamp={timestamp}&sign={sign}&access_token={access_token}"
        params = {
            "page_size": 50,
            "time_from": int(from_date.timestamp()),
            "time_to": int(to_date.timestamp()),
            "next_cursor": next_cursor
        }
        if status and status.upper() != 'ALL':
            params['status'] = status.upper()
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                return None, data.get("message")
            return_list = data.get("response", {}).get("return_sn_list", [])
            all_return_sn_list.extend([r['return_sn'] for r in return_list])
            if data.get("response", {}).get("more", False):
                next_cursor = data["response"].get("next_cursor", "")
            else:
                break
        except requests.exceptions.RequestException as e:
            return None, str(e)
    return all_return_sn_list, None

# === GET RETURN DETAILS ===
def get_return_details(shop_id, access_token, return_sn_list):
    path = "/api/v2/return/get_return_detail"
    timestamp = int(time.time())
    sign = generate_shopee_signature(path, timestamp)
    url = f"{SHOPEE_BASE_URL}{path}?partner_id={PARTNER_ID}&shop_id={shop_id}&timestamp={timestamp}&sign={sign}&access_token={access_token}"
    body = {"return_sn": return_sn_list}
    try:
        response = requests.post(url, json=body)
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            return None, data.get("message")
        return data.get("response", {}).get("return_list", []), None
    except requests.exceptions.RequestException as e:
        return None, str(e)

# === GENERATE REPORT ===
@app.route('/generate_report', methods=['POST'])
def generate_report():
    store_name = request.form['store_name']
    from_date_str = request.form['from_date']
    to_date_str = request.form['to_date']
    status = request.form['status']

    store_creds = session.get('connected_stores', {}).get(store_name)
    if not store_creds:
        flash("Toko tidak ditemukan di sesi. Silakan hubungkan ulang.", "error")
        return redirect(url_for('index'))

    all_return_details = []
    start_date = datetime.strptime(from_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(to_date_str, '%Y-%m-%d')

    current_start = start_date
    while current_start <= end_date:
        current_end = current_start + timedelta(days=89)
        if current_end > end_date:
            current_end = end_date

        flash(f"Menarik data retur dari {current_start.date()} sampai {current_end.date()}...", "info")
        return_sn_list, error = get_all_return_sn(store_creds['shop_id'], store_creds['access_token'], current_start, current_end, status)

        if error:
            flash(f"Error saat tarik SN: {error}", "error")
            return redirect(url_for('index'))

        for i in range(0, len(return_sn_list), 50):
            chunk = return_sn_list[i:i + 50]
            details, error_detail = get_return_details(store_creds['shop_id'], store_creds['access_token'], chunk)
            if error_detail:
                flash(f"Error saat tarik detail: {error_detail}", "error")
                continue
            all_return_details.extend(details)

        current_start = current_end + timedelta(days=1)

    if not all_return_details:
        flash("Tidak ada data retur ditemukan.", "info")
        return redirect(url_for('index'))

    processed_data = []
    for r in all_return_details:
        item_info = r.get('item', [{}])[0]
        processed_data.append({
            "Nomor Pesanan": r.get('order_sn'),
            "Resi Pengembalian": r.get('return_sn'),
            "Status Retur": r.get('status'),
            "Alasan Retur": r.get('reason'),
            "Tanggal Order Dibuat": datetime.fromtimestamp(r.get('create_time')).strftime('%Y-%m-%d %H:%M:%S'),
            "Metode Pembayaran": r.get('payment_method'),
            "Resi Pengiriman Asli": r.get('tracking_number'),
            "Nama Pembeli": r.get('user', {}).get('username'),
            "Nama Barang": item_info.get('item_name'),
            "SKU": item_info.get('item_sku'),
            "Jumlah Retur": item_info.get('amount'),
            "Total Pengembalian Dana": r.get('refund_amount'),
            "Gambar Bukti": ", ".join(r.get('image', [])),
            "Update Terakhir": datetime.fromtimestamp(r.get('update_time')).strftime('%Y-%m-%d %H:%M:%S'),
        })

    df = pd.DataFrame(processed_data)
    filename = f"Laporan_Retur_{store_name}_{from_date_str}_sd_{to_date_str}.xlsx"
    if not os.path.exists('downloads'): os.makedirs('downloads')
    filepath = os.path.join('downloads', filename)
    df.to_excel(filepath, index=False)
    session['last_report'] = filename

    flash(f"Laporan berhasil dibuat! {len(processed_data)} data diekspor.", "success")
    return redirect(url_for('index'))

# === DOWNLOAD LAPORAN ===
@app.route('/download')
def download_file():
    filename = session.get('last_report')
    if not filename:
        return "Tidak ada laporan untuk diunduh.", 404
    return send_file(os.path.join('downloads', filename), as_attachment=True)

# === LOGOUT ===
@app.route('/logout')
def logout():
    session.clear()
    flash("Sesi toko telah dihapus.", "info")
    return redirect(url_for('index'))

# === RUN ===
if __name__ == '__main__':
    app.run(debug=True)
