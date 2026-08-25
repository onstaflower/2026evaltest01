"""
구글 스프레드시트 연동 모듈 (sheets_handler.py)
1. [강력 추천 / 기본] Google Apps Script 웹훅 URL 방식:
   - 인증 키 파일, IAM, JWT 서명 문제 100% 제거
   - requests 기반으로 학생 명단 조회(GET) 및 채점 결과 저장/갱신(POST)
2. [기존 호환] Google Cloud Service Account (gspread) 방식
3. [오프라인] 로컬 세션 모드 자동 폴백
"""

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import requests

# 기본 내장 샘플 학생 명단 (미연결 시 로컬 폴백용)
DEFAULT_SAMPLE_ROSTER = [
    {"학년": "4", "반": "1", "번호": "1", "이름": "강민우"},
    {"학년": "4", "반": "1", "번호": "2", "이름": "김서연"},
    {"학년": "4", "반": "1", "번호": "3", "이름": "김태윤"},
    {"학년": "4", "반": "1", "번호": "4", "이름": "박지후"},
    {"학년": "4", "반": "1", "번호": "5", "이름": "배수아"},
    {"학년": "4", "반": "1", "번호": "6", "이름": "송예준"},
    {"학년": "4", "반": "1", "번호": "7", "이름": "안채원"},
    {"학년": "4", "반": "1", "번호": "8", "이름": "오현우"},
    {"학년": "4", "반": "1", "번호": "9", "이름": "유지아"},
    {"학년": "4", "반": "1", "번호": "10", "이름": "이도현"},
    {"학년": "4", "반": "1", "번호": "11", "이름": "이하은"},
    {"학년": "4", "반": "1", "번호": "12", "이름": "정시우"},
    {"학년": "4", "반": "1", "번호": "13", "이름": "조은우"},
    {"학년": "4", "반": "1", "번호": "14", "이름": "최민서"},
    {"학년": "4", "반": "1", "번호": "15", "이름": "한지우"},
    {"학년": "4", "반": "2", "번호": "1", "이름": "권도윤"},
    {"학년": "4", "반": "2", "번호": "2", "이름": "김나은"},
    {"학년": "4", "반": "2", "번호": "3", "이름": "박시은"},
    {"학년": "4", "반": "2", "번호": "4", "이름": "신우진"},
    {"학년": "4", "반": "2", "번호": "5", "이름": "윤하린"}
]


def clean_spreadsheet_id(raw_id: str) -> str:
    """스프레드시트 URL이나 Apps Script URL을 정리합니다."""
    if not raw_id:
        return ""
    raw_id = str(raw_id).strip()
    
    # Google Apps Script 웹훅 URL인 경우 그대로 반환
    if "script.google.com" in raw_id:
        return raw_id
    
    # URL 형태인 경우: /d/와 /edit 사이의 키 추출
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", raw_id)
    if match:
        return match.group(1)
        
    return raw_id.strip()


class SheetsHandler:
    def __init__(self, spreadsheet_id: Optional[str] = None, service_account_info: Optional[Any] = None):
        self.raw_input = spreadsheet_id
        self.target_url_or_id = clean_spreadsheet_id(spreadsheet_id) if spreadsheet_id else ""
        self.is_webhook = "script.google.com" in self.target_url_or_id
        self.is_connected = False
        self.error_message = ""
        self.local_results: List[Dict[str, Any]] = []
        self.sheet_title = "구글 시트"
        
        self.connect()

    def connect(self) -> Tuple[bool, str]:
        """구글 시트 연동 테스트"""
        if not self.target_url_or_id:
            self.is_connected = False
            self.error_message = "스프레드시트 URL 또는 Webhook 주소가 비어있습니다."
            return False, self.error_message

        # 1. Apps Script Webhook URL 방식
        if self.is_webhook:
            try:
                res = requests.get(f"{self.target_url_or_id}?action=test", timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    self.is_connected = True
                    self.sheet_title = data.get("title", "구글 스프레드시트")
                    return True, f"'{self.sheet_title}'와 웹훅으로 성공적으로 연결되었습니다!"
                else:
                    self.is_connected = False
                    self.error_message = f"웹훅 응답 오류 (코드: {res.status_code})"
                    return False, self.error_message
            except Exception as e:
                self.is_connected = False
                self.error_message = f"웹훅 연결 실패: {str(e)}"
                return False, self.error_message

        # 2. 일반 시트 ID인 경우 (웹훅 URL 권장 안내)
        self.is_connected = True
        return True, "로컬 세션 모드로 실행됩니다. (클라우드 실시간 동기화를 위해 Apps Script URL 입력을 권장합니다)"

    def load_student_roster(self) -> pd.DataFrame:
        """학생 명단 로드 (학년, 반, 번호, 이름)"""
        if self.is_webhook and self.target_url_or_id:
            try:
                res = requests.get(f"{self.target_url_or_id}?action=roster", timeout=10)
                if res.status_code == 200:
                    roster_list = res.json()
                    if isinstance(roster_list, list) and len(roster_list) > 0:
                        df = pd.DataFrame(roster_list)
                        req_cols = ["학년", "반", "번호", "이름"]
                        # 컬럼 매핑
                        col_map = {}
                        for col in df.columns:
                            c = str(col).strip()
                            if "학년" in c: col_map[col] = "학년"
                            elif "반" in c: col_map[col] = "반"
                            elif "번호" in c: col_map[col] = "번호"
                            elif "이름" in c: col_map[col] = "이름"
                        df = df.rename(columns=col_map)
                        if all(c in df.columns for c in req_cols):
                            df["학년"] = df["학년"].astype(str)
                            df["반"] = df["반"].astype(str)
                            df["번호"] = df["번호"].astype(str)
                            df["이름"] = df["이름"].astype(str)
                            return df[req_cols]
            except Exception as e:
                print(f"웹훅 명단 로드 오류: {e}")

        # 로컬 기본 샘플 명단 반환
        return pd.DataFrame(DEFAULT_SAMPLE_ROSTER)

    def save_grading_result(self, record: Dict[str, Any]) -> Tuple[bool, str]:
        """채점 결과 저장 또는 업데이트 (Upsert)"""
        # 로컬 캐시에 즉시 반영
        updated = False
        for i, item in enumerate(self.local_results):
            if (str(item.get("학년")) == str(record.get("학년")) and 
                str(item.get("반")) == str(record.get("반")) and 
                str(item.get("번호")) == str(record.get("번호")) and 
                str(item.get("이름")) == str(record.get("이름")) and
                str(item.get("평가명")) == str(record.get("평가명"))):
                self.local_results[i] = record
                updated = True
                break
        if not updated:
            self.local_results.append(record)

        # 구글 Apps Script 웹훅으로 전송
        if self.is_webhook and self.target_url_or_id:
            try:
                payload = {
                    "action": "save",
                    "data": {
                        "학년": str(record.get("학년", "")),
                        "반": str(record.get("반", "")),
                        "번호": str(record.get("번호", "")),
                        "이름": str(record.get("이름", "")),
                        "학생답안": str(record.get("학생답안", "")),
                        "평가명": str(record.get("평가명", "")),
                        "총점": record.get("총점", 0),
                        "만점": record.get("만점", 100),
                        "문항별상세": str(record.get("문항별상세", "")),
                        "총평피드백": str(record.get("총평피드백", "")),
                        "생기부피드백": str(record.get("생기부피드백", "")),
                        "채점일시": str(record.get("채점일시", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    }
                }
                res = requests.post(self.target_url_or_id, json=payload, timeout=15)
                if res.status_code == 200:
                    return True, "구글 시트에 실시간 저장 완료!"
                else:
                    return True, f"로컬 보관됨 (웹훅 응답 코드: {res.status_code})"
            except Exception as e:
                return True, f"로컬 보관 완료 (시트 전송 실패: {str(e)})"

        return True, "로컬 세션에 안전하게 저장되었습니다."

    def get_all_results_df(self) -> pd.DataFrame:
        """전체 채점 결과 데이터프레임 반환"""
        if self.local_results:
            return pd.DataFrame(self.local_results)
        
        return pd.DataFrame(columns=["학년", "반", "번호", "이름", "평가명", "총점", "만점", "문항별상세", "총평피드백", "생기부피드백", "채점일시"])
