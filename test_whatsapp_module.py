from whatsapp import send_whatsapp_message

TO_NUMBER = "6282331226740"

message = """
Tes modul WhatsApp Gigamas.

Jika pesan ini berhasil diproses, berarti file whatsapp.py sudah siap dipakai untuk alert otomatis.
"""

result = send_whatsapp_message(TO_NUMBER, message)

print("HASIL KIRIM:", result)