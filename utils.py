"""
유틸리티 모듈 (utils.py)
- PDF 및 TXT 루브릭 텍스트 추출
- 이미지 리사이징 및 바이트 변환
- 평가 결과 데이터 가공 및 내보내기 도구
"""

import io
from typing import List, Optional, Tuple
from PIL import Image
import pandas as pd
from pypdf import PdfReader


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """PDF 또는 TXT 파일 바이트로부터 텍스트를 추출합니다."""
    filename_lower = filename.lower()
    
    if filename_lower.endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            text_pages = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_pages.append(f"[페이지 {i+1}]\n{page_text}")
            return "\n\n".join(text_pages) if text_pages else "PDF에서 텍스트를 추출할 수 없습니다."
        except Exception as e:
            return f"PDF 읽기 오류: {str(e)}"
    
    elif filename_lower.endswith(".txt") or filename_lower.endswith(".md"):
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return file_bytes.decode("cp949")
            except Exception as e:
                return f"텍스트 파일 인코딩 오류: {str(e)}"
    else:
        return "지원하지 않는 파일 형식입니다. (PDF, TXT, MD 파일 권장)"


def process_images_for_ai(image_files) -> List[Image.Image]:
    """업로드된 이미지 파일들을 PIL Image 객체 목록으로 변환 및 최적화합니다."""
    processed_images = []
    max_dimension = 1800  # API 토큰 및 전송 속도 최적화를 위한 최대 해상도

    for img_file in image_files:
        try:
            if hasattr(img_file, "read"):
                img_bytes = img_file.read()
                img_file.seek(0)
                image = Image.open(io.BytesIO(img_bytes))
            elif isinstance(img_file, bytes):
                image = Image.open(io.BytesIO(img_file))
            elif isinstance(img_file, Image.Image):
                image = img_file
            else:
                continue

            # RGB 변환 (RGBA 또는 Palette 모드 호환)
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")

            # 리사이징 (종횡비 유지)
            w, h = image.size
            if max(w, h) > max_dimension:
                if w > h:
                    new_w = max_dimension
                    new_h = int(h * (max_dimension / w))
                else:
                    new_h = max_dimension
                    new_w = int(w * (max_dimension / h))
                image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

            processed_images.append(image)
        except Exception as e:
            print(f"이미지 처리 중 오류 발생: {e}")
            continue

    return processed_images


def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """데이터프레임을 한글 엑셀 호환 UTF-8-BOM CSV 바이트로 변환합니다."""
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def format_student_id(grade: str, class_num: str, student_num: str) -> str:
    """학년, 반, 번호를 표준 학번 문자열로 포맷팅합니다 (예: 40215 -> 4학년 2반 15번)."""
    g = str(grade).strip()
    c = str(class_num).strip().zfill(2)
    n = str(student_num).strip().zfill(2)
    return f"{g}{c}{n}"
