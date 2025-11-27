import streamlit as st
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
from datetime import datetime, timedelta
import io

def parse_date(date_str):
    """날짜 문자열을 datetime으로 파싱"""
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d')
    except ValueError:
        try:
            return datetime.strptime(date_str.strip(), '%Y.%m.%d')
        except:
            return None

def scroll_to_bottom(driver, scroll_wait_timeout=2, scroll_stable_interval=0.05):
    """동적 콘텐츠 로드를 위한 스크롤"""
    before_h = driver.execute_script("return window.scrollY")
    while True:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
        stable_time = 0
        while stable_time < scroll_wait_timeout:
            time.sleep(scroll_stable_interval)
            after_h = driver.execute_script("return window.scrollY")
            if after_h == before_h:
                stable_time += scroll_stable_interval
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
            else:
                before_h = after_h
                break
        else:
            break

def scrape_with_period(start_date, end_date, progress_bar):
    """기간 필터링 크롤링 함수 (진행바 지원)"""
    options = uc.ChromeOptions()
    options.add_argument('--headless')  # 로컬 테스트 시 주석 해제
    driver = uc.Chrome(options=options)
    
    base_url = "https://www.gdhwelfare.or.kr/community/PhotoList.do?bbsNo=&pageIndex={}&searchKeyword="
    data = []
    page_index = 1
    max_pages = 100
    
    try:
        while page_index <= max_pages:
            # 진행바 업데이트
            progress = page_index / max_pages
            progress_bar.progress(progress, text=f"페이지 {page_index}/{max_pages} 처리 중...")
            
            url = base_url.format(page_index)
            st.write(f"📄 페이지 {page_index} 로딩 중...")
            driver.get(url)
            
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".list_in"))
                )
                st.write(f"✅ 페이지 {page_index} 로딩 완료")
            except:
                st.write(f"⚠️ 페이지 {page_index} 로딩 실패")
                break
            
            scroll_to_bottom(driver)
            
            items = driver.find_elements(By.CSS_SELECTOR, ".list_in")
            if not items:
                st.write(f"📭 페이지 {page_index}에 게시물 없음.")
                break
            
            page_has_valid = False
            for item in items:
                Title = item.find_elements(By.CSS_SELECTOR, ".bold.ellipsis")
                DATE = item.find_elements(By.CSS_SELECTOR, ".photo_info > span:nth-child(2)")
                
                if Title and DATE:
                    Title_ = Title[0].text.strip()
                    Date_str = DATE[0].text.strip()
                    upload_date = parse_date(Date_str)
                    
                    if upload_date:
                        if start_date <= upload_date <= end_date:
                            data.append([Title_, Date_str])
                            page_has_valid = True
                            st.write(f"📝 추가: {Title_[:30]}... | {Date_str}")
                        else:
                            if upload_date < start_date:
                                st.write(f"🛑 기간 초과. 크롤링 중단 (페이지 {page_index}).")
                                return data
                    else:
                        st.write(f"⚠️ 날짜 파싱 실패: {Date_str}")
            
            if not page_has_valid and page_index > 1:
                st.write("🛑 기간 내 데이터 더 없음. 종료.")
                break
            
            page_index += 1
            time.sleep(1)
        
        return data
    finally:
        driver.quit()

# Streamlit 앱 UI
st.title("🖼️ GD 복지 사진 게시물 크롤러")
st.write("기간 내 제목과 날짜를 자동 추출해 Excel로 저장합니다.")

# 사이드바: 설정
st.sidebar.header("📅 크롤링 설정")
col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.sidebar.date_input("시작 날짜", value=datetime.now() - timedelta(days=7))
with col2:
    end_date = st.sidebar.date_input("종료 날짜", value=datetime.now())

if start_date > end_date:
    st.sidebar.error("❌ 시작 날짜가 종료 날짜보다 늦습니다!")
    st.stop()

start_dt = datetime.combine(start_date, datetime.min.time())
end_dt = datetime.combine(end_date, datetime.min.time())

st.sidebar.info(f"기간: {start_date} ~ {end_date}")

# 메인: 실행 버튼
if st.button("🚀 크롤링 시작", type="primary"):
    # 진행바 초기화
    progress_bar = st.progress(0)
    status_text = st.empty()  # 상태 메시지용
    
    with st.spinner("크롤링 중... (페이지 로딩 및 스크롤 처리)"):
        data = scrape_with_period(start_dt, end_dt, progress_bar)
    
    # 진행바 완료
    progress_bar.progress(1.0, text="크롤링 완료!")
    
    if data:
        df = pd.DataFrame(data, columns=['제목', '날짜'])
        
        # 테이블 미리보기
        st.subheader("📊 추출 결과 미리보기")
        st.dataframe(df, use_container_width=True)
        
        # Excel 다운로드
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"gdhwelfare_photos_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}_{timestamp}.xlsx"
        
        st.subheader("💾 다운로드")
        st.download_button(
            label="Excel 파일 다운로드",
            data=output.getvalue(),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.success(f"✅ {len(data)}개 게시물 추출 완료!")
    else:
        st.warning("❌ 기간 내 게시물 없음. 기간을 조정해 보세요.")

