# android-tv-debloat

[English](README.md) · Türkçe

Bir Android TV'yi ağ üzerinden temizle. Tek bir Python dosyası, `adb` dışında bağımlılık yok.
Hiçbir şey silinmez: paketler kullanıcı için kapatılır, her değişiklik önce yedeklenir ve `restore` geri alır.

Sürekli donan bir TCL Smart TV Pro (Android 11, 2 GB RAM) üzerinde yapıldı: TCL'in reklam, telemetri ve promosyon
servisleri bellekte ~440 MB tutuyordu ve TV 40 saatte swap üzerinden 5,6 GB veri geçirmişti.

## Kullanım

TV'de: Ayarlar → Sistem → Hakkında → *Android TV OS yapısı*'na 7 kez bas, sonra Geliştirici seçeneklerinden
USB / ağ hata ayıklamasını aç.

```bash
brew install --cask android-platform-tools      # ya da herhangi bir adb
python3 debloat.py -d 192.168.1.80 scan          # TV'deki onayı kabul et; sadece okur
python3 debloat.py apply                         # güvenli katmanın deneme çalıştırması
python3 debloat.py apply --yes                   # uygula (yedek backups/ içine yazılır)
python3 debloat.py apply --also com.tcl.gallery --yes   # güvenli katman artı seçtiğin isteğe bağlı paketler
python3 debloat.py restore                       # bu TV'deki her uygulamayı geri al
python3 debloat.py check                         # firmware güncellemesinden sonra: geri açılanlar
python3 debloat.py check --fix                   # onları tekrar kapat
```

`scan` listedeki her paketi, kapalı mı, açık mı yoksa çalışıyor mu olduğunu ve ne kadar RAM tuttuğunu gösterir.
`apply` ayrıca arayüz animasyonlarını 0.5x yapar (atlamak için `--no-tweaks`).

Firmware güncellemesi kapattığın paketleri çoğu zaman geri açar. `check`, TV'yi uygulamalarının kapattıklarıyla
karşılaştırır ve bir şey geri geldiyse 1 ile çıkar; haftalık bir cron işine uyar. `check --fix` o paketleri tekrar
kapatır. Güncelleme ana ekranı stok başlatıcıya da geri verebilir:
[android-tv-home](https://github.com/caferyukseloglu/android-tv-home) kullanıyorsan `./home.sh home` komutunu
tekrar çalıştır.

## Listeler

`lists/android-tv.json` her Android TV'yi kapsar; `lists/<marka>.json` TV'nin üreticisine göre seçilir.
İki katman var: `safe` (reklamlar, telemetri, promosyonlar, bir TV'nin kullanamayacağı uygulamalar) ve `optional`
(kullanmayabileceğin gerçek özellikler). Listede olmayan bir pakete asla dokunulmaz. Başka markalar için pull
request'ler memnuniyetle; lütfen hangi modelde denediğini yaz.

## Testler

```bash
python3 -m unittest test_debloat
```

## Ayrıca bak

[android-tv-home](https://github.com/caferyukseloglu/android-tv-home): Philips Hue ışıkları içinde, sakin,
tvOS tarzı bir ana ekran; aynı TV'de yapıldı.

## Lisans

MIT
