import os
import time
import hmac
import hashlib
import json
from datetime import datetime, timedelta
import pandas as pd
from flask import (Flask, render_template, request, redirect, url_for, 
                   session, send_file, flash)

# Konfigurasi Aplikasi Flask
app = Flask(__name__)
app.secret_key = 'kunci-final-yang-super-aman-dan-acak'

# Gunakan URL Sandbox Shopee
SHOPEE_BASE_URL = "https://partner.test-stable.shopeemobile.com"

# --- FUNGSI BANTU UNTUK SHOPEE API ---

def generate_shopee_signature(partner_id, partner_key, path):
    """Membuat timestamp & signature untuk otentikasi Shopee."""
    timestamp = int(time.time())
    cleaned_partner_key = partner_key.strip()
    base_string = f"{partner_id}{path}{timestamp}"
    
    sign = hmac.new(
        cleaned_partner_key.encode('utf-8'), 
        base_string.encode('utf-8'), 
        hashlib.sha256
    ).hexdigest()
    
    return timestamp, sign

def get_return_details(shop_id, access_token, partner_id, partner_key, return_sn_list):
    """Mengambil detail lengkap dari beberapa retur berdasarkan return_sn."""
    path = "/api/v2/return/get_return_detail"
    timestamp, sign = generate_shopee_signature(partner_id, partner_key, path)
    
    url = f"{SHOPEE_BASE_URL}{path}?partner_id={partner_id}&shop_id={shop_id}&timestamp={timestamp}&sign={sign}&access_token={access_token}"
    body = {"return_sn": return_sn_list}

    try:
        response = requests.post(url, json=body)
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            return None, data.get("message", "Error tidak diketahui dari Shopee.")
        return data.get("response", {}).get("return_list", []), None
    except requests.exceptions.RequestException as e:
        return None, f"Error koneksi: {e}"

def get_all_return_sn(shop_id, access_token, partner_id, partner_key, from_date, to_date, status):
    """Menarik semua return_sn dari Shopee dengan paginasi otomatis."""
    path = "/api/v2/returns/get_return_list"
    all_return_sn_list = []
    next_cursor = ""
    
    while True:
        timestamp, sign = generate_shopee_signature(partner_id, partner_key, path)
        url = f"{SHOPEE_BASE_URL}{path}?partner_id={partner_id}&shop_id={shop_id}&timestamp={timestamp}&sign={sign}&access_token={access_token}"
        
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
                return None, data.get("message", "Error tidak diketahui dari Shopee.")

            response_data = data.get("response", {})
            return_list = response_data.get("return_sn_list", [])
            if return_list:
                all_return_sn_list.extend([r['return_sn'] for r in return_list])

            if response_data.get("more", False):
                next_cursor = response_data.get("next_cursor", "")
            else:
                break
        
        except requests.exceptions.RequestException as e:
            return None, f"Error koneksi: {e}"
            
    return all_return_sn_list, None

# --- ROUTE / HALAMAN APLIKASI WEB ---

@app.route('/')
def index():
    if 'developer_creds' not in session:
        return redirect(url_for('setup'))
    connected_stores = session.get('connected_stores', {})
    return render_template('index.html', stores=connected_stores)

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        session['developer_creds'] = {
            "partner_id": int(request.form['partner_id']),
            "partner_key": request.form['partner_key']
        }
        flash("Kredensial developer berhasil disimpan!", "success")
        return redirect(url_for('index'))
    return render_template('setup.html')

@app.route('/authorize_shopee')
def authorize_shopee():
    if 'developer_creds' not in session: return redirect(url_for('setup'))
    creds = session['developer_creds']
    path = "/api/v2/shop/auth_partner"
    redirect_url = url_for('shopee_callback', _external=True)
    timestamp, sign = generate_shopee_signature(creds['partner_id'], creds['partner_key'], path)
    auth_url = f"{SHOPEE_BASE_URL}{path}?partner_id={creds['partner_id']}&timestamp={timestamp}&sign={sign}&redirect={redirect_url}"
    return redirect(auth_url)

@app.route('/callback')
def shopee_callback():
    if 'developer_creds' not in session: return redirect(url_for('setup'))
    code, shop_id = request.args.get('code'), request.args.get('shop_id')
    if not code or not shop_id:
        flash("Otorisasi gagal atau dibatalkan.", "error")
        return redirect(url_for('index'))

    creds = session['developer_creds']
    path = "/api/v2/auth/token/get"
    # PERBAIKAN BUG: Timestamp harus dibuat di sini untuk panggilan API ini
    timestamp, sign = generate_shopee_signature(creds['partner_id'], creds['partner_key'], path)
    url = f"{SHOPEE_BASE_URL}{path}?partner_id={creds['partner_id']}&timestamp={timestamp}&sign={sign}"
    body = {"code": code, "shop_id": int(shop_id)}
    
    try:
        response = requests.post(url, json=body)
        response.raise_for_status()
        token_data = response.json()

        if token_data.get("error"):
            flash(f"Gagal mendapatkan token: {token_data.get('message')}", "error")
        else:
            if 'connected_stores' not in session: session['connected_stores'] = {}
            stores = session.get('connected_stores', {})
            store_name = f"Toko_{shop_id}"
            stores[store_name] = {
                'shop_id': int(shop_id),
                'access_token': token_data['access_token'],
                'refresh_token': token_data['refresh_token']
            }
            session['connected_stores'] = stores
            flash(f"Toko {store_name} berhasil terhubung!", "success")
    except requests.exceptions.RequestException as e:
        flash(f"Error komunikasi dengan API Shopee: {e}", "error")

    return redirect(url_for('index'))

@app.route('/generate_report', methods=['POST'])
def generate_report():
    store_name = request.form['store_name']
    from_date_str = request.form['from_date']
    to_date_str = request.form['to_date']
    status = request.form['status']
    
    store_creds = session.get('connected_stores', {}).get(store_name)
    developer_creds = session.get('developer_creds')

    if not store_creds or not developer_creds:
        flash("Sesi tidak valid, silakan setup ulang.", "error")
        return redirect(url_for('logout'))

    all_return_details = []
    start_date = datetime.strptime(from_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(to_date_str, '%Y-%m-%d')
    
    # Loop per 90 hari untuk mengatasi batasan API Shopee
    current_start = start_date
    while current_start <= end_date:
        current_end = current_start + timedelta(days=89)
        if current_end > end_date:
            current_end = end_date
        
        flash(f"Menarik daftar retur dari {current_start.date()} sampai {current_end.date()}...", "info")
        
        return_sn_list, error = get_all_return_sn(
            store_creds['shop_id'], store_creds['access_token'],
            developer_creds['partner_id'], developer_creds['partner_key'],
            current_start, current_end, status
        )
        
        if error:
            flash(f"Error saat menarik daftar retur: {error}", "error")
            return redirect(url_for('index'))

        if return_sn_list:
            flash(f"Menarik detail untuk {len(return_sn_list)} retur...", "info")
            # Shopee API mengizinkan fetch detail hingga 50 SN sekaligus
            for i in range(0, len(return_sn_list), 50):
                chunk = return_sn_list[i:i + 50]
                details, error_detail = get_return_details(
                    store_creds['shop_id'], store_creds['access_token'],
                    developer_creds['partner_id'], developer_creds['partner_key'],
                    chunk
                )
                if error_detail:
                    flash(f"Error saat menarik detail retur: {error_detail}", "error")
                    continue
                all_return_details.extend(details)
        
        current_start = current_end + timedelta(days=1)

    if not all_return_details:
        flash("Tidak ada data retur ditemukan pada rentang tanggal dan status yang dipilih.", "info")
        return redirect(url_for('index'))

    # Proses data yang didapat menjadi format Excel
    processed_data = []
    for r in all_return_details:
        # Mengambil detail item pertama sebagai contoh
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
            "Gambar Bukti": ", ".join(r.get('image', []))
        })
    
    df = pd.DataFrame(processed_data)
    filename = f"Laporan_Retur_{store_name}_{from_date_str}_sd_{to_date_str}.xlsx"
    
    downloads_folder = 'downloads'
    if not os.path.exists(downloads_folder):
        os.makedirs(downloads_folder)
    filepath = os.path.join(downloads_folder, filename)
    
    df.to_excel(filepath, index=False)
    
    session['last_report'] = filename
    flash(f"Laporan berhasil dibuat! {len(processed_data)} data diekspor.", "success")
    return redirect(url_for('index'))

@app.route('/download')
def download_file():
    filename = session.get('last_report')
    if not filename:
        return "Tidak ada laporan untuk diunduh.", 404
    return send_file(os.path.join('downloads', filename), as_attachment=True)
    
@app.route('/logout')
def logout():
    session.clear()
    flash("Anda telah logout.", "info")
    return redirect(url_for('setup'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)