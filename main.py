import yfinance as yf
import numpy as np
import pandas as pd
from textblob import TextBlob
import feedparser
import gspread
from google.oauth2.service_account import Credentials
import os
import json
from datetime import datetime
import urllib.parse
import time

# --- 1. GİZLİ KİMLİK DOĞRULAMASI (GITHUB SECRETS) ---
# GitHub Ayarlarındaki GCP_CREDENTIALS kısmını kullanır
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
gcp_json_str = os.environ.get('GCP_CREDENTIALS')
creds_dict = json.loads(gcp_json_str)
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)

# --- 2. DUYGU ANALİZİ (FINANSAL SÖZLÜK DESTEKLİ) ---
def get_detailed_sentiment(hisse_adi):
    try:
        query = urllib.parse.quote(f"{hisse_adi} hisse haberleri")
        url = f"https://news.google.com/rss/search?q={query}&hl=tr&gl=TR&ceid=TR:tr"
        feed = feedparser.parse(url)
        
        pozitif = ["temettü", "rekor", "yükseliş", "alım", "pozitif", "kar", "artış", "anlaşma"]
        negatif = ["düşüş", "zarar", "negatif", "satış", "kriz", "düşük", "kayıp", "gerileme"]

        if not feed.entries: return 0.0, "Notr"
        puan = 0
        limit = min(len(feed.entries), 3)
        for entry in feed.entries[:limit]:
            baslik = entry.title.lower()
            for k in pozitif:
                if k in baslik: puan += 0.30
            for k in negatif:
                if k in baslik: puan -= 0.30
            puan += TextBlob(entry.title).sentiment.polarity
        
        avg = puan / limit
        durum = "Pozitif" if avg > 0.02 else ("Negatif" if avg < -0.02 else "Notr")
        return avg, durum
    except: return 0.0, "Hata"

# --- 3. ANA İŞLEM VE SENKRONİZASYON ---
hisseler = ['THYAO.IS', 'ASELS.IS', 'KCHOL.IS', 'BIMAS.IS', 'EREGL.IS']
sh = gc.open("Borsa_Tahminleri_ESP32")
worksheet = sh.get_worksheet(0)

print("--- AKILLI BORSA TERMİNALİ GÜNCELLEMESİ BAŞLIYOR ---")
yeni_satirlar = []

for h in hisseler:
    try:
        # Fiyat Verisi (En güncel)
        df = yf.download(h, period='2d', interval='1m', progress=False)
        son_fiyat = float(df['Close'].iloc[-1].item())
        
        # Duygu Analizi
        h_sade = h.replace('.IS', '')
        duygu_skoru, duygu_metni = get_detailed_sentiment(h_sade)
        
        # Hibrit Tahmin: Teknik fiyat + Haber etkisi (%5 duyarlılık)
        # Haber pozitifse fiyatı yukarı, negatifse aşağı esnetir
        tahmin_fiyat = son_fiyat * (1 + (duygu_skoru * 0.05) + 0.002)
        
        yeni_satirlar.append([
            h_sade, 
            round(son_fiyat, 2), 
            round(tahmin_fiyat, 2), 
            duygu_metni, 
            datetime.now().strftime("%H:%M:%S")
        ])
        print(f"✅ {h_sade}: Analiz Tamamlandı ({duygu_metni})")
        time.sleep(1) # Yahoo engelini önlemek için
    except Exception as e:
        print(f"❌ {h} hatası: {e}")

# --- 4. VERİLERİ SİLMEDEN GÜNCELLEME (KRİTİK!) ---
# sheet.clear() KULLANMIYORUZ. Sadece A-E (Hisse-Saat) arasını güncelliyoruz.
# Böylece F ve G sütunundaki Adet ve Maliyet verilerin korunur.
worksheet.update('A2:E6', yeni_satirlar)

print("\n🚀 Tüm sistemler (Sheets, Power BI, ESP32) başarıyla senkronize edildi!")
