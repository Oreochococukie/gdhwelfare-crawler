import streamlit as st
import subprocess
import sys
import pandas as pd
import time
from datetime import datetime, timedelta
import io

# ------------------------------------------------------
# [핵심] Streamlit Cloud에서 Playwright 브라우저 강제 설치
# ------------------------------------------------------
# 이 코드가 없으면 클라우드에서 "Executable doesn't exist" 에러가 뜹니다.
@st.cache_resource
def install_playwright_browser():
    print("🚀 Playwright 브라우저 설치 중...")
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("✅ 브라우저 설치 완료!")
    except Exception as e:
        print(f"❌ 설치 중 오류 발생: {e}")

# 앱 시작 시 딱 한 번만 실행됨
install_playwright_browser()

from playwright.sync_api import sync_playwright

# ------------------------------------------------------
# 기존 크롤링 로직 (그대로 유지)
# ------------------------------------------------------

def parse_date(date_str):
    """날짜 문자열을 datetime으로 파싱"""
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d')
    except ValueError:
        try:
            return datetime.strptime(date_str.strip(), '%Y.%m.%d')
        except:
            return None

def scroll_to_bottom(page):
    """동적 콘텐츠 로드를 위한 스크롤"""
    scroll_wait_timeout = 2000
    scroll_stable_interval = 50
    before_h = page.evaluate("() => window.scrollY")
    
    while True:
        page.keyboard.press("End")
        stable_time = 0
        while stable_time < scroll_wait_timeout:
            time.sleep(scroll_stable_interval / 1000)
            after_h = page.evaluate("() => window.scrollY")
            if after_h == before_h:
                stable_time += scroll_stable_interval
                page.keyboard.press("End")
            else:
                before_h = after_h
                break
        else:
            break

def scrape_with_period(start_date, end_date, progress_bar):
    data = []
    base_url = "https://www.gdhwelfare.or.kr/community/PhotoList.do?bbsNo=&pageIndex={}&searchKeyword=#none"
    page_index = 1
    max_pages = 100
    
    with sync_playwright() as p:
        # Streamlit Cloud에서는 headless 모드 필수
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        try:
            while page_index <= max_pages:
                progress = page_index / max_pages
                progress_bar.progress(progress, text=f"페이지 {page_index}/{max_pages} 처리 중...")
                
                url = base_url.format(page_index)
                # st.write(f"📄 페이지 {page_index} 로딩 중...") # 로그 너무 많으면 지저분해서 주석 처리
                
                try:
                    page.goto(url, wait_until='networkidle', timeout=60000) # 타임아웃 60초로 넉넉하게
                except Exception as e:
                    st.error(f"페이지 로드 실패: {e}")
                    break

                try:
                    page.wait_for_selector(".list_in", timeout=5000)
                except:
                    st.write("게시물이 없거나 로딩이 너무 오래 걸립니다.")
                    break
                
                scroll_to_bottom(page)
                
                items = page.query_selector_all(".list_in")
                if not items:
                    break
                
                page_has_valid = False
                for item in items:
                    try:
                        title_elem = item.query_selector(".bold.ellipsis")
                        date_elem = item.query_selector(".photo_info > span:nth-child(2)")
                        
                        if title_elem and date_elem:
                            Title_ = title_elem.inner_text().strip()
                            Date_str = date_elem.inner_text().strip()
                            upload_date = parse_date(Date_str)
                            
                            if upload_date:
                                if start_date <= upload_date <= end_date:
                                    data.append([Title_, Date_str])
                                    page_has_valid = True
                                else:
                                    if upload_date < start_date:
                                        return data
                    except Exception:
                        continue
                
                if not page_has_valid and page_index > 1:
                    break
                
                page_index += 1
                time.sleep(1)
            
            return data
        finally:
            browser.close()
    
    return data

# UI 부분
st.set_page_config(page_title="GD 복지 크롤러", page_icon="🐢")

st.title("🐢 GD 복지 사진 게시물 크롤러")
st.markdown("Playwright 엔진을 사용하여 동적 페이지를 크롤링합니다.")

st.sidebar.header("📅 설정")
col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.sidebar.date_input("시작 날짜", value=datetime.now() - timedelta(days=7))
with col2:
    end_date = st.sidebar.date_input("종료 날짜", value=datetime.now())

if st.button("🚀 크롤링 시작", type="primary"):
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.min.time())
    
    progress_bar = st.progress(0)
    with st.spinner("브라우저를 띄우고 데이터를 수집 중입니다..."):
        data = scrape_with_period(start_dt, end_dt, progress_bar)
    
    progress_bar.progress(1.0, text="완료!")
    
    if data:
        df = pd.DataFrame(data, columns=['제목', '날짜'])
        st.success(f"총 {len(data)}건 수집 완료!")
        st.dataframe(df)
        
        # 엑셀 다운로드
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        
        st.download_button(
            label="📥 엑셀 다운로드",
            data=output.getvalue(),
            file_name=f"result_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("수집된 데이터가 없습니다.")
