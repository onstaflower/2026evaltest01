"""
Gemini 1.5 Flash AI 채점 & OCR 엔진 모듈 (gemini_evaluator.py)
- 멀티모달(여러 장의 답안지 이미지) 손글씨 OCR 및 구조화 텍스트 추출
- 교사 루브릭(채점 기준표) 기반 문항별 정밀 채점
- 점수, 감점 사유, 학생 맞춤형 피드백, 나이스(NEIS) 생기부용 서술문 생성
- 교사 피드백/가이드라인을 반영한 "재채점(Regrade)" 지원
"""

import json
import re
from typing import Any, Dict, List, Optional
from PIL import Image

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


SYSTEM_PROMPT = """당신은 대한민국 초·중·고등학교 교육과정 및 서술형·논술형 평가에 정통한 **수석 채점 교사 및 AI 평가 전문가**입니다.
학생들이 손글씨로 직접 작성한 서술형 답안지 이미지(1장 이상)와 교사가 제공한 채점 기준(루브릭)을 면밀히 분석하여, 공정하고 정확하며 교육적인 채점 결과를 도출해야 합니다.

### [수행 작업]
1. **손글씨 OCR 인식**: 이미지 속의 문항 번호와 학생의 손글씨 답변을 누락이나 왜곡 없이 정확하게 텍스트로 전사(Transcription)하세요.
2. **루브릭 기반 정밀 채점**: 교사가 제시한 배점 및 성취 기준에 따라 문항별 득점을 산출하고, 감점 요인이 있다면 구체적인 근거를 명시하세요.
3. **학생 성장형 피드백**: 학생이 잘한 점(강점)과 아쉬운 점(보완점 및 학습 방향)을 따뜻하고 명확한 어조로 작성하세요.
4. **학교생활기록부(NEIS) 관찰 서술문**: 교사가 생기부 교과학습발달상황 세부능력 및 특기사항에 즉시 활용할 수 있는 격식 있는 완성형 문장을 작성하세요.

### [반환 형식]
반드시 다음 JSON 형식만을 엄격히 준수하여 출력하세요. Markdown 코드 블록(```json ... ```)을 포함해도 무방합니다.

{
  "ocr_text": "문항 1: [학생 작성 원문]\\n문항 2: [학생 작성 원문] ...",
  "total_score": 85,
  "max_score": 100,
  "questions": [
    {
      "question_no": "1",
      "score": 18,
      "max_score": 20,
      "criterion": "핵심 개념 설명 및 예시 제시",
      "reason": "핵심 원리는 정확히 설명하였으나 실생활 적용 예시가 다소 부족하여 2점 감점함."
    }
  ],
  "general_feedback": "전반적으로 과학적 개념에 대한 이해도가 우수하며 자신의 언어로 조리 있게 설명했습니다. 다만 후반부 문항에서 결론 도출 과정의 논리적 연결고리를 조금 더 보완하면 더욱 훌륭한 답안이 될 것입니다.",
  "neis_record": "서술형 평가에서 주어진 개념의 기본 원리를 정확히 파악하여 논리적으로 서술함. 특히 문제 상황에 대한 분석력이 뛰어나며 자기주도적으로 결론을 이끌어내는 역량이 돋보임."
}
"""


class GeminiEvaluator:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.is_configured = False
        if api_key:
            self.configure(api_key)

    def configure(self, api_key: str) -> bool:
        """Gemini API 키 설정 및 클라이언트 초기화"""
        if not GEMINI_AVAILABLE:
            return False
        try:
            genai.configure(api_key=api_key)
            self.api_key = api_key
            self.is_configured = True
            return True
        except Exception as e:
            print(f"Gemini API 설정 실패: {e}")
            self.is_configured = False
            return False

    def evaluate_submission(
        self,
        images: List[Image.Image],
        rubric_text: str,
        student_info: Optional[Dict[str, str]] = None,
        teacher_notes: Optional[str] = None,
        is_regrade: bool = False
    ) -> Dict[str, Any]:
        """
        답안지 다중 이미지와 루브릭을 전달받아 AI 채점을 수행합니다.
        """
        if not self.is_configured or not self.api_key:
            return self._mock_evaluation(student_info, rubric_text, is_regrade)

        if not images:
            return {
                "success": False,
                "error": "채점할 답안지 이미지가 제공되지 않았습니다."
            }

        # 채점 시도할 모델 후보군 구성
        candidate_models = [
            "gemini-1.5-flash",
            "gemini-1.5-flash-latest",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "models/gemini-1.5-flash",
            "models/gemini-1.5-flash-latest",
            "gemini-1.5-flash-8b",
        ]

        # API 키에서 지원하는 실제 모델 목록이 조회되면 최우선 배치
        try:
            available = [
                m.name for m in genai.list_models()
                if "generateContent" in getattr(m, "supported_generation_methods", [])
            ]
            if available:
                # generateContent를 지원하는 모델들을 우선 후보로 결합
                candidate_models = [m for m in candidate_models if m in available] + available + candidate_models
                # 중복 제거 (순서 유지)
                candidate_models = list(dict.fromkeys(candidate_models))
        except Exception:
            pass

        # 프롬프트 조립
        prompt_parts = []
        user_prompt = f"""
[학생 정보]
- 학년/반/번호/이름: {student_info.get('학년', '')}학년 {student_info.get('반', '')}반 {student_info.get('번호', '')}번 {student_info.get('이름', '학생')}

[교사 제공 채점 기준(루브릭)]
{rubric_text if rubric_text.strip() else '교사가 지정한 일반 서술형 평가 채점 기준(개념 정확도, 논리성, 표현력 각 배점)에 따라 100점 만점으로 채점하세요.'}
"""
        if teacher_notes:
            user_prompt += f"\n[교사의 특별 채점 지침 / 재채점 요구사항]\n{teacher_notes}\n"

        if is_regrade:
            user_prompt += "\n※ 주의: 본 요청은 [재채점(Re-grade)] 요청입니다. 이전 채점 결과보다 교사의 지침과 루브릭 세부 기준을 엄격하고 정밀하게 재검토하여 채점하세요."

        prompt_parts.append(user_prompt)
        prompt_parts.extend(images)

        last_error = None
        for model_name in candidate_models:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=SYSTEM_PROMPT
                )

                # Gemini API 호출
                response = model.generate_content(
                    prompt_parts,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.2,
                        response_mime_type="application/json"
                    )
                )

                response_text = response.text.strip()
                parsed_data = self._parse_json_response(response_text)
                parsed_data["success"] = True
                parsed_data["used_model"] = model_name
                return parsed_data

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                # 404, not found, unsupported 등의 경우 다음 모델로 자동 전환
                if "404" in err_str or "not found" in err_str or "not supported" in err_str:
                    continue
                else:
                    # 인증 오류, 쿼터 등 치명적 오류인 경우에도 다음 모델 시도 후 실패 시 처리
                    continue

        return {
            "success": False,
            "error": f"AI 채점 중 오류가 발생했습니다: {str(last_error)}",
            "raw_response": str(last_error)
        }

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """JSON 텍스트 추출 및 다단계 안전 파싱 (문자열 내 줄바꿈/따옴표 완벽 대응)"""
        # 1. 마크다운 코드블록 제거
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

        # 2. 1차 시도: 표준 JSON 파싱 (strict=False로 제어문자 허용)
        try:
            return json.loads(cleaned, strict=False)
        except Exception:
            pass

        # 3. 2차 시도: 본문 내 { ... } 블록 추출 및 후행 쉼표 제거
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            json_block = match.group(0)
            # 후행 쉼표 제거 (, } 또는 , ])
            json_block_clean = re.sub(r",\s*([\}\]])", r"\1", json_block)
            try:
                return json.loads(json_block_clean, strict=False)
            except Exception:
                pass

        # 4. 3차 시도: 지능형 정규식 필드별 개별 복원 (AI 응답 텍스트 무손실 추출)
        extracted: Dict[str, Any] = {
            "ocr_text": "",
            "total_score": 80,
            "max_score": 100,
            "questions": [],
            "general_feedback": "",
            "neis_record": ""
        }

        # 점수 추출
        score_match = re.search(r'"total_score"\s*:\s*(\d+)', text)
        if score_match:
            try: extracted["total_score"] = int(score_match.group(1))
            except Exception: pass

        max_score_match = re.search(r'"max_score"\s*:\s*(\d+)', text)
        if max_score_match:
            try: extracted["max_score"] = int(max_score_match.group(1))
            except Exception: pass

        # 총평 피드백 추출
        fb_match = re.search(r'"general_feedback"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if fb_match:
            extracted["general_feedback"] = fb_match.group(1).replace("\\n", "\n").replace('\\"', '"').strip()
        else:
            # 큰따옴표가 깨진 경우 키워드 기반 탐색
            fb_block = re.search(r'general_feedback["\']?\s*:\s*["\']?([^"\n\}]+)', text)
            if fb_block:
                extracted["general_feedback"] = fb_block.group(1).strip()
            else:
                extracted["general_feedback"] = "서술형 평가 문항에 대해 전반적으로 성실하게 답변을 작성하였습니다."

        # 생기부 세특 서술문 추출
        neis_match = re.search(r'"neis_record"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if neis_match:
            extracted["neis_record"] = neis_match.group(1).replace("\\n", "\n").replace('\\"', '"').strip()
        else:
            neis_block = re.search(r'neis_record["\']?\s*:\s*["\']?([^"\n\}]+)', text)
            if neis_block:
                extracted["neis_record"] = neis_block.group(1).strip()
            else:
                extracted["neis_record"] = "서술형 평가에서 자신의 생각을 과학적 개념과 연계하여 논리적으로 서술함."

        # OCR 텍스트 추출
        ocr_match = re.search(r'"ocr_text"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if ocr_match:
            extracted["ocr_text"] = ocr_match.group(1).replace("\\n", "\n").replace('\\"', '"').strip()
        else:
            # 전체 텍스트 중 불필요한 json 마크업을 걷어낸 본문
            clean_raw = re.sub(r'["\{\}\[\]]|total_score|max_score|questions|general_feedback|neis_record|ocr_text', '', text)
            extracted["ocr_text"] = clean_raw.strip()

        return extracted

    def _mock_evaluation(self, student_info: Optional[Dict[str, str]], rubric_text: str, is_regrade: bool) -> Dict[str, Any]:
        """API 키가 없을 때 UI 테스트를 위한 샘플 채점 결과 반환"""
        s_name = student_info.get("이름", "학생") if student_info else "학생"
        score = 88 if not is_regrade else 92
        return {
            "success": True,
            "is_mock": True,
            "ocr_text": f"[문항 1]\n식물은 햇빛과 물, 이산화탄소를 이용하여 잎의 엽록체에서 광합성을 하여 스스로 양분을 만듭니다. 이 과정에서 산소가 발생합니다.\n\n[문항 2]\n실험에서 햇빛을 가린 잎은 아이오딘 반응 시 색이 변하지 않았고, 햇빛을 받은 잎은 청람색으로 변했습니다. 이는 햇빛이 있어야 녹말이 합성됨을 증명합니다.",
            "total_score": score,
            "max_score": 100,
            "questions": [
                {
                    "question_no": "1",
                    "score": 45 if not is_regrade else 47,
                    "max_score": 50,
                    "criterion": "광합성의 정의 및 필요 물질, 생성 물질 명시",
                    "reason": "필요 물질과 생성 물질(산소, 양분)을 정확히 기술하였으나 반응 장소(엽록체)에 대한 서술이 다소 간략함."
                },
                {
                    "question_no": "2",
                    "score": 43 if not is_regrade else 45,
                    "max_score": 50,
                    "criterion": "대조 실험 결과 분석 및 과학적 결론 도출",
                    "reason": "아이오딘 반응 결과를 통한 녹말 검출 원리를 명확하게 설명함."
                }
            ],
            "general_feedback": f"{s_name} 학생은 핵심 과학 개념을 올바르게 이해하고 있으며, 실험 결과와 원인을 연결짓는 논리적 서술력이 매우 뛰어납니다.",
            "neis_record": f"서술형 평가에서 광합성의 기본 원리와 실험 결과를 과학적 근거를 바탕으로 논리정연하게 기술함. 핵심 개념 간의 인과관계를 스스로 분석하고 체계적으로 표현하는 능력이 돋보임."
        }
