import streamlit as st
import google.generativeai as genai
from groq import Groq
from supabase import create_client
from smolagents import CodeAgent, Tool
import requests
import xml.etree.ElementTree as ET
from PIL import Image
import io
import time

# ==========================================
# 1. 화면 설정 및 스타일 (API 시각화 포함)
# ==========================================
st.set_page_config(layout="wide", page_title="AI 행정관: AMP System", page_icon="🏛️")

st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    
    /* 실시간 API 로그 박스 스타일 */
    .log-box { 
        padding: 12px; border-radius: 6px; margin-bottom: 8px; 
        font-family: 'Consolas', monospace; font-size: 0.9em; 
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        animation: fadeIn 0.3s ease-in-out;
    }
    .log-law { background-color: #eff6ff; border-left: 5px solid #3b82f6; color: #1e3a8a; } /* 법령 (Blue) */
    .log-naver { background-color: #f0fdf4; border-left: 5px solid #22c55e; color: #14532d; } /* 네이버 (Green) */
    .log-db { background-color: #fef2f2; border-left: 5px solid #ef4444; color: #7f1d1d; } /* DB (Red) */
    .log-brain { background-color: #f3f4f6; border-left: 5px solid #6b7280; color: #1f2937; } /* Groq (Gray) */
    
    @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 엔진 어댑터 (Groq & Gemini)
# ==========================================

class GroqAdapter:
    """smolagents가 Groq를 사용하도록 연결"""
    def __init__(self):
        self.api_key = st.secrets["general"]["GROQ_API_KEY"]
        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.3-70b-versatile"

    def __call__(self, messages, stop_sequences=None):
        try:
            completion = self.client.chat.completions.create(
                model=self.model, messages=messages, stop=stop_sequences, temperature=0.1
            )
            return completion.choices[0].message.content
        except Exception as e:
            return f"Error: {e}"

def analyze_image_gemini(image_bytes):
    """Gemini 1.5 Flash로 이미지 분석"""
    try:
        genai.configure(api_key=st.secrets["general"]["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        img = Image.open(io.BytesIO(image_bytes))
        
        # [시각화] 로그 출력
        st.markdown("<div class='log-box log-brain'>👁️ [Vision] Gemini가 현장 사진을 정밀 분석 중...</div>", unsafe_allow_html=True)
        return model.generate_content(["이 공문서/현장 사진의 내용을 매우 상세하게 텍스트로 서술하시오.", img]).text
    except:
        return "이미지 분석 실패"

# ==========================================
# 3. 도구 (Tools) - API 호출 시각화 적용
# ==========================================

class OfficialLawApiTool(Tool):
    name = "search_law_api"
    description = "국가법령정보센터 API를 호출하여 법령 원문을 조회합니다. (법률가용)"
    inputs = {"query": {"type": "string", "description": "검색할 법령명 (예: 도로교통법)"}}
    output_type = "string"

    def forward(self, query: str) -> str:
        # 🚨 [API 시각화]
        st.markdown(f"<div class='log-box log-law'>🏛️ [Analyst] 국가법령정보센터 조회: '{query}'</div>", unsafe_allow_html=True)
        
        api_id = st.secrets["general"].get("LAW_API_ID")
        url = "http://www.law.go.kr/DRF/lawSearch.do"
        params = {"OC": api_id, "target": "law", "type": "XML", "query": query, "display": 3}
        try:
            resp = requests.get(url, params=params)
            root = ET.fromstring(resp.content)
            laws = []
            for item in root.findall(".//law"):
                name = item.find('lawNm').text
                link = item.find('lawDetailLink').text
                laws.append(f"- {name} (Link: ...{link[-10:]})")
            
            result = "\n".join(laws) if laws else "검색 결과 없음"
            st.markdown(f"<div class='log-box log-law'>↳ 법령 데이터 수신 완료 ({len(laws)}건)</div>", unsafe_allow_html=True)
            return result
        except Exception as e: return f"API 오류: {e}"

class NaverSearchTool(Tool):
    name = "search_naver"
    description = "네이버 검색(뉴스/블로그)을 통해 판례 해석 및 행정 사례를 찾습니다. (행정가용)"
    inputs = {"query": {"type": "string", "description": "검색어"}}
    output_type = "string"

    def forward(self, query: str) -> str:
        # 🚨 [API 시각화]
        st.markdown(f"<div class='log-box log-naver'>🌱 [Manager] 네이버 검색 API 호출: '{query}'</div>", unsafe_allow_html=True)
        
        headers = {
            "X-Naver-Client-Id": st.secrets["naver"]["CLIENT_ID"],
            "X-Naver-Client-Secret": st.secrets["naver"]["CLIENT_SECRET"]
        }
        res_txt = ""
        # 1. 뉴스
        try:
            news = requests.get("https://openapi.naver.com/v1/search/news.json", headers=headers, params={"query": query, "display": 1}).json()
            if news.get('items'): res_txt += f"[뉴스] {news['items'][0]['title']}\n"
        except: pass
        # 2. 블로그
        try:
            blog = requests.get("https://openapi.naver.com/v1/search/blog.json", headers=headers, params={"query": query + " 판례", "display": 1}).json()
            if blog.get('items'): res_txt += f"[블로그] {blog['items'][0]['title']}"
        except: pass
        
        result = res_txt if res_txt else "결과 없음"
        st.markdown(f"<div class='log-box log-naver'>↳ 여론/사례 데이터 수신 완료</div>", unsafe_allow_html=True)
        return result

class DBTool(Tool):
    name = "save_record"
    description = "처리 결과를 데이터베이스에 저장합니다. (주무관용)"
    inputs = {"summary": {"type": "string", "description": "저장할 내용"}}
    output_type = "string"
    
    def forward(self, summary: str) -> str:
        # 🚨 [API 시각화]
        st.markdown(f"<div class='log-box log-db'>💾 [Practitioner] Supabase DB 저장 시도...</div>", unsafe_allow_html=True)
        try:
            sb = create_client(st.secrets["supabase"]["SUPABASE_URL"], st.secrets["supabase"]["SUPABASE_KEY"])
            sb.table("law_reports").insert({"summary": summary}).execute()
            st.toast("DB 저장 성공!", icon="✅")
            return "저장 성공"
        except: return "저장 실패"

# ==========================================
# 4. 메인 실행 로직 (AMP 프롬프트)
# ==========================================

def main():
    st.title("🏛️ AI 행정관 Pro (AMP Edition)")
    st.caption("실시간 API 호출 시각화: 국가법령(Blue) / 네이버(Green) / DB(Red)")

    col1, col2 = st.columns([1, 1.1])

    with col1:
        st.subheader("📝 민원 접수")
        uploaded_file = st.file_uploader("증빙 서류/사진", type=['jpg', 'png'])
        user_input = st.text_area("민원 내용", height=150, placeholder="내용을 입력하세요.")

        if st.button("🚀 업무 처리 시작", type="primary", use_container_width=True):
            if not user_input and not uploaded_file:
                st.warning("내용을 입력해주세요.")
            else:
                # API 로그가 찍힐 컨테이너
                with st.status("🔄 AI 에이전트 팀이 협업 중입니다...", expanded=True) as status:
                    
                    # 1. Vision
                    vision_res = ""
                    if uploaded_file:
                        vision_res = analyze_image_gemini(uploaded_file.getvalue())

                    # 2. Agent Setup
                    st.markdown("---")
                    st.markdown("**🧠 Groq (Llama 3)가 AMP 프로토콜을 가동합니다.**")
                    
                    # AMP 시스템 프롬프트
                    prompt = f"""
                    당신은 행정관 팀 리더입니다. 아래 민원에 대해 3단계(AMP)로 처리하고, 각 단계마다 적절한 도구를 반드시 사용하세요.

                    [민원]: {user_input}
                    [사진분석]: {vision_res}

                    [Step 1: Analyst (법률가)]
                    - 'search_law_api' 도구를 사용하여 관련 법령을 찾으시오.
                    - 위법 여부를 판단하시오.

                    [Step 2: Manager (행정가)]
                    - 'search_naver' 도구를 사용하여 유사 판례나 행정 해석을 찾으시오.
                    - 처분 수위(과태료, 계도 등)를 결정하시오.

                    [Step 3: Practitioner (주무관)]
                    - 최종 '처분사전통지서' 또는 '답변서'를 작성하시오.
                    - 'save_record' 도구로 기록을 저장하시오.
                    """

                    model = GroqAdapter()
                    tools = [OfficialLawApiTool(), NaverSearchTool(), DBTool()]
                    
                    # 🚨 [핵심 수정] add_base_tools=False (DuckDuckGo 끄기)
                    agent = CodeAgent(tools=tools, model=model, add_base_tools=False)
                    
                    try:
                        # 에이전트 실행 (로그는 Tool 내부에서 자동 출력됨)
                        result = agent.run(prompt)
                        st.session_state['result'] = result
                        status.update(label="✅ 업무 처리 완료!", state="complete", expanded=False)
                    except Exception as e:
                        st.error(f"실행 중 오류: {e}")

    with col2:
        st.subheader("📄 최종 결과 보고서")
        if 'result' in st.session_state:
            # 결과 표시
            st.markdown(f"""
            <div style='background:white; padding:30px; border-radius:10px; border:1px solid #ddd; box-shadow:0 2px 10px rgba(0,0,0,0.05);'>
                {st.session_state['result']}
            </div>
            """, unsafe_allow_html=True)
            st.success("모든 절차가 법적/행정적 검토를 거쳐 완료되었습니다.")
        else:
            st.info("왼쪽에서 실행하면 API 호출 과정과 결과가 여기에 표시됩니다.")

if __name__ == "__main__":
    main()
