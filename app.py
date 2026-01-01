import streamlit as st
import google.generativeai as genai
from groq import Groq
from supabase import create_client
from smolagents import CodeAgent, Tool
import requests
import xml.etree.ElementTree as ET
from PIL import Image
import io

# ==========================================
# 1. UI 스타일 & 설정
# ==========================================
st.set_page_config(layout="wide", page_title="AI 행정관: Process View", page_icon="⚙️")

st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    
    /* API 로그 스타일 */
    .log-box { padding: 10px; border-radius: 5px; margin-bottom: 8px; font-family: monospace; font-size: 0.9em; animation: fadeIn 0.5s; }
    .log-law { background-color: #e0e7ff; border-left: 4px solid #4338ca; color: #3730a3; } /* 법령 API (Blue) */
    .log-naver { background-color: #dcfce7; border-left: 4px solid #15803d; color: #14532d; } /* 네이버 API (Green) */
    .log-db { background-color: #fee2e2; border-left: 4px solid #b91c1c; color: #7f1d1d; } /* DB (Red) */
    .log-groq { background-color: #f3f4f6; border-left: 4px solid #4b5563; color: #1f2937; } /* Groq (Gray) */

    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 엔진 어댑터
# ==========================================
class GroqAdapter:
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
    try:
        genai.configure(api_key=st.secrets["general"]["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        img = Image.open(io.BytesIO(image_bytes))
        # 시각화: 로그 출력
        st.markdown("<div class='log-box log-groq'>👁️ [Vision API] Gemini 1.5 Flash가 이미지를 분석 중...</div>", unsafe_allow_html=True)
        return model.generate_content(["이 문서/사진의 내용을 상세히 텍스트로 추출하라.", img]).text
    except:
        return "이미지 분석 실패"

# ==========================================
# 3. 도구 (Tools) - 시각화 로직 추가됨 🚨
# ==========================================

class OfficialLawApiTool(Tool):
    name = "search_law_api"
    description = "국가법령정보센터 API를 호출합니다. 법률가가 사용합니다."
    inputs = {"query": {"type": "string", "description": "법령명"}}
    output_type = "string"

    def forward(self, query: str) -> str:
        # 🚨 [시각화] API 호출 알림
        st.markdown(f"<div class='log-box log-law'>🏛️ [Analyst] 국가법령정보센터 API 호출: '{query}' 검색 중...</div>", unsafe_allow_html=True)
        st.toast(f"🏛️ 국가법령 API: {query}", icon="⚖️")
        
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
                laws.append(f"{name} (Link: ...{link[-10:]})")
            
            result = ", ".join(laws) if laws else "검색 결과 없음"
            # 🚨 [시각화] 결과 알림
            st.markdown(f"<div class='log-box log-law'>↳ 결과 수신: {result}</div>", unsafe_allow_html=True)
            return result
        except Exception as e: return f"API 오류: {e}"

class NaverSearchTool(Tool):
    name = "search_naver"
    description = "네이버 검색 API를 호출합니다. 판례 및 여론 확인용."
    inputs = {"query": {"type": "string", "description": "검색어"}}
    output_type = "string"

    def forward(self, query: str) -> str:
        # 🚨 [시각화] API 호출 알림
        st.markdown(f"<div class='log-box log-naver'>🌱 [Manager] 네이버 검색 API 호출: '{query}'</div>", unsafe_allow_html=True)
        st.toast(f"🌱 네이버 API: {query}", icon="🔍")

        headers = {
            "X-Naver-Client-Id": st.secrets["naver"]["CLIENT_ID"],
            "X-Naver-Client-Secret": st.secrets["naver"]["CLIENT_SECRET"]
        }
        res_txt = ""
        try:
            news = requests.get("https://openapi.naver.com/v1/search/news.json", headers=headers, params={"query": query, "display": 1}).json()
            title = news['items'][0]['title'] if news['items'] else "뉴스 없음"
            res_txt = f"뉴스: {title}"
        except: res_txt = "검색 실패"
        
        st.markdown(f"<div class='log-box log-naver'>↳ 결과 수신: {res_txt}</div>", unsafe_allow_html=True)
        return res_txt

class DBTool(Tool):
    name = "save_record"
    description = "Supabase DB에 저장합니다."
    inputs = {"summary": {"type": "string", "description": "내용"}}
    output_type = "string"
    def forward(self, summary: str) -> str:
        # 🚨 [시각화] API 호출 알림
        st.markdown(f"<div class='log-box log-db'>💾 [Practitioner] Supabase DB 연결 및 저장 시도...</div>", unsafe_allow_html=True)
        try:
            sb = create_client(st.secrets["supabase"]["SUPABASE_URL"], st.secrets["supabase"]["SUPABASE_KEY"])
            sb.table("law_reports").insert({"summary": summary}).execute()
            st.toast("저장 완료!", icon="✅")
            return "저장 완료"
        except: return "저장 실패"

# ==========================================
# 4. 메인 로직
# ==========================================
def main():
    st.title("👁️ AI 행정관: 투명한 API 로그")
    st.info("각 단계에서 어떤 API가 호출되는지 실시간으로 보여줍니다.")

    col1, col2 = st.columns([1, 1])

    with col1:
        uploaded_file = st.file_uploader("증빙 자료", type=['jpg', 'png'])
        user_input = st.text_area("민원 내용", height=100)

        if st.button("🚀 AMP 시스템 실행", type="primary", use_container_width=True):
            if not user_input and not uploaded_file:
                st.warning("내용을 입력해주세요.")
            else:
                # 로그가 표시될 컨테이너
                with st.status("🔄 AI 처리 로그 (실시간 API 호출)", expanded=True) as status:
                    
                    # 1. Vision
                    vision_context = ""
                    if uploaded_file:
                        vision_context = analyze_image_gemini(uploaded_file.getvalue())

                    # 2. Agent Run
                    st.markdown("---")
                    st.markdown("**🧠 Groq (Llama 3) 사고 시작...**")
                    
                    full_query = f"""
                    상황: {user_input}
                    사진내용: {vision_context}
                    
                    AMP 프로토콜(법률가->행정가->주무관)에 따라:
                    1. 'search_law_api'로 법령 확인
                    2. 'search_naver'로 판례 확인
                    3. 'save_record'로 저장
                    
                    각 단계별 내용을 상세히 작성하시오.
                    """

                    model = GroqAdapter()
                    tools = [OfficialLawApiTool(), NaverSearchTool(), DBTool()]
                    agent = CodeAgent(tools=tools, model=model, add_base_tools=True)
                    
                    try:
                        # 에이전트 실행 시, 위에서 정의한 Tool의 forward 함수가 실행되면서
                        # 자동으로 st.markdown 로그가 찍힙니다.
                        result = agent.run(full_query)
                        st.session_state['result'] = result
                        status.update(label="✅ 처리 완료", state="complete")
                    except Exception as e:
                        st.error(f"실행 중 오류: {e}")

    with col2:
        st.subheader("📄 최종 결과물")
        if 'result' in st.session_state:
            st.write(st.session_state['result'])
        else:
            st.caption("왼쪽에서 실행하면 API 호출 과정이 보입니다.")

if __name__ == "__main__":
    main()
