import os
import requests
from dotenv import load_dotenv

load_dotenv()


def send_whatsapp_message(to_number, message):
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    api_version = os.getenv("WHATSAPP_API_VERSION", "v20.0")

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {
            "body": message
        }
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=15
        )

        print("STATUS:", response.status_code)
        print("RESPONSE:", response.json())

        return response.status_code == 200

    except Exception as e:
        print("ERROR WHATSAPP:", e)
        return False


def send_low_stock_alert(nama_barang, nama_cabang, stok_sisa):
    pesan = f"""
⚠️ ALERT STOK MENIPIS - GIGAMAS

Barang: {nama_barang}
Cabang: {nama_cabang}
Stok Sisa: {stok_sisa}

Segera lakukan pengecekan dan penambahan stok.
"""

    return pesan


def send_critical_stock_alert(nama_barang, nama_cabang, stok_sisa):
    pesan = f"""
🚨 ALERT STOK KRITIS - GIGAMAS

Barang: {nama_barang}
Cabang: {nama_cabang}
Stok Sisa: {stok_sisa}

Mohon segera dilakukan tindakan.
"""

    return pesan


def send_large_outgoing_alert(nama_barang, nama_cabang, jumlah_keluar):
    pesan = f"""
📦 ALERT BARANG KELUAR BESAR - GIGAMAS

Barang: {nama_barang}
Cabang: {nama_cabang}
Jumlah Keluar: {jumlah_keluar}

Transaksi barang keluar melebihi batas normal.
"""

    return pesan