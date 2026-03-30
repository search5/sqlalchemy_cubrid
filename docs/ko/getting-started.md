# 시작하기

이 가이드에서는 sqlalchemy-cubrid를 설치하고, Docker로 CUBRID 데이터베이스를 설정하고, 첫 번째 쿼리를 실행하는 방법을 안내합니다.

## 설치

### pip 사용

```bash
pip install git+https://github.com/search5/sqlalchemy_cubrid.git
```

이 명령은 `sqlalchemy-cubrid`를 의존성(`sqlalchemy>=2.0` 및 `pycubrid>=0.6.0`)과 함께 설치합니다.

### Poetry 사용

```bash
poetry add git+https://github.com/search5/sqlalchemy_cubrid.git
```

### 소스에서 설치

```bash
git clone https://github.com/search5/sqlalchemy_cubrid.git
cd sqlalchemy_cubrid
poetry install
```

## Docker로 CUBRID 설정하기

개발용으로 CUBRID를 실행하는 가장 쉬운 방법은 Docker를 사용하는 것입니다.

### CUBRID 컨테이너 시작

```bash
docker run -d \
  --name cubrid-dev \
  -p 33000:33000 \
  -e CUBRID_DB=testdb \
  cubrid/cubrid:11.4
```

이 명령은 `testdb`라는 데이터베이스를 가진 CUBRID 11.4를 포트 33000으로 노출하여 시작합니다. 기본 DBA 사용자의 비밀번호는 비어 있습니다.

### 컨테이너 실행 확인

```bash
docker logs cubrid-dev
```

데이터베이스가 준비되었다는 메시지가 표시될 때까지 기다리십시오.

### 다른 CUBRID 버전

```bash
# CUBRID 11.2
docker run -d --name cubrid-11.2 -p 33000:33000 -e CUBRID_DB=testdb cubrid/cubrid:11.2

# CUBRID 10.2
docker run -d --name cubrid-10.2 -p 33000:33000 -e CUBRID_DB=testdb cubrid/cubrid:10.2
```

## 첫 번째 연결

```python
from sqlalchemy import create_engine, text

# CUBRID에 연결
engine = create_engine("cubrid://dba:@localhost:33000/testdb")

# 연결 테스트
with engine.connect() as conn:
    result = conn.execute(text("SELECT 1 FROM db_root"))
    print(result.scalar())  # 1
```

!!! note
    연결 URL 형식은 `cubrid://user:password@host:port/database`입니다. 기본 사용자는 `dba`이며 비밀번호는 비어 있습니다. CUBRID 브로커의 기본 포트는 `33000`입니다.

## 기본 ORM 예제

다음은 SQLAlchemy ORM을 사용하여 테이블을 생성하고, 행을 삽입하고, 쿼리하는 완전한 예제입니다.

### 모델 정의

```python
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200))

    def __repr__(self):
        return f"<User(id={self.id}, name={self.name!r})>"
```

### 테이블 생성 및 데이터 추가

```python
engine = create_engine("cubrid://dba:@localhost:33000/testdb", echo=True)

# 모든 테이블 생성
Base.metadata.create_all(engine)

# 행 삽입
with Session(engine) as session:
    session.add_all([
        User(name="Alice", email="alice@example.com"),
        User(name="Bob", email="bob@example.com"),
        User(name="Charlie", email="charlie@example.com"),
    ])
    session.commit()
```

### 데이터 조회

```python
from sqlalchemy import select

with Session(engine) as session:
    # 모든 사용자 조회
    stmt = select(User).order_by(User.name)
    users = session.scalars(stmt).all()
    for user in users:
        print(user)
    # <User(id=1, name='Alice')>
    # <User(id=2, name='Bob')>
    # <User(id=3, name='Charlie')>

    # 필터링
    stmt = select(User).where(User.name == "Alice")
    alice = session.scalars(stmt).first()
    print(alice.email)  # alice@example.com
```

### 수정 및 삭제

```python
with Session(engine) as session:
    # 수정
    alice = session.scalars(
        select(User).where(User.name == "Alice")
    ).first()
    alice.email = "alice@newdomain.com"
    session.commit()

    # 삭제
    bob = session.scalars(
        select(User).where(User.name == "Bob")
    ).first()
    session.delete(bob)
    session.commit()
```

### 정리

```python
# 모든 테이블 삭제
Base.metadata.drop_all(engine)
```

## SQLAlchemy Core 사용하기

ORM 대신 Core API를 선호하는 경우:

```python
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, select, insert

engine = create_engine("cubrid://dba:@localhost:33000/testdb")
metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("email", String(200)),
)

# 테이블 생성
metadata.create_all(engine)

with engine.connect() as conn:
    # 삽입
    conn.execute(insert(users).values(name="Alice", email="alice@example.com"))
    conn.commit()

    # 조회
    stmt = select(users).where(users.c.name == "Alice")
    row = conn.execute(stmt).first()
    print(row)  # (1, 'Alice', 'alice@example.com')

# 테이블 삭제
metadata.drop_all(engine)
```

## 다음 단계

- [연결](connection.md) -- 연결 옵션 및 격리 수준에 대해 알아보기
- [타입](types.md) -- CUBRID 타입 매핑 이해하기
- [DDL](ddl.md) -- 테이블, 시퀀스, 인덱스 생성하기
- [CUBRID 기능](cubrid-features.md) -- 컬렉션 타입, 상속, OID 참조 알아보기
