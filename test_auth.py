"""
구글 시트 연결 독립 진단 스크립트
- Streamlit 없이 직접 인증 테스트
"""
import json
import os
import datetime

KEY_FILE = os.path.join(os.path.dirname(__file__), "evaluatingtest01-788da0427ce1.json")
SPREADSHEET_ID = "1b4jFv5sLf9mZt3hPmZH5fnnw6klLSpwPhN4zZVne6dM"
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

print("=" * 60)
print("구글 시트 연결 진단 스크립트")
print("=" * 60)

# 1. 현재 시각 확인
now = datetime.datetime.now()
print(f"\n[1] 현재 시스템 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}")
print("    ※ 이 시각이 실제 시각과 5분 이상 다르면 JWT 오류 발생")

# 2. 키 파일 존재 확인
print(f"\n[2] 키 파일 경로: {KEY_FILE}")
if os.path.exists(KEY_FILE):
    with open(KEY_FILE, "r") as f:
        key_data = json.load(f)
    print(f"    ✅ 파일 존재: YES")
    print(f"    private_key_id : {key_data.get('private_key_id')}")
    print(f"    client_email   : {key_data.get('client_email')}")
    print(f"    project_id     : {key_data.get('project_id')}")
else:
    print("    ❌ 파일 없음!")
    exit(1)

# 3. 라이브러리 확인
print("\n[3] 필수 라이브러리 확인")
try:
    import gspread
    print(f"    ✅ gspread: {gspread.__version__}")
except ImportError as e:
    print(f"    ❌ gspread: {e}")
    exit(1)

try:
    from google.oauth2.service_account import Credentials
    print(f"    ✅ google-auth: OK")
except ImportError as e:
    print(f"    ❌ google-auth: {e}")
    exit(1)

# 4. 인증 시도
print("\n[4] 인증 시도")
try:
    creds = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
    print(f"    ✅ 인증 객체 생성 성공")
    print(f"    서비스 계정: {creds.service_account_email}")
except Exception as e:
    print(f"    ❌ 인증 객체 생성 실패: {e}")
    exit(1)

# 5. gspread 연결 시도
print("\n[5] 구글 시트 연결 시도")
try:
    client = gspread.authorize(creds)
    print(f"    ✅ gspread 클라이언트 생성 성공")
except Exception as e:
    print(f"    ❌ gspread 클라이언트 실패: {e}")
    exit(1)

# 6. 시트 열기 시도
print(f"\n[6] 스프레드시트 열기 시도 (ID: {SPREADSHEET_ID})")
try:
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    print(f"    ✅ 연결 성공! 스프레드시트명: '{spreadsheet.title}'")
    sheets = spreadsheet.worksheets()
    print(f"    시트 목록: {[s.title for s in sheets]}")
except Exception as e:
    print(f"    ❌ 시트 열기 실패: {e}")

print("\n" + "=" * 60)
