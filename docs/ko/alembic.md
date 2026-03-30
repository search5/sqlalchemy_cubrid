# Alembic 통합

이 페이지에서는 Alembic 마이그레이션 지원과 쿼리 추적 유틸리티를 다룹니다.

## 개요

sqlalchemy-cubrid는 `CubridImpl` 클래스를 통해 Alembic 통합을 제공하며, 이 클래스는 엔트리 포인트로 자동 등록됩니다. 이를 통해 Alembic이 마이그레이션 중에 CUBRID 호환 DDL을 생성하고 실행할 수 있습니다.

## 설정

### 엔트리 포인트 등록

dialect는 `pyproject.toml`을 통해 자동 등록됩니다:

```toml
[tool.poetry.plugins."alembic.ddl"]
cubrid = "sqlalchemy_cubrid.alembic_impl:CubridImpl"
```

Alembic이 CUBRID 연결 URL을 감지하면 자동으로 `CubridImpl`을 사용합니다.

### Alembic 설정

표준 `alembic.ini`가 CUBRID와 함께 작동합니다:

```ini
[alembic]
script_location = alembic
sqlalchemy.url = cubrid://dba:@localhost:33000/testdb
```

### Alembic 초기화

```bash
alembic init alembic
```

그런 다음 `alembic/env.py`를 편집하여 모델을 임포트합니다:

```python
from myapp.models import Base
target_metadata = Base.metadata
```

## CubridImpl

`CubridImpl` 클래스는 Alembic의 `DefaultImpl`을 CUBRID 전용 동작으로 확장합니다.

### transactional_ddl = False

!!! warning
    CUBRID는 DDL 구문을 자동 커밋합니다. 이는 실패한 마이그레이션을 **롤백할 수 없음**을 의미합니다. 각 DDL 구문 (CREATE TABLE, ALTER TABLE, DROP TABLE 등)은 즉시 커밋됩니다.

이로 인해 `CubridImpl`은 `transactional_ddl = False`를 설정하여 DDL 작업이 비트랜잭션임을 Alembic에 알립니다.

```python
class CubridImpl(DefaultImpl):
    __dialect__ = "cubrid"
    transactional_ddl = False
```

### render_type()

`render_type()` 메서드는 자동 생성된 마이그레이션 스크립트에서 CUBRID 컬렉션 타입을 처리합니다. Alembic이 `CubridSet`, `CubridMultiset`, `CubridList` 컬럼을 포함하는 마이그레이션을 생성할 때 임포트 가능한 Python 코드를 생성합니다:

```python
# 자동 생성된 마이그레이션에 포함될 내용:
from sqlalchemy_cubrid.types import CubridSet

op.add_column("products", sa.Column("tags", CubridSet("VARCHAR(50)")))
```

표준 SQLAlchemy 타입의 경우 `render_type()`은 부모 클래스에 위임합니다.

### compare_type()

`compare_type()` 메서드는 `alembic --autogenerate` 시 컬렉션 타입에 대한 지능적 타입 비교를 제공합니다:

- **같은 컬렉션 종류, 같은 요소 타입** -- 변경 없음으로 감지
- **같은 컬렉션 종류, 다른 요소 타입** -- 변경으로 감지 (대소문자 무시 비교)
- **다른 컬렉션 종류** (예: SET vs LIST) -- 변경으로 감지
- **컬렉션 vs 비컬렉션** -- 변경으로 감지
- **표준 타입** -- 부모 클래스에 위임

```python
# 예시: 다음은 동일하게 간주됩니다 (대소문자 무시):
# 데이터베이스:  CubridSet("varchar(50)")
# 모델:         CubridSet("VARCHAR(50)")

# 예시: 다음은 마이그레이션을 트리거합니다:
# 데이터베이스:  CubridSet("VARCHAR(50)")
# 모델:         CubridSet("VARCHAR(100)")
```

## 마이그레이션 워크플로

### 마이그레이션 생성

```bash
alembic revision --autogenerate -m "add products table"
```

### 생성된 마이그레이션 검토

```python
"""add products table

Revision ID: a1b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy_cubrid.types import CubridSet


def upgrade():
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("tags", CubridSet("VARCHAR(50)")),
    )


def downgrade():
    op.drop_table("products")
```

### 마이그레이션 적용

```bash
alembic upgrade head
```

### 롤백

```bash
alembic downgrade -1
```

!!! warning
    CUBRID가 DDL을 자동 커밋하므로 실패한 `upgrade`가 데이터베이스를 부분적으로 마이그레이션된 상태로 남길 수 있습니다. 적용 전에 항상 마이그레이션을 신중하게 검토하십시오.

## CUBRID 마이그레이션 모범 사례

1. **마이그레이션을 작게 유지하십시오.** DDL이 자동 커밋되므로 각 마이그레이션은 단일 논리적 변경이어야 합니다. 다단계 마이그레이션이 도중에 실패하면 수동 정리가 필요합니다.

2. **복사본에서 마이그레이션을 테스트하십시오.** 항상 비프로덕션 데이터베이스에서 먼저 테스트하십시오.

3. **큰 테이블에서 ALTER TABLE을 피하십시오.** CUBRID의 ALTER TABLE은 큰 테이블에서 느릴 수 있습니다. 새 테이블을 생성하고 데이터를 마이그레이션하는 것을 고려하십시오.

4. **AUTO_INCREMENT 제한을 확인하십시오.** CUBRID는 테이블당 AUTO_INCREMENT 컬럼을 하나만 허용한다는 점을 기억하십시오.

5. **명시적 시리얼 이름을 사용하십시오.** 시퀀스 (시리얼)를 사용할 때 Alembic이 올바르게 추적할 수 있도록 명시적 이름을 지정하십시오.

## 쿼리 추적

sqlalchemy-cubrid에는 CUBRID의 `SET TRACE ON` / `SHOW TRACE` 명령을 사용하는 내장 쿼리 추적 유틸리티가 포함되어 있습니다. 이는 성능 문제를 디버깅하고 쿼리 실행 계획을 이해하는 데 유용합니다.

### trace_query()

추적을 활성화하고 쿼리를 실행한 후 결과와 추적 출력을 모두 반환하는 일회성 함수입니다:

```python
from sqlalchemy_cubrid import trace_query
from sqlalchemy import text

with engine.connect() as conn:
    result, trace_output = trace_query(
        conn,
        "SELECT * FROM employees WHERE department_id = :dept",
        {"dept": 10},
    )
    print(trace_output)
    # Trace Statistics:
    #   SELECT (time: 1, fetch: 0, ioread: 0)
    #   ...
```

#### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `connection` | Connection | 필수 | SQLAlchemy 연결 |
| `sql`        | str/text   | 필수 | SQL 문자열 또는 text() 구문 |
| `params`     | dict       | `None`   | 바인드 파라미터 |
| `output`     | str        | `"TEXT"` | 출력 형식: `"TEXT"` 또는 `"JSON"` |

#### JSON 출력

```python
result, trace_json = trace_query(
    conn,
    "SELECT * FROM employees",
    output="JSON",
)

import json
trace_data = json.loads(trace_json)
print(json.dumps(trace_data, indent=2))
```

### QueryTracer 컨텍스트 관리자

블록 내에서 여러 쿼리를 추적하는 경우:

```python
from sqlalchemy_cubrid import QueryTracer
from sqlalchemy import text

with engine.connect() as conn:
    with QueryTracer(conn, output="TEXT") as tracer:
        conn.execute(text("SELECT * FROM employees"))
        conn.execute(text("SELECT * FROM departments"))

    # 추적 출력은 컨텍스트 관리자가 종료될 때 캡처됩니다
    # 출력을 가져오려면 start/stop을 명시적으로 사용하십시오:

    tracer = QueryTracer(conn, output="JSON")
    tracer.start()
    conn.execute(text("SELECT * FROM employees WHERE id = 1"))
    conn.execute(text("UPDATE employees SET name = 'Test' WHERE id = 1"))
    trace_output = tracer.stop()
    print(trace_output)
```

#### 수동 시작/중지

```python
tracer = QueryTracer(conn, output="TEXT")
tracer.start()

# 여러 구문 실행
conn.execute(text("SELECT ..."))
conn.execute(text("UPDATE ..."))

# 축적된 추적 가져오기
trace_output = tracer.stop()
print(trace_output)
```

### 추적 작동 방식

내부적으로 추적 유틸리티는 다음 CUBRID 명령을 실행합니다:

1. `SET TRACE ON OUTPUT TEXT` (또는 `JSON`) -- 추적 활성화
2. SQL 구문이 정상적으로 실행됩니다
3. `SHOW TRACE` -- 축적된 추적 데이터 조회
4. `SET TRACE OFF` -- 추적 비활성화

추적 출력에는 CUBRID 쿼리 엔진의 실행 계획, 타이밍 정보, I/O 통계 및 기타 성능 메트릭이 포함됩니다.

## 임포트 참조

```python
# Alembic 통합 (일반적으로 엔트리 포인트를 통해 자동)
from sqlalchemy_cubrid.alembic_impl import CubridImpl

# 쿼리 추적
from sqlalchemy_cubrid import trace_query, QueryTracer

# 또는 서브모듈에서
from sqlalchemy_cubrid.trace import trace_query, QueryTracer
```
