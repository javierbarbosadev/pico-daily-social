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
    target_char = str(correct_letter).strip().upper()
    if target_char not in ["A", "B", "C", "D"]:
        target_char = "B"
        
    print(f"Launching Playwright to record Reel for: {url} (Target Answer: {target_char})")
    os.makedirs("raw_video", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # Match viewport to video recording size (1080x1920) so it fills the full screen
        context = browser.new_context(
            viewport={"width": 1080, "height": 1920},
            device_scale_factor=1,
            record_video_dir="raw_video/",
            record_video_size={"width": 1080, "height": 1920},
            is_mobile=True,
            has_touch=True
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle")

        # Inject Reel styling and layout scaling
        page.add_style_tag(content="""
            /* Hide top site navigation and extraneous buttons */
            header, nav, [class*="header"], [class*="navbar"], button:has-text("Check Answer") { 
                display: none !important; 
            }

            html, body {
                width: 1080px !important;
                height: 1920px !important;
                background-color: #F8FAFC !important;
                font-family: system-ui, -apple-system, sans-serif !important;
                overflow: hidden !important;
                margin: 0 !important;
                padding: 0 !important;
                box-sizing: border-box !important;
            }

            /* Scale the question content up to fill the 1080x1920 vertical canvas comfortably */
            body > div, main {
                transform: scale(1.65);
                transform-origin: top center;
                margin-top: 180px !important;
            }

            /* Top Hook Banner */
            #pico-reel-hook {
                position: fixed;
                top: 50px;
                left: 40px;
                right: 40px;
                background: #0F172A;
                color: #FFFFFF;
                padding: 32px 30px;
                border-radius: 28px;
                font-size: 42px;
                font-weight: 800;
                text-align: center;
                box-shadow: 0 15px 35px rgba(0,0,0,0.25);
                z-index: 999999;
                transform: none !important;
            }

            /* 3.5s countdown timer bar */
            #pico-timer-wrapper {
                width: 100%;
                height: 14px;
                background: #334155;
                border-radius: 7px;
                margin-top: 20px;
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
                border: 4px solid #059669 !important;
                transform: scale(1.05) !important;
                transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
                box-shadow: 0 0 35px rgba(16, 185, 129, 0.6) !important;
            }
            .pico-highlight-correct * {
                color: #FFFFFF !important;
            }

            /* Sliding CTA overlay card */
            #pico-cta-overlay {
                position: fixed;
                bottom: -500px;
                left: 40px;
                right: 40px;
                background: #FFFFFF;
                border-radius: 32px;
                border-top: 8px solid #10B981;
                box-shadow: 0 -20px 60px rgba(0,0,0,0.25);
                padding: 44px 30px;
                text-align: center;
                transition: transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
                z-index: 999999;
                transform: none;
            }
            #pico-cta-overlay.active {
                transform: translateY(-560px) !important;
            }
        """)

        # Inject Hook, CTA and target the specific letter element
        page.evaluate(f"""() => {{
            // 1. Hook Banner
            const banner = document.createElement('div');
            banner.id = 'pico-reel-hook';
            banner.innerHTML = `
                <div>⏱️ Can your Year 5 child solve this?</div>
                <div id="pico-timer-wrapper"><div id="pico-timer-bar"></div></div>
            `;
            document.body.prepend(banner);

            // 2. CTA Card
            const cta = document.createElement('div');
            cta.id = 'pico-cta-overlay';
            cta.innerHTML = `
                <div style="font-size: 38px; font-weight: 800; color: #0F172A; margin-bottom: 12px;">PicoLearn 11+ Practice</div>
                <div style="font-size: 26px; color: #475569; margin-bottom: 24px;">Smart questions that adapt to your child's level.</div>
                <div style="display: inline-block; background: #10B981; color: #fff; font-size: 26px; font-weight: 700; padding: 16px 36px; border-radius: 18px;">
                    Try free at picolearn.co.uk
                </div>
            `;
            document.body.appendChild(cta);

            // 3. Highlight the correct choice element at 3.5s by searching for its text label
            setTimeout(() => {{
                const target = "{target_char}";
                // Find any card or container starting with or displaying the letter badge
                const allElements = Array.from(document.querySelectorAll('div, button, li, label'));
                
                // Find candidates that represent the answer row for that letter
                const match = allElements.find(el => {{
                    const text = el.innerText ? el.innerText.trim() : '';
                    return (
                        (text === target || text.startsWith(target + ' ') || text.startsWith(target + '\\n')) &&
                        el.children.length <= 3 &&
                        el.offsetHeight > 30 &&
                        el.offsetHeight < 160
                    );
                }});

                if (match) {{
                    // Highlight the container row or button itself
                    const container = match.closest('button') || match.closest('[class*="option"]') || match;
                    container.classList.add('pico-highlight-correct');
                }}
            }}, 3500);

            // 4. Slide up CTA at 5.5s
            setTimeout(() => {{
                cta.classList.add('active');
            }}, 5500);
        }}""")

        # Wait to complete the 7.5 second sequence
        page.wait_for_timeout(7500)

        video_path = page.video.path()
        context.close()
        browser.close()

    print(f"Recorded raw WebM: {video_path}")

    # Convert to 1080x1920 MP4
    print("Converting to Instagram H.264 MP4...")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", "scale=1080:1920",
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
