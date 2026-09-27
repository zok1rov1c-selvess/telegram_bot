# 📚 AI O'quv Yordamchi Boti

## Buyruqlar

| Buyruq | Vazifa |
|--------|--------|
| `/start` | Botni ishga tushirish |
| `/help` | Yordam va holat ko'rish |
| `/read` | Faylni tahlil qilib PDF qaytarish |
| `/presentation` | Fayldan PowerPoint taqdimot yaratish |

## Qanday ishlaydi

### /read
1. `/read` buyrug'ini yuboring
2. Fayl yuboring (PDF, DOCX, TXT, PPTX, XLSX, CSV...)
3. Bot faylni o'qib, AI yordamida tahlil qiladi
4. Chiroyli **PDF hisobot** yuboradi (bo'limlar, atamalar, xulosa, nazorat savollari)

### /presentation
1. `/presentation` buyrug'ini yuboring  
2. O'quv material faylini yuboring
3. Bot AI + Wikipedia yordamida reja tuzadi, rasmlar yuklab oladi
4. Kamida **15 slaydli PPTX** fayl yuboradi

## O'rnatish

```bash
cd telegram_bot
pip install -r requirements.txt
```

## Sozlash (.env)

```env
BOT_TOKEN=sizning_bot_tokeningiz

# AI (bittasini to'ldiring)
GEMINI_API_KEY=gemini_api_kalitingiz    # https://aistudio.google.com/apikey
# yoki
OPENAI_API_KEY=openai_api_kalitingiz
```

> ⚠️ AI kaliti bo'lmasa bot **offline rejimda** ishlaydi (asosiy funksiyalar ishlaydi, lekin sifat pastroq).

## Ishga tushirish

```bash
python bot.py
# yoki Windows da:
run.bat
```

## Qo'llab-quvvatlanadigan fayl turlari
PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, XLS, HTML, JSON, RTF, LOG, PY, JS + rasmlar (OCR)
