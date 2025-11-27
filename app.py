import streamlit as st
from playwright.sync_api import sync_playwright  # Playwright sync API
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

def scroll_to_bottom(page):
    """동적 콘텐츠 로드를 위한 스크롤 (Playwright JS 버전)"""
    scroll_wait_timeout = 2000  # ms
    scroll_stable_interval = 50  # ms
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
    """기간 필터링 크롤링 함수 (Playwright 사용)"""
    data = []
    base_url = "https://www.gdhwelfare.or.kr/community/PhotoList.do?bbsNo=&pageIndex={}&searchKeyword="
    page_index = 1
    max_pages = 100
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        try:
            while page_index <= max_pages:
                # 진행바 업데이트
                progress = page_index / max_pages
                progress_bar.progress(progress, text=f"페이지 {page_index}/{max_pages} 처리 중...")
                
                url = base_url.format(page_index)
                st.write(f"📄 페이지 {page_index} 로딩 중...")
                page.goto(url, wait_until='networkidle')  # 네트워크 안정 대기
                
                # 로딩 대기
                page.wait_for_selector(".list_in", timeout=10000)
                st.write(f"✅ 페이지 {page_index} 로딩 완료")
                
                scroll_to_bottom(page)
                
                # 게시물 추출
                items = page.query_selector_all(".list_in")
                if not items:
                    st.write(f"📭 페이지 {page_index}에 게시물 없음.")
                    break
                
                page_has_valid = False
                for item in items:
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
            browser.close()
    
    return data

# Streamlit 앱 UI (기존과 동일)
st.title("🖼️ GD 복지 사진 게시물 크롤러")
st.write("기간 내 제목과 날짜를 자동 추출해 Excel로 저장합니다. (Playwright로 동적 로딩 지원)")

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

# 푸터: 도움말
st.sidebar.markdown("---")
st.sidebar.markdown("""
### 📖 사용 팁
- **로컬 테스트**: `playwright install chromium` 후 실행.
- **Cloud 에러 시**: Manage app > Logs 확인. (Playwright가 브라우저 다운로드 중 실패하면 재부팅.)
- **대안**: 동적 사이트라 Playwright 추천. 문제가 지속되면 로컬 공유 (ngrok 등).
""")
