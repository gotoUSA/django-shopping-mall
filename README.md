# Django 쇼핑몰 API 프로젝트

Django REST Framework를 활용한 이커머스 플랫폼 백엔드 API

## 🚀 주요 기능

- 사용자 인증 및 권한 관리 (커스텀 User 모델)
- 상품 관리 (카테고리, 이미지, 리뷰)
- 장바구니 기능
- 주문 및 결제 프로세스
- 관리자 페이지 커스터마이징

## 🛠 기술 스택

- Python 3.12
- Django 5.2.4
- Django REST Framework
- SQLite (개발) / PostgreSQL (프로덕션 예정)

## 📦 설치 방법

### 1. 저장소 클론
```bash
git clone https://github.com/gotoUSA/django-shopping-mall.git
cd django-shopping-mall
2. 가상환경 생성 및 활성화
bashpython -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
3. 의존성 설치
bashpip install -r requirements.txt
4. 환경 변수 설정
bashcp .env.example .env
# .env 파일을 열어 SECRET_KEY 등 설정
5. 데이터베이스 마이그레이션
bashpython manage.py migrate
6. 슈퍼유저 생성
bashpython manage.py createsuperuser
7. 서버 실행
bashpython manage.py runserver
📁 프로젝트 구조
myproject/
├── myproject/          # 프로젝트 설정
├── shopping/           # 메인 앱
│   ├── models/        # 모델 분리
│   │   ├── user.py
│   │   ├── product.py
│   │   ├── order.py
│   │   └── cart.py
│   ├── views/         # API 뷰
│   ├── serializers/   # DRF 시리얼라이저
│   └── admin.py       # 관리자 설정
├── requirements.txt
└── README.md

🔍 주요 모델

User: AbstractUser 상속, 추가 필드 (전화번호, 주소, 포인트 등)
Product: 상품 정보, 다중 이미지, 리뷰
Cart/CartItem: 장바구니 기능
Order/OrderItem: 주문 관리

📝 API 엔드포인트 (예정)

/api/products/ - 상품 목록/상세
/api/cart/ - 장바구니 CRUD
/api/orders/ - 주문 관리
/api/auth/ - 인증 관련

🤝 기여 방법

Fork the Project
Create your Feature Branch (git checkout -b feature/AmazingFeature)
Commit your Changes (git commit -m 'Add some AmazingFeature')
Push to the Branch (git push origin feature/AmazingFeature)
Open a Pull Request

📄 라이선스
This project is licensed under the MIT License

👤 작성자
GitHub: [@gotoUSA](https://github.com/gotoUSA)