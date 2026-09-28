# 🎯 나의 버킷 리스트

인생에서 꼭 이루고 싶은 것들을 기록하고 관리하는 간단한 웹 애플리케이션입니다.

## ✨ 주요 기능

- ✅ **버킷 리스트 추가/수정/삭제** - 간편한 CRUD 기능
- 📊 **실시간 통계** - 전체, 완료, 진행중 항목 개수와 달성률 표시
- 🔍 **필터링** - 전체/진행중/완료 항목 필터 기능
- 💾 **자동 저장** - LocalStorage를 통한 데이터 영구 보관
- 📱 **반응형 디자인** - 모바일, 태블릿, 데스크톱 모두 지원
- 🎨 **직관적인 UI** - 깔끔하고 사용하기 쉬운 인터페이스

## 🛠 기술 스택

- **Frontend**: HTML5, CSS3, JavaScript (ES6+)
- **CSS Framework**: Tailwind CSS (CDN)
- **Storage**: LocalStorage API
- **Architecture**: Vanilla JavaScript (프레임워크 없음)

## 📁 프로젝트 구조

```
bucket-list/
├── index.html              # 메인 HTML 파일
├── css/
│   └── styles.css          # 커스텀 스타일 (Tailwind 보완)
├── js/
│   ├── storage.js          # LocalStorage 관리 모듈
│   └── app.js              # 메인 애플리케이션 로직
├── assets/                 # 추가 자원용 폴더
└── README.md               # 프로젝트 문서
```

## 🚀 설치 및 실행 방법

### 방법 1: 직접 실행 (가장 간단)

1. 프로젝트 클론 또는 다운로드
   ```bash
   git clone <repository-url>
   cd bucket-list
   ```

2. `index.html` 파일을 웹 브라우저로 열기
   - 파일 탐색기에서 `index.html` 더블클릭
   - 또는 브라우저 주소창에 파일 경로 입력

### 방법 2: Live Server 사용 (VS Code)

1. VS Code에서 프로젝트 열기
2. Live Server 확장 프로그램 설치 (없는 경우)
3. `index.html` 우클릭 → "Open with Live Server"

### 방법 3: Python 간이 서버

```bash
# Python 3.x
python -m http.server 8000

# 브라우저에서 http://localhost:8000 접속
```

## 📖 사용 방법

### 1. 버킷 리스트 추가
- 상단 입력창에 목표를 입력
- "추가" 버튼 클릭 또는 Enter 키 입력

### 2. 완료 상태 변경
- 항목 왼쪽의 체크박스 클릭
- 완료된 항목은 취소선과 함께 회색으로 표시

### 3. 항목 수정
- 각 항목의 "수정" 버튼 클릭
- 모달 창에서 새로운 내용 입력 후 "저장"

### 4. 항목 삭제
- 각 항목의 "삭제" 버튼 클릭
- 확인 메시지에서 "확인" 선택

### 5. 필터링
- **전체**: 모든 항목 표시
- **진행중**: 미완료 항목만 표시
- **완료**: 완료된 항목만 표시

## 📊 데이터 구조

```javascript
{
  id: "1730880000000",           // 고유 ID (timestamp)
  title: "세계 일주하기",         // 버킷 리스트 제목
  completed: false,               // 완료 여부
  createdAt: "2025-11-06",       // 생성 날짜
  completedAt: null               // 완료 날짜 (완료 시에만)
}
```

## 💡 주요 특징

### LocalStorage 활용
- 브라우저 LocalStorage에 데이터 자동 저장
- 새로고침 후에도 데이터 유지
- 별도의 서버나 데이터베이스 불필요

### 반응형 디자인
- **모바일** (320px~): 세로 레이아웃
- **태블릿** (768px~): 최적화된 레이아웃
- **데스크톱** (1024px~): 넓은 화면 활용

### 깔끔한 코드 구조
- **모듈화**: Storage와 App 로직 분리
- **클래스 기반**: 객체 지향 프로그래밍
- **한국어 주석**: 코드 이해도 향상

## 🎨 UI/UX

- **색상 테마**
  - Primary: Blue (#3b82f6) - 버튼, 강조
  - Success: Green (#10b981) - 완료 상태
  - Background: Gray-50 (#f9fafb)

- **애니메이션**
  - 항목 추가 시 슬라이드인 효과
  - 버튼 호버 및 클릭 효과
  - 모달 페이드인 효과

## 🔧 커스터마이징

### 색상 변경
`index.html`의 Tailwind CSS 클래스 수정:
```html
<!-- 예: 파란색 → 보라색 -->
<button class="bg-purple-600 hover:bg-purple-700">
```

### 스타일 추가
`css/styles.css`에 커스텀 CSS 추가

### 기능 확장
`js/app.js` 또는 `js/storage.js`에 새로운 메서드 추가

## 📝 향후 개선 사항

- [ ] 카테고리/태그 기능
- [ ] 항목에 이미지 추가
- [ ] 상세 메모 기능
- [ ] 목표 날짜 설정
- [ ] 우선순위 지정
- [ ] 데이터 내보내기/가져오기 (JSON)
- [ ] 다크 모드 토글
- [ ] 드래그 앤 드롭 정렬

## 🌐 브라우저 호환성

- Chrome (최신 버전)
- Firefox (최신 버전)
- Safari (최신 버전)
- Edge (최신 버전)

> **참고**: LocalStorage를 지원하는 모든 모던 브라우저에서 작동합니다.

## 📄 라이선스

이 프로젝트는 자유롭게 사용 및 수정이 가능합니다.

## 👨‍💻 개발자

개인 학습 및 포트폴리오 목적으로 제작되었습니다.

## 🙏 감사의 말

- [Tailwind CSS](https://tailwindcss.com/) - 빠른 스타일링
- LocalStorage API - 간편한 데이터 저장

---

**즐거운 버킷 리스트 작성 되세요! 🎉**
