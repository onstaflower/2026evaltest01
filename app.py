"""
학생 서술형 평가 AI 채점 & 결과 관리 시스템 (app.py)
- Streamlit + Gemini 1.5 Flash + Google Sheets Webhook 기반
- 학생: 로그인 없는 명단 선택 및 손글씨 답안지 다중 업로드 제출 (교사 메뉴 완벽 차단)
- 교사: 비밀번호 로그인 후 루브릭 설정, 손글씨 OCR 및 AI 채점 확인, 점수/피드백 수정, 재채점, 구글 시트 연동
"""

import datetime
import os
from typing import Any, Dict, List, Optional
import pandas as pd
from PIL import Image
import streamlit as st

from gemini_evaluator import GeminiEvaluator
from sheets_handler import SheetsHandler, clean_spreadsheet_id
from utils import convert_df_to_csv, extract_text_from_file, format_student_id, process_images_for_ai
from storage_manager import load_global_rubric, save_global_rubric, save_submission


# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 디자인 시스템 (CSS)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AI 서술형 평가 채점 시스템",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 세련되고 정제된 교육용 커스텀 스타일
st.markdown("""
<style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    * {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #1E1B4B 0%, #312E81 50%, #4338CA 100%);
        color: white;
        padding: 1.8rem 2.2rem;
        border-radius: 16px;
        margin-bottom: 1.8rem;
        box-shadow: 0 10px 25px -5px rgba(49, 46, 129, 0.2);
    }
    .main-header h1 {
        font-size: 1.8rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.02em;
        color: #FFFFFF !important;
    }
    .main-header p {
        font-size: 0.95rem;
        color: #C7D2FE;
        margin-top: 0.4rem;
        margin-bottom: 0;
    }

    .custom-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.4rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
    }

    .badge-primary {
        background-color: #EEF2FF;
        color: #4338CA;
        font-size: 0.8rem;
        font-weight: 600;
        padding: 4px 10px;
        border-radius: 20px;
        border: 1px solid #C7D2FE;
        display: inline-block;
    }

    .score-box {
        text-align: center;
        background: linear-gradient(135deg, #F8FAFC 0%, #EEF2FF 100%);
        border: 2px solid #6366F1;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
    }
    .score-number {
        font-size: 2.4rem;
        font-weight: 800;
        color: #4338CA;
        line-height: 1.1;
    }
    .score-label {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 2. 세션 상태 초기화
# -----------------------------------------------------------------------------
def init_session_state():
    default_api_key = ""
    if "GEMINI_API_KEY" in st.secrets:
        default_api_key = st.secrets["GEMINI_API_KEY"]
    elif "GEMINI_API_KEY" in os.environ:
        default_api_key = os.environ["GEMINI_API_KEY"]

    default_sheet_id = ""
    if "SPREADSHEET_ID" in st.secrets:
        default_sheet_id = clean_spreadsheet_id(st.secrets["SPREADSHEET_ID"])
    elif "SPREADSHEET_ID" in os.environ:
        default_sheet_id = clean_spreadsheet_id(os.environ["SPREADSHEET_ID"])

    default_teacher_pw = "1234"
    if "TEACHER_PASSWORD" in st.secrets:
        default_teacher_pw = str(st.secrets["TEACHER_PASSWORD"])

    if "api_key" not in st.session_state:
        st.session_state.api_key = default_api_key
    if "sheet_id" not in st.session_state:
        st.session_state.sheet_id = default_sheet_id
    if "is_teacher_authenticated" not in st.session_state:
        st.session_state.is_teacher_authenticated = False
    if "teacher_password" not in st.session_state:
        st.session_state.teacher_password = default_teacher_pw

    if "rubric_title" not in st.session_state:
        st.session_state.rubric_title = "2026학년도 과학 서술형 평가 (식물의 구조와 광합성)"
    if "rubric_text" not in st.session_state:
        st.session_state.rubric_text = """[평가 영역] 과학 탐구 및 개념 적용 (총점: 100점)

[문항 1] 광합성의 정의와 필요 요소 및 생성 물질 (배점: 50점)
- 상 (45~50점): 광합성의 개념, 필요 물질(빛, 물, 이산화탄소), 생성 물질(산소, 양분/포도당/녹말), 장소(엽록체)를 모두 정확히 서술함.
- 중 (30~44점): 필수 요소 중 1~2개 누락 또는 서술이 부분적으로 미흡함.
- 하 (0~29점): 광합성의 개념을 오인하거나 핵심 물질 서술이 결여됨.

[문항 2] 광합성 실험(아이오딘 반응) 결과 해석 (배점: 50점)
- 상 (45~50점): 대조군과 실험군의 색깔 변화 차이와 그 원인(녹말 생성 여부)을 과학적 인과관계에 따라 명확히 설명함.
- 중 (30~44점): 실험 결과는 언급했으나 원인에 대한 인과적 설명이 다소 부족함.
- 하 (0~29점): 실험 결과 및 원리 해석이 부정확함."""

    if "submissions" not in st.session_state:
        st.session_state.submissions = {}
    if "selected_student_key" not in st.session_state:
        st.session_state.selected_student_key = None

init_session_state()


# -----------------------------------------------------------------------------
# 3. 서비스 클라이언트 로드 (Gemini & Sheets)
# -----------------------------------------------------------------------------
@st.cache_resource
def get_evaluator(api_key: str) -> GeminiEvaluator:
    return GeminiEvaluator(api_key=api_key)

@st.cache_resource
def get_sheets_handler(sheet_id: str) -> SheetsHandler:
    try:
        service_info = dict(st.secrets) if hasattr(st, "secrets") else None
    except Exception:
        service_info = None
    return SheetsHandler(spreadsheet_id=sheet_id, service_account_info=service_info)

evaluator = get_evaluator(st.session_state.api_key)
sheets_handler = get_sheets_handler(st.session_state.sheet_id)


# -----------------------------------------------------------------------------
# 4. 헤더 및 사이드바 (교사 전용 비밀번호 로그인 보호)
# -----------------------------------------------------------------------------
st.markdown("""
<div class="main-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h1>📝 AI 학생 손글씨 서술형 평가 채점 시스템</h1>
            <p>Gemini 1.5 Flash 멀티모달 비전 OCR 채점 & 구글 시트 실시간 자동 기록</p>
        </div>
        <div>
            <span class="badge-primary">스마트 평가 시스템</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 시스템 상태")
    
    if evaluator.is_configured:
        st.success("🟢 Gemini 1.5 Flash AI 준비 완료")
    else:
        st.warning("🟡 Gemini API 미연동 (샘플 모드)")

    if sheets_handler.is_connected:
        st.success("🟢 구글 시트 실시간 연동 완료")
    else:
        st.info("🔵 로컬 세션 모드")

    st.markdown("---")

    # 교사 관리자 로그인 / 로그아웃 영역
    if not st.session_state.is_teacher_authenticated:
        with st.expander("🔒 교사 관리자 로그인"):
            st.caption("선생님 전용 채점 관리 & 대시보드 접근")
            pw_input = st.text_input("교사 비밀번호", type="password", key="teacher_login_pw")
            if st.button("로그인", type="primary", use_container_width=True):
                if pw_input == str(st.session_state.teacher_password):
                    st.session_state.is_teacher_authenticated = True
                    st.success("교사 인증 완료!")
                    st.rerun()
                else:
                    st.error("비밀번호가 올바르지 않습니다.")
    else:
        st.success("👩‍🏫 선생님 모드 활성화됨")
        if st.button("🔓 로그아웃 (학생 모드로 전환)", use_container_width=True):
            st.session_state.is_teacher_authenticated = False
            st.rerun()

        st.markdown("---")
        st.subheader("📋 현재 평가 기준 (루브릭)")
        st.markdown(f"**{st.session_state.rubric_title}**")
        with st.expander("루브릭 본문 미리보기"):
            st.text(st.session_state.rubric_text[:300] + ("..." if len(st.session_state.rubric_text) > 300 else ""))


# -----------------------------------------------------------------------------
# 5. 각 모드별 화면 정의 (학생 모드 / 교사 모드 / 시스템 설정)
# -----------------------------------------------------------------------------

def render_student_mode():
    """학생 답안 제출 화면"""
    st.subheader("📤 서술형 평가 답안지 제출")
    st.write("학생 본인의 학년, 반, 번호, 이름을 선택하고 직접 작성한 손글씨 답안지 사진을 업로드해 주세요.")

    roster_df = sheets_handler.load_student_roster()
    
    col_g, col_c, col_s = st.columns(3)
    
    grades = sorted(list(roster_df["학년"].astype(str).unique()))
    with col_g:
        selected_grade = st.selectbox("1️⃣ 학년", grades if grades else ["4"], key="st_grade")

    filtered_by_grade = roster_df[roster_df["학년"].astype(str) == str(selected_grade)]
    classes = sorted(list(filtered_by_grade["반"].astype(str).unique()))
    with col_c:
        selected_class = st.selectbox("2️⃣ 반", classes if classes else ["1"], key="st_class")

    filtered_by_class = filtered_by_grade[filtered_by_grade["반"].astype(str) == str(selected_class)]
    student_options = [
        f"{row['번호']}번 - {row['이름']}" 
        for _, row in filtered_by_class.sort_values(by="번호", key=lambda x: pd.to_numeric(x, errors='coerce')).iterrows()
    ]
    with col_s:
        selected_student_str = st.selectbox("3️⃣ 학생 (번호 - 이름)", student_options if student_options else ["1번 - 홍길동"], key="st_student")

    if student_options and selected_student_str:
        s_num = selected_student_str.split("번")[0].strip()
        s_name = selected_student_str.split("-")[1].strip()
    else:
        s_num, s_name = "1", "홍길동"

    student_key = f"{selected_grade}_{selected_class}_{s_num}_{s_name}"

    st.markdown("---")

    st.markdown("#### 📷 손글씨 답안지 사진 업로드 (여러 장 연속 업로드 가능)")
    st.caption("답안지가 여러 쪽이거나 내용이 긴 경우, 여러 장의 사진을 한 번에 선택하여 업로드하세요. (JPG, PNG, WEBP 지원)")

    uploaded_images = st.file_uploader(
        "답안지 이미지 파일 선택",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=f"uploader_{student_key}"
    )

    if uploaded_images:
        st.markdown(f"**선택된 이미지 총 {len(uploaded_images)}장**")
        cols = st.columns(min(len(uploaded_images), 4))
        for idx, img_file in enumerate(uploaded_images):
            with cols[idx % 4]:
                st.image(img_file, caption=f"페이지 {idx+1}: {img_file.name}", use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 답안지 제출 및 AI 채점 요청하기", type="primary", use_container_width=True):
        if not uploaded_images:
            st.error("⚠️ 채점할 답안지 이미지를 1장 이상 업로드해 주세요.")
        else:
            with st.spinner("AI(Gemini 1.5 Flash)가 손글씨를 읽고 루브릭에 따라 채점 중입니다. 잠시만 기다려주세요..."):
                processed_pil_images = process_images_for_ai(uploaded_images)
                
                student_info = {
                    "학년": str(selected_grade),
                    "반": str(selected_class),
                    "번호": str(s_num),
                    "이름": str(s_name)
                }
                
                result = evaluator.evaluate_submission(
                    images=processed_pil_images,
                    rubric_text=st.session_state.rubric_text,
                    student_info=student_info
                )

                if result.get("success", False):
                    submission_record = {
                        "학년": str(selected_grade),
                        "반": str(selected_class),
                        "번호": str(s_num),
                        "이름": str(s_name),
                        "평가명": st.session_state.rubric_title,
                        "총점": result.get("total_score", 0),
                        "만점": result.get("max_score", 100),
                        "ocr_text": result.get("ocr_text", ""),
                        "학생답안": result.get("ocr_text", ""),
                        "questions": result.get("questions", []),
                        "문항별상세": "\n".join([f"Q{q.get('question_no')}: {q.get('score')}/{q.get('max_score')} ({q.get('reason')})" for q in result.get("questions", [])]),
                        "총평피드백": result.get("general_feedback", ""),
                        "생기부피드백": result.get("neis_record", ""),
                        "채점일시": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "images": processed_pil_images,
                        "is_mock": result.get("is_mock", False)
                    }
                    st.session_state.submissions[student_key] = submission_record
                    st.session_state.selected_student_key = student_key

                    save_success, save_msg = sheets_handler.save_grading_result(submission_record)
                    # Persist submission locally for async handling
                    save_submission(student_key, submission_record)
                    
                    st.success(f"🎉 **{s_name}** 학생의 답안지가 성공적으로 제출 및 채점되었습니다! (총점: {result.get('total_score')}점 / {result.get('max_score')}점)")
                    if save_success:
                        st.info(f"💾 데이터 영속성: {save_msg}")

                    with st.expander("📄 제출 답안지 인식(OCR) 및 AI 피드백 미리보기", expanded=True):
                        st.markdown(f"**[AI 추출 손글씨 텍스트]**\n\n```\n{result.get('ocr_text', '')}\n```")
                        st.markdown(f"**[학생 격려 총평]**\n\n> {result.get('general_feedback', '')}")
                else:
                    st.error(f"❌ 채점 처리 중 오류가 발생했습니다: {result.get('error', '알 수 없는 오류')}")


def render_teacher_mode():
    """교사 전용 채점 관리 & 대시보드 화면"""
    st.subheader("👩‍🏫 서술형 평가 채점 관리 및 교사 대시보드")
    
    with st.expander("📋 평가 루브릭(채점 기준표) 등록 및 수정", expanded=False):
        col_r1, col_r2 = st.columns([1, 1])
        with col_r1:
            rubric_title_input = st.text_input("평가 제목", value=st.session_state.rubric_title)
            rubric_file = st.file_uploader("루브릭 파일 업로드 (PDF / TXT)", type=["pdf", "txt", "md"])
            if rubric_file:
                extracted = extract_text_from_file(rubric_file.read(), rubric_file.name)
                st.session_state.rubric_text = extracted
                st.success(f"'{rubric_file.name}'에서 루브릭을 성공적으로 불러왔습니다.")

        with col_r2:
            st.session_state.rubric_text = st.text_area("루브릭 세부 내용 및 배점 기준", value=st.session_state.rubric_text, height=180)
            if st.button("💾 루브릭 설정 저장"):
                st.session_state.rubric_title = rubric_title_input
                st.success("루브릭 설정이 저장되었습니다. 이후 제출되는 답안에 즉시 반영됩니다.")

    st.markdown("---")

    submissions = st.session_state.submissions
    
    if not submissions:
        st.info("📌 아직 제출된 답안지가 없습니다. 학생 화면에서 답안지를 제출하거나 아래 샘플 데모 데이터를 불러와보세요.")
        if st.button("✨ 데모 제출 샘플 2건 자동 생성하기"):
            demo1_key = "4_1_2_김서연"
            st.session_state.submissions[demo1_key] = {
                "학년": "4", "반": "1", "번호": "2", "이름": "김서연",
                "평가명": st.session_state.rubric_title,
                "총점": 92, "만점": 100,
                "ocr_text": "[문항 1]\n식물은 잎의 엽록체에서 햇빛, 이산화탄소, 물을 받아 광합성을 하고 포도당과 산소를 만듭니다.\n\n[문항 2]\n햇빛을 받은 잎은 광합성으로 녹말이 생성되어 아이오딘-아이오딘화 칼륨 용액에 청람색으로 반응했습니다.",
                "questions": [
                    {"question_no": 1, "score": 48, "max_score": 50, "reason": "광합성의 정의, 장소(엽록체), 필요물질, 생성물질을 모두 완벽하게 서술함.", "feedback": "개념 이해도가 매우 우수합니다."},
                    {"question_no": 2, "score": 44, "max_score": 50, "reason": "아이오딘 반응과 녹말 생성 원리를 잘 서술했으나, 대조군 언급이 다소 간략함.", "feedback": "빛을 받지 않은 잎과의 비교를 덧붙이면 더욱 완벽합니다."}
                ],
                "문항별상세": "Q1: 48/50 (개념 완벽)\nQ2: 44/50 (대조군 비교 보완)",
                "총평피드백": "광합성의 전 과정과 실험 원리를 정확하게 이해하고 체계적으로 기술한 우수한 답안입니다.",
                "생기부피드백": "식물의 광합성 작용 및 실험적 검증 원리를 깊이 있게 이해하고 논리적인 과학적 서술 역량을 발휘함.",
                "채점일시": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "images": [],
                "is_mock": True
            }
            demo2_key = "4_1_5_배수아"
            st.session_state.submissions[demo2_key] = {
                "학년": "4", "반": "1", "번호": "5", "이름": "배수아",
                "평가명": st.session_state.rubric_title,
                "총점": 78, "만점": 100,
                "ocr_text": "[문항 1]\n광합성은 식물이 빛과 물로 영양분을 만드는 것입니다.\n\n[문항 2]\n아이오딘을 떨어뜨렸을 때 색이 변했습니다.",
                "questions": [
                    {"question_no": 1, "score": 40, "max_score": 50, "reason": "이산화탄소와 산소 생성에 대한 언급이 누락됨.", "feedback": "필요한 기체와 방출되는 기체도 함께 적어보세요."},
                    {"question_no": 2, "score": 38, "max_score": 50, "reason": "색깔 변화의 정확한 명칭(청람색)과 녹말 생성 원리가 부족함.", "feedback": "어떤 색으로 변했는지, 왜 변했는지 구체적으로 적어보세요."}
                ],
                "문항별상세": "Q1: 40/50 (기체 요소 보완 필요)\nQ2: 38/50 (색상 및 원리 보완)",
                "총평피드백": "핵심 개념을 잘 파악하고 있으나, 반응 조건과 구체적인 생성 물질을 보완하면 좋겠습니다.",
                "생기부피드백": "광합성의 기본 개념을 이해하고 있으며 실험 현상을 관찰하여 사실에 기반해 서술함.",
                "채점일시": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "images": [],
                "is_mock": True
            }
            st.session_state.selected_student_key = demo1_key
            st.rerun()
    else:
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        total_sub_count = len(submissions)
        avg_score = sum([v.get("총점", 0) for v in submissions.values()]) / max(total_sub_count, 1)
        max_sub_score = max([v.get("총점", 0) for v in submissions.values()])
        min_sub_score = min([v.get("총점", 0) for v in submissions.values()])

        with col_m1:
            st.metric("총 제출 학생 수", f"{total_sub_count}명")
        with col_m2:
            st.metric("학급 평균 점수", f"{avg_score:.1f}점")
        with col_m3:
            st.metric("최고 점수", f"{max_sub_score}점")
        with col_m4:
            st.metric("최저 점수", f"{min_sub_score}점")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 🎯 개별 학생 채점 상세 검토 및 피드백 수정")

        submission_keys = list(submissions.keys())
        student_display_names = [
            f"{submissions[k]['학년']}학년 {submissions[k]['반']}반 {submissions[k]['번호']}번 {submissions[k]['이름']} (총점: {submissions[k]['총점']}점)"
            for k in submission_keys
        ]
        
        curr_idx = 0
        if st.session_state.selected_student_key in submission_keys:
            curr_idx = submission_keys.index(st.session_state.selected_student_key)

        selected_display = st.selectbox(
            "검토할 학생 선택",
            student_display_names,
            index=curr_idx,
            key="teacher_student_selector"
        )
        
        selected_key = submission_keys[student_display_names.index(selected_display)]
        st.session_state.selected_student_key = selected_key
        curr_sub = submissions[selected_key]

        col_left, col_right = st.columns([1, 1], gap="large")

        with col_left:
            st.markdown("##### 📷 학생 제출 손글씨 원본 답안지")
            if curr_sub.get("images"):
                for p_idx, pil_img in enumerate(curr_sub["images"]):
                    st.image(pil_img, caption=f"답안지 페이지 {p_idx+1}", use_container_width=True)
            else:
                st.info("첨부된 원본 답안지 이미지가 없습니다 (데모 모드)")

            st.markdown("##### 🔤 AI OCR 추출 원문 (수정 가능)")
            edited_ocr = st.text_area(
                "인식된 텍스트",
                value=curr_sub.get("ocr_text", ""),
                height=180,
                key=f"ocr_edit_{selected_key}"
            )

        with col_right:
            st.markdown(f"##### 📊 AI 채점 결과: **{curr_sub['이름']} 학생**")
            
            c_sc1, c_sc2 = st.columns([1, 2])
            with c_sc1:
                st.markdown(f"""
                <div class="score-box">
                    <div class="score-number">{curr_sub.get('총점', 0)}</div>
                    <div class="score-label">/ {curr_sub.get('만점', 100)}점</div>
                </div>
                """, unsafe_allow_html=True)
            with c_sc2:
                edited_total_score = st.number_input(
                    "교사 최종 점수 수정",
                    min_value=0,
                    max_value=int(curr_sub.get("만점", 100)),
                    value=int(curr_sub.get("총점", 0)),
                    key=f"score_edit_{selected_key}"
                )
                st.caption(f"제출 일시: {curr_sub.get('채점일시', '')}")

            st.markdown("##### 📝 문항별 세부 채점 근거")
            if curr_sub.get("questions"):
                for q in curr_sub["questions"]:
                    with st.container():
                        st.markdown(f"**문항 {q.get('question_no')}번** : `{q.get('score')}점 / {q.get('max_score')}점`")
                        st.markdown(f"- **채점 사유**: {q.get('reason')}")
                        st.markdown(f"- **개별 피드백**: {q.get('feedback')}")
            else:
                st.write(curr_sub.get("문항별상세", "세부 내역 없음"))

            st.markdown("##### 💬 종합 학생 격려 총평 피드백")
            edited_feedback = st.text_area(
                "피드백 수정",
                value=curr_sub.get("총평피드백", ""),
                height=90,
                key=f"fb_edit_{selected_key}"
            )

            st.markdown("##### 📑 생활기록부(NEIS) 세특 서술문")
            edited_neis = st.text_area(
                "생기부 문장 수정",
                value=curr_sub.get("생기부피드백", ""),
                height=90,
                key=f"neis_edit_{selected_key}"
            )

            st.markdown("<br>", unsafe_allow_html=True)
            col_b1, col_b2 = st.columns(2)
            
            with col_b1:
                if st.button("💾 교사 수정사항 저장", type="primary", use_container_width=True):
                    curr_sub["총점"] = edited_total_score
                    curr_sub["ocr_text"] = edited_ocr
                    curr_sub["총평피드백"] = edited_feedback
                    curr_sub["생기부피드백"] = edited_neis
                    st.session_state.submissions[selected_key] = curr_sub

                    ok, msg = sheets_handler.save_grading_result(curr_sub)
                    st.success(f"수정사항이 저장되었습니다! ({msg})")
                    st.rerun()

            with col_b2:
                with st.popover("🤖 AI 재채점(Regrade) 실행", use_container_width=True):
                    st.markdown("**재채점 지침 입력**")
                    teacher_regrade_note = st.text_area(
                        "AI에게 추가로 전달할 채점 지침 / 기준",
                        placeholder="예: 문항 2에서 '인과관계' 요소를 좀 더 엄격하게 채점하고, 실생활 연계 여부를 점수에 반영해줘.",
                        key=f"regrade_note_{selected_key}"
                    )
                    if st.button("⚡ 재채점 시작", type="primary", use_container_width=True):
                        with st.spinner("AI가 교사 지침을 바탕으로 답안지를 재채점 중입니다..."):
                            regrade_res = evaluator.evaluate_submission(
                                images=curr_sub.get("images", []),
                                rubric_text=st.session_state.rubric_text,
                                student_info={
                                    "학년": curr_sub["학년"],
                                    "반": curr_sub["반"],
                                    "번호": curr_sub["번호"],
                                    "이름": curr_sub["이름"]
                                },
                                teacher_notes=teacher_regrade_note,
                                is_regrade=True
                            )
                            if regrade_res.get("success", False):
                                curr_sub["총점"] = regrade_res.get("total_score", curr_sub["총점"])
                                curr_sub["ocr_text"] = regrade_res.get("ocr_text", curr_sub["ocr_text"])
                                curr_sub["questions"] = regrade_res.get("questions", curr_sub.get("questions", []))
                                curr_sub["총평피드백"] = regrade_res.get("general_feedback", curr_sub["총평피드백"])
                                curr_sub["생기부피드백"] = regrade_res.get("neis_record", curr_sub["생기부피드백"])
                                curr_sub["채점일시"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (재채점됨)"
                                st.session_state.submissions[selected_key] = curr_sub
                                sheets_handler.save_grading_result(curr_sub)
                                st.success("🎉 AI 재채점이 완료되었습니다!")
                                st.rerun()
                            else:
                                st.error(f"재채점 실패: {regrade_res.get('error')}")

        st.markdown("---")

        st.subheader("📊 전체 학급 채점 데이터 테이블")
        summary_rows = []
        for k, v in submissions.items():
            summary_rows.append({
                "학년": v.get("학년"),
                "반": v.get("반"),
                "번호": v.get("번호"),
                "이름": v.get("이름"),
                "평가명": v.get("평가명"),
                "총점": v.get("총점"),
                "만점": v.get("만점"),
                "총평피드백": v.get("총평피드백"),
                "생기부피드백": v.get("생기부피드백"),
                "채점일시": v.get("채점일시")
            })
        
        all_df = pd.DataFrame(summary_rows)
        st.dataframe(all_df, use_container_width=True)

        csv_bytes = convert_df_to_csv(all_df)
        st.download_button(
            label="📥 채점 결과 전체 엑셀(CSV) 다운로드",
            data=csv_bytes,
            file_name=f"서술형평가_채점결과_{datetime.date.today().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            type="secondary"
        )


def render_settings_mode():
    """시스템 연동 및 설정 화면"""
    st.subheader("🔧 시스템 연동 및 보안 설정")
    st.write("Google Gemini API 무료 키 및 Google 스프레드시트 웹훅을 연동하여 100% 무료 클라우드 환경을 제어할 수 있습니다.")

    col_set1, col_set2 = st.columns(2, gap="large")

    with col_set1:
        st.markdown("#### 1️⃣ Google Gemini API 키 설정 (무료)")
        st.markdown("""
        1. [Google AI Studio](https://aistudio.google.com/)에 접속하여 구글 계정으로 로그인합니다.
        2. **'Get API Key'** 버튼을 눌러 무료 API 키를 생성합니다.
        3. 아래 입력창에 붙여넣고 저장하세요.
        """)

        input_api_key = st.text_input(
            "Gemini API Key",
            value=st.session_state.api_key,
            type="password",
            placeholder="AIzaSy..."
        )

        if st.button("🔑 Gemini API 키 저장 및 테스트"):
            if input_api_key.strip():
                st.session_state.api_key = input_api_key.strip()
                configured = evaluator.configure(input_api_key.strip())
                if configured:
                    st.success("✅ Gemini API 연결 성공! 1.5 Flash 모델을 사용할 수 있습니다.")
                else:
                    st.error("❌ API 연결에 실패했습니다. 키를 다시 확인해주세요.")
            else:
                st.warning("API 키를 입력해주세요.")

    with col_set2:
        st.markdown("#### 2️⃣ Google 스프레드시트 연동 (초간편 웹훅)")
        st.markdown("""
        - 구글 시트의 **Apps Script 배포 URL**을 입력합니다.
        - 💡 **Apps Script URL 연동 시**: 구글 클라우드 키 설정 없이 실시간 명단 동기화 및 채점 결과 자동 기록이 100% 작동합니다.
        """)

        input_sheet_id = st.text_input(
            "Google Apps Script 웹 앱 URL",
            value=st.session_state.sheet_id,
            placeholder="https://script.google.com/macros/s/.../exec"
        )

        if st.button("📊 스프레드시트 연결 테스트 및 저장", use_container_width=True):
            clean_id = clean_spreadsheet_id(input_sheet_id)
            st.session_state.sheet_id = clean_id
            st.cache_resource.clear()
            sheets_handler = get_sheets_handler(clean_id)
            success, msg = sheets_handler.connect()
            if success:
                st.success(f"✅ {msg}")
                st.balloons()
            else:
                st.error(f"❌ {msg}")

    st.markdown("---")
    st.markdown("#### 3️⃣ 🔒 교사 관리자 비밀번호 변경")
    col_pw1, col_pw2 = st.columns([2, 1])
    with col_pw1:
        new_pw = st.text_input("새 교사 비밀번호", value=str(st.session_state.teacher_password), type="password", key="new_teacher_pw_input")
    with col_pw2:
        st.write("<br>", unsafe_allow_html=True)
        if st.button("🔐 비밀번호 저장", type="primary", use_container_width=True):
            if new_pw.strip():
                st.session_state.teacher_password = new_pw.strip()
                st.success("교사 비밀번호가 성공적으로 변경되었습니다!")
            else:
                st.warning("비밀번호를 입력해주세요.")


# -----------------------------------------------------------------------------
# 6. 메인 분기: 교사 인증 여부에 따른 화면 렌더링
# -----------------------------------------------------------------------------
if st.session_state.is_teacher_authenticated:
    # 교사 모드: 전체 3개 탭 노출
    tab_student, tab_teacher, tab_settings = st.tabs([
        "👨‍🎓 1. 학생 답안 제출 모드",
        "👩‍🏫 2. 교사 채점 관리 & 대시보드",
        "🔧 3. 시스템 연동 & 설정"
    ])
    with tab_student:
        render_student_mode()
    with tab_teacher:
        render_teacher_mode()
    with tab_settings:
        render_settings_mode()
else:
    # 학생 모드 (기본): 교사 메뉴 일절 노출 없이 학생 답안 제출 화면만 단독 렌더링
    render_student_mode()