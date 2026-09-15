# EDA Bulguları ve Feature Fikirleri

**Proje:** Türkiye saatlik elektrik tüketimi tahmini
**Veri kaynağı:** EPİAŞ Şeffaflık Platformu — Gerçek Zamanlı Tüketim
**Kapsam:** 2017-01-01 00:00 → 2026-08-30 23:00 (Europe/Istanbul, sabit UTC+03:00)

---

## 1. Veri Kalitesi

| Kontrol | Sonuç |
|---|---|
| Toplam satır | 84.696 (beklenen saat sayısıyla birebir) |
| Eksik saat | Yok |
| Tekrar eden zaman damgası | Yok |
| Null | Yok |
| Sıfır / negatif değer | Yok |
| Sıralama | Monotonik artan |

**Tanımlayıcı istatistikler (MWh):**

| | Değer |
|---|---|
| Ortalama | 36.295 |
| Std. sapma | 6.408 |
| Min | 15.333 → 2020-05-25 07:00 |
| %25 | 31.565 |
| Medyan | 35.940 |
| %75 | 40.532 |
| Max | 59.504 → 2025-07-28 14:00 |

**Not:** Türkiye Eylül 2016'dan beri kalıcı UTC+03:00'te. Bu yüzden 2017 başlangıcı seçildi — yaz saati uygulamasından kaynaklanan tekrarlı/eksik saat problemi yok.

---

## 2. Üç Ayrı Periyodiklik

Seride eş zamanlı çalışan üç döngü var:

| Döngü | Periyot |
|---|---|
| Günlük | 24 saat |
| Haftalık | 168 saat |
| Yıllık | ~8.766 saat |

Modelin üçünü birden yakalaması gerekiyor.

---

## 3. Trend

2017'den 2026'ya doğru belirgin artan trend. Hem seviye hem de yaz zirvelerinin genliği büyüyor — yaz tepeleri kış tepelerine göre daha hızlı yükseliyor.

> **Yorum:** Soğutma yükünün toplam içindeki payı artıyor olabilir. Klima yaygınlaşması + ortalama sıcaklık artışı.

---

## 4. Yıllık Mevsimsellik

Yılda **iki maksimum, iki minimum:**

| Dönem | Seviye | Sebep |
|---|---|---|
| Ocak–Şubat | Yüksek | Isıtma + aydınlatma |
| **Nisan–Mayıs** | **En düşük** | Ne ısıtma ne soğutma |
| Temmuz–Ağustos | **En yüksek** | Soğutma |
| Ekim | Düşük | Ne ısıtma ne soğutma |

**Ana çıkarım:** Tüketim takvim ayına değil, ayın taşıdığı **sıcaklığa** tepki veriyor. İlişki doğrusal değil — U şeklinde. Hem yüksek hem düşük sıcaklıkta tüketim artıyor, ortada minimum.

---

## 5. Günlük Profil

- **Minimum:** ~04:00–05:00
- **Saat 8'de keskin sıçrama:** Her ayda, aynı yerde. Mesai/ticari yükün başlangıcı. Mevsimden bağımsız.
- **Yaz zirvesi:** ~12:00–15:00 (soğutma)
- **Kış zirvesi:** Sabaha kayıyor, ~07:00–09:00

**Kış sabah zirvesinin sebebi:** Ankara'da Ocak ayında güneş ~08:30'da doğuyor. Sabit UTC+03:00 nedeniyle kış sabahları karanlık. Karanlık + soğuk + eşzamanlı uyanma = aydınlatma yükü. Yazın aynı saatte bu bileşen sıfır.

> **Modelleme sonucu:** Tek bir `hour` değişkeni yetmiyor. Günlük profilin *şekli* mevsime göre değişiyor.

---

## 6. Haftalık Profil

| Gün | Davranış |
|---|---|
| Pazartesi | Gece saatleri tüm haftanın en düşüğü — sanayi Pazar'dan devrede değil |
| Salı–Cuma | En yüksek ve birbirine benzer |
| Cumartesi | Orta seviye. Sabah rampası **yumuşak** |
| Pazar | En düşük |

**Cumartesi'nin yumuşak rampası:** Hafta içi saat 8'deki sıçrama, eşzamanlı mesai başlangıcının adım fonksiyonu. Cumartesi bu senkronizasyon yok — aynı yük zamana yayılıyor. Ayrıca Cuma gecesi geç yatma nedeniyle Cumartesi gecesi hafta içinden yüksek başlıyor.

> **Modelleme sonucu:** `is_weekend` ikili değişkeni **yetersiz.** Pazartesi, Cumartesi ve Pazar birbirinden ve diğer günlerden farklı davranıyor. Günün kendisi ayrı özellik olmalı.

---

## 7. Bayram Etkisi (Kritik)

Yıllık grafiklerde belirgin düşüşler var ve **her yıl ~11 gün geriye kayıyor:**

| Yıl | Düşüş dönemleri |
|---|---|
| 2017 | Haziran sonu, Eylül başı |
| 2026 | Mart, Mayıs |

9 yılda ~100 günlük kayma. Sebep: dini bayramlar Hicri takvime bağlı, Gregoryen takvimde sabit değil.

> **Modelleme sonucu:** `month` veya `dayofyear` gibi takvim özellikleri bu düşüşleri **asla öğrenemez.** Aynı takvim gününe her yıl farklı bir olay denk geliyor. Ayrı bir bayram göstergesi zorunlu.

---

## 8. Anomaliler

| Dönem | Durum | Açıklama |
|---|---|---|
| Nisan 2020 – ~2021 | ✅ Tespit edildi | COVID-19, sokağa çıkma kısıtlamaları. Belirgin seviye düşüşü |
| 2020-05-25 | ✅ Tespit edildi | Serinin mutlak minimumu. Bayram + COVID üst üste binmesi |
| Ocak 2022 | ⬜ Doğrulanacak | Doğal gaz arz kesintisi → sanayi tüketiminde birkaç günlük sert düşüş |
| Şubat 2023 | ⬜ Doğrulanacak | Deprem. Bölgesel ama ulusal seride görünür |

---

## 9. Feature Fikirleri

### 9.1 Takvim (tahmin anında %100 biliniyor)

| Feature | Not |
|---|---|
| `hour` | 0–23 |
| `dayofweek` | 0–6. İkili weekend yerine tam gün |
| `month` | 1–12 |
| `dayofyear` | Yıllık pozisyon |
| `year` veya zaman indeksi | Trendi yakalamak için |
| `is_weekend` | Tek başına yetersiz, ama etkileşimlerde faydalı |

### 9.2 Döngüsel Kodlama

`hour`, `dayofweek`, `dayofyear` için `sin`/`cos` dönüşümü.

> **Neden:** Saat 23 ile saat 0 komşu, ama ham sayısal değer olarak 23 birim uzak. Ağaç tabanlı modellerde gerekmeyebilir, doğrusal ve sinir ağı modellerinde gerekli. Model seçiminden sonra karar ver.

### 9.3 Tatil

| Feature | Not |
|---|---|
| `is_resmi_tatil` | Sabit tarihli resmi tatiller |
| `is_bayram` | Dini bayram günleri |
| `bayram_gun_index` | Bayramın 1., 2., 3. günü farklı davranıyor |
| `is_arife` | Arife günü yarım gün, ayrı davranış |
| `is_kopru_gun` | Tatil ile hafta sonu arasına sıkışan iş günü |

Python `holidays` paketi Türkiye'yi destekliyor.

### 9.4 Sıcaklık (⚠️ leakage riski — Bölüm 10)

| Feature | Not |
|---|---|
| `HDD` (Heating Degree Days) | `max(0, T_baz − T)` |
| `CDD` (Cooling Degree Days) | `max(0, T − T_baz)` |
| Sıcaklık lag'leri | Bina termal ataleti — dünkü sıcaklık bugünü etkiler |
| Hareketli ortalama | 24s, 72s |

> **Neden HDD/CDD:** İlişki U şeklinde olduğu için ham sıcaklık doğrusal modelde işe yaramaz — katsayı pozitif mi negatif mi olacağını bilemez. Nötr noktadan (muhtemelen 16–18°C) sapmayı iki yönlü ayırmak gerekiyor. `T_baz` değeri veriden kalibre edilmeli.

### 9.5 Aydınlatma / Güneş (takvimden hesaplanır, leakage yok)

| Feature | Not |
|---|---|
| `gun_uzunlugu` | O günkü toplam güneş ışığı süresi |
| `is_karanlik` | O saat güneş doğmadan önce / battıktan sonra mı |
| `gunes_dogusuna_kalan_saat` | Sabah rampasını hizalar |

`astral` veya `suntime` kütüphanesi. ⚠️ Gün uzunluğu ile sıcaklık yüksek korelasyonlu — ikisini birden koymadan önce test et.

### 9.6 Lag ve Hareketli Özellikler

| Feature | Not |
|---|---|
| `lag_24` | Dün aynı saat |
| `lag_48` | Önceki gün aynı saat |
| `lag_168` | Geçen hafta aynı gün ve saat |
| `rolling_mean_24`, `rolling_mean_168` | Kısa vadeli seviye |

⚠️ Tahmin ufkuna göre hangi lag'lerin gerçekten kullanılabilir olduğu değişir.

### 9.7 Etkileşimler

- `hour × month` → günlük profilin mevsime göre değişmesi
- `hour × dayofweek` → Cumartesi'nin yumuşak rampası
- `hour × is_karanlik` → aydınlatma yükü

> Ağaç tabanlı modeller (XGBoost, LightGBM) bunları kendiliğinden öğrenebilir. Doğrusal modellerde açıkça oluşturulmalı.

### 9.8 Gereksiz Bulunan Fikirler

| Fikir | Neden gereksiz |
|---|---|
| `is_mesai` | `hour` + `dayofweek` bunu zaten kodluyor. Bilgi tekrarı |

---

## 10. ⚠️ Data Leakage Uyarısı

Yarının tüketimini tahmin ederken elimde gerçekten ne var?

| Bilgi | Tahmin anında var mı? |
|---|---|
| Takvim özellikleri | ✅ Evet |
| Tatil / bayram takvimi | ✅ Evet |
| Güneş doğuş/batış saatleri | ✅ Evet (astronomik hesap) |
| **Yarının sıcaklığı** | ❌ **Hayır** — sadece tahmini var |
| Yakın geçmiş lag'leri | ⚠️ Tahmin ufkuna bağlı |

**Risk:** Modeli geçmiş veriyle eğitirken *gerçekleşen* sıcaklığı kullanırsam, gerçek hayatta var olmayacak bir bilgiyle eğitmiş olurum. Test skoru yüksek çıkar, canlıda çöker.

**Karar verilecek:** Sıcaklık için gerçekleşen mi, tahmin mi kullanılacak? Tahmin ufku ne olacak (saat ilerisi / gün ilerisi)?

---

## 11. Sıradaki Adımlar

- [ ] Ocak 2022 ve Şubat 2023 anomalilerini doğrula
- [ ] Sıcaklık verisini çek (Open-Meteo, İstanbul/Ankara/İzmir, 2017+)
- [ ] Üç şehri tek ulusal sinyale indirgeme yöntemine karar ver ve gerekçelendir
- [ ] Sıcaklık–tüketim saçılım grafiği çiz, U şeklini doğrula
- [ ] `T_baz` nötr sıcaklığı veriden kalibre et
- [ ] Tahmin ufkunu ve sıcaklık kullanım stratejisini netleştir

---

## Metodolojik Notlar

**Rastgele tek gün/hafta seçmek anekdottur, kalıp değil.** İlk grafikler böyle çizildi, sonra `groupby` + ısı haritasına geçildi. Tek bir güne bakmak gürültüyü yapı sanmaya yol açıyor.

**Tek renk skalası seviye farkını gösterir, şekil farkını gizler.** Ay × saat ısı haritasında yaz ayları skalayı domine ettiği için kış günlerinin profil farkı görünmüyordu. Her satırı kendi ortalamasına bölerek (`pivot.div(pivot.mean(axis=1), axis=0)`) normalize etmek gerekiyor.

**Isı haritalarında satır sırası önemli.** Gün isimleri alfabetik değil, Pazartesi→Pazar sırasında olmalı.
