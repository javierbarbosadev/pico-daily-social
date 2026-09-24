import os
import json
import time
import subprocess
import requests
import cloudinary
import cloudinary.uploader
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.sync_api import sync_playwright

# 1. Environment Configurations
GCP_KEY = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
IG_USER_ID = os.getenv("IG_USER_ID")
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

def record_reel_video(url: str, correct_letter: str, output_mp4: str = "daily_reel.mp4") -> str:
    print(f"Launching Playwright to record Reel for: {url} (Answer: {correct_letter})")
    
    os.makedirs("raw_video", exist_ok=True)
    letter_index_map = {"A": 0, "B": 1, "C": 2, "D": 3}
    target_idx = letter_index_map.get(str(correct_letter).strip().upper(), 1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 540, "height": 960}, # 9:16 mobile canvas
            record_video_dir="raw_video/",
            record_video_size={"width": 1080, "height": 1920}
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle")

        # Inject Reel overlay styles: Hook banner, animated timer bar, answer flash, and CTA card
        page.add_style_tag(content="""
            /* Hide top site navigation and footers */
            header, nav, [class*="header"], [class*="navbar"] { display: none !important; }

            body {
                background-color: #F8FAFC !important;
                padding: 120px 24px 40px 24px !important;
                font-family: system-ui, -apple-system, sans-serif !important;
                position: relative !important;
                overflow: hidden !important;
            }

            /* Top Hook Banner */
            #pico-reel-hook {
                position: fixed;
                top: 24px;
                left: 20px;
                right: 20px;
                background: #0F172A;
                color: #FFFFFF;
                padding: 16px 20px;
                border-radius: 16px;
                font-size: 20px;
                font-weight: 700;
                text-align: center;
                box-shadow: 0 10px 25px rgba(0,0,0,0.15);
                z-index: 9999;
            }

            /* 3.5-second countdown progress bar */
            #pico-timer-wrapper {
                width: 100%;
                height: 8px;
                background: #334155;
                border-radius: 4px;
                margin-top: 12px;
                overflow: hidden;
            }
            #pico-timer-bar {
                height: 100%;
                background: #10B981;
                width: 100%;
                animation: picoCountdown 3.5s linear forwards;
            }

            @keyframes picoCountdown {
                from { width: 100%; background: #10B981; }
                50%  { background: #F59E0B; }
                to   { width: 0%; background: #EF4444; }
            }

            /* Correct answer pop animation */
            .pico-highlight-correct {
                background-color: #10B981 !important;
                color: #FFFFFF !important;
                border-color: #059669 !important;
                transform: scale(1.04) !important;
                transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
                box-shadow: 0 0 25px rgba(16, 185, 129, 0.4) !important;
            }

            /* Sliding CTA overlay card */
            #pico-cta-overlay {
                position: fixed;
                bottom: -280px;
                left: 16px;
                right: 16px;
                background: #FFFFFF;
                border-radius: 20px;
                border-top: 5px solid #10B981;
                box-shadow: 0 -10px 40px rgba(0,0,0,0.2);
                padding: 24px;
                text-align: center;
                transition: transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
                z-index: 10000;
            }
            #pico-cta-overlay.active {
                transform: translateY(-295px);
            }
        """)

        # Inject DOM elements and trigger timing via browser JS
        page.evaluate(f"""() => {{
            // 1. Inject Hook Banner
            const banner = document.createElement('div');
            banner.id = 'pico-reel-hook';
            banner.innerHTML = `
                <div>⏱️ Can your Year 5 child solve this?</div>
                <div id="pico-timer-wrapper"><div id="pico-timer-bar"></div></div>
            `;
            document.body.prepend(banner);

            // 2. Inject CTA Overlay
            const cta = document.createElement('div');
            cta.id = 'pico-cta-overlay';
            cta.innerHTML = `
                <div style="font-size: 20px; font-weight: 800; color: #0F172A; margin-bottom: 6px;">PicoLearn 11+ Practice</div>
                <div style="font-size: 15px; color: #475569; margin-bottom: 12px;">Difficulty adapts automatically to your child.</div>
                <div style="display: inline-block; background: #10B981; color: #fff; font-size: 14px; font-weight: 700; padding: 8px 16px; border-radius: 10px;">
                    Try free at picolearn.co.uk
                </div>
            `;
            document.body.appendChild(cta);

            // 3. Trigger answer highlight at 3.5s
            setTimeout(() => {{
                // Finds answer buttons or choice cards on the page
                const options = document.querySelectorAll('button, [class*="option"], [class*="choice"], [class*="answer"]');
                if (options.length > {target_idx}) {{
                    options[{target_idx}].classList.add('pico-highlight-correct');
                }}
            }}, 3500);

            // 4. Slide up CTA at 5.5s
            setTimeout(() => {{
                cta.classList.add('active');
            }}, 5500);
        }}""")

        # Record total duration: 7.5 seconds
        page.wait_for_timeout(7500)
        
        # Save video
        video_path = page.video.path()
        context.close()
        browser.close()

    print(f"Recorded raw WebM: {video_path}")

    # Convert to Instagram-compliant MP4 using ffmpeg
    print("Converting to Instagram H.264 MP4...")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30",
        output_mp4
    ]
    subprocess.run(ffmpeg_cmd, check=True)
    print("Video rendered successfully.")
    return output_mp4

def upload_video_to_cdn(video_path: str) -> str:
    print("Uploading MP4 Reel to Cloudinary...")
    res = cloudinary.uploader.upload(
        video_path,
        folder="picolearn_reels",
        resource_type="video",
        overwrite=True,
        invalidate=True
    )
    url = res["secure_url"]
    print(f"Video hosted: {url}")
    # Wait 8s for CDN edge warm-up
    time.sleep(8)
    return url

def publish_reel_to_instagram(video_url: str, caption: str):
    base_url = f"https://graph.facebook.com/v21.0/{IG_USER_ID}"

    print("Creating Reel media container on Instagram...")
    container_payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    res = requests.post(f"{base_url}/media", data=container_payload).json()
    if "id" not in res:
        raise RuntimeError(f"Reel container creation failed: {res}")

    container_id = res["id"]
    print(f"Reel Container created. ID: {container_id}")

    # Meta takes 20-30 seconds to encode and process video
    print("Waiting 25 seconds for Meta video processing...")
    time.sleep(25)

    print("Publishing Reel to feed...")
    pub_res = requests.post(
        f"{base_url}/media_publish",
        data={"creation_id": container_id, "access_token": ACCESS_TOKEN}
    ).json()

    if "id" not in pub_res:
        raise RuntimeError(f"Publish failed: {pub_res}")

    print(f"Success! Reel live on @pico11plus. Live ID: {pub_res['id']}")

def main():
    if not GCP_KEY:
        raise ValueError("Missing GCP_SERVICE_ACCOUNT_KEY secret.")

    creds_dict = json.loads(GCP_KEY)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    sheet = client.open("PicoLearn Social Queue").sheet1
    records = sheet.get_all_records()

    if not records:
        print("No records found in Google Sheet.")
        return

    # Normalise headers for safe column lookup
    headers = [str(h).strip().lower() for h in sheet.row_values(1)]
    status_col = headers.index("status") + 1 if "status" in headers else 6

    for idx, row in enumerate(records, start=2):
        # Normalise dictionary keys to lowercase with underscores
        clean_row = {str(k).strip().lower().replace(" ", "_"): v for k, v in row.items()}

        if str(clean_row.get("status", "")).strip().upper() == "READY":
            url = (
                clean_row.get("target_url")
                or clean_row.get("preview_url")
                or clean_row.get("url")
                or clean_row.get("question_url")
                or clean_row.get("link")
            )

            if not url or not str(url).strip().startswith("http"):
                print(f"Skipping row {idx}: URL is missing or invalid. Columns found: {list(clean_row.keys())}")
                continue

            caption = (
                clean_row.get("caption")
                or "Can your child solve this daily 11+ challenge? Drop your answer below! 👇 #11plus #11plusprep #grammarschool"
            )

            correct_answer = (
                clean_row.get("answer")
                or clean_row.get("correct_answer")
                or clean_row.get("correct_option")
                or "B"
            )

            print(f"Processing Reel row {idx} with URL: {url} (Answer: {correct_answer})")
            mp4_file = record_reel_video(str(url).strip(), correct_letter=str(correct_answer).strip())
            video_cdn_url = upload_video_to_cdn(mp4_file)
            publish_reel_to_instagram(video_cdn_url, caption)

            # Update row status to POSTED
            sheet.update_cell(idx, status_col, "POSTED")
            print(f"Row {idx} updated to POSTED.")
            break

if __name__ == "__main__":
    main()
