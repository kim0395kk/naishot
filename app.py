import streamlit as st
import requests
import matplotlib.pyplot as plt

st.title("충주시 평균 나이 대시보드")

region = st.text_input("지역명 입력", "충주시")
if region:
    resp = requests.get(
        "https://api.odcloud.kr/api/XXXX/인구현황",
        params={
            "serviceKey": st.secrets["public_api"]["key"],
            "cond[지역명]": region
        }
    )
    data = resp.json()["data"][0]["age_distribution"]
    ages = list(map(int, data.keys()))
    pops = list(data.values())
    avg_age = sum(a*p for a,p in zip(ages,pops)) / sum(pops)
    youth_index = 100 - abs(avg_age - 40)

    fig, ax = plt.subplots()
    ax.bar(ages, pops)
    ax.set_xlabel("나이")
    ax.set_ylabel("인구 수")
    st.pyplot(fig)

    st.metric("평균 나이", f"{avg_age:.1f}세")
    st.metric("젊음 지수", f"{youth_index:.1f} / 100")

