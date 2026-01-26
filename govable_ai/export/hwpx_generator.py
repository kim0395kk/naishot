# -*- coding: utf-8 -*-
"""
HWPX Document Generator
한글(HWP) HWPX 형식 문서 생성 모듈
"""
import os
import shutil
import zipfile
from io import BytesIO
from datetime import datetime
import re
from pathlib import Path

class HWPXGenerator:
    """HWPX 문서 생성기"""
    
    def __init__(self, template_dir="hwpx_template"):
        """
        Args:
            template_dir: HWPX 템플릿 디렉토리 경로
        """
        self.template_dir = Path(template_dir)
        
    def generate_official_document(self, doc_data: dict) -> BytesIO:
        """
        공문서 HWPX 생성
        
        Args:
            doc_data: 문서 데이터
                - title: 문서 제목
                - receiver: 수신자
                - body_paragraphs: 본문 단락 리스트
                - doc_num: 문서번호 (선택)
                - doc_date: 시행일자 (선택)
                - department_head: 발신명의 (선택)
        
        Returns:
            BytesIO: HWPX 파일 바이트 스트림
        """
        # 데이터 검증
        if not isinstance(doc_data, dict):
            raise ValueError(f"doc_data must be dict, got {type(doc_data)}")
        
        # 플레이스홀더 매핑
        placeholders = {
            "{{DOC_TITLE}}": str(doc_data.get("title", "공문서")),
            "{{DOC_RECEIVER}}": str(doc_data.get("receiver", "수신자")),
            "{{DOC_BODY}}": self._format_body(doc_data.get("body_paragraphs", [])),
            "{{DOC_NUM}}": str(doc_data.get("doc_num", self._generate_doc_num())),
            "{{DOC_DATE}}": self._format_date_standard(doc_data.get("doc_date")),
            "{{DEPARTMENT_HEAD}}": str(doc_data.get("department_head", "행정기관장")),
            "{{ATTACHMENTS}}": str(doc_data.get("attachments", "")),
        }
        
        return self._generate_hwpx(placeholders)
    
    def generate_processing_guide(self, workflow_data: dict) -> BytesIO:
        """
        처리가이드 보고서 HWPX 생성
        
        Args:
            workflow_data: 워크플로우 데이터
                - analysis: 분석 결과
                - law: 법적 검토
                - strategy: 처리 전략
                - procedure: 절차
        
        Returns:
            BytesIO: HWPX 파일 바이트 스트림
        """
        # 데이터 검증
        if not isinstance(workflow_data, dict):
            raise ValueError(f"workflow_data must be dict, got {type(workflow_data)}")
        
        # 데이터 추출 (안전하게)
        analysis = workflow_data.get("analysis") or {}
        if isinstance(analysis, str):
            analysis = {"summary": [analysis]}
        
        law = workflow_data.get("law") or {}
        if isinstance(law, str):
            law = {"review": law}
        
        strategy = workflow_data.get("strategy") or {}
        if isinstance(strategy, str):
            strategy = {"summary": strategy}
        
        procedure = workflow_data.get("procedure") or {}
        if isinstance(procedure, str):
            procedure = {"steps": [procedure]}
        
        # 플레이스홀더 매핑
        placeholders = {
            "{{REPORT_TITLE}}": "행정 처리 가이드",
            "{{REPORT_DATE}}": self._format_date_standard(None),
            "{{AUTHOR_NAME}}": "AI 행정관 Pro",
            "{{ANALYSIS_CASE_TYPE}}": str(analysis.get("case_type", "일반 민원")),
            "{{ANALYSIS_SUMMARY}}": self._format_analysis_section(analysis),
            "{{RISK_FLAGS}}": self._format_bullet_list(analysis.get("risks", [])),
            "{{LEGAL_REVIEW}}": self._format_legal_review(law),
            "{{STRATEGY_SUMMARY}}": str(strategy.get("summary", "")),
            "{{STRATEGY_STEPS}}": self._format_strategy_section(strategy),
            "{{CHECKLIST}}": self._format_checklist(procedure.get("checklist", [])),
            "{{TEMPLATES}}": self._format_bullet_list(procedure.get("templates", [])),
            "{{NEXT_ACTION}}": str(procedure.get("next_action", "")),
        }
        
        return self._generate_hwpx(placeholders)
    
    def _generate_hwpx(self, placeholders: dict) -> BytesIO:
        """
        HWPX 파일 생성 (템플릿 기반)
        
        Args:
            placeholders: 플레이스홀더 치환 딕셔너리
        
        Returns:
            BytesIO: HWPX 파일 바이트 스트림
        """
        # 임시 디렉토리 생성
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # 템플릿 복사
            shutil.copytree(self.template_dir, temp_dir / "hwpx", dirs_exist_ok=True)
            
            # XML 파일들에서 플레이스홀더 치환
            xml_files = [
                temp_dir / "hwpx" / "Contents" / "section0.xml",
                temp_dir / "hwpx" / "Contents" / "header.xml",
            ]
            
            for xml_file in xml_files:
                if xml_file.exists():
                    with open(xml_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 플레이스홀더 치환
                    for placeholder, value in placeholders.items():
                        content = content.replace(placeholder, self._escape_xml(value))
                    
                    with open(xml_file, 'w', encoding='utf-8') as f:
                        f.write(content)
            
            # HWPX 파일로 압축 (ZIP 형식)
            output = BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(temp_dir / "hwpx"):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(temp_dir / "hwpx")
                        zipf.write(file_path, arcname)
            
            output.seek(0)
            return output
            
        finally:
            # 임시 디렉토리 정리
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def _format_body(self, paragraphs) -> str:
        """
        본문 단락을 HWPX 형식으로 포맷팅
        
        Args:
            paragraphs: 단락 리스트 또는 문자열
        
        Returns:
            포맷팅된 본문
        """
        # 문자열인 경우 리스트로 변환
        if isinstance(paragraphs, str):
            # 이미 포맷팅된 문자열인 경우 그대로 사용
            if "\n" in paragraphs:
                paragraphs = paragraphs.split("\n")
            else:
                paragraphs = [paragraphs]
        elif not paragraphs:
            paragraphs = []
        
        # 2025 개정 표준 적용
        formatted = []
        for para in paragraphs:
            if not para or not para.strip():
                continue
            # 항목 체계 자동 감지 및 들여쓰기
            para = self._apply_hierarchy(para.strip())
            formatted.append(para)
        
        # 본문 끝에 "끝." 추가
        body = "\n\n".join(formatted)
        if body and not body.endswith("끝."):
            body = body.rstrip() + " 끝."
        
        return body if body else ""
    
    def _apply_hierarchy(self, text: str) -> str:
        """
        항목 체계 적용 (1. → 가. → 1) → 가))
        
        Args:
            text: 원본 텍스트
        
        Returns:
            들여쓰기가 적용된 텍스트
        """
        # 항목 패턴 감지
        patterns = [
            (r'^(\d+)\.\s', 0),      # 1. (대항목, 0타)
            (r'^([가-힣])\.\s', 2),  # 가. (중항목, 2타)
            (r'^(\d+)\)\s', 4),      # 1) (소항목, 4타)
            (r'^([가-힣])\)\s', 6),  # 가) (세부항목, 6타)
        ]
        
        for pattern, indent in patterns:
            if re.match(pattern, text):
                # 들여쓰기 적용 (1타 = 공백 1개)
                return ' ' * indent + text
        
        return text
    
    def _format_date(self, dt: datetime) -> str:
        """
        날짜를 2025 개정 표준 형식으로 포맷팅
        
        Args:
            dt: datetime 객체
        
        Returns:
            "2025. 1. 27." 형식 문자열
        """
        return f"{dt.year}. {dt.month}. {dt.day}."
    
    def _generate_doc_num(self) -> str:
        """문서번호 자동 생성"""
        today = datetime.now()
        return f"행정-{today.year}-{today.strftime('%m%d')}-001호"
    
    def _format_bullet_list(self, items: list) -> str:
        """불렛 리스트 포맷팅"""
        if not items:
            return ""
        return "\n".join([f"• {item}" for item in items])
    
    def _format_numbered_list(self, items: list) -> str:
        """번호 리스트 포맷팅"""
        if not items:
            return ""
        return "\n".join([f"{i+1}. {item}" for i, item in enumerate(items)])
    
    def _format_checklist(self, items: list) -> str:
        """체크리스트 포맷팅"""
        if not items:
            return ""
        return "\n".join([f"☐ {item}" for item in items])
    
    def _format_legal_review(self, law_data: dict) -> str:
        """법적 검토 결과 포맷팅"""
        if not law_data:
            return ""
        
        result = []
        if law_data.get("statutes"):
            result.append("관련 법령:")
            for statute in law_data["statutes"]:
                result.append(f"  - {statute}")
        
        if law_data.get("precedents"):
            result.append("\n판례:")
            for precedent in law_data["precedents"]:
                result.append(f"  - {precedent}")
        
        return "\n".join(result)
    
    
    def _format_date_standard(self, date_input) -> str:
        """
        2025 개정 표준 날짜 형식 (예: 2025. 1. 27.)
        
        Args:
            date_input: datetime 객체, 문자열, 또는 None
        
        Returns:
            "2025. 1. 27." 형식 문자열
        """
        if date_input is None:
            dt = datetime.now()
        elif isinstance(date_input, str):
            # 이미 포맷팅된 경우 그대로 반환
            if ". " in date_input:
                return date_input
            # ISO 형식 파싱 시도
            try:
                dt = datetime.fromisoformat(date_input.replace("Z", "+00:00"))
            except:
                dt = datetime.now()
        elif isinstance(date_input, datetime):
            dt = date_input
        else:
            dt = datetime.now()
        
        # 2025 개정 표준: "2025. 1. 27." (숫자 뒤 마침표, 한 칸 띄움)
        return f"{dt.year}. {dt.month}. {dt.day}."
    
    def _format_analysis_section(self, analysis: dict) -> str:
        """분석 섹션 포맷팅"""
        result = []
        
        # 핵심 쟁점
        if analysis.get("summary"):
            summary = analysis["summary"]
            if isinstance(summary, list):
                result.append("핵심 쟁점:")
                for item in summary:
                    result.append(f"  • {item}")
            else:
                result.append(str(summary))
        
        # 리스크
        if analysis.get("risks"):
            result.append("\n리스크 요소:")
            for risk in analysis["risks"]:
                result.append(f"  ⚠ {risk}")
        
        return "\n".join(result) if result else "분석 내용 없음"
    
    def _format_strategy_section(self, strategy: dict) -> str:
        """처리 전략 섹션 포맷팅"""
        result = []
        
        # 요약
        if strategy.get("summary"):
            result.append(f"처리 방안: {strategy['summary']}")
            result.append("")
        
        # 단계별 조치
        if strategy.get("steps"):
            result.append("단계별 조치 계획:")
            steps = strategy["steps"]
            if isinstance(steps, list):
                for i, step in enumerate(steps, 1):
                    result.append(f"  {i}. {step}")
            else:
                result.append(f"  {steps}")
        
        return "\n".join(result) if result else "전략 없음"
    
    def _escape_xml(self, text: str) -> str:
        """XML 특수문자 이스케이프"""
        if not isinstance(text, str):
            text = str(text)
        
        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&apos;',
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text


# 편의 함수
def generate_official_hwpx(doc_data: dict) -> BytesIO:
    """공문서 HWPX 생성 (편의 함수)"""
    generator = HWPXGenerator()
    return generator.generate_official_document(doc_data)


def generate_guide_hwpx(workflow_data: dict) -> BytesIO:
    """처리가이드 HWPX 생성 (편의 함수)"""
    generator = HWPXGenerator()
    return generator.generate_processing_guide(workflow_data)
