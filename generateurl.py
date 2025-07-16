import time
import hmac
import hashlib

# ===================================================================
#   ISI DATA DARI APLIKASI BARU ANDA DI SINI
# ===================================================================
# GANTI DENGAN PARTNER ID DARI APLIKASI BARU ANDA
PARTNER_ID = 1175054  # <-- GANTI DENGAN ID BARU ANDA

# GANTI DENGAN PARTNER KEY DARI APLIKASI BARU ANDA (PASTIKAN TIDAK ADA TYPO)
PARTNER_KEY = "shpk4b6f515159434376684f416b68774552754d6e714d5976744247796e7573" # <-- GANTI DENGAN KEY BARU

# ===================================================================
#   Konfigurasi (Jangan diubah)
# ===================================================================
SHOPEE_SANDBOX_URL = "https://partner.test-stable.shopeemobile.com"
API_PATH = "/api/v2/shop/auth_partner"
# Kita gunakan Google sebagai redirect sementara untuk tes ini
REDIRECT_URL = "https://google.com" 

# --- Logika Pembuatan URL ---
timestamp = int(time.time())
base_string = f"{PARTNER_ID}{API_PATH}{timestamp}"
sign = hmac.new(PARTNER_KEY.encode('utf-8'), base_string.encode('utf-8'), hashlib.sha256).hexdigest()

final_url = f"{SHOPEE_SANDBOX_URL}{API_PATH}?partner_id={PARTNER_ID}&timestamp={timestamp}&sign={sign}&redirect={REDIRECT_URL}"

# --- Cetak Hasil ---
print("="*50)
print("URL Otorisasi Shopee (Siap Pakai):")
print("="*50)
print(final_url)
print("\nSilakan copy seluruh URL di atas dan paste di browser Anda.")
print("="*50)