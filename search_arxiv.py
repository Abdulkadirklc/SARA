# makale_arastirici_v8_SON.py (Hatalı eleman seçimi düzeltildi)

import asyncio
import json
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import argparse

async def arxiv_arastir_ve_getir(aranacak_terim: str, makale_sayisi: int = 10):
    """
    arxivxplorer.com sitesinde belirtilen terimle arama yapar ve istenen sayıda
    makalenin yapılandırılmış verisini döndürür.
    (Final Sürüm - Hatalı liste seçimi düzeltildi)
    """
    print(f"'{aranacak_terim}' için araştırma başlatılıyor...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) 
        page = await browser.new_page()

        try:
            print("Siteye gidiliyor...")
            await page.goto("https://arxivxplorer.com", timeout=60000, wait_until="networkidle")
            print("Siteye başarıyla ulaşıldı.")

            arama_kutusu_selector = 'input[placeholder="Enter paper ID, URL or search query"]'
            await page.wait_for_selector(arama_kutusu_selector, timeout=60000)
            
            print("Arama kutusuna tıklanıyor ve insan gibi yazılıyor...")
            await page.click(arama_kutusu_selector)
            await page.type(arama_kutusu_selector, aranacak_terim)

            print("Aramayı başlatmak için 'Enter' tuşuna basılıyor...")
            await page.press(arama_kutusu_selector, "Enter")
            
            print("Arama sonuçlarının yüklenmesi bekleniyor...")
            await page.wait_for_load_state('networkidle', timeout=60000)
            await asyncio.sleep(3)  # extra wait for dynamic content
            makale_karti_selector = "div.chakra-card__root"
            await page.wait_for_selector(makale_karti_selector, timeout=30000)
            print("Makale kartları başarıyla bulundu!")

            # 1. Get all article elements first
            print("Tüm makale kartları toplanıyor...")
            makale_elementleri = await page.query_selector_all(makale_karti_selector)
            
            # 2. Sonra Python'da ilk 10 tanesini seç
            toplanacak_elementler = makale_elementleri[:makale_sayisi]
            # --- DÜZELTME SONU ---
            
            toplanan_makaleler = []
            print(f"İlk {len(toplanacak_elementler)} makalenin verileri toplanıyor...")

            for i, element in enumerate(toplanacak_elementler):
                try:
                    baslik_element = await element.query_selector("h2.chakra-heading")
                    baslik = await baslik_element.inner_text() if baslik_element else "Başlık Yok"
                    yazarlar_element = await element.query_selector("p.css-p24j8d")
                    yazarlar = await yazarlar_element.inner_text() if yazarlar_element else "Yazar Yok"
                    ozet_element = await element.query_selector("p.css-1tkc83c")
                    ozet = await ozet_element.inner_text() if ozet_element else "Özet Yok"
                    link_element = await element.query_selector("a[href*='arxiv.org/abs']")
                    link = await link_element.get_attribute("href") if link_element else "Link Bulunamadı"

                    toplanan_makaleler.append({
                        "sira": i + 1, 
                        "baslik": baslik.strip(), 
                        "yazarlar": yazarlar.strip(),
                        "ozet": ozet.strip(), 
                        "tam_metin_linki": link
                    })
                    print(f"{i+1}. makale bilgileri alındı: {baslik[:50]}...")
                except Exception as e:
                    print(f"  - {i+1}. makale işlenirken bir hata oluştu: {e}")
                    continue
        
        except PlaywrightTimeoutError as e:
            print(f"\nHATA: Zaman aşımı! {e}")
            await page.screenshot(path='hata_ekran_goruntusu.png')
            print("Hata anının ekran görüntüsü 'hata_ekran_goruntusu.png' olarak kaydedildi.")
            return []
        except Exception as e:
            print(f"Beklenmedik bir hata oluştu: {e}")
            await page.screenshot(path='hata_ekran_goruntusu.png')
            print("Hata anının ekran görüntüsü 'hata_ekran_goruntusu.png' olarak kaydedildi.")
            return []
        finally:
            await browser.close()
            print("Tarayıcı kapatıldı.")
        return toplanan_makaleler

async def main():
    # --- YENİ EKLENEN ARGÜMAN PARSER BÖLÜMÜ ---
    parser = argparse.ArgumentParser(description="Scrape ArxivXplorer for papers based on a query.")
    parser.add_argument("--query", type=str, required=True, help="The search query for Arxiv.")
    parser.add_argument("--limit", type=int, default=10, help="The maximum number of papers to retrieve.")
    args = parser.parse_args()
    # --- BÖLÜM SONU ---

    # Değişkenleri artık sabit değil, gelen argümanlardan alıyoruz
    ARANACAK_TERIM = args.query
    MAKSIMUM_MAKALE = args.limit
    
    makaleler = await arxiv_arastir_ve_getir(ARANACAK_TERIM, MAKSIMUM_MAKALE)
    if makaleler:
        print("\n--- ARAŞTIRMA SONUÇLARI ---")
        # ... (geri kalan kod aynı) ...
        dosya_adi = "arastirma_sonuclari.json"
        with open(dosya_adi, 'w', encoding='utf-8') as f:
            json.dump(makaleler, f, ensure_ascii=False, indent=4)
        print(f"\n✨ Sonuçlar başarıyla '{dosya_adi}' dosyasına kaydedildi.")
    else:
        print("İşlem tamamlandı fakat hiç makale bulunamadı veya bir hata oluştu.")

if __name__ == "__main__":
    asyncio.run(main())