# BTU OBS Sınav Sonucu Bildirim Botu 🎓

Bursa Teknik Üniversitesi OBS sistemini otomatik kontrol edip, yeni sınav sonuçları açıklandığında **Telegram** üzerinden bildirim gönderen Python botu.

## ✨ Özellikler

- 🔄 Belirli aralıklarla OBS'yi otomatik kontrol eder
- 📱 Yeni not açıklandığında Telegram'dan bildirim gönderir
- � **Gemini Vision AI** ile matematik captcha'yı %100'e yakın çözer (v3.0 Pro / v1.5 Flash)
- 💾 Notları cache'leyerek gereksiz bildirim göndermez
- ☁️ GitHub Actions ile **ömür boyu ücretsiz** çalışır

## 🚀 Kurulum

### 1. Telegram Bot Oluşturma

1. Telegram'da [@BotFather](https://t.me/BotFather) ile konuşma başlat
2. `/newbot` komutunu gönder
3. Bot için bir isim gir (örn: "OBS Bildirim")
4. Bot için bir kullanıcı adı gir (örn: `btu_obs_bot`)
5. BotFather'ın verdiği **token**'ı kaydet

### 2. Chat ID Alma

1. Oluşturduğun bota `/start` mesajı gönder
2. Tarayıcıda şu URL'yi aç (TOKEN yerine kendi token'ını yaz):
   ```
   https://api.telegram.org/botTOKEN/getUpdates
   ```
3. JSON'daki `"chat":{"id":123456789}` kısmından **chat_id**'yi bul

### 3. Gemini API Key Alma (Ücretsiz)

1. [Google AI Studio](https://aistudio.google.com/app/apikey) adresine git.
2. "Create API Key" butonuna bas.
3. Aldığın anahtarı kaydet.

### 4. Lokal Kurulum

```bash
# Python 3.10+ gerekli
cd c:\Users\userl\Desktop\oku

# Sanal ortam oluştur (opsiyonel ama önerilir)
python -m venv venv
venv\Scripts\activate

# Bağımlılıkları yükle
pip install -r requirements.txt

# .env dosyası oluştur
copy .env.example .env
# .env dosyasını düzenleyerek bilgilerini gir
```

### 5. Ortam Değişkenlerini Ayarlama

`.env` dosyasını aç ve bilgilerini gir:

```env
OBS_USERNAME=ogrenci_numaran
OBS_PASSWORD=obs_sifren
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
GEMINI_API_KEY=AIzaSy... (API Keyin)
CHECK_INTERVAL=30
```

### 6. Test Etme

```bash
python main.py --test
```

Bu komut:
- Konfigürasyonu doğrular
- Telegram bağlantısını test eder
- OBS'ye giriş yapmayı dener (Gemini ile captcha çözer)
- Mevcut notları gösterir

## ☁️ Cloud Deployment (Ücretsiz 7/24 Çalıştırma)

### 🏆 GitHub Actions (Önerilen)

Bu yöntem ile bot, GitHub sunucularında 5-7 dakikada bir çalışır, notları kontrol eder ve kapanır. **Tamamen ücretsizdir.**

> **Not:** Bot sürekli açık (listening) modda değildir. Yani Telegram'dan mesaj attığınızda cevap vermez. Sadece not açıklandığında size mesaj atar.

#### Kurulum:

1. **GitHub'a push et:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/KULLANICI/obs-bot.git
   git push -u origin main
   ```

2. **GitHub Secrets ekle:**
   - Repo → Settings → Secrets and variables → Actions → New repository secret
   - Şu 5 secret'ı ekle:
     - `OBS_USERNAME` - OBS öğrenci numaran
     - `OBS_PASSWORD` - OBS şifren
     - `TELEGRAM_BOT_TOKEN` - BotFather'dan aldığın token
     - `TELEGRAM_CHAT_ID` - Chat ID'n
     - `GEMINI_API_KEY` - Google AI Studio'dan aldığın anahtar

3. **Actions'ı aktifleştir:**
   - Repo → Actions → "I understand my workflows, go ahead and enable them"

4. **Manuel test:**
   - Actions → "BTU OBS Grade Checker" → "Run workflow"

✅ Artık her 5 dakikada bir otomatik kontrol yapılacak!

## 🔧 Kullanım

```bash
# Normal modda çalıştır (sürekli kontrol - yerel bilgisayarda)
python main.py

# Test modu
python main.py --test

# Tek seferlik kontrol (GitHub Actions bu modu kullanır)
python main.py --once
```

## 📁 Dosya Yapısı

```
oku/
├── config.py           # Konfigürasyon yönetimi
├── obs_scraper.py      # OBS login, Gemini captcha ve not çekme
├── telegram_bot.py     # Telegram bildirimleri
├── main.py             # Ana çalıştırıcı
├── requirements.txt    # Python bağımlılıkları
├── .env.example        # Örnek ortam dosyası
├── .gitignore          # Git ignore
└── README.md           # Bu dosya
```

## ⚠️ Önemli Notlar

- **Şifreni güvenli tut**: `.env` dosyasını asla Git'e commit etme
- **Kontrol sıklığı**: GitHub Actions schedule'ı en sık 5 dakikada bir çalışabilir.
- **OBS yapısı değişebilir**: Sayfa yapısı değişirse scraper güncellenmeli

## 🐛 Sorun Giderme

### "Login failed" hatası
- Kullanıcı adı/şifre doğru mu kontrol et
- OBS'ye manuel giriş yapıp captcha türünü kontrol et

### "Telegram error" hatası
- Bot token'ı doğru mu?
- Bot'a `/start` mesajı gönderdin mi?
- Chat ID doğru mu?

### Bildirim gelmiyor
- `grades_cache.json` dosyasını silip yeniden başlat
- `--test` modunda çalıştırıp logları kontrol et

## 📄 Lisans

Bu proje eğitim amaçlı oluşturulmuştur. Kendi sorumluluğunuzda kullanın.
