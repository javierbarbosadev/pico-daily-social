import os
import time
import requests
import cloudinary
import cloudinary.uploader
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# --- Read Secrets from Environment ---
IG_USER_ID = os.environ["IG_USER_ID"]
ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "PicoLearn Social Queue")
SERVICE_ACCOUNT_FILE = "service_account.json"

cloudinary.config(
    cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key=os.environ["CLOUDINARY_API_KEY"],
    api_secret=os.environ["CLOUDINARY_API_SECRET"]
)

def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(creds)
    return client.open(SPREADSHEET_NAME).sheet1

def capture_card(url: str, output_path: str = "daily_question.jpg") -> str:
    print(f"Launching Playwright mobile capture: {url}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # 430 x 537.5 is exactly 4:5 (the standard Instagram portrait ratio).
        # device_scale_factor=2 produces an ultra-sharp 860 x 1075 image.
        context = browser.new_context(
            viewport={"width": 430, "height": 538},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1000)

        # Target the card or fall back to the exact 4:5 viewport
        card = page.locator("#question-container")
        if card.count() > 0:
            print("Targeting #question-container...")
            card.screenshot(path=output_path, type="jpeg", quality=95)
        else:
            print("Capturing 4:5 mobile viewport...")
            page.screenshot(path=output_path, type="jpeg", quality=95)

        browser.close()
    print("Screenshot captured successfully.")
    return output_path
    
def upload_to_cdn(image_path: str) -> str:
    print("Uploading screenshot to Cloudinary...")
    res = cloudinary.uploader.upload(
        image_path,
        folder="picolearn_social",
        resource_type="image",
        overwrite=True,
        invalidate=True
    )
    url = res["secure_url"]
    print(f"Uploaded successfully. Waiting 5s for CDN edge warm-up: {url}")
    time.sleep(5)
    return url

def publish_to_instagram(image_url: str, caption: str):
    base_url = f"https://graph.facebook.com/v21.0/{IG_USER_ID}"
    
    # 1. Create Media Container
    print("Creating media container on Instagram...")
    container_payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    
    # Send as data or params
    res = requests.post(f"{base_url}/media", data=container_payload).json()
    
    if "id" not in res:
        raise RuntimeError(f"Container creation failed: {res}")

    container_id = res["id"]
    print(f"Container created. ID: {container_id}")

    # Meta needs a brief buffer to download and process the asset
    print("Waiting 15 seconds for Meta processing...")
    time.sleep(15)

    # 2. Publish Live
    print("Publishing container to live feed...")
    publish_payload = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }
    pub_res = requests.post(f"{base_url}/media_publish", data=publish_payload).json()

    if "id" not in pub_res:
        raise RuntimeError(f"Publish failed: {pub_res}")

    print(f"Success! Post live on @pico11plus. Live Media ID: {pub_res['id']}")
    
def main():
    sheet = get_sheet()
    records = sheet.get_all_records()

    target_row_index = None
    target_row = None
    for idx, row in enumerate(records, start=2): # 1-indexed, header is row 1
        if str(row.get("status", "")).strip().upper() == "READY":
            target_row_index = idx
            target_row = row
            break

    if not target_row:
        print("No rows marked READY in the queue. Exiting.")
        return

    print(f"Processing question {target_row.get('id')} ({target_row.get('category')})")

    image_path = capture_card(target_row["target_url"])
    cdn_url = upload_to_cdn(image_path)
    print(f"Hosted image: {cdn_url}")

    caption = f"""{target_row['hook']}

Can your Year 5 child solve this 11+ question? Drop your answer in the comments below! 👇

...
SOLUTION & EXPLANATION:
{target_row['explanation']}

👉 Practise thousands more interactive questions at picolearn.co.uk

#11plus #11plusprep #grammarSchool #elevenplus #maths #reasoning"""

    publish_to_instagram(cdn_url, caption)

    # Mark status as POSTED in the Sheet (Column F is index 6)
    sheet.update_cell(target_row_index, 6, "POSTED")
    print(f"Updated row {target_row_index} status to POSTED.")

    if os.path.exists(image_path):
        os.remove(image_path)

if __name__ == "__main__":
    main()
