# -*- coding: utf-8 -*-
"""
Premium Animation Components for Govable AI
Apple/Toss-level UI/UX animations for document revision workflow
"""
import streamlit as st
import time
from typing import Callable, Optional

def get_animation_css() -> str:
    """프리미엄 애니메이션을 위한 CSS 스타일"""
    return """
    <style>
    /* ====================== */
    /* Premium Animation Card - Frosted Glass Effect */
    /* ====================== */
    .premium-animation-card {
        background: linear-gradient(135deg, 
            rgba(29, 78, 216, 0.05) 0%, 
            rgba(37, 99, 235, 0.08) 50%,
            rgba(251, 191, 36, 0.05) 100%);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 20px;
        border: 2px solid rgba(255, 255, 255, 0.3);
        box-shadow: 
            0 8px 32px 0 rgba(31, 38, 135, 0.15),
            inset 0 1px 0 0 rgba(255, 255, 255, 0.4);
        padding: 3rem 2.5rem;
        margin: 2rem auto;
        max-width: 600px;
        position: relative;
        overflow: hidden;
    }
    
    /* ====================== */
    /* Aura Glow - Border Animation */
    /* ====================== */
    @keyframes aura-glow {
        0%, 100% {
            box-shadow: 
                0 0 20px rgba(59, 130, 246, 0.4),
                0 0 40px rgba(59, 130, 246, 0.2),
                0 8px 32px 0 rgba(31, 38, 135, 0.15);
        }
        50% {
            box-shadow: 
                0 0 30px rgba(251, 191, 36, 0.5),
                0 0 60px rgba(251, 191, 36, 0.3),
                0 8px 32px 0 rgba(31, 38, 135, 0.15);
        }
    }
    
    .aura-glow {
        animation: aura-glow 3s ease-in-out infinite;
    }
    
    /* ====================== */
    /* Stage Container - Fade In/Out */
    /* ====================== */
    @keyframes stage-fade-in {
        0% {
            opacity: 0;
            transform: translateY(20px) scale(0.95);
        }
        100% {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }
    
    @keyframes stage-fade-out {
        0% {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
        100% {
            opacity: 0;
            transform: translateY(-20px) scale(0.95);
        }
    }
    
    .stage-container {
        text-align: center;
        animation: stage-fade-in 0.6s ease-out forwards;
    }
    
    .stage-icon {
        font-size: 4rem;
        margin-bottom: 1.5rem;
        display: inline-block;
    }
    
    .stage-title {
        font-size: 1.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 1rem;
    }
    
    .stage-description {
        font-size: 1rem;
        color: #64748b;
        line-height: 1.6;
        font-weight: 500;
    }
    
    /* ====================== */
    /* Scan Line Animation - Stage 01 */
    /* ====================== */
    @keyframes scan-line {
        0% {
            top: 0%;
            opacity: 0;
        }
        10% {
            opacity: 1;
        }
        90% {
            opacity: 1;
        }
        100% {
            top: 100%;
            opacity: 0;
        }
    }
    
    .scan-line {
        position: absolute;
        left: 0;
        width: 100%;
        height: 3px;
        background: linear-gradient(90deg, 
            transparent 0%, 
            rgba(59, 130, 246, 0.8) 50%, 
            transparent 100%);
        box-shadow: 0 0 10px rgba(59, 130, 246, 0.6);
        animation: scan-line 2s ease-in-out infinite;
    }
    
    /* ====================== */
    /* Alignment Animation - Stage 02 */
    /* ====================== */
    @keyframes align-items {
        0% {
            transform: translateX(-30px);
            opacity: 0.3;
        }
        50% {
            transform: translateX(0);
            opacity: 1;
        }
        100% {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    .align-icon {
        animation: align-items 1.5s ease-out forwards;
    }
    
    /* ====================== */
    /* Word Transform - Stage 03 */
    /* ====================== */
    @keyframes word-morph {
        0%, 100% {
            transform: scale(1);
            filter: blur(0px);
        }
        50% {
            transform: scale(1.1);
            filter: blur(2px);
        }
    }
    
    .word-transform {
        animation: word-morph 2s ease-in-out infinite;
    }
    
    /* ====================== */
    /* Completion Glow - Stage 04 */
    /* ====================== */
    @keyframes completion-glow {
        0% {
            opacity: 0;
            transform: scale(0.8);
            filter: brightness(1);
        }
        50% {
            opacity: 1;
            transform: scale(1.05);
            filter: brightness(1.3);
        }
        100% {
            opacity: 1;
            transform: scale(1);
            filter: brightness(1);
        }
    }
    
    .completion-icon {
        animation: completion-glow 1.2s ease-out forwards;
    }
    
    /* ====================== */
    /* Confetti Particles */
    /* ====================== */
    @keyframes confetti-fall {
        0% {
            transform: translateY(-100vh) rotate(0deg);
            opacity: 1;
        }
        100% {
            transform: translateY(100vh) rotate(720deg);
            opacity: 0;
        }
    }
    
    .confetti-particle {
        position: fixed;
        width: 10px;
        height: 10px;
        z-index: 9999;
        pointer-events: none;
    }
    
    /* ====================== */
    /* Progress Bar */
    /* ====================== */
    @keyframes progress-fill {
        0% {
            width: 0%;
        }
        100% {
            width: 100%;
        }
    }
    
    .progress-bar-container {
        width: 100%;
        height: 4px;
        background: rgba(148, 163, 184, 0.2);
        border-radius: 2px;
        overflow: hidden;
        margin-top: 2rem;
    }
    
    .progress-bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #3b82f6 0%, #8b5cf6 100%);
        border-radius: 2px;
        animation: progress-fill 0.8s ease-out forwards;
    }
    </style>
    """

def render_revision_animation(
    placeholder: st.delta_generator.DeltaGenerator,
    workflow_func: Callable,
    *args,
    **kwargs
) -> dict:
    """
    8단계 프리미엄 애니메이션과 함께 문서 수정 워크플로우 실행
    
    Args:
        placeholder: Streamlit placeholder for animation
        workflow_func: 실제 실행할 워크플로우 함수
        *args, **kwargs: 워크플로우 함수에 전달할 인자
    
    Returns:
        워크플로우 함수의 결과
    """
    # CSS 주입 (한 번만)
    st.markdown(get_animation_css(), unsafe_allow_html=True)
    
    stages = [
        {
            "icon": "📖",
            "title": "문서 구조 파싱",
            "description": "원문의 제목, 수신, 본문 구조를 분석합니다.",
            "duration": 0.8,
            "color": "rgba(59, 130, 246, 0.3)"
        },
        {
            "icon": "🔍",
            "title": "표준 규격 대조",
            "description": "2025 개정 공문서 작성 표준과 비교합니다.",
            "duration": 0.8,
            "color": "rgba(59, 130, 246, 0.3)"
        },
        {
            "icon": "📐",
            "title": "항목 기호 정렬",
            "description": "1. → 가. → 1) 순서로 항목 기호를 정렬합니다.",
            "duration": 0.8,
            "color": "rgba(59, 130, 246, 0.3)"
        },
        {
            "icon": "📅",
            "title": "날짜/시간 표기 교정",
            "description": "2025. 1. 27. 형식으로 날짜를 통일합니다.",
            "duration": 0.8,
            "color": "rgba(59, 130, 246, 0.3)"
        },
        {
            "icon": "✨",
            "title": "언어 순화 진행",
            "description": "위압적 표현을 부드럽게 다듬습니다.",
            "duration": 0.8,
            "color": "rgba(139, 92, 246, 0.3)"
        },
        {
            "icon": "🔤",
            "title": "오탈자 검사",
            "description": "맞춤법과 띄어쓰기를 점검합니다.",
            "duration": 0.8,
            "color": "rgba(139, 92, 246, 0.3)"
        },
        {
            "icon": "🎨",
            "title": "최종 조판 중",
            "description": "문서 형식을 완성하고 있습니다...",
            "duration": 0.0,  # 실제 작업 중
            "color": "rgba(251, 191, 36, 0.5)"
        },
    ]
    
    # 처음 6단계는 애니메이션만 표시
    for i, stage in enumerate(stages[:6]):
        with placeholder.container():
            st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, rgba(29, 78, 216, 0.05) 0%, rgba(37, 99, 235, 0.08) 50%, rgba(251, 191, 36, 0.05) 100%);
                    border-radius: 20px;
                    border: 2px solid {stage["color"]};
                    padding: 3rem 2.5rem;
                    margin: 2rem auto;
                    max-width: 600px;
                    text-align: center;
                    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.15);
                ">
                    <div style="font-size: 4rem; margin-bottom: 1.5rem;">{stage["icon"]}</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: #1d4ed8; margin-bottom: 1rem;">
                        {stage["title"]}
                    </div>
                    <div style="font-size: 1rem; color: #64748b; line-height: 1.6;">
                        {stage["description"]}
                    </div>
                    <div style="width: 100%; height: 4px; background: rgba(148, 163, 184, 0.2); border-radius: 2px; margin-top: 2rem; overflow: hidden;">
                        <div style="height: 100%; background: linear-gradient(90deg, #3b82f6 0%, #8b5cf6 100%); width: {((i+1)/len(stages))*100}%; transition: width 0.5s ease;"></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        
        time.sleep(stage["duration"])
    
    # 7단계: 실제 워크플로우 실행 중 애니메이션 표시
    stage = stages[6]
    
    # 실행 중 애니메이션을 별도 스레드로 표시
    import threading
    result_container = {"result": None, "done": False}
    
    def run_workflow():
        result_container["result"] = workflow_func(*args, **kwargs)
        result_container["done"] = True
    
    # 워크플로우를 백그라운드에서 실행
    thread = threading.Thread(target=run_workflow)
    thread.start()
    
    # 실행 중 애니메이션 (점이 증가하는 효과)
    dots = 0
    while not result_container["done"]:
        dots = (dots + 1) % 4
        dot_text = "." * dots
        
        with placeholder.container():
            st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, rgba(29, 78, 216, 0.05) 0%, rgba(37, 99, 235, 0.08) 50%, rgba(251, 191, 36, 0.05) 100%);
                    border-radius: 20px;
                    border: 2px solid {stage["color"]};
                    padding: 3rem 2.5rem;
                    margin: 2rem auto;
                    max-width: 600px;
                    text-align: center;
                    box-shadow: 0 0 30px rgba(251, 191, 36, 0.3);
                ">
                    <div style="font-size: 4rem; margin-bottom: 1.5rem;">{stage["icon"]}</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: #1d4ed8; margin-bottom: 1rem;">
                        {stage["title"]}{dot_text}
                    </div>
                    <div style="font-size: 1rem; color: #64748b; line-height: 1.6;">
                        {stage["description"]}
                    </div>
                    <div style="width: 100%; height: 4px; background: rgba(148, 163, 184, 0.2); border-radius: 2px; margin-top: 2rem; overflow: hidden;">
                        <div style="height: 100%; background: linear-gradient(90deg, #3b82f6 0%, #8b5cf6 100%); width: 85%; transition: width 0.5s ease;"></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        
        time.sleep(0.5)
    
    # 워크플로우 완료 대기
    thread.join()
    result = result_container["result"]
    
    # 8단계: 완료 표시
    with placeholder.container():
        st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, rgba(34, 197, 94, 0.05) 0%, rgba(16, 185, 129, 0.08) 100%);
                border-radius: 20px;
                border: 2px solid rgba(34, 197, 94, 0.5);
                padding: 3rem 2.5rem;
                margin: 2rem auto;
                max-width: 600px;
                text-align: center;
                box-shadow: 0 0 30px rgba(34, 197, 94, 0.3);
            ">
                <div style="font-size: 4rem; margin-bottom: 1.5rem;">✅</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #059669; margin-bottom: 1rem;">
                    수정 완료!
                </div>
                <div style="font-size: 1rem; color: #64748b; line-height: 1.6;">
                    격조 높은 공문서가 완성되었습니다.
                </div>
                <div style="width: 100%; height: 4px; background: rgba(148, 163, 184, 0.2); border-radius: 2px; margin-top: 2rem; overflow: hidden;">
                    <div style="height: 100%; background: linear-gradient(90deg, #10b981 0%, #34d399 100%); width: 100%;"></div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    time.sleep(0.8)
    
    return result

def render_completion_confetti(placeholder: st.delta_generator.DeltaGenerator):
    """완료 시 Confetti 효과 표시"""
    colors = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981"]
    
    confetti_html = """
    <div id="confetti-container" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 9999;">
    """
    
    # 50개의 confetti 파티클 생성
    for i in range(50):
        import random
        color = random.choice(colors)
        left = random.randint(0, 100)
        delay = random.uniform(0, 0.5)
        duration = random.uniform(2, 4)
        
        confetti_html += f"""
        <div class="confetti-particle" style="
            left: {left}%;
            background: {color};
            animation: confetti-fall {duration}s linear {delay}s forwards;
        "></div>
        """
    
    confetti_html += "</div>"
    
    with placeholder.container():
        st.markdown(confetti_html, unsafe_allow_html=True)
    
    time.sleep(0.8)  # Confetti 효과 지속 시간

def render_simple_stage_animation(
    stage_num: int,
    total_stages: int,
    title: str,
    description: str,
    icon: str = "⚙️"
):
    """
    간단한 단계별 애니메이션 (다른 워크플로우에서도 재사용 가능)
    
    Args:
        stage_num: 현재 단계 번호 (1부터 시작)
        total_stages: 전체 단계 수
        title: 단계 제목
        description: 단계 설명
        icon: 아이콘 (이모지)
    """
    progress = (stage_num / total_stages) * 100
    
    st.markdown(get_animation_css(), unsafe_allow_html=True)
    
    st.markdown(f"""
        <div class="premium-animation-card">
            <div class="stage-container">
                <div class="stage-icon">{icon}</div>
                <div class="stage-title">{title}</div>
                <div class="stage-description">{description}</div>
                <div class="progress-bar-container">
                    <div class="progress-bar-fill"></div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)
