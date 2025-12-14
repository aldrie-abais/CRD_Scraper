import sys
import io
import time
import json
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==========================================
# --- CONFIGURATION ---
# ==========================================
OUTPUT_FILE = "reaction_database.json"

# Set to None to scrape ALL pages. Set to a number (e.g., 5) to limit it.
MAX_PAGES_TO_SCRAPE = 1
# ==========================================

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

driver = webdriver.Chrome()
driver.maximize_window()
wait = WebDriverWait(driver, 10)

if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        try:
            master_database = json.load(f)
        except:
            master_database = []
else:
    master_database = []

def save_to_file():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(master_database, f, indent=4)
    print(f"💾 Saved progress to {OUTPUT_FILE}")

try:
    # --- PHASE 1: GATHER LINKS ---
    archive_url = "https://kmt.vander-lingen.nl/archive"
    print(f"\n\n\nWelcome to CRD Scraper developed by Aldrie U. Abais and Khylle Villasurda\n\n\n")
    print(f"--- 1. LOADING ARCHIVE: {archive_url} ---")
    driver.get(archive_url)

    links = wait.until(EC.presence_of_all_elements_located((By.PARTIAL_LINK_TEXT, "reaction data")))
    target_urls = []
    for link in links:
        url = link.get_attribute("href")
        if url and url not in target_urls:
            target_urls.append(url)

    if MAX_PAGES_TO_SCRAPE is not None:
        target_urls = target_urls[:MAX_PAGES_TO_SCRAPE]
        print(f"⚠️ LIMIT APPLIED: Scraping only first {MAX_PAGES_TO_SCRAPE} pages.")

    print(f"✅ Found {len(target_urls)} DOI pages to scrape.")
    print("="*60 + "\n")

    # --- PHASE 2: PROCESS EACH PAGE ---
    for page_idx, current_url in enumerate(target_urls):
        print(f"--- PROCESSING PAGE {page_idx + 1}/{len(target_urls)} ---")
        print(f"URL: {current_url}")
        
        if any(d.get('page_url') == current_url for d in master_database):
            print("   [Skip] Already scraped this page.")
            continue
        
        driver.get(current_url)
        
        try:
            # Filter for visible panes only
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[id^='reaction-pane-']")))
            all_panes = driver.find_elements(By.CSS_SELECTOR, "div[id^='reaction-pane-']")
            visible_panes = [p for p in all_panes if p.is_displayed()]
            count = len(visible_panes)
            
            print(f"👉 Found {count} VISIBLE reactions.")
            page_data = []

            for i, current_pane in enumerate(visible_panes):
                print(f"   > Scraping Reaction {i+1} of {count}...")
                driver.switch_to.window(driver.window_handles[0])

                # A. Main Reaction SMILES
                try:
                    smiles_btn = current_pane.find_element(By.CSS_SELECTOR, "button[data-reaction-smiles]")
                    main_smiles = smiles_btn.get_attribute("data-reaction-smiles")
                except:
                    main_smiles = "N/A"

                # B. Click Details
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", current_pane)
                    time.sleep(0.5) 
                    details_btn = current_pane.find_element(By.PARTIAL_LINK_TEXT, "Details")
                    details_btn.click()
                except Exception as e:
                    print(f"     [Skip] Could not click Details: {e}")
                    continue

                # C. Switch Tab
                try:
                    wait.until(EC.number_of_windows_to_be(2))
                    driver.switch_to.window(driver.window_handles[-1])
                    details_window = driver.current_window_handle
                except:
                    print("     [Error] Tab switch failed.")
                    continue

                # D. Find Table
                try:
                    tables = wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "table")))
                    target_table = None
                    for tbl in tables:
                        if "reactant" in tbl.text.lower() or "product" in tbl.text.lower():
                            target_table = tbl
                            break
                    if not target_table: target_table = tables[-1]
                    rows = target_table.find_elements(By.TAG_NAME, "tr")
                except:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                    continue

                # E. Scrape Data
                reactants, solvents, products, others = [], [], [], []
                reactant_smiles, product_smiles = [], [] # REMOVED solvent/other smiles lists

                for row in rows:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) < 3: continue

                    role = cols[0].text.strip().lower()
                    name = cols[2].text.strip()
                    mol_smiles = None

                    # --- OPTIMIZATION: ONLY DEEP DIVE FOR REACTANTS OR PRODUCTS ---
                    if "reactant" in role or "product" in role:
                        try:
                            links = row.find_elements(By.TAG_NAME, "a")
                            profile_link = None
                            for link in links:
                                if "profile" in link.get_attribute("href"):
                                    profile_link = link
                                    break
                            
                            if profile_link:
                                profile_link.click()
                                wait.until(EC.number_of_windows_to_be(3))
                                driver.switch_to.window(driver.window_handles[-1])
                                
                                try:
                                    smiles_node = wait.until(EC.presence_of_element_located(
                                        (By.XPATH, "//td[contains(text(), 'Smiles')]/following-sibling::td")
                                    ))
                                    mol_smiles = smiles_node.text.strip()
                                except:
                                    pass
                                
                                driver.close()
                                driver.switch_to.window(details_window)
                        except:
                            if len(driver.window_handles) > 2:
                                driver.switch_to.window(driver.window_handles[-1])
                                driver.close()
                                driver.switch_to.window(details_window)

                    # --- STORE DATA (Modified) ---
                    if "reactant" in role:
                        reactants.append(name)
                        if mol_smiles: reactant_smiles.append(mol_smiles)
                    elif "solvent" in role:
                        solvents.append(name)
                        # Skipped solvent smiles storage
                    elif "product" in role:
                        products.append(name)
                        if mol_smiles: product_smiles.append(mol_smiles)
                    else:
                        others.append(f"{role}: {name}")
                        # Skipped other smiles storage

                # F. Build Object (Cleaned Up)
                reaction_obj = {
                    "page_url": current_url,
                    "reaction_id": i + 1,
                    "reactant": ", ".join(reactants),
                    "solvent": ", ".join(solvents),
                    "product": ", ".join(products),
                    "others": ", ".join(others),
                    "main_smiles": main_smiles,
                    "reactant_smiles": reactant_smiles,
                    "product_smiles": product_smiles
                    # solvent_smiles and other_smiles are completely removed
                }
                page_data.append(reaction_obj)

                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                time.sleep(0.5)

            master_database.extend(page_data)
            save_to_file()
            print(f"✅ Page Complete. Saved {len(page_data)} reactions.\n")

        except Exception as e:
            print(f"⚠️ Error on page {current_url}: {e}")
            continue

    print("="*60)
    print(f"GRAND TOTAL: Scraped {len(master_database)} reactions.")
    print(f"Data saved to: {os.path.abspath(OUTPUT_FILE)}")
    print("="*60)

except Exception as e:
    print(f"\nCRITICAL ERROR: {e}")
    save_to_file()

finally:
    input("\nPress Enter to close browser...")
    driver.quit()