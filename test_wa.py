import requests

ACCESS_TOKEN = "EAAtXZBBNJfVsBRZAi9WgWSQAxpssx3BnuZCKtOwz1ZC8ikVWs0oZC8iAK4L79DRgPccbqfVZCRXtG48ep0jY8Jz4yjLu7LSfnUsAKKht7yo6xQbGJkZAmuYs8UM7f7krqDvS4cZAfpzyHsYFLfZBfZALKSEcSmOFLqo8XTtJxHvwUPU3NoA1eysm3dFYRXiQNAZCLfxcLtruixZAuyKSD3v2XiV4nE8DUvYJcfzS6u97Uqw2ZAOC4vgtKphei17qXiZAXZBHCSijUmoOWZArUlLCvvkNxR2ZCdzoU"
PHONE_NUMBER_ID = "1131048716754620"
TO_NUMBER = "6282331226740"

url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

data = {
    "messaging_product": "whatsapp",
    "to": TO_NUMBER,
    "type": "text",
    "text": {
        "body": "Tes WhatsApp dari aplikasi Gigamas"
    }
}

response = requests.post(
    url,
    headers=headers,
    json=data
)

print("STATUS :", response.status_code)
print("RESPONSE :", response.json())