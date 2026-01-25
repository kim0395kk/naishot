# -*- coding: utf-8 -*-
import streamlit as st
import json
import re
import time
from typing import Optional, Tuple, Dict, Any

def render_revision_sidebar_button():
    """
    사이드바에 '기안/공고문 수정' 버튼을 렌더링하고,
    클릭 시 세션 상태를 'revision' 모드로 변경합니다.
    """
    if st.sidebar.button("\U0001F4DD 기안, 공고문 수정", use_container_width=True):
        st.session_state["app_mode"] = "revision"
        st.session_state["workflow_result"] = None  # 기존 결과 초기화
        st.session_state["current_archive_id"] = None
        st.rerun()

def run_revision_workflow(user_input: str, llm_service, sb=None, user_email=None) -> Dict[str, Any]:
    """
    사용자 입력(원문+지시사항)을 받아 수정된 공문과 변경 로그를 반환합니다.
    지시사항이 없으면 기본 '공문서 작성 표준 준수' 지침을 적용합니다.
    """
    if not user_input:
        return {}

    # 입력 파싱 (원문 vs 지시사항)
    original_text = ""
    request_text = ""
    
    if "[원문]" in user_input and "[수정 요청]" in user_input:
        parts = user_input.split("[수정 요청]")
        original_text = parts[0].replace("[원문]", "").strip()
        request_text = parts[1].strip()
    else:
        original_text = user_input
        request_text = ""

    # 기본 지시사항 적용
    if not request_text:
        request_text = "공문서 작성 표준 지침(2025 개정)에 맞게 오탈자, 띄어쓰기, 표현을 교정하고 형식을 갖춰주세요."

    # 1. LLM에게 원문과 지시사항 분리 및 수정 요청
    prompt = f"""
당신은 대한민국 행정기관의 공문서 작성 및 교정 전문가인 'AI 행정관 Pro'이다.
사용자가 입력한 텍스트(원문)를 분석하여 요청사항에 따라 문서를 수정하라.

[원문]
{original_text}

[수정 요청사항]
{request_text}

[작성 원칙 (2025 개정 표준)]
1. **핵심 원칙**:
   - 사실성: 육하원칙 준수, 오자/탈자/계수 착오 금지.
   - 용이성: 쉬운 용어 사용, 짧고 명확한 문장.
   - 명확성: 불분명한 단어 회피, 정확한 조사 사용.
   - 비고압성: '금지', '엄금' 대신 '안내', '부탁' 등 긍정적 표현 사용.
   - 수요자 중심: 주어를 '국민(수요자)' 관점으로.

2. **형식 및 표기 규칙 (엄격 준수)**:
   - **항목 기호 순서**: 1. -> 가. -> 1) -> 가) -> (1) -> (가) -> ① -> ㉮
   - **띄어쓰기**: 하위 항목은 상위 항목보다 2타(한글 1자) 오른쪽 시작.
   - **날짜/시간**: 2025. 1. 8. (마침표+공백), 09:00 (쌍점 붙임).
   - **금액**: 금13,500원(금일만삼천오백원) (붙여쓰기).
   - **끝 표시**: 본문/붙임 끝에 2타 띄우고 '끝.'

[출력 형식 - 반드시 JSON 하나로만]
{{{{
  "revised_doc": {{{{
    "title": "수정된 제목",
    "receiver": "수정된 수신자",
    "body_paragraphs": ["수정된 본문 문단1", "수정된 본문 문단2", ...],
    "department_head": "발신 명의"
  }}}},
  "changelog": [
    "제목 변경: 'OOO' -> 'XXX'",
    "일시 수정: '10일' -> '2025. 1. 10.' (표기법 준수)",
    "오타 수정: '함니다' -> '합니다'",
    "표현 개선: '역전앞' -> '역전' (동어반복 삭제)"
  ],
  "summary": "수정 요약 멘트"
}}}}
"""
    try:
        start_time = time.time()
        model_name = "gemini-2.5-flash"
        result = llm_service.generate_json(prompt, preferred_model=model_name)
        end_time = time.time()
        
        if not result:
            return {"error": "AI 응답을 분석할 수 없습니다."}
            
        # DB 저장
        if sb:
            try:
                data = {
                    "original_text": original_text,
                    "revision_request": request_text,
                    "revised_json": result.get("revised_doc"),
                    "changelog": result.get("changelog"),
                    "summary": result.get("summary"),
                    "model_used": model_name,
                    "execution_time": end_time - start_time,
                    "user_email": user_email
                }
                sb.table("document_revisions").insert(data).execute()
            except Exception as e:
                print(f"DB Insert Error: {e}")
                
        return result
    except Exception as e:
        return {"error": f"처리 중 오류 발생: {str(e)}"}
