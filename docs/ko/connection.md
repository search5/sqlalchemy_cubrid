# 연결

이 페이지에서는 엔진 URL 형식, 연결 옵션, 격리 수준, 연결 풀링, 연결 끊김 감지에 대해 다룹니다.

## 엔진 URL 형식

CUBRID 연결 URL은 표준 SQLAlchemy 형식을 따릅니다:

```
cubrid://user:password@host:port/database
```

| 구성 요소 | 기본값 | 설명 |
|-----------|--------|------|
| `user`     | `dba`       | CUBRID 데이터베이스 사용자 |
| `password` | (비어 있음)  | 사용자 비밀번호 |
| `host`     | `localhost` | CUBRID 브로커 호스트 |
| `port`     | `33000`     | CUBRID 브로커 포트 |
| `database` | (비어 있음)  | 데이터베이스 이름 |

### 예시

```python
from sqlalchemy import create_engine

# 기본 DBA 사용자 (비밀번호 없음)
engine = create_engine("cubrid://dba:@localhost:33000/testdb")

# 명시적 자격 증명
engine = create_engine("cubrid://myuser:mypassword@db.example.com:33000/production")

# 명시적 드라이버 이름 (pycubrid만 지원)
engine = create_engine("cubrid+pycubrid://dba:@localhost:33000/testdb")
```

## 연결 옵션

`create_engine()` 함수는 표준 SQLAlchemy 옵션을 지원합니다:

```python
engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    echo=True,              # 모든 SQL 구문 로깅
    pool_size=5,            # 영구 연결 수
    max_overflow=10,        # pool_size를 초과하는 추가 연결 수
    pool_timeout=30,        # 연결 대기 시간 (초)
    pool_recycle=3600,      # N초 후 연결 재생성
    pool_pre_ping=True,     # 체크아웃 전 연결 테스트
)
```

### JSON 직렬화

JSON 컬럼 타입을 위한 사용자 정의 JSON 직렬화/역직렬화기를 전달할 수 있습니다:

```python
import orjson

engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    json_serializer=lambda obj: orjson.dumps(obj).decode(),
    json_deserializer=orjson.loads,
)
```

## 격리 수준

CUBRID는 세 가지 트랜잭션 격리 수준과 자동 커밋 모드를 지원합니다. dialect는 이를 CUBRID 숫자 코드로 내부적으로 매핑합니다.

| SQLAlchemy 이름 | CUBRID 코드 | 설명 |
|-----------------|-------------|------|
| `READ COMMITTED`    | 4           | 기본값. 커밋된 데이터만 읽습니다. |
| `REPEATABLE READ`   | 5           | 트랜잭션 내 읽기가 안정적입니다. |
| `SERIALIZABLE`      | 6           | 완전한 격리. 가장 엄격한 수준입니다. |
| `AUTOCOMMIT`        | --          | 각 구문이 즉시 커밋됩니다. |

!!! note
    CUBRID는 `READ UNCOMMITTED`를 지원하지 않습니다. 가장 낮은 격리 수준은 `READ COMMITTED`입니다.

### 격리 수준 설정

#### 엔진 생성 시

```python
engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    isolation_level="REPEATABLE READ",
)
```

#### 연결 단위

```python
with engine.connect().execution_options(
    isolation_level="SERIALIZABLE"
) as conn:
    # 이 연결은 SERIALIZABLE 격리를 사용합니다
    result = conn.execute(text("SELECT ..."))
```

#### 자동 커밋 모드

```python
with engine.connect().execution_options(
    isolation_level="AUTOCOMMIT"
) as conn:
    # 즉시 커밋이 필요한 DDL 또는 구문
    conn.execute(text("CREATE TABLE ..."))
```

!!! warning
    `AUTOCOMMIT`에서 트랜잭션 수준으로 되돌릴 때, dialect는 기본 pycubrid 연결에서 자동 커밋을 자동으로 비활성화합니다.

## 연결 풀링

SQLAlchemy는 내장 연결 풀링을 제공합니다. dialect는 모든 표준 풀 구현체와 함께 작동합니다.

### CUBRID 권장 설정

```python
engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    pool_size=5,          # 5개 연결 유지
    max_overflow=10,      # 최대 15개까지 허용
    pool_recycle=1800,    # 30분 후 재생성
    pool_pre_ping=True,   # 체크아웃 시 연결 검증
)
```

### NullPool (풀링 없음)

단기 실행 스크립트나 서버리스 환경의 경우:

```python
from sqlalchemy.pool import NullPool

engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    poolclass=NullPool,
)
```

## do_ping()

dialect는 연결을 검증하기 위해 `do_ping()`을 구현합니다. 이 메서드는 SQLAlchemy의 `pool_pre_ping` 기능에 사용되며 다음 쿼리를 실행합니다:

```sql
SELECT 1 FROM db_root
```

쿼리가 성공하면 연결이 활성 상태입니다. `pycubrid.Error`가 발생하면 연결이 끊어진 것으로 간주되어 교체됩니다.

```python
# pre-ping을 활성화하여 끊어진 연결을 자동 복구
engine = create_engine(
    "cubrid://dba:@localhost:33000/testdb",
    pool_pre_ping=True,
)
```

## is_disconnect()

dialect는 pycubrid에서 발생하는 예외를 검사하여 끊어진 연결을 감지합니다. 다음 경우에 연결이 끊어진 것으로 분류됩니다:

- `InterfaceError` 메시지에 "closed" 또는 "connection"이 포함된 경우
- `OperationalError` 메시지에 "communication" 또는 "connection"이 포함된 경우
- pycubrid 숫자 오류 코드가 알려진 연결 끊김 코드와 일치하는 경우:
    - `-4` -- 통신 오류
    - `-11` -- 핸들이 닫힘
    - `-21003` -- 연결 거부

`is_disconnect()`가 `True`를 반환하면 SQLAlchemy가 해당 연결을 무효화하고 풀에서 제거합니다.

## on_connect()

새로운 원시 DBAPI 연결이 생성될 때 dialect는 `on_connect` 콜백을 실행하여:

1. 자동 커밋을 비활성화합니다 (기본적으로 트랜잭션 동작을 위해)
2. 격리 수준 추적을 `READ COMMITTED`로 초기화합니다

이를 통해 모든 연결이 일관된 상태로 시작됩니다.

## Savepoint

CUBRID는 `SAVEPOINT`와 `ROLLBACK TO SAVEPOINT`를 지원하지만 `RELEASE SAVEPOINT`는 지원하지 않습니다. dialect는 릴리스 작업을 자동으로 건너뛰어 SQLAlchemy의 중첩 트랜잭션 (savepoint) 지원이 올바르게 작동하도록 합니다.

```python
with engine.connect() as conn:
    conn.begin()
    conn.begin_nested()  # SAVEPOINT
    conn.execute(text("INSERT INTO ..."))
    conn.rollback()      # ROLLBACK TO SAVEPOINT
    conn.commit()        # 외부 트랜잭션 COMMIT
```

## 서버 버전 감지

dialect는 초기화 시 pycubrid에서 서버 버전을 읽어 튜플로 제공합니다:

```python
with engine.connect() as conn:
    pass  # initialize() 트리거

print(engine.dialect._cubrid_version)  # (11, 4, 0)
print(engine.dialect.server_version_info)  # (11, 4, 0)
```

이 버전 정보는 조건부 동작에 내부적으로 사용됩니다 (예: `db_serial` 카탈로그 컬럼이 CUBRID 11.4에서 `att_name`에서 `attr_name`으로 변경됨).
