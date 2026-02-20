import yfinance as yf
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
import gspread
from google.oauth2.service_account import Credentials
import os
import json

# --- GİZLİ KİMLİK DOĞRULAMASI (GITHUB SECRETS'TEN ÇEKİLİR) ---
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
gcp_json_str = os.environ.get('GCP_CREDENTIALS')
creds_dict = json.loads(gcp_json_str)
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)

# --- AYARLAR ---
hisseler = ['THYAO.IS', 'ASELS.IS', 'KCHOL.IS', 'BIMAS.IS', 'TUPRS.IS']
tahminler = {}
tablo_adi = "Borsa_Tahminleri_ESP32"

def terbiye_edilmis_model(hisse_adi):
    print(f"\n⚙️ {hisse_adi} için Filtreli Model eğitiliyor...")
    df = yf.download(hisse_adi, period='3y', interval='1d', progress=False)
    
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df.dropna(inplace=True)
    
    features = df[['Open', 'High', 'Low', 'Close', 'Volume', 'EMA_20', 'RSI', 'MACD']].values
    target = df[['Close']].values
    
    scaler_x = MinMaxScaler(feature_range=(0, 1))
    scaler_y = MinMaxScaler(feature_range=(0, 1))
    
    scaled_features = scaler_x.fit_transform(features)
    scaled_target = scaler_y.fit_transform(target)
    
    prediction_days = 60
    x_train, y_train = [], []
    for x in range(prediction_days, len(scaled_features)):
        x_train.append(scaled_features[x-prediction_days:x])
        y_train.append(scaled_target[x, 0])
        
    x_train, y_train = np.array(x_train), np.array(y_train)
    
    model = Sequential([
        LSTM(units=64, return_sequences=True, input_shape=(x_train.shape[1], x_train.shape[2])),
        Dropout(0.2),
        LSTM(units=64, return_sequences=False),
        Dropout(0.2),
        Dense(units=32, activation='relu'),
        Dense(units=1)
    ])
    
    model.compile(optimizer='adam', loss='mean_squared_error')
    model.fit(x_train, y_train, epochs=20, batch_size=32, verbose=0)
    
    last_60_days = scaled_features[-prediction_days:]
    last_60_days = np.expand_dims(last_60_days, axis=0)
    
    prediction_scaled = model.predict(last_60_days, verbose=0)
    raw_prediction = float(scaler_y.inverse_transform(prediction_scaled)[0][0])
    
    current_price = df['Close'].iloc[-1]
    fark = raw_prediction - current_price
    smoothed_prediction = current_price + (fark * 0.70) 
    
    return float(smoothed_prediction)

print("--- OTONOM YAPAY ZEKA EĞİTİMİ BAŞLIYOR ---")
for h in hisseler:
    try:
        sonuc = terbiye_edilmis_model(h)
        tahminler[h] = sonuc
        print(f"✅ {h}: {sonuc:.2f} TL")
    except Exception as e:
        print(f"❌ {h} hatası: {e}")

sh = gc.open(tablo_adi)
sheet = sh.sheet1
sheet.clear()
sheet.update_acell('A1', 'Hisse')
sheet.update_acell('B1', 'Tahmin')

satir = 2
for hisse, tahmin in tahminler.items():
    hisse_kisa = hisse.replace('.IS', '') 
    sheet.update_cell(satir, 1, hisse_kisa)
    sheet.update_cell(satir, 2, str(round(tahmin, 2)))
    satir += 1

print("\n🚀 Otonom sistem başarıyla verileri E-Tablo'ya yazdı!")
